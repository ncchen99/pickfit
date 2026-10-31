#!/usr/bin/env python3
"""Tests for the shared L2 tools. Python 3.8+ stdlib (unittest), git and sh; no network, no strace.

  python3 eval/fixtures/_shared/test_shared.py
  (pytest collects it too)

The live strace cases are in `egress.py selftest` and run only inside the Linux box.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import egress  # noqa: E402
import git_diff_lines  # noqa: E402
import zh_script  # noqa: E402

DICT = os.path.join(HERE, "selftest_dict")


class EgressParser(unittest.TestCase):
    def test_every_fixed_line_is_classified_as_expected(self):
        result = egress.parser_selftest()
        self.assertTrue(result["ok"], result["failed"])

    def write_run(self, folder, label, lines, self_addrs=()):
        with open(os.path.join(folder, label + ".strace"), "w") as fh:
            fh.write("\n".join(lines) + "\n")
        egress.write_json(os.path.join(folder, label + ".json"),
                          {"tool": "egress.py", "label": label, "trace": "/box/path/" + label + ".strace",
                           "self_addresses": list(self_addrs), "tracer_pid": None, "tracer_running": False,
                           "exit_code": 0})

    def report(self, folder, *labels):
        out = os.path.join(folder, "report.json")
        code = egress.main(["report", "--out", folder, "--json", out] + (["--labels"] + list(labels) if labels else []))
        with open(out) as fh:
            return code, json.load(fh)

    def test_report_pass_fail_and_undetermined(self):
        folder = tempfile.mkdtemp()
        try:
            execve = '10 1761800000.1 execve("/bin/sh", ["sh"], 0x0 /* 1 var */) = 0'
            self.write_run(folder, "clean", [execve,
                           '10 connect(3, {sa_family=AF_INET, sin_port=htons(11434), sin_addr=inet_addr("127.0.0.1")}, 16) = 0'])
            self.write_run(folder, "selfaddr", [execve,
                           '10 connect(3, {sa_family=AF_INET, sin_port=htons(80), sin_addr=inet_addr("172.17.0.2")}, 16) = 0'],
                           self_addrs=["172.17.0.2"])
            self.write_run(folder, "dirty", [execve,
                           '11 sendto(5, "x", 1, 0, {sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("127.0.0.53")}, 16) = 1'])
            self.write_run(folder, "empty", [])
            code, rep = self.report(folder, "clean", "selfaddr")
            self.assertEqual((code, rep["result"]), (0, "pass"))
            code, rep = self.report(folder, "clean", "dirty")
            self.assertEqual((code, rep["result"]), (1, "fail"))
            self.assertEqual(rep["traces"][1]["attempts"][0]["reason"], "name lookup (port 53)")
            code, rep = self.report(folder, "clean", "empty")
            self.assertEqual((code, rep["result"]), (2, "undetermined"))
            code, rep = self.report(folder, "missing")
            self.assertEqual(rep["result"], "undetermined")
            code, rep = self.report(folder)  # every label in the folder
            self.assertEqual(rep["result"], "fail")
        finally:
            shutil.rmtree(folder)


FAKE_STRACE = """#!/bin/sh
# stands in for strace in tests: writes one execve line to the -o file, then runs the command
out=
while [ $# -gt 0 ]; do
  case $1 in -o) out=$2; shift 2 ;; --) shift; break ;; *) shift ;; esac
