#!/bin/bash
# L2 for q17, run 1, experimental: the answer's install lines verbatim in one shell (dev image).
set -u
mkdir -p "$OUT" /work/q17
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
cd /work/q17
DEBIAN_FRONTEND=noninteractive apt-get update -qq > /dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sudo > /dev/null; echo "environment: sudo (9.3 A) exit $?"
cat > /tmp/install.lines <<'LINES'
TTY:sudo apt install poppler-utils
curl -fsSL https://ollama.com/install.sh -o ollama-install.sh
less ollama-install.sh && sh ollama-install.sh
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
cargo install aichat
LINES
run_lines install /tmp/install.lines
all_ok install && echo "item 1: every install line exit 0" | tee -a "$OUT/steps.txt" || echo "item 1 FAIL (an install line failed)" | tee -a "$OUT/steps.txt"
for c in less cargo ollama pdftotext aichat; do echo "image has $c: $(command -v $c || echo no)"; done | tee -a "$OUT/steps.txt"
echo "== done"; cat "$OUT/steps.txt"
