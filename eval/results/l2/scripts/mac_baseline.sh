#!/bin/bash
# Mac L2 baseline, part 1 (run as the image's admin, in a fresh clone; eval/fixtures/_mac/CHECKLIST.md sections 1-2
# in a VM): a new admin user that logs in automatically, and the image's own Homebrew moved aside so that the user
# can install an empty one. The user's password is random, made here, and never printed or kept outside the guest.
# Differences from the hand checklist, the same for both groups: sudo needs no password for this user (a person
# would type it at a terminal sudo prompt); the Tart Guest Agent is copied out of /opt/homebrew so that it survives
# the move; the image's /etc/paths.d/homebrew entry (not on a stock Mac) is moved aside too. The caller then shuts
# the guest down from inside (a host-side stop can cut power before these writes reach the disk) and starts it again.
set -euo pipefail
U=evaluser
ASIDE=/var/eval-image-aside
sudo mkdir -p /usr/local/libexec "$ASIDE"
sudo cp /opt/homebrew/bin/tart-guest-agent /usr/local/libexec/tart-guest-agent
for p in /Library/LaunchAgents/org.cirruslabs.tart-guest-agent.plist /Library/LaunchDaemons/org.cirruslabs.tart-guest-daemon.plist; do
  sudo sed -i '' 's#/opt/homebrew/bin/tart-guest-agent#/usr/local/libexec/tart-guest-agent#g' "$p"
done
PW=$(openssl rand -hex 12)
sudo sysadminctl -addUser "$U" -fullName "Eval User" -password "$PW" -admin 2> /dev/null
sudo dseditgroup -o edit -a "$U" -t user admin
echo "$U ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/$U > /dev/null
sudo chmod 440 /etc/sudoers.d/$U
# auto-login: /etc/kcpassword is the password XORed with Apple's fixed key, padded to a multiple of 12
PW="$PW" sudo -E /usr/bin/python3 -c '
import os
key = [125, 137, 82, 35, 210, 188, 221, 234, 163, 185, 31]
pw = os.environ["PW"].encode()
pw += b"\0" * (12 - len(pw) % 12)
open("/etc/kcpassword", "wb").write(bytes(b ^ key[i % len(key)] for i, b in enumerate(pw)))
os.chmod("/etc/kcpassword", 0o600)'
unset PW
sudo defaults write /Library/Preferences/com.apple.loginwindow autoLoginUser "$U"
sudo createhomedir -c -u "$U" > /dev/null
# skip the first-login assistant panes (they are part of making the account, not of the answer's steps)
for k in DidSeeCloudSetup DidSeeSiriSetup DidSeePrivacy DidSeeScreenTime DidSeeAppearanceSetup DidSeeTouchIDSetup \
         DidSeeAccessibility DidSeeIntelligence DidSeeActivationLock DidSeeTermsOfAddress; do
  sudo -u "$U" defaults write com.apple.SetupAssistant "$k" -bool true
done
sudo -u "$U" defaults write com.apple.SetupAssistant SkipFirstLoginOptimization -bool true
sudo mv /opt/homebrew "$ASIDE/homebrew"
sudo mv /etc/paths.d/homebrew "$ASIDE/paths.d-homebrew"
sync
echo "baseline part 1 done: user $U ($(id -Gn $U | tr ' ' ',')), image Homebrew moved to $ASIDE"
