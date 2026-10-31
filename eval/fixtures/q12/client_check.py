#!/usr/bin/env python3
"""q12 L2-3/L2-4 (and L2-5 after a restart): call the local server with the
pinned official openai Python client.

  python client_check.py --base-url http://127.0.0.1:PORT/v1 --model MODEL [--out result.json]

  * non-streaming: chat.completions.create(...) must return a non-empty
    choices[0].message.content (whitespace-only counts as empty);
  * streaming: chat.completions.create(..., stream=True) must yield at least 2
    chunks and the SDK's iterator must finish without raising.

The request carries only model, messages and max_tokens. The client makes no
retries (max_retries=0), so a failure is seen as it is. No API key is needed by
a local server, but the SDK requires one: unless --api-key is given (use it
only when the answer names one), a random dummy key is generated at run time
and never printed or saved.

--raw does the same two requests with urllib instead of the SDK. It is for
diagnosis and for this folder's self-test only; it never counts for grading.

Exit 0 when both checks pass, 1 otherwise, 2 when the openai package is missing.
"""
import argparse
import json
import secrets
import sys
import time
import urllib.request

PROMPT = "Reply with one short sentence about the sea."
MAX_TOKENS = 64


def sdk_checks(base_url, model, api_key, timeout):
    try:
        import openai
    except ImportError:
        print("the openai package is not installed in this Python; use the pinned grader venv (calibration.md)")
        sys.exit(2)
    client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)
    res = {"client": "openai-python %s" % openai.__version__}
    msgs = [{"role": "user", "content": PROMPT}]

    t = time.time()
    try:
        r = client.chat.completions.create(model=model, messages=msgs, max_tokens=MAX_TOKENS)
        content = r.choices[0].message.content if r.choices else None
        ok = isinstance(content, str) and content.strip() != ""
        res["nonstream"] = {"pass": ok, "content": content, "finish_reason": r.choices[0].finish_reason if r.choices else None,
                            "seconds": round(time.time() - t, 2)}
    except Exception as e:  # any SDK or transport error fails the check
        res["nonstream"] = {"pass": False, "error": "%s: %s" % (type(e).__name__, e), "seconds": round(time.time() - t, 2)}

    t = time.time()
    chunks, content_chunks, text, finish = 0, 0, [], None
    try:
        stream = client.chat.completions.create(model=model, messages=msgs, max_tokens=MAX_TOKENS, stream=True)
        for ch in stream:
            chunks += 1
            if ch.choices:
                d = ch.choices[0].delta
                if d is not None and getattr(d, "content", None):
                    content_chunks += 1
                    text.append(d.content)
                if ch.choices[0].finish_reason:
                    finish = ch.choices[0].finish_reason
        res["stream"] = {"pass": chunks >= 2, "chunks": chunks, "content_chunks": content_chunks,
                         "text": "".join(text), "finish_reason": finish, "seconds": round(time.time() - t, 2)}
    except Exception as e:
        res["stream"] = {"pass": False, "chunks": chunks, "error": "%s: %s" % (type(e).__name__, e),
                         "seconds": round(time.time() - t, 2)}
    return res


def raw_checks(base_url, model, api_key, timeout):
    url = base_url.rstrip("/") + "/chat/completions"
    hdr = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}
    res = {"client": "urllib (diagnosis only, not for grading)"}
    body = {"model": model, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": MAX_TOKENS}
    try:
        req = urllib.request.Request(url, json.dumps(body).encode(), hdr)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        res["nonstream"] = {"pass": isinstance(content, str) and content.strip() != "", "content": content}
    except Exception as e:
        res["nonstream"] = {"pass": False, "error": "%s: %s" % (type(e).__name__, e)}
    body["stream"] = True
    chunks, done = 0, False
    try:
        req = urllib.request.Request(url, json.dumps(body).encode(), hdr)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for line in r:
                line = line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    done = True
                    break
                json.loads(payload)
                chunks += 1
        res["stream"] = {"pass": chunks >= 2 and done, "chunks": chunks, "done_marker": done}
        if chunks >= 2 and not done:
            res["stream"]["error"] = "stream ended without data: [DONE]"
    except Exception as e:
        res["stream"] = {"pass": False, "chunks": chunks, "error": "%s: %s" % (type(e).__name__, e)}
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="q12 OpenAI-client checks")
    ap.add_argument("--base-url", required=True, help="e.g. http://127.0.0.1:8080/v1")
    ap.add_argument("--model", required=True, help="the model name the answer says to send")
    ap.add_argument("--api-key", help="only if the answer names one; otherwise a dummy is generated")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--out")
    ap.add_argument("--raw", action="store_true", help="urllib instead of the SDK (diagnosis only)")
    a = ap.parse_args(argv)
    key = a.api_key or ("eval-dummy-" + secrets.token_hex(16))
    res = (raw_checks if a.raw else sdk_checks)(a.base_url, a.model, key, a.timeout)
    res.update({"base_url": a.base_url, "model": a.model, "prompt": PROMPT, "max_tokens": MAX_TOKENS,
                "api_key": "given by the answer" if a.api_key else "generated dummy (not recorded)",
                "python": sys.version.split()[0], "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    print("client: %s" % res["client"])
    n, s = res["nonstream"], res["stream"]
    print("L2-3 non-streaming: %s%s" % ("PASS" if n["pass"] else "FAIL",
                                       " - %r" % (n.get("content") or "")[:80] if n["pass"] else " - " + str(n.get("error", "empty content"))))
    print("L2-4 streaming: %s (%d chunks)%s" % ("PASS" if s["pass"] else "FAIL", s.get("chunks", 0),
                                               "" if s["pass"] else " - " + str(s.get("error", "fewer than 2 chunks"))))
    return 0 if n["pass"] and s["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
