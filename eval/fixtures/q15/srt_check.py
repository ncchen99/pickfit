#!/usr/bin/env python3
"""q15 L2: is the answer's output valid SRT, and do its cues cover the clip?

Valid means all of:
  1. the file is UTF-8 (a BOM is allowed) and parses with the pinned SRT
     parser (the `srt` package, needs.json) without errors;
  2. at least one cue;
  3. indices are sequential: each cue's index is the previous index + 1;
  4. start < end in every cue;
  5. start times never decrease.
Coverage: the union of all cue intervals, clipped to [0, --duration], is at
least --min-coverage seconds (60-second clip, 50 seconds).

--parser builtin is a strict stand-in used by this folder's tests and for a
quick look when the pinned package is missing; it does not count for the
item.

Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import namedtuple

Cue = namedtuple("Cue", "index start end content")
_TIME = re.compile(r"^(\d{1,3}):([0-5]\d):([0-5]\d)[,.](\d{1,3})$")
_ARROW = re.compile(r"^\s*(\S+)\s+-->\s+(\S+)(?:\s+.*)?$")
_TAGS = re.compile(r"<[^>]*>|\{\\[^}]*\}")


class SrtError(ValueError):
    pass


def _seconds(text: str) -> float:
    m = _TIME.match(text)
    if not m:
        raise SrtError("bad timestamp %r" % text)
    h, mi, s, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def parse_builtin(text: str) -> list:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    body = text.strip("\n")
    if not body.strip():
        return []
    cues = []
    for n, block in enumerate(re.split(r"\n[ \t]*\n+", body), 1):
        lines = block.split("\n")
        if len(lines) < 2:
            raise SrtError("block %d: needs an index line and a timing line" % n)
        if not lines[0].strip().isdigit():
            raise SrtError("block %d: index line %r is not a number" % (n, lines[0]))
        m = _ARROW.match(lines[1])
        if not m:
            raise SrtError("block %d: timing line %r" % (n, lines[1]))
        cues.append(Cue(int(lines[0].strip()), _seconds(m.group(1)), _seconds(m.group(2)), "\n".join(lines[2:])))
    return cues


def parse_pinned(text: str) -> list:
    try:
        import srt
    except ImportError:
        raise SystemExit("srt_check: the pinned `srt` package is not installed (needs.json)")
    return [Cue(s.index, s.start.total_seconds(), s.end.total_seconds(), s.content) for s in srt.parse(text)]


def read_text(path: str) -> str:
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SrtError("not UTF-8: %s" % exc)


def parse_file(path: str, parser: str = "pinned") -> list:
    text = read_text(path)
    return parse_pinned(text) if parser == "pinned" else parse_builtin(text)


def cue_text(cues: list) -> str:
    return "\n".join(_TAGS.sub("", c.content) for c in cues)


def coverage(cues: list, duration: float) -> float:
    ivs = sorted((max(0.0, c.start), min(duration, c.end)) for c in cues)
    total, cur_s, cur_e = 0.0, None, None
    for s, e in ivs:
        if e <= s:
            continue
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def check(path: str, duration: float, min_coverage: float, parser: str = "pinned") -> dict:
    out = {"tool": "srt_check.py", "file": path, "parser": parser, "problems": []}
    try:
        cues = parse_file(path, parser)
    except Exception as exc:  # the pinned parser raises its own exception types
        out.update(valid=False, cues=0, coverage_seconds=0.0, passed=False)
        out["problems"].append("does not parse: %s: %s" % (type(exc).__name__, exc))
        return out
    probs = out["problems"]
    if not cues:
        probs.append("no cues")
    for prev, cur in zip(cues, cues[1:]):
        if cur.index != prev.index + 1:
            probs.append("index %d follows %d" % (cur.index, prev.index))
        if cur.start < prev.start:
            probs.append("cue %d starts before cue %d" % (cur.index, prev.index))
    for c in cues:
        if not c.start < c.end:
            probs.append("cue %d: start %.3f is not before end %.3f" % (c.index, c.start, c.end))
    cov = coverage(cues, duration)
    out.update(valid=not probs, cues=len(cues), first_index=cues[0].index if cues else None,
               coverage_seconds=round(cov, 3), min_coverage=min_coverage)
    out["passed"] = out["valid"] and cov >= min_coverage
    out["text"] = cue_text(cues)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("srt_file")
    p.add_argument("--duration", type=float, default=60.0)
    p.add_argument("--min-coverage", type=float, default=50.0)
    p.add_argument("--parser", choices=["pinned", "builtin"], default="pinned")
    p.add_argument("--out")
    args = p.parse_args(argv)
    out = check(args.srt_file, args.duration, args.min_coverage, args.parser)
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    sys.stdout.write(text)
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
