#!/bin/sh
# q08 checks for L2-2 and L2-3: run in the eval account's Terminal AFTER the answer's install
# (and first-run) steps. The two checked commands are typed exactly as in the checklist.
#
#   sh /Users/Shared/q08-fixture/checks.sh [OUTDIR]      (default OUTDIR: ~/q08-run)
#
# Writes everything to OUTDIR/checks.log and prints one verdict line per item.

here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$HOME/q08-run"}
mkdir -p "$out"
log="$out/checks.log"
note() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$log"; }

note "q08 checks start, user=$(id -un)"
note "docker on PATH: $(command -v docker || echo none)"
[ -n "$(command -v docker)" ] && note "docker resolves to: $(readlink "$(command -v docker)" || echo '<not a symlink>')"
note "DOCKER_HOST=${DOCKER_HOST-<unset>} DOCKER_CONTEXT=${DOCKER_CONTEXT-<unset>}"
note "docker context show: $(docker context show 2>&1)"
docker context ls >> "$log" 2>&1
docker version >> "$log" 2>&1
docker compose version >> "$log" 2>&1
pgrep -lf '/Applications/Docker.app/|com.docker.backend' >> "$log" 2>&1 && note "WARNING: Docker Desktop process seen"

# ---- L2-2 ----------------------------------------------------------------------------
note '$ docker run --rm hello-world'
docker run --rm hello-world > "$out/hello.txt" 2>&1
r_run=$?
cat "$out/hello.txt" >> "$log"
note "exit=$r_run"
grep -q 'Hello from Docker!' "$out/hello.txt"
r_msg=$?
note "\$ docker image inspect hello-world --format '{{.Architecture}}'"
arch=$(docker image inspect hello-world --format '{{.Architecture}}' 2>> "$log")
note "printed: $arch"
docker image inspect hello-world --format '{{.Id}} {{.Os}}/{{.Architecture}} {{.RepoDigests}}' >> "$log" 2>&1
if [ $r_run -eq 0 ] && [ $r_msg -eq 0 ] && [ "$arch" = arm64 ]; then l22=PASS; else l22=FAIL; fi

# ---- L2-3 ----------------------------------------------------------------------------
proj="$HOME/q08-compose"
mkdir -p "$proj"
cp "$here/compose.yaml" "$proj/compose.yaml"
cd "$proj" || exit 1
busy=""
for h in 127.0.0.1 ::1; do
  nc -z -G 2 "$h" 8080 >/dev/null 2>&1 && busy="$busy $h"
done
if [ -n "$busy" ]; then
  note "INVALID: something already listens on port 8080 ($busy) before compose up; free it and rerun"
  note "L2-2 (hello-world runs, arm64): $l22"
  note "L2-3: not judged (port 8080 busy before the check)"
  exit 2
fi
note '$ docker compose up -d'
docker compose up -d >> "$log" 2>&1
r_up=$?
note "exit=$r_up"
web=$(docker inspect -f '{{.State.Running}}' q08-web 2>> "$log")
cache=$(docker inspect -f '{{.State.Running}}' q08-cache 2>> "$log")
note "running: web=$web cache=$cache"
code=000
i=0
while [ $i -lt 30 ]; do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080)
  [ "$code" = 200 ] && break
  i=$((i + 1))
  sleep 2
done
note "\$ curl -s -o /dev/null -w '%{http_code}' http://localhost:8080  -> $code (attempt $((i + 1)) of at most 30, 2 s apart)"
note "response Server header (evidence only): $(curl -s -I http://localhost:8080 | grep -i '^server:' | tr -d '\r')"
if [ $r_up -eq 0 ] && [ "$web" = true ] && [ "$cache" = true ] && [ "$code" = 200 ]; then l23=PASS; else l23=FAIL; fi

note '$ docker compose down'
docker compose down >> "$log" 2>&1

note "L2-2 (hello-world runs, arm64): $l22"
note "L2-3 (compose up, both running, host curl 200): $l23"
note "L2-1 and L2-4 are judged by the person running this (run-log-template.md)"
