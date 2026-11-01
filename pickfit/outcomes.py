"""`pickfit outcomes sync`: usage reports from the Worker's D1 into data/software. No model call.

Reads the counted report_outcome rows from D1 (read-only: one SELECT), keeps one result per
recommendation and stage, the latest (score.outcomes_from_events), and writes per-slug counts into
each record's `outcomes`. The record's scores are then refreshed (score.refresh_scores), so
`pickfit publish` carries the result to the Worker. usage_outcomes still has no score below 3
outside reports (USAGE_MIN_REPORTS).

Only outside reports go in. The rule:
- reporter must be 'external', the Worker's value when no X-Pickfit-Reporter header is sent. eval,
  demo and dev are this project's own runs: sessions that check the live Worker send the header,
  and scripts/checkin.py has --reporter.
- a check that forgot the header can be left out with --exclude FILE: rec_ids, one per line, in a
  file kept outside the repo.

What reaches the repo, per slug: counts per stage and replacement names (plain names only;
anything else counts as "other"). Never a rec_id, a report time, a note, an error excerpt, an OS or
a client. eval, demo and dev stay zero, and last_report_at and synced_at stay null. last_used
buckets are printed, not stored: Outcomes has no field for them yet, and adding one rewrites every
record (the schema requires every field).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pickfit.d1 import Database
from pickfit.schema import Outcomes, SoftwareRecord, StageCounts
from pickfit.score import outcomes_from_events, refresh_scores

# score.OUTCOME_ROWS plus last_used (printed only): rec_id IS NOT NULL is the Worker's "counted" mark.
ROWS = (
    "SELECT rec_id, slug, ts, stage, success, replaced_by, reporter, last_used FROM events "
    "WHERE type = 'outcome' AND rec_id IS NOT NULL"
)
OUTSIDE = "external"
_PLAIN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._+/@-]{0,59}$")
_REC_ID = re.compile(r"^rec_[0-9a-f]{32}$")


@dataclass
class Read:
    """What the D1 rows came to, before anything is written."""

    outcomes: dict[str, Outcomes]
    last_used: dict[str, dict[str, int]] = field(default_factory=dict)  # slug -> bucket -> latest reports
    rows: int = 0
    not_outside: dict[str, int] = field(default_factory=dict)  # reporter -> rows left out
    excluded: int = 0  # rows left out by --exclude


def load_exclude(path: Path | None) -> set[str]:
    if path is None:
        return set()
    ids = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()}
    bad = sorted(i for i in ids if i and not i.startswith("#") and not _REC_ID.match(i))
    if bad:
        raise ValueError(f"--exclude: not a rec_id: {bad[0][:40]}")
    return {i for i in ids if _REC_ID.match(i)}


def read_outcomes(rows: list[dict[str, Any]], exclude: Collection[str] = frozenset()) -> Read:
    """Outside reports only, one latest result per (slug, rec_id, stage), as record `outcomes`."""
    out = Read(outcomes={}, rows=len(rows))
    kept = []
    for row in rows:
        reporter = row.get("reporter")
        if reporter != OUTSIDE:
            key = str(reporter)
            out.not_outside[key] = out.not_outside.get(key, 0) + 1
        elif row.get("rec_id") in exclude:
            out.excluded += 1
        else:
            kept.append(row)
    counted = outcomes_from_events(kept)
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(kept, key=lambda r: r["ts"]):
        if row["stage"] == "still_using":
            latest[(row["slug"], row["rec_id"])] = row
    for slug, outcomes in counted.items():
        replaced: dict[str, int] = {}
        for name, n in outcomes.replaced_by.items():
            key = name.strip() if _PLAIN_NAME.match(name.strip()) else "other"
            replaced[key] = replaced.get(key, 0) + n
        buckets: dict[str, int] = {}
        for (row_slug, _), row in latest.items():
            if row_slug == slug:
                bucket = row.get("last_used") or "unknown"
                buckets[bucket] = buckets.get(bucket, 0) + 1
        out.outcomes[slug] = Outcomes(external=outcomes.external, replaced_by=dict(sorted(replaced.items())))
        if buckets:
            out.last_used[slug] = dict(sorted(buckets.items()))
    return out


def _changes(before: Outcomes, after: Outcomes) -> list[str]:
    parts = []
    for stage in StageCounts.model_fields:
        old, new = getattr(before.external, stage), getattr(after.external, stage)
        if old != new:
            parts.append(f"{stage} {old}->{new}")
    if before.replaced_by != after.replaced_by:
        parts.append(f"replaced_by {json.dumps(before.replaced_by, ensure_ascii=False)}->"
                     f"{json.dumps(after.replaced_by, ensure_ascii=False)}")
    for name in ("eval", "demo", "dev"):
        if getattr(before, name).total():
            parts.append(f"{name} reports cleared ({getattr(before, name).total()})")
    if before.last_report_at or before.synced_at:
        parts.append("timestamps cleared")
    return parts


def sync(data_dir: Path, db: Database, *, now: datetime, dry_run: bool = False,
         exclude: Collection[str] = frozenset(), log: Callable[[str], None] = print) -> int:
    """Write each record's `outcomes` from D1 and refresh its scores; print what changes per slug."""
    read = read_outcomes(db.query(ROWS), exclude)
    left_out = ", ".join(f"{k} {v}" for k, v in sorted(read.not_outside.items())) or "none"
    log(f"D1: {read.rows} counted outcome rows; left out as our own (reporter): {left_out}; "
        f"left out by --exclude: {read.excluded}; outside reports for {len(read.outcomes)} slugs")
    paths = {p.stem: p for p in sorted(data_dir.glob("*.json"))}
    for slug in sorted(set(read.outcomes) - set(paths)):
        log(f"  {slug}: reported, but not in {data_dir}; skipped")
    changed = 0
    for slug, path in paths.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        before = Outcomes.model_validate(data.get("outcomes") or {})
        after = read.outcomes.get(slug, Outcomes())
        parts = _changes(before, after)
        if not parts:
            continue
        changed += 1
        old_total = (data.get("scores") or {}).get("quality", {}).get("total")
        data["outcomes"] = after.model_dump(mode="json")
        note = refresh_scores(data, now)
        new_total = (data.get("scores") or {}).get("quality", {}).get("total")
        n = after.external.total()
        score = f"quality {old_total} -> {new_total}" if note else "score unchanged"
        used = f" · last_used {json.dumps(read.last_used[slug])}" if slug in read.last_used else ""
        log(f"  {slug}: {'; '.join(parts)} · {n} outside report{'s' if n != 1 else ''}{used} · {score}")
        if not dry_run:
            data["updated_at"] = now.isoformat(timespec="seconds")
            SoftwareRecord.model_validate(data)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(path)
    verb = "would change" if dry_run else "changed"
    log(f"{changed} record{'s' if changed != 1 else ''} {verb}" + (" (--dry-run: nothing written)" if dry_run else ""))
    return 0
