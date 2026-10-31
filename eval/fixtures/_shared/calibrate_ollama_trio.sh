#!/bin/bash
# q18, q19 and q20 calibration in one sandbox (the same Ollama release; each script still runs its
# own setup with its own pins.env). Run through calibrate_box.py with --fixtures q18 q19 q20 _shared pins.json.
{ echo "nproc $(nproc)"; grep -m1 "model name" /proc/cpuinfo; head -1 /proc/meminfo
  command -v nvidia-smi || echo "no nvidia-smi"; } | tee "$OUT/box.txt"
for q in q18 q19 q20; do
  echo "######## $q"; bash "$F/$q/calibrate.sh"; echo "######## $q exit $?"
  # OLLAMA_NO_CLOUD=1 in the start scripts: the server log must say so
  grep -h -o "OLLAMA_NO_CLOUD:[^ ]*\|cloud disabled[^\"]*" /tmp/${q}cal/ollama.log 2>/dev/null | sort | uniq -c | tee "$OUT/$q-cloud.txt"
done
