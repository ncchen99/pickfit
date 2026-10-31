#!/usr/bin/env python3
"""q07 L2-5: commit the request files, change one request's URL, measure the git diff.

    diff_check.py init   PROJECT_DIR
    diff_check.py edit   PROJECT_DIR --file REL_PATH --from OLD --to NEW
    diff_check.py report PROJECT_DIR --file REL_PATH [--report diff.json]

init    git init + commit everything in PROJECT_DIR as the baseline (needs git).
edit    replace every occurrence of OLD with NEW in that one file (bytes, no reformatting);
        prints the count. Run it more than once when the tool stores the URL in more than
        one form (for example a full URL plus a path list), each time for a form of the
        same URL. Editing by hand in a text editor is equally fine.
report  verdict on `git diff` against the baseline, counted by the shared
        eval/fixtures/_shared/git_diff_lines.py (_shared/README.md section 4):
          * exactly one path differs (new, deleted and moved files included) and it is
            REL_PATH, modified in place; no other file was added, removed or changed;
          * that file is valid UTF-8 text and not a binary change;
          * changed lines (the shared count: per hunk max(removed, added), summed) <= 3;
          * every removed line contains "widgets" and every added line contains "gadgets"
            (the change touches only the edited request's URL, which also shows the other
            requests are untouched when all three share one file).
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.environ.get("SHARED") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_shared"))
import git_diff_lines  # noqa: E402

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="eval", GIT_AUTHOR_EMAIL="eval@localhost",
               GIT_COMMITTER_NAME="eval", GIT_COMMITTER_EMAIL="eval@localhost",
               GIT_AUTHOR_DATE="2026-10-30T00:00:00Z", GIT_COMMITTER_DATE="2026-10-30T00:00:00Z")


def git(d, *args):
    return subprocess.run(["git", "-C", d, "-c", "core.autocrlf=false", "-c", "core.quotepath=false"] + list(args),
                          capture_output=True, text=True, env=GIT_ENV, check=False)


def init(d):
    if os.path.isdir(os.path.join(d, ".git")):
        sys.exit("%s already has a .git directory; use a fresh copy of the project" % d)
    for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "q07 baseline")):
        r = git(d, *args)
        if r.returncode:
            sys.exit("git %s failed: %s" % (args[0], r.stderr))
    files = git(d, "ls-files").stdout.split()
    print(json.dumps({"baseline_commit": git(d, "rev-parse", "HEAD").stdout.strip(), "files": files}, indent=2))


def edit(d, rel, old, new):
    path = os.path.join(d, rel)
    data = open(path, "rb").read()
    n = data.count(old.encode("utf-8"))
    if n == 0:
        sys.exit("%r not found in %s" % (old, rel))
    with open(path, "wb") as fh:
        fh.write(data.replace(old.encode("utf-8"), new.encode("utf-8")))
    print(json.dumps({"file": rel, "replaced": n, "from": old, "to": new}))


def report(d, rel, out):
    count = git_diff_lines.count(d, "HEAD")
    files = count["files"]
    diff = count["diff"]
    removed = [ln[1:] for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")]
    added = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    one = len(files) == 1 and files[0]["path"] == rel and files[0]["status"] == "M"
    binary = bool(count["binary"])
    utf8 = bool(files) and all(f.get("utf8_text") for f in files)
    changed = count["changed_lines"]
    only_url = bool(removed) and bool(added) and all("widgets" in ln for ln in removed) and \
        all("gadgets" in ln for ln in added)
    ok = one and not binary and utf8 and changed is not None and changed <= 3 and only_url
    res = {"pass": ok, "changed_paths": [(f["status"], f["path"]) for f in files], "one_file_is_the_edited_file": one,
           "binary": binary, "utf8": utf8, "added": count["added"], "deleted": count["removed"],
           "changed_lines": changed, "threshold": 3, "only_url_lines_changed": only_url, "diff": diff[:4000]}
    text = json.dumps(res, ensure_ascii=False, indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["init", "edit", "report"])
    ap.add_argument("dir")
    ap.add_argument("--file")
    ap.add_argument("--from", dest="old")
    ap.add_argument("--to", dest="new")
    ap.add_argument("--report")
    a = ap.parse_args()
    d = os.path.abspath(a.dir)
    if a.action == "init":
        init(d)
    elif a.action == "edit":
        edit(d, a.file, a.old, a.new)
    else:
        report(d, a.file, a.report)


if __name__ == "__main__":
    main()
