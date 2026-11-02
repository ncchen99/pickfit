#!/bin/bash
# L2 for q05 (eval/fixtures/q05/README.md section 5), run 1, experimental: the answer's steps verbatim in one shell.
set -u
FIX=$F/q05; mkdir -p "$OUT" /work/in /work/out/pdf /work/out/docx
cp "$FIX/fixture.pdf" "$FIX/fixture.docx" /work/in/
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
cd /work
cat > /tmp/install.lines <<'LINES'
python3 -m venv ~/.venvs/docling
source ~/.venvs/docling/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install docling
docling-tools models download
LINES
run_lines install /tmp/install.lines
all_ok install && echo "L2-1 install: every line exit 0" | tee -a "$OUT/steps.txt" || echo "L2-1 FAIL (an install line failed)" | tee -a "$OUT/steps.txt"
cd /work
python3 "$SHARED/egress.py" run --out /work/out/egress --label pdf --block-network --timeout 600 --sh 'docling /work/in/fixture.pdf --to md --output /work/out/pdf --heading-hierarchy --no-ocr --table-mode accurate' < /dev/null
echo "pdf convert exit $?" | tee -a "$OUT/steps.txt"
python3 "$SHARED/egress.py" run --out /work/out/egress --label docx --block-network --timeout 600 --sh 'docling /work/in/fixture.docx --to md --output /work/out/docx' < /dev/null
echo "docx convert exit $?" | tee -a "$OUT/steps.txt"
python3 "$SHARED/egress.py" stop --out /work/out/egress --kill > /dev/null 2>&1
python3 "$SHARED/egress.py" report --out /work/out/egress --labels pdf docx --json /work/out/egress.json > "$OUT/egress-report.txt" 2>&1
echo "egress report exit $?: $(tail -1 "$OUT/egress-report.txt")" | tee -a "$OUT/steps.txt"
ls -R /work/out/pdf /work/out/docx | tee -a "$OUT/steps.txt"
for k in pdf docx; do
  md=$(ls /work/out/$k/*.md 2>/dev/null | head -1)
  [ -n "$md" ] && cp "$md" "$OUT/fixture_$k.md" && python3 "$FIX/check_md.py" "$OUT/fixture_$k.md" --report "$OUT/$k.check.json" > "$OUT/$k.check.txt" 2>&1
  echo "$k md=[$md] check: $(tail -3 "$OUT/$k.check.txt" 2>/dev/null | tr '\n' ' ')" | tee -a "$OUT/steps.txt"
done
cp /work/out/egress/*.json /work/out/egress.json "$OUT/" 2>/dev/null
echo "== done"; cat "$OUT/steps.txt"
