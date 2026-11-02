"""L2 for q15 (eval/fixtures/q15/README.md sections 2-4), run 1: test box T and baseline box BL, dev image 4 vCPU 16 GB.

  uv run python eval/results/l2/scripts/q15.py control|experimental

Recorded choices: the answer's lines run in one bash (README section 2) with each exit code kept; its input
placeholder `meeting.m4a` is filled with /work/input/meeting.wav (the clip), because the answer's own first
step writes `meeting.wav` and the fixture's fixed name would make ffmpeg overwrite its input; the run starts in
the whisper.cpp folder the install ends in; every timed or traced run is in a --block-network namespace
(section 2: egress blocked after setup); the baseline pins come from eval/fixtures/pins.json (calibration.md's
baseline table is blank); `-t 8` is filled with this box's core count (4): both answers say to set it to
the CPU's physical cores (nproc); the scorers run in T after the answer's runs, with pinned srt and OpenCC dictionaries.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "eval" / "runner"))
from l2_boxes import Flow  # noqa: E402

GROUP = sys.argv[1]
OUT = ROOT / "eval" / "results" / "l2" / f"q15-{GROUP}"
LIB = (Path(__file__).resolve().parent / "_lib.sh").read_text()
PINS = {i["id"]: i for i in json.loads((ROOT / "eval/fixtures/pins.json").read_text())["items"]}

if GROUP == "control":
    INSTALL = """sudo apt update
sudo apt install -y build-essential cmake git ffmpeg opencc
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build
cmake --build build -j --config Release
sh ./models/download-ggml-model.sh large-v3-turbo-q5_0"""
    RUN = """cd /work/whisper.cpp
ffmpeg -i /work/input/meeting.wav -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav
./build/bin/whisper-cli -m models/ggml-large-v3-turbo-q5_0.bin -f meeting.wav -l zh -t 4 --prompt "以下是一場會議的逐字稿，使用繁體中文與全形標點符號。" -osrt
opencc -i meeting.wav.srt -o meeting.zh-TW.srt -c s2twp.json"""
    OUTPUTS = "meeting.wav meeting.wav.srt meeting.zh-TW.srt"
else:
    INSTALL = """TTY:sudo apt install build-essential cmake git ffmpeg opencc
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build -j --config Release
sh ./models/download-ggml-model.sh large-v3-turbo-q5_0
sh ./models/download-vad-model.sh silero-v5.1.2"""
    RUN = """cd /work/whisper.cpp
