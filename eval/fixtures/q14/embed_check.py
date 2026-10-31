#!/usr/bin/env python3
"""q14 L2: embeddings through the pinned openai Python client.

Items covered:
  dims   an English input and a Chinese input (data.json "dimension_check")
         return vectors of the same, non-zero dimension (finite, non-zero norm);
  pairs  for each of the 3 frozen English-Chinese pairs,
         cos(en, its translation) > cos(en, the frozen unrelated distractor).

--client openai (the official check) builds `OpenAI(base_url=..., api_key=...)`
and calls `client.embeddings.create(model=..., input=<one string>)` with no
other option, i.e. "only base_url changed". The api_key is the value of
--api-key-env when the answer's server was started with a key, otherwise a
random throwaway string generated here (the client refuses to start without
one). --client raw posts the same JSON with urllib; it is for testing this
script only and does not count for the item.

Needs the pinned `openai` package for --client openai (see needs.json).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def load_data(path=None) -> dict:
    with open(path or os.path.join(HERE, "data.json"), encoding="utf-8") as fh:
        return json.load(fh)


def cosine(a, b) -> float:
    if len(a) != len(b):
        raise ValueError("dimension mismatch %d vs %d" % (len(a), len(b)))
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        raise ValueError("zero vector")
    return dot / (na * nb)


def openai_embedder(base_url: str, model: str, api_key: str):
    from openai import OpenAI  # pinned version, see needs.json

    client = OpenAI(base_url=base_url, api_key=api_key)

    def embed(text: str):
        resp = client.embeddings.create(model=model, input=text)
        return list(resp.data[0].embedding)

    return embed


def raw_embedder(base_url: str, model: str, api_key: str):
    def embed(text: str):
        body = json.dumps({"model": model, "input": text}).encode("utf-8")
        req = urllib.request.Request(base_url.rstrip("/") + "/embeddings", data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + api_key})
        with OPENER.open(req, timeout=120) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        return list(doc["data"][0]["embedding"])

    return embed


def valid_vector(v) -> bool:
    return (isinstance(v, list) and len(v) > 0 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in v)
            and any(x != 0 for x in v))


def check(embed, data: dict) -> dict:
    out = {"items": {}}
    try:
        en = embed(data["dimension_check"]["en"])
        zh = embed(data["dimension_check"]["zh"])
        out["dims"] = {"en": len(en), "zh": len(zh)}
        ok = valid_vector(en) and valid_vector(zh) and len(en) == len(zh)
        out["items"]["dims"] = {"passed": ok, "en_dim": len(en), "zh_dim": len(zh),
                                "valid": [valid_vector(en), valid_vector(zh)]}
    except Exception as exc:
        out["items"]["dims"] = {"passed": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    try:
        dvec = embed(data["distractor_zh"])
        rows = []
        for pair in data["pairs"]:
            e = embed(pair["en"])
            t = embed(pair["zh"])
            pos, neg = cosine(e, t), cosine(e, dvec)
            rows.append({"id": pair["id"], "cos_translation": round(pos, 6), "cos_distractor": round(neg, 6),
                         "passed": pos > neg})
        out["items"]["pairs"] = {"passed": all(r["passed"] for r in rows), "pairs": rows}
    except Exception as exc:
        out["items"]["pairs"] = {"passed": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", required=True, help="e.g. http://127.0.0.1:PORT/v1 (as in the answer)")
    p.add_argument("--model", required=True, help="embedding model name the answer uses")
    p.add_argument("--api-key-env", help="env var holding the key the server was started with")
    p.add_argument("--client", choices=["openai", "raw"], default="openai")
    p.add_argument("--data")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    api_key = (os.environ.get(args.api_key_env) if args.api_key_env else None) or ("eval-" + secrets.token_hex(16))
    maker = openai_embedder if args.client == "openai" else raw_embedder
    out = {"tool": "embed_check.py", "client": args.client, "base_url": args.base_url, "model": args.model}
    if args.client == "openai":
        try:
            import openai

            out["openai_version"] = getattr(openai, "__version__", None)
        except ImportError:
            raise SystemExit("embed_check: the pinned openai package is not installed (needs.json)")
    out.update(check(maker(args.base_url, args.model, api_key), load_data(args.data)))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    sys.stderr.write("embed_check: dims=%s pairs=%s\n" % (out["items"]["dims"]["passed"], out["items"]["pairs"]["passed"]))
    return 0 if all(v["passed"] for v in out["items"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
