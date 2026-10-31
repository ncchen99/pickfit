#!/usr/bin/env python3
"""Shared OpenCC scorer (eval/README.md section 5): character-by-character
Traditional vs Simplified judgement, Traditional ratio >= 0.95 with at least
30 script-differing characters. Python 3.8+ stdlib only.

It reads OpenCC's own character tables from a pinned OpenCC release (the text
dictionaries STCharacters.txt and TSCharacters.txt from the source tree's
data/dictionary/ folder, pinned by version and SHA-256 in calibration.md);
the OpenCC library itself is not needed. Each line of those files is
"<char>\t<candidate> <candidate> ...".

For each character c of the text:
  simplified-only  : c is a key of STCharacters and is not among its own
                     Traditional candidates (e.g. a character that only
                     exists as the Simplified form);
  traditional-only : c is a key of TSCharacters and is not among its own
                     Simplified candidates;
  neutral          : neither, or both (characters valid in both scripts,
                     such as one that is its own Traditional candidate).
ratio = traditional-only / (traditional-only + simplified-only).
"script-differing characters" = traditional-only + simplified-only.

Usage:
  python3 opencc_scorer.py --dict-dir DIR FILE [FILE ...]   # files are concatenated
  python3 opencc_scorer.py --dict-dir DIR --json FILE ...
  python3 opencc_scorer.py --dict-dir DIR --probe 台后里為为   # classify single characters
Exit 0 when the text passes (ratio >= 0.95 and >= 30 differing), 1 otherwise.
"""
import argparse
import collections
import hashlib
import json
import os
import sys

MIN_RATIO = 0.95
MIN_DIFFERING = 30
DICT_FILES = ("STCharacters.txt", "TSCharacters.txt")


def load_table(path):
    table = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or "\t" not in line:
                continue
            key, vals = line.split("\t", 1)
            table[key] = set(vals.split())
    return table


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


class Scorer(object):
    def __init__(self, dict_dir):
        self.dict_dir = dict_dir
        self.st = load_table(os.path.join(dict_dir, "STCharacters.txt"))
        self.ts = load_table(os.path.join(dict_dir, "TSCharacters.txt"))
        self.hashes = {n: sha256(os.path.join(dict_dir, n)) for n in DICT_FILES}

    def classify(self, c):
        simp = c in self.st and c not in self.st[c]
        trad = c in self.ts and c not in self.ts[c]
        if simp and not trad:
            return "simplified"
        if trad and not simp:
            return "traditional"
        return None

    def score(self, text):
        counts = collections.Counter()
        simp_chars = collections.Counter()
        trad_chars = collections.Counter()
        for c in text:
            k = self.classify(c)
            if k == "simplified":
                counts["simplified"] += 1
                simp_chars[c] += 1
            elif k == "traditional":
                counts["traditional"] += 1
                trad_chars[c] += 1
        t, s = counts["traditional"], counts["simplified"]
        differing = t + s
        ratio = (float(t) / differing) if differing else 0.0
        return {
            "traditional": t,
            "simplified": s,
            "differing": differing,
            "ratio": round(ratio, 4),
            "pass": differing >= MIN_DIFFERING and ratio >= MIN_RATIO,
            "simplified_chars": "".join(c for c, _ in simp_chars.most_common()),
            "distinct_traditional_chars": len(trad_chars),
            "dict_dir": self.dict_dir,
            "dict_sha256": self.hashes,
        }


def main(argv=None):
    ap = argparse.ArgumentParser(description="OpenCC character-level Traditional ratio")
    ap.add_argument("--dict-dir", required=True, help="folder with STCharacters.txt and TSCharacters.txt")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--probe", help="print the class of each character of this string and exit")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args(argv)
    if a.probe:
        sc = Scorer(a.dict_dir)
        for c in a.probe:
            print("%s U+%04X %s" % (c, ord(c), sc.classify(c) or "neutral"))
        return 0
    if not a.files:
        ap.error("no input files")
    text = ""
    for p in a.files:
        with open(p, encoding="utf-8") as f:
            text += f.read() + "\n"
    rep = Scorer(a.dict_dir).score(text)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("traditional-only %d, simplified-only %d, differing %d, ratio %.4f"
              % (rep["traditional"], rep["simplified"], rep["differing"], rep["ratio"]))
        if rep["simplified_chars"]:
            print("simplified-only characters: %s" % rep["simplified_chars"])
        print("script check: %s (needs ratio >= %.2f and >= %d differing)"
              % ("PASS" if rep["pass"] else "FAIL", MIN_RATIO, MIN_DIFFERING))
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
