"""What the ingest loop may spend, and what has been spent since its caps were set (docs/loop.md).

Since 2026-11-15 the shared ledger stops no call unless the user sets a cap, so the loop keeps its own, in
loop/budget.json, counted from that file's `since`:

- model: every model call a pickfit session makes is a row in the shared ledger (~/.pickfit/ledger.sqlite).
  The rows since `since`, of every budget and provider, are what the pipeline spent on models, whichever
  session made the call: the credit they draw on is one balance.
- box: Modal sandbox time. Modal's bill is not in the ledger. Each verification run writes pickfit's own
  estimate (box_usd in runs/verify/<run>/outcome.json) and those are added up. Image builds, limit tests and
  web runs are not in that sum, so the cap is set well under the credit that is left.

    uv run python scripts/loop_budget.py status              # one line: spent / cap, in all and today
    uv run python scripts/loop_budget.py status --exit-code  # exit 4 when a cap is reached

scripts/loop_guard.py refuses a paid pipeline command once a cap is reached, and scripts/loop.sh starts no
batch. Standard library only; runs under the system Python (the guard imports it).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOP_DIR = REPO_ROOT / "loop"
RUNS_DIR = REPO_ROOT / "runs"
DEFAULT_LEDGER = Path.home() / ".pickfit" / "ledger.sqlite"
TAIPEI = timezone(timedelta(hours=8), "Asia/Taipei")  # as pickfit.ledger: the ledger's day is Taipei's
ACCOUNTS = ("model", "box")
# What counts in the ledger: the reservation while a call is open, the actual cost after (pickfit.ledger._SPEND).
_SPEND = "COALESCE(SUM(CASE WHEN status = 'reserved' THEN reserved_usd ELSE cost_usd END), 0)"


class BudgetError(Exception):
    """loop/budget.json is missing or does not say what the caps are."""


def load(loop_dir: Path = LOOP_DIR) -> dict[str, Any]:
    path = loop_dir / "budget.json"
    try:
        budget = json.loads(path.read_text())
        since = datetime.fromisoformat(budget["since"])
        caps = {name: {key: float(budget[f"{name}_usd"][key]) for key in ("total", "daily")} for name in ACCOUNTS}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise BudgetError(f"{path}: {type(error).__name__}: {error}") from error
    if since.tzinfo is None:
        raise BudgetError(f"{path}: `since` needs a UTC offset, e.g. 2026-11-15T23:55:00+08:00")
    if any(value < 0 for cap in caps.values() for value in cap.values()):
        raise BudgetError(f"{path}: a cap cannot be negative")
    return {"since": since, "caps": caps, "item_usd": float(budget.get("item_usd", 0))}


def model_spend(ledger: Path, since: datetime, today: str) -> tuple[float, float]:
    """(since `since`, today) in USD from the shared ledger; nothing when there is no ledger yet."""
    if not ledger.exists():
        return 0.0, 0.0
    start = since.astimezone(TAIPEI).isoformat()  # the ledger writes Taipei time, so text order is time order
    with sqlite3.connect(str(ledger), timeout=10) as conn:
        total = conn.execute(f"SELECT {_SPEND} FROM calls WHERE ts >= ?", (start,)).fetchone()[0]
        day = conn.execute(f"SELECT {_SPEND} FROM calls WHERE ts >= ? AND day = ?", (start, today)).fetchone()[0]
    return float(total), float(day)


def box_spend(runs_dir: Path, since: datetime, today: str) -> tuple[float, float]:
    """(since `since`, today) in USD: pickfit's estimate of each verification run's sandbox time."""
    total = day = 0.0
    for path in (runs_dir / "verify").glob("*/outcome.json"):
        try:
            written = datetime.fromtimestamp(path.stat().st_mtime, TAIPEI)
            if written < since:
                continue
            usd = float(json.loads(path.read_text()).get("box_usd") or 0)
        except (OSError, ValueError, TypeError):
            continue
        total += usd
        if written.date().isoformat() == today:
            day += usd
    return total, day


def report(loop_dir: Path = LOOP_DIR, *, ledger: Path | None = None, runs_dir: Path | None = None,
           now: datetime | None = None) -> dict[str, Any]:
    """Spent and cap for each account, and `reached`: the caps that leave no room."""
    budget = load(loop_dir)
    now = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    today = now.date().isoformat()
    ledger = ledger or Path(os.environ.get("PICKFIT_LEDGER") or DEFAULT_LEDGER)
    spent = {"model": model_spend(ledger, budget["since"], today),
             "box": box_spend(runs_dir or RUNS_DIR, budget["since"], today)}
    out: dict[str, Any] = {"since": budget["since"].isoformat(), "item_usd": budget["item_usd"], "reached": []}
    for name in ACCOUNTS:
        total, day = spent[name]
        cap = budget["caps"][name]
        out[name] = {"spent": round(total, 4), "cap": cap["total"], "today": round(day, 4), "daily_cap": cap["daily"]}
        if total >= cap["total"]:
            out["reached"].append(f"{name} total (${total:.2f} of ${cap['total']:g})")
        elif day >= cap["daily"]:
            out["reached"].append(f"{name} today (${day:.2f} of ${cap['daily']:g})")
    return out


def line(rep: dict[str, Any]) -> str:
    parts = [f"{name}=${rep[name]['spent']:.2f}/{rep[name]['cap']:g} (today ${rep[name]['today']:.2f}/"
             f"{rep[name]['daily_cap']:g})" for name in ACCOUNTS]
    reached = "; reached: " + ", ".join(rep["reached"]) if rep["reached"] else ""
    return "LOOP_BUDGET " + " ".join(parts) + reached


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--loop-dir", type=Path, default=LOOP_DIR)
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument("--runs-dir", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="spent and cap per account")
    status.add_argument("--exit-code", action="store_true", help="exit 4 when a cap is reached")
    args = parser.parse_args(argv)
    try:
        rep = report(args.loop_dir, ledger=args.ledger, runs_dir=args.runs_dir)
    except BudgetError as error:
        print(f"loop_budget: {error}", file=sys.stderr)
        return 2
    print(line(rep))
    return 4 if args.exit_code and rep["reached"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
