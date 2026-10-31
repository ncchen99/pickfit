#!/bin/sh
# Start the q19 fixture "self-hosted model server" (no network needed):
#   - the pinned Ollama on 127.0.0.1:11435 with the frozen fixture model loaded (not used directly);
#   - the logging proxy on 127.0.0.1:$PROXY_PORT (default 8000), relaying to it.
# The answer's placeholder base URL is filled with http://127.0.0.1:$PROXY_PORT/v1, so every
# request the agent sends is logged in $STATE/proxy (the "local server's log" of the checklist).
# Nothing listens on Ollama's default port 11434, so traffic that bypasses the configured URL fails.
# Usage: STATE=/eval-work/q19/state sh start_fixture_servers.sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/pins.env"
STATE=${STATE:-$HERE/state}
OLLAMA="$OLLAMA_PREFIX/bin/ollama"
: "${FIXTURE_MODEL:?pins.env: FIXTURE_MODEL is empty; fill it at freeze}"
PROXY_PORT=${PROXY_PORT:-8000}
mkdir -p "$STATE/proxy"

wait_http() {
  python3 - "$1" "${2:-60}" <<'EOF'
import sys, time, urllib.request
url, t = sys.argv[1], float(sys.argv[2])
end = time.time() + t
while time.time() < end:
    try:
        urllib.request.urlopen(url, timeout=2).read()
        sys.exit(0)
    except Exception:
        time.sleep(0.5)
sys.exit("timeout waiting for " + url)
EOF
}

OLLAMA_HOST=127.0.0.1:11435 OLLAMA_MODELS="$OLLAMA_MODELS" OLLAMA_CONTEXT_LENGTH="$OLLAMA_CONTEXT_LENGTH" \
  OLLAMA_KEEP_ALIVE=-1 nohup "$OLLAMA" serve >>"$STATE/ollama.log" 2>&1 &
echo $! >"$STATE/ollama.pid"
wait_http http://127.0.0.1:11435/api/version 60

python3 - "$FIXTURE_MODEL" "${FIXTURE_MODEL_DIGEST:-}" <<'EOF'
import json, sys, urllib.request
model, want = sys.argv[1], sys.argv[2]
tags = json.load(urllib.request.urlopen("http://127.0.0.1:11435/api/tags"))["models"]
m = [t for t in tags if t.get("name") == model or t.get("model") == model]
if not m:
    sys.exit("fixture model %s is not in the model store" % model)
if want and m[0]["digest"] != want:
    sys.exit("fixture model digest %s differs from pins.env %s" % (m[0]["digest"], want))
req = urllib.request.Request("http://127.0.0.1:11435/api/generate",
                             data=json.dumps({"model": model, "keep_alive": -1}).encode(),
                             headers={"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=600).read()
print("fixture model loaded:", model, m[0]["digest"])
EOF

nohup python3 "$HERE/tools/logging_proxy.py" --listen "127.0.0.1:$PROXY_PORT" --listen "[::1]:$PROXY_PORT" \
  --upstream 127.0.0.1:11435 --log-dir "$STATE/proxy" >>"$STATE/proxy.stderr" 2>&1 &
echo $! >"$STATE/proxy.pid"
wait_http "http://127.0.0.1:$PROXY_PORT/v1/models" 30
echo "q19 fixture server up: base URL http://127.0.0.1:$PROXY_PORT/v1 (model $FIXTURE_MODEL), logs in $STATE"
