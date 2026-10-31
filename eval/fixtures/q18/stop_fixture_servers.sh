#!/bin/sh
# Stop what start_fixture_servers.sh started. Usage: STATE=/eval-work/q18/state sh stop_fixture_servers.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
STATE=${STATE:-$HERE/state}
for name in proxy ollama; do
  if [ -f "$STATE/$name.pid" ]; then
    kill "$(cat "$STATE/$name.pid")" 2>/dev/null || true
    rm -f "$STATE/$name.pid"
  fi
done
echo "stopped"
