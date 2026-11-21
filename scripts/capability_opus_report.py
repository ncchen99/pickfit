"""Read the Opus-path check of the capabilities backfill (worker/bench/capability/opus-check.json).

Usage:
    uv run python scripts/capability_opus_report.py [--rows worker/bench/capability/baseline-backfill50-model.json]
        [--against OTHER.json]

--rows may be a run on another model (bench/capability.ts --model-id); the report names the model the run used.
--against prints, per query, where two runs differ: the target found or not, and the picks.

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
    parser.add_argument("--against", type=Path, help="another run of the same queries, compared query by query")
    args = parser.parse_args(argv)

    run = json.loads(args.rows.read_text())
    rows = run["rows"]
    backfilled = {e["slug"] for e in json.loads(args.index.read_text())["entries"] if e.get("capabilities")}
    labels = json.loads((BENCH / "fit-fresh" / "labels.json").read_text())["labels"]
    before = {(r["id"], r["lang"]): r for r in json.loads((BENCH / "capability" / "baseline-model.json").read_text())["rows"]}
    opus = [r for r in rows if r.get("matchedBy") and r["matchedBy"] != "rules"]
    model = model_of(run)
    print(f"cost_usd {run['summary'].get('cost_usd')} · matched by {model} {len(opus)}, by rules (past --cap or failed) "
          f"{len(rows) - len(opus)}")

    sub = [r for r in rows if r["slug"] is not None]
    sub_opus = [r for r in sub if r in opus]
    both = [r for r in sub_opus if before.get((r["id"], r["lang"]), {}).get("matchedBy") not in (None, "rules")]
    print("\nsecondary-capability queries on backfilled tools")
    print(f"  {model} now  {sum(r['model'] for r in sub_opus)}/{len(sub_opus)}")
    print(f"  rules now       {sum(r['rules'] for r in sub)}/{len(sub)}")
    print(f"  same queries, Opus before the backfill vs {model} now: "
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
        print(f"  {r['id']} [{r.get('matchedBy')}] model: {graded(r['id'], r.get('modelPicks') or [])}")
        print(f"  {' ' * len(r['id'])}  rules: {graded(r['id'], r['rulesPicks'])}")
    for side, (good, unlabeled, n) in totals.items():
        print(f"  {side}: {n} picks, {good} graded 2, {unlabeled} backfilled tools never labeled")
    if args.against:
        other = json.loads(args.against.read_text())
        print(f"\nwhere {model} ({args.rows.name}) and {model_of(other)} ({args.against.name}) differ")
        for line in differences(rows, other["rows"], graded):
            print(f"  {line}")
    return 0


def model_of(run: dict) -> str:
    """The model a run used: --model-id when it says, else the one most rows were matched by."""
    named = run["summary"].get("model_id")
    if named:
        return named
    counts: dict[str, int] = {}
    for r in run["rows"]:
        if r.get("matchedBy") and r["matchedBy"] != "rules":
            counts[r["matchedBy"]] = counts.get(r["matchedBy"], 0) + 1
    return max(counts, key=counts.get) if counts else "rules"


def differences(rows: list[dict], other: list[dict], graded) -> list[str]:
    """Per query asked in both runs: a target found by one and not the other, or different picks."""
    theirs = {(r["id"], r["lang"]): r for r in other}
    out = []
    for r in rows:
        o = theirs.get((r["id"], r["lang"]))
        if o is None:
            continue
        mine, them = r.get("modelPicks") or [], o.get("modelPicks") or []
        if r["slug"] is not None and r["model"] != o["model"]:
            out.append(f"{r['id']} {r['slug']}: {'found' if r['model'] else 'missed'} here, "
                       f"{'found' if o['model'] else 'missed'} there · here {mine} · there {them}")
        elif r["slug"] is None and sorted(mine) != sorted(them):
            out.append(f"{r['id']}: here {graded(r['id'], mine)} · there {graded(r['id'], them)}")
    return out


if __name__ == "__main__":
    sys.exit(main())
