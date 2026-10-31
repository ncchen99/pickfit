"""Build the shortlist check set: each verified record's summary rewritten as a user need.

Usage:
    uv run python scripts/shortlist_needs.py [--out runs/shortlist-check/needs.json] [--limit N]

Only data/software is read (never eval/). A Meta model writes, for every tool whose
install steps were run, the request a person would type before they know the tool:
one in English and one in Traditional Chinese. worker/bench/shortlist.ts then
checks whether the tool lands among the cards sent to the matcher. Public data
only, so the contributor model is used; the run costs a few cents.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from pickfit.env import REPO_ROOT
from pickfit.index import DEFAULT_DATA_DIR, build_index
from pickfit.meta import call_meta
from pickfit.schema import meta_strict_schema

STAGE = "shortlist-check"
MODEL = "muse-spark-1.3-contributor"
BATCH = 20
MAX_OUTPUT_TOKENS = 8_000
DEFAULT_OUT = REPO_ROOT / "runs" / "shortlist-check" / "needs.json"

INSTRUCTIONS = """You write test requests for a software recommender. For each tool in the input, write the request a person would type to an AI assistant when they need what the tool does, before they know the tool exists.

Rules:
- Describe the person's job or problem, not the tool. Never use the tool's name or words taken from its name.
- Do not copy phrases from the summary or use cases; say it the way a user would, in one or two plain sentences of at most 30 words.
- Do not mention an operating system unless the tool runs on only one.
- en: in English.
- zh: in Traditional Chinese as a Taiwanese developer would type it, phrased on its own (not a word-for-word translation of en). Keep product names and file formats in English when that is natural (Docker, PDF, JSON); write everything else in Chinese.
- Return one item per input tool with its slug unchanged."""


class Need(BaseModel):
    slug: str
    en: str
    zh: str


class Needs(BaseModel):
    items: list[Need]


def tool_text(entry: dict) -> dict:
    return {
        "slug": entry["slug"],
        "category": entry["category"],
        "summary": entry["summary"],
        "use_cases": entry["use_cases"][:3],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None, help="first N verified records only")
    args = parser.parse_args(argv)

    entries = [e for e in build_index(DEFAULT_DATA_DIR).index["entries"] if e["install"]]
    entries.sort(key=lambda e: e["slug"])
    if args.limit:
        entries = entries[: args.limit]
    done: dict[str, dict] = {}
    if args.out.exists():
        done = {item["slug"]: item for item in json.loads(args.out.read_text())["needs"]}
    todo = [e for e in entries if e["slug"] not in done]
    cost = 0.0
    schema = meta_strict_schema(Needs)
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        body = {
            "instructions": INSTRUCTIONS,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": json.dumps([tool_text(e) for e in batch])}]}],
            "text": {"format": {"type": "json_schema", "name": "needs", "schema": schema, "strict": True}},
            "store": False,
        }
        result = call_meta("responses", body, stage=STAGE, public_data_only=True, model=MODEL,
                           max_output_tokens=MAX_OUTPUT_TOKENS, reasoning_effort="low", output_model=Needs)
        cost += result.cost_usd
        wanted = {e["slug"]: e for e in batch}
        got = result.parsed.items if result.parsed else []
        for item in got:
            if item.slug in wanted:
                e = wanted[item.slug]
                done[item.slug] = {"slug": item.slug, "category": e["category"], "en": item.en, "zh": item.zh}
        print(f"batch {start // BATCH + 1}: {len(got)}/{len(batch)} needs, ${result.cost_usd:.4f}", file=sys.stderr)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        ordered = [done[s] for s in sorted(done)]
        args.out.write_text(json.dumps({"model": MODEL, "needs": ordered}, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(done)} needs -> {args.out} (${cost:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
