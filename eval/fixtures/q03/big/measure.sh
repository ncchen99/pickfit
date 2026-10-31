#!/bin/sh
# Time and memory wrapper for q03 L2 item 3 (runs inside the q03 sandbox).
#
#   sh measure.sh RESULT_TSV LABEL 'COMMAND STRING'
#
# Runs the command string with `sh -c` exactly as the answer gives it (after
# placeholders are filled), and appends one tab-separated line to RESULT_TSV:
#
#   label exit_code wall_seconds peak_before peak_after max_current max_anon oom_kills
#
#   peak_before / peak_after  /sys/fs/cgroup/memory.peak before and after (bytes)
#   max_current               highest sampled /sys/fs/cgroup/memory.current
#   max_anon                  highest sampled "anon" line of memory.stat
#   oom_kills                 increase of oom_kill in memory.events during the command
# Samples are taken every 0.2 s. "NA" means the file is not available in this
# sandbox (calibration.md decides which number the pass rule uses).
#
# The command's stdout goes to RESULT_TSV.LABEL.out (for check_outputs.py);
# stderr is passed through. Exit status: the command's own.
# POSIX sh + awk + GNU date (Ubuntu base image); no Python.
set -u
if [ $# -ne 3 ]; then
  echo "usage: measure.sh RESULT_TSV LABEL 'COMMAND STRING'" >&2
  exit 2
fi
res=$1
label=$2
cmd=$3
cg=${CGROUP_DIR:-/sys/fs/cgroup}
samples=$res.$label.samples

rd() { if [ -r "$1" ]; then cat "$1" 2>/dev/null || echo NA; else echo NA; fi; }
anon() { if [ -r "$cg/memory.stat" ]; then awk '$1=="anon"{print $2}' "$cg/memory.stat"; else echo NA; fi; }
now() { d=$(date +%s.%N); case $d in *N*) date +%s ;; *) echo "$d" ;; esac; }
ooms() { if [ -r "$cg/memory.events" ]; then awk '$1=="oom_kill"{print $2}' "$cg/memory.events"; else echo NA; fi; }

: > "$samples"
(
  while :; do
    printf '%s\t%s\n' "$(rd "$cg/memory.current")" "$(anon)" >> "$samples"
    sleep 0.2
  done
) &
sampler=$!

peak_before=$(rd "$cg/memory.peak")
oom_before=$(ooms)
t0=$(now)
sh -c "$cmd" > "$res.$label.out"
rc=$?
t1=$(now)
peak_after=$(rd "$cg/memory.peak")
oom_after=$(ooms)
kill "$sampler" 2>/dev/null
wait "$sampler" 2>/dev/null
printf '%s\t%s\n' "$(rd "$cg/memory.current")" "$(anon)" >> "$samples"

max_current=$(awk -F'\t' '$1!="NA" && $1+0>m{m=$1+0} END{if(m=="")print "NA"; else printf "%d", m}' "$samples")
max_anon=$(awk -F'\t' '$2!="NA" && $2+0>m{m=$2+0} END{if(m=="")print "NA"; else printf "%d", m}' "$samples")
wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.3f", b-a}')
case "$oom_before$oom_after" in *NA*) oom=NA ;; *) oom=$((oom_after - oom_before)) ;; esac
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$label" "$rc" "$wall" "$peak_before" "$peak_after" \
  "$max_current" "$max_anon" "$oom" >> "$res"
printf 'measure: %s exit=%s wall=%ss peak_after=%s max_anon=%s oom_kills=%s\n' "$label" "$rc" \
  "$wall" "$peak_after" "$max_anon" "$oom" >&2
exit "$rc"
