#!/usr/bin/env python3
"""pickfit check-in: a one-shot, read-only look at the tools pickfit recommended to you.

You run it yourself, whenever you like (or schedule it yourself). pickfit installs nothing and
leaves nothing running. Python 3.10+ standard library only, so you can read all of it first.

Usage:
    python3 scripts/checkin.py checkins.json            # check, ask, show, send after "yes"
    python3 scripts/checkin.py checkins.json --dry-run  # check, ask, show; never send

checkins.json holds what you kept from get_install_guide: one object or a list, each with
rec_id, slug, name and check_in (the guide's own result has exactly these fields). Your agent can
save it for you when it installs a tool, if you ask it to.

What it does, per tool:
1. Runs only check_in commands of the forms pickfit writes (`command -v X`, `brew list --versions X`,
   `npm ls -g --depth=0 X`, `uv tool list | grep ...`, `pip show X`, `claude mcp get X`, macOS
   `mdls -name kMDItemLastUsedDate` for an app). Anything else in the file is skipped, never run.
   No shell: each one runs as a plain argument list, and grep filters happen here, in Python.
2. Asks you what it cannot see: do you still use it, and roughly when you last did.
3. Prints exactly what it would send, then sends only if you type yes.

Sent per tool: slug, rec_id, stage (still_using, replaced or abandoned), last_used (this_week,
this_month, older or unknown) and, if you replaced it, what with. Never the command output, a
date, a path, or anything about other software.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ENDPOINT = "https://pickfit-mcp.ncchen99.workers.dev/mcp"
TIMEOUT_S = 30
LAST_USED = ("this_week", "this_month", "older", "unknown")

_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
_NPM = r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]{0,99}"  # never a leading "-": not an option
_APP = r"[A-Za-z0-9][A-Za-z0-9 .+_-]{0,60}"
_ONLY = rf"(?: \| grep -i -- '\^({_NAME}) '| \| Select-String -Pattern '\^({_NAME}) ')"
_REC_ID = re.compile(r"^rec_[0-9a-f]{32}$")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass
class Check:
    """One allowed command as an argument list. `which`: look it up on PATH instead of running
    anything; `only`: keep the output lines that start with this name and a space."""

    command: str
    argv: list[str]
    which: str | None = None
    only: str | None = None
    last_used: bool = False


def parse(command: str) -> Check | None:
    """The check for one of the command forms pickfit writes (worker/src/checkin.ts), else None."""
    if m := re.fullmatch(rf"command -v ({_NAME})|Get-Command ({_NAME}) -ErrorAction SilentlyContinue", command):
        return Check(command, [], which=m[1] or m[2])
    if m := re.fullmatch(rf"npm ls -g --depth=0 ({_NPM})", command, re.I):
        return Check(command, ["npm", "ls", "-g", "--depth=0", m[1]])
    if m := re.fullmatch(rf"(uv tool list|pipx list --short|cargo install --list){_ONLY}", command):
        return Check(command, m[1].split(), only=m[2] or m[3])
    if m := re.fullmatch(rf"brew list --versions ({_NAME})", command):
        return Check(command, ["brew", "list", "--versions", m[1]])
    if m := re.fullmatch(rf"(python3|py) -m pip show ({_NAME})", command):
        return Check(command, [m[1], "-m", "pip", "show", m[2]])
    if m := re.fullmatch(rf"claude mcp get ({_NAME})", command):
        return Check(command, ["claude", "mcp", "get", m[1]])
    if m := re.fullmatch(rf'mdls -name kMDItemLastUsedDate -raw "(/Applications/{_APP}\.app)"', command):
        return Check(command, ["mdls", "-name", "kMDItemLastUsedDate", "-raw", m[1]], last_used=True)
    return None


Run = Callable[..., subprocess.CompletedProcess[str]]


def found(check: Check, run: Run, which: Callable[[str], str | None]) -> bool | None:
    """True: it is there; False: it is not; None: this check could not tell (e.g. no npm here)."""
    if check.which:
        return which(check.which) is not None
    try:
        proc = run(check.argv, capture_output=True, text=True, timeout=TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if check.only:
        prefix = check.only.lower() + " "
        return proc.returncode == 0 and any(line.lower().startswith(prefix) for line in proc.stdout.splitlines())
    return proc.returncode == 0 and bool(proc.stdout.strip())


def bucket(mdls_output: str, now: datetime) -> str | None:
    """`2026-10-28 03:12:45 +0000` -> this_week / this_month / older; (null) or anything else -> None."""
    try:
        when = datetime.strptime(mdls_output.strip(), "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return None
    days = (now - when).total_seconds() / 86_400
    return "this_week" if days < 7 else "this_month" if days < 31 else "older"


def load(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else [data]
    good = []
    for item in items:
        if not (isinstance(item, dict) and _REC_ID.match(str(item.get("rec_id"))) and _SLUG.match(str(item.get("slug")))):
            print(f"skipped an entry without a valid rec_id and slug: {str(item)[:80]}")
            continue
        good.append(item)
    return good


Ask = Callable[[str], str]


def check_tool(item: dict[str, Any], *, run: Run, which: Callable[[str], str | None], ask: Ask,
               now: datetime) -> dict[str, Any] | None:
    """Run the allowed checks for one tool, ask the user, and return report_outcome's arguments
    (or None when the user skips it)."""
    name = item.get("name") or item["slug"]
    print(f"\n== {name} ({item['slug']})")
    results: list[bool | None] = []
    seen: str | None = None
    for entry in (item.get("check_in") or {}).get("commands") or []:
        command = str(entry.get("command", "")) if isinstance(entry, dict) else ""
        check = parse(command)
        if check is None:
            print(f"  skipped (not a form pickfit writes): {command[:100]}")
            continue
        if check.last_used:
            try:
                proc = run(check.argv, capture_output=True, text=True, timeout=TIMEOUT_S)
                seen = bucket(proc.stdout, now) if proc.returncode == 0 else None
            except (OSError, subprocess.TimeoutExpired):
                seen = None
            print(f"  {command}\n    -> last opened: {seen or 'not recorded'}")
            continue
        result = found(check, run, which)
        results.append(result)
        print(f"  {command}\n    -> {'found' if result else 'not found' if result is False else 'could not tell'}")
    installed = True if any(results) else False if results and all(r is False for r in results) else None
    print(f"  still installed: {'yes' if installed else 'no' if installed is False else 'could not tell'}")

    if installed is False:
        answer = ask(f"  {name} looks uninstalled. Do you still use it? [y]es / [n]o / [s]kip (Enter: no): ")
        answer = answer.strip().lower() or "n"
    else:
        answer = ask(f"  Do you still use {name}? [y]es / [n]o / [s]kip (Enter: skip): ").strip().lower() or "s"
    if answer.startswith("s"):
        print("  skipped: nothing will be sent for this tool")
        return None
    stage = "still_using" if answer.startswith("y") else "abandoned"
    replaced_by = None
    if stage == "abandoned":
        other = ask("  Did something replace it? Its name, or Enter for no: ").strip()
        if other:
            stage, replaced_by = "replaced", other[:100]
    last_used = seen
    if last_used is None and stage == "still_using":
        letter = ask("  When did you last use it? [w]eek / [m]onth / [o]lder / [u]nknown: ").strip().lower()[:1]
        last_used = {"w": "this_week", "m": "this_month", "o": "older"}.get(letter, "unknown")
    report: dict[str, Any] = {"slug": item["slug"], "rec_id": item["rec_id"], "stage": stage,
                              "last_used": last_used or "unknown"}
    if replaced_by:
        report["replaced_by"] = replaced_by
    return report


def post(endpoint: str, report: dict[str, Any], reporter: str, call_id: int) -> dict[str, Any]:
    """One MCP tools/call of report_outcome (the server is stateless: no session to open)."""
    body = {"jsonrpc": "2.0", "id": call_id, "method": "tools/call",
            "params": {"name": "report_outcome", "arguments": report}}
    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream",
               "mcp-protocol-version": "2025-11-25"}
    if reporter != "external":
        headers["x-pickfit-reporter"] = reporter
    request = urllib.request.Request(endpoint, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 (https endpoint)
        text = response.read().decode()
    data = text if text.startswith("{") else next(line[6:] for line in text.splitlines() if line.startswith("data: "))
    return json.loads(data)


def main(argv: list[str] | None = None, *, run: Run = subprocess.run,
         which: Callable[[str], str | None] = shutil.which, ask: Ask = input,
         send: Callable[[str, dict[str, Any], str, int], dict[str, Any]] = post,
         now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file", type=Path, help="JSON with rec_id, slug, name and check_in per tool")
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--dry-run", action="store_true", help="show what would be sent; send nothing")
    parser.add_argument("--reporter", choices=("external", "demo", "dev"), default="external",
                        help="demo or dev: marked as pickfit's own run and kept out of scores")
    args = parser.parse_args(argv)

    reports = [r for item in load(args.file) if (r := check_tool(item, run=run, which=which, ask=ask, now=now()))]
    if not reports:
        print("\nNothing to send.")
        return 0
    print(f"\nThis is everything that would be sent to {args.endpoint} (report_outcome), one call per tool:")
    print(json.dumps(reports, indent=2))
    if args.dry_run:
        print("--dry-run: nothing sent.")
        return 0
    if ask("Type yes to send: ").strip().lower() != "yes":
        print("Nothing sent.")
        return 0
    failed = 0
    for i, report in enumerate(reports, 1):
        try:
            reply = send(args.endpoint, report, args.reporter, i)
        except Exception as err:  # noqa: BLE001 (report and go on)
            failed += 1
            print(f"{report['slug']}: not sent ({type(err).__name__})")
            continue
        out = (reply.get("result") or {}).get("structuredContent") or {}
        if reply.get("error") or (reply.get("result") or {}).get("isError") or not out:
            failed += 1
            print(f"{report['slug']}: refused by pickfit")
            continue
        counted = "counted" if out.get("counted_in_score") else f"stored, not counted ({out.get('not_counted_reason')})"
        print(f"{report['slug']}: sent, {counted}{', already reported' if out.get('deduplicated') else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
