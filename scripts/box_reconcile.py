"""Compare pickfit's machine estimates (the ledger's boxes table) with what the providers billed, by day and provider.

The estimates are what pickfit.verify.meter wrote for every Modal sandbox, EC2 instance and rented Mac. The bills are
files you export from the providers' own tools; this script reads files only and calls no provider:

    uv run python scripts/box_reconcile.py --print-commands --since 2026-11-19 --until 2026-11-26
    # run those two commands (they need Modal's and AWS's logins), then:
    uv run python scripts/box_reconcile.py --since 2026-11-19 --until 2026-11-26 \\
        --modal-report modal-report.json --aws-cost aws-cost.json [--actual scaleway.csv] [--json]

- Modal: `modal billing report --json` (or --csv). Modal bills an app, not a sandbox: the rows of the app the boxes
  run in (--modal-app, pickfit-verify) are compared; other objects of the workspace are shown apart.
- AWS: Cost Explorer's GetCostAndUsage answer, daily, for instances tagged pickfit=verify, grouped by the
  pickfit:purpose tag. The tags count only once the account's owner has activated them as cost allocation tags,
  and only from then on.
- Anything else (a Scaleway invoice): a CSV with day,provider,usd.

Days are UTC days, as the providers bill them. A box that spans midnight is split by the time it ran on each day.
A rented Mac counts once, as its own row; the shares of it written to its VMs are a run's cost, not more spending.
A box still open is priced up to now (a rented Mac, at least its first 24 h). Exit 0; the table is the result.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pickfit.ledger import DEFAULT_PATH, BoxLedger, box_cost  # noqa: E402

MODAL_APP = "pickfit-verify"
Key = tuple[str, str]  # (UTC day, provider)


def _utc(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone(UTC)


def _split_by_day(start: datetime, end: datetime, usd: float) -> dict[str, float]:
    """usd spread over the UTC days between start and end, by the seconds in each."""
    total = (end - start).total_seconds()
    if total <= 0:
        return {start.date().isoformat(): usd}
    parts: dict[str, float] = {}
    moment = start
    while moment < end:
        midnight = datetime.combine(moment.date() + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        upto = min(midnight, end)
        parts[moment.date().isoformat()] = parts.get(moment.date().isoformat(), 0.0) + usd * (
            (upto - moment).total_seconds() / total)
        moment = upto
    return parts


def estimates(rows: list[dict[str, Any]], now: datetime) -> tuple[dict[Key, float], dict[str, Any]]:
    """{(day, provider): estimated USD} from the ledger's rows, and what could not be priced."""
    out: dict[Key, float] = defaultdict(float)
    notes = {"open": 0, "unknown_end": 0, "unpriced": 0, "shares_skipped": 0, "boxes": 0}
    for row in rows:
        if row.get("share_of"):  # a share of a rented host: the host's own row counts it
            notes["shares_skipped"] += 1
            continue
        if row.get("end_note") == "unknown":
            notes["unknown_end"] += 1
            continue
        start = _utc(row["started_at"])
        if row.get("ended_at"):
            end, usd = _utc(row["ended_at"]), row.get("est_usd")
        else:  # still open: up to now
            notes["open"] += 1
            end = max(start, now)
            usd = box_cost(row.get("rate_usd_per_hour"), (end - start).total_seconds(), row.get("min_billed_s") or 0)
        if usd is None:
            if row.get("rate_usd_per_hour") is None and row.get("provider") != "tart":
                notes["unpriced"] += 1
            continue
        notes["boxes"] += 1
        for day, part in _split_by_day(start, end, float(usd)).items():
            out[(day, row["provider"])] += part
    return dict(out), notes


def _rows_of(text: str) -> list[dict[str, Any]]:
    """JSON (a list of objects) or CSV with a header row."""
    stripped = text.lstrip()
    if stripped.startswith("["):
        return list(json.loads(stripped))
    return list(csv.DictReader(io.StringIO(text)))


