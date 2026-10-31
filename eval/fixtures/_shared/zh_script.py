#!/usr/bin/env python3
"""The shared OpenCC scorer (eval/README.md section 5), used by q11 and q15.

Python 3.8+ standard library only; runs on the grader's Mac or in the box.
Everything comes from ONE pinned OpenCC release: its text dictionaries
STCharacters.txt, STPhrases.txt, TSCharacters.txt and TWVariants.txt
(data/dictionary/ of the source tree at that tag; see _shared/needs.json).
They are not committed; --dict-dir points at the folder that holds them, and
every report records their SHA-256. No OpenCC binary or Python package is used.

  zh_script.py --dict-dir DIR ratio FILE [FILE ...]   Traditional ratio of the files' text (concatenated)
  zh_script.py --dict-dir DIR convert --to t|tw FILE  print the text converted to Traditional
  zh_script.py --dict-dir DIR probe 台后里為为         class of each character
  zh_script.py --dict-dir DIR ref-stats FILE          script-differing characters after s2tw (q15)

ratio (section 5: per character; pass = ratio >= 0.95 and >= 30 differing):
  For each character c of the text, as written (nothing is converted first):
    Simplified   c is a key of STCharacters and is not one of its own
                 Traditional candidates (it exists only as the Simplified form);
    Traditional  c is a key of TSCharacters and is not one of its own
                 Simplified candidates;
    neutral      neither, or both (a character valid in both scripts, such as
                 one listed as its own candidate: 后, 里, 台, 着 ...).
  ratio = Traditional / (Traditional + Simplified); "script-differing
  characters" = Traditional + Simplified. No context and no allow-list: a
  character that can be correct in Traditional text is never counted against it.

convert (q15's CER normalisation, "converting both to Traditional with the
pinned OpenCC"): OpenCC's s2t from the same files: greedy longest match over
STPhrases + STCharacters (first candidate), then for --to tw the TWVariants
table on the result (OpenCC's s2tw chain). Both sides of the CER go through the
same function, so a rare segmentation difference from the OpenCC binary cannot
favour either side.

Exit status: ratio 0 = pass, 1 = fail; ref-stats 0 when >= --min-differing.
"""

import argparse
import collections
import hashlib
import json
import os
import sys

MIN_RATIO = 0.95
MIN_DIFFERING = 30
DICT_FILES = ("STCharacters.txt", "STPhrases.txt", "TSCharacters.txt", "TWVariants.txt")


def is_han(ch):
    c = ord(ch)
    return (0x3400 <= c <= 0x4DBF or 0x4E00 <= c <= 0x9FFF or 0xF900 <= c <= 0xFAFF
            or 0x20000 <= c <= 0x2FA1F or 0x30000 <= c <= 0x323AF)


def load_table(path):
    """{key: [candidates in file order]}; a missing file is an empty table (STPhrases, TWVariants are optional for ratio)."""
    table = {}
    if not os.path.exists(path):
        return table
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or "\t" not in line:
                continue
            key, values = line.split("\t", 1)
            table[key] = values.split()
    return table


