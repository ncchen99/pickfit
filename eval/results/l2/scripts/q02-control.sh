#!/bin/bash
# L2 for q02 (eval/fixtures/q02/README.md section 4), run 1, control: the answer's steps verbatim.
set -u
FIX=$F/q02; ST=/opt/eval/state; mkdir -p "$ST" "$OUT" /work/q02
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
# Environment (recorded substitution, 9.3 A): sudo installed, since a stock Ubuntu has it and the dev image does not.
DEBIAN_FRONTEND=noninteractive apt-get update -qq > /dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sudo > /dev/null; echo "env sudo exit $?"
cd /work/q02
cat > /tmp/install.lines <<'LINES'
TTY:curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
cargo install leakguard
leakguard --list-kinds
LINES
run_lines install /tmp/install.lines
all_ok install && echo "item 1 PASS (every install line exit 0)" | tee -a "$OUT/steps.txt" || echo "item 1 FAIL" | tee -a "$OUT/steps.txt"
python3 "$FIX/gen_log.py" /work/q02 > "$OUT/gen_log.txt" 2>&1; cat "$OUT/gen_log.txt"
cd /work/q02
python3 "$SHARED/egress.py" run --out "$ST/q02-egress" --label pipeline --timeout 600 --sh 'cat app.log | leakguard > clean.log' < /dev/null
echo "pipeline exit: $?" | tee "$ST/q02-exit.txt" | tee -a "$OUT/steps.txt"
python3 "$FIX/check_clean.py" --manifest manifest.json --input app.log --output clean.log --report "$ST/q02-check.json" > "$OUT/check.txt" 2>&1
cat "$OUT/check.txt" | tee -a "$OUT/steps.txt"
python3 "$SHARED/egress.py" stop --out "$ST/q02-egress" > /dev/null 2>&1
python3 "$SHARED/egress.py" report --out "$ST/q02-egress" --json "$ST/q02-egress.json" > "$OUT/item4-report.txt" 2>&1
echo "item 4 egress report exit $?: $(tail -1 "$OUT/item4-report.txt")" | tee -a "$OUT/steps.txt"
# fake values stay in the sandbox (README section 2): only reports leave it
rm -f /work/q02/app.log /work/q02/manifest.json /work/q02/clean.log
cp "$ST"/q02-check.json "$ST"/q02-egress.json "$ST"/q02-exit.txt "$OUT"/ 2>/dev/null
echo "== done"; cat "$OUT/steps.txt"
