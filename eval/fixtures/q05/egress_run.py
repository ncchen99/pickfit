#!/usr/bin/env python3
"""Run one command for an L2 check and report network egress, exit code and time.

Python 3.8+ standard library only. Byte-identical copies live in eval/fixtures/q05, q06, q07.

    egress_run.py [--block-network] [--timeout SEC] [--trace FILE] [--report FILE]
                  [--stdout FILE] [--cwd DIR] [--no-strace] -- CMD [ARG...]
    egress_run.py --parse TRACE [--report FILE]
    egress_run.py --selftest

What it does (Linux):
  * --block-network: runs CMD in a new network namespace that has only the loopback
    interface (brought up here), so nothing outside the box is reachable. Needs root
    (or CAP_SYS_ADMIN). Aborts with exit 125 if any interface other than lo is visible.
  * strace (default on): records connect/sendto/sendmsg/sendmmsg of CMD and every child
    process. The trace is then classified; any attempt to reach a non-loopback address,
    any DNS-type port (53, 853, 5353, 5355) even on loopback, any AF_PACKET send and any
    connect to a resolver UNIX socket counts as one egress attempt. Attempts count even
    when they failed (for example ENETUNREACH inside the blocked namespace).
  * --timeout: kills the whole process group after SEC seconds (exit 124 in the report).

The report (JSON) has exit_code, timed_out, duration_s, and egress.verdict:
  "pass"        strace ran and found zero egress attempts
  "fail"        at least one egress attempt (listed with the raw trace line)
  "not_checked" strace was not used (--no-strace); the egress item cannot pass this way
The wrapper exits with CMD's exit code (124 on timeout, 125 on setup error).
"""

import argparse
import datetime
import hashlib
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time

TRACE_SYSCALLS = "connect,sendto,sendmsg,sendmmsg"
DNS_PORTS = {53, 853, 5353, 5355}
RESOLVER_UNIX_PREFIXES = ("/run/systemd/resolve", "/var/run/nscd", "/run/nscd")
EXIT_TIMEOUT = 124
EXIT_SETUP = 125

SOCKADDR_RE = re.compile(r"\{sa_family=(AF_[A-Z0-9_]+)([^{}]*)\}")
SYSCALL_RE = re.compile(r"^(?:\[pid\s+\d+\]\s+|\d+\s+)?(?:[\d:.]+\s+)?(\w+)\(")
PORT_RE = re.compile(r"sin6?_port=htons\((\d+)\)")
V4_RE = re.compile(r'inet_addr\("([^"]+)"\)')
V6_RE = re.compile(r'inet_pton\(AF_INET6,\s*"([^"]+)"')
UNIX_RE = re.compile(r'sun_path=(@?)"([^"]*)"')
RESULT_RE = re.compile(r"\)\s+=\s+(-?\d+|\?)(?:\s+(E[A-Z0-9]+))?")


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _is_loopback_ip(text):
    try:
        ip = ipaddress.ip_address(text.split("%")[0])
    except ValueError:
        return False
    if ip.is_loopback or ip.is_unspecified:
        return True
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None and (mapped.is_loopback or mapped.is_unspecified):
        return True
    return False


def classify_line(line):
    """Return a list of dicts, one per socket address in this strace line."""
    out = []
    m = SYSCALL_RE.match(line)
    syscall = m.group(1) if m else "?"
    if syscall not in ("connect", "sendto", "sendmsg", "sendmmsg"):
        # "<... connect resumed>" lines carry no address; the unfinished half had it.
        r = re.search(r"<\.\.\. (\w+) resumed>", line)
        if r:
            syscall = r.group(1)
    rm = RESULT_RE.search(line)
    result = None
    if rm:
        result = rm.group(1) + ((" " + rm.group(2)) if rm.group(2) else "")
    for fam, body in SOCKADDR_RE.findall(line):
        entry = {"syscall": syscall, "family": fam, "result": result, "egress": False, "reason": ""}
        if fam in ("AF_INET", "AF_INET6"):
            pm = PORT_RE.search(body)
            port = int(pm.group(1)) if pm else None
            am = (V4_RE if fam == "AF_INET" else V6_RE).search(body)
            addr = am.group(1) if am else None
            entry.update({"addr": addr, "port": port})
            if addr is None:
                entry.update({"egress": True, "reason": "address not decoded"})
            elif not _is_loopback_ip(addr):
                entry.update({"egress": True, "reason": "non-loopback address"})
            elif port in DNS_PORTS:
                entry.update({"egress": True, "reason": "DNS-type port on loopback (name lookup)"})
        elif fam == "AF_UNIX":
            um = UNIX_RE.search(body)
            path = (um.group(1) + um.group(2)) if um else ""
            entry.update({"addr": path, "port": None})
            if any(path.startswith(p) for p in RESOLVER_UNIX_PREFIXES):
                entry.update({"egress": True, "reason": "resolver socket (name lookup)"})
        elif fam == "AF_PACKET":
            entry.update({"addr": body.strip(", "), "port": None, "egress": True,
                          "reason": "raw packet socket"})
        else:
            entry.update({"addr": body.strip(", ")[:80], "port": None})
        out.append(entry)
    return out


