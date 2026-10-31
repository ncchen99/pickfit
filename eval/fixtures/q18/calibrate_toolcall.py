#!/usr/bin/env python3
"""Pre-freeze calibration for q18: does the fixture model make the tool call through Ollama's own API?

Python stdlib only. Run against the pinned Ollama itself (not through the proxy):

  python3 calibrate_toolcall.py --host http://127.0.0.1:11435 --model TAG --runs 3 --out calib.json

Each run sends the frozen request (request.txt) to POST /api/chat with the
fixture server's tool definition (same name, description and JSON schema as
mcp_server/project_code_server.py), stream false, no system prompt, default
options. A run is correct when the reply's message.tool_calls has a call to
get_project_code whose "name" argument is project alpha (same normalisation as
the server) and no call to any other tool.

Second turn (recorded, not required by the checklist): the tool result
"Project alpha: code <random token>" is sent back as a tool message and the
final reply is checked for the token.

Exit 0 only when every run is correct (the checklist requires 3 of 3).
"""

import argparse
import importlib.util
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def load_server():
    path = os.path.join(HERE, "mcp_server", "project_code_server.py")
    spec = importlib.util.spec_from_file_location("project_code_server", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def call(host, path, body=None, timeout=900):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(host.rstrip("/") + path, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="http://127.0.0.1:11435")
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out")
    a = ap.parse_args()
    srv = load_server()
    with open(os.path.join(HERE, "request.txt"), encoding="utf-8") as f:
        request = f.read().strip()
    tool = {"type": "function", "function": {"name": srv.TOOL["name"], "description": srv.TOOL["description"],
                                             "parameters": srv.TOOL["inputSchema"]}}
    rec = {"host": a.host, "model": a.model, "request": request, "tool": tool, "runs": []}
    try:
        rec["ollama_version"] = call(a.host, "/api/version").get("version")
        tags = call(a.host, "/api/tags").get("models", [])
        m = [t for t in tags if t.get("name") == a.model or t.get("model") == a.model]
        rec["model_digest"] = m[0].get("digest") if m else None
        rec["model_details"] = m[0].get("details") if m else None
    except OSError as e:
        rec["info_error"] = str(e)
    for i in range(a.runs):
        run = {"n": i + 1}
        t0 = time.time()
        msgs = [{"role": "user", "content": request}]
        try:
            r1 = call(a.host, "/api/chat", {"model": a.model, "messages": msgs, "tools": [tool], "stream": False})
        except OSError as e:
            run.update({"error": str(e), "correct": False})
            rec["runs"].append(run)
            continue
        run["seconds_turn1"] = round(time.time() - t0, 2)
        msg = r1.get("message", {})
        calls = msg.get("tool_calls") or []
        run["tool_calls"] = calls
        names = [c.get("function", {}).get("name") for c in calls]
        args = [c.get("function", {}).get("arguments") or {} for c in calls]
        good = [x for n, x in zip(names, args) if n == srv.TOOL["name"] and isinstance(x, dict)
                and srv.Server.normalize(x.get("name", "")) == "alpha"]
        run["correct"] = bool(good) and all(n == srv.TOOL["name"] for n in names)
        if run["correct"]:
            token = srv.new_token()
            msgs.append(msg)
            msgs.append({"role": "tool", "content": "Project alpha: code %s" % token, "tool_name": srv.TOOL["name"]})
            t1 = time.time()
            try:
                r2 = call(a.host, "/api/chat", {"model": a.model, "messages": msgs, "tools": [tool], "stream": False})
                content = r2.get("message", {}).get("content", "")
                run["seconds_turn2"] = round(time.time() - t1, 2)
                run["final_reply"] = content[:500]
                run["final_has_token"] = token in content
            except OSError as e:
                run["turn2_error"] = str(e)
        rec["runs"].append(run)
        print("run %d: correct=%s final_has_token=%s" % (i + 1, run["correct"], run.get("final_has_token")))
    rec["correct_runs"] = sum(1 for r in rec["runs"] if r.get("correct"))
    rec["pass"] = rec["correct_runs"] == a.runs
    text = json.dumps(rec, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0 if rec["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
