#!/usr/bin/env python3
"""Self-test for the q19 fixtures (stdlib only, offline, no root). A fake server stands in for the model."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAILS = []
EXPECTED = open(os.path.join(ROOT, "expected_output.txt")).read().rstrip("\n")


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class FakeOpenAI(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    wrong = False

    def log_message(self, *a):
        pass

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send({"object": "list", "data": [{"id": "fake:1", "object": "model"}]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n))
        if "max_tokens" in req and req["max_tokens"] == 1:
            self._send({"choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {"prompt_tokens": 99}})
            return
        if not any(m.get("role") == "tool" for m in req["messages"]):
            line = "Hello from somewhere else" if self.wrong else EXPECTED
            args = json.dumps({"path": "hello.py", "content": "print(%r)\n" % line})
            msg = {"role": "assistant", "content": None,
                   "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "write_file", "arguments": args}}]}
        else:
            msg = {"role": "assistant", "content": "Created hello.py."}
        self._send({"choices": [{"index": 0, "message": msg, "finish_reason": "stop"}]})


FAKE_AGENT = r'''
import json, os, sys, urllib.request
base = os.environ["FAKE_BASE_URL"]
task = sys.argv[1]
def post(body):
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())
msgs = [{"role": "user", "content": task}]
tools = [{"type": "function", "function": {"name": "write_file", "parameters": {"type": "object", "properties": {}}}}]
m = post({"model": "fake:1", "messages": msgs, "tools": tools})["choices"][0]["message"]
for c in m.get("tool_calls") or []:
    a = json.loads(c["function"]["arguments"])
    sys.stdout.write("Write %s? (y/n) " % a["path"]); sys.stdout.flush()
    if sys.stdin.readline().strip() != "y":
        sys.exit(5)
    open(a["path"], "w").write(a["content"])
    msgs += [m, {"role": "tool", "tool_call_id": c["id"], "content": "ok"}]
print(post({"model": "fake:1", "messages": msgs, "tools": tools})["choices"][0]["message"]["content"])
'''


def main():
    up = free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", up), FakeOpenAI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    px = free_port()
    work = tempfile.mkdtemp(prefix="q19-test-")
    state = os.path.join(work, "state")
    os.makedirs(os.path.join(state, "proxy"))
    proxy = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "logging_proxy.py"), "--listen",
                              "127.0.0.1:%d" % px, "--listen", "[::1]:%d" % px, "--upstream", "127.0.0.1:%d" % up,
                              "--log-dir", os.path.join(state, "proxy")], stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", px), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        base = "http://127.0.0.1:%d/v1" % px
        cal = os.path.join(work, "cal.json")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "reference_harness.py"), "--base-url", base,
                            "--model", "fake:1", "--runs", "3", "--probe-prefill", "2000", "--out", cal],
                           capture_output=True, text=True, timeout=120)
        rec = json.load(open(cal))
        check(r.returncode == 0 and rec["passed_runs"] == 3, "reference harness: 3/3 against the fake server")
        check(rec["prefill_probe"].get("seconds") is not None, "reference harness records the prefill probe")

        agent = os.path.join(work, "fake_agent.py")
        open(agent, "w").write(FAKE_AGENT)
        runs = os.path.join(work, "runs")
        task = open(os.path.join(ROOT, "task.txt")).read().strip()

        def one(label, wrong):
            FakeOpenAI.wrong = wrong
            wd = os.path.join(work, "repo-" + label)
            rd = subprocess.run([sys.executable, os.path.join(ROOT, "new_run.py"), "--runs-dir", runs, "--label", label,
                                 "--workdir", wd], capture_output=True, text=True, timeout=60).stdout.strip()
            env = dict(os.environ, FAKE_BASE_URL=base)
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "pty_drive.py"), "--out", os.path.join(rd, "agent"),
                            "--timeout", "60", "--approve", r"\(y/n\)", "--", sys.executable, agent, task],
                           cwd=wd, env=env, capture_output=True, timeout=120)
            time.sleep(0.2)
            return rd, wd

        (r1, w1), (r2, w2), (r3, w3) = one("r1", False), one("r2", True), one("r3", False)
        info = json.load(open(os.path.join(r1, "run.json")))
        check(info["git"] is (subprocess.run(["which", "git"], capture_output=True).returncode == 0),
              "workdir is a git repo when git exists")
        heads = {json.load(open(os.path.join(d, "run.json"))).get("head") for d in (r1, r2, r3)}
        check(len(heads) == 1, "every run starts from the same commit id")
        res = subprocess.run([sys.executable, os.path.join(ROOT, "check_run.py"), "--state-dir", state, r1, r2, r3],
                             capture_output=True, text=True, timeout=60)
        rep = json.loads(res.stdout)
        by = {x["run"]: x for x in rep["runs"]}
        check(by["r1"]["pass"] and by["r3"]["pass"] and not by["r2"]["pass"], "right string passes, wrong string fails")
        check(rep["L2-2"] == "pass" and rep["server_log_shows_requests"], "2 of 3 -> L2-2 pass; server log shows requests")
        check(rep["L2-3"] == "undetermined" and rep["egress"] == "not checked", "L2-3 stays undetermined without an egress report")
        check(all(by[k]["server_requests"] == 2 for k in by), "proxy log shows both agent requests per run")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "check_hello.py"), w2], capture_output=True, text=True)
        check(r.returncode == 1, "check_hello rejects a different line")
    finally:
        proxy.terminate()
        proxy.wait(5)
        srv.shutdown()
    print("\n%d failure(s)" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
