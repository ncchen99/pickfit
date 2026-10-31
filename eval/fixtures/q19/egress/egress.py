#!/usr/bin/env python3
"""Egress check for the eval fixtures (Python stdlib only, Python 3.9+).

"Egress" here means any attempt to reach an address other than this machine:
a DNS query for a name that is not a localhost name, or a connect/sendto/sendmsg
to an IPv4/IPv6 address that is not loopback (127.0.0.0/8, ::1), unspecified
(0.0.0.0, ::) or one of this sandbox's own interface addresses.

Three independent layers, all written under one output directory:

  dns    A DNS server on 127.0.0.1:53 that logs every query. /etc/resolv.conf
         is pointed at it. In "sink" mode it answers NXDOMAIN for every
         non-localhost name (use while egress is blocked); in "forward" mode
         it relays to the original resolver (use while the network is open).
         Needs root. System-wide: covers every process started after it.
  strace Optional. `egress.py trace -- CMD` runs CMD under strace (if the
         strace binary exists) and logs connect/sendto/sendmsg/sendmmsg of
         CMD and all its children. Per process tree, so it attributes traffic.
  poll   Polls /proc/net/{tcp,tcp6,udp,udp6} every 50 ms and records sockets
         whose remote address is not local. Best effort, system-wide.

Typical use (as root, inside the sandbox):

  python3 egress.py start  --out /eval-work/egress --mode sink
  ... start fixture services, then run the steps under test, optionally
      wrapped as: python3 egress.py trace --out /eval-work/egress --label run1 -- CMD ...
  python3 egress.py stop   --out /eval-work/egress
  python3 egress.py report --out /eval-work/egress [--since EPOCH --until EPOCH]

`report` prints JSON and exits 0 when no layer saw egress, 1 when any layer
saw egress, 2 when a required layer was not active (dns is always required;
add --require-strace / --require-poll when calibration says they work).
"""

import argparse
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
import threading
import time

RESOLV = "/etc/resolv.conf"
QTYPES = {1: "A", 2: "NS", 5: "CNAME", 6: "SOA", 12: "PTR", 15: "MX", 16: "TXT",
          28: "AAAA", 33: "SRV", 41: "OPT", 65: "HTTPS", 64: "SVCB", 255: "ANY"}
LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
               "localhost6", "localhost6.localdomain6"}
IP6_LOOPBACK_PTR = "1." + "0." * 31 + "ip6.arpa"


def now():
    return time.time()