def sha256(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class OpenCCTables(object):
    def __init__(self, dict_dir):
        self.dict_dir = dict_dir
        for name in ("STCharacters.txt", "TSCharacters.txt"):
            if not os.path.exists(os.path.join(dict_dir, name)):
                raise SystemExit("zh_script: %s missing in %s (pinned OpenCC dictionaries, _shared/needs.json)" % (name, dict_dir))
        self.st = load_table(os.path.join(dict_dir, "STCharacters.txt"))
        self.st_phrases = load_table(os.path.join(dict_dir, "STPhrases.txt"))
        self.ts = load_table(os.path.join(dict_dir, "TSCharacters.txt"))
        self.tw = load_table(os.path.join(dict_dir, "TWVariants.txt"))
        self.hashes = {n: sha256(os.path.join(dict_dir, n)) for n in DICT_FILES}
        self.longest_phrase = max([len(k) for k in self.st_phrases] + [1])

    # ---- per-character script judgement

    def classify(self, c):
        simp = c in self.st and c not in self.st[c]
        trad = c in self.ts and c not in self.ts[c]
        if simp and not trad:
            return "simplified"
        if trad and not simp:
            return "traditional"
        return None

    def ratio(self, text, min_differing=MIN_DIFFERING, min_ratio=MIN_RATIO):
        counts = collections.Counter()
        simplified = collections.Counter()
        traditional = collections.Counter()
        for c in text:
            kind = self.classify(c)
            if kind:
                counts[kind] += 1
                (simplified if kind == "simplified" else traditional)[c] += 1
        t, s = counts["traditional"], counts["simplified"]
        differing = t + s
        value = float(t) / differing if differing else None
        return {
            "traditional": t,
            "simplified": s,
            "differing": differing,
            "ratio": round(value, 4) if value is not None else None,
            "min_ratio": min_ratio,
            "min_differing": min_differing,
            "pass": differing >= min_differing and value is not None and value >= min_ratio,
            "simplified_chars": "".join(c for c, _ in simplified.most_common()),
            "distinct_traditional_chars": len(traditional),
            "dict_dir": self.dict_dir,
            "dict_sha256": self.hashes,
        }

    # ---- conversion (s2t, s2tw)

    def s2t(self, text):
        out, i = [], 0
        while i < len(text):
            for size in range(min(self.longest_phrase, len(text) - i), 0, -1):
                piece = text[i:i + size]
                hit = self.st_phrases.get(piece) if size > 1 else (self.st_phrases.get(piece) or self.st.get(piece))
                if hit:
                    out.append(hit[0])
                    i += size
                    break
            else:
                out.append(text[i])
                i += 1
        return "".join(out)

    def s2tw(self, text):
        t = self.s2t(text)
        return "".join(self.tw[c][0] if c in self.tw else c for c in t)

    def convert(self, text, to="tw"):
        return self.s2tw(text) if to == "tw" else self.s2t(text)


def read_files(paths):
    text = ""
    for path in paths:
        with open(path, encoding="utf-8-sig") as fh:
            text += fh.read() + "\n"
    return text


def reference_stats(tables, text, min_differing=60):
    """q15: the reference after s2tw must hold at least `min_differing` script-differing characters."""
    trad = tables.s2tw(text)
    r = tables.ratio(trad, min_differing=min_differing)
    return {"han_chars": sum(1 for ch in trad if is_han(ch)), "script_differing": r["differing"],
            "traditional": r["traditional"], "simplified_left_after_s2tw": r["simplified_chars"],
            "min_required": min_differing, "pass": r["differing"] >= min_differing}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dict-dir", required=True, help="folder with the pinned OpenCC dictionary files")
    sub = ap.add_subparsers(dest="action", required=True)
    sp = sub.add_parser("ratio")
    sp.add_argument("files", nargs="+")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("convert")
    sp.add_argument("--to", choices=["t", "tw"], default="tw")
    sp.add_argument("file")
    sp = sub.add_parser("probe")
    sp.add_argument("chars")
    sp = sub.add_parser("ref-stats")
    sp.add_argument("file")
    sp.add_argument("--min-differing", type=int, default=60)
    a = ap.parse_args(argv)
    tables = OpenCCTables(a.dict_dir)
    if a.action == "probe":
        for c in a.chars:
            print("%s U+%04X %s" % (c, ord(c), tables.classify(c) or "neutral"))
        return 0
    if a.action == "convert":
        sys.stdout.write(tables.convert(read_files([a.file]), a.to))
        return 0
    if a.action == "ref-stats":
        rep = reference_stats(tables, read_files([a.file]), a.min_differing)
        rep["dict_sha256"] = tables.hashes
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0 if rep["pass"] else 1
    rep = tables.ratio(read_files(a.files))
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("traditional-only %d, simplified-only %d, differing %d, ratio %s"
              % (rep["traditional"], rep["simplified"], rep["differing"], rep["ratio"]))
        if rep["simplified_chars"]:
            print("simplified-only characters: %s" % rep["simplified_chars"])
        print("script check: %s (needs ratio >= %.2f and >= %d differing)"
              % ("PASS" if rep["pass"] else "FAIL", MIN_RATIO, MIN_DIFFERING))
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
