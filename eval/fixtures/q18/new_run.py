#!/usr/bin/env python3
"""Start one q18 run: make a fresh random token and a run folder (Python stdlib only).

  python3 new_run.py --runs-dir /eval-work/q18/runs --label r1 [--state-dir STATE]

Writes STATE/token.txt (read by the fixture MCP server on every call) and
RUNS/r1/run.json with the token and the start time (epoch seconds). Prints the
run folder. Run it immediately before starting the client for that run.
"""

import argparse
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def load_server():
    path = os.path.join(HERE, "mcp_server", "project_code_server.py")
    spec = importlib.util.spec_from_file_location("project_code_server", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-dir", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--state-dir", default=os.path.join(HERE, "state"))
    a = ap.parse_args()
    srv = load_server()
    run = os.path.join(a.runs_dir, a.label)
    if os.path.exists(os.path.join(run, "run.json")):
        print("run folder already used: %s" % run, file=sys.stderr)
        return 2
    os.makedirs(run, exist_ok=True)
    os.makedirs(a.state_dir, exist_ok=True)
    token = srv.new_token()
    with open(os.path.join(a.state_dir, "token.txt"), "w", encoding="utf-8") as f:
        f.write(token + "\n")
    info = {"label": a.label, "token": token, "t_start": time.time(),
            "state_dir": os.path.abspath(a.state_dir)}
    with open(os.path.join(run, "run.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    print(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
