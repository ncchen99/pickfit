#!/bin/sh
# Renders the LinkedIn banner (banner.html) to PNG at twice LinkedIn's 1584 × 396, so it stays sharp after LinkedIn recompresses it.
# Run from the repo root: sh brand/linkedin/render.sh
set -e
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
HERE="$(cd "$(dirname "$0")" && pwd)"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
  --force-device-scale-factor=2 --virtual-time-budget=2000 \
  --window-size=1584,396 --screenshot="$HERE/pickfit-linkedin-banner.png" "file://$HERE/banner.html" >/dev/null 2>&1
ls -l "$HERE/pickfit-linkedin-banner.png"
