#!/usr/bin/env python3
"""q14 L2: one rerank request with the frozen query and 5 passages.

The request format is the one the answer gives, or, when the answer gives
none, the one in the server's docs for the installed version. The grader
records which (README.md). Three ways to build the body:

  --shape query-documents  {"model"?, "query": Q, "documents": [5 strings]}
  --shape query-texts      {"model"?, "query": Q, "texts": [5 strings]}
  --shape template --template FILE
                           any JSON body; the strings "{{query}}",
                           "{{documents}}" and "{{model}}" are replaced
                           (documents by the list itself)
  --extra-json '{"top_n": 5}' merges extra fields named by the answer or docs.

Reading the response (no format is assumed): the result list is the response
itself when it is a list, else the first list found under results, data,
rankings, ranking, result or documents. Each entry gives a passage index
(index, document_index, doc_index, corpus_id) or the passage text (document,
text), and optionally a score (relevance_score, score, relevance, logit,
similarity). With scores the ranking is by score, highest first; without them
it is the returned order. A list of bare numbers with one per passage is read
as scores in passage order. --index-key / --score-key override the names.

Pass: the relevant passage (data.json relevant_index) is first, and with
scores its score is strictly higher than every other passage's.

Python 3.9+ standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
LIST_KEYS = ("results", "data", "rankings", "ranking", "result", "documents")
INDEX_KEYS = ("index", "document_index", "doc_index", "corpus_id")
SCORE_KEYS = ("relevance_score", "score", "relevance", "logit", "similarity")
TEXT_KEYS = ("document", "text")


def load_data(path=None) -> dict:
    with open(path or os.path.join(HERE, "data.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _fill(node, query, docs, model):
    if isinstance(node, dict):
        return {k: _fill(v, query, docs, model) for k, v in node.items()}
    if isinstance(node, list):
        return [_fill(v, query, docs, model) for v in node]
    if node == "{{documents}}":
        return list(docs)
    if node == "{{query}}":
        return query
    if node == "{{model}}":
        return model
    return node


def build_body(shape: str, query: str, docs: list, model=None, template=None, extra=None) -> dict:
    if shape == "query-documents":
        body = {"query": query, "documents": list(docs)}
    elif shape == "query-texts":
        body = {"query": query, "texts": list(docs)}
    elif shape == "template":
        if template is None:
            raise ValueError("--shape template needs --template")
        body = _fill(template, query, docs, model)
    else:
        raise ValueError("unknown shape %r" % shape)
    if model and shape != "template":
        body = dict({"model": model}, **body)
    if extra:
        body.update(extra)
    return body


def post_json(url: str, body: dict, api_key=None, timeout=120.0) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except Exception as exc:
        return {"status": None, "json": None, "error": "%s: %s" % (type(exc).__name__, exc)}
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        doc = None
    return {"status": status, "json": doc, "error": None if status == 200 else raw[:300].decode("utf-8", "replace")}


def _first_list(doc):
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        for k in LIST_KEYS:
            if isinstance(doc.get(k), list):
                return doc[k]
    return None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def ranking(doc, docs: list, index_key=None, score_key=None) -> dict:
    items = _first_list(doc)
    if not items:
        return {"error": "no result list in the response"}
    entries = []
    if all(_num(x) is not None for x in items) and len(items) == len(docs):
        entries = [(i, float(x), i) for i, x in enumerate(items)]
    else:
        for pos, item in enumerate(items):
            if not isinstance(item, dict):
                return {"error": "result entry %d is not an object" % pos}
            idx = None
            for k in ([index_key] if index_key else INDEX_KEYS):
                if isinstance(item.get(k), int) and not isinstance(item.get(k), bool):
                    idx = item[k]
                    break
            if idx is None:
                for k in TEXT_KEYS:
                    text = item.get(k)
                    if isinstance(text, dict):
                        text = text.get("text")
                    if isinstance(text, str) and text in docs:
                        idx = docs.index(text)
                        break
            score = None
            for k in ([score_key] if score_key else SCORE_KEYS):
                if _num(item.get(k)) is not None:
                    score = float(item[k])
                    break
            entries.append((idx, score, pos))
    if any(e[0] is None or not 0 <= e[0] < len(docs) for e in entries):
        return {"error": "a result entry has no usable passage index", "entries": entries}
    scored = all(e[1] is not None for e in entries)
    order = sorted(entries, key=lambda e: (-e[1], e[2])) if scored else sorted(entries, key=lambda e: e[2])
    return {"order": [e[0] for e in order], "scores": {e[0]: e[1] for e in entries} if scored else None,
            "by": "score" if scored else "returned order"}


def judge(rank: dict, relevant: int) -> dict:
    if "error" in rank:
        return {"passed": False, "reason": rank["error"]}
    if not rank["order"] or rank["order"][0] != relevant:
        return {"passed": False, "reason": "relevant passage is not first", "order": rank["order"]}
    if rank["scores"] is not None:
        top = rank["scores"][relevant]
        others = [s for i, s in rank["scores"].items() if i != relevant]
        if others and not all(top > s for s in others):
            return {"passed": False, "reason": "relevant passage ties for first", "order": rank["order"]}
    return {"passed": True, "order": rank["order"], "by": rank["by"]}


def run(args) -> dict:
    data = load_data(args.data)
    r = data["rerank"]
    template = None
    if args.template:
        with open(args.template, encoding="utf-8") as fh:
            template = json.load(fh)
    extra = json.loads(args.extra_json) if args.extra_json else None
    body = build_body(args.shape, r["query"], r["passages"], args.model, template, extra)
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    resp = post_json(args.url, body, api_key)
    out = {"tool": "rerank_check.py", "url": args.url, "shape": args.shape, "format_source": args.format_source,
           "request_body": body, "status": resp["status"], "response": resp["json"], "error": resp["error"]}
    if resp["status"] != 200:
        out["item"] = {"passed": False, "reason": "HTTP status %s" % resp["status"]}
    else:
        out["item"] = judge(ranking(resp["json"], r["passages"], args.index_key, args.score_key), r["relevant_index"])
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", required=True, help="full rerank endpoint URL from the answer or the docs")
    p.add_argument("--shape", required=True, choices=["query-documents", "query-texts", "template"])
    p.add_argument("--template")
    p.add_argument("--model")
    p.add_argument("--extra-json")
    p.add_argument("--format-source", required=True, choices=["answer", "server-docs"],
                   help="where the request format came from (recorded)")
    p.add_argument("--api-key-env")
    p.add_argument("--index-key")
    p.add_argument("--score-key")
    p.add_argument("--data")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    out = run(args)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    sys.stderr.write("rerank_check: %s\n" % json.dumps(out["item"], ensure_ascii=False))
    return 0 if out["item"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
