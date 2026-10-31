#!/usr/bin/env python3
"""Check the q19 result in one workdir (Python stdlib only).

  python3 check_hello.py WORKDIR

Pass when WORKDIR/hello.py is a regular file and `python3 hello.py`, run in
WORKDIR (30 s limit), exits 0 and its stdout is exactly the line in
expected_output.txt followed by at most one newline. Prints JSON; exit 0 on pass.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def expected():
    with open(os.path.join(HERE, "expected_output.txt"), encoding="utf-8") as f:
        return f.read().rstrip("\n")


def check(workdir, python="python3"):
    want = expected()
    path = os.path.join(workdir, "hello.py")
    res = {"workdir": workdir, "expected": want, "exists": os.path.isfile(path)}
    if not res["exists"]:
        res["pass"] = False
        return res
    try:
        p = subprocess.run([python, "hello.py"], cwd=workdir, capture_output=True, timeout=30)
        out = p.stdout.decode("utf-8", "replace")
        res.update({"exit_code": p.returncode, "stdout": out[:500], "stderr": p.stderr.decode("utf-8", "replace")[:500]})
        line = out[:-1] if out.endswith("\n") else out
        res["pass"] = p.returncode == 0 and line == want
    except subprocess.TimeoutExpired:
        res.update({"timed_out": True, "pass": False})
    return res


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    res = check(sys.argv[1])
    print(json.dumps(res, indent=1))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
