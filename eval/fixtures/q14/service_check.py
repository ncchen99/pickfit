#!/usr/bin/env python3
"""q14 L2: one start command brings up one service serving both models.

The grader starts the answer's single start command (exactly one command
line) in the background and passes its PID here. This script then waits, at
most --wait seconds, until
  * POST <embeddings URL> with {"model": <embedding model>, "input": "ping"}
    returns 200 with a non-empty embedding, and
  * the rerank request built by rerank_check.py (same shape options) returns
    200,
and checks that both URLs have the same scheme, host and port (one service).
For the record it also lists the TCP ports in LISTEN state and the processes
descended from --pid (Linux /proc only).

Pass: both endpoints ready within --wait, same origin.

Python 3.9+ standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rerank_check  # noqa: E402  (same folder)


def origin(url: str):
    u = urllib.parse.urlsplit(url)
    port = u.port or (443 if u.scheme == "https" else 80)
    return (u.scheme, u.hostname, port)


def listening_ports(root: str = "/proc/net") -> list:
    ports = set()
    for proto in ("tcp", "tcp6"):
        try:
            with open(os.path.join(root, proto)) as fh:
                lines = fh.read().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) > 3 and parts[3].upper() == "0A":
                ports.add(int(parts[1].split(":")[1], 16))
    return sorted(ports)


def descendants(pid: int, proc_root: str = "/proc") -> list:
    parent = {}
    names = {}
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return []
    for name in entries:
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, name, "stat")) as fh:
                stat = fh.read()
        except OSError:
            continue
        rparen = stat.rfind(")")
        fields = stat[rparen + 2:].split()
        parent[int(name)] = int(fields[1])
        names[int(name)] = stat[stat.find("(") + 1:rparen]
    out, todo = [], [pid]
    while todo:
        cur = todo.pop()
        for child, ppid in parent.items():
            if ppid == cur:
                out.append({"pid": child, "comm": names.get(child)})
                todo.append(child)
    return sorted(out, key=lambda d: d["pid"])


def embed_ready(url: str, model: str, api_key):
    r = rerank_check.post_json(url, {"model": model, "input": "ping"}, api_key, timeout=60)
    if r["status"] != 200:
        return False, r
    try:
        vec = r["json"]["data"][0]["embedding"]
        return (isinstance(vec, (list, str)) and len(vec) > 0), r
    except (KeyError, IndexError, TypeError):
        return False, r


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--embeddings-url", required=True, help="e.g. http://127.0.0.1:PORT/v1/embeddings")
    p.add_argument("--embedding-model", required=True)
    p.add_argument("--rerank-url", required=True)
    p.add_argument("--rerank-shape", required=True, choices=["query-documents", "query-texts", "template"])
    p.add_argument("--rerank-template")
    p.add_argument("--rerank-model")
    p.add_argument("--rerank-extra-json")
    p.add_argument("--api-key-env")
    p.add_argument("--pid", type=int, help="PID of the start command the grader launched")
    p.add_argument("--wait", type=float, default=600.0)
    p.add_argument("--data")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    data = rerank_check.load_data(args.data)["rerank"]
    template = None
    if args.rerank_template:
        with open(args.rerank_template, encoding="utf-8") as fh:
            template = json.load(fh)
    extra = json.loads(args.rerank_extra_json) if args.rerank_extra_json else None
    body = rerank_check.build_body(args.rerank_shape, data["query"], data["passages"], args.rerank_model, template, extra)
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    t0 = time.monotonic()
    emb_ok = rr_ok = False
    last = {}
    while time.monotonic() - t0 < args.wait:
        if not emb_ok:
            emb_ok, last["embeddings"] = embed_ready(args.embeddings_url, args.embedding_model, api_key)
        if not rr_ok:
            r = rerank_check.post_json(args.rerank_url, body, api_key, timeout=60)
            rr_ok, last["rerank"] = r["status"] == 200, r
        if emb_ok and rr_ok:
            break
        time.sleep(3)
    same = origin(args.embeddings_url) == origin(args.rerank_url)
    out = {
        "tool": "service_check.py",
        "embeddings_ready": emb_ok,
        "rerank_ready": rr_ok,
        "ready_after_seconds": round(time.monotonic() - t0, 1),
        "same_origin": same,
        "origins": [list(origin(args.embeddings_url)), list(origin(args.rerank_url))],
        "listening_tcp_ports": listening_ports(),
        "process_tree": descendants(args.pid) if args.pid else None,
        "last_status": {k: v.get("status") for k, v in last.items()},
        "passed": bool(emb_ok and rr_ok and same),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    sys.stderr.write("service_check: passed=%s (embeddings=%s rerank=%s same_origin=%s)\n" % (
        out["passed"], emb_ok, rr_ok, same))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
