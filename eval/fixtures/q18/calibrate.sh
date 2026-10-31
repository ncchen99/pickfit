#!/bin/bash
# q18 calibration C1-C7 (calibration.md) in a dev-image sandbox; run through calibrate_box.py
# with --fixtures q18 _shared pins.json. F, SHARED, OUT are set; results go to $OUT/q18.
set -u
Q=$F/q18; O=$OUT/q18; ST=/tmp/q18cal
mkdir -p "$O" "$ST"
. "$Q/pins.env"
echo "== C1-C2: pinned Ollama and model"
bash "$SHARED/ollama_prepare.sh" "$Q" "$O" || exit 1
echo "== C3: start, context, memory"
STATE=$ST sh "$Q/start_fixture_servers.sh" > "$O/start.txt" 2>&1 || { cat "$O/start.txt"; exit 1; }
free -m > "$O/free.txt"; grep -io "context[^ ]*[ =:]*[0-9]*\|num_ctx[^ ]*[ =:]*[0-9]*" "$ST/ollama.log" | sort | uniq -c | head > "$O/context.txt"
echo "== C4: tool call through Ollama's own API, 3 runs"
python3 "$Q/calibrate_toolcall.py" --host http://127.0.0.1:11435 --model "$FIXTURE_MODEL" --runs 3 --out "$O/toolcall.json" > "$O/c4.txt" 2>&1
echo "C4 exit $?"; tail -3 "$O/c4.txt"
echo "== C5: the same through the logging proxy"
python3 "$Q/calibrate_toolcall.py" --host http://127.0.0.1:11434 --model "$FIXTURE_MODEL" --runs 3 --out "$O/toolcall-proxy.json" > "$O/c5.txt" 2>&1
echo "C5 exit $?"; tail -3 "$O/c5.txt"
wc -l < "$ST/proxy/requests.jsonl" > "$O/proxy-requests.txt"; ls "$ST/proxy" | grep -c '\.resp$' >> "$O/proxy-requests.txt"
cat "$O/proxy-requests.txt"
STATE=$ST sh "$Q/stop_fixture_servers.sh" > /dev/null; sleep 2
echo "== C6: the fixture servers make no outbound connection (network open, traced)"
python3 "$SHARED/egress.py" run --out "$O/eg" --label fixtures --sh "STATE=$ST sh $Q/start_fixture_servers.sh" > /dev/null 2>&1
python3 "$Q/calibrate_toolcall.py" --host http://127.0.0.1:11434 --model "$FIXTURE_MODEL" --runs 1 --out "$O/c6-run.json" > /dev/null 2>&1
sleep 120
python3 "$SHARED/egress.py" stop --out "$O/eg" --kill > /dev/null 2>&1
python3 "$SHARED/egress.py" report --out "$O/eg" --json "$O/c6-egress.json" | tail -3
STATE=$ST sh "$Q/stop_fixture_servers.sh" > /dev/null 2>&1; pkill -f "ollama serve" 2>/dev/null; sleep 1
echo "== C7: selftest"
sh "$Q/selftest.sh" > "$O/selftest.txt" 2>&1; grep -E "failure" "$O/selftest.txt"
