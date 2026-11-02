#!/bin/bash
# L2 for q20 (eval/fixtures/q20/README.md section 2), run 1, experimental. Environment = calibration C1-C2 (pinned
# Ollama + frozen small model, the user's venv with pinned openai, /home/dev/ask.py). The answer's main way:
# OPENAI_BASE_URL=http://localhost:11434/v1 and OPENAI_API_KEY=ollama as environment variables, the model name
# replaced in the script; its model is the placeholder for FIXTURE_MODEL (9.3 C). L2-3 runs in the same box with
# Ollama stopped first and a fresh --block-network namespace (as calibration C5 did), not a snapshot copy.
set -u
Q=$F/q20; O=$OUT; W=/eval-work/q20; mkdir -p "$O" "$W/runs" "$W/state"
. "$Q/pins.env"
bash "$SHARED/ollama_prepare.sh" "$Q" "$O" > "$O/env-ollama.txt" 2>&1 || { tail -5 "$O/env-ollama.txt"; exit 1; }
apt-get update -qq > /dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends python3-venv > /dev/null || exit 1
STATE=$W/state sh "$Q/setup_user_env.sh" > "$O/env-venv.txt" 2>&1 || { tail -5 "$O/env-venv.txt"; exit 1; }
useradd -m dev 2>/dev/null; cp "$Q/script/ask.py" /home/dev/ask.py
echo "== L2-1"; python3 "$Q/check_base_url.py" "http://localhost:11434/v1" > "$O/l2-1.txt" 2>&1; echo "L2-1 check_base_url exit $?" | tee -a "$O/steps.txt"
echo "== L2-2"
STATE=$W/state sh "$Q/start_ollama.sh" > "$O/start-online.txt" 2>&1; echo "start ollama exit $?" | tee -a "$O/steps.txt"
sed -e "s|model=\"gpt-4o-mini\"|model=\"$FIXTURE_MODEL\"|" /home/dev/ask.py > "$W/ask.py"
python3 "$Q/check_script_diff.py" /home/dev/ask.py "$W/ask.py" > "$O/diff.json"; echo "check_script_diff exit $?" | tee -a "$O/steps.txt"
python3 "$Q/run_ask.py" --script "$W/ask.py" --python "$VENV/bin/python" --env OPENAI_BASE_URL=http://localhost:11434/v1 \
  --env OPENAI_API_KEY=ollama --out "$W/runs/online"; echo "run_ask online exit $?" | tee -a "$O/steps.txt"
pkill -f "ollama serve"; sleep 2
echo "== L2-3"
cat > "$W/blocked.sh" <<SH
set -u
python3 $SHARED/egress.py probe --json $W/runs/probe.json > /dev/null || { echo "probe: not blocked"; exit 3; }
STATE=$W/state sh $Q/start_ollama.sh > $O/start-blocked.txt 2>&1 || exit 4
python3 $Q/run_ask.py --script $W/ask.py --python $VENV/bin/python --env OPENAI_BASE_URL=http://localhost:11434/v1 --env OPENAI_API_KEY=ollama --out $W/runs/blocked
SH
python3 "$SHARED/egress.py" run --out "$W/egress" --label blocked --block-network --kill-leftovers --sh "bash $W/blocked.sh"
echo "blocked run exit $?" | tee -a "$O/steps.txt"
W0=$(python3 -c "import json; print(json.load(open('$W/runs/blocked.json'))['start'])")
W1=$(python3 -c "import json; print(json.load(open('$W/runs/blocked.json'))['end'])")
python3 "$SHARED/egress.py" report --out "$W/egress" --since "$W0" --until "$W1" --json "$W/runs/egress-report.json"; echo "egress report exit $?" | tee -a "$O/steps.txt"
cp "$W"/runs/*.json "$O/"
for r in online blocked; do python3 -c "import json; d=json.load(open('$W/runs/$r.json')); print('$r pass', d.get('pass'), 'exit', d.get('exit_code'), repr((d.get('stdout') or '')[:120]))" | tee -a "$O/steps.txt"; done
python3 -c "import json; print('egress', json.load(open('$W/runs/egress-report.json')).get('result'))" | tee -a "$O/steps.txt"
echo "== done"; cat "$O/steps.txt"
