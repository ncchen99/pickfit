#!/bin/bash
# _shared/calibration.md step 4 for one sandbox shape: which cgroup memory counters exist. F, SHARED, OUT set.
set -u
mkdir -p "$OUT/cgroup"
ls /sys/fs/cgroup/ | tr '\n' ' ' > "$OUT/cgroup/files.txt"; echo >> "$OUT/cgroup/files.txt"
for f in memory.max memory.peak memory.current memory.swap.max memory.events; do printf '%s: %s\n' "$f" "$(cat /sys/fs/cgroup/$f 2>&1 | tr '\n' ' ')"; done | tee "$OUT/cgroup/counters.txt"
nproc | tee -a "$OUT/cgroup/counters.txt"
sh "$SHARED/mem_peak.sh" read "$OUT/cgroup/read.json"
