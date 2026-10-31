#!/bin/sh
# Mac L2 (q11, q12): record what is installed system-wide, before and after a
# test run, so diff_state.py can list everything that has to be removed.
#
#   sudo sh snapshot_state.sh DIR before  TESTUSER  # before the answer's first step
#   sudo sh snapshot_state.sh DIR after   TESTUSER  # after the last check
#   python3 diff_state.py DIR/before DIR/after      # removal checklist
#   ... remove everything on the checklist, delete the test user ...
#   sudo sh snapshot_state.sh DIR cleanup TESTUSER
#   python3 diff_state.py DIR/before DIR/cleanup    # must print "nothing left"
#
# Run from the grader's (admin) account. Read-only apart from writing DIR.
# "after" and "cleanup" also list every file outside the test user's home that
# changed since "before" (in /Applications, /Library, /opt, /usr/local, /Users/Shared,
# /private/etc, /private/var/db/receipts).
set -u

dir=${1:?usage: snapshot_state.sh DIR before|after|cleanup TESTUSER}
label=${2:?usage: snapshot_state.sh DIR before|after|cleanup TESTUSER}
tuser=${3:?usage: snapshot_state.sh DIR before|after|cleanup TESTUSER}
case "$label" in before|after|cleanup) ;; *) echo "label must be before, after or cleanup" >&2; exit 2 ;; esac
[ "$(id -u)" = 0 ] || echo "warning: not root; some lists will be incomplete" >&2

out="$dir/$label"
mkdir -p "$out"
thome=$(dscl . -read "/Users/$tuser" NFSHomeDirectory 2>/dev/null | awk '{print $2}')

{ date -u +%Y-%m-%dT%H:%M:%SZ; sw_vers -productVersion; echo "test user: $tuser ($thome)"; } > "$out/info.txt"
[ "$label" = before ] && touch "$dir/marker"

find /Applications /Applications/Utilities /Users/*/Applications -maxdepth 1 -name '*.app' 2>/dev/null \
  | sort > "$out/applications.txt"

for prefix in /opt/homebrew /usr/local; do
  b="$prefix/bin/brew"
  [ -x "$b" ] || continue
  owner=$(stat -f %Su "$prefix")
  tag=$(echo "$prefix" | tr / _)
  # Homebrew refuses to run as root: run it as the owner of the prefix.
  if [ "$(id -u)" = 0 ]; then
    as_owner="sudo -u $owner"
  elif [ "$owner" = "$(id -un)" ]; then
    as_owner=""
  else
    echo "skipping $prefix: owned by $owner (run with sudo)" >&2
    continue
  fi
  $as_owner "$b" list --formula --versions 2>/dev/null | sort > "$out/brew-formulae$tag.txt"
  $as_owner "$b" list --cask --versions 2>/dev/null | sort > "$out/brew-casks$tag.txt"
  $as_owner "$b" tap 2>/dev/null | sort > "$out/brew-taps$tag.txt"
  echo "$prefix owner=$owner $($as_owner "$b" --version 2>/dev/null | head -1)" > "$out/brew-info$tag.txt"
done
[ -d /opt/homebrew ] || echo "absent" > "$out/brew-info_opt_homebrew.txt"

ls -1A /Library/LaunchAgents /Library/LaunchDaemons /Users/*/Library/LaunchAgents 2>/dev/null > "$out/launchd-plists.txt"
pkgutil --pkgs 2>/dev/null | sort > "$out/pkg-receipts.txt"
ls -1A /usr/local/bin /opt/homebrew/bin 2>/dev/null > "$out/bin-dirs.txt"
cat /etc/paths /etc/paths.d/* 2>/dev/null > "$out/etc-paths.txt"
ls -1A /Users/Shared 2>/dev/null | sort > "$out/users-shared.txt"
# accounts other than the test account itself (it is created before "before" and deleted before "cleanup")
dscl . -list /Users UniqueID 2>/dev/null | awk -v u="$tuser" '$2 >= 500 && $1 != u' | sort > "$out/users.txt"
# listening sockets of the test user and of root (other users' ephemeral ports would only add noise)
lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | awk -v u="$tuser" 'NR>1 && ($3==u || $3=="root") {print $1, $3, $9}' \
  | sort -u > "$out/listeners.txt"
ps -axo user=,comm= 2>/dev/null | awk -v u="$tuser" '$1==u' | sort -u > "$out/test-user-processes.txt"

if [ "$label" != before ] && [ -f "$dir/marker" ]; then
  find /Applications /Library /opt /usr/local /Users/Shared /private/etc /private/var/db/receipts \
    -xdev -newer "$dir/marker" \( -type f -o -type l \) 2>/dev/null \
    | grep -v -E '^/Library/(Caches|Logs)/|^/Library/Application Support/(CrashReporter|com\.apple)|^/Library/Preferences/(SystemConfiguration/|com\.apple\.)|/\.DS_Store$' \
    | sort > "$out/changed-outside-home.txt"
  if [ -n "$thome" ] && [ -d "$thome" ]; then
    find "$thome" -xdev -type f -size +204800 2>/dev/null | sort > "$out/large-files-in-test-home.txt"
  fi
fi

echo "snapshot written to $out"
ls -1 "$out"
