#!/bin/sh
# q03 L2 item 1, second half: after the answer's install steps, none of
# python3, java, node may be on PATH.
#
#   sh check_runtime.sh
#
# The item writes `command -v python3 java node`. In dash (Ubuntu's /bin/sh)
# `command -v` with several names looks up only the first one, so each name
# is checked on its own here; this is the same test bash runs for that line.
# Prints whatever command -v finds (nothing on a pass), then PASS or FAIL.
# Also lists python, nodejs and javac as information only (not part of the rule).
found=""
for c in python3 java node; do
  p=$(command -v "$c" 2>/dev/null) && { echo "$p"; found="$found $c"; }
done
info=""
for c in python nodejs javac; do
  p=$(command -v "$c" 2>/dev/null) && info="$info $c=$p"
done
[ -n "$info" ] && echo "info (not judged):$info" >&2
if [ -z "$found" ]; then
  echo "PASS: command -v python3 java node prints nothing" >&2
  exit 0
fi
echo "FAIL: found$found" >&2
exit 1
