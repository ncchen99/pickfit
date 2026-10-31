#!/bin/sh
# Build the q20 user's existing Python environment: a venv with the pinned official openai package.
# NEEDS NETWORK: run only while building the q20 base image, before any answer's steps.
# Requires python3 with venv support (Ubuntu: python3-venv). Writes $VENV and $STATE/pip-freeze.txt.
# Not run by the fixture author (no downloads were allowed while writing the fixtures).
# Usage: STATE=/eval-work/q20/state sh setup_user_env.sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/pins.env"
STATE=${STATE:-$HERE/state}
: "${OPENAI_PKG_VERSION:?pins.env: OPENAI_PKG_VERSION is empty; fill it at freeze}"
mkdir -p "$STATE"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check --no-input "openai==$OPENAI_PKG_VERSION"
"$VENV/bin/python" -m pip freeze --all >"$STATE/pip-freeze.txt"
"$VENV/bin/python" -c "import openai; print('openai', openai.__version__)"
echo "venv ready at $VENV; record $STATE/pip-freeze.txt in calibration.md"
