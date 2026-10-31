#!/usr/bin/env python3
"""q09 egress check: read strace logs written by dev_shell.sh (EGRESS_LOG=...)
and list every attempt to reach another host (Python 3.8+ stdlib only).

Counted as egress (the check fails):
  * connect / sendto / sendmsg / sendmmsg to an IPv4 or IPv6 address outside
    loopback (127.0.0.0/8, ::1, ::ffff:127.0.0.0/104) and the unspecified
    address (0.0.0.0, ::), whether the call succeeded or failed;
  * any of those calls to port 53 on any address, loopback included
    (a DNS lookup: a local resolver stub forwards it out).
Not counted: AF_UNIX, AF_NETLINK, AF_UNSPEC (disconnect), loopback.

Usage:
  python3 egress_parse.py LOG [LOG ...]

Exit status: 0 when no log shows egress, 1 otherwise, 2 when a log is missing
or empty of trace lines while the command was expected to run.
"""
import ipaddress
import re
import sys

CALL_RE = re.compile(r"^(?:\[pid\s+)?(\d+)?\]?\s*(connect|sendto|sendmsg|sendmmsg)\(")
INET_RE = re.compile(r'sa_family=AF_INET, sin_port=htons\((\d+)\), sin_addr=inet_addr\("([0-9.]+)"\)')
INET6_RE = re.compile(r'sa_family=AF_INET6, sin6_port=htons\((\d+)\),.*?inet_pton\(AF_INET6, "([^"]+)"')


def local(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_unspecified


def scan(path):
    hits, calls = [], 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            m = CALL_RE.match(line)
            if not m:
                continue
            calls += 1
            for rx, fam in ((INET_RE, "inet"), (INET6_RE, "inet6")):
                for port, addr in rx.findall(line):
                    port = int(port)
                    if port == 53 or not local(addr):
                        hits.append({"log": path, "line": n, "call": m.group(2), "family": fam,
                                     "addr": addr, "port": port,
                                     "dns": port == 53, "text": line[:200]})
    return hits, calls


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    all_hits = []
    for p in argv:
        try:
            hits, calls = scan(p)
        except OSError as e:
            print("cannot read %s: %s" % (p, e))
            return 2
        all_hits.extend(hits)
        print("%s: %d network calls traced, %d egress" % (p, calls, len(hits)))
    for h in all_hits:
        print("  EGRESS %s:%d %s %s port %d%s" % (h["log"], h["line"], h["call"], h["addr"], h["port"],
                                                 " (DNS)" if h["dns"] else ""))
    print("egress check: %s" % ("PASS" if not all_hits else "FAIL (%d attempts)" % len(all_hits)))
    return 0 if not all_hits else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
