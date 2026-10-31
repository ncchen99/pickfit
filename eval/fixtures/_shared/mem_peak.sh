#!/bin/sh
# The one memory measurement for the Linux L2 fixtures (q03, q14).
# POSIX sh + awk + coreutils only: q03's box has no Python on purpose.
#
#   sh mem_peak.sh run   OUT.json 'COMMAND STRING'   run one step and measure it
#   sh mem_peak.sh watch OUT.json                    sample until SIGTERM/SIGINT (a service
#                                                    measured across several steps; run it in
#                                                    the background, then `kill` it)
#   sh mem_peak.sh read  OUT.json [WATCH.json]       the counters now, plus a watch's maxima
#
# Options (environment): CGROUP_DIR (default /sys/fs/cgroup), PROC_DIR (default /proc),
# INTERVAL (sampling, default 0.2 s), and the rule: MAX_BYTES (pass when value <= MAX_BYTES)
# or BELOW_BYTES (pass when value < BELOW_BYTES). Without either, no pass/fail is written.
#
# What is recorded (bytes; null = not available in this box):
#   cgroup          v2, v1 or none
#   peak_before     memory.peak (v1: memory.max_usage_in_bytes) when the step started (run only)
#   peak_after      the same counter at the end
#   max_current     highest sampled memory.current (v1: memory.usage_in_bytes)
#   max_anon        highest sampled anon (v1: rss) from memory.stat: memory the processes
#                   allocated, without the page cache of files they read
#   max_rss_sum     highest sampled sum of VmRSS over every process in PROC_DIR
#   limit           memory.max (v1: memory.limit_in_bytes)
#   oom_kills       oom_kill events during the step (run) or in total (read)
#   exit_code, wall_seconds (run only); the step's stdout goes to OUT.json.stdout
#
# The value judged ("value", "method"), in this order:
#   1. peak_after, the kernel's own peak counter, when it exists and, for `run`, peak_before
#      is below the threshold (a counter already over the line before the step says nothing
#      about the step: use a fresh box);
#   2. max_current, sampled;
#   3. max_rss_sum, sampled.
# result = pass when the value is within the rule and oom_kills is 0 (or null), fail
# otherwise, undetermined when no value exists. Whether page cache counts (memory.peak
# includes it) is decided per question in its calibration.md; max_anon is always recorded
# so that decision can be made from the same log.
#
# Exit status: run = the step's exit status; watch = 0; read = 0 pass, 1 fail, 2 undetermined
# or no rule given.
set -u
cg=${CGROUP_DIR:-/sys/fs/cgroup}
proc=${PROC_DIR:-/proc}
interval=${INTERVAL:-0.2}

if [ -r "$cg/memory.current" ] || [ -r "$cg/memory.peak" ]; then
  kind=v2; f_peak=$cg/memory.peak; f_cur=$cg/memory.current; f_lim=$cg/memory.max
  f_stat=$cg/memory.stat; anon_key=anon; f_ev=$cg/memory.events
elif [ -r "$cg/memory/memory.usage_in_bytes" ]; then
  kind=v1; f_peak=$cg/memory/memory.max_usage_in_bytes; f_cur=$cg/memory/memory.usage_in_bytes
  f_lim=$cg/memory/memory.limit_in_bytes; f_stat=$cg/memory/memory.stat; anon_key=rss
  f_ev=$cg/memory/memory.oom_control
else
  kind=none; f_peak=; f_cur=; f_lim=; f_stat=; anon_key=; f_ev=
fi

num() {  # a file's first number, or null ("max" and missing files are null)
  if [ -n "$1" ] && [ -r "$1" ]; then
    awk 'NR==1 && $1 ~ /^[0-9]+$/ {print $1; found=1} END{if(!found) print "null"}' "$1" 2>/dev/null || echo null
  else
    echo null
  fi
}
key() {  # value of a "key value" line in a file, or null
  if [ -n "$1" ] && [ -r "$1" ]; then
    awk -v k="$2" '$1==k {print $2; found=1} END{if(!found) print "null"}' "$1" 2>/dev/null || echo null
  else
    echo null
  fi
}
rss_sum() {
  cat "$proc"/[0-9]*/status 2>/dev/null | awk '$1=="VmRSS:"{s+=$2*1024} END{printf "%d\n", s+0}'
}
now() { d=$(date +%s.%N); case $d in *N*) date +%s ;; *) echo "$d" ;; esac; }

sample_loop() {  # appends "current anon rss_sum" lines to $1 until killed
  while :; do
    printf '%s %s %s\n' "$(num "$f_cur")" "$(key "$f_stat" "$anon_key")" "$(rss_sum)" >> "$1"
    sleep "$interval"
  done
}
col_max() {  # max of column $2 in file $1, or null
  awk -v c="$2" '$c!="null" && ($c+0>m || !seen) {m=$c+0; seen=1} END{if(seen) printf "%d\n", m; else print "null"}' "$1"
}
jmax() {  # max of two JSON numbers that may be null
  if [ "$1" = null ]; then echo "$2"; elif [ "$2" = null ]; then echo "$1";
  elif [ "$1" -ge "$2" ]; then echo "$1"; else echo "$2"; fi
}

