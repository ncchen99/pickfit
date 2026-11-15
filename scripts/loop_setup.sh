#!/usr/bin/env bash
# Make the worktree an ingest loop runs in (docs/loop.md): its own branch loop/<date>, the main checkout's
# .env and runs/ linked in, and the loop's guard installed for that worktree only.
#
#   scripts/loop_setup.sh            # .claude/worktrees/loop on a new branch loop/<today>, from main
#   scripts/loop_setup.sh night      # another worktree, .claude/worktrees/night
#   LOOP_BASE=claude/harness-loop scripts/loop_setup.sh    # branch from somewhere else
#
# Run again on an existing loop worktree to refresh its settings from loop/settings.json. Nothing here
# changes the main checkout, another session's worktree, or any setting outside the loop worktree.
set -euo pipefail

common=$(git rev-parse --path-format=absolute --git-common-dir)
main=${common%/.git}
name=${1:-loop}
dir="$main/.claude/worktrees/$name"
base=${LOOP_BASE:-main}

if [ -d "$dir" ]; then
  branch=$(git -C "$dir" branch --show-current)
  case "$branch" in
    loop/*) echo "loop_setup: $dir exists on $branch; refreshing its settings" ;;
    *) echo "loop_setup: $dir exists on branch '$branch', which is not a loop branch; pick another name" >&2
       exit 2 ;;
  esac
else
  branch="loop/$(date +%Y%m%d)"
  if git -C "$main" show-ref --verify --quiet "refs/heads/$branch"; then
    branch="$branch-$(date +%H%M)"
  fi
  if ! git -C "$main" cat-file -e "$base:loop/settings.json" 2>/dev/null; then
    echo "loop_setup: $base has no loop/settings.json yet; merge the loop scaffolding first, or set LOOP_BASE" >&2
    exit 2
  fi
  git -C "$main" worktree add "$dir" -b "$branch" "$base"
fi

# The pipeline reads .env itself and keeps its database, traces and evidence under runs/; both live in the
# main checkout and neither is in git. The session never reads .env (scripts/loop_guard.py).
[ -e "$dir/.env" ] || [ ! -e "$main/.env" ] || ln -s "$main/.env" "$dir/.env"
[ -e "$dir/runs" ] || { mkdir -p "$main/runs"; ln -s "$main/runs" "$dir/runs"; }

# settings.local.json is read only by sessions started in this worktree and is not committed.
mkdir -p "$dir/.claude"
cp "$dir/loop/settings.json" "$dir/.claude/settings.local.json"

(cd "$dir" && uv sync --quiet)

cat <<EOF

loop worktree: $dir
branch:        $branch

Attended (you can watch and steer): open a Claude Code session in that folder, choose Auto in the
permission-mode picker, and send:

  /goal Work pickfit's ingest loop as the pickfit-loop skill says. Met when \`uv run python scripts/loop_state.py status\` shows todo=0 doing=0, or 10 more items done or parked than the first status line of this session; print the status line after every item. Never ask a question: write what needs me in loop/journal.md and take the next item.

Unattended (a fresh session per batch):

  cd $dir && scripts/loop.sh --dry-run     # see the command first
  cd $dir && scripts/loop.sh

Stop it after the batch in flight:  touch $dir/loop/STOP
EOF
