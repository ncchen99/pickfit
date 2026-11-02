"""P3.13 fixture: a GPU box with the simulated microphone, checked end to end without a model.

In one Modal box (gVisor, GPU, microphone), as the box user:
1. GPU: a vector-add kernel, written in PTX, loaded and launched through libcuda with ctypes (the driver compiles
   PTX itself, so no CUDA toolkit is needed); pickfit picks the inputs and checks the sums.
2. Microphone: faster-whisper (MIT) with the Whisper base.en model (MIT) on that GPU, wrapped in a 12-line
   "dictation tool" that records 10 s from the default device with arecord and prints or saves the transcript;
   pickfit checks it with listen (audio.run_listen), on its output and on the file it writes. The CPU is the
   fallback when the GPU libraries do not load.
Evidence goes to runs/verify/p3-13-fixture-<time>/: report.json (every command, its output and pickfit's lines)
and the WAV files pickfit played (copied out by root).

    uv run python scripts/gpu_mic_fixture.py [--gpu T4] [--cpu-whisper]
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import asdict
from pathlib import Path

from pickfit.ledger import taipei_now
from pickfit.verify.agent import _runs_dir
from pickfit.verify.audio import ListenArgs, run_listen
from pickfit.verify.box import BoxLimits
from pickfit.verify.modal_box import ModalBox

PTX = r"""
.version 6.0
.target sm_50
.address_size 64
.visible .entry add(.param .u64 a, .param .u64 b, .param .u64 c, .param .u32 n)
{
  .reg .pred %p<2>; .reg .b32 %r<6>; .reg .f32 %f<4>; .reg .b64 %rd<11>;
  ld.param.u64 %rd1, [a]; ld.param.u64 %rd2, [b]; ld.param.u64 %rd3, [c]; ld.param.u32 %r2, [n];
  mov.u32 %r3, %ctaid.x; mov.u32 %r4, %ntid.x; mov.u32 %r5, %tid.x;
  mad.lo.s32 %r1, %r3, %r4, %r5;
  setp.ge.s32 %p1, %r1, %r2;
  @%p1 bra DONE;
  cvta.to.global.u64 %rd4, %rd1; cvta.to.global.u64 %rd5, %rd2; cvta.to.global.u64 %rd6, %rd3;
  mul.wide.s32 %rd7, %r1, 4;
  add.s64 %rd8, %rd4, %rd7; add.s64 %rd9, %rd5, %rd7; add.s64 %rd10, %rd6, %rd7;
  ld.global.f32 %f1, [%rd8]; ld.global.f32 %f2, [%rd9]; add.f32 %f3, %f1, %f2; st.global.f32 [%rd10], %f3;
DONE:
  ret;
}
"""

# The box user's CUDA driver program: reads n, then a and b (floats) from argv's JSON; prints the device and c.
CUDA_PY = r"""import ctypes, json, sys
P = json.loads(sys.argv[1])
cu = ctypes.CDLL("libcuda.so.1")
def ok(r, what):
    if r:
        raise SystemExit(f"{what} failed: CUDA error {r}")
n = len(P["a"])
ok(cu.cuInit(0), "cuInit")
dev, ctx, mod, fn = ctypes.c_int(), ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
ok(cu.cuDeviceGet(ctypes.byref(dev), 0), "cuDeviceGet")
name = ctypes.create_string_buffer(100)
ok(cu.cuDeviceGetName(name, 100, dev), "cuDeviceGetName")
ok(cu.cuCtxCreate_v2(ctypes.byref(ctx), 0, dev), "cuCtxCreate")
ok(cu.cuModuleLoadData(ctypes.byref(mod), ctypes.c_char_p(P["ptx"].encode())), "cuModuleLoadData")
ok(cu.cuModuleGetFunction(ctypes.byref(fn), mod, b"add"), "cuModuleGetFunction")
F = ctypes.c_float * n
a, b, c = F(*P["a"]), F(*P["b"]), F()
ptrs = [ctypes.c_uint64() for _ in range(3)]
for p in ptrs:
    ok(cu.cuMemAlloc_v2(ctypes.byref(p), ctypes.sizeof(F)), "cuMemAlloc")
