#!/bin/sh
# Start the q20 user's existing Ollama exactly at its default address (no network needed):
# OLLAMA_HOST is left unset, so it listens on Ollama's own default. Checks the frozen small
# model is in the store with the pinned digest and loads it.
# Usage: STATE=/eval-work/q20/state sh start_ollama.sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/pins.env"
STATE=${STATE:-$HERE/state}
OLLAMA="$OLLAMA_PREFIX/bin/ollama"
: "${FIXTURE_MODEL:?pins.env: FIXTURE_MODEL is empty; fill it at freeze}"
mkdir -p "$STATE"
unset OLLAMA_HOST
# OLLAMA_NO_CLOUD=1: Ollama's documented local-only mode (docs.ollama.com/faq, "disabling Ollama's cloud
# features"). Without it the server connects to ollama.com:443 on its own (q18 calibration C6, 2026-10-31).
OLLAMA_NO_CLOUD=1 OLLAMA_MODELS="$OLLAMA_MODELS" OLLAMA_CONTEXT_LENGTH="$OLLAMA_CONTEXT_LENGTH" OLLAMA_KEEP_ALIVE=-1 \
  nohup "$OLLAMA" serve >>"$STATE/ollama.log" 2>&1 &
echo $! >"$STATE/ollama.pid"
python3 - "$FIXTURE_MODEL" "${FIXTURE_MODEL_DIGEST:-}" <<'EOF'
import json, sys, time, urllib.request
model, want = sys.argv[1], sys.argv[2]
base = "http://127.0.0.1:11434"
end = time.time() + 60
while True:
    try:
        urllib.request.urlopen(base + "/api/version", timeout=2).read()
        break
    except Exception:
        if time.time() > end:
            sys.exit("ollama did not come up on its default address")
        time.sleep(0.5)
tags = json.load(urllib.request.urlopen(base + "/api/tags"))["models"]
m = [t for t in tags if t.get("name") == model or t.get("model") == model]
if not m:
    sys.exit("frozen model %s is not in the model store" % model)
if want and m[0]["digest"] != want:
    sys.exit("model digest %s differs from pins.env %s" % (m[0]["digest"], want))
req = urllib.request.Request(base + "/api/generate", data=json.dumps({"model": model, "keep_alive": -1}).encode(),
                             headers={"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=600).read()
print("ollama up on its default address with", model, m[0]["digest"])
EOF
