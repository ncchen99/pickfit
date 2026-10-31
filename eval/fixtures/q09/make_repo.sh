#!/bin/sh
# q09 fixture: a fresh git repo for the task-tracker checks.
#
#   sh make_repo.sh DEST
#
# One commit holding a README, with fixed identity and dates, so the commit id
# is the same on every run (printed at the end). Run it as the non-root user
# that runs the answer's commands. POSIX sh + git only.
set -eu

dest=${1:?usage: make_repo.sh DEST}
if [ -e "$dest" ]; then
  echo "refusing to overwrite existing path: $dest" >&2
  exit 2
fi
mkdir -p "$dest"
cd "$dest"

# Keep any global/system git config (hooks, signing, templates) out of the build.
GIT_CONFIG_NOSYSTEM=1
GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM GIT_CONFIG_GLOBAL

git -c init.defaultBranch=main init -q
# Repo-local identity, so commits work without any home-directory git config.
git config user.name "Fixture Author"
git config user.email "fixture@example.invalid"

printf '%s\n' "# sample-project" "" "A small project used to test task tracking." > README.md
git add README.md
GIT_AUTHOR_DATE="2026-10-30T09:00:00+0800" GIT_COMMITTER_DATE="2026-10-30T09:00:00+0800" \
  git commit -q -m "Initial commit"

echo "repo: $dest"
echo "base: $(git rev-parse HEAD)"
