#!/usr/bin/env python3
"""Egress check for the eval's L2 runs.

q14, q15 and q16 keep byte-identical copies of this file
(eval/fixtures/<qid>/egress_check.py).

  probe       prove that egress is blocked: TCP connects to public addresses,
              a UDP DNS query to public resolvers and a lookup of a public name
              must all fail. Exit 0 = blocked, 1 = something got through.
  run         run one command (no shell of its own; wrap pipelines in
              `bash -c '...'`), record every outbound connection attempt the
              command and its children make to a non-loopback address, probe
              before and after, and write one JSON log. Exit code = the
              command's exit code.
  selftest    inside the blocked sandbox: make deliberate attempts to RFC 5737
              TEST-NET addresses and confirm the chosen monitor records them.
  parse-strace  print the outbound attempts found in an strace output file.

Monitor methods (`--monitor auto` picks the first that works here):
  strace+seccomp  strace -f --seccomp-bpf -e trace=connect,sendto,sendmsg,sendmmsg
  strace          the same without --seccomp-bpf (slower on syscall-heavy code)
  proc            poll /proc/net/{tcp,tcp6,udp,udp6} every 50 ms; misses
                  connects that fail at once and unconnected UDP, so it is the
                  weaker method, used only when strace cannot run
  none            timing only; the log carries no egress verdict

When the command itself has exited, processes it left running in the
background get 2 seconds and are then stopped (SIGTERM, then SIGKILL), so the
log is complete and no traced daemon outlives the run.

Python 3.9+ standard library only; the monitors need Linux.
"""
from __future__ import annotations

import argparse
import datetime
import ipaddress
import json
import os
import platform
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

VERSION = 1
DEFAULT_TCP = ("1.1.1.1:443", "8.8.8.8:53", "9.9.9.9:443", "[2606:4700:4700::1111]:443")
DEFAULT_UDP_DNS = ("8.8.8.8:53", "1.1.1.1:53")
DEFAULT_NAME = "example.com"
SELFTEST_TCP = ("192.0.2.1", 9)  # RFC 5737 TEST-NET-1, never routed
SELFTEST_UDP = ("198.51.100.1", 53)  # RFC 5737 TEST-NET-2
TRACED_SYSCALLS = "connect,sendto,sendmsg,sendmmsg"
LEFTOVER_GRACE_S = 2.0


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _err(exc: BaseException) -> str:
    return "%s: %s" % (type(exc).__name__, exc)


def split_hostport(text: str):
    if text.startswith("["):
        host, sep, port = text[1:].partition("]:")
    else:
        host, sep, port = text.rpartition(":")
    if not sep or not host:
        raise ValueError("expected HOST:PORT or [V6]:PORT, got %r" % text)
    return host, int(port)


def _family(host: str) -> int:
    return socket.AF_INET6 if ":" in host else socket.AF_INET


def is_outbound(ip) -> bool:
    """Anything except loopback and the unspecified address counts as egress."""
    if isinstance(ip, str):
        ip = ipaddress.ip_address(ip)
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (ip.is_loopback or ip.is_unspecified)


# ---------------------------------------------------------------- probe


def probe_tcp(target: str, timeout: float) -> dict:
    host, port = split_hostport(target)
    try:
        sock = socket.socket(_family(host), socket.SOCK_STREAM)
    except OSError as exc:
        return {"target": target, "reached": False, "error": _err(exc)}
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except OSError as exc:
        return {"target": target, "reached": False, "error": _err(exc)}
    finally:
        sock.close()
    return {"target": target, "reached": True, "error": None}


def dns_query(name: str) -> bytes:
    header = struct.pack(">HHHHHH", 0x5151, 0x0100, 1, 0, 0, 0)
    labels = b"".join(bytes([len(p)]) + p.encode("ascii") for p in name.strip(".").split("."))
    return header + labels + b"\x00" + struct.pack(">HH", 1, 1)


