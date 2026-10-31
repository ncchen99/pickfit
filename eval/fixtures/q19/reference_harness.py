#!/usr/bin/env python3
"""Pre-freeze calibration for q19: can the fixture model do the task through its tool API?

Python stdlib only. A minimal reference agent that calls the pinned server's
OpenAI-compatible Chat Completions API directly, with three file tools, on a
fresh copy of the seed repo:

  python3 reference_harness.py --base-url http://127.0.0.1:8000/v1 --model TAG --runs 3 --out calib.json

Each run: system prompt below, user message = task.txt, tools list_files /
read_file / write_file (paths confined to the workdir), non-streaming, default
sampling, at most --max-turns model calls. The run passes when check_hello.py
passes on the workdir afterwards and the run took at most --limit seconds
(default 900, the checklist's 15 minutes). The checklist requires 3 of 3.

--probe-prefill N (optional, informational) also times one request whose
prompt is about N tokens of filler, to estimate how long a real agent's long
system prompt takes on this machine.
"""

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = ("You are a coding assistant working inside a project directory. Use the tools to look at and "
          "change files. Paths are relative to the project directory. When the task is done, reply with one "
          "short sentence saying what you did.")
TOOLS = [
    {"type": "function", "function": {"name": "list_files", "description": "List the files in the project directory.",
                                      "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read a text file.",
                                      "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                                                     "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Create or overwrite a text file.",
                                      "parameters": {"type": "object",
                                                     "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                                                     "required": ["path", "content"]}}},
]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def post(base, path, body, key, timeout):
    req = urllib.request.Request(base.rstrip("/") + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def safe(workdir, p):
    full = os.path.realpath(os.path.join(workdir, p))
    root = os.path.realpath(workdir)
    if full != root and not full.startswith(root + os.sep):
        raise ValueError("path outside the project: %s" % p)
    return full


def run_tool(workdir, name, args):
    try:
        if name == "list_files":
            return "\n".join(sorted(f for f in os.listdir(workdir) if not f.startswith(".git")))
        if name == "read_file":
            with open(safe(workdir, args["path"]), encoding="utf-8") as f:
                return f.read()
        if name == "write_file":
            path = safe(workdir, args["path"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(args["content"])
            return "wrote %d characters to %s" % (len(args["content"]), args["path"])
        return "unknown tool %s" % name
    except (OSError, KeyError, ValueError, TypeError) as e:
        return "error: %s" % e


def one_run(a, task, nr, checker):
    workdir = tempfile.mkdtemp(prefix="q19-ref-")
    shutil.rmtree(workdir)
    nr.make_workdir(workdir, use_git=False)
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    rec = {"workdir": workdir, "turns": [], "tool_calls": 0}
    t0 = time.time()
    for turn in range(a.max_turns):
        if time.time() - t0 > a.limit:
            rec["stopped"] = "limit"
            break
        t = time.time()
        try:
            r = post(a.base_url, "/chat/completions", {"model": a.model, "messages": msgs, "tools": TOOLS},
                     a.api_key, a.limit)
        except OSError as e:
            rec["error"] = str(e)
            break
        msg = r["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        rec["turns"].append({"seconds": round(time.time() - t, 2), "tool_calls": [c["function"]["name"] for c in calls],
                             "content": (msg.get("content") or "")[:300]})
        if not calls:
            break
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            rec["tool_calls"] += 1
            raw = c["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except ValueError:
                args = {}
            msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": run_tool(workdir, c["function"]["name"], args)})
    rec["elapsed"] = round(time.time() - t0, 2)
    rec["hello"] = checker.check(workdir)
    rec["pass"] = bool(rec["hello"]["pass"]) and rec["elapsed"] <= a.limit
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key", default="unused", help="sent as a Bearer value; the local server ignores it")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--limit", type=float, default=900.0)
    ap.add_argument("--probe-prefill", type=int, default=0)
    ap.add_argument("--out")
    a = ap.parse_args()
    nr = load(os.path.join(HERE, "new_run.py"), "q19_new_run")
    checker = load(os.path.join(HERE, "check_hello.py"), "q19_check_hello")
    with open(os.path.join(HERE, "task.txt"), encoding="utf-8") as f:
        task = f.read().strip()
    out = {"base_url": a.base_url, "model": a.model, "task": task, "system": SYSTEM, "runs": []}
    for i in range(a.runs):
        rec = one_run(a, task, nr, checker)
        rec["n"] = i + 1
        out["runs"].append(rec)
        print("run %d: pass=%s elapsed=%ss turns=%d" % (i + 1, rec["pass"], rec["elapsed"], len(rec["turns"])))
    if a.probe_prefill:
        filler = ("The quick brown fox jumps over the lazy dog near the quiet river bank. " * (a.probe_prefill // 14 + 1))
        t = time.time()
        try:
            r = post(a.base_url, "/chat/completions",
                     {"model": a.model, "max_tokens": 1,
                      "messages": [{"role": "system", "content": filler}, {"role": "user", "content": "Say ok."}]},
                     a.api_key, 3600)
            out["prefill_probe"] = {"approx_tokens": a.probe_prefill, "seconds": round(time.time() - t, 2),
                                    "usage": r.get("usage")}
        except OSError as e:
            out["prefill_probe"] = {"error": str(e)}
    out["passed_runs"] = sum(1 for r in out["runs"] if r["pass"])
    out["pass"] = out["passed_runs"] == a.runs
    text = json.dumps(out, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
