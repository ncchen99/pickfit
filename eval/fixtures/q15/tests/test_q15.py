"""Self-tests for eval/fixtures/q15 (stdlib unittest; also runs under pytest).

    python3 -m unittest discover -s eval/fixtures/q15/tests -v

The OpenCC conversions are replaced by tiny character tables here, so the
tests check the scoring rules, not OpenCC itself; calibration.md runs the
real, pinned OpenCC on the real reference.
"""
import array
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import build_clip  # noqa: E402
import srt_check  # noqa: E402
import zh_score  # noqa: E402

SHARED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "_shared")
DICT = os.path.join(SHARED, "selftest_dict")  # hand-written TEST-ONLY tables, not OpenCC data


def srt_text(cues):
    out = []
    for i, (a, b, t) in enumerate(cues, 1):
        def ts(x):
            ms = int(round(x * 1000))
            return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)
        out.append("%d\n%s --> %s\n%s\n" % (i, ts(a), ts(b), t))
    return "\n".join(out)


class SrtTest(unittest.TestCase):
    def check(self, text, **kw):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "o.srt")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
            return srt_check.check(p, 60.0, 50.0, "builtin")

    def test_valid_and_covering(self):
        cues = [(i * 5.0, i * 5.0 + 4.8, "第%d句" % i) for i in range(12)]
        r = self.check(srt_text(cues))
        self.assertTrue(r["passed"], r)
        self.assertAlmostEqual(r["coverage_seconds"], 57.6, places=2)

    def test_bom_and_crlf(self):
        cues = [(0, 55, "全部")]
        r = self.check("﻿" + srt_text(cues).replace("\n", "\r\n"))
        self.assertTrue(r["passed"], r)

    def test_low_coverage(self):
        r = self.check(srt_text([(0, 20, "a"), (10, 30, "b")]))
        self.assertTrue(r["valid"])
        self.assertFalse(r["passed"])
        self.assertAlmostEqual(r["coverage_seconds"], 30.0)

    def test_index_gap(self):
        text = srt_text([(0, 30, "a"), (30, 58, "b")]).replace("2\n00:00:30", "3\n00:00:30")
        self.assertFalse(self.check(text)["valid"])

    def test_start_not_before_end(self):
        self.assertFalse(self.check(srt_text([(0, 30, "a"), (40, 40, "b"), (41, 60, "c")]))["valid"])

    def test_decreasing_start(self):
        r = self.check(srt_text([(30, 58, "a"), (0, 29, "b")]))
        self.assertFalse(r["valid"])
        self.assertTrue(any("starts before" in p for p in r["problems"]))

    def test_garbage(self):
        r = self.check("WEBVTT\n\n00:00.000 --> 00:05.000\nhello\n")
        self.assertFalse(r["passed"])
        self.assertTrue(r["problems"])

    def test_tags_removed(self):
        cues = srt_check.parse_builtin(srt_text([(0, 2, "<i>會議</i>{\\an8}開始")]))
        self.assertEqual(srt_check.cue_text(cues), "會議開始")


