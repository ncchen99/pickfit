#!/bin/sh
# q10: run one diff command under a pseudo-terminal, exactly as the checklist says,
# and keep the raw bytes it printed.
#
#   sh capture.sh REPO OUTFILE 'CMD'
#
# Runs:  cd REPO && script -qc 'CMD' /dev/null  > OUTFILE
# with   LANG=C.UTF-8, GIT_PAGER=cat, TERM=xterm-256color, no LC_* overrides.
#
# TERM must be set: git treats a missing TERM (or TERM=dumb) as a terminal that
# cannot show colour, which a real terminal never is.
# `script` is util-linux script (bsdutils on Ubuntu); this file is for the
# Linux base image, not for macOS (BSD script takes different arguments).
# POSIX sh only; python is not needed here (run extract_spans.py on OUTFILE
# afterwards, on the grader's machine or after copying the file out).
set -u

repo=${1:?usage: capture.sh REPO OUTFILE CMD}
out=${2:?usage: capture.sh REPO OUTFILE CMD}
cmd=${3:?usage: capture.sh REPO OUTFILE CMD}

case "$out" in
  /*) ;;
  *) out="$(pwd)/$out" ;;
esac

unset LC_ALL LC_CTYPE LC_COLLATE LC_MESSAGES LANGUAGE GIT_DIR GIT_WORK_TREE
LANG=C.UTF-8
GIT_PAGER=cat
TERM=xterm-256color
export LANG GIT_PAGER TERM

cd "$repo" || exit 2
script -qc "$cmd" /dev/null > "$out"
status=$?

{
  echo "cmd: $cmd"
  echo "script_exit: $status"
  echo "bytes: $(wc -c < "$out" | tr -d ' ')"
  echo "sha256: $(sha256sum "$out" 2>/dev/null | cut -d' ' -f1)"
} > "$out.meta"
cat "$out.meta"
exit 0
