#!/usr/bin/env python3
"""Frozen stdio MCP fixture server for eval q01.

Speaks MCP over stdio: one JSON-RPC 2.0 message per line on stdin,
one response per line on stdout (nothing else is ever written to stdout).
Python 3 standard library only; no network, no files written.

Implements: initialize, notifications/* (ignored), ping, tools/list,
tools/call (one tool, "echo"). Any other request gets JSON-RPC error -32601.

The server name reported in serverInfo defaults to "fixture-echo" and can be
changed with --server-name NAME (used for the pre-existing "keep-existing"
entry seeded in project-scope files).
"""
import json
import re
import sys

KNOWN_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ECHO_TOOL = {
    "name": "echo",
    "description": "Return the given text unchanged.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Text to return."}},
        "required": ["text"],
    },
}


def parse_args(argv):
    name = "fixture-echo"
    i = 0
    while i < len(argv):
        if argv[i] == "--server-name" and i + 1 < len(argv):
            name = argv[i + 1]
            i += 2
        else:
            i += 1
    return name


def negotiate(requested):
    # Echo a date-shaped version back so any client generation is accepted;
    # otherwise answer with the newest version this fixture knows.
    if isinstance(requested, str) and VERSION_RE.match(requested):
        return requested
    return KNOWN_VERSIONS[0]


def handle(msg, server_name):
    """Return a response dict, or None for notifications / responses."""
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}}
    if "method" not in msg:
        return None  # a response from the client; nothing to do
    method = msg.get("method")
    has_id = "id" in msg
    if not has_id:
        return None  # notification (e.g. notifications/initialized)
    mid = msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        result = {
            "protocolVersion": negotiate(params.get("protocolVersion")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": server_name, "version": "1.0.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [ECHO_TOOL]}
    elif method == "tools/call":
        if params.get("name") != "echo":
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32602, "message": "Unknown tool"}}
        text = (params.get("arguments") or {}).get("text", "")
        result = {"content": [{"type": "text", "text": str(text)}], "isError": False}
    elif method in ("resources/list", "prompts/list", "resources/templates/list"):
        key = {"resources/list": "resources", "prompts/list": "prompts",
               "resources/templates/list": "resourceTemplates"}[method]
        result = {key: []}
    else:
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main():
    server_name = parse_args(sys.argv[1:])
    out = sys.stdout
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp = {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "Parse error"}}
            out.write(json.dumps(resp, separators=(",", ":")) + "\n")
            out.flush()
            continue
        if isinstance(msg, list):  # JSON-RPC batch (allowed by 2025-03-26)
            resps = [r for r in (handle(m, server_name) for m in msg) if r is not None]
            if resps:
                out.write(json.dumps(resps, separators=(",", ":")) + "\n")
                out.flush()
            continue
        resp = handle(msg, server_name)
        if resp is not None:
            out.write(json.dumps(resp, separators=(",", ":")) + "\n")
            out.flush()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
