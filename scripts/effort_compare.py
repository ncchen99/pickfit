"""Ask the verification agent's saved decision points again at two reasoning efforts, and compare its next action.

The agent runs at REASONING_EFFORT "medium" (pickfit/verify/agent.py). About 55% of its output tokens are
thinking, so "low" would cost less; whether it still picks the same next step is what this measures, offline:
no box, only model calls (docs/proposals/tokens.md, T4). Nothing in the pipeline changes.

A decision point is the agent's input just before one of its answers. Each Claude run in replay mode saves its
conversation as sent (runs/verify/<run_id>/history.json, from 11/19 on), and turn n's input is that history up
to its n-th answer, thinking blocks and all, so the point is asked exactly as the agent saw it. Runs from before
11/19 have only report.json, which keeps neither the task prompt (with its README excerpt) nor what read_file
returned nor the thinking: they are skipped rather than rebuilt from a guess.

For each point and each effort the model answers once (call_meta, stage "effort-compare", the ledger's pipeline
budget). Its first tool call is compared: the same tool, and the same action (the same command, path, level or
goal). The output lists the agreement between the two efforts and with what the run did, every disagreement,
and the cost and output tokens of each effort.

    uv run python scripts/effort_compare.py --dry-run                 # count points, estimate the cost
    uv run python scripts/effort_compare.py --points 20 --max-usd 3   # paid: about US$1-2 for 20 points

Points are taken a whole run at a time, and calls of one effort go in run order with the prompt cache marked
(call_meta conversation=True), so a run's next point reads the earlier one's prefix from the cache, as the
agent's own turns did; the two efforts do not share it (a change of effort starts the messages cache again).
The estimate: a run of about 8 turns ending near 25K input tokens costs about US$0.2 per effort this way.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pickfit.env import REPO_ROOT
from pickfit.ledger import BudgetExceeded, taipei_now
from pickfit.meta import PRICES, PROD_MODEL, MetaResult, call_meta, provider_for

STAGE = "effort-compare"
EFFORTS = ("medium", "low")
MAX_OUTPUT_TOKENS = 8_000  # as the agent's turns (agent.MAX_OUTPUT_TOKENS)
DEFAULT_POINTS = 20
DEFAULT_MAX_USD = 3.0
CHARS_PER_TOKEN = 4  # for the dry run's estimate only
OUTPUT_TOKENS_GUESS = 450  # median agent turn on Opus (11/17-11/18 traces): for the estimate only
# What makes two calls of a tool the same action: the arguments that say what it does, not why or how long.
KEY_ARGS = {"run_command": ("command",), "run_background": ("command",), "read_file": ("path",),
            "list_dir": ("path",), "launch_gui": ("command",), "operate_gui": ("goal",), "listen": ("command",),
            "finish": ("level",)}


@dataclass
class Point:
    run_id: str
    turn: int  # the answer this input led to, from 1
    model: str
    instructions: str
    tools: list[dict[str, Any]]
    input: list[dict[str, Any]]
    recorded: list[dict[str, Any]]  # the function calls the run made here

    @property
    def chars(self) -> int:
        return len(json.dumps({"i": self.instructions, "t": self.tools, "x": self.input}, ensure_ascii=False))


@dataclass
class Asked:
    effort: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    text: str | None = None
    cost_usd: float = 0.0
    output_tokens: int = 0
    error: str | None = None


def _is_answer(item: dict[str, Any]) -> bool:
    """An item the agent's model wrote (Responses output: reasoning, its message, a function call)."""
    if "anthropic_block" in item:
        return True
    kind = item.get("type") or "message"
    return kind in ("reasoning", "function_call") or (kind == "message" and item.get("role") == "assistant")


def points_of(run_id: str, history: dict[str, Any]) -> list[Point]:
    """Every decision point of one saved conversation: the input before each answer, and what the answer called."""
    items = history.get("input") or []
    found: list[Point] = []
    i, turn = 0, 0
    while i < len(items):
        if not _is_answer(items[i]):
            i += 1
            continue
        start = i
        while i < len(items) and _is_answer(items[i]):
            i += 1
        turn += 1
        calls = [{"name": item.get("name", ""), "arguments": item.get("arguments") or "{}"}
                 for item in items[start:i] if item.get("type") == "function_call"]
        found.append(Point(run_id, turn, history.get("model") or PROD_MODEL, history.get("instructions") or "",
                           history.get("tools") or [], items[:start], calls))
    return found


