#!/usr/bin/env python3
"""Fallback for q01 L2 item 3: validate one agent's MCP entry against that
agent's documented config shape, for an agent whose own `mcp list` command
pre-freeze calibration showed cannot run offline without login.

Use it only for agents recorded as substituted in calibration.md. The shape
rules below are transcribed from each agent's public MCP docs (see
locations.json "doc"); calibration.md step 2 re-checks them against the
pinned version's docs and records any change here before the freeze.

  python3 validate_shape.py --agent codex-cli --state /opt/eval/state/q01-seeded.json

It looks in every seeded location of that agent (from the state file written
by seed_configs.py) for the fixture server and passes when at least one
location the agent reads holds a well-formed stdio entry that launches the
frozen server (same command after PATH lookup, same args).

Python 3.11+ standard library. Exit 0 pass, 1 fail, 2 usage error.
"""
import argparse
import json
import os
import shutil
import sys

try:
    import tomllib
except ImportError:
    tomllib = None

HERE = os.path.dirname(os.path.abspath(__file__))

# Documented stdio entry shape per agent.
SHAPES = {
    "claude-code": {"format": "json", "containers": [["mcpServers"], ["projects", "{PROJECT}", "mcpServers"]],
                    "type_field": ("type", {"stdio"}), "forbid": ["url"]},
    "codex-cli": {"format": "toml", "containers": [["mcp_servers"]],
                  "type_field": None, "forbid": ["url"]},
    "gemini-cli": {"format": "json", "containers": [["mcpServers"]],
                   "type_field": None, "forbid": ["url", "httpUrl"]},
}


def load(fmt, path):
    with open(path, "rb") as f:
        data = f.read()
    if fmt == "json":
        return json.loads(data.decode("utf-8"))
    return tomllib.loads(data.decode("utf-8"))


def entry_problems(entry, shape, want_cmd, want_args):
    probs = []
    if not isinstance(entry, dict):
        return ["entry is not an object/table"]
    if shape["type_field"]:
        field, allowed = shape["type_field"]
        if field in entry and entry[field] not in allowed:
            probs.append("%s=%r is not a stdio transport" % (field, entry[field]))
    for k in shape["forbid"]:
        if k in entry:
            probs.append("has %r (remote transport field) on a stdio entry" % k)
    cmd = entry.get("command")
    if not isinstance(cmd, str) or not cmd:
        probs.append("command missing or not a string")
    args = entry.get("args", [])
    if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
        probs.append("args is not a list of strings")
    env = entry.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(v, str) for v in env.values()):
        probs.append("env is not a map of strings")
    if not probs:
        same_cmd = cmd == want_cmd or (shutil.which(cmd) and shutil.which(want_cmd)
                                       and os.path.realpath(shutil.which(cmd))
                                       == os.path.realpath(shutil.which(want_cmd)))
        if not same_cmd:
            probs.append("command %r does not resolve to %r" % (cmd, want_cmd))
        if args != want_args:
            probs.append("args %r != frozen args %r" % (args, want_args))
    return probs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=sorted(SHAPES))
    ap.add_argument("--state", required=True)
    ap.add_argument("--server-json", default=os.path.join(os.path.dirname(HERE), "server", "server.json"))
    a = ap.parse_args()
    if tomllib is None:
        print("error: needs Python 3.11+ (tomllib)", file=sys.stderr)
        return 2
    with open(a.state, encoding="utf-8") as f:
        state = json.load(f)
    with open(a.server_json, encoding="utf-8") as f:
        server = json.load(f)
    fixture = state["mapping"]["FIXTURE"]
    project = state["mapping"]["PROJECT"]
    want_cmd = server["command"]
    want_args = [x.replace("{FIXTURE}", fixture) for x in server["args"]]
    name = server["name"]
    shape = SHAPES[a.agent]
    found_ok = False
    for loc in state["locations"]:
        if loc["agent"] != a.agent:
            continue
        try:
            obj = load(shape["format"], loc["path"])
        except FileNotFoundError:
            print("FAIL  %s: file missing" % loc["path"])
            continue
        except ValueError as exc:
            print("FAIL  %s: does not parse (%s)" % (loc["path"], str(exc).splitlines()[0][:120]))
            continue
        for cpath in shape["containers"]:
            cpath = [p.replace("{PROJECT}", project) for p in cpath]
            cur = obj
            for k in cpath:
                cur = cur.get(k) if isinstance(cur, dict) else None
            if not isinstance(cur, dict) or name not in cur:
                continue
            probs = entry_problems(cur[name], shape, want_cmd, want_args)
            where = "%s: %s.%s" % (loc["path"], ".".join(cpath), name)
            if probs:
                print("FAIL  " + where + ": " + "; ".join(probs))
            else:
                print("PASS  " + where)
                found_ok = True
    if not found_ok:
        print("RESULT FAIL (no well-formed %r entry in any %s location)" % (name, a.agent))
        return 1
    print("RESULT PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