done
echo '1 1761800000.1 execve("/bin/sh", ["sh"], 0x0 /* 1 var */) = 0' > "$out"
exec "$@"
"""


class EgressRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "strace"), "w") as fh:
            fh.write(FAKE_STRACE)
        os.chmod(os.path.join(self.bin, "strace"), 0o755)
        self.out = os.path.join(self.tmp, "eg")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_step(self, *args):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"])
        p = subprocess.run([sys.executable, os.path.join(HERE, "egress.py"), "run", "--out", self.out] + list(args),
                           env=env, capture_output=True, text=True, timeout=60)
        return p.returncode

    def meta(self, label):
        with open(os.path.join(self.out, label + ".json")) as fh:
            return json.load(fh)

    def test_shell_string_exit_code_and_output_files(self):
        self.assertEqual(self.run_step("--label", "s1", "--sh", "echo out; echo err >&2; exit 7"), 7)
        m = self.meta("s1")
        self.assertEqual((m["exit_code"], m["timed_out"], m["traced"]), (7, False, True))
        with open(m["stdout"]) as fh:
            self.assertEqual(fh.read(), "out\n")
        with open(m["stderr"]) as fh:
            self.assertEqual(fh.read(), "err\n")
        self.assertEqual(egress.main(["report", "--out", self.out, "--json", os.path.join(self.tmp, "r.json")]), 0)

    def test_argv_form_and_timeout(self):
        self.assertEqual(self.run_step("--label", "a1", "--", "sh", "-c", "exit 3"), 3)
        self.assertEqual(self.run_step("--label", "t1", "--timeout", "1", "--", "sleep", "30"), 124)
        self.assertTrue(self.meta("t1")["timed_out"])

    def test_returns_when_the_step_exits_even_with_a_leftover_process(self):
        import time
        t0 = time.monotonic()
        self.assertEqual(self.run_step("--label", "bg", "--kill-leftovers", "--sh", "sleep 20 & echo started"), 0)
        self.assertLess(time.monotonic() - t0, 15)
        self.assertTrue(self.meta("bg").get("leftovers_killed"))

    def test_window_and_epochs(self):
        self.run_step("--label", "w", "--sh", "true")
        m = self.meta("w")
        self.assertLessEqual(m["started_epoch"], m["ended_epoch"])
        with open(os.path.join(self.out, "w.strace"), "a") as fh:
            fh.write('2 1761800100.5 connect(3, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("1.2.3.4")}, 16) = 0\n')
        self.assertEqual(egress.main(["report", "--out", self.out, "--since", "1761800200"]), 0)
        self.assertEqual(egress.main(["report", "--out", self.out, "--since", "1761800000", "--until", "1761800200"]), 1)
        self.assertEqual(egress.main(["report", "--out", self.out]), 1)
        rows = egress.step_verdicts(self.out, ["w"], since=1761800200)
        self.assertEqual((rows[0]["result"], rows[0]["started_epoch"] is not None), ("pass", True))

    def test_inherit_output_keeps_the_callers_stdout(self):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"])
        p = subprocess.run([sys.executable, os.path.join(HERE, "egress.py"), "run", "--out", self.out, "--label", "io",
                            "--inherit-output", "--sh", "echo visible"], env=env, capture_output=True, text=True)
        self.assertEqual(p.stdout, "visible\n")
        self.assertIsNone(self.meta("io")["stdout"])

    def test_no_trace_is_timing_only_and_left_out_of_the_report(self):
        self.assertEqual(self.run_step("--label", "timing", "--no-trace", "--sh", "true"), 0)
        m = self.meta("timing")
        self.assertEqual((m["traced"], m["trace"]), (False, None))
        self.assertFalse(os.path.exists(os.path.join(self.out, "timing.strace")))
        self.run_step("--label", "traced", "--sh", "true")
        self.assertEqual(egress.main(["report", "--out", self.out, "--json", os.path.join(self.tmp, "r.json")]), 0)
        with open(os.path.join(self.tmp, "r.json")) as fh:
            self.assertEqual([t["label"] for t in json.load(fh)["traces"]], ["traced"])


class ZhScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = zh_script.OpenCCTables(DICT)

    def test_characters_valid_in_both_scripts_are_neutral(self):
        self.assertTrue(all(self.t.classify(c) is None for c in "台后里干只内"))
        self.assertEqual((self.t.classify("軟"), self.t.classify("软")), ("traditional", "simplified"))

    def test_thresholds(self):
        self.assertFalse(self.t.ratio("軟體" * 10)["pass"])  # 10 differing < 30
        r = self.t.ratio("網" * 95 + "网" * 5)
        self.assertEqual((r["ratio"], r["pass"]), (0.95, True))
        self.assertFalse(self.t.ratio("網" * 94 + "网" * 6)["pass"])
        self.assertIsNone(self.t.ratio("abc")["ratio"])
        self.assertEqual(set(r["dict_sha256"]), set(zh_script.DICT_FILES))

    def test_conversion_uses_phrases_then_characters_then_tw_variants(self):
        self.assertEqual(self.t.s2t("头发"), "頭髮")
        self.assertEqual(self.t.s2t("里面"), "裡面")
        self.assertEqual(self.t.s2t("里"), "裏")
        self.assertEqual(self.t.s2tw("里"), "裡")
        self.assertEqual(self.t.s2tw("网络abc"), "網絡abc")

    def test_reference_stats_count_after_s2tw(self):
        r = zh_script.reference_stats(self.t, "网络" * 30)
        self.assertEqual((r["script_differing"], r["pass"]), (60, True))


class GitDiffLines(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@localhost"}
        self.env = dict(os.environ, **env)
        self.git("init", "-q")
        self.write("a.txt", "one\ntwo\nthree\nfour\n")
        self.write("b.txt", "keep\n" * 20)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        shutil.rmtree(self.repo)

    def git(self, *args):
        return subprocess.run(["git", "-C", self.repo] + list(args), check=True, capture_output=True, text=True,
                              env=self.env).stdout

    def write(self, name, text, mode="w"):
        path = os.path.join(self.repo, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode) as fh:
            fh.write(text)

    def test_a_line_edited_in_place_is_one_line(self):
        self.write("a.txt", "one\nTWO\nthree\nfour\n")
        r = git_diff_lines.count(self.repo, self.base)
        self.assertEqual((r["changed_lines"], r["added"], r["removed"]), (1, 1, 1))
        self.assertTrue(r["files"][0]["utf8_text"])

    def test_hunks_add_up_and_new_files_count(self):
        self.write("a.txt", "one\nTWO\nthree\nfour\nfive\nsix\n")  # 1 edit + 2 added = hunks 1 and 2
        self.write("new.txt", "x\ny\n")
        r = git_diff_lines.count(self.repo, self.base)
        self.assertEqual(r["changed_lines"], 5)
        self.assertEqual(sorted(f["status"] for f in r["files"]), ["A", "M"])

    def test_a_moved_file_without_edits_is_zero_lines_and_listed(self):
        os.makedirs(os.path.join(self.repo, "closed"))
        self.git("mv", "b.txt", "closed/b.txt")
        r = git_diff_lines.count(self.repo, self.base)
        self.assertEqual((r["changed_lines"], r["renamed"]), (0, ["closed/b.txt"]))

    def test_a_deleted_file_counts_its_lines(self):
        os.unlink(os.path.join(self.repo, "a.txt"))
        r = git_diff_lines.count(self.repo, self.base)
        self.assertEqual(r["changed_lines"], 4)

    def test_binary_change_has_no_count(self):
        self.write("blob.bin", b"\0\1\2" * 10, mode="wb")
        r = git_diff_lines.count(self.repo, self.base)
        self.assertIsNone(r["changed_lines"])
        self.assertEqual(r["binary"], ["blob.bin"])

    def test_non_utf8_text_is_flagged(self):
        self.write("a.txt", "one\n".encode("utf-8") + "二".encode("big5") + b"\n", mode="wb")
        r = git_diff_lines.count(self.repo, self.base)
        self.assertFalse(next(f for f in r["files"] if f["path"] == "a.txt")["utf8_text"])


class MemPeak(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cg = os.path.join(self.tmp, "cg")
        self.proc = os.path.join(self.tmp, "proc")
        os.makedirs(os.path.join(self.proc, "1"))
        os.makedirs(self.cg)
        with open(os.path.join(self.proc, "1", "status"), "w") as fh:
            fh.write("Name:\tx\nVmRSS:\t   1000 kB\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def cgroup(self, **files):
        for name, value in files.items():
            with open(os.path.join(self.cg, name.replace("_", ".", 1)), "w") as fh:
                fh.write(value)

    def sh(self, *args, **env):
        e = dict(os.environ, CGROUP_DIR=self.cg, PROC_DIR=self.proc, INTERVAL="0.05", **env)
        p = subprocess.run(["sh", os.path.join(HERE, "mem_peak.sh")] + list(args), env=e, capture_output=True, text=True)
        return p.returncode

    def load(self, name):
        with open(os.path.join(self.tmp, name)) as fh:
            return json.load(fh)

    def test_run_uses_the_peak_counter_and_the_rule(self):
        self.cgroup(memory_current="500\n", memory_peak="800\n", memory_max="max\n",
                    memory_stat="anon 300\nfile 200\n", memory_events="oom 0\noom_kill 0\n")
        out = os.path.join(self.tmp, "run.json")
        self.assertEqual(self.sh("run", out, "echo hi; exit 3", MAX_BYTES="800"), 3)
        r = self.load("run.json")
        self.assertEqual((r["method"], r["value"], r["result"], r["oom_kills"]), ("peak counter", 800, "pass", 0))
        self.assertEqual((r["max_anon"], r["limit"], r["exit_code"]), (300, None, 3))
        with open(out + ".stdout") as fh:
            self.assertEqual(fh.read(), "hi\n")
        self.sh("run", out, "true", BELOW_BYTES="900")
        self.assertEqual(self.load("run.json")["result"], "pass")
        self.cgroup(memory_current="950\n")
        self.sh("run", out, "true", BELOW_BYTES="900")  # the peak counter (800) was already within before the step
        self.assertEqual((self.load("run.json")["value"], self.load("run.json")["result"]), (800, "pass"))
        self.cgroup(memory_peak="950\n")
        self.sh("run", out, "true", BELOW_BYTES="900")  # over the line before the step: samples decide
        r = self.load("run.json")
        self.assertEqual((r["method"], r["value"], r["result"]), ("sampled memory.current", 950, "fail"))

    def test_a_peak_already_over_the_line_falls_back_to_samples(self):
        self.cgroup(memory_current="500\n", memory_peak="5000\n", memory_stat="anon 300\n", memory_events="oom_kill 0\n")
        self.sh("run", os.path.join(self.tmp, "run.json"), "true", MAX_BYTES="1000")
        r = self.load("run.json")
        self.assertEqual((r["method"], r["value"], r["result"]), ("sampled memory.current", 500, "pass"))

    def test_read_without_cgroup_uses_rss_and_oom_fails(self):
        self.assertEqual(self.sh("read", os.path.join(self.tmp, "read.json"), BELOW_BYTES="2000000"), 0)
        r = self.load("read.json")
        self.assertEqual((r["cgroup"], r["method"], r["value"]), ("none", "sampled RSS sum", 1024000))
        self.cgroup(memory_current="10\n", memory_peak="20\n", memory_events="oom_kill 1\n")
        self.assertEqual(self.sh("read", os.path.join(self.tmp, "read.json"), MAX_BYTES="100"), 1)
        self.assertEqual(self.load("read.json")["oom_kills"], 1)

    def test_watch_then_read_folds_in_the_maxima(self):
        self.cgroup(memory_current="700\n", memory_stat="anon 600\n")
        watch = os.path.join(self.tmp, "watch.json")
        e = dict(os.environ, CGROUP_DIR=self.cg, PROC_DIR=self.proc, INTERVAL="0.05")
        p = subprocess.Popen(["sh", os.path.join(HERE, "mem_peak.sh"), "watch", watch], env=e)
        import time
        time.sleep(0.4)
        self.cgroup(memory_current="100\n")
        time.sleep(0.2)
        p.terminate()
        p.wait(10)
        self.assertEqual(self.load("watch.json")["max_current"], 700)
        self.sh("read", os.path.join(self.tmp, "read.json"), watch, MAX_BYTES="1000")
        r = self.load("read.json")
        self.assertEqual((r["max_current"], r["value"], r["result"]), (700, 700, "pass"))


if __name__ == "__main__":
    unittest.main()
