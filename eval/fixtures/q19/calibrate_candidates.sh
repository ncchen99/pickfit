#!/bin/bash
# q19: calibrate the next fixture-model candidates (needs.json order) after llama3.2:3b failed C4
# (calibration.md, "換候選"). Each candidate runs the unchanged calibrate.sh against a copy of q19
# whose pins.env names that model. Run through calibrate_box.py with --fixtures q19 _shared pins.json.
set -u
{ echo "nproc $(nproc)"; head -1 /proc/meminfo; } | tee "$OUT/box.txt"
for M in qwen2.5:7b qwen3:4b; do
  R=/opt/cand/$(echo "$M" | tr ':' '_')
  pkill -f "ollama serve" 2>/dev/null; sleep 2
  rm -rf "$R" /tmp/q19cal /tmp/q19runs /tmp/q19wd /opt/eval-models/ollama
  mkdir -p "$R" && cp -r "$F/q19" "$R/q19" && cp "$F/pins.json" "$R/pins.json"
  sed -i -e "s/^FIXTURE_MODEL=.*/FIXTURE_MODEL=$M/" -e "s/^FIXTURE_MODEL_DIGEST=.*/FIXTURE_MODEL_DIGEST=/" "$R/q19/pins.env"
  echo "######## q19 candidate $M"
  F=$R OUT=$OUT/$(basename "$R") bash "$R/q19/calibrate.sh"
  echo "######## q19 candidate $M exit $?"
  grep -h -o "OLLAMA_NO_CLOUD:[^ ]*\|cloud disabled[^\"]*" /tmp/q19cal/ollama.log 2>/dev/null | sort | uniq -c
done
