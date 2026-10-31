#!/bin/sh
# q08 system snapshot for the removal checklist. Lists system-wide places where an install
# can leave things behind; never prints file contents or secrets. Run from the MAIN account
# before the eval account is created (baseline) and again after it has been deleted.
#
#   sh snapshot.sh OUTFILE
#   diff BASELINE OUTFILE        (only the "## taken" line may differ)

out=${1:?usage: sh snapshot.sh OUTFILE}
sec() { printf '\n## %s\n' "$1"; }
{
  printf '## taken %s by %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(id -un)"
  sec "users (non-system)"; dscl . list /Users | grep -v '^_' | sort
  sec "/Users"; ls -1 /Users
  sec "/Applications"; ls -1 /Applications
  sec "/Library/LaunchDaemons"; ls -1 /Library/LaunchDaemons 2>&1
  sec "/Library/LaunchAgents"; ls -1 /Library/LaunchAgents 2>&1
  sec "/Library/PrivilegedHelperTools"; ls -1 /Library/PrivilegedHelperTools 2>&1
  sec "/Library/Extensions"; ls -1 /Library/Extensions 2>&1
  sec "system extensions"; systemextensionsctl list 2>&1 | grep -v '^[0-9]* extension(s)$'
  sec "/usr/local/bin"; ls -l /usr/local/bin 2>&1 | awk 'NR>1 {print $9, $10, $11}'
  sec "/usr/local (top level)"; ls -1 /usr/local 2>&1
  sec "/opt (top level)"; ls -1 /opt 2>&1
  sec "/etc/sudoers.d"; ls -1 /etc/sudoers.d 2>&1
  sec "/etc/paths.d"; ls -1 /etc/paths.d 2>&1
  sec "/etc/resolver"; ls -1 /etc/resolver 2>&1
  sec "/etc/pam.d/sudo_local"; shasum -a 256 /etc/pam.d/sudo_local 2>&1
  sec "/etc/hosts"; shasum -a 256 /etc/hosts
  sec "/etc/exports"; shasum -a 256 /etc/exports 2>&1
  sec "/var/run/docker.sock"; ls -l /var/run/docker.sock 2>&1 | awk '{print $1, $9, $10, $11}'
  sec "installer receipts"; pkgutil --pkgs | sort
  sec "network interfaces"; ifconfig -l | tr ' ' '\n' | sort
  sec "network services"; networksetup -listallnetworkservices 2>&1
  sec "Homebrew"
  if [ -x /opt/homebrew/bin/brew ]; then
    ls -ld /opt/homebrew | awk '{print $1, $3, $4}'
    /opt/homebrew/bin/brew list --versions --formula 2>&1
    /opt/homebrew/bin/brew list --versions --cask 2>&1
  else
    echo "no /opt/homebrew/bin/brew"
  fi
  sec "virtual machine processes"; pgrep -lf 'com.apple.Virtualization.VirtualMachine|qemu-system' 2>/dev/null | awk '{print $2}' | sort -u
} > "$out" 2>&1
echo "snapshot written to $out"
