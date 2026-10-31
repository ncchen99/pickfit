#!/usr/bin/env python3
"""q15 L2: character error rate and the Traditional-script ratio, with the
pinned OpenCC (eval/README.md section 5: per-character judgement, Traditional
ratio >= 0.95 and at least 30 script-differing characters).

  cer        CER of the answer's SRT text against reference.txt. Both sides:
             Unicode NFKC, then OpenCC "s2tw" (to Traditional, Taiwan
             variants), then every character that is not a letter or a digit
             is removed (punctuation, symbols, spaces, line breaks), Latin
             letters lower-cased. CER = Levenshtein distance / reference
             length. Pass: CER <= 0.25.
  script     Traditional ratio of the answer's SRT text, characters as written
             (no conversion of the answer). For each Han character, judged in
             context:
               Simplified  OpenCC "s2t" changes it AND "s2tw" changes it
                           (a form that both standard and Taiwan Traditional
                           replace), unless it is listed in --allow;
               Traditional otherwise, when OpenCC "t2s" changes it;
               neutral     everything else (same in both scripts).
             The three conversions run on the whole text so phrase rules see
             the context; when a conversion changes the text length the
             judgement falls back to one character at a time.
             ratio = Traditional / (Traditional + Simplified).
             Pass: Traditional + Simplified >= 30 and ratio >= 0.95.
  ref-stats  script-differing characters of the reference (after s2tw);
             the item requires at least 60.
  all        cer + script in one JSON.

The answer's text is the concatenation of its SRT cue texts (srt_check.py
reads the file; formatting tags are removed there).

Needs the pinned OpenCC Python package (needs.json). Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CER_MAX = 0.25
RATIO_MIN = 0.95
MIN_DIFFERING_OUTPUT = 30
MIN_DIFFERING_REFERENCE = 60


def is_han(ch: str) -> bool:
    c = ord(ch)
    return (0x3400 <= c <= 0x4DBF or 0x4E00 <= c <= 0x9FFF or 0xF900 <= c <= 0xFAFF
            or 0x20000 <= c <= 0x2FA1F or 0x30000 <= c <= 0x323AF)


class Converters:
    def __init__(self, s2t, s2tw, t2s, version=None):
        self.s2t, self.s2tw, self.t2s, self.version = s2t, s2tw, t2s, version


def load_opencc() -> Converters:
    try:
        import opencc
    except ImportError:
        raise SystemExit("zh_score: the pinned OpenCC package is not installed (needs.json)")

    def make(cfg):
        last = None
        for name in (cfg, cfg + ".json"):
            try:
                return opencc.OpenCC(name).convert
            except Exception as exc:  # the two packages name configs differently
                last = exc
        raise SystemExit("zh_score: OpenCC config %s failed: %s" % (cfg, last))

    version = getattr(opencc, "__version__", None)
    return Converters(make("s2t"), make("s2tw"), make("t2s"), version)


def normalize_for_cer(text: str, conv: Converters) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = conv.s2tw(text)
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


def cer(reference: str, hypothesis: str, conv: Converters) -> dict:
    r = normalize_for_cer(reference, conv)
    h = normalize_for_cer(hypothesis, conv)
    if not r:
        raise ValueError("empty reference after normalization")
    d = edit_distance(r, h)
    value = d / len(r)
    return {"cer": round(value, 4), "edits": d, "reference_chars": len(r), "hypothesis_chars": len(h),
            "max": CER_MAX, "passed": value <= CER_MAX}


def _aligned(text: str, conv: Converters):
    a, b, c = conv.s2t(text), conv.s2tw(text), conv.t2s(text)
    if len(a) == len(b) == len(c) == len(text):
        return "context", zip(text, a, b, c)
    return "per-character", ((ch, conv.s2t(ch), conv.s2tw(ch), conv.t2s(ch)) for ch in text)


def script_counts(text: str, conv: Converters, allow: str = "") -> dict:
    mode, rows = _aligned(text, conv)
    trad = simp = neutral = 0
    simplified_chars: dict = {}
    for ch, to_t, to_tw, to_s in rows:
        if not is_han(ch):
            continue
        if to_t != ch and to_tw != ch and ch not in allow:
            simp += 1
            simplified_chars[ch] = simplified_chars.get(ch, 0) + 1
        elif to_s != ch:
            trad += 1
        else:
            neutral += 1
    diff = trad + simp
    return {"mode": mode, "traditional": trad, "simplified": simp, "neutral": neutral, "differing": diff,
            "ratio": round(trad / diff, 4) if diff else None,
            "simplified_chars": dict(sorted(simplified_chars.items(), key=lambda kv: -kv[1]))}


def script_item(text: str, conv: Converters, allow: str = "") -> dict:
    s = script_counts(text, conv, allow)
    s["min_differing"] = MIN_DIFFERING_OUTPUT
    s["min_ratio"] = RATIO_MIN
    s["passed"] = s["differing"] >= MIN_DIFFERING_OUTPUT and s["ratio"] is not None and s["ratio"] >= RATIO_MIN
    return s


def reference_stats(reference: str, conv: Converters) -> dict:
    trad_ref = conv.s2tw(unicodedata.normalize("NFKC", reference))
    s = script_counts(trad_ref, conv)
    return {"han_chars": sum(1 for ch in trad_ref if is_han(ch)), "script_differing": s["traditional"],
            "min_required": MIN_DIFFERING_REFERENCE, "passed": s["traditional"] >= MIN_DIFFERING_REFERENCE,
            "simplified_left_after_s2tw": s["simplified_chars"]}


def _read(path: str) -> str:
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _hyp_text(args) -> str:
    if args.text:
        return _read(args.text)
    import srt_check

    return srt_check.cue_text(srt_check.parse_file(args.srt, args.parser))


def _allow(args) -> str:
    if not args.allow:
        return ""
    return "".join(ch for ch in _read(args.allow) if is_han(ch))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
            sp.add_argument("--allow", help="file of characters never counted as Simplified (calibration.md)")
        sp.add_argument("--out")
    args = p.parse_args(argv)
    conv = load_opencc()
    out = {"tool": "zh_score.py", "opencc_version": conv.version}
    if args.action == "ref-stats":
        out["reference"] = reference_stats(_read(args.ref), conv)
        ok = out["reference"]["passed"]
    else:
        hyp = _hyp_text(args)
        ok = True
        if args.action in ("cer", "all"):
            out["cer"] = cer(_read(args.ref), hyp, conv)
            ok = ok and out["cer"]["passed"]
        if args.action in ("script", "all"):
            out["script"] = script_item(hyp, conv, _allow(args))
            ok = ok and out["script"]["passed"]
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    sys.stdout.write(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