def append_jsonl(path, obj):
    line = json.dumps(obj, sort_keys=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


# ---------------------------------------------------------------- addresses

def self_addresses():
    """Addresses of this machine's own interfaces, read from /proc (best effort)."""
    addrs = set()
    try:
        with open("/proc/net/fib_trie", encoding="utf-8") as f:
            last = None
            for line in f:
                m = re.search(r"\|--\s+(\d+\.\d+\.\d+\.\d+)", line)
                if m:
                    last = m.group(1)
                elif "/32 host LOCAL" in line and last:
                    addrs.add(last)
    except OSError:
        pass
    try:
        with open("/proc/net/if_inet6", encoding="utf-8") as f:
            for line in f:
                h = line.split()[0]
                if len(h) == 32:
                    addrs.add(str(ipaddress.IPv6Address(bytes.fromhex(h))))
    except (OSError, ValueError, IndexError):
        pass
    return addrs


def classify_ip(ip, selfaddrs=()):
    """Return 'loopback', 'unspecified', 'self' or 'remote'."""
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return "remote"
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped is not None:
        a = a.ipv4_mapped
    if a.is_loopback:
        return "loopback"
    if a.is_unspecified:
        return "unspecified"
    if str(a) in selfaddrs:
        return "self"
    return "remote"


# ---------------------------------------------------------------- DNS layer

def read_name(data, off):
    labels = []
    jumps = 0
    end = None
    while True:
        if off >= len(data):
            raise ValueError("name runs past packet")
        n = data[off]
        if n == 0:
            off += 1
            break
        if n & 0xC0 == 0xC0:
            if off + 1 >= len(data):
                raise ValueError("bad pointer")
            ptr = ((n & 0x3F) << 8) | data[off + 1]
            if end is None:
                end = off + 2
            off = ptr
            jumps += 1
            if jumps > 20:
                raise ValueError("pointer loop")
            continue
        off += 1
        labels.append(data[off:off + n].decode("ascii", "replace"))
        off += n
    return ".".join(labels), (end if end is not None else off)


def parse_query(data):
    if len(data) < 12:
        raise ValueError("short packet")
    qid, flags, qd = struct.unpack("!HHH", data[:6])
    if qd != 1:
        raise ValueError("qdcount %d" % qd)
    name, off = read_name(data, 12)
    if off + 4 > len(data):
        raise ValueError("short question")
    qtype, qclass = struct.unpack("!HH", data[off:off + 4])
    return qid, flags, name, qtype, qclass, off + 4


def is_local_name(name, hostnames):
    n = name.lower().rstrip(".")
    if n in LOCAL_NAMES or n.endswith(".localhost") or n in hostnames:
        return True
    if n.endswith(".127.in-addr.arpa") or n == IP6_LOOPBACK_PTR:
        return True
    return False


def build_reply(data, qend, rcode, answers=()):
    qid, flags = struct.unpack("!HH", data[:4])
    opcode = flags & 0x7800
    rd = flags & 0x0100
    rflags = 0x8000 | opcode | rd | 0x0080 | (rcode & 0xF)
    header = struct.pack("!HHHHHH", qid, rflags, 1, len(answers), 0, 0)
    return header + data[12:qend] + b"".join(answers)


def rr_pointer(qtype, rdata):
    return struct.pack("!HHHIH", 0xC00C, qtype, 1, 0, len(rdata)) + rdata


class DnsServer(object):
    def __init__(self, out, mode, host, port, upstream):
        self.out = out
        self.log = os.path.join(out, "dns.jsonl")
        self.mode = mode
        self.host = host
        self.port = port
        self.upstream = upstream
        hn = socket.gethostname().lower()
        self.hostnames = {hn, hn.split(".")[0]}
        self.lock = threading.Lock()

    def record(self, obj):
        with self.lock:
            append_jsonl(self.log, obj)

    def answer(self, data, proto, client):
        try:
            qid, flags, name, qtype, qclass, qend = parse_query(data)
        except ValueError as e:
            self.record({"ts": now(), "event": "bad_query", "proto": proto,
                         "client": client, "error": str(e)})
            if len(data) >= 12:
                return data[:2] + struct.pack("!H", 0x8081) + b"\x00" * 8
            return None
        local = is_local_name(name, self.hostnames)
        opcode = (flags >> 11) & 0xF
        entry = {"ts": now(), "event": "query", "proto": proto, "client": client,
                 "qname": name, "qtype": QTYPES.get(qtype, str(qtype)), "local": local}
        if opcode != 0:
            entry["action"] = "notimp"
            self.record(entry)
            return build_reply(data, qend, 4)
        if local:
            answers = []
            if qtype == 1:
                answers.append(rr_pointer(1, socket.inet_aton("127.0.0.1")))
            elif qtype == 28:
                answers.append(rr_pointer(28, socket.inet_pton(socket.AF_INET6, "::1")))
            entry["action"] = "answer_local"
            self.record(entry)
            return build_reply(data, qend, 0, answers)
        if self.mode == "forward" and self.upstream:
            try:
                s = socket.socket(socket.AF_INET6 if ":" in self.upstream else socket.AF_INET,
                                  socket.SOCK_DGRAM)
                s.settimeout(3.0)
                s.sendto(data, (self.upstream, 53))
                reply, _ = s.recvfrom(65535)
                s.close()
                entry["action"] = "forward"
                self.record(entry)
                return reply
            except OSError as e:
                entry["action"] = "servfail"
                entry["error"] = str(e)
                self.record(entry)
                return build_reply(data, qend, 2)
        entry["action"] = "nxdomain"
        self.record(entry)
        return build_reply(data, qend, 3)

    def serve_udp(self, sock):
        while True:
            try:
                data, addr = sock.recvfrom(65535)
            except OSError:
                return
            reply = self.answer(data, "udp", "%s:%d" % (addr[0], addr[1]))
            if reply:
                try:
                    sock.sendto(reply, addr)
                except OSError:
                    pass

    def serve_tcp_conn(self, conn, addr):
        try:
            conn.settimeout(10)
            while True:
                hdr = self._recv_exact(conn, 2)
                if not hdr:
                    return
                (n,) = struct.unpack("!H", hdr)
                data = self._recv_exact(conn, n)
                if not data:
                    return
                reply = self.answer(data, "tcp", "%s:%d" % (addr[0], addr[1]))
                if reply:
                    conn.sendall(struct.pack("!H", len(reply)) + reply)
        except OSError:
            pass
        finally:
            conn.close()

    @staticmethod
    def _recv_exact(conn, n):
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def serve_tcp(self, sock):
        while True:
            try:
                conn, addr = sock.accept()
            except OSError:
                return
            t = threading.Thread(target=self.serve_tcp_conn, args=(conn, addr))
            t.daemon = True
            t.start()

    def run(self):
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        u.bind((self.host, self.port))
        t = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        t.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        t.bind((self.host, self.port))
        t.listen(16)
        self.record({"ts": now(), "event": "dns_start", "mode": self.mode,
                     "listen": "%s:%d" % (self.host, self.port), "upstream": self.upstream,
                     "pid": os.getpid()})
        th = threading.Thread(target=self.serve_tcp, args=(t,))
        th.daemon = True
        th.start()
        signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
        try:
            self.serve_udp(u)
        finally:
            self.record({"ts": now(), "event": "dns_stop"})


def first_nameserver(text):
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver" and parts[1] not in ("127.0.0.1",):
            return parts[1]
    return None


def dns_query_packet(name, qtype=1, qid=0x1234):
    q = b"".join(bytes([len(p)]) + p.encode("ascii") for p in name.split(".") if p) + b"\x00"
    return struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0) + q + struct.pack("!HH", qtype, 1)


