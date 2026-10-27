#!/usr/bin/env bash
# Spike：量本機 Docker（runc）與 gVisor（runsc）的啟動時間，當作雲端沙盒的對照基準。
#
# 驗證什麼：
#   1. `docker run --rm <image> true` 從呼叫到結束要幾秒（runc，預設網路與 --network none）。
#   2. 若有 runsc：`runsc --network=none do python3 -c 'print(1)'` 要幾秒（gVisor，不經過 Docker）。
#
# 怎麼跑：
#   bash spikes/sb_local_timing.sh                 # 預設 image：python:3.12-slim，每項 5 次
#   IMAGE=debian:stable-slim N=10 bash spikes/sb_local_timing.sh
#
# gVisor 只支援 Linux 主機（x86_64／ARM64，kernel 5.6+；gvisor.dev/docs/user_guide/install/）。
# macOS 上的 Docker Desktop 不適用這一段。
# 結果（2026-10-28，雲端 Linux VM，4 vCPU，Docker 29.9.2，runsc release-20261019.0）：
#   runc：0.30–0.50 s；runc + --network none（跑 python）：0.23–0.28 s；runsc do：0.08–0.12 s。
#   runsc --network=host 在該環境連不上外網（環境限制），所以沒量到 gVisor 下的安裝時間。

set -u
IMAGE="${IMAGE:-python:3.12-slim}"
N="${N:-5}"

t() {
  local s e
  s=$(date +%s.%N)
  "$@" >/dev/null 2>&1
  local rc=$?
  e=$(date +%s.%N)
  printf '%.2f s (rc=%d)\n' "$(echo "$e - $s" | bc)" "$rc"
}

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull -q "$IMAGE" >/dev/null

echo "== runc: docker run --rm $IMAGE true"
for _ in $(seq "$N"); do t docker run --rm "$IMAGE" true; done

echo "== runc + --network none: python -c 'print(1)'"
for _ in $(seq "$N"); do t docker run --rm --network none "$IMAGE" python -c 'print(1)'; done

if command -v runsc >/dev/null 2>&1; then
  echo "== gVisor: runsc --network=none do python3 -c 'print(1)'"
  for _ in $(seq "$N"); do t runsc --network=none --ignore-cgroups do python3 -c 'print(1)'; done
else
  echo "== 沒有 runsc，略過 gVisor（安裝方式見 gvisor.dev/docs/user_guide/install/）"
fi
