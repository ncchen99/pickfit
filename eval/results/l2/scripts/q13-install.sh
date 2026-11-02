#!/bin/bash
# L2-1 for q13: both answers give "A. Prebuilt binary" first. The newest build release (bNNNN; /releases/latest
# points at v0.8.0, which has only nightly-tag.txt) is used. Control names `llama-<build>-bin-ubuntu-x64.zip`
# and "unzip it"; experimental names "the latest …-bin-ubuntu-x64 archive" and "extract it".
set -u
mkdir -p "$OUT"
echo "nproc $(nproc); nvidia-smi: $(command -v nvidia-smi || echo none); unzip: $(command -v unzip || echo none)" | tee -a "$OUT/steps.txt"
curl -fsSL "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=1" > /tmp/rel.json
python3 - <<'PY' | tee -a "$OUT/steps.txt"
import json; r = json.load(open('/tmp/rel.json'))[0]
print('newest build release', r['tag_name'], r['published_at'])
for a in r['assets']:
    if 'ubuntu-x64' in a['name'] and 'cuda' not in a['name'] and 'vulkan' not in a['name'] and 'rocm' not in a['name']: print('asset', a['name'])
open('/tmp/url', 'w').write(next(a['browser_download_url'] for a in r['assets'] if a['name'].endswith('-bin-ubuntu-x64.tar.gz')))
print('control: a .zip ubuntu-x64 asset exists:', any(a['name'].endswith('-bin-ubuntu-x64.zip') for a in r['assets']))
PY
URL=$(cat /tmp/url); cd /tmp && curl -fsSLO "$URL"; echo "experimental download exit $?" | tee -a "$OUT/steps.txt"
mkdir -p /opt/llama.cpp && tar -xzf "/tmp/$(basename "$URL")" -C /opt/llama.cpp; echo "experimental extract (tar) exit $?" | tee -a "$OUT/steps.txt"
S=$(find /opt/llama.cpp -name llama-server -type f | head -1); echo "llama-server at: $S" | tee -a "$OUT/steps.txt"
"$S" --version > /tmp/v.txt 2>&1; echo "llama-server --version exit $?: $(tail -1 /tmp/v.txt)" | tee -a "$OUT/steps.txt"
echo "== done"; cat "$OUT/steps.txt"
