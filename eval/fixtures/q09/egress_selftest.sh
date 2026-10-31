#!/bin/sh
# q09: confirm the egress check works in this sandbox before the first eval run.
# Run as root in the dev image after `sh setup_user.sh` and `apt-get install -y strace`.
#
#   sh egress_selftest.sh /tmp/egress-selftest
#
# Expected: case 1 and 2 report no egress; case 3 (a TCP connect to a TEST-NET-1
# address that is never routed) and case 4 (a DNS lookup of a .invalid name)
# are both detected. If case 3 or 4 is not detected, strace does not work in
# this sandbox: use the network-blocked fallback described in README.md.
set -u
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?usage: egress_selftest.sh OUTDIR}
mkdir -p "$out"
chmod 0777 "$out"

EGRESS_LOG="$out/1-true.log" sh "$here/dev_shell.sh" 'true'
EGRESS_LOG="$out/2-loopback.log" sh "$here/dev_shell.sh" 'timeout 3 bash -c "exec 3<>/dev/tcp/127.0.0.1/9" 2>/dev/null; true'
EGRESS_LOG="$out/3-testnet.log" sh "$here/dev_shell.sh" 'timeout 3 bash -c "exec 3<>/dev/tcp/192.0.2.1/9" 2>/dev/null; true'
EGRESS_LOG="$out/4-dns.log" sh "$here/dev_shell.sh" 'getent hosts egress-selftest.invalid >/dev/null; true'

ok=1
python3 "$here/egress_parse.py" "$out/1-true.log" "$out/2-loopback.log" >/dev/null || { echo "case 1/2: unexpected egress"; ok=0; }
python3 "$here/egress_parse.py" "$out/3-testnet.log" >/dev/null && { echo "case 3: connect NOT detected"; ok=0; }
python3 "$here/egress_parse.py" "$out/4-dns.log" >/dev/null && { echo "case 4: DNS lookup NOT detected"; ok=0; }
python3 "$here/egress_parse.py" "$out"/*.log
[ "$ok" = 1 ] && echo "egress self-test: OK" || { echo "egress self-test: FAILED"; exit 1; }
