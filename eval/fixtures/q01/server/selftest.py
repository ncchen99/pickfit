#!/usr/bin/env python3
"""Self-test for the q01 fixture MCP server: spawn it over stdio and run a
handshake (initialize, notifications/initialized, ping, tools/list, tools/call).

Usage: python3 selftest.py [--command python3] [--server PATH] [--server-name NAME]
Exit 0 when every step answers as expected. Standard library only; no network.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--command", default=sys.executable)
    ap.add_argument("--server", default=os.path.join(HERE, "fixture_mcp_server.py"))
    ap.add_argument("--server-name", default=None)
    a = ap.parse_args()

    argv = [a.command, a.server]
    if a.server_name:
        argv += ["--server-name", a.server_name]
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1)

    def call(msg, expect_reply=True):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        if not expect_reply:
            return None
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("FAIL: server closed stdout")
        return json.loads(line)

    want_name = a.server_name or "fixture-echo"
    checks = []
    r = call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "selftest", "version": "0"}}})
    res = r.get("result", {})
    checks.append(("initialize", res.get("protocolVersion") == "2025-06-18"
                   and res.get("serverInfo", {}).get("name") == want_name
                   and "tools" in res.get("capabilities", {})))
    call({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_reply=False)
    r = call({"jsonrpc": "2.0", "id": "p1", "method": "ping"})
    checks.append(("ping", r.get("id") == "p1" and r.get("result") == {}))
    r = call({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = [t.get("name") for t in r.get("result", {}).get("tools", [])]
    checks.append(("tools/list", tools == ["echo"]))
    r = call({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": "echo", "arguments": {"text": "hello fixture"}}})
    content = r.get("result", {}).get("content", [{}])
    checks.append(("tools/call", content and content[0].get("text") == "hello fixture"))
    r = call({"jsonrpc": "2.0", "id": 4, "method": "no/such/method"})
    checks.append(("unknown method", r.get("error", {}).get("code") == -32601))
    r = call({"jsonrpc": "2.0", "id": 5, "method": "initialize",
              "params": {"protocolVersion": "not-a-date"}})
    checks.append(("version fallback",
                   r.get("result", {}).get("protocolVersion") == "2025-11-25"))

    proc.stdin.close()
    proc.wait(timeout=10)
    stderr = proc.stderr.read()
    ok = all(c[1] for c in checks) and proc.returncode == 0 and stderr == ""
    for name, passed in checks:
        print(("PASS " if passed else "FAIL ") + name)
    if stderr:
        print("FAIL server wrote to stderr: " + stderr[:200])
    print("RESULT " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