def _field(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(k).strip().lower().replace(" ", "_"): v for k, v in row.items()}
    return next((lowered[n] for n in names if n in lowered), None)


def modal_actual(text: str, app: str = MODAL_APP) -> tuple[dict[Key, float], dict[str, float]]:
    """({(day, "modal"): USD} for the app's rows, {day: USD} of the workspace's other objects)."""
    ours: dict[Key, float] = defaultdict(float)
    other: dict[str, float] = defaultdict(float)
    for row in _rows_of(text):
        day = str(_field(row, "interval_start") or "")[:10]
        cost = float(_field(row, "cost") or 0)
        if not day:
            continue
        name = str(_field(row, "description") or "")
        if app and name != app:
            other[day] += cost
        else:
            ours[(day, "modal")] += cost
    return dict(ours), dict(other)


def aws_actual(text: str) -> tuple[dict[Key, float], dict[str, dict[str, float]]]:
    """({(day, "ec2"): USD}, {day: {purpose: USD}}) from a GetCostAndUsage answer (UnblendedCost)."""
    data = json.loads(text)
    total: dict[Key, float] = defaultdict(float)
    by_purpose: dict[str, dict[str, float]] = defaultdict(dict)
    for period in data.get("ResultsByTime", []):
        day = period["TimePeriod"]["Start"][:10]
        groups = period.get("Groups") or []
        if groups:
            for group in groups:
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                purpose = group["Keys"][0].split("$", 1)[-1] or "(untagged)"
                by_purpose[day][purpose] = by_purpose[day].get(purpose, 0.0) + amount
                total[(day, "ec2")] += amount
        else:
            total[(day, "ec2")] += float(period.get("Total", {}).get("UnblendedCost", {}).get("Amount", 0))
    return dict(total), dict(by_purpose)


def generic_actual(text: str) -> dict[Key, float]:
    out: dict[Key, float] = defaultdict(float)
    for row in csv.DictReader(io.StringIO(text)):
        out[(row["day"].strip()[:10], row["provider"].strip())] += float(row["usd"])
    return dict(out)


def reconcile(estimated: dict[Key, float], actual: dict[Key, float], *, since: date | None = None,
              until: date | None = None) -> list[dict[str, Any]]:
    """One line per (day, provider): estimated, actual (None when no bill was given for that provider), the
    difference (actual - estimated) and the ratio."""
    billed = {provider for _, provider in actual}
    keys = sorted(set(estimated) | set(actual))
    lines = []
    for day, provider in keys:
        when = date.fromisoformat(day)
        if (since and when < since) or (until and when >= until):
            continue
        est = round(estimated.get((day, provider), 0.0), 4)
        act = round(actual[(day, provider)], 4) if (day, provider) in actual else (0.0 if provider in billed else None)
        lines.append({"day": day, "provider": provider, "estimated_usd": est, "actual_usd": act,
                      "diff_usd": None if act is None else round(act - est, 4),
                      "ratio": None if act is None or not est else round(act / est, 3)})
    return lines


