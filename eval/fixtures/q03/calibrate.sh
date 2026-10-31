#!/bin/bash
# q03 calibration steps 1-4 (calibration.md) in a base-image sandbox (no python3): run through
# calibrate_box.py --variant base --fixtures q03 _shared. Step 3a runs when the sandbox has no
# memory limit, 3b when memory.max is set. POSIX tools only. F, SHARED, OUT are set.
set -u
Q=$F/q03; O=$OUT/q03
mkdir -p "$O" /work
MEM="sh $SHARED/mem_peak.sh"
echo "== step 1: base image"
{ head -2 /etc/os-release; awk -W version 2>&1 | head -1; nproc; cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null; } | tee "$O/step1.txt"
sh "$Q/check_runtime.sh" > "$O/check_runtime.out" 2> "$O/check_runtime.err"; echo "check_runtime exit $? stdout=[$(cat "$O/check_runtime.out")]"
echo "== step 2: the generator"
s=$(date +%s); sh "$Q/big/gen_big.sh" /work/big.csv > "$O/gen.txt" 2>&1; e=$(date +%s)
echo "gen exit $? seconds $((e - s))"; cat /work/big.csv.meta
sha256sum /work/big.csv /work/big.csv.expected_counts.csv | tee "$O/step2-sha.txt"
# cgroup v2 memory.max, else v1 memory.limit_in_bytes (Modal's gVisor box); a limit above 100 GB is no limit.
limit=$(cat /sys/fs/cgroup/memory.max 2>/dev/null || cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || echo NA)
if [ "$limit" = max ] || [ "$limit" = NA ] || [ "$limit" -gt 100000000000 ]; then
  echo "== step 3a: no memory limit"
  $MEM run "$O/cal-baseline_cat.json" 'cat /work/big.csv > /dev/null'; cat "$O/cal-baseline_cat.json"
else
  echo "== step 3b: hard limit $limit"
  $MEM run "$O/cal-limit_cat.json" 'cat /work/big.csv > /dev/null'; cat "$O/cal-limit_cat.json"
  { echo "limit $limit"; grep -i swap /proc/meminfo; } | tee "$O/limits.txt"
fi
echo "== step 4: wc -l reference"
$MEM run "$O/cal-ref_wc.json" 'wc -l /work/big.csv'; cat "$O/cal-ref_wc.json"
df -h /work | tail -1 | tee "$O/disk.txt"
if [ "$limit" != max ] && [ "$limit" != NA ] && [ "$limit" -le 100000000000 ]; then
  echo "== step 3b, last: a 1.5 GB allocation over the limit (expected: killed; in Modal the whole sandbox may go)"
  $MEM run "$O/cal-limit_hog.json" "awk 'BEGIN{s=\"x\"; while (length(s) < 1500000000) s = s s; print length(s)}'"
  echo "hog exit $?"; cat "$O/cal-limit_hog.json"
fi
