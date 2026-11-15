"""The ingest loop's state on disk: a queue of items and a list of harness issues (docs/loop.md).

A loop session keeps nothing in its head between items. What is left to do, what is blocked and on what,
is in two files under loop/, and this script is the only thing that changes their structure:

- loop/queue.jsonl: one item per line. An item is a record to verify again (`reverify`, target = slug) or a
  repository or site to bring in (`new`, target = owner/name or a URL). status goes todo -> doing -> done or
  parked. A parked item names the harness issue it waits for.
- loop/issues.md: one `## H-001 [open] title` section per harness issue; the text under the heading is the
  session's own notes (symptom, how to reproduce, what was tried). This script only reads and rewrites the
  heading line.

    uv run python scripts/loop_state.py status            # the one line a /goal evaluator reads
    uv run python scripts/loop_state.py next              # claim the next item (a `doing` item first)
    uv run python scripts/loop_state.py finish ID --result verified|unverified|rejected [--note ...]
    uv run python scripts/loop_state.py park ID --issue H-003 [--note ...]
    uv run python scripts/loop_state.py add --kind new --target owner/name [--issue H-003]
    uv run python scripts/loop_state.py seed-unverified   # records the box could not verify -> reverify items
    uv run python scripts/loop_state.py issue-new "title" [--reason needs_toolchain]
    uv run python scripts/loop_state.py issue-status H-003 fixed   # fixed also puts its parked items back
    uv run python scripts/loop_state.py issues

Standard library only, no model call, no network.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import re
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOP_DIR = REPO_ROOT / "loop"
DATA_DIR = REPO_ROOT / "data" / "software"
TAIPEI = ZoneInfo("Asia/Taipei")

KINDS = ("reverify", "new")
STATUSES = ("todo", "doing", "done", "parked")
RESULTS = ("verified", "unverified", "rejected")
ISSUE_STATUSES = ("open", "fixing", "fixed", "parked", "review")
# An issue the loop may still work on. `review` waits for a person (a change to a protected file), `parked`
# for a new idea; neither stops the loop.
ISSUE_ACTIVE = ("open", "fixing")
# The unverified reasons that describe pickfit's box, not the software: what a better harness can remove.
BOX_REASONS = ("needs_toolchain", "needs_root", "needs_container", "needs_more_resources")
MAX_TRIES = 3

_HEADING = re.compile(r"^## (H-\d{3}) \[(\w+)\] (.+)$")
_REASON_LINE = re.compile(r"^reason: (\w+)\s*$", re.M)


class StateError(Exception):
    """A request the state cannot honor: an unknown id, a transition that is not allowed."""


def now() -> str:
    return datetime.now(TAIPEI).isoformat(timespec="seconds")


@contextmanager
def locked(loop_dir: Path) -> Iterator[None]:
    """One writer at a time: two sessions in the same worktree must not interleave a read and a write."""
    loop_dir.mkdir(parents=True, exist_ok=True)
    with open(loop_dir / ".lock", "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


# --- queue ---------------------------------------------------------------------------------------------------


def read_queue(loop_dir: Path) -> list[dict[str, Any]]:
    path = loop_dir / "queue.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_queue(loop_dir: Path, items: list[dict[str, Any]]) -> None:
    path = loop_dir / "queue.jsonl"
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in items))
    tmp.replace(path)


def item_id(kind: str, target: str) -> str:
    return f"{kind}:{target.strip().lower()}"


def add_item(items: list[dict[str, Any]], kind: str, target: str, *, issue: str | None = None,
             note: str | None = None) -> dict[str, Any] | None:
    """Append a todo item; None when the same kind and target is already queued, whatever its status."""
    if kind not in KINDS:
        raise StateError(f"unknown kind {kind!r}; expected one of {KINDS}")
    ident = item_id(kind, target)
    if any(item["id"] == ident for item in items):
        return None
    item = {"id": ident, "kind": kind, "target": target.strip(), "status": "todo", "issue": issue,
            "tries": 0, "result": None, "note": note, "updated_at": now()}
    items.append(item)
    return item


def _find(items: list[dict[str, Any]], ident: str) -> dict[str, Any]:
    for item in items:
        if item["id"] == ident:
            return item
    raise StateError(f"no item {ident!r} in the queue")


def claim_next(items: list[dict[str, Any]], issues: dict[str, str]) -> dict[str, Any] | None:
    """The item to work on now: one left `doing` by a session that ended, else the first todo.

    A todo item that names an issue which is not active any more (parked, or waiting for a review) would
    only fail the same way, so it is parked on the spot. An item claimed MAX_TRIES times is parked too:
    the loop moves on instead of retrying the same thing forever.
    """
    for item in items:
        if item["status"] == "doing":
            return item
    for item in items:
        if item["status"] != "todo":
            continue
        issue = item.get("issue")
        if issue and issues.get(issue) in ("parked", "review"):
            item.update(status="parked", note=f"waits for {issue} ({issues[issue]})", updated_at=now())
            continue
        if item["tries"] >= MAX_TRIES:
            item.update(status="parked", note=f"claimed {MAX_TRIES} times without a result", updated_at=now())
            continue
        item.update(status="doing", tries=item["tries"] + 1, updated_at=now())
        return item
    return None


def finish(items: list[dict[str, Any]], ident: str, result: str, note: str | None) -> dict[str, Any]:
    if result not in RESULTS:
        raise StateError(f"unknown result {result!r}; expected one of {RESULTS}")
    item = _find(items, ident)
    if item["status"] != "doing":
        raise StateError(f"{ident} is {item['status']}, not doing; claim it with `next` first")
    item.update(status="done", result=result, note=note, updated_at=now())
    return item


def park(items: list[dict[str, Any]], ident: str, issue: str, note: str | None,
         issues: dict[str, str]) -> dict[str, Any]:
    if issue not in issues:
        raise StateError(f"no issue {issue} in loop/issues.md; create it with `issue-new` first")
    item = _find(items, ident)
    if item["status"] not in ("doing", "todo"):
        raise StateError(f"{ident} is {item['status']}; only a todo or doing item can be parked")
    item.update(status="parked", issue=issue, note=note, updated_at=now())
    return item


def requeue(items: list[dict[str, Any]], issue: str) -> list[str]:
    """Put the items parked on a fixed issue back in line, with their tries reset: the box changed."""
    back = []
    for item in items:
        if item["status"] == "parked" and item.get("issue") == issue:
            item.update(status="todo", tries=0, note=f"{issue} fixed; try again", updated_at=now())
            back.append(item["id"])
    return back


# --- issues --------------------------------------------------------------------------------------------------


def read_issues(loop_dir: Path) -> dict[str, str]:
    """Issue id -> status, from the headings of loop/issues.md."""
    path = loop_dir / "issues.md"
    if not path.exists():
        return {}
    found = {}
    for line in path.read_text().splitlines():
        match = _HEADING.match(line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def issue_reasons(loop_dir: Path) -> dict[str, str]:
    """Unverified reason -> the issue that covers it, from each section's `reason: <code>` line."""
    path = loop_dir / "issues.md"
    if not path.exists():
        return {}
    reasons: dict[str, str] = {}
    current = None
    for line in path.read_text().splitlines():
        match = _HEADING.match(line)
        if match:
            current = match.group(1)
            continue
        reason = _REASON_LINE.match(line)
        if reason and current:
            reasons.setdefault(reason.group(1), current)
    return reasons


