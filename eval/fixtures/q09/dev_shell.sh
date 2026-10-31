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
# EGRESS_LOG=FILE set, the whole thing runs under strace and every connect /
# sendto / sendmsg / sendmmsg call is written to FILE (see egress_parse.py).
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
  command -v strace >/dev/null 2>&1 || { echo "strace not installed" >&2; exit 98; }
  strace -f -qq -o "$EGRESS_LOG" -e trace=connect,sendto,sendmsg,sendmmsg -e signal=none \
    su - "$user" -c "$run"
else
  su - "$user" -c "$run"
fi
