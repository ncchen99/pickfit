#!/usr/bin/env python3
"""The one "how many lines did this change in git diff" count (q07 L2-5, q09 L2-4).

Python 3.8+ standard library and git.

  git_diff_lines.py REPO BASE [--json FILE]

Stages everything first (`git add -A`, so new, deleted and moved files count;
a tool that commits by itself is covered because BASE is a commit taken before
the change), then reads `git diff --cached -M --unified=0 BASE`.

Changed lines: for every hunk, max(lines removed, lines added), summed over all
hunks of all files. A line edited in place is 1 changed line (it shows as one
removal and one addition); a line only added or only removed is 1; a file moved
without edits is 0 lines and is listed under `renamed`. A binary change has no
line count: it is listed under `binary` and the count is null.

Also reported: every changed path with its status, the added and removed line
counts, and whether each changed file is UTF-8 text in the working tree (strict
decoding, no NUL, no control characters other than tab, LF, CR and form feed).
The pass rule (how many lines, how many files) is the question's; this script
only counts. Exit 0 when it could count, 1 when a binary change makes the
count null, 2 on a usage or git error.
"""

import argparse
import json
import os
import re
import subprocess
import sys

HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
ALLOWED_CTRL = {0x09, 0x0A, 0x0C, 0x0D}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, "-c", "core.quotepath=false", "-c", "core.autocrlf=false"] + list(args),
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def text_problems(path):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        return ["cannot read (%s)" % exc]
    problems = []
    if b"\0" in data:
        problems.append("contains NUL")
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        return problems + ["not UTF-8 (%s)" % exc]
    ctrl = sorted({hex(ord(c)) for c in text if (ord(c) < 0x20 and ord(c) not in ALLOWED_CTRL) or ord(c) == 0x7F})
    if ctrl:
        problems.append("control characters %s" % ", ".join(ctrl))
    return problems


def count(repo, base):
    git(repo, "add", "-A")
    files = []
    raw = git(repo, "diff", "--cached", "-M", "--name-status", "-z", base).decode("utf-8", "replace").split("\0")
    i = 0
    while i < len(raw) and raw[i]:
        status = raw[i]
        if status[0] in "RC":
            files.append({"status": status, "from": raw[i + 1], "path": raw[i + 2]})
            i += 3
        else:
            files.append({"status": status, "path": raw[i + 1]})
            i += 2
    numstat, fields = {}, git(repo, "diff", "--cached", "-M", "--numstat", "-z", base).decode("utf-8", "replace").split("\0")
    i = 0
    while i < len(fields) and fields[i]:
        added, removed, path = fields[i].split("\t", 2)
        if path:
            i += 1
        else:  # a rename: "added\tremoved\t" then the old and the new path
            path = fields[i + 2]
            i += 3
        numstat[path] = (added, removed)
    diff = git(repo, "diff", "--cached", "-M", "--unified=0", "--no-color", base).decode("utf-8", "replace")
    per_file, source, current = {}, None, None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            source = current = None
        elif line.startswith("--- ") and current is None:
            source = line[6:] if line.startswith("--- a/") else None
        elif line.startswith("+++ ") and current is None:
            current = line[6:] if line.startswith("+++ b/") else source
        m = HUNK_RE.match(line)
        if m:
            removed = int(m.group(1)) if m.group(1) is not None else 1
            added = int(m.group(2)) if m.group(2) is not None else 1
            per_file[current] = per_file.get(current, 0) + max(removed, added)
    total_added = total_removed = 0
    binary, renamed = [], []
    for f in files:
        a, r = numstat.get(f["path"], ("0", "0"))
        if a == "-":
            binary.append(f["path"])
            f.update(added=None, removed=None, changed_lines=None)
        else:
            f.update(added=int(a), removed=int(r), changed_lines=per_file.get(f["path"], 0))
            total_added += int(a)
            total_removed += int(r)
        if f["status"].startswith("R"):
            renamed.append(f["path"])
        if f["status"] != "D":
            problems = text_problems(os.path.join(repo, f["path"]))
            f.update(utf8_text=not problems, text_problems=problems)
    changed = None if binary else sum(f["changed_lines"] for f in files)
    return {"base": base, "files": files, "changed_lines": changed, "added": total_added, "removed": total_removed,
            "binary": binary, "renamed": renamed, "diff": diff[:6000]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("base")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    try:
        rep = count(os.path.abspath(a.repo), a.base)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write("git_diff_lines: git failed: %s\n" % exc.stderr.decode("utf-8", "replace").strip())
        return 2
    text = json.dumps(rep, ensure_ascii=False, indent=2)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 1 if rep["changed_lines"] is None else 0


if __name__ == "__main__":
    sys.exit(main())
