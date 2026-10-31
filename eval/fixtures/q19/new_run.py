#!/usr/bin/env python3
"""Start one q19 run: a fresh copy of the seed repo and a run folder (Python stdlib only).

  python3 new_run.py --runs-dir /eval-work/q19/runs --label r1 --workdir /home/dev/inventory-r1

Copies workdir_seed/ to --workdir (which must not exist yet). If `git` is on
PATH, makes it a git repository with one commit (fixed author and dates, so
every run starts from the same commit id). Writes RUNS/r1/run.json with the
start time (epoch seconds) and the workdir, and prints the run folder.
Run it immediately before starting the agent; start the agent in --workdir.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GIT_ENV = {"GIT_AUTHOR_NAME": "Eval Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "Eval Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
           "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+0000",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}


def make_workdir(dest, use_git=True):
    if os.path.exists(dest):
        raise SystemExit("workdir already exists: %s" % dest)
    shutil.copytree(os.path.join(HERE, "workdir_seed"), dest)
    info = {"git": False}
    if use_git and shutil.which("git"):
        env = dict(os.environ, **GIT_ENV)
        run = lambda *c: subprocess.run(["git"] + list(c), cwd=dest, env=env, check=True,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run("init", "-q", "-b", "main")
        run("add", "-A")
        run("-c", "commit.gpgsign=false", "commit", "-q", "-m", "Initial commit")
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest, capture_output=True, text=True).stdout.strip()
        info = {"git": True, "head": head}
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-dir", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--no-git", action="store_true")
    a = ap.parse_args()
    run = os.path.join(a.runs_dir, a.label)
    if os.path.exists(os.path.join(run, "run.json")):
        print("run folder already used: %s" % run, file=sys.stderr)
        return 2
    os.makedirs(run, exist_ok=True)
    info = make_workdir(os.path.abspath(a.workdir), not a.no_git)
    rec = {"label": a.label, "workdir": os.path.abspath(a.workdir), "t_start": time.time()}
    rec.update(info)
    with open(os.path.join(run, "run.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    print(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
