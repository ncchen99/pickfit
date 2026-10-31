#!/usr/bin/env python3
"""Mac L2 (q11, also usable for q12): watch the memory footprint of every
process the answer's steps start, including background servers.
macOS only; Python 3.8+ stdlib (ctypes on libproc).

It reads the same kernel counter that `/usr/bin/time -l` prints as "peak
memory footprint" (rusage_info_v4.ri_lifetime_max_phys_footprint), for every
process that did not exist when the watcher started and that either
  * descends from the shell the steps are typed into (--shell-pid), or
  * belongs to the test user (--uid) and does not run from a system path
    (/System, /usr/libexec, /usr/sbin, /sbin, /usr/bin, /bin, /Library/Apple),
    which covers servers started through launchd or a detached daemon.

The reported number is the largest, over all sampling instants, of the sum of
the peak footprints of the processes alive at that instant. Processes that run
one after another are not added together; a server and a client that run at
the same time are.

Usage (run with sudo so other users' and root processes can be read):
  sudo /usr/bin/python3 footprint_watch.py --uid $(id -u TESTUSER) --shell-pid PID --out DIR
  ... run the steps ...; stop with Ctrl-C or `touch DIR/stop`

Writes DIR/footprint.json (per process and per sample) and prints a summary.
Exit 0 when the reported peak is under --limit-gib (default 12), 1 otherwise.

If the list shows a process the steps did not start (for example a system
agent of the test user that happened to launch), recompute without it:
  python3 footprint_watch.py recompute DIR/footprint.json --exclude-pid PID ...
"""
import argparse
import ctypes
import json
import os
import signal
import subprocess
import sys
import time

RUSAGE_INFO_V4 = 4
PROC_PIDTBSDINFO = 3
SYSTEM_PREFIXES = ("/System/", "/usr/libexec/", "/usr/sbin/", "/sbin/", "/usr/bin/", "/bin/",
                   "/Library/Apple/")


class RusageInfoV4(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in (
        "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups", "ri_interrupt_wkups",
        "ri_pageins", "ri_wired_size", "ri_resident_size", "ri_phys_footprint",
        "ri_proc_start_abstime", "ri_proc_exit_abstime", "ri_child_user_time",
        "ri_child_system_time", "ri_child_pkg_idle_wkups", "ri_child_interrupt_wkups",
        "ri_child_pageins", "ri_child_elapsed_abstime", "ri_diskio_bytesread",
        "ri_diskio_byteswritten", "ri_cpu_time_qos_default", "ri_cpu_time_qos_maintenance",
        "ri_cpu_time_qos_background", "ri_cpu_time_qos_utility", "ri_cpu_time_qos_legacy",
        "ri_cpu_time_qos_user_initiated", "ri_cpu_time_qos_user_interactive",
        "ri_billed_system_time", "ri_serviced_system_time", "ri_logical_writes",
        "ri_lifetime_max_phys_footprint", "ri_instructions", "ri_cycles", "ri_billed_energy",
        "ri_serviced_energy", "ri_interval_max_phys_footprint", "ri_runnable_time")]


class ProcBsdInfo(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint32) for n in (
        "pbi_flags", "pbi_status", "pbi_xstatus", "pbi_pid", "pbi_ppid", "pbi_uid", "pbi_gid",
        "pbi_ruid", "pbi_rgid", "pbi_svuid", "pbi_svgid", "rfu_1")] + [
        ("pbi_comm", ctypes.c_char * 16), ("pbi_name", ctypes.c_char * 32)] + [
        (n, ctypes.c_uint32) for n in ("pbi_nfiles", "pbi_pgid", "pbi_pjobc", "e_tdev", "e_tpgid")] + [
        ("pbi_nice", ctypes.c_int32), ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64)]


libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
libproc.proc_listallpids.argtypes = [ctypes.c_void_p, ctypes.c_int]
libproc.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
libproc.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
libproc.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]


def all_pids():
    n = libproc.proc_listallpids(None, 0)
    buf = (ctypes.c_int * (n + 256))()
    got = libproc.proc_listallpids(buf, ctypes.sizeof(buf))
    return [p for p in buf[:got] if p > 0]


def bsdinfo(pid):
    info = ProcBsdInfo()
    r = libproc.proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, ctypes.byref(info), ctypes.sizeof(info))
    if r != ctypes.sizeof(info):
        return None
    return info


def pidpath(pid):
    buf = ctypes.create_string_buffer(4096)
    r = libproc.proc_pidpath(pid, buf, 4096)
    return buf.value.decode("utf-8", "replace") if r > 0 else ""


def rusage(pid):
    ri = RusageInfoV4()
    if libproc.proc_pid_rusage(pid, RUSAGE_INFO_V4, ctypes.byref(ri)) != 0:
        return None
    return ri


