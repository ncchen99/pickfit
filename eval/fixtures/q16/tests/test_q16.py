"""Self-tests for eval/fixtures/q16 (stdlib unittest; also runs under pytest).

    python3 -m unittest discover -s eval/fixtures/q16/tests -v

Positive control: calibration/control-pt-PT (a hand translation of the
variant file). Negative controls: the pt-BR version and tampered copies.
Files 01 and 03 get a mechanical stand-in "translation" that keeps code,
URLs, numbers and product names and replaces every other English word.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "meaning"))

import build_manifest  # noqa: E402
import lang_check  # noqa: E402
import make_judge_input  # noqa: E402
import md_check  # noqa: E402
import mdtools  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
PT = os.path.join(ROOT, "calibration", "control-pt-PT", "02-team-handbook.md")
BR = os.path.join(ROOT, "calibration", "control-pt-BR", "02-team-handbook.md")
URLISH = re.compile(r"\]\([^)]*\)|<https?://[^>]+>|https?://\S+|^\[[^\]]+\]:.*$|`[^`]*`", re.M)


def stand_in(text):
    """Replace English words outside code, URLs and link targets."""
    out = []
    for b in re.split(r"(?ms)(^(?:```|~~~).*?^(?:```|~~~)[ \t]*$)", text):
        if b.startswith(("```", "~~~")):
            out.append(b)
            continue
        keep = {}

        def hold(m):
            keep["\0%d\0" % len(keep)] = m.group(0)
            return "\0%d\0" % (len(keep) - 1)

        b = URLISH.sub(hold, b)
        b = re.sub(r"[A-Za-z]+", lambda m: m.group(0) if m.group(0) in mdtools.PRODUCT_NAMES else "palavra", b)
        for k, v in keep.items():
            b = b.replace(k, v)
        out.append(b)
    return "".join(out)


def make_output(d, second=PT, extra=None):
    os.makedirs(d, exist_ok=True)
    for name in ("01-getting-started.md", "03-api-gateway.md"):
        with open(os.path.join(d, name[:-3] + ".pt.md"), "w", encoding="utf-8") as fh:
            fh.write(stand_in(mdtools.read(os.path.join(DOCS, name))))
    shutil.copy(second, os.path.join(d, "02-team-handbook.pt.md"))
    if extra:
        extra(d)
    return d


def check(out_dir, run_log=None):
    with tempfile.TemporaryDirectory() as t:
        res = os.path.join(t, "r.json")
        args = ["--output", out_dir, "--out", res]
        if run_log:
            lp = os.path.join(t, "log.json")
            with open(lp, "w") as fh:
                json.dump(run_log, fh)
            args += ["--run-log", lp]
        rc = md_check.main(args)
        with open(res, encoding="utf-8") as fh:
            return rc, json.load(fh)


class FixtureTest(unittest.TestCase):
    def test_manifest_up_to_date(self):
        self.assertEqual(build_manifest.main(["--check"]), 0)

    def test_fixture_shape(self):
        with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        self.assertTrue(900 <= m["total_words"] <= 1100)
        self.assertEqual(len(m["files"]), 3)
        self.assertEqual(len(m["variant"]["items"]), 5)
        self.assertEqual(len(m["meaning_sample"]["sentences"]), 5)
        for f in m["files"].values():
            self.assertGreaterEqual(len(f["code_blocks"]), 1)
            self.assertGreaterEqual(len(f["urls"]), 2)
            self.assertGreaterEqual(f["headings"], 4)

    def test_no_source_block_is_skipped_by_lang_check(self):
        for name in os.listdir(DOCS):
            for b in mdtools.analyze(mdtools.read(os.path.join(DOCS, name)))["prose"]:
                self.assertGreaterEqual(mdtools.word_count(mdtools.lang_text(b)), lang_check.MIN_WORDS, b["text"])

    def test_parser(self):
        a = mdtools.analyze(mdtools.read(os.path.join(DOCS, "01-getting-started.md")))
        self.assertEqual(a["headings"], 5)  # the '# ...' comments inside code are not headings
        self.assertEqual(len(a["code_blocks"]), 4)
        self.assertTrue(a["code_blocks"][0].startswith("```bash\n") and a["code_blocks"][0].endswith("```\n"))
        t = "~~~~text\n```\nnot closed by backticks\n~~~~\n\n# H\n\n````\nopen to the end\n"
        b = mdtools.analyze(t)
        self.assertEqual(len(b["code_blocks"]), 2)
        self.assertEqual(b["headings"], 1)
        self.assertEqual(mdtools.urls_in("see [a](https://x.example/p?q=1#f \"t\") and <https://y.example/> or https://z.example/a."),
                         ["https://x.example/p?q=1#f", "https://y.example/", "https://z.example/a"])


class CheckTest(unittest.TestCase):
    def test_positive_control(self):
        with tempfile.TemporaryDirectory() as d:
            rc, r = check(make_output(d), {"duration_s": 600, "timed_out": False, "exit_code": 0})
        self.assertEqual(rc, 0, json.dumps(r["items"]))
        self.assertEqual(r["variant"]["pt_pt_count"], 5)
        self.assertTrue(r["files"]["passed"])

    def test_brazilian_control_fails_variant(self):
        with tempfile.TemporaryDirectory() as d:
            rc, r = check(make_output(d, second=BR))
        self.assertFalse(r["items"]["variant"])
        self.assertEqual(sorted(r["variant"]["pt_br_found"]), ["file", "mobile phone", "screen", "to download", "user"])
        self.assertTrue(r["items"]["structure"])

    def test_time_limit(self):
        with tempfile.TemporaryDirectory() as d:
            _, r = check(make_output(d), {"duration_s": 1801, "timed_out": False})
            self.assertFalse(r["items"]["files_within_30_min"])
            _, r = check(d, {"duration_s": 100, "timed_out": True})
            self.assertFalse(r["items"]["files_within_30_min"])

    def _tamper(self, fn):
        def extra(d):
            p = os.path.join(d, "03-api-gateway.pt.md")
            with open(p, encoding="utf-8") as fh:
                t = fh.read()
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(fn(t))
        with tempfile.TemporaryDirectory() as d:
            return check(make_output(d, extra=extra))[1]

    def test_code_block_changed(self):
        r = self._tamper(lambda t: t.replace("# Ask the gateway whether the new route answers", "# Pergunte ao gateway"))
        self.assertFalse(r["items"]["structure"])

    def test_code_fence_whitespace_changed(self):
        r = self._tamper(lambda t: t.replace("rate_limit_per_minute: 600\n", "rate_limit_per_minute: 600 \n"))
        self.assertFalse(r["items"]["structure"])

    def test_url_changed(self):
        r = self._tamper(lambda t: t.replace("retire?version=2#checklist", "retire?version=2#lista"))
        self.assertFalse(r["items"]["structure"])

    def test_number_spelled_out(self):
        r = self._tamper(lambda t: t.replace(" 7 ", " sete "))
        self.assertIn("number 7", " ".join(r["per_file"]["03-api-gateway.md"]["structure"]["problems"]))

    def test_heading_lost(self):
        r = self._tamper(lambda t: t.replace("## palavra\n", "palavra\n", 1))
        self.assertFalse(r["items"]["structure"])

    def test_english_left(self):
        src = "The name must be unique and may only contain lowercase letters, digits and hyphens."
        r = self._tamper(lambda t: t + "\n" + src + "\n")
        self.assertEqual(r["per_file"]["03-api-gateway.md"]["verbatim"]["english_left"], [src])

    def test_untranslated_copy_is_not_an_output(self):
        with tempfile.TemporaryDirectory() as d:
            for n in os.listdir(DOCS):
                shutil.copy(os.path.join(DOCS, n), os.path.join(d, n))
            rc, r = check(d)
        self.assertFalse(r["files"]["all_produced"])
        self.assertEqual({m["how"] for m in r["files"]["mapping"].values()}, {"missing"})

    def test_mapping_rules(self):
        with tempfile.TemporaryDirectory() as d:
            make_output(d)
            shutil.copy(PT, os.path.join(d, "02-team-handbook.draft.md"))
            m = mdtools.map_outputs(DOCS, d)
            self.assertEqual(m["02-team-handbook.md"]["path"], os.path.join(d, "02-team-handbook.pt.md"))
            os.rename(os.path.join(d, "02-team-handbook.pt.md"), os.path.join(d, "02-team-handbook.x.md"))
            self.assertEqual(mdtools.map_outputs(DOCS, d)["02-team-handbook.md"]["how"], "ambiguous")


class LangTest(unittest.TestCase):
    def test_judging_with_a_stand_in_identifier(self):
        def ident(text):
            pt = sum(w in ("de", "que", "para", "uma", "os", "da", "na", "não", "às") for w in text.lower().split())
            return ("pt", 0.95) if pt >= 1 else ("en", 0.99)

        prose = mdtools.analyze(mdtools.read(PT))["prose"]
        res = lang_check.judge_blocks(prose, ident)
        self.assertEqual(len(res["judged"]), len(prose))
        self.assertTrue(all(j["passed"] for j in res["judged"]))
        res = lang_check.judge_blocks(mdtools.analyze(mdtools.read(os.path.join(DOCS, "02-team-handbook.md")))["prose"], ident)
        self.assertFalse(any(j["passed"] for j in res["judged"]))


class JudgeTest(unittest.TestCase):
    def test_build_requests_score(self):
        with tempfile.TemporaryDirectory() as d:
            out = make_output(os.path.join(d, "out"))
            items = os.path.join(d, "items.json")
            make_judge_input.main(["build", "--output", out, "--out", items])
            with open(items, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(len(data["items"]), 5)
            for it in data["items"]:
                self.assertIn(it["source_sentence"], it["source_paragraph"])
                self.assertTrue(it["portuguese_text"])
            blob = json.dumps(data, ensure_ascii=False).lower()
            self.assertNotIn("pickfit", blob)
            req = os.path.join(d, "req.jsonl")
            make_judge_input.main(["requests", "--items", items, "--model", "judge-model-id", "--out", req])
            with open(req) as fh:
                lines = [json.loads(x) for x in fh]
            self.assertEqual(len(lines), 5)
            self.assertEqual(lines[0]["body"]["temperature"], 0)
            make_judge_input.main(["requests", "--items", items, "--model", "m", "--no-temperature", "--out", req])
            with open(req) as fh:
                self.assertEqual(len(fh.readlines()), 15)
            make_judge_input.main(["sheet", "--items", items, "--out", os.path.join(d, "sheet.md")])

    def test_score_rules(self):
        rows = [{"n": n, "verdict": "PASS"} for n in (1, 2, 3, 4)] + [{"n": 5, "verdict": "FAIL"}]
        self.assertTrue(make_judge_input.score(rows)["passed"])
        rows[0]["verdict"] = '{"verdict": "FAIL", "reason": "x"}'
        self.assertFalse(make_judge_input.score(rows)["passed"])
        three = [{"n": n, "run": r, "verdict": "PASS" if (n < 5 and r != 3) else "FAIL"} for n in range(1, 6) for r in (1, 2, 3)]
        res = make_judge_input.score(three)
        self.assertEqual(res["passed_sentences"], 4)
        self.assertTrue(res["passed"])

    def test_calibration_cases_cover_both_verdicts(self):
        with open(os.path.join(ROOT, "calibration", "judge_cases.json"), encoding="utf-8") as fh:
            cases = json.load(fh)["items"]
        self.assertEqual({c["expected"] for c in cases}, {"PASS", "FAIL"})


if __name__ == "__main__":
    unittest.main()
