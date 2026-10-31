#!/usr/bin/env python3
"""Transparent HTTP logging proxy for a local model server (Python stdlib only).

Sits between a client and a model server on this machine and relays every
request and response unchanged (streaming bodies are relayed chunk by chunk as
they arrive), while logging what passed through:

  python3 logging_proxy.py --listen 127.0.0.1:11434 --upstream 127.0.0.1:11435 --log-dir STATE/proxy

  STATE/proxy/requests.jsonl  one line per request: times, method, path,
                              status, sizes, header NAMES (never values),
                              model / stream / number of tools / messages
                              parsed from a JSON request body
  STATE/proxy/NNNNNN.req      request body  (capped at --max-body bytes)
  STATE/proxy/NNNNNN.resp     response body (capped at --max-body bytes)

Only changes made to the traffic:
  - Accept-Encoding is sent upstream as "identity" so logged bodies are readable;
  - hop-by-hop headers are not forwarded; each response ends the connection
    ("Connection: close"), with the body sent as received (Content-Length kept,
    otherwise re-chunked).
Authorization and other header values are relayed but never written to the log.

`python3 logging_proxy.py text FILE.resp` prints the model-generated text found
in one logged response (JSON, NDJSON or SSE), for checking by hand.
"""

import argparse
import http.client
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
       "trailers", "transfer-encoding", "upgrade", "expect", "proxy-connection"}

TEXT_KEYS = {"content", "response", "text", "delta", "output_text"}
SKIP_KEYS = {"tool_calls", "function_call", "function", "arguments", "thinking", "reasoning",
             "reasoning_content", "input", "instructions", "messages", "prompt", "tools",
             "logprobs", "usage", "context"}