def recompute(path, exclude, limit_gib):
    """Re-derive the peak after the grader excludes processes that the steps did not start."""
    with open(path) as f:
        res = json.load(f)
    ex = set(exclude)
    best_t, best = 0, 0
    for t, _, alive in res["samples"]:
        s = sum(peak for pid, peak in alive if pid not in ex)
        if s > best:
            best_t, best = t, s
    limit = int(limit_gib * (1 << 30))
    print("excluded pids: %s" % (sorted(ex) or "none"))
    print("peak concurrent sum: %.3f GiB at %.1f s (limit %.1f GiB): %s"
          % (best / float(1 << 30), best_t, limit_gib, "PASS" if best < limit else "FAIL"))
    return 0 if best < limit else 1


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "recompute":
        rp = argparse.ArgumentParser(prog="footprint_watch.py recompute")
        rp.add_argument("json")
        rp.add_argument("--exclude-pid", type=int, nargs="*", default=[])
        rp.add_argument("--limit-gib", type=float, default=12.0)
        r = rp.parse_args(argv[1:])
        return recompute(r.json, r.exclude_pid, r.limit_gib)
    ap = argparse.ArgumentParser(description="peak footprint watcher (macOS)")
    ap.add_argument("--uid", type=int, required=True, help="uid of the test user")
    ap.add_argument("--shell-pid", type=int, default=0, help="pid of the shell the steps run in (echo $$)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--limit-gib", type=float, default=12.0)
    ap.add_argument("--duration", type=float, default=0, help="stop after N seconds (testing)")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    stop_file = os.path.join(a.out, "stop")
    if os.path.exists(stop_file):
        os.remove(stop_file)

    me = os.getpid()
    baseline = set()
    for p in all_pids():
        bi = bsdinfo(p)
        baseline.add((p, bi.pbi_start_tvsec if bi else 0))

    procs = {}       # key (pid, start) -> record
    samples = []     # (t, sum of peaks of included processes alive at t)
    stopping = [False]
    signal.signal(signal.SIGINT, lambda *_: stopping.__setitem__(0, True))
    signal.signal(signal.SIGTERM, lambda *_: stopping.__setitem__(0, True))
    t0 = time.time()
    included = set()
    print("watching (uid %d, shell %d); stop with Ctrl-C or: touch %s" % (a.uid, a.shell_pid, stop_file))
    sys.stdout.flush()

    while not stopping[0] and not os.path.exists(stop_file):
        if a.duration and time.time() - t0 > a.duration:
            break
        now = time.time() - t0
        info = {}
        for p in all_pids():
            bi = bsdinfo(p)
            if bi is None:
                continue
            info[p] = bi
        alive_sum = 0
        alive = []
        for p, bi in info.items():
            key = (p, bi.pbi_start_tvsec)
            if key in baseline or p == me:
                continue
            # descendant of the steps' shell?
            desc = False
            q, hops = p, 0
            while a.shell_pid and q > 1 and hops < 64:
                if q == a.shell_pid:
                    desc = True
                    break
                parent = info.get(q)
                q = parent.pbi_ppid if parent else 0
                hops += 1
            if key not in included:
                path = pidpath(p)
                user_proc = bi.pbi_uid == a.uid and not path.startswith(SYSTEM_PREFIXES)
                if not (desc or user_proc):
                    continue
                included.add(key)
                procs[key] = {"pid": p, "ppid": bi.pbi_ppid, "uid": bi.pbi_uid, "path": path,
                              "comm": bi.pbi_comm.decode("utf-8", "replace"),
                              "first_seen_s": round(now, 2), "last_seen_s": round(now, 2),
                              "peak_footprint": 0, "why": "descendant" if desc else "user process"}
            ru = rusage(p)
            rec = procs[key]
            if ru is not None:
                rec["peak_footprint"] = max(rec["peak_footprint"], ru.ri_lifetime_max_phys_footprint)
            rec["last_seen_s"] = round(now, 2)
            alive_sum += rec["peak_footprint"]
            alive.append([p, rec["peak_footprint"]])
        samples.append([round(now, 2), alive_sum, alive])
        time.sleep(a.interval)

    peak_t, peak = max(((x[0], x[1]) for x in samples), key=lambda s: s[1]) if samples else (0, 0)
    limit = int(a.limit_gib * (1 << 30))
    total_all = sum(r["peak_footprint"] for r in procs.values())
    result = {
        "uid": a.uid, "shell_pid": a.shell_pid, "interval_s": a.interval,
        "duration_s": round(time.time() - t0, 1),
        "peak_concurrent_sum_bytes": peak, "peak_at_s": peak_t,
        "sum_of_all_peaks_bytes": total_all,
        "limit_bytes": limit, "pass": peak < limit,
        "processes": sorted(procs.values(), key=lambda r: -r["peak_footprint"]),
        "samples": samples,
    }
    with open(os.path.join(a.out, "footprint.json"), "w") as f:
        json.dump(result, f, indent=1)
    gib = lambda b: b / float(1 << 30)  # noqa: E731
    print("processes watched: %d" % len(procs))
    for r in result["processes"][:15]:
        print("  %8.3f GiB  pid %-6d %-12s %s" % (gib(r["peak_footprint"]), r["pid"], r["why"], r["path"] or r["comm"]))
    print("peak concurrent sum: %.3f GiB at %.1f s (limit %.1f GiB): %s"
          % (gib(peak), peak_t, a.limit_gib, "PASS" if result["pass"] else "FAIL"))
    print("(sum of every peak, for reference: %.3f GiB)" % gib(total_all))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    if sys.platform != "darwin":
        sys.exit("macOS only")
    sys.exit(main())