class ScoreTest(unittest.TestCase):
    """The rules themselves are tested in _shared/test_shared.py; here only q15's use of them."""

    def setUp(self):
        self.tables = zh_score.zh_script.OpenCCTables(DICT)

    def test_edit_distance(self):
        self.assertEqual(zh_score.edit_distance("kitten", "sitting"), 3)
        self.assertEqual(zh_score.edit_distance("", "abc"), 3)
        self.assertEqual(zh_score.edit_distance("會議", "會議"), 0)

    def test_cer_converts_both_sides(self):
        ref = "這裡會開會，時間。"
        hyp = "这里会开会 时间"
        r = zh_score.cer(ref, hyp, self.tables)
        self.assertEqual(r["cer"], 0.0)
        r = zh_score.cer(ref, "這裡開會", self.tables)
        self.assertAlmostEqual(r["cer"], 3 / 7, places=3)
        self.assertFalse(r["passed"])

    def test_cer_nfkc_and_case(self):
        r = zh_score.cer("ＡＢＣ１２３會議", "abc123 會議", self.tables)
        self.assertEqual(r["cer"], 0.0)

    def test_script_ratio_is_the_shared_one(self):
        r = self.tables.ratio("這會錄開時間網絡" * 4)
        self.assertEqual((r["simplified"], r["differing"], r["pass"]), (0, 32, True))
        r = self.tables.ratio("这会录开时间网络" * 4)
        self.assertEqual((r["ratio"], r["pass"]), (0.0, False))
        self.assertTrue(all(self.tables.classify(c) is None for c in "台后里"))

    def test_reference_stats(self):
        r = zh_score.reference_stats("这会网络" * 20, self.tables)
        self.assertEqual(r["script_differing"], 80)
        self.assertTrue(r["pass"])

    def test_cli_all(self):
        with tempfile.TemporaryDirectory() as d:
            ref = os.path.join(d, "ref.txt")
            with open(ref, "w", encoding="utf-8") as fh:
                fh.write("這裡會開會" * 10)
            rc = zh_score.main(["--dict-dir", DICT, "all", "--ref", ref, "--text", ref, "--out", os.path.join(d, "o.json")])
            with open(os.path.join(d, "o.json"), encoding="utf-8") as fh:
                out = json.load(fh)
            self.assertEqual(out["cer"]["cer"], 0.0)
            self.assertEqual(rc, 0)


def tone(seconds, lead=0.5, tail=0.5, amp=8000, freq=440):
    n = int(seconds * build_clip.RATE)
    body = [int(amp * math.sin(2 * math.pi * freq * i / build_clip.RATE)) for i in range(n)]
    pad = lambda s: [0] * int(s * build_clip.RATE)  # noqa: E731
    return array.array("h", pad(lead) + body + pad(tail))


