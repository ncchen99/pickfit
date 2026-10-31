#!/usr/bin/env python3
"""q14 L2: the container's memory peak.

  read   print the cgroup's own counters (cgroup v2 memory.peak, or the v1
         max_usage_in_bytes) plus the limit, OOM-kill count and the anon/file
         split; with --watch-log it also folds in a poller's maximum.
  watch  poll until SIGTERM/SIGINT (or --duration): the cgroup's current usage
         and the summed RSS of every process; write the maxima as JSON.
         Only needed when the kernel has no memory.peak file.

Rule written into the log ("passed"): the peak is below --threshold-bytes
(default 8 GiB) and the cgroup reports no OOM kill. The peak comes from
memory.peak when it exists, else from the v1 counter, else from the watch
log's maximum of memory.current, else from its summed RSS; the log names the
method used.

Python 3.9+ standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time

GIB = 1024 ** 3


def _read(path):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return None


def _int(text):
    if text is None or text == "max":
        return None
    try:
        return int(text.split()[0])
    except (ValueError, IndexError):
        return None


def _kv(text) -> dict:
    out = {}
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                out[parts[0]] = int(parts[1])
            except ValueError:
                pass
    return out


def read_cgroup(root: str = "/sys/fs/cgroup") -> dict:
    v2_peak = os.path.join(root, "memory.peak")
    v2_current = os.path.join(root, "memory.current")
    if os.path.exists(v2_peak) or os.path.exists(v2_current):
        stat = _kv(_read(os.path.join(root, "memory.stat")))
        return {
            "cgroup": "v2",
            "peak_bytes": _int(_read(v2_peak)),
            "current_bytes": _int(_read(v2_current)),
            "limit_bytes": _int(_read(os.path.join(root, "memory.max"))),
            "oom_kill": _kv(_read(os.path.join(root, "memory.events"))).get("oom_kill"),
            "stat": {k: stat[k] for k in ("anon", "file", "shmem", "kernel") if k in stat},
        }
    v1 = os.path.join(root, "memory")
    if os.path.exists(os.path.join(v1, "memory.max_usage_in_bytes")):
        oom = _kv(_read(os.path.join(v1, "memory.oom_control")))
        stat = _kv(_read(os.path.join(v1, "memory.stat")))
        return {
            "cgroup": "v1",
            "peak_bytes": _int(_read(os.path.join(v1, "memory.max_usage_in_bytes"))),
            "current_bytes": _int(_read(os.path.join(v1, "memory.usage_in_bytes"))),
            "limit_bytes": _int(_read(os.path.join(v1, "memory.limit_in_bytes"))),
            "oom_kill": oom.get("oom_kill"),
            "stat": {k: stat[k] for k in ("rss", "cache", "shmem") if k in stat},
        }
    return {"cgroup": None, "peak_bytes": None, "current_bytes": None, "limit_bytes": None, "oom_kill": None, "stat": {}}


def rss_sum(proc_root: str = "/proc") -> int:
    total = 0
    try:
        names = os.listdir(proc_root)
    except OSError:
        return 0
    for name in names:
        if not name.isdigit():
            continue
        text = _read(os.path.join(proc_root, name, "status"))
        for line in (text or "").splitlines():
            if line.startswith("VmRSS:"):
                total += int(line.split()[1]) * 1024
                break
    return total


def decide(cg: dict, watch, threshold: int) -> dict:
    if cg.get("peak_bytes") is not None:
        method, peak = "cgroup %s peak counter" % cg["cgroup"], cg["peak_bytes"]
    elif watch and watch.get("max_current_bytes"):
        method, peak = "watch: max of cgroup current usage", watch["max_current_bytes"]
    elif watch and watch.get("max_rss_sum_bytes"):
        method, peak = "watch: max of summed process RSS", watch["max_rss_sum_bytes"]
    else:
        return {"method": None, "peak_bytes": None, "passed": None, "reason": "no memory counter available"}
    oom = cg.get("oom_kill")
    passed = peak < threshold and not oom
    return {
        "method": method,
        "peak_bytes": peak,
        "peak_gib": round(peak / GIB, 3),
        "threshold_bytes": threshold,
        "oom_kill": oom,
        "passed": passed,
        "reason": "peak below threshold, no OOM kill" if passed else (
            "OOM kill recorded" if oom else "peak reached the threshold"),
    }


def cmd_read(args) -> int:
    cg = read_cgroup(args.cgroup_root)
    watch = None
    if args.watch_log:
        with open(args.watch_log) as fh:
            watch = json.load(fh)
    out = {"tool": "mem_peak.py", "cgroup_counters": cg, "watch": watch,
           "decision": decide(cg, watch, args.threshold_bytes)}
    text = json.dumps(out, indent=2) + "\n"
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text)
    sys.stdout.write(text)
    passed = out["decision"]["passed"]
    return 0 if passed else 1


def cmd_watch(args) -> int:
    stop = {"flag": False}

    def handler(_signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
    max_current = 0
    max_rss = 0
    samples = 0
    t0 = time.monotonic()
    while not stop["flag"]:
        cg = read_cgroup(args.cgroup_root)
        if cg.get("current_bytes"):
            max_current = max(max_current, cg["current_bytes"])
        max_rss = max(max_rss, rss_sum(args.proc_root))
        samples += 1
        if args.duration and time.monotonic() - t0 >= args.duration:
            break
        time.sleep(args.interval)
    out = {"tool": "mem_peak.py watch", "samples": samples, "interval_s": args.interval,
           "seconds": round(time.monotonic() - t0, 1), "max_current_bytes": max_current or None,
           "max_rss_sum_bytes": max_rss or None}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="action", required=True)
    sp = sub.add_parser("read")
    sp.add_argument("--cgroup-root", default="/sys/fs/cgroup")
    sp.add_argument("--watch-log")
    sp.add_argument("--threshold-bytes", type=int, default=8 * GIB)
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_read)
    sp = sub.add_parser("watch")
    sp.add_argument("--cgroup-root", default="/sys/fs/cgroup")
    sp.add_argument("--proc-root", default="/proc")
    sp.add_argument("--interval", type=float, default=0.5)
    sp.add_argument("--duration", type=float, default=None)
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_watch)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
