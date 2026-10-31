#!/bin/sh
# q15 speed baseline: openai-whisper "small" with default settings, in its own
# container (same dev image, same 4 vCPU / 16 GB, same host type as the
# answer's container). Not part of any answer; it is the yardstick.
#
#   sh run_baseline.sh setup          # network open: install, download small.pt
#   sh run_baseline.sh time OUT_DIR   # egress blocked: one timed run
#
# Pins come from calibration.md; there are no defaults on purpose:
#   WHISPER_VERSION   openai-whisper version on PyPI
#   TORCH_VERSION     torch version (CPU wheel)
#   TORCH_INDEX_URL   index the CPU wheel comes from
#   SMALL_PT_SHA256   SHA-256 of the "small" checkpoint
# "Default settings" = `whisper clip.wav --model small` and nothing else
# (language detection, beam size, temperature fallback, fp32 on CPU and the
# output formats are whisper's own defaults).
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
venv=/opt/whisper-baseline
case ${1:-} in
setup)
  : "${WHISPER_VERSION:?set from calibration.md}"
  : "${TORCH_VERSION:?set from calibration.md}"
  : "${TORCH_INDEX_URL:?set from calibration.md}"
  : "${SMALL_PT_SHA256:?set from calibration.md}"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-venv ffmpeg
  python3 -m venv "$venv"
  "$venv/bin/pip" install --index-url "$TORCH_INDEX_URL" "torch==$TORCH_VERSION"
  "$venv/bin/pip" install "openai-whisper==$WHISPER_VERSION"
  mkdir -p /tmp/whisper-warmup
  (cd /tmp/whisper-warmup && "$venv/bin/whisper" "$here/clip/warmup.wav" --model small)
  got=$(sha256sum "$HOME/.cache/whisper/small.pt" | cut -d' ' -f1)
  if [ "$got" != "$SMALL_PT_SHA256" ]; then
    echo "small.pt sha256 $got does not match the pin" >&2
    exit 1
  fi
  "$venv/bin/pip" freeze > /tmp/whisper-warmup/pip-freeze.txt
  echo "baseline ready; record /tmp/whisper-warmup/pip-freeze.txt"
  ;;
time)
  out=${2:?usage: run_baseline.sh time OUT_DIR}
  mkdir -p "$out"
  cd "$out"
  python3 "$here/egress_check.py" run --monitor none --log "$out/baseline_time.json" -- \
    "$venv/bin/whisper" "$here/clip/clip.wav" --model small
  ;;
*)
  echo "usage: run_baseline.sh setup | time OUT_DIR" >&2
  exit 2
  ;;
esac