class ClipTest(unittest.TestCase):
    def _manifest(self, d, durations):
        clips = []
        for i, sec in enumerate(durations):
            name = "c%02d.wav" % i
            build_clip.write_wav(os.path.join(d, name), tone(sec))
            clips.append({"id": "clip-%02d" % i, "wav": name, "text": "第%d句。" % i})
        m = os.path.join(d, "manifest.json")
        with open(m, "w", encoding="utf-8") as fh:
            json.dump({"source": {"dataset": "synthetic", "license": "CC0-1.0"}, "clips": clips}, fh)
        return m

    def test_concat(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._manifest(d, [4.7, 5.1, 4.9, 5.3, 4.6, 5.0, 4.8, 5.2, 9.5, 4.9, 4.7, 3.1, 2.0, 1.2])
            out = os.path.join(d, "out")
            build_clip.main(["concat", "--manifest", m, "--out-dir", out])
            with wave.open(os.path.join(out, "clip.wav")) as w:
                self.assertEqual(w.getnframes(), 60 * build_clip.RATE)
            with wave.open(os.path.join(out, "warmup.wav")) as w:
                self.assertEqual(w.getnframes(), 10 * build_clip.RATE)
            with open(os.path.join(out, "SOURCE.json"), encoding="utf-8") as fh:
                src = json.load(fh)
            with open(os.path.join(out, "reference.txt"), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            self.assertEqual(len(lines), len(src["used"]))
            self.assertLessEqual(src["padding_seconds"], build_clip.MAX_PAD_SECONDS)
            self.assertGreater(src["stats"]["speech_seconds"], 50)
            first = src["used"][0]
            self.assertLess(first["seconds"], 4.7 + 0.25)  # silence trimmed to 100 ms per side

    def test_not_enough_speech(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._manifest(d, [5.0, 5.0])
            with self.assertRaises(SystemExit):
                build_clip.main(["concat", "--manifest", m, "--out-dir", os.path.join(d, "o")])

    def test_cut(self):
        with tempfile.TemporaryDirectory() as d:
            long = os.path.join(d, "long.wav")
            build_clip.write_wav(long, tone(70, lead=0, tail=0))
            ref = os.path.join(d, "ref.txt")
            with open(ref, "w", encoding="utf-8") as fh:
                fh.write("一段話。\n")
            out = os.path.join(d, "o")
            build_clip.main(["cut", "--wav", long, "--start", "3.5", "--text-file", ref, "--out-dir", out])
            with wave.open(os.path.join(out, "clip.wav")) as w:
                self.assertEqual(w.getnframes(), 60 * build_clip.RATE)

    def test_rejects_wrong_format(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "st.wav")
            with wave.open(p, "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(44100)
                w.writeframes(b"\0" * 400)
            with self.assertRaises(SystemExit):
                build_clip.read_wav(p)


class SelectTest(unittest.TestCase):
    def test_rule(self):
        import select_clips

        rows = [
            {"client_id": "a", "path": "x1.mp3", "sentence": "今天的會議從下午兩點開始請準時出席", "up_votes": "2", "down_votes": "0"},
            {"client_id": "a", "path": "x2.mp3", "sentence": "同一位說話者的第二句話不應該被選到喔", "up_votes": "3", "down_votes": "0"},
            {"client_id": "b", "path": "x3.mp3", "sentence": "太短了", "up_votes": "5", "down_votes": "0"},
            {"client_id": "c", "path": "x4.mp3", "sentence": "這一句有人投了反對票所以不能使用的", "up_votes": "4", "down_votes": "1"},
            {"client_id": "d", "path": "x5.mp3", "sentence": "這一句符合所有條件應該會被選進清單", "up_votes": "2", "down_votes": "0"},
        ]
        got = select_clips.select(rows, 10)
        self.assertEqual(sorted(r["path"] for r in got), ["x1.mp3", "x5.mp3"])
        self.assertEqual(select_clips.select(rows, 10), select_clips.select(list(reversed(rows[:1])) + rows[1:], 10))

    def test_cli(self):
        import select_clips

        with tempfile.TemporaryDirectory() as d:
            tsv = os.path.join(d, "validated.tsv")
            with open(tsv, "w", encoding="utf-8") as fh:
                fh.write("client_id\tpath\tsentence\tup_votes\tdown_votes\taccents\n")
                for i in range(30):
                    fh.write("s%d\tclip_%02d.mp3\t第%d句測試用的句子內容要夠長才可以\t2\t0\t\n" % (i, i, i))
            for i in range(30):
                with open(os.path.join(d, "clip_%02d.mp3" % i), "wb") as fh:
                    fh.write(b"fake%d" % i)
            out = os.path.join(d, "m.json")
            select_clips.main(["--tsv", tsv, "--clips-dir", d, "--count", "20", "--dataset", "synthetic",
                               "--url", "file://local", "--out", out])
            with open(out, encoding="utf-8") as fh:
                m = json.load(fh)
            self.assertEqual(len(m["clips"]), 20)
            self.assertTrue(all(c["wav"].endswith(".wav") and len(c["original_sha256"]) == 64 for c in m["clips"]))


class NoTorchTest(unittest.TestCase):
    def run_check(self, root):
        return subprocess.run(["sh", os.path.join(ROOT, "check_no_torch.sh"), root],
                              stdout=subprocess.PIPE, universal_newlines=True)

    def test_detects_venv_and_ignores_cache(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "root/.cache/pip/http/torch"))
            os.makedirs(os.path.join(d, "opt/venv/lib/python3.12/site-packages/numpy"))
            self.assertEqual(self.run_check(d).returncode, 0)
            os.makedirs(os.path.join(d, "opt/venv/lib/python3.12/site-packages/torch-2.5.1+cpu.dist-info"))
            r = self.run_check(d + "/")
            self.assertEqual(r.returncode, 1)
            self.assertIn("torch-2.5.1+cpu.dist-info", r.stdout)

    def test_detects_dist_packages(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "usr/lib/python3/dist-packages/torch"))
            self.assertEqual(self.run_check(d).returncode, 1)


if __name__ == "__main__":
    unittest.main()
