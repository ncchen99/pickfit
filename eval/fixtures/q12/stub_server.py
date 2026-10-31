#!/usr/bin/env python3
"""q12 self-test only: a tiny OpenAI-style chat server with canned replies
(Python 3.8+ stdlib). It loads no model and is never used to grade an answer;
it lets the grader check client_check.py, the pinned openai client and the
offline procedure before the first run.

  python3 stub_server.py --port 18080 [--mode good|one-chunk|empty|drop|error]

Modes:
  good       non-streaming reply with text; streaming reply in 4 chunks + [DONE]
  one-chunk  streaming reply in a single chunk (+ [DONE])
  empty      non-streaming reply with empty content
  drop       streaming response cut off in the middle (connection closed)
  error      HTTP 500 for every chat request
Binds 127.0.0.1 only.
"""
import argparse
import json
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = "good"
WORDS = ["The ", "sea ", "is ", "calm."]


def completion(content):
    return {"id": "stub-1", "object": "chat.completion", "created": int(time.time()), "model": "stub-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


def chunk(delta, finish=None):
    return {"id": "stub-1", "object": "chat.completion.chunk", "created": int(time.time()), "model": "stub-model",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("stub: " + fmt % args + "\n")

    def send_json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self.send_json(200, {"object": "list", "data": [{"id": "stub-model", "object": "model", "owned_by": "stub"}]})
        else:
            self.send_json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n) or b"{}")
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self.send_json(404, {"error": {"message": "not found"}})
        if MODE == "error":
            return self.send_json(500, {"error": {"message": "stub error"}})
        if not body.get("stream"):
            return self.send_json(200, completion("" if MODE == "empty" else "".join(WORDS)))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def sse(obj):
            payload = ("data: %s\n\n" % (obj if isinstance(obj, str) else json.dumps(obj))).encode()
            self.wfile.write(b"%x\r\n%s\r\n" % (len(payload), payload))
            self.wfile.flush()

        if MODE == "one-chunk":
            sse(chunk({"role": "assistant", "content": "".join(WORDS)}, "stop"))
        else:
            sse(chunk({"role": "assistant", "content": ""}))
            for i, w in enumerate(WORDS):
                if MODE == "drop" and i == 2:
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.close_connection = True
                    return
                sse(chunk({"content": w}))
            sse(chunk({}, "stop"))
        sse("[DONE]")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()


def main(argv=None):
    global MODE
    ap = argparse.ArgumentParser(description="q12 stub server (self-test only)")
    ap.add_argument("--port", type=int, default=18080)
    ap.add_argument("--mode", default="good", choices=["good", "one-chunk", "empty", "drop", "error"])
    a = ap.parse_args(argv)
    MODE = a.mode
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print("stub server on http://127.0.0.1:%d/v1 (mode %s)" % (a.port, a.mode))
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
