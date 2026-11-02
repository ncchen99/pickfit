"""q11 L2-3 blind judge (eval/fixtures/q11/judge_rubric.md), pinned 2026-11-02 as late calibration before any q11
run: claude-opus-5-5 at effort high, the C4 grader's settings (Opus 5.5 takes no temperature, so the model id and
effort are what is fixed). Reads score_replies.py --write-judge-requests output; writes judge-raw.jsonl and one
judge.json per reply set ({"P1": true, ...}); a reply that is not valid JSON is sent once more (rubric).
Spend goes to the grading cap (grade.py's ledger).

  uv run --with anthropic==2.3.0 python eval/runner/q11_judge.py REQUESTS.jsonl --out DIR
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade  # noqa: E402

MODEL, EFFORT = "claude-opus-5-5", "high"
SCHEMA = {"type": "object", "properties": {"answers_prompt": {"type": "boolean"}, "reason": {"type": "string"}},
          "required": ["answers_prompt", "reason"], "additionalProperties": False}


def call(system: str, user: str) -> dict:
    import anthropic

    sys.path.insert(0, str(grade.ROOT))
    from pickfit.env import read_env

    client = anthropic.Anthropic(api_key=read_env(["ANTHROPIC_API_KEY"])["ANTHROPIC_API_KEY"])
    r = client.messages.create(model=MODEL, max_tokens=4000, system=system, messages=[{"role": "user", "content": user}],
                               output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}})
    u = r.usage
    usage = {"input_tokens": u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
             "cached_input_tokens": u.cache_read_input_tokens or 0, "output_tokens": u.output_tokens}
    return {"model": r.model, "text": next((b.text for b in r.content if b.type == "text"), ""),
            "request_id": r._request_id, "usage": usage, "cost_usd": round(grade.cost(MODEL, usage), 6)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("requests", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--use", default="q11_judge")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    verdicts: dict[str, dict[str, bool | None]] = {}
    with (a.out / "judge-raw.jsonl").open("a", encoding="utf-8") as raw:
        for line in a.requests.read_text(encoding="utf-8").splitlines():
            req = json.loads(line)
            run, p = req["id"].split(":")
            value = None
            for attempt in (1, 2):
                res = call(req["system"], req["messages"][0]["content"])
                grade.record({"use": a.use, "item": req["id"], "attempt": attempt, "at": grade.now(), "model": res["model"],
                              "request_id": res["request_id"], "usage": res["usage"], "cost_usd": res["cost_usd"]}, "grading")
                raw.write(json.dumps({"id": req["id"], "attempt": attempt, **res}, ensure_ascii=False) + "\n")
                try:
                    value = bool(json.loads(res["text"])["answers_prompt"])
                    break
                except (ValueError, KeyError, TypeError):
                    continue
            verdicts.setdefault(run, {})[p] = value
    for run, v in verdicts.items():
        (a.out / f"judge-{run}.json").write_text(json.dumps(v) + "\n", encoding="utf-8")
    print("judged", sum(len(v) for v in verdicts.values()), "replies in", len(verdicts), "sets ->", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
