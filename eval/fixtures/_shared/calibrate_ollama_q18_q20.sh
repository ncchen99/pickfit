#!/bin/bash
# q18 and q20 calibration again in one 8 vCPU sandbox, after q19's long-prompt time moved q18-q20
# to 8 vCPU (eval/README.md 9.3 C.4). Run through calibrate_box.py with --fixtures q18 q20 _shared pins.json.
{ echo "nproc $(nproc)"; cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us /sys/fs/cgroup/cpu/cpu.cfs_period_us 2>/dev/null
  head -1 /proc/meminfo; command -v nvidia-smi || echo "no nvidia-smi"; } | tee "$OUT/box.txt"
for q in q18 q20; do
  echo "######## $q"; bash "$F/$q/calibrate.sh"; echo "######## $q exit $?"
done
