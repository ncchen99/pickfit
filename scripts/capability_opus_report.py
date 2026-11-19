"""Read the Opus-path check of the capabilities backfill (worker/bench/capability/opus-check.json).

Usage:
    uv run python scripts/capability_opus_report.py [--rows worker/bench/capability/baseline-backfill50-model.json]

Free: it reads the bench's output and prints, for the 31 secondary-capability queries, how often Opus picked the
tool now and before the backfill (baseline-model.json, where that query went to Opus then too), and for the 15 dev
queries, every pick graded by bench/fit-fresh/labels.json (? = never labeled), marking the backfilled tools, beside
the rules path's picks. Rows the run's --cap sent to rules (matchedBy "rules") are counted apart.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "worker" / "bench"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=Path, default=BENCH / "capability" / "baseline-backfill50-model.json")
    parser.add_argument("--index", type=Path, default=ROOT / "worker" / "src" / "generated" / "index.json")
    args = parser.parse_args(argv)

    run = json.loads(args.rows.read_text())
    rows = run["rows"]
    backfilled = {e["slug"] for e in json.loads(args.index.read_text())["entries"] if e.get("capabilities")}
    labels = json.loads((BENCH / "fit-fresh" / "labels.json").read_text())["labels"]
    before = {(r["id"], r["lang"]): r for r in json.loads((BENCH / "capability" / "baseline-model.json").read_text())["rows"]}
    opus = [r for r in rows if r.get("matchedBy") and r["matchedBy"] != "rules"]
    print(f"cost_usd {run['summary'].get('cost_usd')} · matched by Opus {len(opus)}, by rules (past --cap or failed) "
          f"{len(rows) - len(opus)}")

    sub = [r for r in rows if r["slug"] is not None]
    sub_opus = [r for r in sub if r in opus]
    both = [r for r in sub_opus if before.get((r["id"], r["lang"]), {}).get("matchedBy") not in (None, "rules")]
    print("\nsecondary-capability queries on backfilled tools")
    print(f"  Opus now        {sum(r['model'] for r in sub_opus)}/{len(sub_opus)}")
    print(f"  rules now       {sum(r['rules'] for r in sub)}/{len(sub)}")
    print(f"  same queries, Opus before the backfill vs now: "
          f"{sum(before[(r['id'], r['lang'])]['model'] for r in both)}/{len(both)} -> {sum(r['model'] for r in both)}/{len(both)}")

    def graded(qid: str, picks: list[str]) -> str:
        grades = labels.get(qid.removeprefix("dev-"), {})
        return ", ".join(f"{s}:{grades.get(s, '?')}{'*' if s in backfilled else ''}" for s in picks) or "(none)"

    dev = [r for r in rows if r["slug"] is None]
    totals = {"model": [0, 0, 0], "rules": [0, 0, 0]}  # grade-2 picks, backfilled picks never labeled, picks
    print("\ndev queries (pick:grade, * backfilled, ? never labeled)")
    for r in dev:
        qid = r["id"].removeprefix("dev-")
        for side, picks in (("model", r.get("modelPicks") or []), ("rules", r["rulesPicks"])):
            grades = labels.get(qid, {})
            totals[side][0] += sum(grades.get(s) == 2 for s in picks)
            totals[side][1] += sum(s in backfilled and s not in grades for s in picks)
            totals[side][2] += len(picks)
        print(f"  {r['id']} [{r.get('matchedBy')}] opus: {graded(r['id'], r.get('modelPicks') or [])}")
        print(f"  {' ' * len(r['id'])}  rules: {graded(r['id'], r['rulesPicks'])}")
    for side, (good, unlabeled, n) in totals.items():
        print(f"  {side}: {n} picks, {good} graded 2, {unlabeled} backfilled tools never labeled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
