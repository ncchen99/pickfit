#!/usr/bin/env python3
"""Self-test for the q18 fixtures (stdlib only, offline, no root).

Uses a fake model server in place of Ollama; nothing here downloads or calls a real model.
"""

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
SERVER = os.path.join(ROOT, "mcp_server", "project_code_server.py")
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


def rpc_session(state, lines):
    p = subprocess.Popen([sys.executable, SERVER, "--state-dir", state], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate(b"".join(lines), timeout=30)
    return [json.loads(l) for l in out.splitlines() if l.strip()], err


def j(obj):
    return json.dumps(obj).encode() + b"\n"


def test_server():
    state = tempfile.mkdtemp(prefix="q18-state-")
    with open(os.path.join(state, "token.txt"), "w") as f:
        f.write("ABCD-EFGH-JKMN\n")
    body = j({"jsonrpc": "2.0", "id": 9, "method": "ping"})
    replies, err = rpc_session(state, [
        j({"jsonrpc": "2.0", "id": 1, "method": "initialize",
           "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}),
        j({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        j({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
        j({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_project_code", "arguments": {"name": "alpha"}}}),
        j({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_project_code", "arguments": {"name": " Project Alpha "}}}),
        j({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "get_project_code", "arguments": {"name": "beta"}}}),
        j({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "other_tool", "arguments": {}}}),
        j({"jsonrpc": "2.0", "id": 7, "method": "no/such"}),
        j([{"jsonrpc": "2.0", "id": 8, "method": "prompts/list"}, {"jsonrpc": "2.0", "method": "notifications/x"}]),
        b"Content-Length: %d\r\n\r\n" % len(body) + body,
        b"{not json\n",
    ])
    by_id = {}
    for r in replies:
        for x in (r if isinstance(r, list) else [r]):
            by_id[x.get("id")] = x
    check(by_id[1]["result"]["protocolVersion"] == "2025-03-26", "initialize echoes the client's protocol version")
    check(by_id[1]["result"]["capabilities"] == {"tools": {"listChanged": False}}, "initialize declares tools")
    tools = by_id[2]["result"]["tools"]
    check(len(tools) == 1 and tools[0]["name"] == "get_project_code", "tools/list has get_project_code")
    check("ABCD-EFGH-JKMN" in by_id[3]["result"]["content"][0]["text"], "tools/call alpha returns the token")
    check("ABCD-EFGH-JKMN" in by_id[4]["result"]["content"][0]["text"], "'Project Alpha' normalises to alpha")
    check(by_id[5]["result"]["isError"] is True and "ABCD" not in json.dumps(by_id[5]), "beta gets no token")
    check(by_id[6]["error"]["code"] == -32602, "unknown tool is an error")
    check(by_id[7]["error"]["code"] == -32601, "unknown method is method-not-found")
    check(by_id[8]["result"] == {"prompts": []}, "batch request answered")
    check(9 in by_id and by_id[9]["result"] == {}, "Content-Length framing accepted")
    check(by_id.get(None, {}).get("error", {}).get("code") == -32700, "parse error answered")
    log = [json.loads(l) for l in open(os.path.join(state, "server.log"))]
    calls = [e for e in log if e["event"] == "tools_call"]
    check([c["result"] for c in calls] == ["token", "token", "no_such_project", "unknown_tool"], "server.log records calls")
    check(not any(e.get("notification") is False and e.get("method") == "notifications/initialized" for e in log),
          "notifications are logged as notifications")
    os.remove(os.path.join(state, "token.txt"))
    replies, _ = rpc_session(state, [j({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                         "params": {"name": "get_project_code", "arguments": {"name": "alpha"}}})])
    tok = open(os.path.join(state, "token.txt")).read().strip()
    check(len(tok) == 14 and tok in replies[0]["result"]["content"][0]["text"], "missing token.txt -> new random token")


class FakeOllama(BaseHTTPRequestHandler):
    """Stands in for Ollama: tool call on the first turn, then a reply built from the tool message."""
    protocol_version = "HTTP/1.1"
    forget = False

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
        if self.path == "/api/version":
            self._send({"version": "0.0.0-fake"})
        else:
            self._send({"models": [{"name": "fake:1", "model": "fake:1", "digest": "f" * 64, "details": {}}]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n))
        msgs = req.get("messages", [])
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        if not tool_msgs:
            msg = {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "get_project_code", "arguments": {"name": "alpha"}}}]}
        else:
            code = tool_msgs[-1]["content"].split("code ")[-1].strip()
            msg = {"role": "assistant", "content": "I do not know." if self.forget else "The code is %s." % code}
        if req.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            parts = [msg["content"][:9], msg["content"][9:]] if msg["content"] else [""]
            for i, p in enumerate(parts):
                line = json.dumps({"message": dict(msg, content=p), "done": i == len(parts) - 1}).encode() + b"\n"
                self.wfile.write(b"%x\r\n%s\r\n" % (len(line), line))
            self.wfile.write(b"0\r\n\r\n")
        else:
            self._send({"message": msg, "done": True})


FAKE_CLIENT = r'''
import json, subprocess, sys, urllib.request
server, state, proxy = sys.argv[1], sys.argv[2], sys.argv[3]
print("fake client > ", end="", flush=True)
request = sys.stdin.readline().strip()
p = subprocess.Popen([sys.executable, server, "--state-dir", state], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
def rpc(i, method, params):
    p.stdin.write((json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n").encode()); p.stdin.flush()
    return json.loads(p.stdout.readline())
rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fake", "version": "0"}})
def chat(msgs):
    req = urllib.request.Request(proxy + "/api/chat", data=json.dumps({"model": "fake:1", "messages": msgs, "stream": True}).encode(),
                                 headers={"Content-Type": "application/json"})
    text, last = "", None
    for line in urllib.request.urlopen(req).read().decode().splitlines():
        o = json.loads(line); last = o["message"]; text += o["message"].get("content", "")
    return last, text
msgs = [{"role": "user", "content": request}]
m, _ = chat(msgs)
call = m["tool_calls"][0]["function"]
print("Allow tool %s? [y/N] " % call["name"], end="", flush=True)
if sys.stdin.readline().strip().lower() != "y":
    sys.exit(4)
res = rpc(2, "tools/call", {"name": call["name"], "arguments": call["arguments"]})
out = res["result"]["content"][0]["text"]
print("[tool output] " + out)
msgs += [m, {"role": "tool", "content": out}]
_, reply = chat(msgs)
print("assistant: " + reply)
'''


def test_calibration_and_runs():
    up = free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", up), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    out = tempfile.mkdtemp(prefix="q18-cal-")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "calibrate_toolcall.py"), "--host", "http://127.0.0.1:%d" % up,
                        "--model", "fake:1", "--runs", "3", "--out", os.path.join(out, "c.json")],
                       capture_output=True, text=True, timeout=60)
    rec = json.load(open(os.path.join(out, "c.json")))
    check(r.returncode == 0 and rec["correct_runs"] == 3 and all(x["final_has_token"] for x in rec["runs"]),
          "calibrate_toolcall: 3/3 against the fake model server")
    check(rec["model_digest"] == "f" * 64, "calibrate_toolcall records the model digest")

    px = free_port()
    work = tempfile.mkdtemp(prefix="q18-run-")
    state = os.path.join(work, "state")
    os.makedirs(os.path.join(state, "proxy"))
    proxy = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "logging_proxy.py"), "--listen",
                              "127.0.0.1:%d" % px, "--upstream", "127.0.0.1:%d" % up, "--log-dir", os.path.join(state, "proxy")])
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", px), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        client = os.path.join(work, "fake_client.py")
        open(client, "w").write(FAKE_CLIENT)
        runs = os.path.join(work, "runs")

        def one(label, forget):
            FakeOllama.forget = forget
            rd = subprocess.run([sys.executable, os.path.join(ROOT, "new_run.py"), "--runs-dir", runs, "--label", label,
                                 "--state-dir", state], capture_output=True, text=True, timeout=30).stdout.strip()
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "pty_drive.py"), "--out", os.path.join(rd, "client"),
                            "--timeout", "60", "--send-file", os.path.join(ROOT, "request.txt"), "--send-after", "> ",
                            "--approve", r"\[y/N\]", "--approve-keys", "y\\r", "--",
                            sys.executable, client, SERVER, state, "http://127.0.0.1:%d" % px],
                           capture_output=True, timeout=120)
            time.sleep(0.2)
            return rd

        r1, r2, r3 = one("r1", False), one("r2", True), one("r3", False)
        res = subprocess.run([sys.executable, os.path.join(ROOT, "check_run.py"), "--state-dir", state, r1, r2, r3],
                             capture_output=True, text=True, timeout=60)
        rep = json.loads(res.stdout)
        by = {x["run"]: x for x in rep["runs"]}
        check(by["r1"]["pass"] and by["r3"]["pass"], "runs where the model states the token pass")
        check(by["r2"]["transcript"] and not by["r2"]["model_reply"] and not by["r2"]["pass"],
              "echoed tool output alone does not pass (model never said the token)")
        check(rep["L2-2"] == "pass" and rep["runs_passed"] == 2 and res.returncode == 0, "2 of 3 runs -> L2-2 pass")
        tokens = {json.load(open(os.path.join(d, "run.json")))["token"] for d in (r1, r2, r3)}
        check(len(tokens) == 3, "every run gets its own token")

        def egress_dir(name, bad_run=None):
            # a folder as eval/fixtures/_shared/egress.py run writes it: one traced step per run, plus the
            # config step whose leftover (a background helper) phones home during bad_run's window
            d = os.path.join(work, name)
            os.makedirs(d)
            execve = '1 1761800000.1 execve("/bin/sh", ["sh"], 0x0 /* 1 var */) = 0\n'
            for label in ("config", "r1", "r2", "r3"):
                trace = execve
                if label == "config" and bad_run:
                    t = json.load(open(os.path.join(bad_run, "run.json")))["t_start"] + 0.05
                    trace += ('2 %.6f connect(3, {sa_family=AF_INET, sin_port=htons(443), '
                              'sin_addr=inet_addr("203.0.113.9")}, 16) = 0\n' % t)
                with open(os.path.join(d, label + ".strace"), "w") as f:
                    f.write(trace)
                with open(os.path.join(d, label + ".json"), "w") as f:
                    json.dump({"tool": "egress.py", "label": label, "trace": os.path.join(d, label + ".strace"),
                               "traced": True, "tracer_running": False, "self_addresses": []}, f)
            return d

        for name, bad, want in (("eg-clean", None, "pass"), ("eg-bad", r2, "fail")):
            res = subprocess.run([sys.executable, os.path.join(ROOT, "check_run.py"), "--state-dir", state,
                                  "--egress-dir", egress_dir(name, bad), r1, r2, r3],
                                 capture_output=True, text=True, timeout=60)
            rep = json.loads(res.stdout)
            check(rep["L2-3"] == want, "egress %s -> L2-3 %s (got %s)" % (name, want, rep["L2-3"]))
        by = {x["run"]: x for x in rep["runs"]}
        check(by["r2"]["egress"] == "fail" and "203.0.113.9" in by["r2"]["egress_attempts"][0]
              and by["r1"]["egress"] == "pass" and by["r3"]["egress"] == "pass",
              "egress violation is attributed to the run whose window it falls in")
    finally:
        proxy.terminate()
        proxy.wait(5)
        srv.shutdown()


def main():
    test_server()
    test_calibration_and_runs()
    print("\n%d failure(s)" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
