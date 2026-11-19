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
    uv run python scripts/loop_state.py reopen ID --note "why"   # a done item that was closed by mistake
    uv run python scripts/loop_state.py add --kind new --target owner/name [--issue H-003]
    uv run python scripts/loop_state.py seed-unverified   # records the box could not verify -> reverify items
    uv run python scripts/loop_state.py issue-new "title" [--reason needs_toolchain]
    uv run python scripts/loop_state.py issue-status H-003 fixed   # fixed also puts its parked items back
    uv run python scripts/loop_state.py issues
    uv run python scripts/loop_state.py open-issues [--all]  # one line per unresolved issue: id, title, reason
    uv run python scripts/loop_state.py issue H-003          # that one section of loop/issues.md, notes and all
    uv run python scripts/loop_state.py run-summary [RUN] [--slug SLUG]  # a verify run's outcome in a few lines

A session reads the short forms (open-issues, run-summary) instead of the whole of loop/issues.md or a verify
run's output, and opens one issue or the run's files only when it needs the detail (11/19).

Standard library only, no model call, no network.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
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
RUNS_DIR = REPO_ROOT / "runs"
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


def reopen(items: list[dict[str, Any]], ident: str, note: str) -> dict[str, Any]:
    """Put a closed item back in line when its result was recorded by mistake (a write-back that failed after
    the item was finished, say). The claim that went wrong still counts toward MAX_TRIES."""
    item = _find(items, ident)
    if item["status"] != "done":
        raise StateError(f"{ident} is {item['status']}; only a done item can be reopened")
    item.update(status="todo", result=None, note=note, updated_at=now())
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


def issue_index(loop_dir: Path) -> list[dict[str, str | None]]:
    """Each issue's id, status, title and `reason:` code, in file order: the headings, not the notes."""
    path = loop_dir / "issues.md"
    if not path.exists():
        return []
    out: list[dict[str, str | None]] = []
    for line in path.read_text().splitlines():
        match = _HEADING.match(line)
        if match:
            out.append({"id": match.group(1), "status": match.group(2), "title": match.group(3), "reason": None})
            continue
        reason = _REASON_LINE.match(line)
        if reason and out and out[-1]["reason"] is None:
            out[-1]["reason"] = reason.group(1)
    return out


def issue_section(loop_dir: Path, ident: str) -> str:
    """One issue's section of loop/issues.md: its heading and notes, up to the next issue's heading."""
    path = loop_dir / "issues.md"
    lines = path.read_text().splitlines() if path.exists() else []
    section: list[str] = []
    for line in lines:
        match = _HEADING.match(line)
        if match:
            if section:
                break
            if match.group(1) == ident:
                section.append(line)
            continue
        if section:
            section.append(line)
    if not section:
        raise StateError(f"no issue {ident} in loop/issues.md")
    return "\n".join(section).rstrip() + "\n"


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


# --- a verify run in a few lines -----------------------------------------------------------------------------


