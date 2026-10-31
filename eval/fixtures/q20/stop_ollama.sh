#!/bin/sh
# Stop what start_ollama.sh started. Usage: STATE=/eval-work/q20/state sh stop_ollama.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
STATE=${STATE:-$HERE/state}
if [ -f "$STATE/ollama.pid" ]; then
  kill "$(cat "$STATE/ollama.pid")" 2>/dev/null || true
  rm -f "$STATE/ollama.pid"
fi
echo "stopped"
