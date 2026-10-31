#!/usr/bin/env python3
"""Self-test for the q20 fixtures (stdlib only, offline, no root).

The end-to-end part needs a Python that can `import openai`; give it with
Q20_OPENAI_PYTHON=/path/to/venv/bin/python (skipped otherwise). A fake
OpenAI-compatible server stands in for the model server.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASK = os.path.join(ROOT, "script", "ask.py")
FAILS = []


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


def py(*args):
    return subprocess.run([sys.executable] + list(args), capture_output=True, text=True, timeout=120)


def test_base_url():
    good = ["http://localhost:11434/v1", "http://127.0.0.1:11434/v1/", "http://LOCALHOST:11434/v1"]
    bad = ["http://localhost:11434", "https://localhost:11434/v1", "http://0.0.0.0:11434/v1",
           "http://localhost:4000/v1", "http://localhost:11434/v1/chat/completions", "http://localhost:11434/api"]
    for u in good:
        check(py(os.path.join(ROOT, "check_base_url.py"), u).returncode == 0, "base_url accepted: " + u)
    for u in bad:
        check(py(os.path.join(ROOT, "check_base_url.py"), u).returncode == 1, "base_url rejected: " + u)


def variant(tmp, name, old, new):
    src = open(ASK).read()
    assert old in src, old
    p = os.path.join(tmp, name, "ask.py")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(src.replace(old, new))
    return p


def test_diff(tmp):
    a = variant(tmp, "full", 'client = OpenAI()', 'client = OpenAI(\n    base_url="http://localhost:11434/v1",  # local\n    api_key="ollama",\n)')
    a = open(a).read().replace('model="gpt-4o-mini"', 'model="small:1"')
    open(os.path.join(tmp, "full", "ask.py"), "w").write(a)
    r = py(os.path.join(ROOT, "check_script_diff.py"), ASK, os.path.join(tmp, "full", "ask.py"))
    rep = json.loads(r.stdout)
    check(r.returncode == 0 and rep["base_url"] == "http://localhost:11434/v1" and rep["model"] == "small:1",
          "diff: base_url + api_key + model only -> allowed, values reported")
    m = variant(tmp, "model_only", 'model="gpt-4o-mini"', 'model="small:1"')
    check(py(os.path.join(ROOT, "check_script_diff.py"), ASK, m).returncode == 0, "diff: model only (env vars for the rest) -> allowed")
    x = variant(tmp, "extra", 'from openai import OpenAI', 'import os\nfrom openai import OpenAI')
    check(py(os.path.join(ROOT, "check_script_diff.py"), ASK, x).returncode == 1, "diff: an added import -> not allowed")
    y = variant(tmp, "prompt", 'what is a lighthouse for?', 'what is a harbour for?')
    check(py(os.path.join(ROOT, "check_script_diff.py"), ASK, y).returncode == 1, "diff: a changed prompt -> not allowed")


class Fake(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    empty = False

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n))
        content = "" if self.empty else "A lighthouse warns ships away from danger."
        body = json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": req.get("model"),
                           "choices": [{"index": 0, "finish_reason": "stop",
                                        "message": {"role": "assistant", "content": content}}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_e2e(tmp, openai_py):
    port = free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/v1" % port
    try:
        full = variant(tmp, "e2e_full", 'client = OpenAI()', 'client = OpenAI(base_url="%s", api_key="ollama")' % base)
        r = py(os.path.join(ROOT, "run_ask.py"), "--script", full, "--python", openai_py, "--out", os.path.join(tmp, "o1"))
        check(r.returncode == 0, "run_ask: base_url + api_key in the script -> non-empty completion")
        nokey = variant(tmp, "e2e_nokey", 'client = OpenAI()', 'client = OpenAI(base_url="%s")' % base)
        r = py(os.path.join(ROOT, "run_ask.py"), "--script", nokey, "--python", openai_py, "--out", os.path.join(tmp, "o2"))
        rec = json.load(open(os.path.join(tmp, "o2.json")))
        check(r.returncode == 1 and "api_key" in rec["stderr_tail"], "run_ask: no api_key and OPENAI_API_KEY unset -> fails")
        r = py(os.path.join(ROOT, "run_ask.py"), "--script", ASK, "--python", openai_py,
               "--env", "OPENAI_BASE_URL=" + base, "--env", "OPENAI_API_KEY=ollama", "--out", os.path.join(tmp, "o3"))
        check(r.returncode == 0, "run_ask: env vars only (script unchanged) -> non-empty completion")
        Fake.empty = True
        r = py(os.path.join(ROOT, "run_ask.py"), "--script", full, "--python", openai_py, "--out", os.path.join(tmp, "o4"))
        check(r.returncode == 1, "run_ask: empty completion -> fails")
    finally:
        srv.shutdown()


def main():
    tmp = tempfile.mkdtemp(prefix="q20-test-")
    test_base_url()
    test_diff(tmp)
    openai_py = os.environ.get("Q20_OPENAI_PYTHON")
    usable = False
    if openai_py:
        try:
            usable = subprocess.run([openai_py, "-c", "import openai"], capture_output=True).returncode == 0
        except OSError:
            usable = False
    if usable:
        test_e2e(tmp, openai_py)
    else:
        print("skip end-to-end part (set Q20_OPENAI_PYTHON to a python with the openai package)")
    print("\n%d failure(s)" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
