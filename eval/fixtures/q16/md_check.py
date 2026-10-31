#!/usr/bin/env python3
"""q16 L2: the checks on the translated files that need no model.

  files       each of the 3 inputs has one non-empty output .md file (naming
              rule in mdtools.map_outputs; --map NAME=PATH when the answer
              names its outputs otherwise); with --run-log (the step file
              <label>.json that _shared/egress.py run wrote for the translation
              run) also: the run
              ended within 1800 s and was not stopped by the time limit.
  structure   per file: the sequence of fenced code blocks is identical,
              byte for byte (same count, same order, fences and info string
              included); every link URL of the input appears in the output
              at least as many times (inline links, images, autolinks,
              reference definitions, bare URLs); the heading count is equal;
              every number and every product name in the input prose
              appears in the output prose at least as many times.
  verbatim    no input prose sentence of 4+ English words (manifest.json)
              appears unchanged in the output (whitespace collapsed,
              case-sensitive). Half of the item "identified as Portuguese
              ... and no English source sentence appears verbatim"; the other
              half is lang_check.py.
  variant     the output's bullet items in the variant file (the only bullet
              list there) contain words for at least 4 of the 5 concepts in
              the European forms, and none of the Brazilian forms. Matching is
              case-insensitive on NFC text and accepts inflections:
                ficheiro(s) | ecrã(s) | utilizador(es/a/as) | telemóvel/-eis | transfer*
                arquivo(s)  | tela(s) | usuário(s)/usuária(s) | celular(es)  | baixar/baixe/...
              When the output has no bullet item in that file, the whole file
              is searched instead (recorded as a fallback).

Python 3.9+ standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mdtools  # noqa: E402

TIME_LIMIT_S = 1800
PT_PT = {
    "file": r"\bficheiros?\b",
    "screen": r"\becrãs?\b",
    "user": r"\butilizador(?:es|a|as)?\b",
    "mobile phone": r"\btelemóve(?:l|is)\b",
    "to download": r"\btransfer\w*",
}
PT_BR = {
    "file": r"\barquivos?\b",
    "screen": r"\btelas?\b",
    "user": r"\busuári(?:o|os|a|as)\b",
    "mobile phone": r"\bcelular(?:es)?\b",
    "to download": r"\bbaix(?:ar|e|em|ando|ad[oa]s?|ou|ará|arão)\b",
}


def load_manifest(path=None) -> dict:
    with open(path or os.path.join(HERE, "manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def check_files(mapping: dict, run_log=None) -> dict:
    produced = {n: bool(m["path"]) and os.path.getsize(m["path"]) > 0 for n, m in mapping.items()}
    out = {"mapping": mapping, "produced": produced, "all_produced": all(produced.values()) and len(produced) == 3}
    if run_log is not None:
        wall = run_log.get("duration_s")
        in_time = (not run_log.get("timed_out")) and wall is not None and wall <= TIME_LIMIT_S
        out.update(duration_s=wall, time_limit_s=TIME_LIMIT_S, in_time=in_time,
                   run_exit_code=run_log.get("exit_code"))
        out["passed"] = out["all_produced"] and in_time
    else:
        out["passed"] = None
        out["note"] = "pass --run-log to judge the 30-minute limit"
    return out


def check_structure(src: dict, dst: dict) -> dict:
    problems = []
    if len(src["code_blocks"]) != len(dst["code_blocks"]):
        problems.append("code blocks: %d in, %d out" % (len(src["code_blocks"]), len(dst["code_blocks"])))
    for i, (a, b) in enumerate(zip(src["code_blocks"], dst["code_blocks"])):
        if a != b:
            problems.append("code block %d differs" % (i + 1))
    for url in sorted(set(src["urls"])):
        need, got = src["urls"].count(url), dst["urls"].count(url)
        if got < need:
            problems.append("URL %s: %d in, %d out" % (url, need, got))
    if src["headings"] != dst["headings"]:
        problems.append("headings: %d in, %d out" % (src["headings"], dst["headings"]))
    for num, need in src["numbers"].items():
        if dst["numbers"].get(num, 0) < need:
            problems.append("number %s: %d in, %d out" % (num, need, dst["numbers"].get(num, 0)))
    for name, need in src["names"].items():
        if need and dst["names"].get(name, 0) < need:
            problems.append("name %s: %d in, %d out" % (name, need, dst["names"].get(name, 0)))
    return {"passed": not problems, "problems": problems}


def check_verbatim(sentences: list, dst: dict) -> dict:
    hay = " ".join(dst["search_text"].split())
    left = [s["text"] for s in sentences if " ".join(s["text"].split()) in hay]
    return {"passed": not left, "english_left": left, "checked": len(sentences)}


def check_variant(items: list, whole_text: str) -> dict:
    fallback = not items
    text = unicodedata.normalize("NFC", " ".join(items) if items else whole_text)
    pt = {k: bool(re.search(p, text, re.IGNORECASE)) for k, p in PT_PT.items()}
    br = {k: re.findall(p, text, re.IGNORECASE) for k, p in PT_BR.items()}
    br = {k: v for k, v in br.items() if v}
    n_pt = sum(pt.values())
    return {"passed": n_pt >= 4 and not br, "pt_pt_concepts": pt, "pt_pt_count": n_pt, "pt_br_found": br,
            "items_checked": items, "fallback_whole_file": fallback}


def run(args) -> dict:
    manifest = load_manifest(args.manifest)
    overrides = dict(m.split("=", 1) for m in (args.map or []))
    mapping = mdtools.map_outputs(args.input, args.output, overrides)
    run_log = None
    if args.run_log:
        with open(args.run_log, encoding="utf-8") as fh:
            run_log = json.load(fh)
    out = {"tool": "md_check.py", "input": args.input, "output": args.output,
           "files": check_files(mapping, run_log), "per_file": {}}
    integrity = []
    for name, m in mapping.items():
        src_text = mdtools.read(os.path.join(args.input, name))
        if mdtools.sha256_text(src_text) != manifest["files"][name]["sha256"]:
            integrity.append(name)
        src = mdtools.analyze(src_text)
        if not m["path"]:
            out["per_file"][name] = {"structure": {"passed": False, "problems": ["no output file"]},
                                     "verbatim": {"passed": False, "english_left": ["no output file"]}}
            continue
        dst_text = mdtools.read(m["path"])
        dst = mdtools.analyze(dst_text)
        entry = {"structure": check_structure(src, dst),
                 "verbatim": check_verbatim(manifest["files"][name]["sentences"], dst)}
        if name == manifest["variant"]["file"]:
            out["variant"] = check_variant(dst["bullets"], mdtools.plain(dst_text))
        out["per_file"][name] = entry
    if "variant" not in out:
        out["variant"] = {"passed": False, "reason": "no output for %s" % manifest["variant"]["file"]}
    out["fixture_integrity"] = {"passed": not integrity, "changed_inputs": integrity}
    out["items"] = {
        "files_within_30_min": out["files"]["passed"],
        "structure": all(e["structure"]["passed"] for e in out["per_file"].values()) and len(out["per_file"]) == 3,
        "no_verbatim_english": all(e["verbatim"]["passed"] for e in out["per_file"].values()),
        "variant": out["variant"]["passed"],
    }
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default=os.path.join(HERE, "docs"), help="the untouched fixture docs")
    p.add_argument("--output", required=True, help="folder holding the answer's translated files")
    p.add_argument("--map", action="append", help="NAME=PATH when the answer's naming is not recognised")
    p.add_argument("--run-log", help="_shared/egress.py run step file (<label>.json) of the translation run")
    p.add_argument("--manifest")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    out = run(args)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    sys.stderr.write("md_check: %s\n" % json.dumps(out["items"]))
    if not out["fixture_integrity"]["passed"]:
        sys.stderr.write("md_check: WARNING fixture inputs differ from manifest.json\n")
        return 2
    return 0 if all(v is True for v in out["items"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