def parse_trace(path, keep=200):
    attempts, loopback, total, n_egress = [], 0, 0, 0
    families = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            for e in classify_line(line):
                total += 1
                families[e["family"]] = families.get(e["family"], 0) + 1
                if e["egress"]:
                    n_egress += 1
                    if len(attempts) < keep:
                        e["line"] = line[:500]
                        attempts.append(e)
                elif e["family"] in ("AF_INET", "AF_INET6"):
                    loopback += 1
    with open(path, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    return {
        "checked": True,
        "trace_file": os.path.abspath(path),
        "trace_sha256": sha,
        "sockaddr_records": total,
        "by_family": families,
        "loopback_inet_records": loopback,
        "egress_attempts": n_egress,
        "attempts": attempts,
        "attempts_listed": len(attempts),
        "verdict": "pass" if n_egress == 0 else "fail",
    }


def _netns_exec(info_path, cmd):
    """Internal: unshare the network namespace, bring lo up, record interfaces, exec CMD."""
    import ctypes
    import fcntl
    CLONE_NEWNET = 0x40000000
    try:
        if hasattr(os, "unshare"):
            os.unshare(CLONE_NEWNET)
        else:
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.unshare(CLONE_NEWNET) != 0:
                err = ctypes.get_errno()
                raise OSError(err, os.strerror(err))
        SIOCGIFFLAGS, SIOCSIFFLAGS, IFF_UP = 0x8913, 0x8914, 0x1
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        req = struct.pack("16sh22x", b"lo", 0)
        res = fcntl.ioctl(s.fileno(), SIOCGIFFLAGS, req)
        flags = struct.unpack("16sh", res[:18])[1]
        fcntl.ioctl(s.fileno(), SIOCSIFFLAGS, struct.pack("16sh22x", b"lo", flags | IFF_UP))
        s.close()
        names = sorted(n for _, n in socket.if_nameindex())
    except Exception as exc:  # noqa: BLE001
        with open(info_path, "w") as fh:
            json.dump({"ok": False, "error": repr(exc)}, fh)
        sys.stderr.write("egress_run: cannot create network namespace: %r\n" % (exc,))
        os._exit(EXIT_SETUP)
    ok = names == ["lo"]
    with open(info_path, "w") as fh:
        json.dump({"ok": ok, "interfaces": names}, fh)
    if not ok:
        sys.stderr.write("egress_run: namespace still has interfaces %r\n" % (names,))
        os._exit(EXIT_SETUP)
    os.execvp(cmd[0], cmd)


def run(args):
    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        sys.exit("egress_run: no command given")
    report_path = args.report or "egress_report.json"
    base = os.path.splitext(report_path)[0]
    trace = os.path.abspath(args.trace or (base + ".strace"))
    info_path = os.path.abspath(base + ".netns.json")
    full = cmd
    strace_bin = None
    if not args.no_strace:
        strace_bin = shutil.which("strace")
        if not strace_bin:
            sys.stderr.write("egress_run: strace not found; install it or pass --no-strace\n")
            sys.exit(EXIT_SETUP)
        full = [strace_bin, "-f", "-qq", "-s", "160", "-e", "trace=" + TRACE_SYSCALLS,
                "-e", "signal=none", "-o", trace, "--"] + full
    if args.block_network:
        full = [sys.executable, os.path.abspath(__file__), "--_netns-exec", info_path, "--"] + full
    stdout = open(args.stdout, "wb") if args.stdout else None
    started, t0 = utcnow(), time.monotonic()
    proc = subprocess.Popen(full, cwd=args.cwd, stdout=stdout, start_new_session=True)
    stopped_by_signal = []

    def _forward(signum, _frame):
        stopped_by_signal.append(signum)
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, _forward)
    signal.signal(signal.SIGINT, _forward)
    timed_out = False
    try:
        rc = proc.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        rc = proc.wait()
    duration = time.monotonic() - t0
    if stdout:
        stdout.close()
    report = {
        "command": cmd,
        "cwd": os.path.abspath(args.cwd or "."),
        "block_network": bool(args.block_network),
        "timeout_s": args.timeout,
        "started_utc": started,
        "ended_utc": utcnow(),
        "duration_s": round(duration, 3),
        "timed_out": timed_out,
        "stopped_by_signal": stopped_by_signal[0] if stopped_by_signal else None,
        "exit_code": EXIT_TIMEOUT if timed_out else rc,
        "strace": strace_bin,
    }
    if args.block_network:
        try:
            with open(info_path) as fh:
                report["netns"] = json.load(fh)
        except (OSError, ValueError):
            report["netns"] = {"ok": False, "error": "no namespace info written"}
    if strace_bin and os.path.exists(trace):
        report["egress"] = parse_trace(trace)
    elif strace_bin:
        report["egress"] = {"checked": False, "verdict": "fail", "reason": "trace file missing"}
    else:
        report["egress"] = {"checked": False, "verdict": "not_checked"}
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    sys.stderr.write("egress_run: exit=%s timed_out=%s duration=%.1fs egress=%s report=%s\n" % (
        report["exit_code"], timed_out, duration, report["egress"]["verdict"], report_path))
    if args.block_network and not report["netns"].get("ok"):
        sys.exit(EXIT_SETUP)
    sys.exit(report["exit_code"] if isinstance(report["exit_code"], int) and report["exit_code"] >= 0
             else 1)


