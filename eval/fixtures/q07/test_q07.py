#!/usr/bin/env python3
"""Local self-test of the q07 harness (server modes, check_q07.py, diff_check.py).

    python3 test_q07.py

Uses a throwaway test double instead of a real API tool: a few lines of urllib that send
the three requests of requests.json and exit 1 when the health assertion fails. It only
proves the harness tells exit codes, server logs and diffs apart; it is not a candidate
answer. Needs git for the diff part. Loopback only; strace is covered by calibration.md.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

DOUBLE = r'''
import json, sys, urllib.request, urllib.error
spec = json.load(open(sys.argv[1]))
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
port = sys.argv[2]
bad = 0
for r in spec["requests"]:
    url = r["url"].replace("18081", port)
    data = json.dumps(r["body"]).encode() if r["body"] is not None else None
    req = urllib.request.Request(url, data=data, method=r["method"], headers=r["headers"])
    try:
        resp = op.open(req, timeout=10); status, body = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read()
    if r["assertions"]:
        if status != 200 or json.loads(body).get("ok") is not True:
            bad += 1
sys.exit(1 if bad else 0)
'''


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def run_mode(tmp, mode, port, double):
    log = os.path.join(tmp, "log_%s.jsonl" % mode)
    srv = subprocess.Popen([PY, os.path.join(HERE, "server.py"), "--mode", mode, "--port", str(port), "--log", log],
                           stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    rep = os.path.join(tmp, "eg")
    subprocess.run([PY, os.path.join(HERE, "..", "_shared", "egress.py"), "run", "--out", rep, "--label", mode,
                    "--no-trace", "--timeout", "60", "--", PY, double, os.path.join(HERE, "requests.json"), str(port)],
                   stderr=subprocess.DEVNULL, check=False)
    srv.terminate()
    srv.wait()
    return rep, log


def main():
    tmp = tempfile.mkdtemp(prefix="q07test-")
    double = os.path.join(tmp, "double.py")
    open(double, "w").write(DOUBLE)
    port = free_port()
    reps = {m: run_mode(tmp, m, port, double) for m in ("ok", "status500", "okfalse")}
    r = subprocess.run([PY, os.path.join(HERE, "check_q07.py"), "--runs", reps["ok"][0], "--ok-log", reps["ok"][1]],
                       capture_output=True, text=True)
    v = json.loads(r.stdout)
    results = [("server modes: ok run passes", v["ok_run"]["pass"] is True),
               ("server modes: 500 and ok:false runs exit non-zero", v["fail_runs"]["pass"] is True),
               ("egress not checked without strace -> not pass", v["egress"]["pass"] is False)]

    if shutil.which("git"):
        def project(variant):
            d = os.path.join(tmp, "proj_" + variant)
            os.makedirs(d)
            for name, url in (("health", "/health"), ("widgets", "/widgets"), ("orders", "/orders")):
                with open(os.path.join(d, name + ".req"), "w") as fh:
                    fh.write("# request %s\nGET http://127.0.0.1:18081%s\nAccept: application/json\n" % (name, url))
            subprocess.run([PY, os.path.join(HERE, "diff_check.py"), "init", d], capture_output=True, check=True)
            return d

        def report(d):
            out = subprocess.run([PY, os.path.join(HERE, "diff_check.py"), "report", d, "--file", "widgets.req"],
                                 capture_output=True, text=True)
            return json.loads(out.stdout)["pass"]

        d = project("good")
        subprocess.run([PY, os.path.join(HERE, "diff_check.py"), "edit", d, "--file", "widgets.req",
                        "--from", "/widgets", "--to", "/gadgets"], capture_output=True, check=True)
        results.append(("diff: one-line URL edit passes", report(d) is True))
        d = project("two_files")
        for f in ("widgets.req", "health.req"):
            p = os.path.join(d, f)
            open(p, "w").write(open(p).read().replace("/widgets", "/gadgets").replace("/health", "/gadgets"))
        results.append(("diff: a second file changed fails", report(d) is False))
        d = project("rewrite")
        p = os.path.join(d, "widgets.req")
        open(p, "w").write("# rewritten\n\n\n\nGET http://127.0.0.1:18081/gadgets\nAccept: application/json\nX: 1\n")
        results.append(("diff: whole-file rewrite fails", report(d) is False))
        d = project("binary")
        open(os.path.join(d, "widgets.req"), "wb").write(b"\x00\xff/gadgets\x00")
        results.append(("diff: binary file fails", report(d) is False))
    else:
        print("git not found: diff cases skipped")
    for name, ok in results:
        print("%-4s %s" % ("ok" if ok else "FAIL", name))
    good = all(ok for _, ok in results)
    print("all cases as expected" if good else "SOME CASES FAILED")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
