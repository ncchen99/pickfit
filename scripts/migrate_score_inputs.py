"""Backfill scores.inputs, the raw GitHub signals, from runs/pipeline.db (docs/proposals/scoring.md R1).

Records scored before b3.v7 kept only the 0-1 results of maintenance, engineering_hygiene and responsiveness; the
raw signals stayed in the local runs/pipeline.db, and the issues were fetched live and never stored. For each record
with scores but no scores.inputs (hosted web apps left out: web.v1 has no repository components):

- its repository a candidate with a snapshot in the database: inputs.github from that snapshot (source
  pipeline_db, fetched_at the snapshot's time), so maintenance and hygiene are computed from raw values from now on;
- inputs.issues stays null: the stored responsiveness is kept as inputs.legacy.responsiveness until the next
  `pickfit score` with GitHub fetches and stores the issues;
- not in the database: all three components kept as inputs.legacy, fetched at its next `pickfit score`.

Only scores.inputs (and updated_at) is written; the scores themselves move to b3.v7 with `pickfit score --refresh`
afterwards. A dry run (the default) reads the database read-only and writes nothing. Run by the coordinator, on the
loop worktree's records and database.

    uv run python scripts/migrate_score_inputs.py --data-dir data/software --db runs/pipeline.db
    uv run python scripts/migrate_score_inputs.py --data-dir data/software --db runs/pipeline.db --write
    uv run pickfit score --refresh
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pickfit.discover.store import ReadOnlyPipelineDB
from pickfit.ledger import taipei_now
from pickfit.score import _canonical, _with_scores, _write, github_inputs, legacy_inputs, snapshot_time


def backfill(raw: dict[str, Any], candidate: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
    """The inputs to store for one record, and what was done; None when nothing is to be written. A record that
    already moved to b3.v7 with its components only as legacy (a write-back refreshed it first) gets its GitHub
    inputs too."""
    scores = raw.get("scores")
    if not scores or raw.get("kind") == "web_app":
        return None, "skipped (no scores or a hosted web app)"
    if (scores.get("inputs") or {}).get("github"):
        return None, "already has github inputs"
    inputs = scores.get("inputs") or legacy_inputs(scores["quality"]["components"])
    if candidate and candidate.get("details_at"):
        fetched = snapshot_time(candidate, taipei_now())
        inputs = inputs | {"github": github_inputs(candidate, "pipeline_db", fetched)}
        legacy = {k: v for k, v in (inputs.get("legacy") or {}).items() if k == "responsiveness" and v is not None}
        inputs["legacy"] = legacy or None
        return _canonical(inputs), "github from pipeline_db" + (", responsiveness kept" if legacy else "")
    if scores.get("inputs"):
        return None, "not in pipeline_db, already kept as legacy"
    return _canonical(inputs), "not in pipeline_db: components kept as legacy"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data/software")
    parser.add_argument("--db", default="runs/pipeline.db")
    parser.add_argument("--write", action="store_true", help="write scores.inputs (default: count only)")
    parser.add_argument("--now", default=None, help="updated_at to write (default now, Taipei time)")
    args = parser.parse_args(argv)
    db = ReadOnlyPipelineDB(args.db) if Path(args.db).exists() else None
    now = datetime.fromisoformat(args.now) if args.now else taipei_now()
    counts: Counter = Counter()
    for path in sorted(Path(args.data_dir).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        candidate = db.candidate(raw["repo_id"]) if db is not None and raw.get("repo_id", "").startswith("gh:") \
            else None
        inputs, what = backfill(raw, candidate)
        counts[what] += 1
        if inputs is not None and args.write:
            _write(path, _with_scores(raw, raw["scores"] | {"inputs": inputs}, now.isoformat(timespec="seconds")))
    print(json.dumps({"written": args.write, "records": dict(sorted(counts.items()))}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