within() {  # is $1 within the rule? (true when no rule is given)
  if [ -n "${MAX_BYTES:-}" ]; then [ "$1" -le "$MAX_BYTES" ]
  elif [ -n "${BELOW_BYTES:-}" ]; then [ "$1" -lt "$BELOW_BYTES" ]
  else true; fi
}
decide() {  # args: peak_before peak_after max_current max_rss_sum oom_kills -> sets method value result
  pb=$1; pa=$2; mc=$3; mr=$4; oom=$5
  method=null; value=null
  if [ "$pa" != null ] && { [ "$pb" = null ] || within "$pb"; }; then
    method='"peak counter"'; value=$pa
  elif [ "$mc" != null ]; then
    method='"sampled memory.current"'; value=$mc
  elif [ "$mr" != null ] && [ "$mr" -gt 0 ]; then
    method='"sampled RSS sum"'; value=$mr
  fi
  if [ "$value" = null ] || { [ -z "${MAX_BYTES:-}" ] && [ -z "${BELOW_BYTES:-}" ]; }; then
    result=undetermined
  elif within "$value" && { [ "$oom" = null ] || [ "$oom" -eq 0 ]; }; then
    result=pass
  else
    result=fail
  fi
}
rule_json() {
  if [ -n "${MAX_BYTES:-}" ]; then printf '"value <= %s and no OOM kill"' "$MAX_BYTES"
  elif [ -n "${BELOW_BYTES:-}" ]; then printf '"value < %s and no OOM kill"' "$BELOW_BYTES"
  else printf null; fi
}
json_str() { printf '%s' "$1" | awk 'BEGIN{ORS=""; print "\""} {gsub(/\\/,"\\\\"); gsub(/"/,"\\\""); gsub(/\t/,"\\t"); if (NR>1) print "\\n"; print} END{print "\""}'; }

mode=${1:-}
out=${2:-}
[ -n "$mode" ] && [ -n "$out" ] || { sed -n '2,13p' "$0" >&2; exit 2; }

case $mode in
run)
  [ $# -eq 3 ] || { echo "usage: mem_peak.sh run OUT.json 'COMMAND STRING'" >&2; exit 2; }
  cmd=$3
  samples=$out.samples
  : > "$samples"
  sample_loop "$samples" &
  sampler=$!
  pb=$(num "$f_peak"); ob=$(key "$f_ev" oom_kill)
  t0=$(now)
  sh -c "$cmd" > "$out.stdout"
  rc=$?
  t1=$(now)
  kill "$sampler" 2>/dev/null; wait "$sampler" 2>/dev/null
  printf '%s %s %s\n' "$(num "$f_cur")" "$(key "$f_stat" "$anon_key")" "$(rss_sum)" >> "$samples"
  pa=$(num "$f_peak"); oa=$(key "$f_ev" oom_kill)
  if [ "$ob" = null ] || [ "$oa" = null ]; then oom=null; else oom=$((oa - ob)); fi
  mc=$(col_max "$samples" 1); ma=$(col_max "$samples" 2); mr=$(col_max "$samples" 3)
  decide "$pb" "$pa" "$mc" "$mr" "$oom"
  wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.3f", b-a}')
  cat > "$out" <<EOF
{"tool": "mem_peak.sh run", "command": $(json_str "$cmd"), "exit_code": $rc, "wall_seconds": $wall,
 "cgroup": "$kind", "peak_before": $pb, "peak_after": $pa, "max_current": $mc, "max_anon": $ma,
 "max_rss_sum": $mr, "limit": $(num "$f_lim"), "oom_kills": $oom,
 "rule": $(rule_json), "method": $method, "value": $value, "result": "$result"}
EOF
  printf 'mem_peak: exit=%s wall=%ss value=%s (%s) oom_kills=%s result=%s\n' "$rc" "$wall" "$value" \
    "$method" "$oom" "$result" >&2
  exit "$rc"
  ;;
watch)
  samples=$out.samples
  : > "$samples"
  trap 'stop=1' TERM INT
  stop=0
  while [ "$stop" = 0 ]; do
    printf '%s %s %s\n' "$(num "$f_cur")" "$(key "$f_stat" "$anon_key")" "$(rss_sum)" >> "$samples"
    sleep "$interval" &
    wait $! 2>/dev/null
  done
  cat > "$out" <<EOF
{"tool": "mem_peak.sh watch", "cgroup": "$kind", "samples": $(wc -l < "$samples" | tr -d ' '),
 "max_current": $(col_max "$samples" 1), "max_anon": $(col_max "$samples" 2), "max_rss_sum": $(col_max "$samples" 3)}
EOF
  exit 0
  ;;
read)
  watch=${3:-}
  wc_=null; wa=null; wr=null
  if [ -n "$watch" ] && [ -r "$watch" ]; then
    wc_=$(awk -F'"max_current": ' 'NF>1{split($2,a,/[,}]/); print a[1]}' "$watch")
    wa=$(awk -F'"max_anon": ' 'NF>1{split($2,a,/[,}]/); print a[1]}' "$watch")
    wr=$(awk -F'"max_rss_sum": ' 'NF>1{split($2,a,/[,}]/); print a[1]}' "$watch")
  fi
  cur=$(num "$f_cur"); anon=$(key "$f_stat" "$anon_key"); rss=$(rss_sum)
  mc=$(jmax "$wc_" "$cur"); ma=$(jmax "$wa" "$anon"); mr=$(jmax "$wr" "$rss")
  pa=$(num "$f_peak"); oom=$(key "$f_ev" oom_kill)
  decide null "$pa" "$mc" "$mr" "$oom"
  cat > "$out" <<EOF
{"tool": "mem_peak.sh read", "cgroup": "$kind", "peak_after": $pa, "max_current": $mc, "max_anon": $ma,
 "max_rss_sum": $mr, "limit": $(num "$f_lim"), "oom_kills": $oom, "watch": $(if [ -n "$watch" ]; then json_str "$watch"; else printf null; fi),
 "rule": $(rule_json), "method": $method, "value": $value, "result": "$result"}
EOF
  cat "$out"
  case $result in pass) exit 0 ;; fail) exit 1 ;; *) exit 2 ;; esac
  ;;
*)
  sed -n '2,13p' "$0" >&2
  exit 2
  ;;
esac
