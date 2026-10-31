#!/usr/bin/env python3
"""Check the frozen q17 corpus before use (Python stdlib only).

  python3 verify_corpus.py                 # hashes in SHA256SUMS + token placement
  python3 verify_corpus.py --regenerate    # also re-run make_corpus.py in a temp dir and compare bytes
  python3 verify_corpus.py --corpus DIR    # check a copy (e.g. the copy placed in the sandbox)
  python3 verify_corpus.py --write-sums    # (fixture author only) rewrite SHA256SUMS

Exit 0 when everything matches.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def listing(corpus, questions):
    rows = []
    for n in sorted(os.listdir(corpus)):
        rows.append(("corpus/" + n, sha256(os.path.join(corpus, n))))
    rows.append(("questions.json", sha256(questions)))
    return rows


def pdf_text(data):
    out = []
    for m in re.finditer(rb"stream\n(.*?)\nendstream", data, re.S):
        try:
            out.append(zlib.decompress(m.group(1)).decode("latin-1"))
        except zlib.error:
            pass
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(HERE, "corpus"))
    ap.add_argument("--questions", default=os.path.join(HERE, "questions.json"))
    ap.add_argument("--sums", default=os.path.join(HERE, "SHA256SUMS"))
    ap.add_argument("--regenerate", action="store_true")
    ap.add_argument("--write-sums", action="store_true")
    a = ap.parse_args()
    rows = listing(a.corpus, a.questions)
    if a.write_sums:
        with open(a.sums, "w") as f:
            for name, h in rows:
                f.write("%s  %s\n" % (h, name))
        print("wrote %s (%d entries)" % (a.sums, len(rows)))
        return 0
    problems = []
    want = {}
    with open(a.sums) as f:
        for line in f:
            h, name = line.split(None, 1)
            want[name.strip()] = h
    got = dict(rows)
    for name in sorted(set(want) | set(got)):
        if want.get(name) != got.get(name):
            problems.append("hash mismatch or missing file: %s" % name)
    with open(a.questions, encoding="utf-8") as f:
        q = json.load(f)
    names = sorted(os.listdir(a.corpus))
    md = [n for n in names if n.endswith(".md")]
    pdf = [n for n in names if n.endswith(".pdf")]
    if len(md) != 50 or len(pdf) != 5 or len(names) != 55:
        problems.append("expected 50 .md + 5 .pdf, found %d + %d (%d files)" % (len(md), len(pdf), len(names)))
    texts = {}
    for n in names:
        with open(os.path.join(a.corpus, n), "rb") as f:
            data = f.read()
        texts[n] = pdf_text(data) if n.endswith(".pdf") else data.decode("utf-8")
    pdf_only = 0
    for item in q["questions"]:
        hits = [n for n, t in texts.items() if item["token"] in t]
        if hits != [item["source_file"]]:
            problems.append("%s: token found in %s, expected only %s" % (item["id"], hits, item["source_file"]))
        if item["pdf_only"]:
            pdf_only += 1
            if not item["source_file"].endswith(".pdf"):
                problems.append("%s marked pdf_only but source is not a PDF" % item["id"])
    if pdf_only != 2 or len(q["questions"]) != 5:
        problems.append("expected 5 questions with 2 PDF-only, got %d / %d" % (len(q["questions"]), pdf_only))
    if a.regenerate:
        tmp = tempfile.mkdtemp(prefix="q17-regen-")
        subprocess.check_call([sys.executable, os.path.join(HERE, "make_corpus.py"), "--out", tmp],
                              stdout=subprocess.DEVNULL)
        regen = dict(listing(os.path.join(tmp, "corpus"), os.path.join(tmp, "questions.json")))
        if regen != got:
            diff = sorted(k for k in set(regen) | set(got) if regen.get(k) != got.get(k))
            problems.append("regenerated corpus differs: %s" % diff[:10])
    for p in problems:
        print("FAIL " + p)
    print("ok: %d files, %d questions, hashes match" % (len(names), len(q["questions"])) if not problems
          else "%d problem(s)" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
