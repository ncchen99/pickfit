#!/bin/sh
# Mac L2 (q11, q12): turn every network interface off, check that the Mac is
# really offline, and turn the interfaces back on afterwards.
#
#   sudo sh offline.sh off   STATEFILE   # disable every enabled network service
#   sh offline.sh check                  # read-only: PASS only when fully offline
#   sudo sh offline.sh on    STATEFILE   # re-enable exactly the services that were on
#
# "Off" means every network service in System Settings > Network (Wi-Fi,
# Ethernet, Thunderbolt Bridge, iPhone USB, VPNs, ...) is disabled with
# networksetup, and Wi-Fi power is off. The check then requires: no default
# route (IPv4 and IPv6), no non-loopback interface with an IPv4 address or a
# non-link-local IPv6 address, and a test HTTPS request that fails.
# Needs an admin account for off/on. macOS only.
set -u

cmd=${1:-}
state=${2:-}

services() {
  # one service name per line; disabled ones start with "*"
  networksetup -listallnetworkservices | sed '1d'
}

wifi_devices() {
  networksetup -listallhardwareports | awk '/^Hardware Port: (Wi-Fi|AirPort)/{getline; print $2}'
}

check() {
  bad=0
  if route -n get -inet default >/dev/null 2>&1; then
    echo "  default IPv4 route present"; bad=1
  fi
  if route -n get -inet6 default >/dev/null 2>&1; then
    echo "  default IPv6 route present"; bad=1
  fi
  addrs=$(ifconfig -a | awk '
    /^[a-z]/ { iface=$1; sub(":", "", iface) }
    $1=="inet" && $2 !~ /^127\./ { print iface " " $2 }
    $1=="inet6" && $2 !~ /^(::1|fe80:)/ { print iface " " $2 }')
  if [ -n "$addrs" ]; then
    echo "  interfaces with addresses:"; echo "$addrs" | sed 's/^/    /'; bad=1
  fi
  if /usr/bin/curl -s -m 5 -o /dev/null https://www.apple.com/ 2>/dev/null; then
    echo "  test HTTPS request succeeded"; bad=1
  fi
  enabled=$(services | grep -v '^\*' || true)
  if [ -n "$enabled" ]; then
    echo "  enabled network services:"; echo "$enabled" | sed 's/^/    /'; bad=1
  fi
  if [ "$bad" = 0 ]; then
    echo "offline check: PASS"
    return 0
  fi
  echo "offline check: FAIL"
  return 1
}

case "$cmd" in
  off)
    [ -n "$state" ] || { echo "usage: offline.sh off STATEFILE" >&2; exit 2; }
    services | grep -v '^\*' > "$state" || true
    echo "saving $(wc -l < "$state" | tr -d ' ') enabled service(s) to $state"
    for dev in $(wifi_devices); do
      networksetup -setairportpower "$dev" off
    done
    while IFS= read -r svc; do
      [ -n "$svc" ] && networksetup -setnetworkserviceenabled "$svc" off && echo "  disabled: $svc"
    done < "$state"
    sleep 5
    check
    ;;
  on)
    [ -n "$state" ] && [ -f "$state" ] || { echo "usage: offline.sh on STATEFILE" >&2; exit 2; }
    while IFS= read -r svc; do
      [ -n "$svc" ] && networksetup -setnetworkserviceenabled "$svc" on && echo "  enabled: $svc"
    done < "$state"
    for dev in $(wifi_devices); do
      networksetup -setairportpower "$dev" on
    done
    echo "network services restored; Wi-Fi may take a few seconds to rejoin"
    ;;
  check)
    check
    ;;
  *)
    echo "usage: offline.sh off STATEFILE | check | on STATEFILE" >&2
    exit 2
    ;;
esac
