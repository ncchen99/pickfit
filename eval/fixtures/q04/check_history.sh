#!/bin/sh
# q04 L2 item 1 check, run in developer A's repo after A encrypted and
# committed the .env as the answer describes.
#
#   sh check_history.sh REPO_DIR VALUES_FILE ENCRYPTED_PATH
#
# ENCRYPTED_PATH is the committed encrypted file the answer produces (path
# relative to REPO_DIR, as the answer names it).
#
# Pass when all of these hold:
#   1. at least one commit exists and ENCRYPTED_PATH is tracked at HEAD;
#   2. for every secret value V in VALUES_FILE,
#        git rev-list --all | xargs git grep -F V
#      prints nothing (the command in the item, run verbatim);
#   3. .env is untracked:  git ls-files --error-unmatch -- .env  fails;
#   4. .env is git-ignored: git check-ignore -q -- .env  succeeds.
# Values are never printed; a leak is reported as value number and rev:path.
# POSIX sh + git + xargs.
set -u
if [ $# -ne 3 ]; then
  echo "usage: check_history.sh REPO_DIR VALUES_FILE ENCRYPTED_PATH" >&2
  exit 2
fi
repo=$1
values=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
enc=$3
cd "$repo" || exit 2
fail=0

nrev=$(git rev-list --all 2>/dev/null | wc -l | tr -d ' ')
if [ "$nrev" -ge 1 ] && git ls-files --error-unmatch -- "$enc" >/dev/null 2>&1; then
  echo "PASS  committed: $nrev commit(s); $enc tracked at HEAD"
else
  echo "FAIL  committed: $nrev commit(s); $enc tracked at HEAD: no"
  fail=1
fi

i=0
while IFS= read -r v || [ -n "$v" ]; do
  [ -n "$v" ] || continue
  i=$((i + 1))
  out=$(git rev-list --all | xargs git grep -F "$v")
  if [ -z "$out" ]; then
    echo "PASS  history: secret value #$i not found in any commit"
  else
    where=$(git rev-list --all | xargs git grep -l -F "$v" | head -5 | tr '\n' ' ')
    echo "FAIL  history: secret value #$i found at $where"
    fail=1
  fi
done < "$values"

if git ls-files --error-unmatch -- .env >/dev/null 2>&1; then
  echo "FAIL  untracked: .env is tracked"
  fail=1
else
  echo "PASS  untracked: .env is not tracked"
fi
if git check-ignore -q -- .env; then
  echo "PASS  ignored: .env is git-ignored"
else
  echo "FAIL  ignored: .env is not git-ignored"
  fail=1
fi
if [ -n "$(git log --all --format=%H -- .env)" ]; then
  echo "info  a commit in history touches the path .env (not judged by itself)"
fi
if [ "$fail" -eq 0 ]; then echo "RESULT PASS"; else echo "RESULT FAIL"; fi
exit "$fail"