def collect_text(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in SKIP_KEYS:
                continue
            if isinstance(v, str):
                if k in TEXT_KEYS:
                    out.append(v)
            elif isinstance(v, (dict, list)):
                collect_text(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_text(v, out)


def model_text(body):
    """Model-generated text in a response body: one JSON doc, NDJSON lines, or SSE events."""
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    out = []
    try:
        collect_text(json.loads(body), out)
        return "".join(out)
    except ValueError:
        pass
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]" or line.startswith("event:") or line.startswith(":"):
            continue
        try:
            collect_text(json.loads(line), out)
        except ValueError:
            continue
    return "".join(out)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "logging-proxy"

    def log_message(self, fmt, *args):
        pass

    def _read_body(self):
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in te:
            parts = []
            while True:
                line = self.rfile.readline()
                if not line:
                    break
                size = int(line.split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while True:
                        t = self.rfile.readline()
                        if not t or t in (b"\r\n", b"\n"):
                            break
                    break
                parts.append(self.rfile.read(size))
                self.rfile.readline()
            return b"".join(parts), True
        n = int(self.headers.get("Content-Length") or 0)
        return (self.rfile.read(n) if n else b""), n > 0

    def _proxy(self):
        srv = self.server
        n = srv.next_id()
        t0 = time.time()
        body, has_body = self._read_body()
        fwd = {}
        for k, v in self.headers.items():
            if k.lower() in HOP or k.lower() == "content-length":
                continue
            fwd[k] = v
        fwd["Accept-Encoding"] = "identity"
        entry = {"id": n, "ts_start": t0, "client": "%s:%d" % self.client_address[:2],
                 "method": self.command, "path": self.path,
                 "req_header_names": sorted({k.lower() for k in self.headers.keys()}),
                 "req_bytes": len(body)}
        if body:
            try:
                j = json.loads(body)
                if isinstance(j, dict):
                    entry["model"] = j.get("model")
                    entry["stream"] = j.get("stream")
                    if isinstance(j.get("tools"), list):
                        entry["n_tools"] = len(j["tools"])
                    if isinstance(j.get("messages"), list):
                        entry["n_messages"] = len(j["messages"])
                    if isinstance(j.get("input"), list):
                        entry["n_input_items"] = len(j["input"])
            except ValueError:
                pass
            srv.save(n, "req", body)
        send_body = body if (has_body or self.command in ("POST", "PUT", "PATCH")) else None
        resp_size = 0
        captured = []
        cap_left = srv.max_body
        try:
            conn = http.client.HTTPConnection(srv.up_host, srv.up_port, timeout=srv.up_timeout)
            conn.request(self.command, self.path, body=send_body, headers=fwd)
            resp = conn.getresponse()
        except (OSError, http.client.HTTPException) as e:
            msg = json.dumps({"error": "upstream unavailable: %s" % e}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(msg)
            entry.update({"status": 502, "error": str(e), "ts_end": time.time(), "resp_bytes": len(msg)})
            srv.log(entry)
            self.close_connection = True
            return
        entry["status"] = resp.status
        length = resp.getheader("Content-Length")
        chunked = length is None
        self.send_response_only(resp.status, resp.reason)
        for k, v in resp.getheaders():
            if k.lower() in HOP or k.lower() == "content-length":
                continue
            self.send_header(k, v)
        no_body = self.command == "HEAD" or resp.status in (204, 304) or 100 <= resp.status < 200
        if no_body:
            if length is not None:
                self.send_header("Content-Length", length)
        elif chunked:
            self.send_header("Transfer-Encoding", "chunked")
        else:
            self.send_header("Content-Length", length)
        self.send_header("Connection", "close")
        self.end_headers()
        aborted = False
        if not no_body:
            while True:
                try:
                    data = resp.read1(65536)
                except (OSError, http.client.HTTPException) as e:
                    entry["upstream_read_error"] = str(e)
                    break
                if not data:
                    break
                resp_size += len(data)
                if cap_left > 0:
                    captured.append(data[:cap_left])
                    cap_left -= len(data)
                try:
                    if chunked:
                        self.wfile.write(b"%x\r\n" % len(data) + data + b"\r\n")
                    else:
                        self.wfile.write(data)
                    self.wfile.flush()
                except OSError:
                    aborted = True
                    break
            if chunked and not aborted:
                try:
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except OSError:
                    aborted = True
        conn.close()
        entry.update({"ts_end": time.time(), "resp_bytes": resp_size,
                      "resp_content_type": resp.getheader("Content-Type"),
                      "client_aborted": aborted, "resp_truncated_in_log": cap_left < 0})
        if captured:
            srv.save(n, "resp", b"".join(captured))
        srv.log(entry)
        self.close_connection = True

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_OPTIONS = do_PATCH = _proxy


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, family, up, log_dir, max_body, timeout, shared):
        self.address_family = family
        self.up_host, self.up_port = up
        self.log_dir = log_dir
        self.max_body = max_body
        self.up_timeout = timeout
        self.shared = shared
        ThreadingHTTPServer.__init__(self, addr, Handler)

    def next_id(self):
        with self.shared["lock"]:
            self.shared["n"] += 1
            return self.shared["n"]

    def save(self, n, kind, data):
        with open(os.path.join(self.log_dir, "%06d.%s" % (n, kind)), "wb") as f:
            f.write(data[: self.max_body])

    def log(self, entry):
        with self.shared["lock"]:
            with open(os.path.join(self.log_dir, "requests.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")


def parse_hostport(s):
    if s.startswith("["):
        host, _, port = s[1:].partition("]:")
        return host, int(port), socket.AF_INET6
    host, _, port = s.rpartition(":")
    return host, int(port), (socket.AF_INET6 if ":" in host else socket.AF_INET)


def existing_max_id(log_dir):
    n = 0
    for f in os.listdir(log_dir):
        base = f.split(".")[0]
        if base.isdigit():
            n = max(n, int(base))
    return n


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "text":
        for path in argv[1:]:
            with open(path, "rb") as f:
                print(model_text(f.read()))
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listen", action="append", required=True, help="HOST:PORT, may be repeated ([::1]:PORT for IPv6)")
    ap.add_argument("--upstream", required=True, help="HOST:PORT of the real server")
    ap.add_argument("--log-dir", required=True)
    ap.add_argument("--max-body", type=int, default=8 * 1024 * 1024)
    ap.add_argument("--timeout", type=float, default=1800.0, help="upstream socket timeout in seconds")
    a = ap.parse_args(argv)
    os.makedirs(a.log_dir, exist_ok=True)
    uh, up, _ = parse_hostport(a.upstream)
    shared = {"lock": threading.Lock(), "n": existing_max_id(a.log_dir)}
    servers = []
    for i, l in enumerate(a.listen):
        h, p, fam = parse_hostport(l)
        try:
            servers.append(Server((h, p), fam, (uh, up), a.log_dir, a.max_body, a.timeout, shared))
        except OSError as e:
            if i == 0:
                raise
            print("logging_proxy: cannot listen on %s (%s); continuing without it" % (l, e), file=sys.stderr)
    with open(os.path.join(a.log_dir, "proxy.start.json"), "w") as f:
        json.dump({"ts": time.time(), "listen": a.listen, "upstream": a.upstream, "pid": os.getpid()}, f)
    threads = []
    for s in servers[1:]:
        t = threading.Thread(target=s.serve_forever)
        t.daemon = True
        t.start()
        threads.append(t)
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
