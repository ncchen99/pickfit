"""The fixed set of READMEs a docs-rubric prompt is compared on before it changes (docs/proposals/scoring.md R2).

Picks about 50 scored records (data/software, read only; never eval/) whose repository is a candidate in the
pipeline database, so the README the rubric reads is stored and a comparison needs no GitHub call. The set is
spread over categories, over the stored install_docs score (low below 0.5, high from 0.8, mid between) and over
the model that graded it (Muse or Claude), and inside each group taken in the order of sha256(slug), so the same
inputs give the same set. Prints the set as JSON for scripts/rubric_calibration_set.json; scripts/compare_rubric.py
reads that file. Changing the set changes what a comparison means: add to it, do not swap members, and say why in
the commit.

    uv run python scripts/rubric_calibration_set.py --db runs/pipeline.db > scripts/rubric_calibration_set.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

SIZE = 50


def band(score: float) -> str:
    return "low" if score < 0.5 else "high" if score >= 0.8 else "mid"


def members(data_dir: Path, db: Path) -> list[dict[str, Any]]:
    """Every record that can be in the set: graded, not a hosted web app, its README stored in `db`."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    stored = {row[0] for row in conn.execute(
        "SELECT repo_id FROM candidates WHERE details_at IS NOT NULL AND readme IS NOT NULL AND readme != ''")}
    conn.close()
    out = []
    for path in sorted(data_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        rubric = (record.get("scores") or {}).get("docs_rubric")
        if record.get("kind") == "web_app" or not rubric or record["repo_id"] not in stored:
            continue
        docs = record["scores"]["quality"]["components"]["install_docs"]["score"]
        out.append({"slug": record["slug"], "repo_id": record["repo_id"], "category": record["category"],
                    "install_docs": docs, "band": band(docs),
                    "grader": "muse" if rubric["model"].startswith("muse-") else "claude"})
    return out


def pick(pool: list[dict[str, Any]], size: int = SIZE) -> list[dict[str, Any]]:
    """Round-robin over (category, band, grader) groups, each in sha256(slug) order."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for m in sorted(pool, key=lambda m: hashlib.sha256(m["slug"].encode()).hexdigest()):
        groups.setdefault((m["category"], m["band"], m["grader"]), []).append(m)
    queues = [groups[key] for key in sorted(groups)]
    chosen: list[dict[str, Any]] = []
    while queues and len(chosen) < size:
        for queue in queues:
            if queue and len(chosen) < size:
                chosen.append(queue.pop(0))
        queues = [q for q in queues if q]
    return sorted(chosen, key=lambda m: m["slug"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data/software")
    parser.add_argument("--db", default="runs/pipeline.db")
    parser.add_argument("--size", type=int, default=SIZE)
    args = parser.parse_args(argv)
    pool = members(Path(args.data_dir), Path(args.db))
    chosen = pick(pool, args.size)
    print(json.dumps({"about": "docs-rubric calibration set (docs/proposals/scoring.md R2); built by "
                               "scripts/rubric_calibration_set.py from records whose README runs/pipeline.db stores",
                      "pool": len(pool), "records": chosen}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
