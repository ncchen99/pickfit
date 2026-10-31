#!/bin/bash
# q20 calibration C1-C7 (calibration.md) in a dev-image sandbox; run through calibrate_box.py
# with --fixtures q20 _shared pins.json. F, SHARED, OUT are set; results go to $OUT/q20.
set -u
Q=$F/q20; O=$OUT/q20; ST=/tmp/q20cal
mkdir -p "$O" "$ST/ref"
. "$Q/pins.env"
echo "== C1-C2: pinned Ollama, model, the user's venv with openai"
bash "$SHARED/ollama_prepare.sh" "$Q" "$O" || exit 1
# The user's existing Python environment needs venv support, which the minimal image lacks.
# (dpkg-query -W also succeeds for a package dpkg knows but has not installed, so check the status.)
installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "install ok installed"; }
installed python3-venv || { apt-get update -qq > /dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  --no-install-recommends python3-venv > /dev/null; } || exit 1
dpkg-query -W python3-venv python3.12-venv > "$O/python3-venv.txt"
STATE=$ST sh "$Q/setup_user_env.sh" > "$O/venv.txt" 2>&1 || { tail -5 "$O/venv.txt"; exit 1; }
cp "$ST/pip-freeze.txt" "$O/"; grep -i "^openai" "$O/pip-freeze.txt"
useradd -m dev 2>/dev/null; cp "$Q/script/ask.py" /home/dev/ask.py
echo "== C3: the default address in use (OLLAMA_HOST unset)"
STATE=$ST sh "$Q/start_ollama.sh" > "$O/start.txt" 2>&1 || { cat "$O/start.txt"; exit 1; }
grep -o "Listening on [^ ]*" "$ST/ollama.log" | tail -1 | tee "$O/listening.txt"
echo "== C4: reference setting, network open"
sed -e 's|client = OpenAI()|client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")|' \
    -e "s|model=\"gpt-4o-mini\"|model=\"$FIXTURE_MODEL\"|" "$Q/script/ask.py" > "$ST/ref/ask.py"
python3 "$Q/check_script_diff.py" "$Q/script/ask.py" "$ST/ref/ask.py" > "$O/c4-diff.json"; echo "diff exit $?"
python3 "$Q/check_base_url.py" http://localhost:11434/v1 > "$O/c4-base-url.txt" 2>&1; echo "base_url exit $?"
python3 "$Q/run_ask.py" --script "$ST/ref/ask.py" --python "$VENV/bin/python" --out "$O/ref-online"; echo "run_ask exit $?"
pkill -f "ollama serve"; sleep 2
echo "== C5: reference setting, network blocked (Ollama and the call in one namespace)"
cat > "$ST/blocked.sh" <<SH
set -u
python3 $SHARED/egress.py probe --json $O/c5-probe.json > /dev/null || { echo "probe: not blocked"; exit 3; }
STATE=$ST sh $Q/start_ollama.sh > $O/c5-start.txt 2>&1 || exit 4
python3 $Q/run_ask.py --script $ST/ref/ask.py --python $VENV/bin/python --out $O/ref-blocked
SH
python3 "$SHARED/egress.py" run --out "$O/eg" --label blocked --block-network --kill-leftovers --sh "bash $ST/blocked.sh"
echo "blocked run exit $?"
# Only the call's window counts (README L2-3): the probe's own attempts come before it.
W0=$(python3 -c "import json; print(json.load(open('$O/ref-blocked.json'))['start'])")
W1=$(python3 -c "import json; print(json.load(open('$O/ref-blocked.json'))['end'])")
python3 "$SHARED/egress.py" report --out "$O/eg" --json "$O/c5-egress-all.json" | tail -1
python3 "$SHARED/egress.py" report --out "$O/eg" --since "$W0" --until "$W1" --json "$O/c5-egress.json" | tail -2
echo "== C6: no key (only the model name changed)"
STATE=$ST sh "$Q/start_ollama.sh" > /dev/null 2>&1
mkdir -p "$ST/nokey" && sed -e "s|model=\"gpt-4o-mini\"|model=\"$FIXTURE_MODEL\"|" "$Q/script/ask.py" > "$ST/nokey/ask.py"
python3 "$Q/run_ask.py" --script "$ST/nokey/ask.py" --python "$VENV/bin/python" --env OPENAI_BASE_URL=http://localhost:11434/v1 --out "$O/nokey"
echo "nokey exit $?"; python3 -c "import json; print(json.load(open('$O/nokey.json'))['stderr_tail'][-300:])"
pkill -f "ollama serve"; sleep 1
echo "== C7: selftest with the real openai package"
Q20_OPENAI_PYTHON=$VENV/bin/python sh "$Q/selftest.sh" > "$O/selftest.txt" 2>&1; grep -E "failure|skip" "$O/selftest.txt"
echo "== OLLAMA_NO_CLOUD in the server log"
grep -h -o "OLLAMA_NO_CLOUD:[^ ]*\|cloud disabled[^\"]*" "$ST/ollama.log" 2>/dev/null | sort | uniq -c | tee "$O/cloud.txt"
