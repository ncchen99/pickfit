#!/usr/bin/env python3
"""q15 L2-3 and L2-4: character error rate and the Traditional-script ratio.

Both come from the shared OpenCC scorer, eval/fixtures/_shared/zh_script.py
(_shared/README.md section 2), with the pinned OpenCC dictionary files in
--dict-dir; q11 uses the same scorer and the same files.

  cer        CER of the answer's SRT text against reference.txt. Both sides:
             Unicode NFKC, then the shared s2tw conversion (to Traditional,
             Taiwan variants), then every character that is not a letter or a
             digit is removed (punctuation, symbols, spaces, line breaks), Latin
             letters lower-cased. CER = Levenshtein distance / reference
             length. Pass: CER <= 0.25.
  script     the shared Traditional ratio of the answer's SRT text, characters
             as written (no conversion of the answer). Pass: Traditional +
             Simplified >= 30 and ratio >= 0.95.
  ref-stats  script-differing characters of the reference after s2tw; the item
             requires at least 60.
  all        cer + script in one JSON.

The answer's text is the concatenation of its SRT cue texts (srt_check.py
reads the file; formatting tags are removed there). Python 3.9+, stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.environ.get("SHARED") or os.path.join(HERE, "..", "_shared"))
import zh_script  # noqa: E402

CER_MAX = 0.25
MIN_DIFFERING_REFERENCE = 60


def normalize_for_cer(text: str, tables) -> str:
    text = tables.s2tw(unicodedata.normalize("NFKC", text))
    return "".join(ch.lower() for ch in text if unicodedata.category(ch)[0] in "LN")


def edit_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str, tables) -> dict:
    r = normalize_for_cer(reference, tables)
    h = normalize_for_cer(hypothesis, tables)
    if not r:
        raise ValueError("empty reference after normalization")
    d = edit_distance(r, h)
    value = d / len(r)
    return {"cer": round(value, 4), "edits": d, "reference_chars": len(r), "hypothesis_chars": len(h),
            "max": CER_MAX, "passed": value <= CER_MAX}


def reference_stats(reference: str, tables) -> dict:
    return zh_script.reference_stats(tables, unicodedata.normalize("NFKC", reference), MIN_DIFFERING_REFERENCE)


def _read(path: str) -> str:
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _hyp_text(args) -> str:
    if args.text:
        return _read(args.text)
    import srt_check

    return srt_check.cue_text(srt_check.parse_file(args.srt, args.parser))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dict-dir", required=True, help="the pinned OpenCC dictionary files (_shared/needs.json)")
    sub = p.add_subparsers(dest="action", required=True)
    for name in ("cer", "script", "all", "ref-stats"):
        sp = sub.add_parser(name)
        if name in ("cer", "all", "ref-stats"):
            sp.add_argument("--ref", required=True, help="reference.txt")
        if name != "ref-stats":
            g = sp.add_mutually_exclusive_group(required=True)
            g.add_argument("--srt", help="the answer's final SRT file")
            g.add_argument("--text", help="plain text instead of an SRT (tests only)")
            sp.add_argument("--parser", choices=["pinned", "builtin"], default="pinned")
        sp.add_argument("--out")
    args = p.parse_args(argv)
    tables = zh_script.OpenCCTables(args.dict_dir)
    out = {"tool": "zh_score.py", "opencc_dict_sha256": tables.hashes}
    if args.action == "ref-stats":
        out["reference"] = reference_stats(_read(args.ref), tables)
        ok = out["reference"]["pass"]
    else:
        hyp = _hyp_text(args)
        ok = True
        if args.action in ("cer", "all"):
            out["cer"] = cer(_read(args.ref), hyp, tables)
            ok = ok and out["cer"]["passed"]
        if args.action in ("script", "all"):
            out["script"] = tables.ratio(hyp)
            ok = ok and out["script"]["pass"]
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    sys.stdout.write(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
