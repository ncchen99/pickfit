#!/usr/bin/env python3
"""Frozen q18 fixture: a stdio MCP server with one tool, get_project_code(name).

Python stdlib only. Speaks JSON-RPC 2.0 over stdin/stdout, one JSON message per
line (the MCP stdio transport); LSP-style Content-Length framing is accepted too.
Nothing but JSON-RPC is written to stdout.

  python3 project_code_server.py [--state-dir DIR]

DIR (default: ../state next to this folder) holds:
  token.txt   the code returned for project "alpha"; read again on every call,
              so the grader can set a fresh token per run (new_run.py). If it is
              missing, a random token is generated and written there.
  server.log  one JSON line per event: start, every message received (method,
              id), every tools/call with its arguments and result, eof.

The token is a made-up project code, generated at run time; it is never committed.
"""

import argparse
import json
import os
import secrets
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE = os.path.join(os.path.dirname(HERE), "state")
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
SERVER_INFO = {"name": "project-codes", "version": "1.0.0"}
DEFAULT_PROTOCOL = "2025-06-18"
TOOL = {
    "name": "get_project_code",
    "description": "Look up the code of a project by its name.",
    "inputSchema": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "The project name."}},
        "required": ["name"],
    },
}


def new_token():
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3))


class Server(object):
    def __init__(self, state_dir):
        self.state = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.log_path = os.path.join(state_dir, "server.log")
        self.token_path = os.path.join(state_dir, "token.txt")

    def log(self, obj):
        obj = dict(obj, ts=time.time(), pid=os.getpid())
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, sort_keys=True) + "\n")

    def token(self):
        try:
            with open(self.token_path, encoding="utf-8") as f:
                t = f.read().strip()
            if t:
                return t
        except OSError:
            pass
        t = new_token()
        with open(self.token_path, "w", encoding="utf-8") as f:
            f.write(t + "\n")
        self.log({"event": "token_generated"})
        return t

    @staticmethod
    def normalize(name):
        n = str(name).strip().strip("\"'`").strip().lower()
        if n.startswith("project "):
            n = n[len("project "):].strip()
        return n

    def call_tool(self, params):
        name = params.get("name")
        args = params.get("arguments") or {}
        if name != TOOL["name"]:
            self.log({"event": "tools_call", "tool": name, "arguments": args, "result": "unknown_tool"})
            return None, {"code": -32602, "message": "Unknown tool: %s" % name}
        project = args.get("name", "") if isinstance(args, dict) else ""
        if self.normalize(project) == "alpha":
            text = "Project alpha: code %s" % self.token()
            result = {"content": [{"type": "text", "text": text}], "isError": False}
            kind = "token"
        else:
            result = {"content": [{"type": "text", "text": "No project named %r." % project}], "isError": True}
            kind = "no_such_project"
        self.log({"event": "tools_call", "tool": name, "arguments": args, "result": kind})
        return result, None

    def handle(self, msg):
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        method = msg.get("method")
        mid = msg.get("id")
        is_note = "id" not in msg
        self.log({"event": "recv", "method": method, "id": mid, "notification": is_note})
        if method is None:
            return None  # a response from the client (e.g. to a ping); nothing to answer
        if is_note:
            return None
        params = msg.get("params") or {}
        result, error = None, None
        if method == "initialize":
            result = {"protocolVersion": params.get("protocolVersion") or DEFAULT_PROTOCOL,
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": SERVER_INFO}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [TOOL]}
        elif method == "tools/call":
            result, error = self.call_tool(params)
        elif method == "resources/list":
            result = {"resources": []}
        elif method == "resources/templates/list":
            result = {"resourceTemplates": []}
        elif method == "prompts/list":
            result = {"prompts": []}
        elif method == "logging/setLevel":
            result = {}
        elif method == "completion/complete":
            result = {"completion": {"values": [], "hasMore": False}}
        else:
            error = {"code": -32601, "message": "Method not found: %s" % method}
        if error is not None:
            return {"jsonrpc": "2.0", "id": mid, "error": error}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def reply(self, obj):
        sys.stdout.buffer.write(json.dumps(obj, separators=(",", ":")).encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()

    def process(self, raw):
        try:
            msg = json.loads(raw)
        except ValueError:
            self.log({"event": "parse_error", "bytes": len(raw)})
            self.reply({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return
        if isinstance(msg, list):
            out = [r for r in (self.handle(m) for m in msg) if r is not None]
            if out:
                self.reply(out)
            return
        r = self.handle(msg)
        if r is not None:
            self.reply(r)

    def run(self):
        self.log({"event": "start", "argv": sys.argv, "cwd": os.getcwd()})
        inp = sys.stdin.buffer
        while True:
            line = inp.readline()
            if not line:
                break
            s = line.strip()
            if not s:
                continue
            if s.lower().startswith(b"content-length:"):
                n = int(s.split(b":", 1)[1].strip())
                while True:
                    h = inp.readline()
                    if not h or not h.strip():
                        break
                self.process(inp.read(n))
                continue
            self.process(s)
        self.log({"event": "eof"})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state-dir", default=DEFAULT_STATE)
    a = ap.parse_args()
    try:
        Server(a.state_dir).run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
