"""Stamp the reuse keys on extractions written before them (docs/proposals/scoring.md R3).

Before R3 an extraction was reused only while the sources rendered for the model were byte for byte the same
(sources_sha), so any change to how a README is rendered would have read every candidate again. Now a row carries
input_sha (the raw text it read), prompt_version and renderer_version, and pickfit.extract.extraction_is_current
compares input_sha only.

For each candidate and model, the newest extraction that a reuse check looks at (the newest one that is not a
features-only row, and the newest finished one) gets, when it has no input_sha yet:

- input_sha of the candidate as runs/pipeline.db holds it now: the row is taken to be the current reading, so the
  migration makes nothing be read again;
- renderer_version RENDERER_VERSION when its sources_sha matches the sources as rendered now (it certainly read this
  text), else "r0": the text or the renderer changed since it was read, and nobody can tell which. Under the old
  rule these rows would be read again; `pickfit extract --refresh-before r1` reads exactly them again;
- prompt_version null: not recorded at the time, so older than every version for --refresh-before p<N>.

Rows of hosted web apps (web: ids, not in the candidates table) are left as they are: they are judged as before,
by the rendered sources. A dry run (the default) opens the database read-only and changes nothing; --write stamps.
Run by the coordinator, on the loop worktree's runs/pipeline.db.

    uv run python scripts/migrate_extraction_keys.py --db runs/pipeline.db
    uv run python scripts/migrate_extraction_keys.py --db runs/pipeline.db --write
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from pickfit.discover.store import PipelineDB, ReadOnlyPipelineDB
from pickfit.extract import _DONE, FEATURES_STATUS, RENDERER_VERSION, build_sources, input_sha, sources_sha

LEGACY_RENDERER = "r0"


def plan(db: PipelineDB) -> tuple[list[dict[str, Any]], Counter]:
    """The stamps to write: one per row a reuse check reads that has no input_sha, and counts by outcome."""
    with db._connect() as conn:
        pairs = conn.execute("SELECT DISTINCT repo_id, model FROM extractions ORDER BY repo_id, model").fetchall()
    stamps: list[dict[str, Any]] = []
    counts: Counter = Counter()
    candidates: dict[str, dict[str, Any] | None] = {}
    for pair in pairs:
        repo_id, model = pair["repo_id"], pair["model"]
        rows = {r["id"]: r for r in (db.last_extraction(repo_id, model, exclude=(FEATURES_STATUS,)),
                                     db.last_extraction(repo_id, model, statuses=_DONE)) if r}
        for row in rows.values():
            if row["status"] not in _DONE:
                continue
            if row.get("input_sha"):
                counts["already stamped"] += 1
                continue
            if repo_id not in candidates:
                candidates[repo_id] = db.candidate(repo_id)
            candidate = candidates[repo_id]
            if candidate is None or not candidate.get("repo"):
                counts["left as before (no candidate row)"] += 1
                continue
            same = row["sources_sha"] == sources_sha(build_sources(candidate))
            counts[f"stamp {RENDERER_VERSION} (sources unchanged)" if same
                   else f"stamp {LEGACY_RENDERER} (sources changed since; old rule would read again)"] += 1
            stamps.append({"id": row["id"], "repo_id": repo_id, "model": model, "input_sha": input_sha(candidate),
                           "renderer_version": RENDERER_VERSION if same else LEGACY_RENDERER})
    return stamps, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default="runs/pipeline.db")
    parser.add_argument("--write", action="store_true", help="stamp the rows (default: count only, read-only)")
    args = parser.parse_args(argv)
    path = Path(args.db)
    if not path.exists():
        print(f"no database at {path}", file=sys.stderr)
        return 2
    db = PipelineDB(path) if args.write else ReadOnlyPipelineDB(path)
    stamps, counts = plan(db)
    if args.write:
        for stamp in stamps:
            db.stamp_extraction(stamp["id"], input_sha=stamp["input_sha"], prompt_version=None,
                                renderer_version=stamp["renderer_version"])
    print(json.dumps({"written": args.write, "rows": dict(sorted(counts.items())), "stamps": len(stamps)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
