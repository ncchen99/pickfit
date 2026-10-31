#!/usr/bin/env python3
"""q13 L2: disk growth of every writable filesystem, model mount excluded.

  snapshot  list the writable mounts (from /proc/self/mounts, or --mount when
            given), run `du -sxk` on each and write the result as JSON.
  compare   growth = sum(after) - sum(before) over the mounts present in
            either snapshot; pass when growth < 5% of the model file's size.

Which mounts count: every mount whose options include "rw", minus kernel
pseudo-filesystems (proc, sysfs, cgroup, devpts, mqueue, ...), minus the
model mount (--exclude) and anything under it. tmpfs mounts (/dev/shm, /tmp,
/run) do count: a copy into RAM-backed storage is still a copy. Mounts that
share a device are measured once (shortest mount point).

Python 3.9+ standard library plus POSIX `du`.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys

PSEUDO = {
    "proc", "sysfs", "cgroup", "cgroup2", "devpts", "mqueue", "debugfs", "tracefs",
    "securityfs", "pstore", "bpf", "configfs", "fusectl", "hugetlbfs", "autofs",
    "binfmt_misc", "nsfs", "efivarfs", "selinuxfs", "rpc_pipefs", "devtmpfs",
}


def unescape(path: str) -> str:
    # /proc/self/mounts escapes space, tab, newline and backslash as octal
    for code, ch in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
        path = path.replace(code, ch)
    return path


def parse_mounts(text: str) -> list:
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        rows.append({"device": parts[0], "mountpoint": unescape(parts[1]), "fstype": parts[2],
                     "options": parts[3].split(",")})
    return rows


def _under(path: str, root: str) -> bool:
    path, root = os.path.normpath(path), os.path.normpath(root)
    return path == root or path.startswith(root.rstrip("/") + "/")


def writable_mounts(rows: list, excludes: list) -> list:
    chosen = []
    for r in rows:
        if "rw" not in r["options"] or r["fstype"] in PSEUDO:
            continue
        if any(_under(r["mountpoint"], ex) for ex in excludes):
            continue
        if r["mountpoint"].startswith(("/proc", "/sys")):
            continue
        chosen.append(r)
    # one entry per device id
    by_dev: dict = {}
    for r in sorted(chosen, key=lambda r: len(r["mountpoint"])):
        try:
            dev = os.stat(r["mountpoint"]).st_dev
        except OSError:
            continue
        by_dev.setdefault(dev, r)
    return sorted(by_dev.values(), key=lambda r: r["mountpoint"])


def du_kib(path: str, excludes: list) -> dict:
    cmd = ["du", "-sxk", path]
    done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    kib = None
    if done.stdout.strip():
        try:
            kib = int(done.stdout.split()[0])
        except ValueError:
            kib = None
    # du -x stays on one device, so a model mount below `path` is skipped; but a
    # bind mount of the same device would not be, so subtract it explicitly.
    for ex in excludes:
        if _under(ex, path) and os.path.normpath(ex) != os.path.normpath(path) and os.path.exists(ex):
            try:
                if os.stat(ex).st_dev == os.stat(path).st_dev:
                    sub = subprocess.run(["du", "-sxk", ex], stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, universal_newlines=True)
                    kib -= int(sub.stdout.split()[0])
            except (OSError, ValueError, IndexError, TypeError):
                pass
    return {"kib": kib, "du_exit": done.returncode, "du_stderr_lines": len(done.stderr.splitlines())}


def snapshot(mounts: list, excludes: list, label: str) -> dict:
    entries = []
    for m in mounts:
        res = du_kib(m["mountpoint"], excludes)
        entries.append(dict(m, **res))
    total = sum(e["kib"] or 0 for e in entries)
    return {"tool": "disk_usage.py", "label": label,
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "excludes": excludes, "mounts": entries, "total_kib": total}


def cmd_snapshot(args) -> int:
    excludes = [os.path.normpath(e) for e in (args.exclude or [])]
    if args.mount:
        mounts = [{"device": "-", "mountpoint": m, "fstype": "given", "options": ["rw"]} for m in args.mount
                  if not any(_under(m, ex) for ex in excludes)]
    else:
        with open("/proc/self/mounts") as fh:
            mounts = writable_mounts(parse_mounts(fh.read()), excludes)
    snap = snapshot(mounts, excludes, args.label)
    with open(args.out, "w") as fh:
        json.dump(snap, fh, indent=2)
        fh.write("\n")
    sys.stderr.write("disk_usage: %d mounts, %d KiB\n" % (len(snap["mounts"]), snap["total_kib"]))
    return 0


def compare(before: dict, after: dict, model_bytes: int, max_fraction: float) -> dict:
    b = {m["mountpoint"]: m["kib"] or 0 for m in before["mounts"]}
    a = {m["mountpoint"]: m["kib"] or 0 for m in after["mounts"]}
    per = {mp: (a.get(mp, 0) - b.get(mp, 0)) * 1024 for mp in sorted(set(a) | set(b))}
    growth = sum(per.values())
    limit = model_bytes * max_fraction
    return {"growth_bytes": growth, "per_mount_growth_bytes": per, "model_bytes": model_bytes,
            "limit_bytes": int(limit), "fraction_of_model": round(growth / model_bytes, 5) if model_bytes else None,
            "passed": growth < limit}


def cmd_compare(args) -> int:
    with open(args.before) as fh:
        before = json.load(fh)
    with open(args.after) as fh:
        after = json.load(fh)
    model_bytes = args.model_bytes if args.model_bytes else os.stat(args.model_file).st_size
    res = compare(before, after, model_bytes, args.max_fraction)
    text = json.dumps(res, indent=2) + "\n"
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text)
    sys.stdout.write(text)
    return 0 if res["passed"] else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="action", required=True)
    sp = sub.add_parser("snapshot")
    sp.add_argument("--exclude", action="append", help="model mount point (repeatable)")
    sp.add_argument("--mount", action="append", help="measure these paths instead of /proc/self/mounts")
    sp.add_argument("--label", default="")
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_snapshot)
    sp = sub.add_parser("compare")
    sp.add_argument("before")
    sp.add_argument("after")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--model-file")
    g.add_argument("--model-bytes", type=int)
    sp.add_argument("--max-fraction", type=float, default=0.05)
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_compare)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
