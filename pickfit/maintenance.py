"""`pickfit maintenance TASK`: the watch VM's scheduled upkeep (docs/proposals/product-ux-cost-audit.md D3, F3, F4).

Each task runs in a git worktree of its own beside the watch's checkout (default <repo>/../maint), never in the
checkout the watch commits and pushes from, so the two never share an index or a half-written data/software. The
program that runs is the watch checkout's; only the records come from the worktree (each command's data flag).

| task      | what                                                                    | model cost | lands on            |
|-----------|-------------------------------------------------------------------------|------------|---------------------|
| security  | `pickfit security --stale-days N --write`, then `pickfit score --refresh` | none       | main (CI deploys it) |
| outcomes  | `pickfit outcomes sync` (outside usage reports from D1 into the scores)  | none       | main (CI deploys it) |
| reverify  | `pickfit reverify --limit N` (reported install failures, fresh box)     | paid       | a branch, for review |

security and outcomes start from origin/main, commit what changed in data/software and data/security, and push to
main, fetching and rebasing when the watch pushed first. reverify rewrites a record's steps from a user's report, so
a person reads the diff before it ships (the watch refuses --reverify with --publish for the same reason): it
commits on a dated branch maint/reverify-YYYYMMDD and pushes that branch, never main. Units in deploy/watch/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PUSH_TRIES = 3
DEFAULT_STALE_DAYS = 7
DEFAULT_REVERIFY_LIMIT = 3
DATA_PATHS = ("data/software", "data/security")

Runner = Callable[[list[str]], int]


def run_pickfit(argv: list[str]) -> int:
    """A pickfit command in this process (the watch checkout's program)."""
    from pickfit.cli import main

    return main(argv)


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, check=check, capture_output=True, text=True)


@dataclass
class Outcome:
    task: str
    commands: list[dict[str, Any]] = field(default_factory=list)
    committed: str | None = None
    pushed: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"task": self.task, "commands": self.commands, "committed": self.committed, "pushed": self.pushed,
                "note": self.note}


def prepare(repo: Path, maint: Path, *, branch: str | None = None) -> None:
    """The maintenance worktree at origin/main, clean: detached, or on a new `branch` from origin/main."""
    git(repo, "fetch", "-q", "origin")
    if not (maint / ".git").exists():
        git(repo, "worktree", "add", "-q", "--detach", str(maint), "origin/main")
    git(maint, "reset", "-q", "--hard")
    git(maint, "clean", "-qfd", "--", *DATA_PATHS)
    if branch:
        git(maint, "checkout", "-q", "-B", branch, "origin/main")
    else:
        git(maint, "checkout", "-q", "--detach", "origin/main")


