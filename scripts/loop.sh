#!/usr/bin/env bash
# The ingest loop, unattended: one fresh Claude Code session per batch of items (docs/loop.md).
#
#   scripts/loop.sh                          # up to 10 batches of 6 items
#   LOOP_BATCHES=30 LOOP_ITEMS=2 scripts/loop.sh
#   LOOP_MODEL=sonnet scripts/loop.sh        # another model for the sessions
#   scripts/loop.sh --dry-run                # print one batch's command and run nothing
#   scripts/loop.sh --probe                  # one small session: does the guard refuse an edit to a judge?
#   touch loop/STOP                          # ends the loop after the batch in flight
#
# Run it in a loop worktree (scripts/loop_setup.sh). Every batch is a new session, so nothing is carried in
# a context window: what is done, parked or broken is in loop/. After each batch this script, not the
# session, looks at the branch: a protected file that changed or a test that was deleted stops the loop
# (exit 4), and two batches in a row that changed nothing stop it too (exit 5). No batch starts once a
# spending cap of loop/budget.json is reached (exit 6).
#
# Do not export ANTHROPIC_API_KEY into this shell unless the sessions should bill the API key: `claude`
# uses a key it finds in its environment (docs/plan.md, section 2, rule 7). pickfit reads .env by itself.
set -euo pipefail

dry=0
[ "${1:-}" = "--dry-run" ] && dry=1

