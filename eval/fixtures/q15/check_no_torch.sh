#!/bin/sh
# q15 L2: is any Python "torch" package installed anywhere in this container?
#
#   sh check_no_torch.sh [ROOT]      (ROOT defaults to /)
#
# Looks in every site-packages and dist-packages directory under ROOT (any
# interpreter, any venv, user installs), plus conda package folders, for:
#   site-packages/torch, torch-*.dist-info, torch-*.egg-info, torch-*.egg,
#   pkgs/pytorch-*
# Download caches (~/.cache/pip and the like) are not installs and are not
# matched. /proc, /sys and /dev are skipped.
# Prints every match. Exit 0 = none found, 1 = torch found.
# POSIX sh + find + grep.
set -u
root=${1:-/}
if [ "$root" != / ]; then root=${root%/}; fi
if [ "$root" = / ]; then base=; else base=$root; fi
matches=$(find "$root" \( -path "$base/proc" -o -path "$base/sys" -o -path "$base/dev" \) -prune -o \
  \( -name torch -o -name 'torch-*.dist-info' -o -name 'torch-*.egg-info' -o -name 'torch-*.egg' -o -name 'pytorch-*' \) \
  -print 2>/dev/null |
  grep -E '/(site|dist)-packages/torch(-[^/]*\.(dist-info|egg-info|egg))?$|/pkgs/pytorch-[^/]*$')
if [ -n "$matches" ]; then
  echo "torch found:"
  echo "$matches"
  exit 1
fi
echo "no torch package found under $root"
exit 0