def commit(maint: Path, message: str) -> str | None:
    """Commit what changed under DATA_PATHS; the new HEAD, or None when nothing changed."""
    git(maint, "add", "-A", "--", *[p for p in DATA_PATHS if (maint / p).exists()])
    if git(maint, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return None
    git(maint, "commit", "-q", "-m", message)
    return git(maint, "rev-parse", "HEAD").stdout.strip()


def push_main(maint: Path, *, tries: int = PUSH_TRIES) -> str | None:
    """Push HEAD to origin main; when the watch (or anyone) pushed first, fetch, rebase and try again."""
    for _ in range(tries):
        if git(maint, "push", "-q", "origin", "HEAD:refs/heads/main", check=False).returncode == 0:
            return git(maint, "rev-parse", "HEAD").stdout.strip()
        git(maint, "fetch", "-q", "origin")
        if git(maint, "rebase", "-q", "origin/main", check=False).returncode != 0:
            git(maint, "rebase", "--abort", check=False)
            return None
    return None


def _run(out: Outcome, run: Runner, argv: list[str]) -> int:
    code = run(argv)
    out.commands.append({"argv": argv, "exit": code})
    return code


def task_security(repo: Path, maint: Path, run: Runner, *, stale_days: int, now: datetime, push: bool) -> Outcome:
    out = Outcome("security")
    prepare(repo, maint)
    data = str(maint / "data" / "software")
    _run(out, run, ["security", "--stale-days", str(stale_days), "--write", "--data-dir", data])
    _run(out, run, ["score", "--refresh", "--data-dir", data])
    out.committed = commit(maint, f"Weekly sec.v2 rescan (records not checked in {stale_days} days) and score "
                                  f"refresh, {now:%Y-%m-%d}\n\npickfit maintenance security: OSV.dev, deps.dev, KEV and "
                                  f"EPSS only, no model call.")
    if out.committed and push:
        out.pushed = push_main(maint)
        out.note = None if out.pushed else "push failed: the commit stays in the maintenance worktree"
    return out


def task_outcomes(repo: Path, maint: Path, run: Runner, *, now: datetime, push: bool) -> Outcome:
    out = Outcome("outcomes")
    prepare(repo, maint)
    _run(out, run, ["outcomes", "sync", "--data", str(maint / "data" / "software")])
    out.committed = commit(maint, f"Sync usage outcomes from D1 into the scores, {now:%Y-%m-%d}\n\n"
                                  f"pickfit maintenance outcomes: outside reports only, no model call.")
    if out.committed and push:
        out.pushed = push_main(maint)
        out.note = None if out.pushed else "push failed: the commit stays in the maintenance worktree"
    return out


def task_reverify(repo: Path, maint: Path, run: Runner, *, limit: int, now: datetime, push: bool) -> Outcome:
    out = Outcome("reverify")
    branch = f"maint/reverify-{now:%Y%m%d}"
    prepare(repo, maint, branch=branch)
    start = git(maint, "rev-parse", "HEAD").stdout.strip()
    _run(out, run, ["reverify", "--limit", str(limit), "--data", str(maint / "data" / "software")])
    head = git(maint, "rev-parse", "HEAD").stdout.strip()
    if head == start:
        out.note = "nothing re-verified changed a record"
        return out
    out.committed = head
    if push:
        pushed = git(maint, "push", "-q", "--force-with-lease", "origin", f"HEAD:refs/heads/{branch}", check=False)
        out.pushed = branch if pushed.returncode == 0 else None
    out.note = f"for review on {branch}: never pushed to main by this task"
    return out


def add_parser(sub: argparse._SubParsersAction) -> None:
    m = sub.add_parser("maintenance", help="the watch VM's scheduled upkeep in a worktree of its own: security "
                                           "(weekly sec.v2 rescan + score refresh, $0), outcomes (D1 usage reports, "
                                           "$0), reverify (paid; commits to a review branch)")
    m.add_argument("task", choices=["security", "outcomes", "reverify"])
    m.add_argument("--repo", type=Path, default=None, help="the watch's checkout (default: this repository)")
    m.add_argument("--maint", type=Path, default=None, help="the maintenance worktree (default <repo>/../maint)")
    m.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS, help="security: records older than N days")
    m.add_argument("--limit", type=int, default=DEFAULT_REVERIFY_LIMIT, help="reverify: reports to take")
    m.add_argument("--no-push", action="store_true", help="commit in the maintenance worktree, push nothing")
    m.set_defaults(func=main)


def main(args: Any, run: Runner = run_pickfit, now: datetime | None = None) -> int:
    from pickfit.env import REPO_ROOT
    from pickfit.ledger import taipei_now

    repo = Path(args.repo or REPO_ROOT).resolve()
    maint = Path(args.maint).resolve() if args.maint else repo.parent / "maint"
    now = now or taipei_now()
    push = not args.no_push
    try:
        if args.task == "security":
            out = task_security(repo, maint, run, stale_days=args.stale_days, now=now, push=push)
        elif args.task == "outcomes":
            out = task_outcomes(repo, maint, run, now=now, push=push)
        else:
            out = task_reverify(repo, maint, run, limit=args.limit, now=now, push=push)
    except subprocess.CalledProcessError as err:
        print(f"pickfit maintenance {args.task}: {' '.join(map(str, err.cmd))}: {(err.stderr or '').strip()[:300]}",
              file=sys.stderr)
        return 2
    print(json.dumps(out.to_dict(), ensure_ascii=False, indent=2))
    failed = any(c["exit"] not in (0, 1) for c in out.commands) or (out.committed and push and not out.pushed)
    return 1 if failed else 0


def _argv(argv: Sequence[str]) -> argparse.Namespace:  # for tests
    parser = argparse.ArgumentParser()
    add_parser(parser.add_subparsers())
    return parser.parse_args(["maintenance", *argv])
