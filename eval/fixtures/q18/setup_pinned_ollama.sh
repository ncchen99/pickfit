#!/bin/sh
# Install the pinned Ollama and pull the pinned fixture model.
# NEEDS NETWORK: run only while building the question's base image (before any answer's steps),
# never during a check. Reads pins.env next to this script and stops if a pin is empty.
# Requires: python3, tar (and unzstd if the asset is .tar.zst). Run as root.
# Not run by the fixture author (no downloads were allowed while writing the fixtures).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/pins.env"
for v in OLLAMA_VERSION OLLAMA_URL OLLAMA_SHA256 FIXTURE_MODEL OLLAMA_PREFIX OLLAMA_MODELS; do
  eval "val=\${$v:-}"
  if [ -z "$val" ]; then
    echo "pins.env: $v is empty; fill it at freeze (see calibration.md)" >&2
    exit 2
  fi
done
WORK=$(mktemp -d)
python3 - "$OLLAMA_URL" "$WORK/ollama.archive" "$OLLAMA_SHA256" <<'EOF'
import hashlib, sys, urllib.request
url, dest, want = sys.argv[1:4]
h = hashlib.sha256()
with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
    while True:
        b = r.read(1 << 20)
        if not b:
            break
        h.update(b)
        f.write(b)
got = h.hexdigest()
if got != want.strip().lower():
    sys.exit("sha256 mismatch for %s: got %s, pins.env says %s" % (url, got, want))
print("sha256 ok:", got)
EOF
case "$OLLAMA_URL" in
  *.tgz|*.tar.gz) tar -C "$OLLAMA_PREFIX" -xzf "$WORK/ollama.archive" ;;
  *.tar.zst) tar -C "$OLLAMA_PREFIX" --use-compress-program=unzstd -xf "$WORK/ollama.archive" ;;
  *) echo "unknown archive type: $OLLAMA_URL" >&2; exit 2 ;;
esac
OLLAMA="$OLLAMA_PREFIX/bin/ollama"
mkdir -p "$OLLAMA_MODELS"
# A temporary server on a side port, only for the pull.
OLLAMA_HOST=127.0.0.1:11499 OLLAMA_MODELS="$OLLAMA_MODELS" "$OLLAMA" serve >"$WORK/serve.log" 2>&1 &
PID=$!
python3 - <<'EOF'
import sys, time, urllib.request
end = time.time() + 60
while time.time() < end:
    try:
        urllib.request.urlopen("http://127.0.0.1:11499/api/version", timeout=2).read()
        sys.exit(0)
    except Exception:
        time.sleep(0.5)
sys.exit("temporary ollama server did not start")
EOF
OLLAMA_HOST=127.0.0.1:11499 "$OLLAMA" pull "$FIXTURE_MODEL"
python3 - "$FIXTURE_MODEL" "${FIXTURE_MODEL_DIGEST:-}" <<'EOF'
import json, sys, urllib.request
model, want = sys.argv[1], sys.argv[2]
v = json.load(urllib.request.urlopen("http://127.0.0.1:11499/api/version"))["version"]
tags = json.load(urllib.request.urlopen("http://127.0.0.1:11499/api/tags"))["models"]
m = [t for t in tags if t.get("name") == model or t.get("model") == model]
if not m:
    sys.exit("model %s not found after pull" % model)
d = m[0]["digest"]
print(json.dumps({"ollama_version": v, "model": model, "digest": d, "size": m[0].get("size")}))
if want and d != want:
    sys.exit("model digest %s differs from pins.env FIXTURE_MODEL_DIGEST %s" % (d, want))
EOF
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
echo "pinned Ollama and model ready (record the JSON line above in calibration.md)"
