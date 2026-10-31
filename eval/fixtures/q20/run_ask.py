#!/usr/bin/env python3
"""Run the (modified) q20 script once in a clean environment and record the result (stdlib only).

  python3 run_ask.py --script /eval-work/q20/ask.py --python /opt/q20-venv/bin/python \
      [--env OPENAI_BASE_URL=http://localhost:11434/v1 --env OPENAI_API_KEY=ollama] \
      [--egress-dir /eval-work/q20/egress --label blocked] --out /eval-work/q20/runs/online

The script runs with only PATH, HOME, LANG and the --env pairs the answer gives;
every other OPENAI_* variable is absent, so OPENAI_API_KEY is unset unless the
answer sets it. With --egress-dir the run is wrapped by the shared egress check
(eval/fixtures/_shared/egress.py run --label LABEL --inherit-output).
Pass: exit code 0 and non-empty stdout (the frozen script exits non-zero on an
empty completion). Writes OUT.json (and OUT.stdout / OUT.stderr). Exit 0 on pass.
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.environ.get("SHARED") or os.path.join(HERE, "..", "_shared")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--script", required=True)
    ap.add_argument("--python", default="python3")
    ap.add_argument("--env", action="append", default=[], help="KEY=VALUE from the answer; may be repeated")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--egress-dir")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/root"),
           "LANG": "C.UTF-8"}
    given = []
    for kv in a.env:
        k, _, v = kv.partition("=")
        env[k] = v
        given.append(k)
    cmd = [a.python, os.path.basename(a.script)]
    if a.egress_dir:
        cmd = [sys.executable, os.path.join(SHARED, "egress.py"), "run", "--out", a.egress_dir,
               "--label", a.label, "--inherit-output", "--"] + cmd
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    t0 = time.time()
    rec = {"cmd": cmd, "env_names": sorted(env), "env_from_answer": given, "start": t0}
    try:
        p = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(a.script)), env=env,
                           capture_output=True, timeout=a.timeout)
        out, err, rc = p.stdout, p.stderr, p.returncode
        rec["timed_out"] = False
    except subprocess.TimeoutExpired as e:
        out, err, rc = e.stdout or b"", e.stderr or b"", None
        rec["timed_out"] = True
    rec["end"] = time.time()
    rec["elapsed"] = round(rec["end"] - t0, 3)
    rec["exit_code"] = rc
    text = out.decode("utf-8", "replace")
    rec["stdout"] = text[:2000]
    rec["stderr_tail"] = err.decode("utf-8", "replace")[-2000:]
    rec["pass"] = rc == 0 and bool(text.strip())
    with open(a.out + ".stdout", "wb") as f:
        f.write(out)
    with open(a.out + ".stderr", "wb") as f:
        f.write(err)
    with open(a.out + ".json", "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    print(json.dumps({k: rec[k] for k in ("pass", "exit_code", "elapsed", "timed_out")}))
    return 0 if rec["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
