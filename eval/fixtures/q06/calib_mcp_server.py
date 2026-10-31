#!/usr/bin/env python3
"""Calibration-only MCP server for q06 (Python 3.8+ stdlib only).

This is NOT a candidate answer and is never shown to the agents under test. It exists so
the grader can prove, before any answer is graded, that the mock API, the reference
client, the egress wrapper and check_q06.py together give "pass" for a correct server and
"fail" for broken ones (see calibration.md).

    calib_mcp_server.py --stdio --spec openapi.json --base-url http://127.0.0.1:18080
    calib_mcp_server.py --http-port 18090 --spec openapi.json --base-url http://127.0.0.1:18080
                        [--sse-responses | --legacy-sse]

One tool per operation (name = operationId). Faults for negative controls:
  --fault extra-tool     list a third tool
  --fault spec-servers   ignore --base-url and call the spec's servers[0].url
  --fault drop-body      send POST /items with an empty JSON object
  --fault startup-egress try one TCP connection to 1.1.1.1:80 at startup (errors ignored)
"""

import argparse
import json
import sys
import queue
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def deref(spec, node):
    if isinstance(node, dict):
        if "$ref" in node:
            cur = spec
            for part in node["$ref"].lstrip("#/").split("/"):
                cur = cur[part]
            return deref(spec, cur)
        return {k: deref(spec, v) for k, v in node.items()}
    if isinstance(node, list):
        return [deref(spec, v) for v in node]
    return node


def build_tools(spec, faults):
    tools = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            props, req = {}, []
            for prm in op.get("parameters", []):
                props[prm["name"]] = dict(deref(spec, prm["schema"]), description=prm.get("description", ""))
                if prm.get("required"):
                    req.append(prm["name"])
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if body:
                b = deref(spec, body)
                props.update(b.get("properties", {}))
                req += b.get("required", [])
            tools.append({"name": op["operationId"], "description": op.get("summary", ""),
                          "inputSchema": {"type": "object", "properties": props, "required": req},
                          "_method": method.upper(), "_path": path,
                          "_params": [p["name"] for p in op.get("parameters", [])], "_has_body": bool(body)})
    if "extra-tool" in faults:
        tools.append({"name": "listEndpoints", "description": "List endpoints",
                      "inputSchema": {"type": "object", "properties": {}}, "_method": None})
    return tools


def call_tool(tool, args, base, faults):
    if tool["_method"] is None:
        return {"content": [{"type": "text", "text": "getItem, createItem"}]}
    path = tool["_path"]
    for p in tool["_params"]:
        path = path.replace("{%s}" % p, str(args.get(p)))
    data = None
    if tool["_has_body"]:
        payload = {} if "drop-body" in faults else {k: v for k, v in args.items() if k not in tool["_params"]}
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=tool["_method"],
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with OPENER.open(req, timeout=20) as r:
            text = r.read().decode("utf-8", errors="replace")
            return {"content": [{"type": "text", "text": text}]}
    except (urllib.error.URLError, OSError) as exc:
        return {"content": [{"type": "text", "text": "request failed: %r" % (exc,)}], "isError": True}


class Server:
    def __init__(self, spec, base, faults):
        self.tools = build_tools(spec, faults)
        self.base = spec["servers"][0]["url"] if "spec-servers" in faults else base
        self.faults = faults

    def handle(self, msg):
        if "id" not in msg:
            return None
        m, rid = msg.get("method"), msg["id"]
        if m == "initialize":
            ver = msg.get("params", {}).get("protocolVersion", "2025-06-18")
            res = {"protocolVersion": ver, "capabilities": {"tools": {}},
                   "serverInfo": {"name": "q06-calibration-server", "version": "1.0.0"}}
        elif m == "ping":
            res = {}
        elif m == "tools/list":
            res = {"tools": [{k: v for k, v in t.items() if not k.startswith("_")} for t in self.tools]}
        elif m == "tools/call":
            p = msg.get("params", {})
            tool = next((t for t in self.tools if t["name"] == p.get("name")), None)
            if tool is None:
                return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": "unknown tool"}}
            res = call_tool(tool, p.get("arguments") or {}, self.base, self.faults)
        else:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}
        return {"jsonrpc": "2.0", "id": rid, "result": res}


def serve_stdio(srv):
    for line in sys.stdin:
        if not line.strip():
            continue
        out = srv.handle(json.loads(line))
        if out is not None:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


def serve_http(srv, port, sse_responses=False, legacy=False):
    outbox = queue.Queue()

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _empty(self, code):
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if not legacy or not self.path.startswith("/sse"):
                return self._empty(405)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"event: endpoint\ndata: /messages?sessionId=calib\n\n")
            self.wfile.flush()
            while True:
                msg = outbox.get()
                try:
                    self.wfile.write(b"event: message\ndata: " + json.dumps(msg).encode("utf-8") + b"\n\n")
                    self.wfile.flush()
                except OSError:
                    return

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            out = srv.handle(json.loads(self.rfile.read(n)))
            if legacy:
                if out is not None:
                    outbox.put(out)
                return self._empty(202)
            if out is None:
                return self._empty(202)
            data = json.dumps(out).encode("utf-8")
            self.send_response(200)
            self.send_header("Mcp-Session-Id", "calib-session")
            if sse_responses:
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(b": calibration\n\nevent: message\ndata: " + data + b"\n\n")
                self.close_connection = True
                return
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_DELETE(self):
            self._empty(204)

    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--stdio", action="store_true")
    ap.add_argument("--http-port", type=int)
    ap.add_argument("--sse-responses", action="store_true", help="answer streamable-HTTP POSTs as SSE streams")
    ap.add_argument("--legacy-sse", action="store_true", help="serve the older HTTP+SSE transport (GET /sse)")
    ap.add_argument("--fault", action="append", default=[], choices=["extra-tool", "spec-servers", "drop-body",
                                                                      "startup-egress"])
    a = ap.parse_args()
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    srv = Server(spec, a.base_url, set(a.fault))
    if "startup-egress" in a.fault:
        import socket
        try:
            socket.create_connection(("1.1.1.1", 80), timeout=3).close()
        except OSError:
            pass
    if a.stdio:
        serve_stdio(srv)
    elif a.http_port:
        serve_http(srv, a.http_port, a.sse_responses, a.legacy_sse)
    else:
        sys.exit("give --stdio or --http-port")


if __name__ == "__main__":
    main()
