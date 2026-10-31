#!/bin/sh
# q04 decryption checks (L2 items 2 and 3).
#
#   sh check_values.sh present VALUES_FILE FILE...
#       pass when every secret value appears in at least one FILE
#       (developer B's decrypted output: the file the answer's decrypt step
#       writes and/or the captured stdout of that step)
#   sh check_values.sh absent  VALUES_FILE PATH...
#       pass when no secret value appears in any PATH (files, or directories
#       searched recursively, skipping .git directories): developer C's clone
#       and captured stdout/stderr, or B's clone and captures after removal
#
# Values are never printed; a hit is reported by value number or file name.
# POSIX sh + GNU grep (Ubuntu base image).
set -u
if [ $# -lt 3 ]; then
  echo "usage: check_values.sh present|absent VALUES_FILE PATH..." >&2
  exit 2
fi
mode=$1
values=$2
shift 2
if grep -qx '' "$values"; then
  echo "check_values: VALUES_FILE has an empty line" >&2
  exit 2
fi
case $mode in
  present)
    fail=0
    i=0
    while IFS= read -r v || [ -n "$v" ]; do
      i=$((i + 1))
      if cat "$@" 2>/dev/null | grep -qF -- "$v"; then
        echo "PASS  value #$i present"
      else
        echo "FAIL  value #$i missing"
        fail=1
      fi
    done < "$values"
    ;;
  absent)
    hits=$(grep -rlF -f "$values" --exclude-dir=.git -- "$@" 2>/dev/null)
    if [ -z "$hits" ]; then
      echo "PASS  no secret value in: $*"
      fail=0
    else
      echo "FAIL  secret value(s) found in:"
      echo "$hits" | sed 's/^/        /'
      fail=1
    fi
    ;;
  *)
    echo "check_values: mode must be present or absent" >&2
    exit 2
    ;;
esac
if [ "$fail" -eq 0 ]; then echo "RESULT PASS"; else echo "RESULT FAIL"; fi
exit "$fail"