def load_points(runs_dirs: Iterable[Path], run_ids: list[str] | None = None) -> tuple[list[Point], list[str]]:
    """Decision points of every saved Claude conversation under runs_dirs/verify, and the runs skipped (why)."""
    points: list[Point] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for runs in runs_dirs:
        for report in sorted((runs / "verify").glob("verify-*/report.json")):
            run_id = report.parent.name
            if run_id in seen or (run_ids and run_id not in run_ids):
                continue
            seen.add(run_id)
            saved = report.parent / "history.json"
            if not saved.exists():
                skipped.append(f"{run_id}: no history.json (a run from before 11/19, or chain mode)")
                continue
            history = json.loads(saved.read_text(encoding="utf-8"))
            if provider_for(history.get("model") or "") != "anthropic":
                skipped.append(f"{run_id}: {history.get('model')} is not a Claude model")
                continue
            points += points_of(run_id, history)
    return points, skipped


def pick(points: list[Point], n: int, seed: int = 1119) -> list[Point]:
    """About n points, whole runs at a time (the same runs for the same seed), in run and turn order: a run's later
    points then read its earlier ones from the prompt cache, as the agent's own turns did, which costs a fraction
    of asking points from many runs."""
    by_run: dict[str, list[Point]] = {}
    for point in points:
        by_run.setdefault(point.run_id, []).append(point)
    runs = sorted(by_run)
    random.Random(seed).shuffle(runs)
    chosen: list[Point] = []
    for run in runs:
        if len(chosen) >= n:
            break
        chosen += sorted(by_run[run], key=lambda p: p.turn)[: n - len(chosen)]  # a run's first turns: one prefix
    return sorted(chosen, key=lambda p: (p.run_id, p.turn))


def action(call: dict[str, Any] | None) -> tuple[str, str] | None:
    """(tool, what it does) of a function call, or None for an answer that called nothing."""
    if call is None:
        return None
    try:
        args = json.loads(call.get("arguments") or "{}")
    except json.JSONDecodeError:
        args = {}
    keys = KEY_ARGS.get(call.get("name", ""), ())
    what = " | ".join(" ".join(str(args.get(k, "")).split()) for k in keys) if isinstance(args, dict) else ""
    return call.get("name", ""), what


def ask(point: Point, effort: str, *, run_id: str, max_usd: float, **call_kwargs: Any) -> Asked:
    body = {"instructions": point.instructions, "tools": point.tools, "input": point.input,
            "reasoning": {"summary": "auto"}, "store": False, "include": ["reasoning.encrypted_content"]}
    asked = Asked(effort)
    try:
        result: MetaResult = call_meta("responses", body, stage=STAGE, public_data_only=True,
                                       max_output_tokens=MAX_OUTPUT_TOKENS, model=point.model,
                                       reasoning_effort=effort, scope=f"{STAGE}:{run_id}", scope_cap_usd=max_usd,
                                       run_id=run_id, cache=False, conversation=True, **call_kwargs)
    except BudgetExceeded:
        raise
    except Exception as err:  # noqa: BLE001 - one point's failure is reported, the rest are asked
        asked.error = f"{type(err).__name__}: {str(err)[:300]}"
        return asked
    asked.calls = [{"name": c.name, "arguments": c.arguments} for c in result.tool_calls]
    asked.text = result.text
    asked.cost_usd = result.cost_usd
    asked.output_tokens = result.usage.output_tokens if result.usage else 0
    return asked


