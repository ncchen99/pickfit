#!/usr/bin/env python3
"""Local self-test of the q06 harness (mock, reference client, checker) without strace.

    python3 test_q06.py

Uses only loopback. Runs the calibration server through stdio and streamable HTTP and
checks that a correct server passes tools_list and tool_calls, and that an extra tool,
a dropped POST body or a wrong base URL fail. The egress item needs strace on Linux and
is covered by calibration.md instead.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    tmp = tempfile.mkdtemp(prefix="q06test-")
    mport, hport = free_port(), free_port()
    log, state = os.path.join(tmp, "mock_log.jsonl"), os.path.join(tmp, "mock_state.json")
    mock = subprocess.Popen([PY, os.path.join(HERE, "mock_api.py"), "--port", str(mport), "--log", log,
                             "--state", state], stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    base = "http://127.0.0.1:%d" % mport
    spec = os.path.join(HERE, "openapi.json")
    calib = [PY, os.path.join(HERE, "calib_mcp_server.py"), "--spec", spec]
    client = [PY, os.path.join(HERE, "mcp_ref_client.py")]
    cases = [
        ("stdio, correct server", ["--stdio", "--"] + calib + ["--stdio", "--base-url", base], True, True),
        ("streamable HTTP, correct server",
         ["--http", "http://127.0.0.1:%d/mcp" % hport, "--spawn",
          " ".join(calib + ["--http-port", str(hport), "--base-url", base])], True, True),
        ("streamable HTTP, SSE-framed responses",
         ["--http", "http://127.0.0.1:%d/mcp" % hport, "--spawn",
          " ".join(calib + ["--http-port", str(hport), "--base-url", base, "--sse-responses"])], True, True),
        ("older HTTP+SSE transport",
         ["--sse", "http://127.0.0.1:%d/sse" % hport, "--spawn",
          " ".join(calib + ["--http-port", str(hport), "--base-url", base, "--legacy-sse"])], True, True),
        ("stdio, extra tool listed", ["--stdio", "--"] + calib + ["--stdio", "--base-url", base,
                                                                  "--fault", "extra-tool"], False, True),
        ("stdio, POST body dropped", ["--stdio", "--"] + calib + ["--stdio", "--base-url", base,
                                                                  "--fault", "drop-body"], True, False),
        ("stdio, wrong base URL (closed port)", ["--stdio", "--"] + calib + [
            "--stdio", "--base-url", "http://127.0.0.1:1"], True, False),
    ]
    ok_all = True
    try:
        for name, args, want_list, want_calls in cases:
            open(log, "w").close()
            rep = os.path.join(tmp, "client.json")
            subprocess.run(client + ["--report", rep] + args, stdout=subprocess.DEVNULL, check=False)
            res = subprocess.run([PY, os.path.join(HERE, "check_q06.py"), "--client-report", rep,
                                  "--mock-log", log, "--mock-state", state], capture_output=True, text=True)
            v = json.loads(res.stdout)
            ok = v["tools_list"]["pass"] == want_list and v["tool_calls"]["pass"] == want_calls
            ok_all = ok_all and ok
            print("%-4s %-38s tools_list=%s tool_calls=%s" % ("ok" if ok else "FAIL", name,
                                                              v["tools_list"]["pass"], v["tool_calls"]["pass"]))
    finally:
        mock.terminate()
    print("all cases as expected" if ok_all else "SOME CASES FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
