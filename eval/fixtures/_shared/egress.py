#!/usr/bin/env python3
"""The one egress check for every L2 fixture ("no outbound connection").

Python 3.8+ standard library only. `run`, `stop`, `probe` and the live part of
`selftest` need Linux and strace; `parse`, `report` and `selftest --parser-only`
run anywhere (for example on the grader's Mac after the files are copied out).

  egress.py run      --out DIR --label L [--timeout S] [--cwd D] [--stdout F] [--stderr F]
                     [--block-network] [--kill-leftovers] [--no-trace] [--inherit-output]
                     (--sh 'COMMAND STRING' | -- ARGV...)
  egress.py stop     --out DIR [--kill]
  egress.py report   --out DIR [--labels L ...] [--since EPOCH] [--until EPOCH] [--json FILE]
  egress.py parse    TRACE [TRACE ...] [--json FILE]
  egress.py probe    [--json FILE]
  egress.py selftest [--out DIR] [--parser-only]

run
  Runs one step under `strace -f`, tracing execve, connect, sendto, sendmsg and
  sendmmsg of the step and every process it starts. `--sh` runs the string with
  /bin/sh -c exactly as the answer gives it (placeholders filled). Writes
  DIR/L.strace (the raw trace), DIR/L.json (command, exit code, times, tracer
  pid, this box's own interface addresses) and the step's output to DIR/L.stdout
  and DIR/L.stderr unless --stdout/--stderr name other files (so a daemon the
  step leaves behind never holds the caller's pipe open); --inherit-output
  keeps the caller's stdout and stderr instead (a pty driver that must see the
  step's output). stdin is the caller's.
  Returns as soon as the step's own command has exited, with its exit code
  (124 after --timeout, 125 when the run could not be set up).
  Processes the step leaves running (a server, a key agent) stay traced until
  `stop`, so their later connections are in the trace too. --kill-leftovers
  instead stops them 2 seconds after the step exits.
  --block-network runs the step in a new network namespace with only loopback
  (as root; where root lacks CAP_SYS_ADMIN, as in Modal's gVisor box, inside a
  new user namespace too, every uid mapped to itself); the namespace, the uid
  mapping and a loopback self-test are recorded in DIR/L.netns.json.
  --no-trace runs the step the same way without strace, for timing only (a
  speed comparison must not pay strace's overhead on one side): it writes no
  trace, and `report` leaves it out unless it is named with --labels.

stop
  Ends every tracer still running in DIR: strace detaches and the processes
  keep running untraced. --kill also stops those processes (SIGTERM, then
  SIGKILL after 10 s). Run it before `report`.

report
  Reads every DIR/*.strace (or only --labels) and gives one verdict. With
  --since/--until (epoch seconds; strace -ttt stamps every line) only attempts
  inside that window count, for example the calls a service started earlier
  makes while one run is being judged; a line without a time stamp always
  counts.
    pass          no egress attempt, every trace shows at least one execve,
                  and no tracer is still running              (exit 0)
    fail          at least one egress attempt                 (exit 1)
    undetermined  no attempt, but a trace is missing or empty, or a tracer is
                  still running (run `stop`): not a verdict on the answer;
                  fix the harness and rerun the step          (exit 2)

parse
  The same classification for traces made by hand (`strace -f -e trace=...`).

probe
  Shows whether the box can reach the internet: TCP connects to public
  addresses and a UDP DNS query sent straight to public resolvers. blocked =
  none of them got through (exit 0; 1 when something did). A lookup of a
  public name through the box's own resolver is reported as `dns_resolves`
  but does not decide `blocked`: Modal's resolver answers even in a sandbox
  with the network blocked (found 2026-10-31), and every name lookup a traced
  step makes is an egress attempt in its trace anyway.

selftest
  Checks the classification on fixed strace lines, then (unless --parser-only)
  runs real steps under the tracer: `true` and a loopback connect must pass; a
  connect to TEST-NET-1, a DNS lookup of a .invalid name, and a connect made
  3 seconds later by a process the step left in the background must each be
  caught. Exit 0 only when every case behaves.

What counts as one egress attempt (calls that failed count too):
  * an AF_INET or AF_INET6 address that is not loopback (127.0.0.0/8, ::1,
    ::ffff:127.0.0.0/104), not unspecified (0.0.0.0, ::) and not one of this
    box's own interface addresses recorded at `run` time;
  * any address, loopback included, on a name-lookup port (53, 853, 5353,
    5355): a local resolver forwards the query out;
  * an AF_INET/AF_INET6 address strace did not decode;
  * a connect to the systemd-resolved socket (/run/systemd/resolve/...);
  * any other socket family that can leave the box (AF_PACKET, AF_VSOCK, ...).
  Not counted: AF_UNIX (other than the resolver), AF_NETLINK, AF_UNSPEC, and
  calls with no address (sends on a socket whose connect was already counted).
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
import tempfile
import time

TRACED = "execve,connect,sendto,sendmsg,sendmmsg"
NET_CALLS = ("connect", "sendto", "sendmsg", "sendmmsg")
DNS_PORTS = {53, 853, 5353, 5355}
RESOLVER_UNIX_PREFIXES = ("/run/systemd/resolve/", "/var/run/systemd/resolve/")
LOCAL_FAMILIES = {"AF_UNIX", "AF_LOCAL", "AF_NETLINK", "AF_UNSPEC"}
EXIT_TIMEOUT, EXIT_SETUP = 124, 125
LEFTOVER_GRACE_S = 2.0

EPOCH_RE = re.compile(r"^\d{9,}\.\d+$")
LINE_RE = re.compile(r"^(?:\[pid\s+(?P<pid1>\d+)\]\s*|(?P<pid2>\d+)\s+)?(?:(?P<ts>\d+(?:[:.]\d+)+)\s+)?"
                     r"(?:(?P<call>\w+)\(|<\.\.\. (?P<resumed>\w+) resumed>)")
SOCKADDR_RE = re.compile(r"\{sa_family=(AF_[A-Z0-9_]+)([^{}]*)\}")
PORT_RE = re.compile(r"sin6?_port=htons\((\d+)\)")
V4_RE = re.compile(r'inet_addr\("([^"]+)"\)')
V6_RE = re.compile(r'inet_pton\(AF_INET6,\s*"([^"]+)"')
UNIX_RE = re.compile(r'sun_path=(@?)"([^"]*)"')
RESULT_RE = re.compile(r"\)\s+=\s+(-?\d+|\?)(?:\s+(E[A-Z0-9]+))?")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def write_json(path, data):
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path in (None, "-"):
        sys.stdout.write(text)
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- classification


def ip_kind(text, self_addrs=()):
    """'local', 'self' or 'remote' for an address string; None when it does not parse."""
    try:
        ip = ipaddress.ip_address(text.split("%")[0])
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback or ip.is_unspecified:
        return "local"
    if str(ip) in self_addrs:
        return "self"
    return "remote"


def classify_line(line, self_addrs=()):
    """(syscall, [entries]) for one strace line; syscall is None for lines that are not traced calls."""
    m = LINE_RE.match(line)
    if not m:
        return None, []
    call = m.group("call") or m.group("resumed")
    if call == "execve":
        return ("execve", []) if m.group("call") else (None, [])
    if call not in NET_CALLS:
        return None, []
    rm = RESULT_RE.search(line)
    result = (rm.group(1) + (" " + rm.group(2) if rm.group(2) else "")) if rm else "unfinished"
    pid = m.group("pid1") or m.group("pid2")
    ts = float(m.group("ts")) if m.group("ts") and EPOCH_RE.match(m.group("ts")) else None
    entries = []
    for family, body in SOCKADDR_RE.findall(line):
        e = {"call": call, "pid": int(pid) if pid else None, "ts": ts, "family": family, "address": None,
             "port": None, "result": result, "egress": False, "reason": ""}
        if family in ("AF_INET", "AF_INET6"):
            pm = PORT_RE.search(body)
            am = (V4_RE if family == "AF_INET" else V6_RE).search(body)
            e["port"] = int(pm.group(1)) if pm else None
            e["address"] = am.group(1) if am else None
            kind = ip_kind(e["address"], self_addrs) if e["address"] else None
            if kind is None:
                e.update(egress=True, reason="address not decoded")
            elif e["port"] in DNS_PORTS:
                e.update(egress=True, reason="name lookup (port %d)" % e["port"])
            elif kind == "remote":
                e.update(egress=True, reason="address outside this box")
            elif kind == "self":
                e["reason"] = "this box's own interface address"
        elif family in ("AF_UNIX", "AF_LOCAL"):
            um = UNIX_RE.search(body)
            e["address"] = (um.group(1) + um.group(2)) if um else None
            if e["address"] and e["address"].startswith(RESOLVER_UNIX_PREFIXES):
                e.update(egress=True, reason="system resolver socket (name lookup)")
        elif family not in LOCAL_FAMILIES:
            e.update(address=body.strip(", ")[:80], egress=True, reason="socket family %s can leave the box" % family)
        entries.append(e)
    return call, entries


def parse_trace(path, self_addrs=(), keep=200, since=None, until=None):
    """Summary of one strace file: execve count, every egress attempt (first `keep` listed), sha256.

    With since/until, attempts stamped outside the window are only counted in `outside_window`.
    """
    out = {"trace": path, "exists": os.path.exists(path), "execve": 0, "net_calls": 0, "egress_attempts": 0,
           "attempts": [], "families": {}, "window": [since, until], "outside_window": 0}
    if not out["exists"]:
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for number, raw in enumerate(fh, 1):
            call, entries = classify_line(raw.rstrip("\n"), self_addrs)
            if call == "execve":
                out["execve"] += 1
            elif call:
                out["net_calls"] += 1
            for e in entries:
                out["families"][e["family"]] = out["families"].get(e["family"], 0) + 1
                if e["egress"] and e["ts"] is not None and ((since is not None and e["ts"] < since)
                                                            or (until is not None and e["ts"] > until)):
                    out["outside_window"] += 1
                elif e["egress"]:
                    out["egress_attempts"] += 1
                    if len(out["attempts"]) < keep:
                        e["line_number"] = number
                        e["line"] = raw.rstrip("\n")[:400]
                        out["attempts"].append(e)
    with open(path, "rb") as fh:
        out["sha256"] = hashlib.sha256(fh.read()).hexdigest()
    return out


def verdict(traces, running=()):
    attempts = sum(t["egress_attempts"] for t in traces)
    empty = [t["trace"] for t in traces if not t["exists"] or t["execve"] == 0]
    if attempts:
        return "fail", "%d egress attempt(s)" % attempts
    if not traces:
        return "undetermined", "no trace to judge"
    if empty:
        return "undetermined", "no evidence that tracing worked (missing or no execve): %s" % ", ".join(empty)
    if running:
        return "undetermined", "tracer still running for %s: run `egress.py stop` first" % ", ".join(running)
    return "pass", "no egress attempt in %d trace(s)" % len(traces)


# ---------------------------------------------------------------- this box


def self_addresses():
    """This box's own interface addresses (best effort, from /proc)."""
    addrs = set()
    try:
        with open("/proc/net/fib_trie", encoding="utf-8") as fh:
            last = None
            for line in fh:
                m = re.search(r"\|--\s+(\d+\.\d+\.\d+\.\d+)", line)
                if m:
                    last = m.group(1)
                elif "/32 host LOCAL" in line and last:
                    addrs.add(last)
    except OSError:
        pass
    try:
        with open("/proc/net/if_inet6", encoding="utf-8") as fh:
            for line in fh:
                h = line.split()[0]
                if len(h) == 32:
                    addrs.add(str(ipaddress.IPv6Address(bytes.fromhex(h))))
    except (OSError, ValueError, IndexError):
        pass
    return sorted(a for a in addrs if ip_kind(a) == "remote")