ok(cu.cuMemcpyHtoD_v2(ptrs[0], a, ctypes.sizeof(F)), "copy a")
ok(cu.cuMemcpyHtoD_v2(ptrs[1], b, ctypes.sizeof(F)), "copy b")
count = ctypes.c_uint32(n)
args = (ctypes.c_void_p * 4)(*[ctypes.cast(ctypes.byref(x), ctypes.c_void_p) for x in (*ptrs, count)])
ok(cu.cuLaunchKernel(fn, (n + 255) // 256, 1, 1, 256, 1, 1, 0, None, args, None), "cuLaunchKernel")
ok(cu.cuCtxSynchronize(), "cuCtxSynchronize")
ok(cu.cuMemcpyDtoH_v2(c, ptrs[2], ctypes.sizeof(F)), "copy c")
print(json.dumps({"device": name.value.decode(), "c": list(c)}))
"""

# A 12-line dictation tool: record from the default device, transcribe with Whisper, print or save the text.
DICTATE_PY = r"""import os, subprocess, sys, tempfile, wave
import numpy as np
from faster_whisper import WhisperModel
out = sys.argv[1] if len(sys.argv) > 1 else None
wav = os.path.join(tempfile.mkdtemp(), "rec.wav")
subprocess.run(["arecord", "-q", "-d", "10", "-f", "S16_LE", "-r", "16000", "-c", "1", wav], check=True)
w = wave.open(wav)
audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
device = os.environ.get("DICTATE_DEVICE", "cuda")
model = WhisperModel(os.path.expanduser("~/models/base.en"), device=device, compute_type="float16" if device == "cuda" else "int8")
text = " ".join(s.text.strip() for s in model.transcribe(audio, language="en")[0])
print(f"whisper base.en on {device}", file=sys.stderr)
open(out, "w").write(text + "\n") if out else print(text)
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gpu", default="T4", choices=["T4", "L4"])
    parser.add_argument("--cpu-whisper", action="store_true", help="transcribe on the CPU (the GPU part still runs)")
    args = parser.parse_args()
    stamp = taipei_now().strftime("%Y%m%d-%H%M%S")
    out_dir = _runs_dir(None) / "verify" / f"p3-13-fixture-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"checked_at": taipei_now().isoformat(timespec="seconds"), "gpu_requested": args.gpu, "steps": []}
    box = ModalBox(gpu=args.gpu, audio=True, limits=BoxLimits(lifetime_s=1800),
                   tags={"pickfit": "verify", "pickfit.role": "p3-13-fixture"})
    began = time.monotonic()
    box.start()
    report.update(runner=box.runner, image=box.image, gpu=box.gpu_name, start_s=box.start_s)
    print(f"box {box.runner} · {box.image} · GPU {box.gpu_name} · started in {box.start_s}s")

    def run(what: str, command: str, timeout: int = 600) -> tuple[dict, str]:
        r = box.exec(command, timeout)
        step = {"what": what, "command": command[:400], "exit_code": r.exit_code, "seconds": r.seconds,
                "stdout": r.stdout[-3000:], "stderr": r.stderr[-1500:]}
        report["steps"].append(step)
        print(f"  {what}: exit {r.exit_code} · {r.seconds:.0f}s · {(r.stdout or r.stderr).strip()[-160:]}")
        return step, r.stdout

    try:
        # 1. A kernel on the GPU, as the box user.
        a = [round(random.uniform(-100, 100), 3) for _ in range(256)]
        b = [round(random.uniform(-100, 100), 3) for _ in range(256)]
        box.write_file("cuda_add.py", CUDA_PY)
        payload = json.dumps({"ptx": PTX, "a": a, "b": b})
        box.write_file("cuda_in.json", payload)
        step, full = run("gpu kernel", "python3 cuda_add.py \"$(cat cuda_in.json)\"", 120)
        try:
            got = json.loads(full.strip().splitlines()[-1])
            worst = max(abs(x + y - z) for x, y, z in zip(a, b, got["c"]))
            report["gpu_check"] = {"device": got["device"], "elements": len(got["c"]), "max_error": worst,
                                   "passed": len(got["c"]) == len(a) and worst < 1e-3}
        except (ValueError, KeyError, IndexError) as err:
            report["gpu_check"] = {"passed": False, "why": f"no result: {err}"}
        print(f"  gpu check: {report['gpu_check']}")
        # 2. The dictation tool: Whisper base.en, on the GPU unless asked otherwise.
        run("install faster-whisper", "pip install --user -q faster-whisper nvidia-cublas-cu12 'nvidia-cudnn-cu12==9.*'", 900)
        run("download base.en", "python3 -c \"from huggingface_hub import snapshot_download; "
            "snapshot_download('Systran/faster-whisper-base.en', local_dir='/home/sbx/models/base.en')\"", 600)
        box.write_file("dictate.py", DICTATE_PY)
        libs = ("LD_LIBRARY_PATH=$(python3 -c 'import os, nvidia.cublas, nvidia.cudnn; "
                "print(\":\".join(os.path.join(m.__path__[0], \"lib\") for m in (nvidia.cublas, nvidia.cudnn)))') ")
        device = "DICTATE_DEVICE=cpu " if args.cpu_whisper else ""
        checks = []
        for kind, command in (("output", f"{libs}{device}python3 dictate.py"),
                              ("file", f"mkdir -p ~/pickfit-out && {libs}{device}python3 dictate.py ~/pickfit-out/dictation.txt")):
            spec = ListenArgs(command=command, timeout_s=300, feature=1,
                              check={"kind": kind, "path": "~/pickfit-out/dictation.txt" if kind == "file" else None})
            result, heard = run_listen(box, spec, f"fixture-{kind}", log=print)
            entry = {"kind": kind, "exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr[-1500:],
                     "listen": asdict(heard)}
            if heard.speech:
                try:
                    wav = box.harness_read(heard.speech, 4_000_000)
                    (out_dir / f"spoken-{kind}.wav").write_bytes(wav)
                    entry["spoken_wav"] = f"spoken-{kind}.wav"
                except Exception as err:  # noqa: BLE001 - evidence only
                    entry["spoken_wav_error"] = str(err)
            checks.append(entry)
            print(result.stdout)
        report["mic_checks"] = checks
        report["passed"] = report["gpu_check"].get("passed") and all(c["listen"]["passed"] for c in checks)
    finally:
        box.close()
        report["seconds"] = round(time.monotonic() - began, 1)
        report["modal_usd_estimate"] = round(report["seconds"] * box.usd_per_second(), 4)
        (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"fixture {'passed' if report.get('passed') else 'FAILED'} · {report['seconds']:.0f}s · "
          f"Modal ~${report['modal_usd_estimate']} · {out_dir}")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
