#!/bin/sh
# Renders the share cards (og.html) and the home-screen icon to PNG with headless Chrome,
# into worker/public/assets/og/. Run from the repo root: sh brand/og/render.sh
set -e
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../../worker/public/assets/og"
mkdir -p "$OUT"
shot() { # url width height file
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
    --force-device-scale-factor=1 --blink-settings=preferredColorScheme=1 --virtual-time-budget=2000 \
    --window-size="$2,$3" --screenshot="$OUT/$4" "$1" >/dev/null 2>&1
}
shot "file://$HERE/og.html" 1200 630 pickfit-en.png
shot "file://$HERE/og.html?lang=zh" 1200 630 pickfit-zh.png
shot "file://$HERE/touch.html" 180 180 apple-touch-icon.png
ls -l "$OUT"
