#!/usr/bin/env python3
"""q10 fixture self-test (Python 3.8+ stdlib; git optional).

1. Checks the fixture files: doc_old.md and doc_new.md differ in exactly one
   character, at the place expected.json says.
2. Runs extract_spans.py on hand-built byte strings (no git involved) that
   imitate each output form the extractor must accept or reject.
3. If git is on PATH, builds the repo with make_repo.sh and checks the two
   negative controls the checklist names: whole-line marking and the default
   whitespace word diff must both FAIL L2-2. Colour is forced with
   `-c color.ui=always` here because this self-test has no pseudo-terminal;
   if util-linux `script` is available (Linux), the same controls also run
   through capture.sh under a real pty.

Exit 0 when every check behaves as expected.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract_spans as ex  # noqa: E402

with open(os.path.join(HERE, "expected.json"), encoding="utf-8") as f:
    EXP = json.load(f)
with open(os.path.join(HERE, "doc_old.md"), encoding="utf-8") as f:
    OLD = f.read()
with open(os.path.join(HERE, "doc_new.md"), encoding="utf-8") as f:
    NEW = f.read()

failures = []


def check(name, cond):
    print("%-58s %s" % (name, "ok" if cond else "FAILED"))
    if not cond:
        failures.append(name)


# ------------------------------------------------------------ 1. fixture files
old_lines, new_lines = OLD.split("\n"), NEW.split("\n")
po, pn = old_lines[EXP["paragraph_line"] - 1], new_lines[EXP["paragraph_line"] - 1]
diffs = [i for i, (a, b) in enumerate(zip(po, pn)) if a != b]
check("fixture: same number of lines", len(old_lines) == len(new_lines))
check("fixture: other lines identical",
      all(a == b for k, (a, b) in enumerate(zip(old_lines, new_lines)) if k != EXP["paragraph_line"] - 1))
check("fixture: paragraph is one line without spaces", " " not in po and len(po) == EXP["paragraph_chars"])
check("fixture: exactly one character differs", len(po) == len(pn) and diffs == [EXP["changed_index_in_paragraph"]])
check("fixture: old/new characters as expected",
      po[diffs[0]] == EXP["old_char"] and pn[diffs[0]] == EXP["new_char"])
check("fixture: changed characters appear once only",
      OLD.count(EXP["old_char"]) == 1 and NEW.count(EXP["new_char"]) == 1
      and OLD.count(EXP["new_char"]) == 0 and NEW.count(EXP["old_char"]) == 0)
check("fixture: about 200 Han characters", 180 <= EXP["paragraph_han_chars"] <= 220)
check("fixture: the two characters share 2 leading UTF-8 bytes",
      EXP["old_char"].encode()[:2] == EXP["new_char"].encode()[:2])

# ------------------------------------------------------------ 2. synthetic outputs
R, G, X = b"\x1b[31m", b"\x1b[32m", b"\x1b[m"
i = EXP["changed_index_in_paragraph"]
pre, post = po[:i].encode(), po[i + 1:].encode()
oc, nc = EXP["old_char"].encode(), EXP["new_char"].encode()
HDR = (b"\x1b[1mdiff --git a/doc.md b/doc.md\x1b[m\n\x1b[1mindex 17de607..c86ca96 100644\x1b[m\n"
       b"\x1b[1m--- a/doc.md\x1b[m\n\x1b[1m+++ b/doc.md\x1b[m\n\x1b[36m@@ -1,3 +1,3 @@\x1b[m\n")
HEAD_CTX = old_lines[0].encode() + b"\n\n"


def run(data):
    return ex.analyse(data, EXP)


def case(name, data, want2, want3, want5):
    """want2/want3/want5: expected pass/fail of L2-2, L2-3 and L2-5."""
    rep = run(data)
    got = (rep["l2_2"]["pass"], rep["l2_3"]["pass"], rep["l2_5"]["pass"])
    ok = got == (want2, want3, want5)
    if not ok:
        print("   report:", json.dumps({k: rep[k] for k in ("mode", "spans", "l2_2", "l2_3", "l2_5")},
                                       ensure_ascii=False))
    check("synthetic: " + name, ok)


case("colour runs, one char each", HDR + HEAD_CTX + pre + R + oc + X + G + nc + X + post + b"\n",
     True, True, True)
case("markers inside colour", HDR + HEAD_CTX + pre + R + b"[-" + oc + b"-]" + X + G + b"{+" + nc + b"+}" + X + post + b"\n",
     True, True, True)
case("markers without colour", HEAD_CTX + pre + b"[-" + oc + b"-]{+" + nc + b"+}" + post + b"\n",
     True, True, True)
case("pty echo of ^D with backspaces", b"^D\x08\x08" + HDR + HEAD_CTX + pre + R + oc + X + G + nc + X + post + b"\n",
     True, True, True)
case("pty line endings (CRLF)", (HDR + HEAD_CTX + pre + R + oc + X + G + nc + X + post + b"\n").replace(b"\n", b"\r\n"),
     True, True, True)
nb_pre = po[i - 1].encode()
case("3-char spans with a neighbour", HDR + HEAD_CTX + pre[:-len(nb_pre)] + R + nb_pre + oc + X + G + nb_pre + nc + X + post + b"\n",
     True, True, True)
case("256-colour and bold attributes", HDR + HEAD_CTX + pre + b"\x1b[1;38;5;9m" + oc + b"\x1b[0m\x1b[1;38;5;10m" + nc + b"\x1b[0m" + post + b"\n",
     True, True, True)
case("24-bit colour (colon form)", HDR + HEAD_CTX + pre + b"\x1b[38:2::220:40:40m" + oc + b"\x1b[m\x1b[38;2;40;200;60m" + nc + b"\x1b[m" + post + b"\n",
     True, True, True)
case("highlighted run inside coloured lines",
     HDR + HEAD_CTX + R + b"-" + pre + b"\x1b[7m" + oc + b"\x1b[27m" + post + X + b"\n"
     + G + b"+" + pre + b"\x1b[7m" + nc + b"\x1b[27m" + post + X + b"\n",
     True, True, True)
case("whole-line colour (plain diff)",
     HDR + b" " + HEAD_CTX + R + b"-" + po.encode() + X + b"\n" + G + b"+" + pn.encode() + X + b"\n",
     False, True, True)
case("whitespace word diff (whole paragraph)",
     HDR + HEAD_CTX + R + b"[-" + po.encode() + b"-]" + X + G + b"{+" + pn.encode() + b"+}" + X + b"\n",
     False, True, True)
case("no colour, no markers", b"-" + po.encode() + b"\n+" + pn.encode() + b"\n", False, True, False)
split_pre = pre + oc[:2]
case("byte-split character (colour)", HDR + HEAD_CTX + split_pre + R + oc[2:] + X + G + nc[2:] + X + post + b"\n",
     False, False, True)
case("byte-split character (markers)", HEAD_CTX + split_pre + b"[-" + oc[2:] + b"-]{+" + nc[2:] + b"+}" + post + b"\n",
     False, False, True)
case("JSON output", json.dumps({"removed": EXP["old_char"], "added": EXP["new_char"]}, ensure_ascii=False).encode() + b"\n",
     False, False, False)
three = po[i - 3:i].encode()
case("4-char spans (too long)", HDR + HEAD_CTX + pre[:-len(three)] + R + three + oc + X + G + three + nc + X + post + b"\n",
     False, True, True)

# ------------------------------------------------------------ 3. git negative controls
git = shutil.which("git")
if not git:
    print("git not found: skipping the git negative controls")
else:
    tmp = tempfile.mkdtemp(prefix="q10-selftest-")
    try:
        repo = os.path.join(tmp, "repo")
        subprocess.run(["sh", os.path.join(HERE, "make_repo.sh"), repo], check=True,
                       stdout=subprocess.DEVNULL)
        env = dict(os.environ)
        for k in list(env):
            if k.startswith("LC_") or k in ("LANGUAGE", "GIT_DIR", "GIT_WORK_TREE"):
                env.pop(k)
        env.update(LANG="C.UTF-8", GIT_PAGER="cat", TERM="xterm-256color",
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        for label, args in (("whole-line marking", ["diff"]),
                            ("default whitespace word diff", ["diff", "--word-diff"]),
                            ("whitespace word diff, colour only", ["diff", "--word-diff=color"])):
            for colour in (True, False):
                cmd = [git, "-c", "color.ui=%s" % ("always" if colour else "never")] + args
                out = subprocess.run(cmd, cwd=repo, env=env, stdout=subprocess.PIPE).stdout
                rep = run(out)
                check("git control fails L2-2: %s%s" % (label, "" if colour else " (no colour)"),
                      not rep["l2_2"]["pass"] and rep["l2_3"]["pass"])
        script = shutil.which("script")
        is_util_linux = False
        if script:
            v = subprocess.run([script, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            is_util_linux = b"util-linux" in v.stdout
        if is_util_linux:
            for label, c in (("whole-line marking", "git diff"), ("default whitespace word diff", "git diff --word-diff")):
                raw = os.path.join(tmp, "pty.raw")
                subprocess.run(["sh", os.path.join(HERE, "capture.sh"), repo, raw, c], check=True,
                               stdout=subprocess.DEVNULL,
                               env=dict(env, GIT_CONFIG_GLOBAL=os.devnull))
                with open(raw, "rb") as f:
                    rep = run(f.read())
                check("pty control (capture.sh) fails L2-2: " + label,
                      rep["mode"] == "color" and not rep["l2_2"]["pass"])
        else:
            print("util-linux script not found: skipping the pty controls (run this on Linux)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print()
print("ALL OK" if not failures else "FAILED: %d check(s)" % len(failures))
sys.exit(1 if failures else 0)
