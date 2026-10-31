#!/usr/bin/env python3
"""Self-test for the q17 fixtures (stdlib only, offline): corpus, verifier, answer checker."""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAILS = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


FAKE_TOOL = r'''
import json, sys, time
qs = json.load(open(sys.argv[1]))["questions"]
mode = sys.argv[3]
q = sys.argv[2]
item = [x for x in qs if x["question"] == q][0]
n = int(item["id"].split("-")[1])
if mode == "good" or (mode == "one_wrong" and n != 3):
    print("Answer: " + item["token"])
    print("Source: notes/" + item["source_file"])
elif mode == "one_wrong":
    print("Answer: I could not find it.")
    print("Source: notes/autumn-baking-log.md")
elif mode == "dump":
    print("Answer: " + item["token"])
    print("Sources: " + ", ".join(sorted(__import__("os").listdir(sys.argv[4]))[:8]) + ", " + item["source_file"])
elif mode == "slow":
    time.sleep(5)
    print(item["token"])
'''


def run_all(tmp, mode, limit="180", extra=None):
    tool = os.path.join(tmp, "fake_tool.py")
    with open(tool, "w") as f:
        f.write(FAKE_TOOL)
    run = os.path.join(tmp, "run-" + mode)
    with open(os.path.join(ROOT, "questions.json")) as f:
        qs = json.load(f)["questions"]
    for q in qs:
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "pty_drive.py"), "--out", os.path.join(run, q["id"]),
                        "--timeout", "3" if mode == "slow" else "60", "--",
                        sys.executable, tool, os.path.join(ROOT, "questions.json"), q["question"], mode,
                        os.path.join(ROOT, "corpus")],
                       capture_output=True, timeout=120)
    rep_path = os.path.join(run, "egress-report.json")
    with open(rep_path, "w") as f:
        json.dump({"result": "pass"}, f)
    cmd = [sys.executable, os.path.join(ROOT, "check_answers.py"), "--run-dir", run, "--egress-report", rep_path,
           "--time-limit", limit] + (extra or [])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.returncode, json.loads(r.stdout)


def main():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "verify_corpus.py"), "--regenerate"],
                       capture_output=True, text=True, timeout=120)
    check(r.returncode == 0, "verify_corpus --regenerate: " + r.stdout.strip().splitlines()[-1])
    tmp = tempfile.mkdtemp(prefix="q17-test-")
    rc, rep = run_all(tmp, "good")
    check(rc == 0 and rep["L2-2"] == "pass" and rep["L2-3"] == "pass", "all-correct answers pass L2-2 and L2-3")
    rc, rep = run_all(tmp, "one_wrong")
    check(rep["tokens_found"] == 4 and rep["L2-2"] == "pass", "4 of 5 tokens with both PDF ones still pass L2-2")
    check(rep["citations_pass"] == 4 and rep["L2-3"] == "pass", "4 of 5 citations pass L2-3")
    rc, rep = run_all(tmp, "dump")
    check(rep["L2-3"] == "pending" and rep["citations_manual"] == 5, "listing >5 files makes citations 'manual'")
    rc, rep = run_all(tmp, "slow", limit="180")
    check(rep["L2-2"] == "fail" and not rep["all_answered_in_time"], "a run killed at its time limit fails L2-2")
    print("\n%d failure(s)" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
