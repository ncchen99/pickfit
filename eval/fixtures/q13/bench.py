#!/usr/bin/env python3
"""q13 L2: concurrent chat completions and the throughput ratio.

Sends the frozen prompt (prompt.json) to an OpenAI-compatible
/v1/chat/completions endpoint, the same way for every server:

  1. wait until the endpoint answers (GET {base}/models, or a 1-token chat
     request when /models is missing), at most --wait seconds;
  2. one warm-up request (not measured);
  3. `rounds` times: one single request, then `concurrency` requests released
     together by a barrier.

Item "4 concurrent requests ... all return 200 with non-empty content" is
judged on round 1's concurrent batch. Item "aggregate throughput ... at least
1.5 times that of a single warmed-up request" uses
  single_tps     = completion_tokens / seconds of that request
  concurrent_tps = sum(completion_tokens of 200 responses) / wall seconds from
                   the barrier release to the last response
  ratio          = median(concurrent_tps over rounds) / median(single_tps)
A response without usage.completion_tokens makes the throughput item fail
(reason "usage missing"), because the item is defined on that field.

Python 3.9+ standard library only. No proxy is used (localhost).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _headers(api_key):
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = "Bearer " + api_key
    return h


def http(method, url, body=None, api_key=None, timeout=600.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers(api_key))
    t0 = time.monotonic()
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except Exception as exc:  # connection refused, timeout, reset
        return {"status": None, "error": "%s: %s" % (type(exc).__name__, exc), "seconds": time.monotonic() - t0}
    out = {"status": status, "seconds": time.monotonic() - t0, "error": None}
    try:
        out["json"] = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        out["json"] = None
        out["raw"] = raw[:500].decode("utf-8", "replace")
    return out


def chat(base, model, prompt, api_key, timeout, max_tokens=None):
    body = {
        "model": model,
        "messages": prompt["messages"],
        "max_tokens": max_tokens if max_tokens is not None else prompt["max_tokens"],
        "temperature": prompt["temperature"],
        "stream": False,
    }
    r = http("POST", base.rstrip("/") + "/chat/completions", body, api_key, timeout)
    content, tokens, finish = None, None, None
    doc = r.get("json") or {}
    try:
        choice = doc["choices"][0]
        content = choice["message"]["content"]
        finish = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError):
        pass
    try:
        tokens = int(doc["usage"]["completion_tokens"])
    except (KeyError, TypeError, ValueError):
        tokens = None
    ok = r["status"] == 200 and isinstance(content, str) and content.strip() != ""
    return {
        "status": r["status"],
        "ok": ok,
        "seconds": round(r["seconds"], 4),
        "completion_tokens": tokens,
        "content_chars": len(content) if isinstance(content, str) else 0,
        "content_head": content[:120] if isinstance(content, str) else None,
        "finish_reason": finish,
        "error": r.get("error") or (None if r["status"] == 200 else (r.get("raw") or json.dumps(doc)[:300])),
    }


def wait_ready(base, model, prompt, api_key, wait):
    deadline = time.monotonic() + wait
    last = None
    while time.monotonic() < deadline:
        r = http("GET", base.rstrip("/") + "/models", None, api_key, 10)
        if r["status"] == 200:
            return {"ready": True, "via": "GET /models", "models": r.get("json")}
        c = chat(base, model, prompt, api_key, 60, max_tokens=1)
        if c["status"] == 200:
            return {"ready": True, "via": "1-token chat request", "models": None}
        last = r.get("error") or c.get("error")
        time.sleep(2)
    return {"ready": False, "last_error": last}


def pick_model(models_doc):
    try:
        return models_doc["data"][0]["id"]
    except (KeyError, IndexError, TypeError):
        return None


def concurrent_batch(base, model, prompt, api_key, n, timeout):
    results = [None] * n
    ends = [None] * n
    barrier = threading.Barrier(n + 1)

    def worker(i):
        barrier.wait()
        results[i] = chat(base, model, prompt, api_key, timeout)
        ends[i] = time.monotonic()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    barrier.wait()
    t0 = time.monotonic()
    for t in threads:
        t.join()
    wall = max(ends) - t0
    tokens = [r["completion_tokens"] for r in results]
    usage_missing = any(r["ok"] and r["completion_tokens"] is None for r in results)
    total = sum(r["completion_tokens"] or 0 for r in results if r["ok"])
    return {
        "requests": results,
        "wall_seconds": round(wall, 4),
        "all_ok": all(r["ok"] for r in results),
        "completion_tokens": tokens,
        "usage_missing": usage_missing,
        "tps": round(total / wall, 4) if wall > 0 else None,
    }


def single(base, model, prompt, api_key, timeout):
    r = chat(base, model, prompt, api_key, timeout)
    tps = None
    if r["ok"] and r["completion_tokens"] and r["seconds"] > 0:
        tps = round(r["completion_tokens"] / r["seconds"], 4)
    return dict(r, tps=tps, usage_missing=r["ok"] and r["completion_tokens"] is None)


def run(args) -> dict:
    with open(args.prompt, encoding="utf-8") as fh:
        prompt = json.load(fh)
    n = args.concurrency or prompt["concurrency"]
    rounds = args.rounds or prompt["rounds"]
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    ready = wait_ready(args.base_url, args.model or "default", prompt, api_key, args.wait)
    out = {"tool": "bench.py", "base_url": args.base_url, "prompt_file": os.path.basename(args.prompt),
           "max_tokens": prompt["max_tokens"], "temperature": prompt["temperature"],
           "concurrency": n, "rounds": rounds, "ready": ready}
    if not ready["ready"]:
        out["items"] = {"concurrent_ok": {"passed": False, "reason": "server never became ready"},
                        "throughput": {"passed": False, "reason": "server never became ready"}}
        return out
    model = args.model or pick_model(ready.get("models")) or "default"
    out["model"] = model
    out["warmup"] = single(args.base_url, model, prompt, api_key, args.timeout)
    out["rounds_detail"] = []
    for _ in range(rounds):
        s = single(args.base_url, model, prompt, api_key, args.timeout)
        c = concurrent_batch(args.base_url, model, prompt, api_key, n, args.timeout)
        out["rounds_detail"].append({"single": s, "concurrent": c})
    first = out["rounds_detail"][0]["concurrent"]
    out["items"] = {"concurrent_ok": {
        "passed": first["all_ok"],
        "statuses": [r["status"] for r in first["requests"]],
        "non_empty": [r["content_chars"] > 0 for r in first["requests"]],
    }}
    singles = [r["single"]["tps"] for r in out["rounds_detail"]]
    concs = [r["concurrent"]["tps"] for r in out["rounds_detail"]]
    usage_missing = any(r["single"]["usage_missing"] or r["concurrent"]["usage_missing"] for r in out["rounds_detail"])
    if usage_missing:
        out["items"]["throughput"] = {"passed": False, "reason": "usage missing: a 200 response had no usage.completion_tokens"}
    elif any(t is None for t in singles):
        out["items"]["throughput"] = {"passed": False, "reason": "a single request failed", "single_tps": singles}
    else:
        ratio = statistics.median([c or 0.0 for c in concs]) / statistics.median(singles)
        out["items"]["throughput"] = {
            "passed": ratio >= prompt["throughput_ratio_min"],
            "ratio": round(ratio, 3),
            "min_ratio": prompt["throughput_ratio_min"],
            "single_tps": singles,
            "concurrent_tps": concs,
        }
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", required=True, help="e.g. http://127.0.0.1:8080/v1")
    p.add_argument("--model", help="model name the answer uses (default: first id from GET /models)")
    p.add_argument("--prompt", default=os.path.join(HERE, "prompt.json"))
    p.add_argument("--concurrency", type=int)
    p.add_argument("--rounds", type=int)
    p.add_argument("--api-key-env", help="env var holding a key, if the answer's server requires one")
    p.add_argument("--wait", type=float, default=600.0, help="seconds to wait for the server")
    p.add_argument("--timeout", type=float, default=600.0, help="per-request timeout")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    out = run(args)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    items = out["items"]
    sys.stderr.write("bench: concurrent_ok=%s throughput=%s ratio=%s\n" % (
        items["concurrent_ok"]["passed"], items["throughput"]["passed"], items["throughput"].get("ratio")))
    return 0 if all(v["passed"] for v in items.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