ffmpeg -i /work/input/meeting.wav -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav
./build/bin/whisper-cli -m models/ggml-large-v3-turbo-q5_0.bin -f meeting.wav -l zh -t 4 --prompt "以下是繁體中文的會議逐字稿。" --vad -vm models/ggml-silero-v5.1.2.bin -osrt -of meeting
opencc -i meeting.srt -o meeting.zh-TW.srt -c s2twp.json"""
    OUTPUTS = "meeting.wav meeting.srt meeting.zh-TW.srt"
FINAL = "/work/whisper.cpp/meeting.zh-TW.srt"
BL_ENV = (f"WHISPER_VERSION={PINS['openai-whisper']['version']} TORCH_VERSION={PINS['torch-cpu']['version']} "
          f"TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu SMALL_PT_SHA256={PINS['whisper-small.pt']['verified_sha256']}")
EGB = "python3 $SHARED/egress.py run --out /results/eg --block-network"
CLEAN = f"cd /work/whisper.cpp && rm -f {OUTPUTS}"


def fetch_pin(box, pid: str, dest: str) -> None:
    p = PINS[pid]
    box.sh(f"mkdir -p $(dirname {dest}) && curl -fsSL -o {dest} '{p['url']}' && echo '{p['verified_sha256']}  {dest}' | sha256sum -c -",
           f"grader pin {pid}")


with Flow(f"q15-{GROUP}", OUT, ["q15", "_shared", "pins.json"], cpu=4.0, memory=16384, timeout=5400) as flow:
    t, bl = flow.box("T"), flow.box("BL")
    for x in (t, bl):
        x.sh("nproc; command -v nvidia-smi || echo no-gpu; grep -m1 'model name' /proc/cpuinfo", "box check")
    # baseline setup can run while T installs (network open in both)
    bl.sh(f"{BL_ENV} sh $F/q15/baseline/run_baseline.sh setup > /tmp/bl-setup.txt 2>&1; echo exit $?; tail -3 /tmp/bl-setup.txt", "BL setup", timeout=2400)
    t.sh("apt-get update -qq > /dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sudo > /dev/null", "environment: sudo (9.3 A)")
    t.put("/results/install.lines", (INSTALL + "\n").encode())
    t.put("/results/run.sh", (RUN + "\n").encode())
    t.put("/results/lib.sh", LIB.encode())
    t.sh("mkdir -p /work/input && cd /work && OUT=/results; . /results/lib.sh; run_lines install /results/install.lines; "
         "all_ok install && echo INSTALL-OK || echo INSTALL-FAIL", "L2-1 install (one shell)", timeout=1200)
    t.sh("cp $F/q15/clip/warmup.wav /work/input/meeting.wav && bash /results/run.sh > /results/warmup.txt 2>&1; "
         f"echo warmup exit $?; ls -l {FINAL}; {CLEAN}", "L2-1 warmup (network open)", timeout=900)
    t.sh("sh $F/q15/check_no_torch.sh / > /results/no-torch.txt 2>&1; echo no-torch exit $?; tail -2 /results/no-torch.txt", "L2-1 no torch")
    t.sh("cp $F/q15/clip/clip.wav /work/input/meeting.wav", "input: clip")
    t.sh(f"{EGB} --label runA --no-trace --timeout 600 -- bash /results/run.sh; echo runA exit $?; cp {FINAL} /results/runA.srt; {CLEAN}", "Run A", timeout=900)
    t.sh(f"{EGB} --label probe-before --no-trace -- python3 $SHARED/egress.py probe --json /results/probe-before.json; echo probe exit $?", "probe before")
    t.sh(f"{EGB} --label runB --timeout 600 -- bash /results/run.sh; echo runB exit $?; cp {FINAL} /results/runB.srt; {CLEAN}", "Run B (traced)", timeout=900)
    t.sh("python3 $SHARED/egress.py stop --out /results/eg --kill", "egress stop")
    t.sh(f"{EGB} --label probe-after --no-trace -- python3 $SHARED/egress.py probe --json /results/probe-after.json; echo probe exit $?", "probe after")
    t.sh("python3 $SHARED/egress.py report --out /results/eg --labels runB --json /results/egress.json; echo report exit $?", "L2-6 egress report")
    t.sh(f"{EGB} --label runC --no-trace --timeout 600 -- bash /results/run.sh; echo runC exit $?; cp {FINAL} /results/runC.srt; {CLEAN}", "Run C", timeout=900)
    bl.sh(f"{EGB} --label baseline-outer --no-trace -- sh $F/q15/baseline/run_baseline.sh time /results/baseline; echo exit $?; cat /results/baseline/baseline.json", "BL time (blocked)", timeout=1200)
    # grader tools in T, after the answer's runs: pinned srt and the four OpenCC dictionaries
    fetch_pin(t, "srt", "/opt/grader/srt.tar.gz")
    t.sh("cd /opt/grader && tar xzf srt.tar.gz && cp srt-3.5.3/srt.py /opt/grader/", "grader: srt module")
    for d in ("STCharacters", "STPhrases", "TSCharacters", "TWVariants"):
        fetch_pin(t, f"opencc-{d}.txt", f"/opt/grader/opencc/{d}.txt")
    for r in "ABC":
        t.sh(f"cd /results && PYTHONPATH=/opt/grader python3 $F/q15/srt_check.py run{r}.srt --out srt{r}.json; "
             f"PYTHONPATH=/opt/grader python3 $F/q15/zh_score.py --dict-dir /opt/grader/opencc all --ref $F/q15/clip/reference.txt "
             f"--srt run{r}.srt --out score{r}.json; tail -c 600 score{r}.json", f"score run {r}")
    for name in ("install.lines", "run.sh", "steps.txt", "warmup.txt", "no-torch.txt", "probe-before.json", "probe-after.json",
                 "egress.json", "runA.srt", "runB.srt", "runC.srt", "srtA.json", "srtB.json", "srtC.json",
                 "scoreA.json", "scoreB.json", "scoreC.json"):
        rc, _ = t.sh(f"test -f /results/{name}", f"has {name}")
        if rc == 0:
            (OUT / name).write_bytes(t.get(f"/results/{name}"))
    for name in ("runA.json", "runB.json", "runC.json"):
        rc, _ = t.sh(f"test -f /results/eg/{name}", f"has eg/{name}")
        if rc == 0:
            (OUT / name).write_bytes(t.get(f"/results/eg/{name}"))
    rc, _ = bl.sh("test -f /results/baseline/baseline.json", "has baseline.json")
    if rc == 0:
        (OUT / "baseline.json").write_bytes(bl.get("/results/baseline/baseline.json"))