def totals(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for line in lines:
        entry = by.setdefault(line["provider"], {"provider": line["provider"], "estimated_usd": 0.0,
                                                 "actual_usd": None})
        entry["estimated_usd"] = round(entry["estimated_usd"] + line["estimated_usd"], 4)
        if line["actual_usd"] is not None:
            entry["actual_usd"] = round((entry["actual_usd"] or 0.0) + line["actual_usd"], 4)
    for entry in by.values():
        act, est = entry["actual_usd"], entry["estimated_usd"]
        entry["diff_usd"] = None if act is None else round(act - est, 4)
        entry["ratio"] = None if act is None or not est else round(act / est, 3)
    return sorted(by.values(), key=lambda e: e["provider"])


def commands(since: date, until: date) -> list[str]:
    """What to run (with Modal's and AWS's logins) to make the bill files this script reads."""
    return [
        f"modal billing report --start {since} --end {until} --json > modal-report.json",
        "aws ce get-cost-and-usage --region us-east-1 "
        f"--time-period Start={since},End={until} --granularity DAILY --metrics UnblendedCost "
        "--filter '{\"Tags\": {\"Key\": \"pickfit\", \"Values\": [\"verify\"]}}' "
        "--group-by Type=TAG,Key=pickfit:purpose > aws-cost.json",
    ]


def _money(value: float | None) -> str:
    return "-" if value is None else f"{value:9.4f}"


def render(lines: list[dict[str, Any]], sums: list[dict[str, Any]], notes: dict[str, Any]) -> str:
    out = [f"{'day':<10}  {'provider':<9} {'estimated':>9} {'actual':>9} {'diff':>9} {'ratio':>6}"]
    for line in lines + [{"day": "total", **s} for s in sums]:
        ratio = "-" if line["ratio"] is None else f"{line['ratio']:6.2f}"
        out.append(f"{line['day']:<10}  {line['provider']:<9} {_money(line['estimated_usd'])} "
                   f"{_money(line['actual_usd'])} {_money(line['diff_usd'])} {ratio:>6}")
    out.append(f"{notes['boxes']} boxes priced ({notes['open']} still open, priced to now); "
               f"{notes['unknown_end']} with no known end and {notes['unpriced']} with no price left out; "
               f"{notes['shares_skipped']} VM shares of a rented host counted once, as the host")
    for day, cost in sorted((notes.get("modal_other") or {}).items()):
        out.append(f"modal, {day}: US${cost:.4f} for other objects of the workspace (not {MODAL_APP})")
    return "\n".join(out)


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ledger", default=None, help=f"the ledger (default PICKFIT_LEDGER or {DEFAULT_PATH})")
    parser.add_argument("--since", type=date.fromisoformat, default=None, help="first UTC day (YYYY-MM-DD)")
    parser.add_argument("--until", type=date.fromisoformat, default=None, help="the day after the last (exclusive)")
    parser.add_argument("--modal-report", type=Path, help="`modal billing report --json` (or --csv) output")
    parser.add_argument("--modal-app", default=MODAL_APP, help=f"the Modal app the boxes run in ({MODAL_APP})")
    parser.add_argument("--aws-cost", type=Path, help="Cost Explorer's GetCostAndUsage answer (JSON)")
    parser.add_argument("--actual", type=Path, action="append", default=[], help="CSV of day,provider,usd")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    parser.add_argument("--print-commands", action="store_true", help="print the commands that make the bill files")
    args = parser.parse_args(argv)
    now = now or datetime.now(UTC)
    if args.print_commands:
        since = args.since or (now - timedelta(days=7)).date()
        until = args.until or (now + timedelta(days=1)).date()
        print("\n".join(commands(since, until)))
        return 0
    from pickfit.env import get_env

    ledger = BoxLedger(args.ledger or get_env("PICKFIT_LEDGER") or DEFAULT_PATH)
    rows = ledger.boxes()
    estimated, notes = estimates(rows, now)
    actual: dict[Key, float] = {}
    purposes: dict[str, dict[str, float]] = {}
    if args.modal_report:
        ours, notes["modal_other"] = modal_actual(args.modal_report.read_text(encoding="utf-8"), args.modal_app)
        actual.update(ours)
    if args.aws_cost:
        ec2, purposes = aws_actual(args.aws_cost.read_text(encoding="utf-8"))
        actual.update(ec2)
    for path in args.actual:
        for key, usd in generic_actual(path.read_text(encoding="utf-8")).items():
            actual[key] = actual.get(key, 0.0) + usd
    lines = reconcile(estimated, actual, since=args.since, until=args.until)
    sums = totals(lines)
    if args.json:
        print(json.dumps({"days": lines, "totals": sums, "notes": notes, "aws_by_purpose": purposes},
                         indent=2, ensure_ascii=False))
    else:
        print(render(lines, sums, notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
