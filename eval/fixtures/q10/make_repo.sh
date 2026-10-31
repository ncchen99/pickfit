#!/bin/sh
# q10 fixture: build the frozen test repo.
#
#   sh make_repo.sh DEST            # default: doc.md committed, the one-character
#                                   # fix left as an unstaged change (what `git diff` shows)
#   sh make_repo.sh DEST --staged     # the fix is staged (for git diff --cached / --staged)
#   sh make_repo.sh DEST --committed  # the fix is a second commit instead
#                                   # (for answers that diff commits: git show, git log -p, git diff HEAD~1)
#
# POSIX sh + git only, so it runs in the q10 base image (ubuntu:24.04 + git).
# Identity and dates are fixed, so the commit ids are the same on every run.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
dest=${1:?usage: make_repo.sh DEST [--staged|--committed]}
mode=${2:-worktree}

case "$mode" in
  worktree|--staged|--committed) ;;
  *) echo "unknown option: $mode" >&2; exit 2 ;;
esac

if [ -e "$dest" ]; then
  echo "refusing to overwrite existing path: $dest" >&2
  exit 2
fi

mkdir -p "$dest"
cd "$dest"

# Keep the user's or image's global/system git config out of the fixture build.
GIT_CONFIG_NOSYSTEM=1
GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM GIT_CONFIG_GLOBAL

git -c init.defaultBranch=main init -q
git config user.name "Fixture Author"
git config user.email "fixture@example.invalid"

GIT_AUTHOR_DATE="2026-10-30T09:00:00+0800"
GIT_COMMITTER_DATE="2026-10-30T09:00:00+0800"
export GIT_AUTHOR_DATE GIT_COMMITTER_DATE

cp "$here/doc_old.md" doc.md
git add doc.md
git commit -q -m "Add setup guide"

cp "$here/doc_new.md" doc.md

if [ "$mode" = "--staged" ]; then
  git add doc.md
fi

if [ "$mode" = "--committed" ]; then
  GIT_AUTHOR_DATE="2026-10-30T09:05:00+0800"
  GIT_COMMITTER_DATE="2026-10-30T09:05:00+0800"
  export GIT_AUTHOR_DATE GIT_COMMITTER_DATE
  git commit -q -am "Fix a typo in the setup guide"
fi

echo "repo: $dest"
git log --format='%H %s'
git status --short
