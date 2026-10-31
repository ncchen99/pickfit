#!/usr/bin/env python3
"""q16 L2: every output prose paragraph is identified as Portuguese by the
pinned language identifier with confidence >= 0.9.

Paragraphs: the prose blocks of each mapped output file (paragraphs, and each
list as one block; headings, code, link definitions excluded). The text given
to the identifier has code spans, URLs, product names and numbers removed
(mdtools.lang_text). Blocks with fewer than 5 words after that are not
judged and are listed as skipped (none of the fixture's source blocks is that
short). Pass: at least one block judged, and every judged block is "pt" with
confidence >= 0.9.

Backends (pin one before freeze, calibration.md):
  fasttext  `fasttext` package + lid.176 model file (--model-path);
            confidence = probability of the top label
  lingua    `lingua-language-detector`; confidence = the top value of
            compute_language_confidence_values over all languages
  langid    `langid` with norm_probs=True; confidence = normalized probability

Python 3.9+; the backend package is the only non-stdlib dependency.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mdtools  # noqa: E402

MIN_CONFIDENCE = 0.9
MIN_WORDS = 5


def fasttext_backend(model_path):
    import fasttext

    model = fasttext.load_model(model_path)

    def identify(text):
        labels, probs = model.predict(text.replace("\n", " "), k=1)
        return labels[0].replace("__label__", ""), float(probs[0])

    return identify, "fasttext %s, model %s" % (getattr(fasttext, "__version__", "?"), os.path.basename(model_path))


def lingua_backend(_model_path):
    from lingua import LanguageDetectorBuilder

    detector = LanguageDetectorBuilder.from_all_languages().build()

    def identify(text):
        values = detector.compute_language_confidence_values(text)
        top = values[0]
        return top.language.iso_code_639_1.name.lower(), float(top.value)

    return identify, "lingua"


def langid_backend(_model_path):
    from langid.langid import LanguageIdentifier, model

    ident = LanguageIdentifier.from_modelstring(model, norm_probs=True)

    def identify(text):
        lang, prob = ident.classify(text)
        return lang, float(prob)

    return identify, "langid"


BACKENDS = {"fasttext": fasttext_backend, "lingua": lingua_backend, "langid": langid_backend}


def judge_blocks(prose: list, identify) -> dict:
    judged, skipped = [], []
    for i, block in enumerate(prose):
        text = mdtools.lang_text(block)
        if mdtools.word_count(text) < MIN_WORDS:
            skipped.append({"block": i, "text": text})
            continue
        lang, conf = identify(text)
        judged.append({"block": i, "lang": lang, "confidence": round(conf, 4),
                       "passed": lang == "pt" and conf >= MIN_CONFIDENCE, "text_head": text[:80]})
    return {"judged": judged, "skipped": skipped}


def run(args, identify, backend_name) -> dict:
    overrides = dict(m.split("=", 1) for m in (args.map or []))
    mapping = mdtools.map_outputs(args.input, args.output, overrides)
    if args.only:
        mapping = {k: v for k, v in mapping.items() if k in args.only}
    out = {"tool": "lang_check.py", "backend": backend_name, "min_confidence": MIN_CONFIDENCE, "files": {}}
    all_ok, n = True, 0
    for name, m in mapping.items():
        if not m["path"]:
            out["files"][name] = {"error": "no output file"}
            all_ok = False
            continue
        res = judge_blocks(mdtools.analyze(mdtools.read(m["path"]))["prose"], identify)
        out["files"][name] = res
        n += len(res["judged"])
        all_ok = all_ok and all(j["passed"] for j in res["judged"])
    out["judged_blocks"] = n
    out["passed"] = all_ok and n > 0
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default=os.path.join(HERE, "docs"))
    p.add_argument("--output", required=True)
    p.add_argument("--map", action="append")
    p.add_argument("--backend", required=True, choices=sorted(BACKENDS))
    p.add_argument("--model-path", help="fasttext model file (lid.176.ftz or .bin)")
    p.add_argument("--only", action="append", help="judge only this input file name (calibration)")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    identify, name = BACKENDS[args.backend](args.model_path)
    out = run(args, identify, name)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    sys.stderr.write("lang_check: passed=%s judged=%d\n" % (out["passed"], out["judged_blocks"]))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
