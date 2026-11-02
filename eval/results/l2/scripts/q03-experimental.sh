#!/bin/bash
# L2 for q03 (eval/fixtures/q03/README.md section 3), run 1, experimental: base image, the answer's install lines verbatim.
set -u
FIX=$F/q03; mkdir -p "$OUT" /work/q03
# --- _lib.sh (inlined) ---
# Shared by the L2 scripts (eval/results/l2/scripts): run an answer's lines verbatim in ONE shell, in order,
# so `source ...` and exported PATHs carry to later lines, recording each exit code (section 5: verbatim).
# A line given as "TTY:<command>" is the answer's command, run under a pseudo-terminal with Enter as the only
# input: the grader accepting the installer's default (section 5), for installers that read /dev/tty.
run_lines() {  # $1 = label, $2 = file with one answer line per line
  local n=0 line rc
  while IFS= read -r line <&3; do
    [ -z "$line" ] && continue
    n=$((n+1))
    echo "== $1 $n: $line" | tee -a "$OUT/steps.txt"
    if [ "${line#TTY:}" != "$line" ]; then
      printf '\n' | script -qec "${line#TTY:}" /dev/null > "$OUT/$1-$n.txt" 2>&1; rc=$?
    else
      eval "$line" > "$OUT/$1-$n.txt" 2>&1 < /dev/null; rc=$?
    fi
    echo "$1 $n exit $rc" | tee -a "$OUT/steps.txt"; tail -3 "$OUT/$1-$n.txt"
  done 3< "$2"
}
all_ok() { ! grep -E "^$1 [0-9]+ exit [1-9]" "$OUT/steps.txt" > /dev/null; }  # every line of label $1 exited 0
# --- end _lib.sh ---
echo "runtime before: [$(sh $FIX/check_runtime.sh)] exit $?" | tee -a "$OUT/steps.txt"
cd /work/q03
cat > /tmp/install.lines <<'LINES'
wget https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip
unzip duckdb_cli-linux-amd64.zip
install -m 755 duckdb ~/.local/bin/
LINES
run_lines install /tmp/install.lines
echo "runtime after: [$(sh $FIX/check_runtime.sh)] exit $?" | tee -a "$OUT/steps.txt"
all_ok install && echo "item 1: every install line exit 0" | tee -a "$OUT/steps.txt" || echo "item 1 FAIL (an install line failed)" | tee -a "$OUT/steps.txt"
for c in curl wget unzip; do echo "base image has $c: $(command -v $c || echo no)"; done | tee -a "$OUT/steps.txt"
echo "== done"; cat "$OUT/steps.txt"