def compare(points: list[Point], answers: dict[str, list[Asked]], efforts: tuple[str, str]) -> dict[str, Any]:
    """Agreement between the two efforts' first calls, and of each with the run's own."""
    a, b = efforts
    rows = []
    for i, point in enumerate(points):
        first = {e: action(answers[e][i].calls[0] if answers[e][i].calls else None) for e in efforts}
        recorded = action(point.recorded[0] if point.recorded else None)
        rows.append({"run_id": point.run_id, "turn": point.turn, "recorded": recorded, **first,
                     "errors": {e: answers[e][i].error for e in efforts if answers[e][i].error}})
    usable = [r for r in rows if not r["errors"]]

    def rate(match: Any) -> float | None:
        return round(sum(1 for r in usable if match(r)) / len(usable), 3) if usable else None

    def tool(x: tuple[str, str] | None) -> str | None:
        return x[0] if x else None

    return {
        "points": len(rows), "answered": len(usable),
        "same_tool": rate(lambda r: tool(r[a]) == tool(r[b])),
        "same_action": rate(lambda r: r[a] == r[b]),
        f"{a}_as_recorded": rate(lambda r: r[a] == r["recorded"]),
        f"{b}_as_recorded": rate(lambda r: r[b] == r["recorded"]),
        "cost_usd": {e: round(sum(x.cost_usd for x in answers[e]), 4) for e in efforts},
        "output_tokens": {e: sum(x.output_tokens for x in answers[e]) for e in efforts},
        "disagreements": [r for r in usable if r[a] != r[b]],
        "errors": [r for r in rows if r["errors"]],
    }


def estimate_usd(points: list[Point], efforts: Iterable[str]) -> tuple[float, float]:
    """(no cache read at all, each run's later points reading the earlier prefix): a rough range for the run."""
    price = PRICES[("anthropic", PROD_MODEL)]
    n = len(list(efforts))
    full = sum(p.chars / CHARS_PER_TOKEN * price.input for p in points) / 1e6
    out = len(points) * OUTPUT_TOKENS_GUESS * price.output / 1e6
    by_run: dict[str, list[Point]] = {}
    for p in points:
        by_run.setdefault(p.run_id, []).append(p)
    cached = 0.0
    for run_points in by_run.values():
        before = 0.0
        for p in run_points:
            tokens = p.chars / CHARS_PER_TOKEN
            cached += (min(before, tokens) * price.cached + max(0.0, tokens - before) * (price.cache_write or 0)) / 1e6
            before = tokens
    return round(n * (full + out), 2), round(n * (cached + out), 2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-dir", type=Path, action="append",
                        help="a runs directory (repeatable; default runs/ here and in the main checkout)")
    parser.add_argument("--run", action="append", help="only this run id (repeatable)")
    parser.add_argument("--points", type=int, default=DEFAULT_POINTS, help="decision points to ask (sampled)")
    parser.add_argument("--efforts", default=",".join(EFFORTS), help="the two efforts, e.g. medium,low")
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD, help="stop spending past this")
    parser.add_argument("--seed", type=int, default=1119)
    parser.add_argument("--out", type=Path, help="write the comparison as JSON here")
    parser.add_argument("--dry-run", action="store_true", help="count points and estimate the cost; no call")
    args = parser.parse_args(argv)
    efforts = tuple(e.strip() for e in args.efforts.split(","))
    if len(efforts) != 2 or efforts[0] == efforts[1]:
        parser.error("--efforts takes two different efforts")
    main_checkout = Path(str(REPO_ROOT).split("/.claude/worktrees/")[0])
    runs_dirs = args.runs_dir or list(dict.fromkeys([REPO_ROOT / "runs", main_checkout / "runs"]))
    found, skipped = load_points(runs_dirs, args.run)
    chosen = pick(found, args.points, args.seed)
    uncached, cached = estimate_usd(chosen, efforts)
    print(f"effort_compare: {len(found)} decision points in saved conversations, {len(skipped)} runs skipped; "
          f"asking {len(chosen)} at {' and '.join(efforts)}: about ${cached:.2f} (up to ${uncached:.2f} with no "
          "cache hit)", file=sys.stderr)
    if args.dry_run or not chosen:
        return 0
    run_id = f"{STAGE}-{taipei_now():%Y%m%d-%H%M%S}"
    answers: dict[str, list[Asked]] = {}
    for effort in efforts:  # one effort at a time, in run order: each run's prefix stays in the cache
        answers[effort] = []
        for point in chosen:
            try:
                answers[effort].append(ask(point, effort, run_id=run_id, max_usd=args.max_usd))
            except BudgetExceeded as err:
                print(f"effort_compare: stopped, {err}", file=sys.stderr)
                return 1
    report = compare(chosen, answers, efforts)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