def new_issue(loop_dir: Path, title: str, reason: str | None = None) -> str:
    title = " ".join(title.split())
    if not title:
        raise StateError("an issue needs a title")
    path = loop_dir / "issues.md"
    text = path.read_text() if path.exists() else "# Harness issues\n"
    numbers = [int(i[2:]) for i in read_issues(loop_dir)]
    ident = f"H-{max(numbers, default=0) + 1:03d}"
    section = [f"## {ident} [open] {title}", ""]
    if reason:
        section += [f"reason: {reason}", ""]
    section += [f"- opened: {now()}", "- symptom:", "- reproduce:", "- tried:", ""]
    path.write_text(text.rstrip("\n") + "\n\n" + "\n".join(section))
    return ident


def set_issue_status(loop_dir: Path, ident: str, status: str) -> None:
    if status not in ISSUE_STATUSES:
        raise StateError(f"unknown issue status {status!r}; expected one of {ISSUE_STATUSES}")
    path = loop_dir / "issues.md"
    lines = path.read_text().splitlines() if path.exists() else []
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and match.group(1) == ident:
            lines[index] = f"## {ident} [{status}] {match.group(3)}"
            path.write_text("\n".join(lines) + "\n")
            return
    raise StateError(f"no issue {ident} in loop/issues.md")


# --- seed and status -----------------------------------------------------------------------------------------


def seed_unverified(items: list[dict[str, Any]], data_dir: Path, reasons: tuple[str, ...],
                    by_reason: dict[str, str]) -> list[str]:
    """A reverify item for every record whose unverified reason is the box's; returns the ids added."""
    added = []
    for path in sorted(data_dir.glob("*.json")):
        record = json.loads(path.read_text())
        reason = (record.get("verification") or {}).get("unverified_reason")
        if reason not in reasons:
            continue
        item = add_item(items, "reverify", record["slug"], issue=by_reason.get(reason), note=reason)
        if item:
            added.append(item["id"])
    return added


