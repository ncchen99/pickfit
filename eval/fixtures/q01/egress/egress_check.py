#!/usr/bin/env python3
"""Egress check, step 2 of 2: read strace logs written by run_traced.sh and
list every outbound network attempt.

  python3 egress_check.py TRACE_LOG [TRACE_LOG ...] [--json OUT.json]
  python3 egress_check.py --self-test

An outbound attempt is any traced connect / sendto / sendmsg / sendmmsg whose
destination is an AF_INET or AF_INET6 address that is not loopback, or any
destination on port 53 (DNS, even on loopback, because a local stub resolver
forwards the query out). Sockets of other families that can reach the network
(for example AF_PACKET) also count. AF_UNIX, AF_NETLINK and AF_UNSPEC do not.
Calls that failed still count: an attempt is an attempt.

Exit codes: 0 = no outbound attempt (pass); 1 = at least one (fail);
2 = no evidence that tracing worked (missing log, or no execve line), so the
step must be re-run under tracing before it can be judged.

Python 3.9+ standard library only. Can run on the grader host after the
trace files are copied out of the sandbox.
"""
import argparse
import ipaddress
import json
import re
import sys

CALL_RE = re.compile(r"^(?:\[pid\s+(?P<pid1>\d+)\]\s*|(?P<pid2>\d+)\s+)?"
                     r"(?:\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+)?"
                     r"(?P<call>execve|connect|sendto|sendmsg|sendmmsg)\(")
INET_RE = re.compile(r'sa_family=AF_INET,\s*sin_port=htons\((?P<port>\d+)\),\s*'
                     r'sin_addr=inet_addr\("(?P<addr>[0-9.]+)"\)')
INET6_RE = re.compile(r'sa_family=AF_INET6,\s*sin6_port=htons\((?P<port>\d+)\)'
                      r'.*?inet_pton\(AF_INET6,\s*"(?P<addr>[0-9A-Fa-f:.]+)"')
FAMILY_RE = re.compile(r"sa_family=(?P<fam>AF_[A-Z0-9]+)")
IGNORED_FAMILIES = {"AF_UNIX", "AF_LOCAL", "AF_NETLINK", "AF_UNSPEC", "AF_INET", "AF_INET6"}


def is_local(addr):
    ip = ipaddress.ip_address(addr)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_unspecified


def scan_lines(lines, source="<log>"):
    execs = 0
    attempts = []
    for n, line in enumerate(lines, 1):
        m = CALL_RE.match(line)
        if not m:
            continue
        call = m.group("call")
        pid = m.group("pid1") or m.group("pid2") or ""
        if call == "execve":
            execs += 1
            continue
        result = line.rsplit(" = ", 1)[1].strip() if " = " in line else "unfinished"
        found = False
        for rx, fam in ((INET_RE, "AF_INET"), (INET6_RE, "AF_INET6")):
            for a in rx.finditer(line):
                found = True
                addr, port = a.group("addr"), int(a.group("port"))
                if port == 53 or not is_local(addr):
                    attempts.append({"source": source, "line": n, "pid": pid, "call": call,
                                     "family": fam, "addr": addr, "port": port,
                                     "result": result})
        if not found:
            for f in FAMILY_RE.finditer(line):
                fam = f.group("fam")
                if fam not in IGNORED_FAMILIES:
                    attempts.append({"source": source, "line": n, "pid": pid, "call": call,
                                     "family": fam, "addr": None, "port": None,
                                     "result": result})
    return execs, attempts


def self_test():
    sample = [
        '100 execve("/bin/sh", ["sh", "-c", "x"], 0x7ffd /* 5 vars */) = 0',
        '101 connect(3, {sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"}, 110) = -1 ENOENT',
        '101 connect(4, {sa_family=AF_INET, sin_port=htons(8080), sin_addr=inet_addr("127.0.0.1")}, 16) = 0',
        '101 connect(5, {sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("127.0.0.53")}, 16) = 0',
        '102 connect(6, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("93.184.215.14")}, 16 <unfinished ...>',
        '103 sendto(7, "\\x12\\x34"..., 40, MSG_NOSIGNAL, {sa_family=AF_INET6, sin6_port=htons(443), '
        'sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "2606:2800:21f:cb07:6820:80da:af6b:8b2c", &sin6_addr), '
        'sin6_scope_id=0}, 28) = 40',
        '103 connect(8, {sa_family=AF_INET6, sin6_port=htons(9000), sin6_flowinfo=htonl(0), '
        'inet_pton(AF_INET6, "::1", &sin6_addr), sin6_scope_id=0}, 28) = 0',
        '104 sendto(9, "x", 1, 0, NULL, 0) = 1',
        '[pid   105] connect(3, {sa_family=AF_INET, sin_port=htons(80), sin_addr=inet_addr("10.1.2.3")}, 16) = -1 ENETUNREACH (Network is unreachable)',
        '106 connect(3, {sa_family=AF_UNSPEC, sa_data="..."}, 16) = 0',
        '107 sendmsg(3, {msg_name={sa_family=AF_NETLINK, nl_pid=0, nl_groups=00000000}, msg_namelen=12}, 0) = 20',
        '108 connect(3, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), '
        'inet_pton(AF_INET6, "::ffff:127.0.0.1", &sin6_addr), sin6_scope_id=0}, 28) = 0',
    ]
    execs, att = scan_lines(sample)
    got = sorted((a["addr"], a["port"]) for a in att)
    want = sorted([("127.0.0.53", 53), ("93.184.215.14", 443),
                   ("2606:2800:21f:cb07:6820:80da:af6b:8b2c", 443), ("10.1.2.3", 80)])
    ok = execs == 1 and got == want
    print("self-test " + ("PASS" if ok else "FAIL: execs=%d got=%r" % (execs, got)))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="*")
    ap.add_argument("--json", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.logs:
        ap.error("give at least one trace log")
    total_execs, attempts, missing = 0, [], []
    for path in a.logs:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                execs, att = scan_lines(f.read().splitlines(), source=path)
        except FileNotFoundError:
            missing.append(path)
            continue
        if execs == 0:
            missing.append(path)
        total_execs += execs
        attempts.extend(att)
    for x in attempts:
        print("EGRESS %s:%d pid=%s %s %s %s:%s -> %s" % (
            x["source"], x["line"], x["pid"], x["call"], x["family"],
            x["addr"], x["port"], x["result"]))
    if attempts:
        verdict, code = "FAIL (%d outbound attempt(s))" % len(attempts), 1
    elif missing:
        verdict, code = "UNDETERMINED (no trace evidence in: %s)" % ", ".join(missing), 2
    else:
        verdict, code = "PASS (no outbound attempt; %d execve traced)" % total_execs, 0
    print("RESULT " + verdict)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"result": verdict, "exit": code, "attempts": attempts,
                       "logs": a.logs, "untraced": missing}, f, indent=2)
            f.write("\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
