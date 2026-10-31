#!/usr/bin/env python3
"""Mock of the internal Items API for q06 (Python 3.8+ stdlib only).

    python3 mock_api.py [--port 18080] [--log mock_log.jsonl] [--state mock_state.json]

Listens on 127.0.0.1 and, when available, ::1 (same port). At start it draws a random
per-run token (secrets.token_hex, not a secret, only proof that a reply came from this
process) and writes it with the base URL to --state. Routes:

  GET  /items/{id}     200 {"id", "name", "quantity", "tags", "token"} (id must be an integer)
  POST /items          201 echo of the JSON body plus "id": 1001 and "token"; 400 if not JSON
  GET  /openapi.json   the spec (only for tools that take a spec URL instead of a path)
  GET  /openapi.yaml   the same in YAML
  anything else        404

Every request is appended to --log as one JSON line: time, peer, method, path, query,
headers (an Authorization value is replaced by its scheme and length), the raw body text
and the parsed JSON body. No authentication is required.
"""

import argparse
import datetime
import json
import os
import re
import secrets
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = threading.Lock()
STATE = {}


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "q06-mock/1"

    def log_message(self, fmt, *args):
        pass

    def _record(self, status, body_text, body_json, kind):
        headers = {}
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in ("authorization", "proxy-authorization", "x-api-key", "api-key"):
                parts = v.split(" ", 1)
                v = {"present": True, "scheme": parts[0] if len(parts) == 2 else None, "length": len(v)}
            headers[lk] = v
        u = urlsplit(self.path)
        entry = {"ts": now(), "peer": self.client_address[0], "kind": kind, "method": self.command,
                 "path": u.path, "query": u.query, "headers": headers, "status": status,
                 "body_text": body_text, "body_json": body_json}
        with LOCK:
            with open(STATE["log"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _send(self, status, obj=None, raw=None, ctype="application/json"):
        data = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n > 0 else b""
        text = raw.decode("utf-8", errors="replace")[:65536]
        try:
            parsed = json.loads(text) if text.strip() else None
        except ValueError:
            parsed = None
        return text, parsed

    def _handle(self):
        text, parsed = self._body()
        path = urlsplit(self.path).path
        m = re.fullmatch(r"/items/([^/]+)", path)
        if self.command == "GET" and path in ("/openapi.json", "/openapi.yaml"):
            fn = os.path.join(HERE, path.lstrip("/"))
            ctype = "application/json" if path.endswith(".json") else "application/yaml"
            self._record(200, text, parsed, "spec")
            return self._send(200, raw=open(fn, "rb").read(), ctype=ctype)
        if self.command == "GET" and m:
            try:
                item_id = int(m.group(1))
            except ValueError:
                self._record(400, text, parsed, "api")
                return self._send(400, {"message": "id must be an integer"})
            self._record(200, text, parsed, "api")
            return self._send(200, {"id": item_id, "name": "fixture item %d" % item_id, "quantity": 7,
                                    "tags": ["fixture"], "token": STATE["token"]})
        if self.command == "POST" and path == "/items":
            if not isinstance(parsed, dict):
                self._record(400, text, parsed, "api")
                return self._send(400, {"message": "body must be a JSON object"})
            self._record(201, text, parsed, "api")
            out = dict(parsed)
            out.update({"id": 1001, "token": STATE["token"]})
            return self._send(201, out)
        self._record(404, text, parsed, "api")
        return self._send(404, {"message": "not found"})

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _handle


class V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=18080)
    ap.add_argument("--log", default="mock_log.jsonl")
    ap.add_argument("--state", default="mock_state.json")
    a = ap.parse_args()
    STATE.update({"log": os.path.abspath(a.log), "token": "q06tok-" + secrets.token_hex(8)})
    open(STATE["log"], "a").close()
    servers = [ThreadingHTTPServer(("127.0.0.1", a.port), Handler)]
    try:
        servers.append(V6Server(("::1", a.port), Handler))
    except OSError:
        pass
    state = {"token": STATE["token"], "base_url": "http://127.0.0.1:%d" % a.port, "port": a.port,
             "listening": ["127.0.0.1"] + (["::1"] if len(servers) > 1 else []), "started_utc": now(),
             "log": STATE["log"], "pid": os.getpid()}
    with open(a.state, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    sys.stderr.write("q06 mock listening on %s (and %s), log %s\n" % (state["base_url"], state["listening"],
                                                                      STATE["log"]))
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
