#!/usr/bin/env python3
"""Local test server for q07 (Python 3.8+ stdlib only).

    python3 server.py --mode ok|status500|okfalse [--port 18081] [--log server_log.jsonl]

Answers every method and path the same way, so any request file format works:

  ok         200  {"ok": true}
  status500  500  {"ok": true}    (only the status assertion can catch this)
  okfalse    200  {"ok": false}   (only the body-field assertion can catch this)

Listens on 127.0.0.1 and, when available, ::1. Each request is appended to --log as one
JSON line (time, mode, method, path, query, headers, raw body, parsed JSON body).
"""

import argparse
import datetime
import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

MODES = {"ok": (200, {"ok": True}), "status500": (500, {"ok": True}), "okfalse": (200, {"ok": False})}
LOCK = threading.Lock()
CFG = {}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "q07-fixture/1"

    def log_message(self, fmt, *args):
        pass

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n > 0 else b""
        text = raw.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text) if text.strip() else None
        except ValueError:
            parsed = None
        status, obj = MODES[CFG["mode"]]
        u = urlsplit(self.path)
        entry = {"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                 "mode": CFG["mode"], "peer": self.client_address[0], "method": self.command, "path": u.path,
                 "query": u.query, "headers": {k.lower(): v for k, v in self.headers.items()},
                 "body_text": text[:65536], "body_json": parsed, "status": status}
        with LOCK:
            with open(CFG["log"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _handle


class V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=sorted(MODES), required=True)
    ap.add_argument("--port", type=int, default=18081)
    ap.add_argument("--log", default="server_log.jsonl")
    a = ap.parse_args()
    CFG.update({"mode": a.mode, "log": a.log})
    open(a.log, "a").close()
    servers = [ThreadingHTTPServer(("127.0.0.1", a.port), Handler)]
    try:
        servers.append(V6Server(("::1", a.port), Handler))
    except OSError:
        pass
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    sys.stderr.write("q07 server mode=%s on 127.0.0.1:%d%s\n" % (a.mode, a.port,
                                                                 " and [::1]" if len(servers) > 1 else ""))
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
