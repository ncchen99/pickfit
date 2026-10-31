#!/bin/sh
# q08 preflight: run in the separate macOS eval account, in Terminal, BEFORE the answer's
# install steps. POSIX sh plus tools that ship with macOS; never starts a container engine.
#
#   sh /Users/Shared/q08-fixture/preflight.sh [OUTDIR]      (default OUTDIR: ~/q08-run)
#
# Prints PASS / WARN / FAIL lines and saves them with details in OUTDIR/preflight.txt.
# Any FAIL means the account is not ready: fix it (see README.md section 3) and rerun.

out=${1:-"$HOME/q08-run"}
mkdir -p "$out"
rep="$out/preflight.txt"
: > "$rep"
fails=0

say() { printf '%s\n' "$*" | tee -a "$rep"; }
detail() { printf '%s\n' "$*" >> "$rep"; }
pass() { say "PASS  $*"; }
warn() { say "WARN  $*"; }
fail() { say "FAIL  $*"; fails=$((fails + 1)); }

say "q08 preflight $(date -u +%Y-%m-%dT%H:%M:%SZ) user=$(id -un)"
detail "$(sw_vers 2>&1)"

[ "$(uname -m)" = arm64 ] && pass "Apple silicon (arm64)" || fail "machine is $(uname -m), not arm64"

main=${Q08_MAIN_ACCOUNT:-ncchen}
[ "$(id -un)" != "$main" ] && pass "running in a separate account ($(id -un))" || fail "this is the main account ($main); use the eval account"

if dseditgroup -o checkmember -m "$(id -un)" admin >/dev/null 2>&1; then
  pass "account is an administrator (terminal sudo possible)"
else
  warn "account is not an administrator; steps that need sudo will fail"
fi

if grep -qs '^[^#]*pam_tid' /etc/pam.d/sudo_local /etc/pam.d/sudo; then
  fail "Touch ID is enabled for sudo (/etc/pam.d/sudo_local); it shows a GUI sheet. Disable it for the run"
else
  pass "sudo asks for the password in the terminal (no Touch ID sheet)"
fi

if pgrep -f '/Applications/Docker.app/|com.docker.backend' >/dev/null 2>&1; then
  fail "Docker Desktop processes are running (any user): quit Docker Desktop"
else
  pass "no Docker Desktop process running"
fi
[ -d /Applications/Docker.app ] && detail "Docker Desktop installed: yes" || detail "Docker Desktop installed: no"

if [ -n "${DOCKER_HOST-}" ]; then fail "DOCKER_HOST is set ($DOCKER_HOST)"; else pass "DOCKER_HOST is not set"; fi
if [ -n "${DOCKER_CONTEXT-}" ]; then fail "DOCKER_CONTEXT is set ($DOCKER_CONTEXT)"; else pass "DOCKER_CONTEXT is not set"; fi
if [ -e "$HOME/.docker" ]; then
  warn "~/.docker already exists in this account (not a fresh account?)"
  detail "$(ls -lA "$HOME/.docker" 2>&1)"
else
  pass "no ~/.docker in this account"
fi

d=$(command -v docker 2>/dev/null)
if [ -z "$d" ]; then
  pass "no docker CLI on PATH before the install"
else
  target=$(readlink "$d" 2>/dev/null)
  detail "docker CLI: $d -> ${target:-<not a symlink>}"
  case "$target" in
    /Applications/*.app/*) fail "docker on PATH ($d) belongs to an installed app ($target); hide it for the run (README 3)";;
    *) warn "a docker CLI is already on PATH: $d (not run by this script)";;
  esac
fi
for f in /usr/local/bin/docker /usr/local/bin/docker-compose /usr/local/bin/docker-buildx; do
  [ -e "$f" ] || [ -L "$f" ] && detail "present: $(ls -l "$f")"
done

sock=${Q08_DOCKER_SOCK:-/var/run/docker.sock}
if [ -e "$sock" ] || [ -L "$sock" ]; then
  detail "$sock: $(ls -l "$sock" 2>&1)"
  if curl -s --max-time 3 --unix-socket "$sock" http://localhost/_ping >/dev/null 2>&1; then
    fail "an engine answers on $sock before the install"
  else
    warn "$sock exists but nothing answers on it"
  fi
else
  pass "no $sock"
fi

busy=0
for h in 127.0.0.1 ::1; do
  if nc -z -G 2 "$h" 8080 >/dev/null 2>&1; then busy=1; detail "something listens on $h:8080"; fi
done
[ $busy -eq 0 ] && pass "host port 8080 is free" || fail "host port 8080 is in use (any user); stop that process"

vms=$(pgrep -lf 'com.apple.Virtualization.VirtualMachine|qemu-system' 2>/dev/null)
if [ -n "$vms" ]; then warn "virtual machines are running on this Mac (any user)"; detail "$vms"; else pass "no virtual machine running"; fi

if [ -d /opt/homebrew ]; then
  owner=$(stat -f %Su /opt/homebrew)
  if [ -w /opt/homebrew ]; then
    pass "Homebrew prefix /opt/homebrew is writable by this account (owner $owner)"
  else
    warn "Homebrew prefix /opt/homebrew is owned by $owner and not writable here (README 3, Homebrew)"
  fi
  [ -x /opt/homebrew/bin/brew ] && detail "brew: $(/opt/homebrew/bin/brew --version 2>/dev/null | head -1); formulae: $(/opt/homebrew/bin/brew list --formula 2>/dev/null | wc -l | tr -d ' '); casks: $(/opt/homebrew/bin/brew list --cask 2>/dev/null | wc -l | tr -d ' ')"
else
  detail "no /opt/homebrew"
fi

detail "xcode-select -p: $(xcode-select -p 2>&1)"
if /usr/bin/arch -x86_64 /usr/bin/true 2>/dev/null; then detail "Rosetta: installed"; else detail "Rosetta: not installed"; fi
detail "firewall: $(/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>&1)"
detail "PATH=$PATH"
detail "shell=$SHELL"

say "preflight: $fails FAIL line(s); details in $rep"
[ $fails -eq 0 ]
