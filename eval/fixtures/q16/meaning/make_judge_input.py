#!/usr/bin/env python3
"""q16 L2 meaning check: build the blind judge's inputs and score its verdicts.

  build     the 5 frozen sample sentences (manifest.json meaning_sample) with
            their English paragraph and the output's prose blocks at the same
            position (block k-1, k, k+1 of the mapped output file, as plain
            text). Nothing in the file names the answer, its tools or its group.
  sheet     the same as a Markdown sheet for a human grader who reads
            Portuguese.
  requests  one Anthropic Messages API request body per sentence (JSON Lines),
            system prompt = rubric.md, temperature 0, for the pinned model
            recorded in calibration.md. This script makes no API call.
            With --no-temperature (a model that rejects the parameter) write
            each request 3 times; the score then needs 2 of 3 PASS per
            sentence (eval/README.md section 5).
  score     read verdicts (JSON Lines: {"n": 1, "run": 1, "verdict": "PASS"|"FAIL",
            "reason": "..."}) and apply the item: at least 4 of 5 sentences pass.

Python 3.9+ standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import mdtools  # noqa: E402

NEED = 4


def _block_text(block: dict) -> str:
    units = block["items"] if block["kind"] == "list" else [block["text"]]
    return "\n".join(mdtools.plain(u) for u in units)


def build(input_dir: str, output_dir: str, overrides: dict, manifest: dict) -> dict:
    mapping = mdtools.map_outputs(input_dir, output_dir, overrides)
    items = []
    for n, s in enumerate(manifest["meaning_sample"]["sentences"], 1):
        name, rest = s["id"].split("#", 1)
        k = int(re.match(r"b(\d+)s", rest).group(1))
        src_prose = mdtools.analyze(mdtools.read(os.path.join(input_dir, name)))["prose"]
        item = {"n": n, "sentence_id": s["id"], "source_sentence": s["text"],
                "source_paragraph": _block_text(src_prose[k])}
        path = mapping[name]["path"]
        if path:
            out_prose = mdtools.analyze(mdtools.read(path))["prose"]
            item["portuguese_text"] = "\n\n".join(_block_text(out_prose[i]) for i in range(k - 1, k + 2)
                                                  if 0 <= i < len(out_prose))
        else:
            item["portuguese_text"] = ""
            item["note"] = "no output file: counts as FAIL"
        items.append(item)
    return {"purpose": "q16 meaning check, blind judge input", "need": NEED, "items": items}


def user_message(item: dict) -> str:
    return ("SOURCE SENTENCE:\n%s\n\nSOURCE PARAGRAPH:\n%s\n\nPORTUGUESE TEXT:\n%s\n"
            % (item["source_sentence"], item["source_paragraph"], item["portuguese_text"] or "(missing)"))


def cmd_build(args) -> int:
    with open(args.manifest or os.path.join(ROOT, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    overrides = dict(m.split("=", 1) for m in (args.map or []))
    data = build(args.input, args.output, overrides, manifest)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return 0


def cmd_sheet(args) -> int:
    with open(args.items, encoding="utf-8") as fh:
        data = json.load(fh)
    with open(os.path.join(HERE, "rubric.md"), encoding="utf-8") as fh:
        rubric = fh.read()
    parts = ["# q16 meaning check (blind)\n", rubric, "\n---\n"]
    for it in data["items"]:
        parts.append("## Sentence %d\n\n%s\n\nVerdict (PASS/FAIL): ____  Reason: ________\n" % (it["n"], user_message(it)))
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    return 0


def cmd_requests(args) -> int:
    with open(args.items, encoding="utf-8") as fh:
        data = json.load(fh)
    with open(os.path.join(HERE, "rubric.md"), encoding="utf-8") as fh:
        rubric = fh.read()
    runs = 3 if args.no_temperature else 1
    with open(args.out, "w", encoding="utf-8") as fh:
        for it in data["items"]:
            for run in range(1, runs + 1):
                body = {"model": args.model, "max_tokens": 300, "system": rubric,
                        "messages": [{"role": "user", "content": user_message(it)}]}
                if not args.no_temperature:
                    body["temperature"] = 0
                fh.write(json.dumps({"n": it["n"], "run": run, "body": body}, ensure_ascii=False) + "\n")
    return 0


def parse_verdict(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(0)).get("verdict")
    except ValueError:
        return None
    return v.upper() if isinstance(v, str) and v.upper() in ("PASS", "FAIL") else None


def score(rows: list, items: int = 5) -> dict:
    by_n: dict = {}
    for r in rows:
        v = r.get("verdict")
        if isinstance(v, str) and v.upper() not in ("PASS", "FAIL"):
            v = parse_verdict(v)
        by_n.setdefault(int(r["n"]), []).append((v or "FAIL").upper())
    per = {}
    for n in range(1, items + 1):
        vs = by_n.get(n, [])
        if len(vs) >= 3:
            ok = sum(v == "PASS" for v in vs) >= 2
        else:
            ok = bool(vs) and vs[0] == "PASS"
        per[n] = {"verdicts": vs, "passed": ok}
    passed = sum(p["passed"] for p in per.values())
    return {"per_sentence": per, "passed_sentences": passed, "need": NEED, "passed": passed >= NEED}


def cmd_score(args) -> int:
    with open(args.verdicts, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    res = score(rows)
    json.dump(res, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if res["passed"] else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="action", required=True)
    sp = sub.add_parser("build")
    sp.add_argument("--input", default=os.path.join(ROOT, "docs"))
    sp.add_argument("--output", required=True)
    sp.add_argument("--map", action="append")
    sp.add_argument("--manifest")
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_build)
    sp = sub.add_parser("sheet")
    sp.add_argument("--items", required=True)
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_sheet)
    sp = sub.add_parser("requests")
    sp.add_argument("--items", required=True)
    sp.add_argument("--model", required=True, help="pinned judge model id from calibration.md")
    sp.add_argument("--no-temperature", action="store_true")
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_requests)
    sp = sub.add_parser("score")
    sp.add_argument("--verdicts", required=True)
    sp.set_defaults(func=cmd_score)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
