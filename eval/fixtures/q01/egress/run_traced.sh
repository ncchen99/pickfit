#!/bin/sh
# Egress check, step 1 of 2: run one command string under strace and keep the
# trace. Step 2 is egress_check.py, which reads the trace.
#
#   sh run_traced.sh TRACE_LOG 'COMMAND STRING'
#
# The command string runs in `sh -c` exactly as the answer gives it (after the
# grader fills in placeholders). Every process it starts, including daemons it
# leaves behind, is traced for execve, connect, sendto, sendmsg and sendmmsg.
# Exit status: the command's own exit status; 125 when strace is missing.
#
# A daemon the command leaves running (for example a key agent) would keep
# strace waiting forever, so once the command itself has exited the tracer is
# given one second and then detached with SIGTERM (the daemon keeps running,
# untraced, and the trace file is complete for the step).
#
# POSIX sh; needs strace (Ubuntu package "strace", see needs.json).
set -u
if [ $# -ne 2 ]; then
  echo "usage: run_traced.sh TRACE_LOG 'COMMAND STRING'" >&2
  exit 2
fi
log=$1
cmd=$2
STRACE=${STRACE:-strace}
if ! command -v "$STRACE" >/dev/null 2>&1; then
  echo "run_traced: strace not found" >&2
  exit 125
fi
rcfile=$log.rc
rm -f "$log" "$rcfile"
# Keep the caller's stdin for the command (a background job would get /dev/null).
exec 3<&0
"$STRACE" -f -qq -s 64 -e trace=execve,connect,sendto,sendmsg,sendmmsg -o "$log" \
  sh -c 'sh -c "$1"; echo $? > "$2"' run_traced "$cmd" "$rcfile" 0<&3 &
spid=$!
exec 3<&-
while [ ! -s "$rcfile" ] && kill -0 "$spid" 2>/dev/null; do
  sleep 1
done
sleep 1
if kill -0 "$spid" 2>/dev/null; then
  kill -TERM "$spid" 2>/dev/null
fi
wait "$spid" 2>/dev/null
if [ -s "$rcfile" ]; then
  rc=$(cat "$rcfile")
else
  echo "run_traced: command exit status not recorded" >&2
  rc=125
fi
exit "$rc"