def alive(pid, marker="strace"):
    """True when pid runs and is still the tracer (guards against pid reuse)."""
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as fh:
            return marker.encode() in fh.read()
    except (OSError, TypeError):
        return False


def _killpg(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


# ---------------------------------------------------------------- run / stop


CLONE_NEWUSER, CLONE_NEWNET = 0x10000000, 0x40000000


def _unshare(flags):
    import ctypes
    if hasattr(os, "unshare"):
        os.unshare(flags)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.unshare(flags) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


def _user_and_net_namespace():
    """New user + network namespaces, every uid and gid mapped to itself.

    For a box whose root lacks CAP_SYS_ADMIN (Modal's gVisor). A helper forked before the unshare
    stays in the original user namespace, where it has CAP_SETUID, and writes this process's
    maps; only then is uid 1000 still uid 1000 inside. Returns the mapping it got.
    """
    ready_r, ready_w = os.pipe()
    done_r, done_w = os.pipe()
    helper = os.fork()
    if helper == 0:
        os.close(ready_w)
        os.close(done_r)
        os.read(ready_r, 1)
        parent = os.getppid()
        result = b"full"
        try:
            for name in ("uid_map", "gid_map"):
                with open("/proc/%d/%s" % (parent, name), "w") as fh:
                    fh.write("0 0 4294967295\n")
        except OSError:
            result = b"none"
        os.write(done_w, result)
        os._exit(0)
    os.close(ready_r)
    os.close(done_w)
    _unshare(CLONE_NEWUSER | CLONE_NEWNET)
    os.write(ready_w, b"x")
    mapping = os.read(done_r, 8).decode() or "none"
    os.waitpid(helper, 0)
    if mapping != "full":  # fall back to mapping only ourselves (root) from inside
        with open("/proc/self/setgroups", "w") as fh:
            fh.write("deny")
        for name, ident in (("uid_map", os.getuid()), ("gid_map", os.getgid())):
            with open("/proc/self/" + name, "w") as fh:
                fh.write("0 %d 1\n" % ident)
        mapping = "root only"
    return mapping


def _loopback_works():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        cli = socket.create_connection(srv.getsockname(), timeout=3)
        cli.close()
        return True
    except OSError:
        return False
    finally:
        srv.close()


def _netns_exec(info_path, cmd):
    """Internal: a network namespace with only loopback, checked and recorded, then exec CMD.

    A plain network namespace when this process may create one; otherwise (Modal's gVisor box:
    root without CAP_SYS_ADMIN) a user namespace with it, every uid mapped to itself.
    """
    import fcntl
    info = {"ok": False}
    try:
        try:
            _unshare(CLONE_NEWNET)
            info["namespaces"] = "net"
        except PermissionError:
            info["namespaces"] = "user+net"
            info["uid_mapping"] = _user_and_net_namespace()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            flags = struct.unpack("16sh", fcntl.ioctl(s.fileno(), 0x8913, struct.pack("16sh22x", b"lo", 0))[:18])[1]
            fcntl.ioctl(s.fileno(), 0x8914, struct.pack("16sh22x", b"lo", flags | 0x1))  # SIOCSIFFLAGS IFF_UP
            info["lo_up"] = "set"
        except OSError as exc:
            info["lo_up"] = "ioctl refused (%s); loopback tested below" % exc.strerror
        finally:
            s.close()
        info["interfaces"] = sorted(n for _, n in socket.if_nameindex())
        info["loopback_works"] = _loopback_works()
    except Exception as exc:  # noqa: BLE001
        info["error"] = repr(exc)
        write_json(info_path, info)
        sys.stderr.write("egress: cannot create a network namespace: %r\n" % (exc,))
        os._exit(EXIT_SETUP)
    info["ok"] = info["interfaces"] == ["lo"] and info["loopback_works"]
    write_json(info_path, info)
    if not info["ok"]:
        sys.stderr.write("egress: the namespace is not loopback-only and working: %r\n" % (info,))
        os._exit(EXIT_SETUP)
    os.execvp(cmd[0], cmd)


def cmd_run(a):
    argv = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else list(a.cmd)
    if bool(a.sh) == bool(argv):
        raise SystemExit("egress run: give either --sh 'COMMAND' or -- ARGV")
    os.makedirs(a.out, exist_ok=True)
    base = os.path.join(os.path.abspath(a.out), a.label)
    trace, meta_path, rc_path = base + ".strace", base + ".json", base + ".rc"
    for path in (trace, rc_path):
        if os.path.exists(path):
            os.unlink(path)
    strace = None if a.no_trace else shutil.which("strace")
    meta = {"tool": "egress.py", "label": a.label, "command": a.sh if a.sh else argv, "shell": bool(a.sh),
            "cwd": os.path.abspath(a.cwd or "."), "trace": None if a.no_trace else trace, "traced": not a.no_trace,
            "block_network": a.block_network, "timeout_s": a.timeout, "self_addresses": self_addresses(),
            "strace": strace}
    if not strace and not a.no_trace:
        meta.update(exit_code=EXIT_SETUP, error="strace not found")
        write_json(meta_path, meta)
        sys.stderr.write("egress: strace not found\n")
        return EXIT_SETUP
    # The rc file is written when the step's own command exits; $0 carries its path.
    if a.sh:
        inner = ["/bin/sh", "-c", '/bin/sh -c "$1"; echo $? > "$0"', rc_path, a.sh]
    else:
        inner = ["/bin/sh", "-c", '"$@"; echo $? > "$0"', rc_path] + argv
    full = inner if a.no_trace else [strace, "-f", "-qq", "-ttt", "-s", "200", "-e", "trace=" + TRACED,
                                      "-e", "signal=none", "-o", trace, "--"] + inner
    info_path = base + ".netns.json"
    if a.block_network:
        full = [sys.executable, os.path.abspath(__file__), "_netns-exec", info_path, "--"] + full
    stdout_path = a.stdout or base + ".stdout"
    stderr_path = a.stderr or base + ".stderr"
    meta.update(stdout=None if a.inherit_output else stdout_path, stderr=None if a.inherit_output else stderr_path,
                started_at=now_iso(), started_epoch=time.time())
    t0 = time.monotonic()
    if a.inherit_output:
        proc = subprocess.Popen(full, cwd=a.cwd, start_new_session=True)
    else:
        with open(stdout_path, "wb") as so, open(stderr_path, "wb") as se:
            proc = subprocess.Popen(full, cwd=a.cwd, stdout=so, stderr=se, start_new_session=True)
    meta["tracer_pid"] = proc.pid
    write_json(meta_path, meta)
    timed_out, ended = False, None
    while True:
        if ended is None and os.path.exists(rc_path) and os.path.getsize(rc_path) > 0:
            ended = time.monotonic()
        if proc.poll() is not None:
            break
        if ended is not None and (not a.kill_leftovers or time.monotonic() - ended > LEFTOVER_GRACE_S):
            break
        if a.timeout and time.monotonic() - t0 > a.timeout:
            timed_out = True
            _killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                _killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            break
        time.sleep(0.05)
    if ended is None and os.path.exists(rc_path) and os.path.getsize(rc_path) > 0:
        ended = time.monotonic()
    if a.kill_leftovers and not timed_out and ended is not None:
        time.sleep(max(0.0, LEFTOVER_GRACE_S - (time.monotonic() - ended)))
        try:
            os.killpg(proc.pid, 0)
            meta["leftovers_killed"] = True
        except (ProcessLookupError, PermissionError):
            meta["leftovers_killed"] = False
        _killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            _killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    exit_code = EXIT_TIMEOUT if timed_out else None
    if exit_code is None:
        try:
            with open(rc_path) as fh:
                exit_code = int(fh.read().strip())
        except (OSError, ValueError):
            exit_code = EXIT_SETUP if proc.returncode in (None, 0) else proc.returncode
            meta["error"] = "the step's exit status was not recorded (tracer exit %s)" % proc.returncode
    end = ended if ended is not None else time.monotonic()
    meta.update(ended_at=now_iso(), ended_epoch=round(time.time() - (time.monotonic() - end), 3),
                duration_s=round(end - t0, 3), timed_out=timed_out, exit_code=exit_code,
                tracer_running=proc.poll() is None)
    if a.block_network:
        meta["netns"] = read_json(info_path) or {"ok": False, "error": "no namespace info written"}
        if not meta["netns"].get("ok"):
            meta["exit_code"] = exit_code = EXIT_SETUP
    write_json(meta_path, meta)
    sys.stderr.write("egress: %s exit=%s timed_out=%s %.1fs tracer_running=%s trace=%s\n" % (
        a.label, exit_code, timed_out, meta["duration_s"], meta["tracer_running"], trace))
    return exit_code if 0 <= exit_code <= 255 else 1


def run_metas(out):
    metas = {}
    for name in sorted(os.listdir(out)) if os.path.isdir(out) else []:
        if name.endswith(".json") and not name.endswith(".netns.json"):
            meta = read_json(os.path.join(out, name))
            if isinstance(meta, dict) and meta.get("tool") == "egress.py":
                metas[meta["label"]] = (os.path.join(out, name), meta)
    return metas


def cmd_stop(a):
    for label, (path, meta) in run_metas(a.out).items():
        pid = meta.get("tracer_pid")
        if not pid or not alive(pid):
            continue
        if a.kill:
            _killpg(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)  # strace detaches; the processes keep running untraced
        for _ in range(100):
            if not alive(pid):
                break
            time.sleep(0.1)
        if alive(pid):
            _killpg(pid, signal.SIGKILL) if a.kill else os.kill(pid, signal.SIGKILL)
        meta.update(tracer_running=False, stopped_at=now_iso(), stopped_with_kill=a.kill)
        write_json(path, meta)
        sys.stderr.write("egress: stopped the tracer of %s\n" % label)
    return 0


STEP_FIELDS = ("label", "command", "exit_code", "timed_out", "duration_s", "started_at", "started_epoch",
               "ended_epoch", "block_network", "netns")


def load_step(out, label, meta=None, since=None, until=None):
    """(step fields, parsed trace, tracer still running) for one label of a run folder."""
    if meta is None:
        meta = read_json(os.path.join(out, label + ".json")) or {}
    path = meta.get("trace") or os.path.join(out, label + ".strace")
    if not os.path.exists(path):
        path = os.path.join(out, label + ".strace")  # copied out of the box: same folder
    t = parse_trace(path, meta.get("self_addresses") or (), since=since, until=until)
    t["label"] = label
    running = bool(meta.get("tracer_pid") and meta.get("tracer_running") and alive(meta["tracer_pid"]))
    return {k: meta.get(k) for k in STEP_FIELDS}, t, running


def step_verdicts(out, labels, since=None, until=None):
    """One verdict per step, for check scripts that judge steps separately (q06, q07, q18, q19)."""
    rows = []
    for label in labels:
        step, t, running = load_step(out, label, since=since, until=until)
        result, reason = verdict([t], [label] if running else ())
        rows.append(dict(step, label=label, result=result, reason=reason,
                         first_attempts=[x["line"] for x in t["attempts"][:5]]))
    return rows


def window_verdict(out, label, since, until):
    """One run of several in one folder (q18, q19): the run's own step counts in full, every other traced
    step (config steps, services, earlier runs' leftovers) only inside [since, until]."""
    traces, running = [], []
    for other, (_, meta) in run_metas(out).items():
        if not meta.get("traced", True) and other != label:
            continue
        own = other == label
        _, t, still = load_step(out, other, meta, None if own else since, None if own else until)
        traces.append(t)
        if still:
            running.append(other)
    if label not in run_metas(out):
        traces.append(dict(parse_trace(os.path.join(out, label + ".strace")), label=label))
    result, reason = verdict(traces, running)
    return {"result": result, "reason": reason, "window": [since, until],
            "first_attempts": [x["line"] for t in traces for x in t["attempts"]][:5]}


def cmd_report(a):
    metas = run_metas(a.out)
    labels = a.labels or sorted(label for label, (_, meta) in metas.items() if meta.get("traced", True))
    traces, running, steps = [], [], []
    for label in labels:
        step, t, still = load_step(a.out, label, metas.get(label, (None, {}))[1], a.since, a.until)
        traces.append(t)
        steps.append(step)
        if still:
            running.append(label)
    result, reason = verdict(traces, running)
    report = {"tool": "egress.py report", "at": now_iso(), "result": result, "reason": reason,
              "steps": steps, "traces": traces}
    write_json(a.json, report) if a.json else None
    for t in traces:
        for x in t["attempts"]:
            print("EGRESS %s:%s pid=%s %s %s %s:%s -> %s (%s)" % (
                t["label"], x["line_number"], x["pid"], x["call"], x["family"], x["address"], x["port"],
                x["result"], x["reason"]))
    print("egress: %s (%s)" % (result.upper(), reason))
    return {"pass": 0, "fail": 1}.get(result, 2)


def cmd_parse(a):
    traces = [parse_trace(p) for p in a.traces]
    result, reason = verdict(traces)
    write_json(a.json, {"result": result, "reason": reason, "traces": traces}) if a.json else None
    for t in traces:
        for x in t["attempts"]:
            print("EGRESS %s:%s %s %s %s:%s (%s)" % (t["trace"], x["line_number"], x["call"], x["family"],
                                                    x["address"], x["port"], x["reason"]))
    print("egress: %s (%s)" % (result.upper(), reason))
    return {"pass": 0, "fail": 1}.get(result, 2)


# ---------------------------------------------------------------- probe

PROBE_TCP = (("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 443), ("2606:4700:4700::1111", 443))
PROBE_UDP = (("8.8.8.8", 53), ("1.1.1.1", 53))
PROBE_NAME = "example.com"


def dns_query(name):
    header = struct.pack(">HHHHHH", 0x5151, 0x0100, 1, 0, 0, 0)
    labels = b"".join(bytes([len(p)]) + p.encode("ascii") for p in name.split("."))
    return header + labels + b"\x00" + struct.pack(">HH", 1, 1)


def probe(timeout=3.0):
    rows = []
    for host, port in PROBE_TCP:
        fam = socket.AF_INET6 if ":" in host else socket.AF_INET
        row = {"proto": "tcp", "target": "%s:%d" % (host, port), "reached": False, "error": None}
        try:
            s = socket.socket(fam, socket.SOCK_STREAM)
            s.settimeout(timeout)
            try:
                s.connect((host, port))
                row["reached"] = True
            finally:
                s.close()
        except OSError as exc:
            row["error"] = "%s: %s" % (type(exc).__name__, exc)
        rows.append(row)
    for host, port in PROBE_UDP:
        row = {"proto": "udp-dns", "target": "%s:%d" % (host, port), "reached": False, "error": None}
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            try:
                s.sendto(dns_query(PROBE_NAME), (host, port))
                s.recvfrom(4096)
                row["reached"] = True
            finally:
                s.close()
        except OSError as exc:
            row["error"] = "%s: %s" % (type(exc).__name__, exc)
        rows.append(row)
    try:
        resolved = sorted({i[4][0] for i in socket.getaddrinfo(PROBE_NAME, 443, proto=socket.IPPROTO_TCP)})
    except OSError:
        resolved = []
    reached = [r["target"] for r in rows if r["reached"]]
    return {"tool": "egress.py probe", "at": now_iso(), "checks": rows, "reached": reached,
            "blocked": not reached, "dns_resolves": bool(resolved), "resolved": resolved}


def cmd_probe(a):
    result = probe(a.timeout)
    write_json(a.json or "-", result)
    return 0 if result["blocked"] else 1


# ---------------------------------------------------------------- selftest

# (strace line, expected egress flag per socket address in the line)
PARSER_CASES = [
    ('100 connect(4, {sa_family=AF_INET, sin_port=htons(8080), sin_addr=inet_addr("127.0.0.1")}, 16) = 0', [False]),
    ('100 connect(5, {sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("127.0.0.53")}, 16) = 0', [True]),
    ('102 1761800000.123456 connect(6, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("93.184.215.14")}, 16 <unfinished ...>', [True]),
    ('102 1761800000.223456 <... connect resumed>) = -1 ENETUNREACH (Network is unreachable)', []),
    ('103 sendto(7, "\\x12\\x34"..., 40, MSG_NOSIGNAL, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), '
     'inet_pton(AF_INET6, "2606:2800:21f:cb07:6820:80da:af6b:8b2c", &sin6_addr), sin6_scope_id=0}, 28) = 40', [True]),
    ('103 connect(8, {sa_family=AF_INET6, sin6_port=htons(9000), sin6_flowinfo=htonl(0), '
     'inet_pton(AF_INET6, "::1", &sin6_addr), sin6_scope_id=0}, 28) = 0', [False]),
    ('108 connect(3, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), '
     'inet_pton(AF_INET6, "::ffff:127.0.0.1", &sin6_addr), sin6_scope_id=0}, 28) = 0', [False]),
    ('104 sendto(9, "x", 1, 0, NULL, 0) = 1', []),
    ('[pid   105] connect(3, {sa_family=AF_INET, sin_port=htons(80), sin_addr=inet_addr("10.1.2.3")}, 16) = -1 ENETUNREACH', [True]),
    ('106 connect(3, {sa_family=AF_UNSPEC, sa_data="\\0\\0"}, 16) = 0', [False]),
    ('107 sendmsg(3, {msg_name={sa_family=AF_NETLINK, nl_pid=0, nl_groups=00000000}, msg_namelen=12}, 0) = 20', [False]),
    ('109 connect(3, {sa_family=AF_INET, sin_port=htons(80), sin_addr=inet_addr("0.0.0.0")}, 16) = 0', [False]),
    ('110 connect(8, {sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"}, 110) = -1 ENOENT', [False]),
    ('110 connect(8, {sa_family=AF_UNIX, sun_path="/run/systemd/resolve/io.systemd.Resolve"}, 110) = -1 ENOENT', [True]),
    ('110 connect(8, {sa_family=AF_UNIX, sun_path="/tmp/app.sock"}, 110) = 0', [False]),
    ('111 sendmmsg(3, [{msg_hdr={msg_name={sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("8.8.8.8")}, '
     'msg_namelen=16}}, {msg_hdr={msg_name={sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("8.8.4.4")}, '
     'msg_namelen=16}}], 2, MSG_NOSIGNAL) = 2', [True, True]),
    ('112 sendto(3, "x", 1, 0, {sa_family=AF_PACKET, sll_protocol=htons(ETH_P_ALL), sll_ifindex=2}, 20) = 1', [True]),
    ('113 connect(3, {sa_family=AF_VSOCK, svm_cid=2, svm_port=52}, 16) = 0', [True]),
    ('114 connect(3, {sa_family=AF_INET, sin_port=htons(5353), sin_addr=inet_addr("224.0.0.251")}, 16) = 0', [True]),
    ('115 connect(3, {sa_family=AF_INET, sin_port=htons(8080), sin_addr=inet_addr("10.0.0.5")}, 16) = 0', [False]),
    ('116 execve("/bin/sh", ["sh", "-c", "x"], 0x7ffd /* 5 vars */) = 0', []),
]
SELF_ADDRS = ("10.0.0.5",)

CONNECT = ("import socket,sys\ns=socket.socket(socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET)\n"
           "s.settimeout(2)\ntry: s.connect((sys.argv[1], int(sys.argv[2])))\nexcept OSError: pass\n")
LIVE_CASES = [
    ("true", ["true"], "pass"),
    ("loopback", [sys.executable, "-c", CONNECT, "127.0.0.1", "9"], "pass"),
    ("testnet", [sys.executable, "-c", CONNECT, "192.0.2.1", "9"], "fail"),
    ("dns", [sys.executable, "-c", "import socket\ntry: socket.getaddrinfo('egress-selftest.invalid', 80)\n"
                                   "except OSError: pass\n"], "fail"),
    ("leftover", ["/bin/sh", "-c", "(sleep 3; %s -c \"$0\" 198.51.100.1 9) >/dev/null 2>&1 &" % sys.executable, CONNECT],
     "fail"),
]


def parser_selftest():
    bad = []
    for line, want in PARSER_CASES:
        got = [e["egress"] for e in classify_line(line, SELF_ADDRS)[1]]
        if got != want:
            bad.append({"line": line[:100], "want": want, "got": got})
    return {"cases": len(PARSER_CASES), "failed": bad, "ok": not bad}


def cmd_selftest(a):
    out = {"tool": "egress.py selftest", "at": now_iso(), "parser": parser_selftest()}
    if not a.parser_only:
        work = a.out or tempfile.mkdtemp(prefix="egress-selftest-")
        live = []
        for label, argv, want in LIVE_CASES:
            ns = argparse.Namespace(out=work, label=label, sh=None, cmd=["--"] + argv, timeout=60, cwd=None,
                                    stdout=None, stderr=None, block_network=False, kill_leftovers=False,
                                    no_trace=False, inherit_output=False)
            cmd_run(ns)
            if label == "leftover":
                time.sleep(5)
            cmd_stop(argparse.Namespace(out=work, kill=True))
            meta = read_json(os.path.join(work, label + ".json")) or {}
            got, reason = verdict([parse_trace(os.path.join(work, label + ".strace"), meta.get("self_addresses") or ())])
            live.append({"case": label, "want": want, "got": got, "reason": reason, "ok": got == want})
        out["live"] = {"dir": work, "cases": live, "ok": all(c["ok"] for c in live)}
    out["ok"] = out["parser"]["ok"] and (a.parser_only or out["live"]["ok"])
    write_json("-", out)
    return 0 if out["ok"] else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["_netns-exec"]:
        rest = argv[2:]
        _netns_exec(argv[1], rest[1:] if rest[:1] == ["--"] else rest)
        return 0
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="action", required=True)
    sp = sub.add_parser("run")
    sp.add_argument("--out", required=True)
    sp.add_argument("--label", required=True)
    sp.add_argument("--sh", help="a command string, run with /bin/sh -c")
    sp.add_argument("--timeout", type=float)
    sp.add_argument("--cwd")
    sp.add_argument("--stdout")
    sp.add_argument("--stderr")
    sp.add_argument("--block-network", action="store_true")
    sp.add_argument("--kill-leftovers", action="store_true")
    sp.add_argument("--no-trace", action="store_true", help="timing only: no strace, no egress verdict")
    sp.add_argument("--inherit-output", action="store_true", help="keep the caller's stdout and stderr")
    sp.add_argument("cmd", nargs=argparse.REMAINDER)
    sp.set_defaults(func=cmd_run)
    sp = sub.add_parser("stop")
    sp.add_argument("--out", required=True)
    sp.add_argument("--kill", action="store_true")
    sp.set_defaults(func=cmd_stop)
    sp = sub.add_parser("report")
    sp.add_argument("--out", required=True)
    sp.add_argument("--labels", nargs="+")
    sp.add_argument("--since", type=float, help="epoch seconds: ignore attempts stamped before")
    sp.add_argument("--until", type=float, help="epoch seconds: ignore attempts stamped after")
    sp.add_argument("--json")
    sp.set_defaults(func=cmd_report)
    sp = sub.add_parser("parse")
    sp.add_argument("traces", nargs="+")
    sp.add_argument("--json")
    sp.set_defaults(func=cmd_parse)
    sp = sub.add_parser("probe")
    sp.add_argument("--json")
    sp.add_argument("--timeout", type=float, default=3.0)
    sp.set_defaults(func=cmd_probe)
    sp = sub.add_parser("selftest")
    sp.add_argument("--out")
    sp.add_argument("--parser-only", action="store_true")
    sp.set_defaults(func=cmd_selftest)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
