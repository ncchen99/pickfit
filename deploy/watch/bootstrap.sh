#!/usr/bin/env bash
# Set up `pickfit watch` on a fresh Ubuntu 24.04 machine (any provider). Run as root; running it again is safe.
#
#   scp deploy/watch/bootstrap.sh deploy/watch/pickfit-watch.service root@HOST: && ssh root@HOST bash bootstrap.sh
#
# It installs git, Node 24 and uv (each checked against its published SHA-256), the Scaleway CLI, Chromium for
# playwright, a `pickfit` user, the repository in /var/lib/pickfit/pickfit, and the systemd service. It never
# writes a secret: deploy/watch/send_secrets.py, run on the Mac, fills /etc/pickfit/watch.env (the names are in
# deploy/watch/watch.env.example) and starts the service.
set -euo pipefail

REPO_URL=${REPO_URL:-https://github.com/ncchen99/pickfit.git}
BRANCH=${BRANCH:-main}
HOME_DIR=/var/lib/pickfit
REPO=$HOME_DIR/pickfit
ARCH=$(dpkg --print-architecture)  # amd64 or arm64
case "$ARCH" in
  amd64) NODE_ARCH=x64; UV_ARCH=x86_64 ;;
  arm64) NODE_ARCH=arm64; UV_ARCH=aarch64 ;;
  *) echo "unsupported architecture $ARCH" >&2; exit 1 ;;
esac

export DEBIAN_FRONTEND=noninteractive

# A small machine (2 GB) gets 2 GB of swap, so npm ci, uv sync and Chromium do not run out of memory.
if [[ -z $(swapon --noheadings) ]] && (( $(awk '/MemTotal/ {print $2}' /proc/meminfo) < 4000000 )); then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

apt-get update -q
apt-get install -y -q git ca-certificates curl openssh-client python3 xz-utils libatomic1  # playwright's node needs libatomic

# fetch URL SHA256 OUT: download and check, or stop.
fetch() {
  curl -fsSL --retry 3 -o "$3" "$1"
  echo "$2  $3" | sha256sum -c --quiet -
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# Node 24 (wrangler for D1 and the Worker's npm ci), from nodejs.org's own checksum list.
if ! command -v node >/dev/null || [[ $(node -p 'process.versions.node.split(".")[0]') != 24 ]]; then
  curl -fsSL -o "$work/SHASUMS256.txt" https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt
  line=$(grep " node-v24\.[0-9.]*-linux-$NODE_ARCH\.tar\.xz$" "$work/SHASUMS256.txt")
  name=${line##* }
  fetch "https://nodejs.org/dist/latest-v24.x/$name" "${line%% *}" "$work/$name"
  tar -xJf "$work/$name" -C /usr/local --strip-components=1 --exclude CHANGELOG.md --exclude LICENSE --exclude README.md
fi

# uv, from its GitHub release and that release's .sha256.
if ! command -v uv >/dev/null; then
  base=https://github.com/astral-sh/uv/releases/latest/download/uv-$UV_ARCH-unknown-linux-gnu.tar.gz
  sum=$(curl -fsSL "$base.sha256" | cut -d' ' -f1)
  fetch "$base" "$sum" "$work/uv.tar.gz"
  tar -xzf "$work/uv.tar.gz" -C "$work"
  install -m 755 "$work"/uv-*/uv "$work"/uv-*/uvx /usr/local/bin/
fi

# The Scaleway CLI (renting Macs for the macOS lane), from its latest release and SHA256SUMS.
if ! command -v scw >/dev/null; then
  release=$(curl -fsSL https://api.github.com/repos/scaleway/scaleway-cli/releases/latest)
  version=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))' <<<"$release")
  asset="scaleway-cli_${version}_linux_${ARCH}"
  sums=$(curl -fsSL "https://github.com/scaleway/scaleway-cli/releases/download/v$version/SHA256SUMS")
  fetch "https://github.com/scaleway/scaleway-cli/releases/download/v$version/$asset" \
    "$(awk -v a="$asset" '$2 == a {print $1}' <<<"$sums")" "$work/scw"
  install -m 755 "$work/scw" /usr/local/bin/scw
fi

id pickfit >/dev/null 2>&1 || useradd --system --create-home --home-dir "$HOME_DIR" --shell /bin/bash pickfit
install -d -m 750 -o root -g pickfit /etc/pickfit
[[ -f /etc/pickfit/watch.env ]] || install -m 640 -o root -g pickfit /dev/null /etc/pickfit/watch.env

as_pickfit() { sudo -u pickfit -H bash -lc "$1"; }
if [[ ! -d $REPO/.git ]]; then
  as_pickfit "git clone -q --branch $BRANCH $REPO_URL $REPO"
fi
# Commits are the watcher's; pushing uses GH_PUSH_TOKEN from the service's environment, never a URL or a file.
as_pickfit "cd $REPO && git config user.name 'pickfit watch' && git config user.email 'watch@pickfit.app' &&
  git config credential.helper '!f() { echo username=x-access-token; echo \"password=\$GH_PUSH_TOKEN\"; }; f'"
as_pickfit "cd $REPO && uv sync --frozen -q && (cd worker && npm ci --silent)"
# Chromium's system libraries as root, outside the repository so root never writes into pickfit's .venv.
(cd / && uvx --from playwright playwright install-deps chromium) >/dev/null
as_pickfit "cd $REPO && uv run --with playwright playwright install chromium"

# The units sent along with this script win (main may not have deploy/watch/ yet), else the repository's.
for name in pickfit-watch.service pickfit-e2e@.service pickfit-harvest.service pickfit-harvest.timer \
    pickfit-harvest-feed.service pickfit-harvest-feed.timer pickfit-harvest-probe.service \
    pickfit-harvest-probe.timer; do
  unit="$(dirname "$0")/$name"
  [[ -f $unit ]] || unit="$REPO/deploy/watch/$name"
  if [[ -f $unit ]]; then install -m 644 "$unit" "/etc/systemd/system/$name"; fi
done
systemctl daemon-reload
echo
echo "Set up. Next:"
echo "  on the Mac, in the repository: uv run python deploy/watch/send_secrets.py root@THIS-HOST"
echo "  (it sends /etc/pickfit/watch.env and the watch state, then starts the service)"
