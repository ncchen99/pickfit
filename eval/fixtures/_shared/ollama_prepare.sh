#!/bin/bash
# Shared by the q18, q19 and q20 calibration scripts: what setup_pinned_ollama.sh needs that the dev
# image lacks (unzstd for the .tar.zst asset), then the question's own setup_pinned_ollama.sh, which
# checks the archive's sha256 and pulls FIXTURE_MODEL. Also checks the pulled model layer against
# eval/fixtures/PINS.md. Usage: bash ollama_prepare.sh QUESTION_DIR OUTDIR
set -u
Q=$1; O=$2
mkdir -p "$O"
command -v unzstd > /dev/null || { apt-get update -qq > /dev/null && DEBIAN_FRONTEND=noninteractive \
  apt-get install -y -qq --no-install-recommends zstd > /dev/null; } || exit 1
dpkg-query -W zstd > "$O/zstd.txt"
. "$Q/pins.env"
sh "$Q/setup_pinned_ollama.sh" > "$O/setup.txt" 2>&1 || { tail -20 "$O/setup.txt"; exit 1; }
grep "^{" "$O/setup.txt" | tail -1 | tee "$O/model.json"   # the JSON line: version, digest, size
python3 - "$F/pins.json" "$FIXTURE_MODEL" "$OLLAMA_MODELS" <<'PY' | tee "$O/model-layer-check.txt"
import json, os, sys
pins, model, store = sys.argv[1:4]
item = {i["id"]: i for i in json.load(open(pins))["items"]}["ollama-model-" + model]
blob = os.path.join(store, "blobs", "sha256-" + item["published_sha256"])
print("model layer", item["published_sha256"][:16], "present" if os.path.exists(blob) else "MISSING", os.path.getsize(blob) if os.path.exists(blob) else "")
if os.path.exists(blob):  # hash the pulled layer here, for pins.py record-layers
    import datetime, hashlib
    h = hashlib.sha256()
    with open(blob, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    at = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec="seconds")
    print(json.dumps({"id": item["id"], "sha256": h.hexdigest(), "bytes": os.path.getsize(blob), "at": at}))
PY
grep -q present "$O/model-layer-check.txt"
