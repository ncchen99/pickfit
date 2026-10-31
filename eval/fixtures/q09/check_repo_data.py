#!/usr/bin/env python3
"""q09 L2-4: the committed task data is UTF-8 text, and closing one more task
changes at most 5 lines (Python 3.8+ stdlib + git).

  python3 check_repo_data.py text REPO BASE
      Every file that differs between BASE (the fixture's initial commit) and
      HEAD, i.e. everything the task commands added and the grader committed,
      must be UTF-8 text in HEAD: strict UTF-8 decoding, no NUL byte, no control
      characters other than tab, LF, CR and form feed, and git must not treat it
      as binary.

  python3 check_repo_data.py diffsize REPO BEFORE
      Run after closing one more task. Counts the changed lines against BEFORE,
      the commit taken just before the close (this also covers tools that
      commit by themselves), with the shared count of
      eval/fixtures/_shared/git_diff_lines.py (_shared/README.md section 4:
      everything staged, renames detected, per hunk max(removed, added),
      summed). Passes when the count is at most 5, no change is binary, and
      something changed.

Exit status: 0 pass, 1 fail, 2 usage error.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.environ.get("SHARED") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_shared"))
import git_diff_lines  # noqa: E402

LIMIT = 5
ALLOWED_CTRL = {0x09, 0x0A, 0x0C, 0x0D}


def git(repo, *args, **kw):
    return subprocess.run(["git", "-C", repo] + list(args), check=True,
                          stdout=subprocess.PIPE, **kw).stdout


def text_check(repo, base):
    names = [n for n in git(repo, "diff", "--name-only", "-z", "--no-renames", base, "HEAD").split(b"\0") if n]
    if not names:
        print("no files differ from %s: no task data was committed" % base)
        print("L2-4 text: FAIL")
        return 1
    numstat = git(repo, "diff", "--numstat", "-z", "--no-renames", base, "HEAD").split(b"\0")
    binary = {rec.split(b"\t", 2)[2] for rec in numstat if rec.startswith(b"-\t-\t")}
    bad = 0
    for n in names:
        path = n.decode("utf-8", "replace")
        exists = subprocess.run(["git", "-C", repo, "cat-file", "-e", "HEAD:" + path],
                                stderr=subprocess.DEVNULL).returncode == 0
        if not exists:
            print("  deleted  %s" % path)
            continue
        data = git(repo, "cat-file", "blob", "HEAD:" + path)
        problems = []
        if n in binary:
            problems.append("git treats it as binary")
        if b"\0" in data:
            problems.append("contains NUL")
        try:
            t = data.decode("utf-8", "strict")
            ctrl = sorted({hex(ord(c)) for c in t if ord(c) < 0x20 and ord(c) not in ALLOWED_CTRL or ord(c) == 0x7F})
            if ctrl:
                problems.append("control characters %s" % ", ".join(ctrl))
        except UnicodeDecodeError as e:
            problems.append("not UTF-8 (%s)" % e)
        print("  %-8s %s (%d bytes)%s" % ("ok" if not problems else "BAD", path, len(data),
                                          "" if not problems else ": " + "; ".join(problems)))
        bad += bool(problems)
    print("L2-4 text: %s" % ("PASS" if not bad else "FAIL"))
    return 0 if not bad else 1


def diffsize(repo, before):
    count = git_diff_lines.count(repo, before)
    total, binary = count["changed_lines"], count["binary"]
    print(git(repo, "diff", "--cached", "-M", "--stat", before).decode("utf-8", "replace").rstrip())
    print("changed lines (shared count): %s, limit %d (added %d, removed %d, renamed %s)"
          % (total, LIMIT, count["added"], count["removed"], count["renamed"] or "none"))
    if binary:
        print("binary changes: %s" % ", ".join(binary))
    ok = total is not None and total <= LIMIT and not binary and bool(count["files"])
    if not count["files"]:
        print("no change at all: the close was not written to the repository")
    print("L2-4 diff: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv):
    if len(argv) != 3 or argv[0] not in ("text", "diffsize"):
        print(__doc__)
        return 2
    cmd, repo, rev = argv
    return text_check(repo, rev) if cmd == "text" else diffsize(repo, rev)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