def probe_dns(host, port, name="localhost", timeout=2.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(dns_query_packet(name), (host, port))
        reply, _ = s.recvfrom(65535)
        return struct.unpack("!H", reply[2:4])[0] & 0xF
    finally:
        s.close()


def cmd_dns_start(a):
    os.makedirs(a.out, exist_ok=True)
    upstream = None
    if os.path.exists(RESOLV):
        with open(RESOLV, encoding="utf-8") as f:
            orig = f.read()
        upstream = first_nameserver(orig)
        backup = os.path.join(a.out, "resolv.conf.orig")
        if not os.path.exists(backup):
            with open(backup, "w", encoding="utf-8") as f:
                f.write(orig)
    if a.mode == "forward" and not upstream:
        print("forward mode needs an upstream nameserver in %s" % RESOLV, file=sys.stderr)
        return 2
    err = open(os.path.join(a.out, "dns.stderr"), "ab")
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "_serve-dns", "--out", a.out,
                          "--mode", a.mode, "--host", a.host, "--port", str(a.port),
                          "--upstream", upstream or ""],
                         stdout=err, stderr=err, start_new_session=True)
    with open(os.path.join(a.out, "dns.pid"), "w") as f:
        f.write(str(p.pid))
    deadline = now() + 5
    ok = False
    while now() < deadline:
        try:
            if probe_dns(a.host, a.port) == 0:
                ok = True
                break
        except OSError:
            time.sleep(0.1)
    if not ok:
        print("DNS logger did not answer on %s:%d (see dns.stderr)" % (a.host, a.port),
              file=sys.stderr)
        return 2
    if not a.no_resolv:
        if a.port != 53:
            print("--port other than 53 cannot be used in resolv.conf; pass --no-resolv",
                  file=sys.stderr)
            return 2
        with open(RESOLV, "w", encoding="utf-8") as f:
            f.write("# written by egress.py; original in %s\n" % os.path.join(a.out, "resolv.conf.orig"))
            f.write("nameserver %s\noptions timeout:2 attempts:2\n" % a.host)
    print(json.dumps({"dns": "started", "mode": a.mode, "pid": p.pid, "upstream": upstream,
                      "resolv_conf_rewritten": not a.no_resolv}))
    return 0


def kill_pidfile(path):
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
    except (ValueError, OSError):
        pass
    os.remove(path)
    return True


