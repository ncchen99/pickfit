#!/bin/bash
# Probe what the Modal box's cgroup files say while a process allocates memory. F, SHARED, OUT set.
set -u
mkdir -p "$OUT/probe"
{ echo "nproc $(nproc)  cpuinfo $(grep -c ^processor /proc/cpuinfo)"
  ls /sys/fs/cgroup /sys/fs/cgroup/memory /sys/fs/cgroup/cpu 2>&1 | tr '\n' ' '; echo
  for f in /sys/fs/cgroup/cpu/cpu.cfs_quota_us /sys/fs/cgroup/cpu/cpu.cfs_period_us /sys/fs/cgroup/memory/memory.limit_in_bytes \
           /sys/fs/cgroup/memory/memory.usage_in_bytes /sys/fs/cgroup/memory/memory.max_usage_in_bytes /sys/fs/cgroup/memory/memory.stat; do
    printf '%s: %s\n' "$f" "$(head -c 400 "$f" 2>&1 | tr '\n' ' ')"; done
  head -3 /proc/meminfo
} | tee "$OUT/probe/static.txt"
python3 -c "
import time, os
b = bytearray(600 * 1024 * 1024)
for i in range(0, len(b), 4096): b[i] = 1
time.sleep(4)
" &
P=$!
for i in 1 2 3 4 5 6; do
  sleep 1
  printf 'usage %s  rss_sum %s  meminfo_used %s\n' "$(cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null)" \
    "$(cat /proc/[0-9]*/status 2>/dev/null | awk '$1=="VmRSS:"{s+=$2*1024} END{print s}')" \
    "$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{print (t-a)*1024}' /proc/meminfo)"
done | tee "$OUT/probe/during-600MB.txt"
wait $P
