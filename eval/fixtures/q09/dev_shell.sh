#!/bin/sh
# q09: run one command as the non-root user, the way a new terminal would.
# Run as root.
#
#   sh dev_shell.sh [-C DIR] 'COMMAND'
#
# The command runs in an interactive login bash of user "dev" (so ~/.profile
# and ~/.bashrc apply, as in a new terminal), with LANG=C.UTF-8.
# With Q09_PRELUDE=FILE set, FILE is sourced first: it holds the answer's
# session-only lines (export / source / eval) copied verbatim, so each new
# shell behaves like the terminal the user installed in. With
# EGRESS_LOG=DIR/NAME.log set, the whole thing runs under the shared egress
# check (eval/fixtures/_shared/egress.py run --out DIR --label NAME); its output
# is printed afterwards. SHARED names the _shared folder (default: next to
# this folder).
#
# Exit status: the command's exit status.
set -eu

user=${Q09_USER:-dev}
dir=
if [ "${1:-}" = "-C" ]; then
  dir=$2
  shift 2
fi
cmd=${1:?usage: dev_shell.sh [-C DIR] COMMAND}

home=$(getent passwd "$user" | cut -d: -f6)
[ -n "$dir" ] || dir=$home

cmdfile=$(mktemp /tmp/q09-cmd.XXXXXX)
trap 'rm -f "$cmdfile"' EXIT
{
  printf 'cd %s || exit 97\n' "'$(printf '%s' "$dir" | sed "s/'/'\\\\''/g")'"
  if [ -n "${Q09_PRELUDE:-}" ]; then
    printf '. %s\n' "'$Q09_PRELUDE'"
  fi
  printf '%s\n' "$cmd"
} > "$cmdfile"
chmod 0644 "$cmdfile"

run="LANG=C.UTF-8 TERM=xterm-256color exec bash -li $cmdfile"

if [ -n "${EGRESS_LOG:-}" ]; then
  shared=${SHARED:-$(cd "$(dirname "$0")/../_shared" && pwd)}
  eg_dir=$(dirname "$EGRESS_LOG")
  eg_label=$(basename "$EGRESS_LOG" .log)
  set +e
  python3 "$shared/egress.py" run --out "$eg_dir" --label "$eg_label" -- su - "$user" -c "$run"
  rc=$?
  set -e
  cat "$eg_dir/$eg_label.stdout"
  cat "$eg_dir/$eg_label.stderr" >&2
  exit "$rc"
else
  su - "$user" -c "$run"
fi