def status_line(items: list[dict[str, Any]], issues: dict[str, str]) -> str:
    counts = Counter(item["status"] for item in items)
    results = Counter(item["result"] for item in items if item["status"] == "done")
    by_issue = Counter(issues.values())
    left = " ".join(f"{name}={counts.get(name, 0)}" for name in STATUSES)
    done = " ".join(f"{name}={results.get(name, 0)}" for name in RESULTS)
    marks = " ".join(f"{name}={by_issue.get(name, 0)}" for name in ISSUE_STATUSES)
    return f"LOOP_STATUS {left} | results {done} | issues {marks}"


def remaining(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if item["status"] in ("todo", "doing"))


# --- command line --------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--loop-dir", type=Path, default=LOOP_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="one line of counts; exit 3 when nothing is left to claim")
    status.add_argument("--exit-code", action="store_true", help="exit 3 when no todo or doing item is left")
    sub.add_parser("next", help="claim the next item and print it as JSON; exit 3 when the queue is empty")
    done = sub.add_parser("finish", help="close the item being worked on")
    done.add_argument("id")
    done.add_argument("--result", required=True, choices=RESULTS)
    done.add_argument("--note")
    parked = sub.add_parser("park", help="set an item aside until a harness issue is fixed")
    parked.add_argument("id")
    parked.add_argument("--issue", required=True)
    parked.add_argument("--note")
    add = sub.add_parser("add", help="queue one item")
    add.add_argument("--kind", required=True, choices=KINDS)
    add.add_argument("--target", required=True)
    add.add_argument("--issue")
    add.add_argument("--note")
    seed = sub.add_parser("seed-unverified", help="queue the records the box could not verify")
    seed.add_argument("--data-dir", type=Path, default=DATA_DIR)
    seed.add_argument("--reason", action="append", choices=BOX_REASONS, help="default: every box reason")
    issue_new = sub.add_parser("issue-new", help="open a harness issue and print its id")
    issue_new.add_argument("title")
    issue_new.add_argument("--reason", help="the unverified reason this issue removes, if one")
    issue_status = sub.add_parser("issue-status", help="set an issue's status; fixed requeues its parked items")
    issue_status.add_argument("id")
    issue_status.add_argument("status", choices=ISSUE_STATUSES)
    sub.add_parser("issues", help="list the issues with the items waiting on each")
    args = parser.parse_args(argv)
    loop_dir: Path = args.loop_dir

    try:
        with locked(loop_dir):
            items = read_queue(loop_dir)
            issues = read_issues(loop_dir)
            if args.command == "status":
                print(status_line(items, issues))
                return 3 if args.exit_code and not remaining(items) else 0
            if args.command == "next":
                item = claim_next(items, issues)
                write_queue(loop_dir, items)
                if item is None:
                    print(status_line(items, issues))
                    return 3
                print(json.dumps(item, ensure_ascii=False))
            elif args.command == "finish":
                print(json.dumps(finish(items, args.id, args.result, args.note), ensure_ascii=False))
                write_queue(loop_dir, items)
            elif args.command == "park":
                print(json.dumps(park(items, args.id, args.issue, args.note, issues), ensure_ascii=False))
                write_queue(loop_dir, items)
            elif args.command == "add":
                if args.issue and args.issue not in issues:
                    raise StateError(f"no issue {args.issue} in loop/issues.md")
                item = add_item(items, args.kind, args.target, issue=args.issue, note=args.note)
                write_queue(loop_dir, items)
                print(json.dumps(item, ensure_ascii=False) if item else f"already queued: {args.target}")
            elif args.command == "seed-unverified":
                reasons = tuple(args.reason or BOX_REASONS)
                added = seed_unverified(items, args.data_dir, reasons, issue_reasons(loop_dir))
                write_queue(loop_dir, items)
                print(f"queued {len(added)} records ({', '.join(reasons)})")
            elif args.command == "issue-new":
                print(new_issue(loop_dir, args.title, args.reason))
            elif args.command == "issue-status":
                set_issue_status(loop_dir, args.id, args.status)
                back = requeue(items, args.id) if args.status == "fixed" else []
                write_queue(loop_dir, items)
                print(f"{args.id} is {args.status}" + (f"; back in line: {', '.join(back)}" if back else ""))
            elif args.command == "issues":
                waiting = Counter(item["issue"] for item in items
                                  if item.get("issue") and item["status"] in ("todo", "doing", "parked"))
                for ident, state in issues.items():
                    print(f"{ident} [{state}] {waiting.get(ident, 0)} items waiting")
    except StateError as error:
        print(f"loop_state: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
