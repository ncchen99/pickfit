"""Send captured Worker request bodies (Responses API) to Meta and keep the raw responses.

Usage:
    uv run python scripts/send_bodies.py <bodies.json> <responses.json> --stage STAGE [--cap 1.0]

`bodies.json` is {"bodies": {id: body}} as the Worker builds them (worker/bench/keyword_bodies.ts
capture). Each body is sent once, as the Worker would (model, reasoning effort and output limit
from the body), through call_meta, so the spend lands in the shared pipeline ledger under STAGE,
capped by --cap. Ids already in responses.json are skipped, so a stopped run can be resumed.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pickfit.meta import call_meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bodies", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--cap", type=float, default=1.0)
    args = parser.parse_args(argv)
    bodies: dict[str, str] = json.loads(args.bodies.read_text())["bodies"]
    responses: dict[str, Any] = json.loads(args.out.read_text())["responses"] if args.out.exists() else {}
    todo = [i for i in bodies if i not in responses]

    def send(item: str) -> tuple[str, Any, float]:
        try:
            return _send(item)
        except Exception as err:  # the cap or the budget: keep what is done
            print(f"{item}: {err}", file=sys.stderr)
            return item, None, 0.0

    def _send(item: str) -> tuple[str, Any, float]:
        body = json.loads(bodies[item])
        effort = body.pop("reasoning")["effort"]
        max_output = body.pop("max_output_tokens")
        model = body.pop("model")
        result = call_meta("responses", body, stage=args.stage, public_data_only=True, max_output_tokens=max_output,
                           model=model, reasoning_effort=effort, scope=args.stage, scope_cap_usd=args.cap,
                           run_id=args.stage, cache=False)
        return item, result.raw, result.cost_usd

    spent = 0.0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for item, raw, cost in pool.map(send, todo):
            if raw is not None:
                responses[item] = raw
            spent += cost
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"responses": responses}, ensure_ascii=False) + "\n")
    print(f"{len(todo)} sent, {len(responses)} of {len(bodies)} answered -> {args.out} (${spent:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
