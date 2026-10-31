"""Send changed match requests to Meta: does a shortlist change move the model's final picks?

Usage:
    uv run python scripts/replay_match.py <diff.json> [--out runs/match-replay/results.json] [--cap 2.0] [--limit N]

`diff.json` comes from `node worker/bench/ai_path_same.ts ... --out diff.json`: each match request
whose cards changed, with the old (main) and new body. One request per need and language is sent
(the variant with a category when both changed), largest card change first. The old body goes twice, so the model's own
run-to-run noise can be told apart from the effect of the change, then the new body once.
Requests are sent exactly as the Worker would (muse-spark-1.3, Responses API, strict schema).
Spend goes to the shared pipeline ledger under stage `match-replay`, capped by --cap.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pickfit.env import REPO_ROOT
from pickfit.meta import call_meta

STAGE = "match-replay"
RUN_ID = "match-replay-negation"


def picks(text: str | None) -> dict[str, Any]:
    """The answer's picks (in order) and best free option, or an error."""
    try:
        answer = json.loads(text or "")
    except ValueError:
        return {"error": "bad_output"}
    return {"picks": [p.get("slug") for p in answer.get("picks", [])], "best_free": answer.get("best_free_slug")}


def send(body_json: str, cap: float, label: str) -> tuple[dict[str, Any], float]:
    body = json.loads(body_json)
    effort = body.pop("reasoning")["effort"]
    max_output = body.pop("max_output_tokens")
    model = body.pop("model")
    result = call_meta("responses", body, stage=STAGE, public_data_only=True, max_output_tokens=max_output,
                       model=model, reasoning_effort=effort, scope=STAGE, scope_cap_usd=cap, run_id=RUN_ID,
                       cache=False)
    print(f"  {label}: ${result.cost_usd:.4f}", file=sys.stderr)
    return picks(result.text), result.cost_usd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("diff", type=Path)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "runs" / "match-replay" / "results.json")
    parser.add_argument("--cap", type=float, default=2.0)
    parser.add_argument("--limit", type=int, default=None, help="send at most this many requests this run")
    args = parser.parse_args(argv)
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    for d in json.loads(args.diff.read_text())["diffs"]:
        key = (d["slug"], d["lang"])
        if key not in chosen or "category" in d["args"]:
            chosen[key] = d
    rows = json.loads(args.out.read_text())["rows"] if args.out.exists() else []
    done = {(r["slug"], r["lang"]) for r in rows}
    spent = 0.0
    # Largest changes first, so a cap or --limit leaves out the requests whose shortlist moved least.
    todo = sorted(((key, d) for key, d in chosen.items() if key not in done), key=lambda kd: -len(kd[1]["out"]))[: args.limit]
    for (slug, lang), d in todo:
        print(f"{slug} {lang}", file=sys.stderr)
        try:
            old1, c1 = send(d["old"], args.cap, "old")
            old2, c2 = send(d["old"], args.cap, "old again")
            new, c3 = send(d["new"], args.cap, "new")
        except Exception as err:  # the scope cap or the budget: keep what is done
            print(f"stopped: {err}", file=sys.stderr)
            break
        spent += c1 + c2 + c3
        rows.append({"slug": slug, "lang": lang, "args": d["args"], "out": d["out"], "in": d["in"],
                     "old": old1, "old_again": old2, "new": new, "cost_usd": c1 + c2 + c3})
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(rows)} of {len(chosen)} requests replayed -> {args.out} (${spent:.4f} this run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
