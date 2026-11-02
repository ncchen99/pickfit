"""L2 for q16 (eval/fixtures/q16/README.md), run 1, experimental (llama.cpp llama-server + EuroLLM-9B-Instruct
GGUF + the answer's md2ptpt.py). Dev image, 4 vCPU 16 GB, one box.

  uv run python eval/results/l2/scripts/q16.py

Recorded choices: install lines in one bash (README section 2), apt's prompt answered with the default; the
answer's script saved verbatim as /work/md2ptpt.py and run from /work with docs/ = /work/docs (its own example,
`nohup python3 md2ptpt.py docs/ docs-pt-PT/ ... &`, followed by a grader `wait`); the server is started as the
answer writes it, in the same run.sh, so that it and the script share one --block-network namespace; the grader
waits for /health before the script starts. The answer fixes temperature 0 (server --temp 0, requests
"temperature": 0), so only translation 1 is run (section 2). L2-5 (pinned language identifier) and L2-7 (meaning
judge) are not run: calibration.md never recorded either choice.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "eval" / "runner"))
from l2_boxes import Flow  # noqa: E402

OUT = ROOT / "eval" / "results" / "l2" / "q16-experimental"
LIB = (Path(__file__).resolve().parent / "_lib.sh").read_text()
ANSWER = (ROOT / "eval/results/runs/run1/q16/experimental/attempt-1/answer.md").read_text()
SCRIPT = re.findall(r"```python\n(.*?)```", ANSWER, re.S)[0]
INSTALL = """TTY:sudo apt install build-essential cmake git libcurl4-openssl-dev python3
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
cmake -B build && cmake --build build --config Release -j"""
RUN = r"""cd /work/llama.cpp
./build/bin/llama-server -hf bartowski/EuroLLM-9B-Instruct-GGUF:Q4_K_M \
  --jinja -c 4096 --temp 0 --host 127.0.0.1 --port 8080 > /results/server-$Q16_RUN.log 2>&1 &
SRV=$!
for i in $(seq 1 900); do curl -sf http://127.0.0.1:8080/health > /dev/null && break; kill -0 $SRV 2> /dev/null || break; sleep 2; done
cd /work
nohup python3 md2ptpt.py docs/ docs-pt-PT/ > translate.log 2>&1 &
wait $!
rc=$?
kill $SRV 2> /dev/null
exit $rc
"""
EGB = "python3 $SHARED/egress.py run --out /results/eg --block-network"

with Flow("q16-experimental", OUT, ["q16", "_shared"], cpu=4.0, memory=16384, timeout=7200) as flow:
    t = flow.box("T")
    t.sh("nproc; command -v nvidia-smi || echo no-gpu", "box check")
    t.sh("apt-get update -qq > /dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sudo > /dev/null", "environment: sudo (9.3 A)")
    t.put("/results/install.lines", (INSTALL + "\n").encode())
    t.put("/results/run.sh", RUN.encode())
    t.put("/results/lib.sh", LIB.encode())
    t.put("/work/md2ptpt.py", SCRIPT.encode())
    t.sh("cd /work && OUT=/results; . /results/lib.sh; run_lines install /results/install.lines; "
         "all_ok install && echo INSTALL-OK || echo INSTALL-FAIL", "L2-1 install (one shell)", timeout=2400)
    t.sh("rm -rf /work/docs /work/docs-pt-PT && cp -r $F/q16/warmup /work/docs && Q16_RUN=warmup bash /results/run.sh; "
         "echo warmup exit $?; tail -5 /results/server-warmup.log; tail -5 /work/translate.log; ls -R /work/docs-pt-PT; "
         "rm -rf /work/docs /work/docs-pt-PT /work/translate.log", "warmup (network open; model download)", timeout=3600)
    t.sh("rm -rf /work/docs && cp -r $F/q16/docs /work/docs", "input: docs")
    t.sh(f"{EGB} --label probe-before --no-trace -- python3 $SHARED/egress.py probe --json /results/probe-before.json; echo probe exit $?", "probe before")
    t.sh(f"Q16_RUN=1 {EGB} --label translate-1 --timeout 1800 -- bash /results/run.sh; echo translate-1 exit $?; "
         "cat /results/eg/translate-1.json | head -c 600; tail -8 /work/translate.log", "translate 1 (blocked, traced)", timeout=2400)
    t.sh("python3 $SHARED/egress.py stop --out /results/eg --kill", "egress stop")
    t.sh(f"{EGB} --label probe-after --no-trace -- python3 $SHARED/egress.py probe --json /results/probe-after.json; echo probe exit $?", "probe after")
    t.sh("python3 $SHARED/egress.py report --out /results/eg --labels translate-1 --json /results/egress.json; echo report exit $?", "L2-2 egress report")
    t.sh("rm -rf /results/out-1 && cp -r /work/docs-pt-PT /results/out-1 && cp /work/translate.log /results/translate-1.log; ls -R /results/out-1", "keep output 1")
    t.sh("cd /results && python3 $F/q16/md_check.py --output out-1 --run-log eg/translate-1.json --out md-1.json; echo md_check exit $?; "
         "python3 -c \"import json; d=json.load(open('md-1.json')); print(json.dumps(d.get('items'), ensure_ascii=False))\"", "L2-3, L2-4, L2-6 md_check")
    t.sh("cd /results && tar czf /tmp/keep.tgz install.lines run.sh steps.txt probe-before.json probe-after.json egress.json "
         "eg/translate-1.json md-1.json out-1 translate-1.log server-1.log server-warmup.log install-*.txt 2> /dev/null; ls -l /tmp/keep.tgz", "pack results")
    (OUT / "results.tgz").write_bytes(t.get("/tmp/keep.tgz"))
