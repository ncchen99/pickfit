#!/usr/bin/env python3
"""q15 calibration: choose speech-corpus clips by a fixed rule, before anyone
listens to them or tries a tool on them.

For a corpus that ships a TSV of validated clips (Common Voice style: columns
client_id, path, sentence, up_votes, down_votes; other columns ignored):

  1. keep rows with up_votes >= 2, down_votes == 0 and at least 12 Han
     characters in the sentence;
  2. keep the first row per speaker (client_id), in file order;
  3. sort by SHA-256(seed + newline + path) and keep the first --count rows.

Writes a manifest for `build_clip.py concat`: each clip's id, its decoded
WAV name (same stem, .wav), the original file name and SHA-256 (when
--clips-dir holds the originals) and the sentence. build_clip.py then takes
clips in this order and skips any that do not fit in 60 s.

Python 3.9+ standard library only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys

SEED = "q15-clip-v1"
MIN_HAN = 12


def han_count(text: str) -> int:
    return sum(1 for ch in text if 0x3400 <= ord(ch) <= 0x9FFF or 0xF900 <= ord(ch) <= 0xFAFF)


def select(rows, count: int, seed: str = SEED) -> list:
    seen, kept = set(), []
    for r in rows:
        try:
            up, down = int(r.get("up_votes") or 0), int(r.get("down_votes") or 0)
        except ValueError:
            continue
        if up < 2 or down != 0 or han_count(r.get("sentence", "")) < MIN_HAN:
            continue
        who = r.get("client_id", "")
        if who in seen:
            continue
        seen.add(who)
        kept.append(r)
    kept.sort(key=lambda r: hashlib.sha256((seed + "\n" + r["path"]).encode("utf-8")).hexdigest())
    return kept[:count]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tsv", required=True, help="validated.tsv (or the corpus' equivalent)")
    p.add_argument("--clips-dir", help="folder with the original clip files (for SHA-256)")
    p.add_argument("--count", type=int, default=25)
    p.add_argument("--dataset", required=True, help="e.g. 'Common Voice Corpus NN.0, zh-TW'")
    p.add_argument("--url", required=True, help="where the corpus was downloaded")
    p.add_argument("--license", default="CC0-1.0")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    with open(args.tsv, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))
    chosen = select(rows, args.count)
    clips = []
    for r in chosen:
        stem = os.path.splitext(os.path.basename(r["path"]))[0]
        entry = {"id": stem, "wav": stem + ".wav", "original_file": r["path"], "text": r["sentence"]}
        if args.clips_dir:
            entry["original_sha256"] = sha256_file(os.path.join(args.clips_dir, r["path"]))
        clips.append(entry)
    manifest = {"source": {"dataset": args.dataset, "url": args.url, "license": args.license,
                           "selection_rule": "up_votes>=2, down_votes==0, >=%d Han chars, one per speaker, "
                                             "sorted by sha256(%r + newline + path)" % (MIN_HAN, SEED),
                           "rows_in_tsv": len(rows)},
                "clips": clips}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    sys.stderr.write("select_clips: %d of %d rows chosen\n" % (len(clips), len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
