"""Compare docs-rubric answers before the rubric prompt or the call changes (docs/proposals/scoring.md R2, R4).

Paid: without --run it prints the plan and the estimated cost and calls nothing. Both modes read the READMEs of
scripts/rubric_calibration_set.json (scored records whose README runs/pipeline.db stores; never the evaluation set)
from the pipeline database, read-only, and write their report to --out only:

- --mode prompt: the current rubric prompt (RUBRIC_PROMPT_VERSION) against --new-prompt FILE, the same model, on
  each README. Run it before bumping RUBRIC_PROMPT_VERSION.
- --mode merged: a rubric call against an extraction call that grades the rubric too (extract.RUBRIC_IN_EXTRACTION,
  R4), on the first --limit records. Run it before turning RUBRIC_IN_EXTRACTION on. It also compares the merged
  extraction with the stored one (features, install claims, quote failures), so a rubric riding along does not
  cost the extraction its quality.

The report gives, per item, how often the two agree, the mean absolute difference of install_docs, and the
records whose install_docs moves by 2 points of 16 or more. Estimates use the ledger's averages on Claude Opus 5.5
(11/19): a rubric call US$0.038, an extraction US$0.057, an extraction that grades the rubric too about US$0.068.

    uv run python scripts/compare_rubric.py --mode prompt --new-prompt new-rubric.txt
    uv run python scripts/compare_rubric.py --mode prompt --new-prompt new-rubric.txt --run --out runs/rubric-prompt
    uv run python scripts/compare_rubric.py --mode merged --limit 30 --run --out runs/rubric-merged
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pickfit.discover.store import ReadOnlyPipelineDB
from pickfit.extract import _DONE, build_sources, extract_one, input_sha, same_tier
from pickfit.ledger import taipei_now
from pickfit.meta import resolve_model
from pickfit.schema import DocsRubricItems
from pickfit.score import INSTRUCTIONS, RUBRIC_PROMPT_VERSION, grade_docs

SET = Path(__file__).resolve().parent / "rubric_calibration_set.json"
RUBRIC_USD = 0.038
EXTRACT_USD = 0.057
MERGED_USD = 0.068
ITEMS = tuple(DocsRubricItems.model_fields)


def estimate(mode: str, n: int) -> float:
    return round(n * (2 * RUBRIC_USD if mode == "prompt" else RUBRIC_USD + MERGED_USD), 2)


def compare(pairs: list[tuple[str, dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    """Agreement of two rubric answers per record: (slug, items a, items b)."""
    agree = {name: 0 for name in ITEMS}
    moved, diffs = [], []
    for slug, a, b in pairs:
        for name in ITEMS:
            agree[name] += a[name]["score"] == b[name]["score"]
        pa, pb = (sum(x[n]["score"] for n in ITEMS) for x in (a, b))
        diffs.append(abs(pa - pb) / 16)
        if abs(pa - pb) >= 2:
            moved.append({"slug": slug, "before": pa, "after": pb})
    n = len(pairs) or 1
    return {"records": len(pairs), "agreement": {k: round(v / n, 3) for k, v in agree.items()},
            "mean_abs_install_docs": round(sum(diffs) / n, 4), "moved_2_points_or_more": moved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("prompt", "merged"), required=True)
    parser.add_argument("--new-prompt", default=None, help="--mode prompt: a file with the new rubric instructions")
    parser.add_argument("--set", default=str(SET))
    parser.add_argument("--db", default="runs/pipeline.db")
    parser.add_argument("--model", default="prod")
    parser.add_argument("--limit", type=int, default=None, help="the first N records (merged: 30 is the plan)")
    parser.add_argument("--run", action="store_true", help="make the calls (paid); without it, print the plan")
    parser.add_argument("--out", default="runs/rubric-compare")
    args = parser.parse_args(argv)
    if args.mode == "prompt" and not args.new_prompt:
        parser.error("--mode prompt needs --new-prompt")
    members = json.loads(Path(args.set).read_text(encoding="utf-8"))["records"]
    limit = args.limit if args.limit is not None else (30 if args.mode == "merged" else len(members))
    members = members[:limit]
    model = resolve_model(args.model)
    plan = {"mode": args.mode, "model": model, "records": len(members), "estimated_usd": estimate(args.mode, len(members))}
    if not args.run:
        print(json.dumps(plan | {"run": "add --run to make the calls"}, indent=2))
        return 0
    db = ReadOnlyPipelineDB(args.db)
    now = taipei_now()
    run_id = f"rubric-compare-{now.strftime('%Y%m%d-%H%M%S')}"
    new_prompt = Path(args.new_prompt).read_text(encoding="utf-8") if args.new_prompt else None
    pairs, extraction_rows, errors, spent = [], [], {}, 0.0
    for member in members:
        candidate = db.candidate(member["repo_id"])
        if candidate is None or not (candidate.get("readme") or "").strip():
            errors[member["slug"]] = "no README in the database"
            continue
        sources = build_sources(candidate)
        common = {"model": model, "run_id": run_id, "now": now, "input_sha": input_sha(candidate)}
        before = grade_docs(sources, scope=f"rubric-compare:{member['slug']}", **common)
        spent += before.cost_usd
        if args.mode == "prompt":
            after = grade_docs(sources, scope=f"rubric-compare-new:{member['slug']}", instructions=new_prompt,
                               prompt_version=f"{RUBRIC_PROMPT_VERSION}-candidate", **common)
            spent += after.cost_usd
            other = after.rubric.items.model_dump(mode="json") if after.rubric else None
        else:
            row = extract_one(candidate, model=model, run_id=run_id, reasoning_effort="minimal", with_rubric=True)
            spent += row["cost_usd"]
            other = (row.get("rubric") or {}).get("items")
            stored = next((r for m in same_tier(model) if (r := db.last_extraction(member["repo_id"], m, _DONE))),
                          None)  # the extraction records were built from, by this model's tier
            extraction_rows.append({
                "slug": member["slug"], "status": row["status"],
                "features": [len((x or {}).get("result", {}).get("features") or []) if x else None
                             for x in (stored, row)],
                "install_methods": [len((x or {}).get("result", {}).get("install_methods") or []) if x else None
                                    for x in (stored, row)],
                "quote_failures": [len((x or {}).get("quote_failures") or []) if x else None for x in (stored, row)]})
        if before.rubric is None or other is None:
            errors[member["slug"]] = before.error or "no rubric from the second answer"
            continue
        pairs.append((member["slug"], before.rubric.items.model_dump(mode="json"), other))
    report = plan | compare(pairs) | {"cost_usd": round(spent, 4), "errors": errors,
                                      "extractions (stored, merged)": extraction_rows or None}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.mode}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "extractions (stored, merged)"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
