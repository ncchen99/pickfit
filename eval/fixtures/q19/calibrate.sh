#!/bin/bash
# q19 calibration C1-C9 (calibration.md) in a dev-image sandbox; run through calibrate_box.py
# with --fixtures q19 _shared pins.json. F, SHARED, OUT are set; results go to $OUT/q19.
set -u
Q=$F/q19; O=$OUT/q19; ST=/tmp/q19cal
mkdir -p "$O" "$ST"
. "$Q/pins.env"
echo "== C1-C2: pinned Ollama and model"
bash "$SHARED/ollama_prepare.sh" "$Q" "$O" || exit 1
echo "== C3: start (context $OLLAMA_CONTEXT_LENGTH), memory"
STATE=$ST sh "$Q/start_fixture_servers.sh" > "$O/start.txt" 2>&1 || { cat "$O/start.txt"; exit 1; }
free -m > "$O/free.txt"
echo "== C4-C5: reference harness, 3 runs, with a 16k-token prefill probe"
python3 "$Q/reference_harness.py" --base-url "http://127.0.0.1:${PROXY_PORT:-8000}/v1" --model "$FIXTURE_MODEL" --runs 3 \
  --probe-prefill 16000 --out "$O/harness.json" > "$O/c4.txt" 2>&1
echo "C4 exit $?"; tail -5 "$O/c4.txt"
free -m > "$O/free-after.txt"
echo "== C6: proxy log"
cp "$ST/proxy/requests.jsonl" "$O/proxy-requests.jsonl" 2>/dev/null; wc -l < "$O/proxy-requests.jsonl"
STATE=$ST sh "$Q/stop_fixture_servers.sh" > /dev/null; sleep 2
echo "== C7: the fixture servers make no outbound connection (network open, traced)"
python3 "$SHARED/egress.py" run --out "$O/eg" --label fixtures --sh "STATE=$ST sh $Q/start_fixture_servers.sh" > /dev/null 2>&1
python3 "$Q/reference_harness.py" --base-url "http://127.0.0.1:${PROXY_PORT:-8000}/v1" --model "$FIXTURE_MODEL" --runs 1 --out "$O/c7-run.json" > /dev/null 2>&1
sleep 120
python3 "$SHARED/egress.py" stop --out "$O/eg" --kill > /dev/null 2>&1
python3 "$SHARED/egress.py" report --out "$O/eg" --json "$O/c7-egress.json" | tail -3
STATE=$ST sh "$Q/stop_fixture_servers.sh" > /dev/null 2>&1; pkill -f "ollama serve" 2>/dev/null; sleep 1
echo "== C8: work folder"
python3 "$Q/new_run.py" --runs-dir /tmp/q19runs --label c --workdir /tmp/q19wd > "$O/c8.txt" 2>&1; cat /tmp/q19runs/c/run.json > "$O/c8-run.json" 2>/dev/null
python3 -c "import json; r=json.load(open('$O/c8-run.json')); print('git', r.get('git'), 'head', r.get('head'))"
echo "== C9: selftest"
sh "$Q/selftest.sh" > "$O/selftest.txt" 2>&1; grep -E "failure" "$O/selftest.txt"
