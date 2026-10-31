#!/bin/sh
# Mac L2 (q11, q12): check that the test account is fresh before the answer's
# first step. Run in Terminal.app inside the test user's own login session.
#
#   sh preflight.sh OUTFILE
#
# Prints every check and ends with "preflight: PASS" or "preflight: FAIL".
# Read-only: makes no network request and changes nothing.
# Environment variable values are never printed, only names.
set -u

out=${1:?usage: preflight.sh OUTFILE}
fail=0
note() { printf '%s\n' "$*" | tee -a "$out"; }
bad() { note "  FAIL: $*"; fail=1; }

: > "$out"
note "== machine"
note "  date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
note "  macOS: $(sw_vers -productVersion) ($(sw_vers -buildVersion)); arch: $(uname -m)"
note "  chip: $(sysctl -n machdep.cpu.brand_string 2>/dev/null); memory: $(( $(sysctl -n hw.memsize) / 1073741824 )) GiB"
note "  developer tools: $(xcode-select -p 2>/dev/null || echo none)"

note "== user"
note "  user: $(id -un) uid=$(id -u) home=$HOME"
if dseditgroup -o checkmember -m "$(id -un)" admin >/dev/null 2>&1; then
  note "  admin: yes"
else
  note "  admin: no"
fi
created=$(stat -f %SB -t %Y-%m-%dT%H:%M "$HOME" 2>/dev/null)
note "  home created: $created"

note "== home directory (must hold only what macOS creates for a new account)"
extra=$(ls -A "$HOME" | grep -v -x -e Desktop -e Documents -e Downloads -e Library -e Movies \
  -e Music -e Pictures -e Public -e .CFUserTextEncoding -e .Trash -e .zsh_sessions \
  -e .zsh_history -e .zprofile -e .zshrc -e .bash_history -e .bash_sessions -e .DS_Store \
  -e Applications -e .lesshst -e .viminfo || true)
if [ -n "$extra" ]; then
  bad "unexpected entries in \$HOME: $(echo $extra)"
else
  note "  ok"
fi
for d in "$HOME/.cache" "$HOME/.local" "$HOME/.config"; do
  [ -e "$d" ] && bad "$d exists"
done

note "== environment (names only)"
names=$(env | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' | \
  grep -E -i 'token|secret|api_?key|password|^HF_|HUGGING|TRANSFORMERS_|_CACHE$|_HOME$|OFFLINE' | \
  grep -v -x -e HOME || true)
if [ -n "$names" ]; then
  bad "set: $(echo $names) (unset them, or start a fresh login session)"
else
  note "  no token, key, cache-location or offline variables set"
fi
note "  PATH=$PATH"

note "== large model-like files readable by this user (>= 100 MB)"
found=$(find "$HOME" /Users/Shared /opt/homebrew /usr/local /private/tmp "${TMPDIR:-/private/tmp}" \
  -xdev -type f -size +204800 \( -iname '*.gguf' -o -iname '*.safetensors' -o -iname '*.bin' \
  -o -iname '*.pt' -o -iname '*.pth' -o -iname '*.onnx' -o -iname '*.npz' -o -iname '*.mlmodel' \
  -o -iname '*.weights' -o -iname '*.ckpt' -o -iname '*.mlx' \) 2>/dev/null | head -50)
if [ -n "$found" ]; then
  bad "model-like files present:"; printf '%s\n' "$found" | sed 's/^/    /' | tee -a "$out"
else
  note "  none"
fi

note "== package managers and runtimes on PATH"
for c in brew python3 pip3 pipx uv node npm cargo go conda docker; do
  p=$(command -v "$c" 2>/dev/null) && note "  $c: $p"
done
if command -v brew >/dev/null 2>&1; then
  note "  brew prefix: $(brew --prefix) owner: $(stat -f %Su "$(brew --prefix)")"
  nf=$(brew list --formula 2>/dev/null | wc -l | tr -d ' ')
  nc=$(brew list --cask 2>/dev/null | wc -l | tr -d ' ')
  note "  brew formulae: $nf, casks: $nc"
fi
for p in /opt/homebrew /usr/local/Homebrew; do
  [ -e "$p" ] && note "  $p exists, owner $(stat -f %Su "$p")"
done

note "== listening TCP ports"
lst=$(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | sed '1d' || true)
if [ -n "$lst" ]; then
  note "  (review: none of these may belong to an earlier test run)"
  printf '%s\n' "$lst" | sed 's/^/    /' | tee -a "$out"
else
  note "  none visible to this user"
fi

note "== virtual machine bridges (stop all VMs before a run)"
br=$(ifconfig -l | tr ' ' '\n' | grep -E '^bridge1[0-9][0-9]$' || true)
if [ -n "$br" ]; then
  bad "bridge interfaces present: $(echo $br)"
else
  note "  none"
fi

note ""
if [ "$fail" = 0 ]; then note "preflight: PASS"; else note "preflight: FAIL"; fi
exit "$fail"