def _clip(text: Any, limit: int) -> str | None:
    if text is None:
        return None
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _tail(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else "…" + flat[-(limit - 1):]


def _load(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def find_run(runs_dir: Path, run: str | None = None, slug: str | None = None) -> Path | None:
    """A verify run's evidence directory: a path, a run id under runs/verify/, or the newest run (of `slug`)."""
    if run:
        path = Path(run)
        if path.is_dir():
            return path
        path = runs_dir / "verify" / run
        return path if path.is_dir() else None
    pattern = f"verify-{slug}-*" if slug else "*"
    runs = [p for p in (runs_dir / "verify").glob(pattern) if p.is_dir() and
            ((p / "outcome.json").exists() or (p / "report.json").exists())]
    if slug:  # verify-<slug>-<date>-<time>-<hex>: a longer slug that starts the same is another tool
        runs = [p for p in runs if re.fullmatch(rf"verify-{re.escape(slug)}-\d{{8}}-\d{{6}}-[0-9a-f]+", p.name)]
    return max(runs, key=lambda p: max(f.stat().st_mtime for f in p.iterdir() if f.is_file()), default=None)


def run_summary(evidence: Path) -> dict[str, Any]:
    """What a session needs to decide on a run, from outcome.json and report.json: the result, why, what it cost,
    the failing command's tail. Never the agent's turns or its thinking (open the files for those)."""
    outcome = _load(evidence / "outcome.json") or {}
    report = _load(evidence / "report.json") or {}
    finish = report.get("finish") or {}
    verdict = report.get("verdict") or {}
    out: dict[str, Any] = {"run": outcome.get("run_id") or report.get("run_id") or evidence.name,
                           "slug": outcome.get("slug") or report.get("slug"), "evidence": str(evidence)}
    if not outcome:
        out["missing"] = "outcome.json (the run did not finish; its last lines are in the log you wrote)"
    for key in ("level", "replayed", "judge", "unverified_reason", "runner", "written", "seconds", "cost_usd",
                "box_usd"):
        if key in outcome:
            out[key] = outcome[key]
    out["blocking_error"] = _clip(outcome.get("blocking_error") or finish.get("blocking_error"), 300)
    out["stop_reason"] = report.get("stop_reason") or None
    out["error"] = _clip(report.get("error"), 300)
    out["summary"] = _clip(finish.get("summary"), 400)
    if verdict:
        out["verdict"] = {"level": verdict.get("level"), "agrees": verdict.get("agrees"),
                          "problems": [_clip(p, 200) for p in (verdict.get("problems") or [])[:5]]}
    features = report.get("features") or []
    if features:
        out["features"] = [f"{f.get('number')}. {_clip(f.get('feature'), 80)}: {f.get('status')}"
                           for f in features[:12]]
    commands = [c for c in report.get("commands") or [] if c.get("command_id") is not None]
    failing = finish.get("failing_command_id") or verdict.get("failing_id")
    picked = [c for c in commands if c.get("command_id") == failing] if failing else []
    if not picked and out.get("level") in (None, "unverified"):
        picked = commands[-3:]  # no command named: the last ones are where it ended
    if picked:
        out["commands"] = [{k: v for k, v in {
            "id": c.get("command_id"), "command": _clip(c.get("command"), 200), "exit_code": c.get("exit_code"),
            "timed_out": c.get("timed_out") or None, "stderr_tail": _tail(c.get("stderr"), 400),
            "stdout_tail": None if c.get("stderr") else _tail(c.get("stdout"), 300)}.items() if v is not None}
            for c in picked]
    notes = outcome.get("notes") or []
    if notes:
        out["notes"] = [_clip(n, 200) for n in notes[:5]]
    return {k: v for k, v in out.items() if v is not None}


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
    again = sub.add_parser("reopen", help="put a done item back in line: its result was recorded by mistake")
    again.add_argument("id")
    again.add_argument("--note", required=True, help="what went wrong")
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
    open_issues = sub.add_parser("open-issues", help="one line per unresolved issue (open, fixing): id, title, "
                                                     "reason code, items waiting; the rest as counts")
    open_issues.add_argument("--all", action="store_true", help="every issue, fixed and parked ones too")
    one = sub.add_parser("issue", help="print one issue's section of loop/issues.md")
    one.add_argument("id")
    summary = sub.add_parser("run-summary", help="a verify run's result in a few lines (outcome.json, report.json)")
    summary.add_argument("run", nargs="?", help="the run's directory or id (default: the newest run)")
    summary.add_argument("--slug", help="the newest run of this slug")
    summary.add_argument("--runs-dir", type=Path, default=None, help="default PICKFIT_RUNS_DIR, else runs/")
    args = parser.parse_args(argv)
    loop_dir: Path = args.loop_dir

    if args.command == "run-summary":  # reads runs/ only: no lock, no queue
        runs_dir = args.runs_dir or Path(os.environ.get("PICKFIT_RUNS_DIR") or RUNS_DIR)
        evidence = find_run(runs_dir, args.run, args.slug)
        if evidence is None:
            print(f"loop_state: no verify run {'like ' + (args.run or args.slug) if args.run or args.slug else ''} "
                  f"under {runs_dir / 'verify'}", file=sys.stderr)
            return 2
        print(json.dumps(run_summary(evidence), ensure_ascii=False, indent=1))
        return 0

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
            elif args.command == "reopen":
                print(json.dumps(reopen(items, args.id, args.note), ensure_ascii=False))
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
            elif args.command == "open-issues":
                waiting = Counter(item["issue"] for item in items
                                  if item.get("issue") and item["status"] in ("todo", "doing", "parked"))
                index = issue_index(loop_dir)
                shown = [i for i in index if args.all or i["status"] in ISSUE_ACTIVE]
                for issue in shown:
                    extra = [f"reason {issue['reason']}"] if issue["reason"] else []
                    if waiting.get(issue["id"]):
                        extra.append(f"{waiting[issue['id']]} items waiting")
                    print(f"{issue['id']} [{issue['status']}] {issue['title']}"
                          + (f" ({', '.join(extra)})" if extra else ""))
                rest = Counter(i["status"] for i in index if i not in shown)
                if rest:
                    print("not listed: " + " ".join(f"{name}={rest[name]}" for name in ISSUE_STATUSES if rest[name])
                          + " (--all lists them; `issue H-00X` prints one)")
            elif args.command == "issue":
                print(issue_section(loop_dir, args.id), end="")
    except StateError as error:
        print(f"loop_state: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