SELFTEST = [
    # (strace line, expected egress flags per sockaddr)
    ('1234 connect(3, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("140.82.112.3")}, 16)'
     ' = -1 ENETUNREACH (Network is unreachable)', [True]),
    ('1234 connect(4, {sa_family=AF_INET, sin_port=htons(18080), sin_addr=inet_addr("127.0.0.1")}, 16) = 0',
     [False]),
    ('1234 connect(5, {sa_family=AF_INET6, sin6_port=htons(18080), sin6_flowinfo=htonl(0), '
     'inet_pton(AF_INET6, "::1", &sin6_addr), sin6_scope_id=0}, 28) = 0', [False]),
    ('1234 connect(5, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), '
     'inet_pton(AF_INET6, "2606:4700::6810:84e5", &sin6_addr), sin6_scope_id=0}, 28) = -1 EINPROGRESS', [True]),
    ('1234 connect(6, {sa_family=AF_INET6, sin6_port=htons(80), sin6_flowinfo=htonl(0), '
     'inet_pton(AF_INET6, "::ffff:127.0.0.1", &sin6_addr), sin6_scope_id=0}, 28) = 0', [False]),
    ('1234 sendto(7, "\\x12\\x34"..., 34, MSG_NOSIGNAL, {sa_family=AF_INET, sin_port=htons(53), '
     'sin_addr=inet_addr("10.0.0.2")}, 16) = 34', [True]),
    ('1234 sendto(7, "abc", 3, 0, {sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("127.0.0.53")}, 16) = 3',
     [True]),
    ('1234 connect(8, {sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"}, 110) = -1 ENOENT', [True]),
    ('1234 connect(8, {sa_family=AF_UNIX, sun_path="/tmp/app.sock"}, 110) = 0', [False]),
    ('1234 sendto(9, "x", 1, 0, NULL, 0) = 1', []),
    ('1234 sendmmsg(3, [{msg_hdr={msg_name={sa_family=AF_INET, sin_port=htons(53), '
     'sin_addr=inet_addr("8.8.8.8")}, msg_namelen=16}}, {msg_hdr={msg_name={sa_family=AF_INET, '
     'sin_port=htons(53), sin_addr=inet_addr("8.8.4.4")}, msg_namelen=16}}], 2, MSG_NOSIGNAL) = 2', [True, True]),
    ('1234 connect(3, {sa_family=AF_INET, sin_port=htons(80), sin_addr=inet_addr("0.0.0.0")}, 16) = 0', [False]),
    ('1234 connect(3, {sa_family=AF_UNSPEC, sa_data="\\0\\0"}, 16) = 0', [False]),
    ('1234 connect(3, {sa_family=AF_NETLINK, nl_pid=0, nl_groups=00000000}, 12) = 0', [False]),
    ('[pid  4321] connect(3, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("93.184.215.14")}, 16 '
     '<unfinished ...>', [True]),
    ('1234 <... connect resumed>) = -1 ENETUNREACH (Network is unreachable)', []),
]


def selftest():
    bad = 0
    for line, expect in SELFTEST:
        got = [e["egress"] for e in classify_line(line)]
        if got != expect:
            bad += 1
            print("FAIL %r\n  expected %r got %r" % (line[:90], expect, got))
    print("selftest: %d/%d lines classified as expected" % (len(SELFTEST) - bad, len(SELFTEST)))
    return 1 if bad else 0


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--_netns-exec":
        rest = sys.argv[3:]
        if rest and rest[0] == "--":
            rest = rest[1:]
        _netns_exec(sys.argv[2], rest)
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--block-network", action="store_true")
    ap.add_argument("--timeout", type=float, default=None)
    ap.add_argument("--trace")
    ap.add_argument("--report")
    ap.add_argument("--stdout", help="write CMD's stdout to this file")
    ap.add_argument("--cwd")
    ap.add_argument("--no-strace", action="store_true")
    ap.add_argument("--parse", metavar="TRACE")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    if args.parse:
        rep = parse_trace(args.parse)
        text = json.dumps(rep, ensure_ascii=False, indent=2)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as fh:
                fh.write(text)
        print(text)
        sys.exit(0 if rep["verdict"] == "pass" else 1)
    run(args)


if __name__ == "__main__":
    main()
