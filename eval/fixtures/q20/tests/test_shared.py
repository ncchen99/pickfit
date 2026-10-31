#!/usr/bin/env python3
"""Self-test for egress.py, pty_drive.py and logging_proxy.py (stdlib only, no root, no network).

Run from the question folder:  python3 tests/test_shared.py
Every tool that a question folder does not ship is skipped.
"""

import http.client
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EGRESS = os.path.join(ROOT, "egress", "egress.py")
PTY = os.path.join(ROOT, "tools", "pty_drive.py")
PROXY = os.path.join(ROOT, "tools", "logging_proxy.py")
STEPS = os.path.join(ROOT, "tools", "run_steps.py")
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


def load(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ egress

def test_egress():
    eg = load(EGRESS, "egress")
    check(eg.classify_ip("127.0.0.1") == "loopback", "127.0.0.1 is loopback")
    check(eg.classify_ip("::ffff:127.0.0.5") == "loopback", "v4-mapped loopback")
    check(eg.classify_ip("::1") == "loopback", "::1 is loopback")
    check(eg.classify_ip("0.0.0.0") == "unspecified", "0.0.0.0 unspecified")
    check(eg.classify_ip("93.184.215.14") == "remote", "public v4 is remote")
    check(eg.classify_ip("10.1.2.3", {"10.1.2.3"}) == "self", "own interface is self")

    sample = "\n".join([
        '101 1761800000.100000 connect(3, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("140.82.112.3")}, 16) = -1 ENETUNREACH (Network is unreachable)',
        '101 1761800000.200000 connect(4, {sa_family=AF_INET, sin_port=htons(11434), sin_addr=inet_addr("127.0.0.1")}, 16) = 0',
        '[pid 102] 1761800000.300000 connect(5, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "2606:4700::6810:84e5", &sin6_addr), sin6_scope_id=0}, 28) = -1 ENETUNREACH',
        '102 1761800000.400000 sendto(6, "\\x12\\x34", 30, MSG_NOSIGNAL, {sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("127.0.0.1")}, 16) = 30',
        '103 1761800000.500000 connect(7, {sa_family=AF_UNIX, sun_path="/run/x.sock"}, 110) = 0',
        '103 1761800000.600000 sendmsg(8, {msg_name={sa_family=AF_INET, sin_port=htons(5353), sin_addr=inet_addr("224.0.0.251")}, msg_namelen=16}, 0) = 40',
        '1761800000.700000 connect(9, {sa_family=AF_INET, sin_port=htons(80), sin_addr=inet_addr("0.0.0.0")}, 16) = 0',
    ])
    ev = eg.parse_strace(sample)
    remote = [e for e in ev if e["kind"] == "remote"]
    check(len(ev) == 6, "strace parser finds 6 inet events (got %d)" % len(ev))
    check(sorted(e["ip"] for e in remote) == ["140.82.112.3", "224.0.0.251", "2606:4700::6810:84e5"],
          "strace parser flags exactly the 3 remote addresses")
    check(any(e["pid"] == 102 for e in ev), "strace parser reads [pid N] prefix")

    proc = ("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
            "   0: 0100007F:2CAA 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1 1\n"
            "   1: 0100007F:D3E2 0100007F:2CAA 01 00000000:00000000 00:00000000 00000000     0        0 2 1\n"
            "   2: 0A00000F:D3E4 0370528C:01BB 02 00000000:00000000 00:00000000 00000000     0        0 3 1\n")
    rows = eg.parse_proc_net(proc, "tcp")
    check(rows[0]["lport"] == 11434 and rows[0]["local"] == "127.0.0.1", "proc parser decodes listen row")
    check(rows[2]["remote"] == "140.82.112.3" and rows[2]["rport"] == 443, "proc parser decodes remote row")
    v6 = eg.hex_to_ip("00000000000000000000000001000000")
    check(v6 == "::1", "proc parser decodes ::1 (got %s)" % v6)

    out = tempfile.mkdtemp(prefix="egress-test-")
    port = free_port()
    r = subprocess.run([sys.executable, EGRESS, "dns-start", "--out", out, "--port", str(port), "--no-resolv"],
                       capture_output=True, text=True, timeout=20)
    check(r.returncode == 0, "dns-start on a high port (%s)" % r.stderr.strip()[:200])
    try:
        rc_local = eg.probe_dns("127.0.0.1", port, "localhost")
        rc_remote = eg.probe_dns("127.0.0.1", port, "telemetry.example.org")
        check(rc_local == 0, "DNS logger answers localhost NOERROR")
        check(rc_remote == 3, "DNS logger answers other names NXDOMAIN in sink mode")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(("127.0.0.1", port))
        q = eg.dns_query_packet("update.example.net", qtype=28)
        s.sendall(struct.pack("!H", len(q)) + q)
        n = struct.unpack("!H", s.recv(2))[0]
        reply = b""
        while len(reply) < n:
            reply += s.recv(n - len(reply))
        s.close()
        check(struct.unpack("!H", reply[2:4])[0] & 0xF == 3, "DNS logger answers over TCP too")
    finally:
        subprocess.run([sys.executable, EGRESS, "dns-stop", "--out", out, "--no-resolv"],
                       capture_output=True, timeout=20)
    rep = eg.build_report(out)
    names = rep["layers"]["dns"]["names"]
    check(rep["result"] == "fail" and names == ["telemetry.example.org", "update.example.net"],
          "report fails on the two non-local queries (got %s, %s)" % (rep["result"], names))
    with open(os.path.join(out, "strace-r1.log"), "w") as f:
        f.write(sample + "\n")
    with open(os.path.join(out, "strace-r1.meta.json"), "w") as f:
        json.dump({"ts": 1761800000.0, "label": "r1", "strace": "/usr/bin/strace"}, f)
    rep = eg.build_report(out, since=1761800000.0, until=1761800001.0, require_strace=True)
    check(rep["layers"]["strace"]["active"] and len(rep["layers"]["strace"]["violations"]) == 3,
          "report counts strace violations inside the window")
    check(rep["layers"]["dns"]["active"] is False and "dns" in rep["missing_layers"],
          "report marks dns inactive when it was not running in the window")
    rep = eg.build_report(out, since=time.time() + 3600, until=time.time() + 7200)
    check(rep["layers"]["dns"]["active"] is False, "report marks dns inactive after dns-stop")

    clean = tempfile.mkdtemp(prefix="egress-clean-")
    port = free_port()
    subprocess.run([sys.executable, EGRESS, "dns-start", "--out", clean, "--port", str(port), "--no-resolv"],
                   capture_output=True, timeout=20)
    t0 = time.time()
    eg.probe_dns("127.0.0.1", port, "localhost")
    eg.probe_dns("127.0.0.1", port, "1.0.0.127.in-addr.arpa")
    t1 = time.time()
    subprocess.run([sys.executable, EGRESS, "dns-stop", "--out", clean, "--no-resolv"],
                   capture_output=True, timeout=20)
    r = subprocess.run([sys.executable, EGRESS, "report", "--out", clean, "--since", str(t0), "--until", str(t1)],
                       capture_output=True, text=True, timeout=20)
    check(r.returncode == 0 and json.loads(r.stdout)["result"] == "pass",
          "report passes when only localhost names were queried")

    tr = tempfile.mkdtemp(prefix="egress-trace-")
    r = subprocess.run([sys.executable, EGRESS, "trace", "--out", tr, "--label", "t", "--",
                        sys.executable, "-c", "print('traced-ok')"], capture_output=True, text=True, timeout=60)
    check("traced-ok" in r.stdout, "trace runs the command (strace present: %s)" %
          bool(__import__("shutil").which("strace")))


# ------------------------------------------------------------------ pty_drive

FAKE_CLI = r'''
import sys, time
print("fake-cli ready")
sys.stdout.write("> "); sys.stdout.flush()
q = sys.stdin.readline().strip()
print("\x1b[1mthinking\x1b[0m about: " + q)
sys.stdout.write("Allow tool get_thing? (y/n) "); sys.stdout.flush()
a = sys.stdin.readline().strip()
if a != "y":
    print("denied"); sys.exit(3)
print("tool result shown")
print("Answer: the code is ZX-" + "42")
sys.stdout.write("> "); sys.stdout.flush()
rest = sys.stdin.read()
print("bye")
'''


def test_pty():
    d = tempfile.mkdtemp(prefix="pty-test-")
    cli = os.path.join(d, "fake_cli.py")
    with open(cli, "w") as f:
        f.write(FAKE_CLI)
    out = os.path.join(d, "run1")
    r = subprocess.run([sys.executable, PTY, "--out", out, "--timeout", "30", "--send", "hello there",
                        "--send-after", "> ", "--approve", r"\(y/n\)", "--approve-keys", "y\\r",
                        "--done", "ZX-42", "--idle", "1", "--exit-keys", "\\x04", "--grace", "3",
                        "--", sys.executable, cli], capture_output=True, text=True, timeout=60)
    with open(out + ".json") as f:
        s = json.load(f)
    with open(out + ".txt") as f:
        txt = f.read()
    check(len(s["approvals"]) == 1, "pty_drive approved exactly once (%d)" % len(s["approvals"]))
    check("Answer: the code is ZX-42" in txt, "pty_drive transcript has the answer")
    check("\x1b" not in txt, "pty_drive .txt has no escape sequences")
    check(not s["timed_out"] and s["elapsed"] < 20, "pty_drive finished before the timeout")
    check(s["exit_code"] == 0 or s["ended_by"] == "done", "pty_drive ended by done/exit (%s, %s)" %
          (s["exit_code"], s["ended_by"]))
    check(0 < s.get("last_output_t", 0) <= s["elapsed"], "pty_drive records last_output_t")

    marker = os.path.join(d, "made.txt")
    out4 = os.path.join(d, "run4")
    subprocess.run([sys.executable, PTY, "--out", out4, "--timeout", "30", "--send", "go", "--send-delay", "0.5",
                    "--done-file", marker, "--idle", "1", "--grace", "1", "--",
                    sys.executable, "-c", "import sys,time; sys.stdin.readline(); open(%r,'w').write('x'); print('made'); time.sleep(60)" % marker],
                   capture_output=True, text=True, timeout=60)
    with open(out4 + ".json") as f:
        s4 = json.load(f)
    check(s4["ended_by"] == "done" and s4["elapsed"] < 15, "pty_drive --done-file ends the session")

    out2 = os.path.join(d, "run2")
    r = subprocess.run([sys.executable, PTY, "--out", out2, "--timeout", "2", "--",
                        sys.executable, "-c", "import time; print('start'); time.sleep(30)"],
                       capture_output=True, text=True, timeout=30)
    with open(out2 + ".json") as f:
        s2 = json.load(f)
    check(s2["timed_out"] and s2["elapsed"] < 10, "pty_drive kills on timeout")

    out3 = os.path.join(d, "run3")
    subprocess.run([sys.executable, PTY, "--out", out3, "--no-pty", "--send", "abc", "--timeout", "10", "--",
                    sys.executable, "-c", "import sys; print('got', sys.stdin.read().strip())"],
                   capture_output=True, text=True, timeout=30)
    with open(out3 + ".txt") as f:
        check("got abc" in f.read(), "pty_drive --no-pty passes stdin")


# ------------------------------------------------------------------ logging_proxy

class Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _chunked(self, ctype, parts):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for p in parts:
            self.wfile.write(b"%x\r\n%s\r\n" % (len(p), p))
            self.wfile.flush()
            time.sleep(0.05)
        self.wfile.write(b"0\r\n\r\n")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", "17")
        self.end_headers()

    def do_GET(self):
        body = b'{"version":"fake"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/chat":
            lines = [{"message": {"role": "assistant", "content": c}, "done": False} for c in ("The code ", "is QK7", "F-M4XB.")]
            lines.append({"message": {"role": "assistant", "content": ""}, "done": True})
            self._chunked("application/x-ndjson", [json.dumps(l).encode() + b"\n" for l in lines])
        elif self.path == "/v1/chat/completions" and req.get("stream"):
            ev = [{"choices": [{"delta": {"content": c}}]} for c in ("Done: ", "QK7F", "-M4XB")]
            ev.append({"choices": [{"delta": {"tool_calls": [{"function": {"arguments": "{\"x\":\"NOTTEXT\"}"}}]}}]})
            parts = [b"data: " + json.dumps(e).encode() + b"\n\n" for e in ev] + [b"data: [DONE]\n\n"]
            self._chunked("text/event-stream", parts)
        else:
            body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "plain QK7F-M4XB"}}],
                               "echo_auth": bool(self.headers.get("Authorization"))}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def test_proxy():
    lp = load(PROXY, "logging_proxy")
    up_port = free_port()
    up = ThreadingHTTPServer(("127.0.0.1", up_port), Upstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    px_port = free_port()
    logd = tempfile.mkdtemp(prefix="proxy-test-")
    p = subprocess.Popen([sys.executable, PROXY, "--listen", "127.0.0.1:%d" % px_port,
                          "--upstream", "127.0.0.1:%d" % up_port, "--log-dir", logd])
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", px_port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

        def req(method, path, body=None, headers=None):
            c = http.client.HTTPConnection("127.0.0.1", px_port, timeout=10)
            c.request(method, path, body=body, headers=headers or {})
            r = c.getresponse()
            data = r.read()
            c.close()
            return r, data

        r, data = req("POST", "/api/chat", json.dumps({"model": "m", "messages": [{"role": "user", "content": "hi"}],
                                                        "tools": [{"type": "function"}], "stream": True}),
                      {"Content-Type": "application/json"})
        check(r.status == 200 and data.count(b"\n") == 4, "proxy relays chunked NDJSON")
        check(lp.model_text(data) == "The code is QK7F-M4XB.", "model_text joins NDJSON content")
        r, data = req("POST", "/v1/chat/completions", json.dumps({"model": "m", "stream": True, "messages": []}),
                      {"Authorization": "Bearer local-test-value", "Content-Type": "application/json"})
        txt = lp.model_text(data)
        check("QK7F-M4XB" in txt and "NOTTEXT" not in txt, "model_text joins SSE deltas, skips tool args")
        r, data = req("POST", "/v1/other", json.dumps({"model": "m"}), {"Authorization": "Bearer local-test-value"})
        check(json.loads(data)["echo_auth"] is True, "proxy forwards Authorization")
        r, data = req("GET", "/api/version")
        check(r.status == 200 and data == b'{"version":"fake"}', "proxy relays GET with Content-Length")
        r, data = req("HEAD", "/")
        check(r.status == 200 and data == b"", "proxy relays HEAD")
        time.sleep(0.3)
        with open(os.path.join(logd, "requests.jsonl")) as f:
            log = [json.loads(l) for l in f]
        check(len(log) == 5, "proxy logged 5 requests (%d)" % len(log))
        check(log[0]["n_tools"] == 1 and log[0]["model"] == "m" and log[0]["stream"] is True,
              "proxy log parses model/stream/tools")
        raw = open(os.path.join(logd, "requests.jsonl")).read()
        for f in os.listdir(logd):
            if f.endswith(".req"):
                raw += open(os.path.join(logd, f), errors="replace").read()
        check("local-test-value" not in raw, "proxy never writes header values to its log")
        check(os.path.exists(os.path.join(logd, "%06d.resp" % log[0]["id"])), "proxy saved response body")
    finally:
        p.terminate()
        p.wait(5)
        up.shutdown()


STEPS_FILE = r'''# grader note: this line is skipped
export FOO=hello
echo "foo is $FOO"
cat <<EOF > out.txt
line one
EOF
read -p "Continue? [Y/n] " ans; echo "ans=[$ans]"
echo split \
  line
#NEW_SHELL
echo "after new shell foo=[$FOO]"
false
echo never
'''


def test_run_steps():
    d = tempfile.mkdtemp(prefix="steps-test-")
    sf = os.path.join(d, "steps.txt")
    with open(sf, "w") as f:
        f.write(STEPS_FILE)
    r = subprocess.run([sys.executable, STEPS, "--steps", sf, "--out", os.path.join(d, "install"),
                        "--accept", r"\[Y/n\]", "--step-timeout", "20", "--total-timeout", "120"],
                       cwd=d, capture_output=True, text=True, timeout=180)
    with open(os.path.join(d, "install.json")) as f:
        rec = json.load(f)
    st = rec["steps"]
    cmds = [x["cmd"] for x in st]
    check(r.returncode == 1 and not rec["all_ok"], "run_steps stops and fails at the failing command")
    check(len(st) == 8 and cmds[-1] == "false" and st[-1]["exit_code"] == 1,
          "run_steps ran 8 commands, last is 'false' with rc 1 (%d, %s)" % (len(st), cmds[-1:]))
    check("foo is hello" in st[1].get("output", ""), "run_steps keeps one session (export persists)")
    out = os.path.join(d, "out.txt")
    check(os.path.exists(out) and open(out).read() == "line one\n", "run_steps keeps a heredoc together")
    check("ans=[]" in st[3].get("output", ""), "run_steps accepts an installer default with Enter")
    check("split line" in st[4].get("output", ""), "run_steps joins a backslash continuation")
    check("foo=[]" in st[6].get("output", ""), "#NEW_SHELL starts a fresh login shell")


def main():
    if os.path.exists(STEPS):
        test_run_steps()
    if os.path.exists(EGRESS):
        test_egress()
    if os.path.exists(PTY):
        test_pty()
    if os.path.exists(PROXY):
        test_proxy()
    print("\n%d failure(s)" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