def cmd_dns_stop(a):
    stopped = kill_pidfile(os.path.join(a.out, "dns.pid"))
    backup = os.path.join(a.out, "resolv.conf.orig")
    restored = False
    if not a.no_resolv and os.path.exists(backup):
        with open(backup, encoding="utf-8") as f:
            orig = f.read()
        try:
            with open(RESOLV, "w", encoding="utf-8") as f:
                f.write(orig)
            restored = True
        except OSError as e:
            print("could not restore %s: %s" % (RESOLV, e), file=sys.stderr)
    print(json.dumps({"dns": "stopped" if stopped else "not running", "resolv_restored": restored}))
    return 0


# ---------------------------------------------------------------- /proc poll

PROC_FILES = ("tcp", "tcp6", "udp", "udp6")


def hex_to_ip(h):
    if len(h) == 8:
        return socket.inet_ntop(socket.AF_INET, bytes.fromhex(h)[::-1])
    raw = b"".join(bytes.fromhex(h[i:i + 8])[::-1] for i in range(0, 32, 8))
    return socket.inet_ntop(socket.AF_INET6, raw)


def parse_proc_net(text, proto):
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            lh, lp = parts[1].split(":")
            rh, rp = parts[2].split(":")
            rows.append({"proto": proto, "local": hex_to_ip(lh), "lport": int(lp, 16),
                         "remote": hex_to_ip(rh), "rport": int(rp, 16), "state": parts[3]})
        except (ValueError, OSError):
            continue
    return rows


def cmd_poll(a):
    log = os.path.join(a.out, "poll.jsonl")
    readable = [p for p in PROC_FILES if os.access("/proc/net/" + p, os.R_OK)]
    selfaddrs = self_addresses()
    append_jsonl(log, {"ts": now(), "event": "poll_start", "files": readable,
                       "interval": a.interval, "pid": os.getpid(), "self": sorted(selfaddrs)})
    if not readable:
        return 0
    seen = set()
    signal.signal(signal.SIGTERM, lambda *x: sys.exit(0))
    while True:
        for p in readable:
            try:
                with open("/proc/net/" + p, encoding="ascii") as f:
                    rows = parse_proc_net(f.read(), p)
            except OSError:
                continue
            for r in rows:
                if r["rport"] == 0 and classify_ip(r["remote"]) == "unspecified":
                    continue
                kind = classify_ip(r["remote"], selfaddrs)
                if kind != "remote":
                    continue
                key = (r["proto"], r["local"], r["lport"], r["remote"], r["rport"])
                if key in seen:
                    continue
                seen.add(key)
                r.update({"ts": now(), "event": "remote_socket"})
                append_jsonl(log, r)
        time.sleep(a.interval)


def cmd_poll_start(a):
    os.makedirs(a.out, exist_ok=True)
    err = open(os.path.join(a.out, "poll.stderr"), "ab")
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "_poll", "--out", a.out,
                          "--interval", str(a.interval)],
                         stdout=err, stderr=err, start_new_session=True)
    with open(os.path.join(a.out, "poll.pid"), "w") as f:
        f.write(str(p.pid))
    print(json.dumps({"poll": "started", "pid": p.pid}))
    return 0


def cmd_poll_stop(a):
    stopped = kill_pidfile(os.path.join(a.out, "poll.pid"))
    print(json.dumps({"poll": "stopped" if stopped else "not running"}))
    return 0


# ---------------------------------------------------------------- strace layer

