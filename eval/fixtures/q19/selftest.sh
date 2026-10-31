#!/bin/sh
# Offline self-test of the q19 fixtures: python3 (3.9+) stdlib only, no root, no network.
# Run before the first eval run, on the dev image and on the machine that scores the runs.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
python3 "$HERE/tests/test_shared.py"
python3 "$HERE/tests/test_q19.py"
