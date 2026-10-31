#!/usr/bin/env python3
"""Mac L2 (q11, q12): list the lines of a terminal transcript that look like
a login, sign-up, token or account prompt, or a gated-download refusal, so the
grader can review them. Python 3.8+ stdlib.

The transcript is what `script -q FILE` (macOS) recorded while the steps ran.
Escape sequences, backspaces and carriage returns are removed first.

  python3 scan_transcript.py TRANSCRIPT [TRANSCRIPT ...]

This only finds candidates. The rule the grader applies to each hit:
  * fail when a step stopped to ask for a login, password, token, API key or
    account, opened a sign-in or sign-up page, or refused a download because
    no login or license acceptance was given;
  * pass when the text only mentions such a thing and the step went on by
    itself (for example "no token found, continuing anonymously").
Exit 0 when nothing matched, 1 when there are hits to review.
"""
import re
import sys

PATTERNS = [
    r"\blog ?in\b", r"\bsign ?in\b", r"\bsign ?up\b", r"\bregister\b", r"create (an |your )?account",
    r"\baccount\b", r"\btoken\b", r"api[ _-]?key", r"\bpassword\b", r"\bpasscode\b",
    r"authenticat", r"unauthori[sz]ed", r"\b401\b", r"\b403\b", r"forbidden", r"\bgated\b",
    r"access (to|is) (this )?(model|repo|repository)", r"accept (the )?(license|terms)",
    r"credential", r"enter your", r"apple id", r"keychain",
    r"登入", r"登錄", r"登录", r"註冊", r"注册", r"帳號", r"账号", r"密碼", r"密码", r"授權", r"授权",
]
RX = re.compile("|".join(PATTERNS), re.I)
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b[@-Z\\-_]")


def clean(line):
    line = ANSI.sub("", line)
    out = []
    for ch in line:
        if ch == "\b":
            if out:
                out.pop()
        elif ch == "\r":
            out = []  # carriage return: later text overwrites the line
        else:
            out.append(ch)
    return "".join(out)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    hits = 0
    for p in argv:
        with open(p, "rb") as f:
            text = f.read().decode("utf-8", "replace")
        for n, raw in enumerate(text.split("\n"), 1):
            line = clean(raw.rstrip("\r")).strip()
            if line and RX.search(line):
                hits += 1
                print("%s:%d: %s" % (p, n, line[:200]))
    print("%d line(s) to review" % hits)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