cd "$(git rev-parse --show-toplevel)"
branch=$(git branch --show-current)
case "$branch" in
  loop/*) ;;
  *) if [ "$dry" = 0 ] && [ "${1:-}" != "--probe" ]; then
       echo "loop.sh: this is branch '$branch'. Run it in a loop worktree (scripts/loop_setup.sh makes one)." >&2
       exit 2
     fi ;;
esac

batches=${LOOP_BATCHES:-10}
# 6 items a session (3 until 11/19): a session now reads one line per open issue and a few lines per verify run
# (scripts/loop_state.py open-issues, run-summary), so each item fills less of its context, and the rules and the
# issue list are read once for twice the items. Claude Code's spending estimate grows with it, about US$8 an item.
items=${LOOP_ITEMS:-6}
batch_usd=${LOOP_BATCH_USD:-$(( (items * 25 + 2) / 3 ))}
model=${LOOP_MODEL:-}
logs=${LOOP_LOG_DIR:-runs/loop}

state() { uv run --quiet python scripts/loop_state.py "$@"; }

budget() { python3 scripts/loop_budget.py "$@"; }

goal="/goal Work pickfit's ingest loop exactly as the pickfit-loop skill says (read .claude/skills/pickfit-loop/SKILL.md first). The goal is met when \`uv run python scripts/loop_state.py status\` shows done plus parked at least $items higher than in the first status line you printed in this session, or shows todo=0 doing=0, or \`python3 scripts/loop_budget.py status\` says a cap is reached. Print both status lines before the first item and after every item. Never ask a question: write what needs a person in loop/journal.md and take the next item. Stop after $((items * 6)) turns in any case."

cmd=(claude -p "$goal" --permission-mode auto --settings loop/settings.json
     --max-budget-usd "$batch_usd" --output-format stream-json --verbose)
[ -n "$model" ] && cmd+=(--model "$model")

if [ "${1:-}" = "--probe" ]; then
  # One small session that tries what the guard must refuse. Run it once after loop_setup.sh.
  target=pickfit/verify/verdict.py
  if [ -n "$(git status --porcelain -- "$target")" ]; then
    echo "loop.sh: $target already has changes; commit or restore it before probing" >&2
    exit 2
  fi
  out=$(claude -p "Do exactly two things and quote any refusal message in full: (1) with the Edit tool, append the line '# probe' to $target; (2) run this shell command: sed -i '' 's/a/a/' $target . If one is refused, do not try another way." \
          --permission-mode acceptEdits --allowedTools "Bash(sed *)" "Read" "Edit" \
          --settings loop/settings.json --max-budget-usd 1 2>&1) || true
  echo "$out" | tail -15
  if [ -n "$(git status --porcelain -- "$target")" ]; then
    echo "loop.sh: the guard did NOT hold: $target changed. Restore it and check loop/settings.json." >&2
    exit 1
  fi
  case "$out" in
    *"decides verdicts"*|*"does not edit"*) echo "loop.sh: the guard refused both attempts" ;;
    *) echo "loop.sh: $target is untouched, but the session did not quote the guard; read the output above" >&2
       exit 1 ;;
  esac
  exit 0
fi

if [ "$dry" = 1 ]; then
  echo "branch:  $branch"
  echo "status:  $(state status)"
  echo "budget:  $(budget status || true)"
  echo "batches: $batches x $items items, at most US\$$batch_usd of model use each (Claude Code's own estimate)"
  printf 'command:'; printf ' %q' "${cmd[@]}"; echo
  exit 0
fi

notify() {
  echo "loop.sh: $1"
  command -v osascript >/dev/null 2>&1 \
    && osascript -e "display notification \"$1\" with title \"pickfit loop\"" >/dev/null 2>&1 || true
}

if [ -n "${ANTHROPIC_API_KEY:-}" ] && [ "${LOOP_ALLOW_API_KEY:-0}" != 1 ]; then
  echo "loop.sh: ANTHROPIC_API_KEY is set in this shell, so the Claude Code sessions themselves would be billed" >&2
  echo "         to the API credit the pipeline needs. Unset it, or run with LOOP_ALLOW_API_KEY=1 to accept that." >&2
  exit 2
fi

mkdir -p "$logs" loop/proposals
protected=$(python3 scripts/loop_guard.py --list-protected)
idle=0
n=0
while [ "$n" -lt "$batches" ]; do
  n=$((n + 1))
  if [ -e loop/STOP ]; then
    notify "loop/STOP is there: stopped before batch $n"
    exit 0
  fi
  rc=0
  before_status=$(state status --exit-code) || rc=$?
  if [ "$rc" = 3 ]; then
    notify "the queue is empty: $before_status"
    exit 0
  elif [ "$rc" != 0 ]; then
    echo "loop.sh: loop_state.py failed ($rc)" >&2
    exit "$rc"
  fi
  rc=0
  spent=$(budget status --exit-code) || rc=$?
  if [ "$rc" != 0 ]; then  # 4: a cap is reached; 2: the budget cannot be read. Either way nothing is started.
    notify "no batch $n: $spent"
    exit 6
  fi
  before=$(git rev-parse HEAD)
  log="$logs/$(date +%Y%m%d-%H%M%S)-batch$n.jsonl"
  echo "loop.sh: batch $n of $batches -> $log"
  "${cmd[@]}" >"$log" 2>&1 || echo "loop.sh: batch $n: claude exited $?"

  # What the session may not decide for itself, checked from outside it.
  # shellcheck disable=SC2086
  changed=$( { git diff --name-only "$before" HEAD -- $protected; git status --porcelain -- $protected | awk '{print $NF}'; } | sort -u)
  deleted=$(git diff --diff-filter=D --name-only "$before" HEAD -- tests/)
  edited=$(git diff --diff-filter=M --name-only "$before" HEAD -- tests/)
  after_status=$(state status)
  {
    echo
    echo "## $(date '+%Y-%m-%d %H:%M') loop.sh batch $n"
    echo "- status: $after_status"
    echo "- $(budget status || true)"
    echo "- commits: $(git rev-list --count "$before"..HEAD)，log: $log"
    [ -z "$edited" ] || echo "- 這批改過的既有測試（請看一眼有沒有改鬆）：$(echo $edited)"
    [ -z "$changed" ] || echo "- 需要你：受保護的檔案被改了，loop 已停：$(echo $changed)"
    [ -z "$deleted" ] || echo "- 需要你：測試被刪了，loop 已停：$(echo $deleted)"
  } >>loop/journal.md
  git add loop/journal.md
  git commit -q -m "Loop: batch $n summary" -- loop/journal.md || true

  if [ -n "$changed$deleted" ]; then
    notify "batch $n touched a protected file or deleted a test; see loop/journal.md"
    exit 4
  fi
  if [ "$after_status" = "$before_status" ] && [ "$(git rev-parse HEAD~1 2>/dev/null)" = "$before" ]; then
    idle=$((idle + 1))
  else
    idle=0
  fi
  if [ "$idle" -ge 2 ]; then
    notify "two batches in a row changed nothing; see $log"
    exit 5
  fi
done
notify "$batches batches done: $(state status)"