def probe_udp_dns(target: str, name: str, timeout: float) -> dict:
    host, port = split_hostport(target)
    try:
        sock = socket.socket(_family(host), socket.SOCK_DGRAM)
    except OSError as exc:
        return {"target": target, "reached": False, "error": _err(exc)}
    sock.settimeout(timeout)
    try:
        sock.sendto(dns_query(name or DEFAULT_NAME), (host, port))
        sock.recvfrom(4096)
    except OSError as exc:  # socket.timeout is an OSError
        return {"target": target, "reached": False, "error": _err(exc)}
    finally:
        sock.close()
    return {"target": target, "reached": True, "error": None}


def probe_name(name: str, timeout: float) -> dict:
    box: dict = {}

    def lookup():
        try:
            infos = socket.getaddrinfo(name, 443, proto=socket.IPPROTO_TCP)
            box["addresses"] = sorted({info[4][0] for info in infos})
        except OSError as exc:
            box["error"] = _err(exc)

    worker = threading.Thread(target=lookup, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return {"name": name, "resolved": False, "error": "no answer within %.0f s" % timeout}
    if "addresses" in box:
        return {"name": name, "resolved": True, "addresses": box["addresses"]}
    return {"name": name, "resolved": False, "error": box.get("error")}


def probe(tcp, udp, name, timeout: float) -> dict:
    result = {
        "time": now_iso(),
        "tcp": [probe_tcp(t, timeout) for t in tcp],
        "udp_dns": [probe_udp_dns(t, name, timeout) for t in udp],
        "name": probe_name(name, timeout * 5) if name else None,
    }
    reached = [r["target"] for r in result["tcp"] + result["udp_dns"] if r["reached"]]
    if result["name"] and result["name"]["resolved"]:
        reached.append("dns:" + name)
    result["reached"] = reached
    result["blocked"] = not reached
    return result


# ---------------------------------------------------------------- strace

_SYSCALL = re.compile(r"\b(connect|sendto|sendmsg|sendmmsg)\(")
_INET4 = re.compile(r'sin_port=htons\((\d+)\), sin_addr=inet_addr\("([0-9.]+)"\)')
_INET6 = re.compile(r'sin6_port=htons\((\d+)\).*?inet_pton\(AF_INET6, "([0-9A-Fa-f:.]+)"')
_RESULT = re.compile(r"\)\s+=\s+(-?\d+|\?)(?:\s+([A-Z][A-Z0-9_]*))?")
_PID = re.compile(r"^(?:\[pid\s+)?(\d+)\]?\s")


def parse_strace_lines(lines) -> list:
    attempts = []
    for line in lines:
        m = _SYSCALL.search(line)
        if not m:
            continue
        found = [("AF_INET", int(p), a) for p, a in _INET4.findall(line)]
        found += [("AF_INET6", int(p), a) for p, a in _INET6.findall(line)]
        for family, port, addr in found:
            try:
                outbound = is_outbound(addr)
            except ValueError:
                continue
            if not outbound:
                continue
            res = _RESULT.search(line, m.end())
            pid = _PID.match(line)
            attempts.append({
                "syscall": m.group(1),
                "family": family,
                "address": addr,
                "port": port,
                "result": res.group(1) if res else None,
                "errno": res.group(2) if res else None,
                "pid": int(pid.group(1)) if pid else None,
                "line": line.rstrip("\n")[:300],
            })
    return attempts


def strace_works(seccomp: bool) -> bool:
    exe = shutil.which("strace")
    if not exe:
        return False
    cmd = [exe, "-f", "-qq"] + (["--seccomp-bpf"] if seccomp else [])
    cmd += ["-e", "trace=connect", "-o", os.devnull, "--", sys.executable, "-c", "pass"]
    try:
        done = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


# ---------------------------------------------------------------- /proc/net

TCP_STATES = {
    "01": "ESTABLISHED", "02": "SYN_SENT", "03": "SYN_RECV", "04": "FIN_WAIT1",
    "05": "FIN_WAIT2", "06": "TIME_WAIT", "07": "CLOSE", "08": "CLOSE_WAIT",
    "09": "LAST_ACK", "0A": "LISTEN", "0B": "CLOSING",
}


def decode_proc_addr(field: str, v6: bool):
    hexaddr, hexport = field.split(":")
    raw = bytes.fromhex(hexaddr)
    if v6:
        raw = b"".join(raw[i:i + 4][::-1] for i in range(0, 16, 4))
    else:
        raw = raw[::-1]
    return ipaddress.ip_address(raw), int(hexport, 16)


def parse_proc_net(text: str, proto: str) -> list:
    v6 = proto.endswith("6")
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            ip, port = decode_proc_addr(parts[2], v6)
        except ValueError:
            continue
        if port == 0 and ip.is_unspecified:
            continue
        if not is_outbound(ip):
            continue
        state = parts[3].upper()
        if ip.version == 6 and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped  # same text on every Python version
        rows.append({
            "proto": proto,
            "address": str(ip),
            "port": port,
            "state": TCP_STATES.get(state, state) if proto.startswith("tcp") else state,
        })
    return rows


class ProcPoller(threading.Thread):
    def __init__(self, root: str = "/proc/net", interval: float = 0.05):
        super().__init__(daemon=True)
        self.root = root
        self.interval = interval
        self.stop_event = threading.Event()
        self.seen: dict = {}

    def poll_once(self):
        for proto in ("tcp", "tcp6", "udp", "udp6"):
            try:
                with open(os.path.join(self.root, proto)) as fh:
                    text = fh.read()
            except OSError:
                continue
            for row in parse_proc_net(text, proto):
                key = (row["proto"], row["address"], row["port"])
                entry = self.seen.setdefault(key, dict(row, first_seen=now_iso(), states=[]))
                if row["state"] not in entry["states"]:
                    entry["states"].append(row["state"])

    def run(self):
        while not self.stop_event.is_set():
            self.poll_once()
            self.stop_event.wait(self.interval)

    def attempts(self) -> list:
        out = []
        for entry in self.seen.values():
            entry = dict(entry)
            entry.pop("state", None)
            out.append(entry)
        return out


# ---------------------------------------------------------------- run


def choose_method(requested: str) -> str:
    if requested == "none":
        return "none"
    if requested in ("auto", "strace+seccomp") and strace_works(True):
        return "strace+seccomp"
    if requested in ("auto", "strace") and strace_works(False):
        return "strace"
    if requested in ("auto", "proc") and os.path.exists("/proc/net/tcp"):
        return "proc"
    if requested == "auto":
        return "none"
    raise SystemExit("egress_check: monitor %r cannot run here" % requested)


def summarize(attempts: list) -> list:
    groups: dict = {}
    for a in attempts:
        key = (a["address"], a["port"])
        g = groups.setdefault(key, {"address": a["address"], "port": a["port"], "count": 0, "example": a})
        g["count"] += 1
    return sorted(groups.values(), key=lambda g: (g["address"], g["port"]))


def _killpg(pgid: int, sig) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def run_monitored(cmd: list, method: str, timeout, keep_trace=None) -> dict:
    rc_fd, rc_path = tempfile.mkstemp(prefix="egress-rc-")
    os.close(rc_fd)
    os.unlink(rc_path)
    inner = ["/bin/sh", "-c", '"$@"; echo $? > "$EGRESS_RC_FILE"', "egress-inner"] + list(cmd)
    env = dict(os.environ, EGRESS_RC_FILE=rc_path)
    trace_path = None
    argv = inner
    if method.startswith("strace"):
        if keep_trace:
            trace_path = keep_trace
        else:
            fd, trace_path = tempfile.mkstemp(prefix="egress-", suffix=".strace")
            os.close(fd)
        argv = [shutil.which("strace"), "-f", "-qq"]
        argv += ["--seccomp-bpf"] if method == "strace+seccomp" else []
        argv += ["-e", "trace=" + TRACED_SYSCALLS, "-o", trace_path, "--"] + inner
    poller = ProcPoller() if method == "proc" else None
    if poller:
        poller.start()
    started_at = now_iso()
    t0 = time.monotonic()
    proc = subprocess.Popen(argv, env=env, start_new_session=True)
    forwarded: list = []

    def forward(signum, _frame):
        forwarded.append(signum)
        _killpg(proc.pid, signum)

    old = {s: signal.signal(s, forward) for s in (signal.SIGINT, signal.SIGTERM)}
    timed_out = False
    leftovers_stopped = False
    cmd_end = None
    try:
        while proc.poll() is None:
            if cmd_end is None and os.path.exists(rc_path) and os.path.getsize(rc_path) > 0:
                cmd_end = time.monotonic()
            if cmd_end is not None and time.monotonic() - cmd_end > LEFTOVER_GRACE_S:
                leftovers_stopped = True
                _killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    _killpg(proc.pid, signal.SIGKILL)
                break
            if timeout and time.monotonic() - t0 > timeout:
                timed_out = True
                _killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(30)
                except subprocess.TimeoutExpired:
                    _killpg(proc.pid, signal.SIGKILL)
                break
            time.sleep(0.1)
        proc.wait()
    finally:
        for s, h in old.items():
            signal.signal(s, h)
    if cmd_end is None and os.path.exists(rc_path) and os.path.getsize(rc_path) > 0:
        cmd_end = time.monotonic()
    wall = (cmd_end if cmd_end is not None else time.monotonic()) - t0
    exit_code = proc.returncode
    try:
        with open(rc_path) as fh:
            exit_code = int(fh.read().strip())
    except (OSError, ValueError):
        pass
    finally:
        if os.path.exists(rc_path):
            os.unlink(rc_path)
    if poller:
        poller.stop_event.set()
        poller.join(5)
        attempts = poller.attempts()
    elif trace_path:
        with open(trace_path, errors="replace") as fh:
            attempts = parse_strace_lines(fh)
        if not keep_trace:
            os.unlink(trace_path)
    else:
        attempts = None
    return {
        "started_at": started_at,
        "wall_seconds": round(wall, 3),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "signals_forwarded": forwarded,
        "leftover_processes_stopped": leftovers_stopped,
        "attempts": attempts,
        "trace_file": keep_trace,
    }


def verdict(method: str, before, after, attempts) -> dict:
    v = {
        "blocked_before": before["blocked"] if before else None,
        "blocked_after": after["blocked"] if after else None,
        "attempt_count": len(attempts) if attempts is not None else None,
    }
    if method == "none" or attempts is None:
        v["egress_check_passed"] = None
        v["reason"] = "monitor none: timing only"
    elif before is None or after is None:
        v["egress_check_passed"] = None
        v["reason"] = "probe skipped: egress block not verified"
    else:
        ok = before["blocked"] and after["blocked"] and not attempts
        v["egress_check_passed"] = bool(ok)
        if not before["blocked"] or not after["blocked"]:
            v["reason"] = "egress was not blocked (harness problem: fix and rerun)"
        elif attempts:
            v["reason"] = "%d outbound attempt(s) recorded" % len(attempts)
        else:
            v["reason"] = "blocked before and after; no outbound attempt recorded"
    return v


def host_info() -> dict:
    info = {"kernel": platform.release(), "machine": platform.machine(), "python": platform.python_version()}
    if hasattr(os, "getuid"):
        info["uid"] = os.getuid()
    return info


def _probe_args(args):
    tcp = args.tcp if args.tcp else list(DEFAULT_TCP)
    udp = args.udp if args.udp else list(DEFAULT_UDP_DNS)
    if args.no_udp:
        udp = []
    name = None if args.no_name else (args.name or DEFAULT_NAME)
    return tcp, udp, name, args.probe_timeout


def _strip_dashes(cmd: list) -> list:
    return cmd[1:] if cmd and cmd[0] == "--" else cmd


def write_json(path, data) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path in (None, "-"):
        sys.stdout.write(text)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def cmd_probe(args) -> int:
    tcp, udp, name, timeout = _probe_args(args)
    result = probe(tcp, udp, name, timeout)
    write_json(args.log, result)
    return 0 if result["blocked"] else 1


def cmd_run(args) -> int:
    cmd = _strip_dashes(args.cmd)
    if not cmd:
        raise SystemExit("egress_check run: no command given")
    tcp, udp, name, timeout = _probe_args(args)
    method = choose_method(args.monitor)
    before = None if args.no_probe else probe(tcp, udp, name, timeout)
    result = run_monitored(cmd, method, args.timeout, args.keep_trace)
    after = None if args.no_probe else probe(tcp, udp, name, timeout)
    attempts = result.pop("attempts")
    log = {
        "tool": "egress_check.py",
        "version": VERSION,
        "command": cmd,
        "monitor": method,
        "host": host_info(),
        "probe_before": before,
        "probe_after": after,
    }
    log.update(result)
    log["attempts"] = summarize(attempts) if attempts is not None else None
    log["verdict"] = verdict(method, before, after, attempts)
    write_json(args.log, log)
    sys.stderr.write("egress_check: monitor=%s exit=%s wall=%.1fs verdict=%s\n" % (
        method, log["exit_code"], log["wall_seconds"], log["verdict"]["egress_check_passed"]))
    return log["exit_code"] if isinstance(log["exit_code"], int) and log["exit_code"] >= 0 else 1


SELFTEST_CODE = """
import socket
s = socket.socket(); s.settimeout(2)
try: s.connect((%r, %d))
except OSError: pass
u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    u.connect((%r, %d)); u.send(b"x")
except OSError: pass
""" % (SELFTEST_TCP + SELFTEST_UDP)


def cmd_selftest(args) -> int:
    tcp, udp, name, timeout = _probe_args(args)
    method = choose_method(args.monitor)
    before = probe(tcp, udp, name, timeout)
    result = run_monitored([sys.executable, "-c", SELFTEST_CODE], method, 60)
    seen = {a["address"] for a in (result["attempts"] or [])}
    wanted = {SELFTEST_TCP[0], SELFTEST_UDP[0]}
    out = {
        "monitor": method,
        "host": host_info(),
        "egress_blocked": before["blocked"],
        "probe": before,
        "detected": sorted(seen & wanted),
        "missed": sorted(wanted - seen),
        "ok": before["blocked"] and wanted <= seen,
    }
    write_json(args.log, out)
    return 0 if out["ok"] else 1


def cmd_parse_strace(args) -> int:
    with open(args.file, errors="replace") as fh:
        write_json("-", summarize(parse_strace_lines(fh)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="action", required=True)

    def probe_opts(sp):
        sp.add_argument("--tcp", action="append", help="HOST:PORT to try (repeatable; default: public resolvers)")
        sp.add_argument("--udp", action="append", help="HOST:PORT for a UDP DNS query (repeatable)")
        sp.add_argument("--no-udp", action="store_true", help="skip the UDP DNS probe")
        sp.add_argument("--name", help="public name to resolve (default %s)" % DEFAULT_NAME)
        sp.add_argument("--no-name", action="store_true", help="skip the name lookup")
        sp.add_argument("--probe-timeout", type=float, default=3.0)

    sp = sub.add_parser("probe", help="prove that egress is blocked")
    probe_opts(sp)
    sp.add_argument("--log", default="-")
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("run", help="run a command under the egress monitor")
    probe_opts(sp)
    sp.add_argument("--log", required=True)
    sp.add_argument("--monitor", default="auto", choices=["auto", "strace+seccomp", "strace", "proc", "none"])
    sp.add_argument("--timeout", type=float, default=None, help="stop the command after this many seconds")
    sp.add_argument("--no-probe", action="store_true", help="skip both probes (verdict becomes null)")
    sp.add_argument("--keep-trace", help="keep the raw strace output at this path")
    sp.add_argument("cmd", nargs=argparse.REMAINDER)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("selftest", help="check that the monitor sees deliberate attempts")
    probe_opts(sp)
    sp.add_argument("--log", default="-")
    sp.add_argument("--monitor", default="auto", choices=["auto", "strace+seccomp", "strace", "proc"])
    sp.set_defaults(func=cmd_selftest)

    sp = sub.add_parser("parse-strace", help="list outbound attempts in an strace file")
    sp.add_argument("file")
    sp.set_defaults(func=cmd_parse_strace)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
