#!/bin/bash
# L2 for q06 (eval/fixtures/q06/README.md section 4), run 1, experimental.
set -u
FIX=$F/q06; mkdir -p "$OUT" /work/api /work/out /work/project
cp "$FIX/openapi.json" "$FIX/openapi.yaml" /work/api/
python3 "$FIX/mock_api.py" --port 18080 --log /work/out/mock_log.jsonl --state /work/out/mock_state.json > /work/out/mock.txt 2>&1 &
sleep 2
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
cd /work/project
cat > /tmp/install.lines <<'LINES'
node --version
brew install node
LINES
run_lines install /tmp/install.lines
all_ok install && echo "L2-1: every install line exit 0" | tee -a "$OUT/steps.txt" || echo "L2-1 FAIL (an install line failed)" | tee -a "$OUT/steps.txt"
TOKEN=$(python3 -c "import secrets; print('fake-' + secrets.token_hex(16))")
python3 "$SHARED/egress.py" run --out /work/out/egress --label session --timeout 600 -- \
  python3 "$FIX/mcp_ref_client.py" --report /work/out/client.json --stdio --cwd /work/project -- npx -y @ivotoby/openapi-mcp-server --api-base-url http://127.0.0.1:18080 --openapi-spec /work/api/openapi.yaml --headers "Authorization:Bearer $TOKEN" --operation get --verbose
echo "session exit $?" | tee -a "$OUT/steps.txt"
python3 "$FIX/check_q06.py" --client-report /work/out/client.json --mock-log /work/out/mock_log.jsonl --mock-state /work/out/mock_state.json \
  --egress-dir /work/out/egress --egress-label session --report /work/out/verdict.json > "$OUT/verdict.txt" 2>&1
echo "check_q06 exit $?" | tee -a "$OUT/steps.txt"; tail -8 "$OUT/verdict.txt" | tee -a "$OUT/steps.txt"
cp /work/out/client.json /work/out/verdict.json /work/out/mock_log.jsonl "$OUT/" 2>/dev/null
sed -i "s/$TOKEN/<fake-token>/g" "$OUT"/*.json "$OUT"/*.txt 2>/dev/null
echo "== done"; cat "$OUT/steps.txt"