def strace_flags():
    base = ["-f", "-qq", "-ttt", "-e", "trace=connect,sendto,sendmsg,sendmmsg", "-e", "signal=none"]
    try:
        r = subprocess.run(["strace", "--seccomp-bpf"] + base + ["-o", os.devnull, "--", "true"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if r.returncode == 0:
            return ["--seccomp-bpf"] + base
    except (OSError, subprocess.SubprocessError):
        pass
    return base


def cmd_trace(a):
    cmd = a.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("trace needs a command after --", file=sys.stderr)
        return 2
    os.makedirs(a.out, exist_ok=True)
    label = re.sub(r"[^A-Za-z0-9_.-]", "_", a.label or "run")
    log = os.path.join(a.out, "strace-%s.log" % label)
    meta = {"ts": now(), "label": label, "cmd": cmd, "strace": None, "log": log}
    if shutil.which("strace"):
        flags = strace_flags()
        meta["strace"] = shutil.which("strace")
        meta["flags"] = flags
        with open(os.path.join(a.out, "strace-%s.meta.json" % label), "w") as f:
            json.dump(meta, f, indent=1)
        sys.stdout.flush()
        os.execvp("strace", ["strace"] + flags + ["-o", log, "--"] + cmd)
    with open(os.path.join(a.out, "strace-%s.meta.json" % label), "w") as f:
        json.dump(meta, f, indent=1)
    sys.stdout.flush()
    os.execvp(cmd[0], cmd)
    return 0


SOCK4 = re.compile(r"sa_family=AF_INET,\s*sin_port=htons\((\d+)\),\s*sin_addr=inet_addr\(\"([^\"]+)\"\)")
SOCK6 = re.compile(r"sa_family=AF_INET6,\s*sin6_port=htons\((\d+)\).*?inet_pton\(AF_INET6,\s*\"([^\"]+)\"")
LINE = re.compile(r"^(?:\[pid\s+(\d+)\]\s+|(\d+)\s+)?(\d+\.\d+)\s+(\w+)\(")


def parse_strace(text, selfaddrs=()):
    events = []
    for line in text.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        pid = int(m.group(1) or m.group(2) or 0)
        ts, call = float(m.group(3)), m.group(4)
        for rx, fam in ((SOCK4, "inet"), (SOCK6, "inet6")):
            for mm in rx.finditer(line):
                port, ip = int(mm.group(1)), mm.group(2)
                kind = classify_ip(ip, selfaddrs)
                result = line.rsplit("=", 1)[-1].strip() if "=" in line else ""
                events.append({"pid": pid, "ts": ts, "call": call, "family": fam, "ip": ip,
                               "port": port, "kind": kind, "result": result[:80]})
    return events


# ---------------------------------------------------------------- report

def in_window(ts, since, until):
    if since is not None and ts < since:
        return False
    if until is not None and ts > until:
        return False
    return True


def build_report(out, since=None, until=None, require_strace=False, require_poll=False):
    selfaddrs = self_addresses()
    rep = {"out": os.path.abspath(out), "since": since, "until": until, "layers": {}}

    dns = read_jsonl(os.path.join(out, "dns.jsonl"))
    starts = [e for e in dns if e.get("event") == "dns_start"]
    stops = [e["ts"] for e in dns if e.get("event") == "dns_stop"]
    end = until if until is not None else float("inf")
    # active = some start before the window ends, and no stop between that start and the window end
    dns_active = any(s["ts"] <= end and not any(s["ts"] < t < end for t in stops) for s in starts)
    qs = [e for e in dns if e.get("event") == "query" and in_window(e["ts"], since, until)]
    dns_bad = [e for e in qs if not e.get("local")]
    rep["layers"]["dns"] = {"active": dns_active, "mode": starts[-1].get("mode") if starts else None,
                            "queries": len(qs), "violations": dns_bad,
                            "names": sorted({e["qname"] for e in dns_bad})}

    strace_logs = sorted(f for f in os.listdir(out) if f.startswith("strace-") and f.endswith(".log")) \
        if os.path.isdir(out) else []
    metas = sorted(f for f in os.listdir(out) if f.startswith("strace-") and f.endswith(".meta.json")) \
        if os.path.isdir(out) else []
    traced_without_strace = []
    for m in metas:
        try:
            with open(os.path.join(out, m)) as f:
                md = json.load(f)
            if not md.get("strace") and in_window(md.get("ts", 0), since, until):
                traced_without_strace.append(md.get("label"))
        except (OSError, ValueError):
            pass
    st_events = []
    for f in strace_logs:
        with open(os.path.join(out, f), encoding="utf-8", errors="replace") as fh:
            for ev in parse_strace(fh.read(), selfaddrs):
                if in_window(ev["ts"], since, until):
                    ev["log"] = f
                    st_events.append(ev)
    st_bad = [e for e in st_events if e["kind"] == "remote"]
    rep["layers"]["strace"] = {"active": bool(strace_logs) and not traced_without_strace,
                               "logs": strace_logs, "traced_without_strace": traced_without_strace,
                               "inet_events": len(st_events), "violations": st_bad,
                               "remotes": sorted({"%s:%d" % (e["ip"], e["port"]) for e in st_bad})}

    poll = read_jsonl(os.path.join(out, "poll.jsonl"))
    pstarts = [e for e in poll if e.get("event") == "poll_start"]
    poll_active = bool(pstarts) and bool(pstarts[-1].get("files"))
    p_bad = [e for e in poll if e.get("event") == "remote_socket" and in_window(e["ts"], since, until)]
    rep["layers"]["poll"] = {"active": poll_active, "violations": p_bad,
                             "remotes": sorted({"%s:%d" % (e["remote"], e["rport"]) for e in p_bad})}

    rep["self_addresses"] = sorted(selfaddrs)
    violations = len(dns_bad) + len(st_bad) + len(p_bad)
    missing = []
    if not dns_active:
        missing.append("dns")
    if require_strace and not rep["layers"]["strace"]["active"]:
        missing.append("strace")
    if require_poll and not poll_active:
        missing.append("poll")
    rep["violations"] = violations
    rep["missing_layers"] = missing
    if violations:
        rep["result"] = "fail"
    elif missing:
        rep["result"] = "incomplete"
    else:
        rep["result"] = "pass"
    return rep


def cmd_report(a):
    rep = build_report(a.out, a.since, a.until, a.require_strace, a.require_poll)
    text = json.dumps(rep, indent=1, sort_keys=True)
    print(text)
    if a.save:
        with open(a.save, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return {"pass": 0, "fail": 1}.get(rep["result"], 2)


def cmd_start(a):
    rc = cmd_dns_start(a)
    if rc:
        return rc
    return cmd_poll_start(a)


def cmd_stop(a):
    cmd_poll_stop(a)
    return cmd_dns_stop(a)


def cmd_selfaddr(a):
    print(json.dumps(sorted(self_addresses())))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="sub")

    def common(p):
        p.add_argument("--out", required=True, help="output directory for all egress logs")

    for name in ("start", "dns-start"):
        p = sub.add_parser(name)
        common(p)
        p.add_argument("--mode", choices=("sink", "forward"), default="sink")
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=53)
        p.add_argument("--no-resolv", action="store_true", help="do not rewrite /etc/resolv.conf")
        p.add_argument("--interval", type=float, default=0.05)
    for name in ("stop", "dns-stop"):
        p = sub.add_parser(name)
        common(p)
        p.add_argument("--no-resolv", action="store_true")
    p = sub.add_parser("poll-start")
    common(p)
    p.add_argument("--interval", type=float, default=0.05)
    p = sub.add_parser("poll-stop")
    common(p)
    p = sub.add_parser("trace")
    common(p)
    p.add_argument("--label", default="run")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    p = sub.add_parser("report")
    common(p)
    p.add_argument("--since", type=float)
    p.add_argument("--until", type=float)
    p.add_argument("--require-strace", action="store_true")
    p.add_argument("--require-poll", action="store_true")
    p.add_argument("--save", help="also write the JSON report to this file")
    sub.add_parser("selfaddr")
    p = sub.add_parser("_serve-dns")
    common(p)
    p.add_argument("--mode", default="sink")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=53)
    p.add_argument("--upstream", default="")
    p = sub.add_parser("_poll")
    common(p)
    p.add_argument("--interval", type=float, default=0.05)

    a = ap.parse_args(argv)
    if a.sub == "_serve-dns":
        DnsServer(a.out, a.mode, a.host, a.port, a.upstream or None).run()
        return 0
    table = {"start": cmd_start, "stop": cmd_stop, "dns-start": cmd_dns_start, "dns-stop": cmd_dns_stop,
             "poll-start": cmd_poll_start, "poll-stop": cmd_poll_stop, "_poll": cmd_poll,
             "trace": cmd_trace, "report": cmd_report, "selfaddr": cmd_selfaddr}
    if a.sub not in table:
        ap.print_help()
        return 2
    return table[a.sub](a)


if __name__ == "__main__":
    sys.exit(main())
