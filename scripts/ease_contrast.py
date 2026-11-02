"""Exploratory 2x2 comparison for the usability pilot (docs/usability-pilot.md section 7): which judge and which prompt
match 念誠's blind ratings. Research only: it never writes records, and the product's judge stays a Meta model.

Cells, each over the same 12 apps, the same evidence and two samples:

- muse-p1: muse-spark-1.3 with the product's prompt (ease.v1.r1); the results of the r1 rerun, copied.
- opus-p1: claude-opus-5-5 with the same prompt.
- muse-p2 / opus-p2: prompt P2, which judges visual design too (current or dated, finish, spacing and alignment,
  broken images, visual hierarchy). Evidence, causes and null-when-unsure are unchanged.

Opus gets the same images, text and strict JSON schema through the Messages API (the schema in the system prompt,
since structured outputs cannot compile it; the answer is validated against the same pydantic model, one retry if it
does not parse), at a fixed effort (OPUS_EFFORT) and no sampling parameters; no refusal fallback, so every answer is
claude-opus-5-5's. Each call
is reserved and settled in the shared ledger under budget "anthropic-research" (ANTHROPIC_CAP_USD); Meta calls run
under their own scope cap (META_CAP_USD). Results go to ~/.pickfit/usability/contrast/<cell>/<slug>.json.

    uv run --with anthropic python scripts/ease_contrast.py run opus-p1 --slug orrery   # one app first
    uv run --with anthropic python scripts/ease_contrast.py run opus-p1
    uv run python scripts/ease_contrast.py run wonder-p1 --slug concessio                 # Muse Wonder (section 8)
    uv run python scripts/ease_contrast.py table
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pickfit.env import read_env
from pickfit.ledger import BudgetExceeded, Caps, Ledger
from pickfit.usability import (
    FIRST_LOOK_INSTRUCTIONS,
    IN_USE_INSTRUCTIONS,
    P1,
    RESULTS_DIR,
    Asked,
    Check,
    FirstLookAnswer,
    InUseAnswer,
    TextFinder,
    Variant,
    bundle_for,
    judge,
    meta_ask,
    pilot_slugs,
)
from scripts.ease_compare import compare

REPO = Path(__file__).resolve().parents[1]
CONTRAST_DIR = RESULTS_DIR / "contrast"
# cell: (judge, prompt, effort). muse-p0 is round 1 (ease.v1, holistic scores), kept only to score it again.
CELLS: dict[str, tuple[str, str, str]] = {
    "muse-p1": ("muse", "p1", "low"), "opus-p1": ("opus", "p1", "low"),
    "muse-p2": ("muse", "p2", "low"), "opus-p2": ("opus", "p2", "low"),
    "wonder-p1": ("wonder", "p1", "low"), "wonder-p2": ("wonder", "p2", "low"),
    "wonder-p1-high": ("wonder", "p1", "high"),
}
EARLIER = {"muse-p0": RESULTS_DIR / "ease.v1"}  # round 1, before r1
WONDER = "muse-wonder-1.0"
WONDER_CAP_USD = 10.0  # all Wonder cells together (section 8)
WONDER_RUN_ID = "usability-wonder-2026-11-03"
WONDER_MAX_TOKENS = 16_000
OPUS = "claude-opus-5-5"
OPUS_EFFORT = "low"  # muse-spark-1.3 runs at reasoning effort low too
OPUS_MAX_TOKENS = 16_000
OPUS_PRICE = {"input": 4.0, "output": 20.0, "cache_write": 5.0, "cache_read": 0.20}  # USD per 1M tokens
IMAGE_TOKENS = 1_600  # a 1280x800 screenshot is about 1,365 tokens; reserve a little more
ANTHROPIC_CAP_USD = 15.0
META_CAP_USD = 2.0
RUN_ID = "usability-contrast-2026-11-03"


class ComfortChecksP2(BaseModel):
    text_readable: Check = Field(description="Text a user needs is easy to read: not tiny, not low contrast.")
    layout_intact: Check = Field(description="No broken or missing images or icons; nothing overlaps or is cut off.")
    spacing_aligned: Check = Field(description="Even spacing and margins, elements aligned; nothing cramped.")
    hierarchy_clear: Check = Field(description="A clear visual hierarchy: the main area and main actions stand out, "
                                               "related controls grouped.")
    looks_current: Check = Field(description="Looks current and finished, not dated, rough or unpolished.")
    nothing_covering: Check = Field(description="No dialog, banner or overlay of the app's covers the work.")


class FirstLookAnswerP2(FirstLookAnswer):
    comfort: ComfortChecksP2  # type: ignore[assignment]


P1_COMFORT = ("- comfort (comfortable to look at): answer the five checks for the app's own screens, and give "
              "comfort_seen, text from the screen you checked. Do not judge colours, style or branding.")
P2_COMFORT = ("- comfort (comfortable to look at): answer the six checks for the app's own screens, and give "
              "comfort_seen, text from the screen you checked. Judge the visual design too: whether the screens look "
              "current and finished or dated and rough, spacing and alignment, broken images or icons, and whether "
              "the visual hierarchy makes clear where to look.")
assert P1_COMFORT in FIRST_LOOK_INSTRUCTIONS
P2 = Variant(f"{P1.name}-p2", FIRST_LOOK_INSTRUCTIONS.replace(P1_COMFORT, P2_COMFORT), FirstLookAnswerP2,
             IN_USE_INSTRUCTIONS, InUseAnswer)
VARIANTS = {"p1": P1, "p2": P2}


def anthropic_ledger() -> Ledger:
    from pickfit.env import get_env

    return Ledger(get_env("PICKFIT_LEDGER"), budget="anthropic-research",
                  caps=Caps(total_usd=ANTHROPIC_CAP_USD, daily_usd=lambda day: ANTHROPIC_CAP_USD))


def _nullable(node: dict[str, Any]) -> dict[str, Any] | None:
    """The non-null form of a nullable schema node (`type: [X, "null"]` or `anyOf: [X, null]`, as Meta's strict mode
    writes them), else None."""
    branches = node.get("anyOf")
    if isinstance(branches, list) and {"type": "null"} in branches and len(branches) == 2:
        other = next(b for b in branches if b != {"type": "null"})
        return {**{k: v for k, v in node.items() if k != "anyOf"}, **other}
    kinds = node.get("type")
    if not (isinstance(kinds, list) and "null" in kinds):
        return None
    others = [k for k in kinds if k != "null"]
    inner = {**node, "type": others[0] if len(others) == 1 else others}
    if "enum" in inner:
        inner["enum"] = [v for v in inner["enum"] if v is not None]
    return inner


def fill_nulls(data: Any, schema: dict[str, Any]) -> Any:
    """Put back, as null, every property the strict schema lists that an answer left out; a box written as the rules
    show it, [x_min, y_min, x_max, y_max], becomes the schema's object."""
    props = schema.get("properties") or {}
    if isinstance(data, list) and list(props) == ["x_min", "y_min", "x_max", "y_max"] and len(data) == 4:
        data = dict(zip(props, data))
    if isinstance(data, dict) and "properties" in schema:
        out = {}
        for name, prop in schema["properties"].items():
            inner = _nullable(prop) or prop
            out[name] = fill_nulls(data[name], inner) if name in data and data[name] is not None else None
        return out
    if isinstance(data, list) and "items" in schema:
        return [fill_nulls(item, schema["items"]) for item in data]
    return data


JSON_RULE = ("\n\nAnswer with one JSON object and nothing else: no prose, no code fence. It must match this JSON "
             "schema exactly, with every property present (null where the schema allows it):\n")


def opus_messages(body: dict[str, Any]) -> dict[str, Any]:
    """The Meta Responses body (instructions, text and data-URL images, strict schema) as a Messages API request.

    Anthropic's structured outputs cannot compile this schema (more than 16 nullable parameters, then "compiled grammar
    is too large"), so the same strict schema goes into the system prompt and the answer is validated against the same
    pydantic model afterwards."""
    blocks: list[dict[str, Any]] = []
    for part in body["input"][0]["content"]:
        if part["type"] == "input_text":
            blocks.append({"type": "text", "text": part["text"]})
        else:
            media, data = part["image_url"].removeprefix("data:").split(";base64,", 1)
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": data}})
    schema = json.dumps(body["text"]["format"]["schema"], separators=(",", ":"))
    return {"model": OPUS, "max_tokens": OPUS_MAX_TOKENS, "system": body["instructions"] + JSON_RULE + schema,
            "messages": [{"role": "user", "content": blocks}], "output_config": {"effort": OPUS_EFFORT}}


def parse_json(text: str) -> Any:
    """The answer's JSON object; tolerates a code fence or a line around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the answer")
    return json.loads(text[start:end + 1])


def opus_cost(usage: Any) -> float:
    return (usage.input_tokens * OPUS_PRICE["input"] + usage.output_tokens * OPUS_PRICE["output"]
            + (usage.cache_creation_input_tokens or 0) * OPUS_PRICE["cache_write"]
            + (usage.cache_read_input_tokens or 0) * OPUS_PRICE["cache_read"]) / 1e6


def opus_ask(ledger: Ledger, client: Any = None):
    import anthropic

    if client is None:
        key = read_env(["ANTHROPIC_API_KEY"]).get("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=key, max_retries=4)

    def ask(body: dict[str, Any], out: type[BaseModel], kind: str) -> Asked:
        first = once(body, out, kind)
        if first.parsed is not None or not (first.error or "").startswith("unparsable"):
            return first
        again = once(body, out, kind)  # one retry for an answer that did not parse; both costs count
        again.cost_usd += first.cost_usd
        return again

    def once(body: dict[str, Any], out: type[BaseModel], kind: str) -> Asked:
        request = opus_messages(body)
        images = sum(b["type"] == "image" for b in request["messages"][0]["content"])
        chars = len(request["system"]) + sum(len(b.get("text", "")) for b in request["messages"][0]["content"])
        estimate = ((chars / 3 + images * IMAGE_TOKENS) * OPUS_PRICE["input"] + OPUS_MAX_TOKENS * OPUS_PRICE["output"]) / 1e6
        row = ledger.reserve(estimate, run_id=RUN_ID, stage="usability-contrast", scope=f"contrast:{kind}",
                             provider="anthropic", model=OPUS)
        try:
            with client.messages.stream(**request) as stream:
                message = stream.get_final_message()
        except anthropic.BadRequestError as err:
            ledger.release(row)
            return Asked(None, 0.0, OPUS, error=f"BadRequestError: {str(err)[:300]}")
        except anthropic.APIError as err:
            ledger.settle(row, estimate, status="error")  # may have been billed: keep the reservation
            return Asked(None, estimate, OPUS, error=f"{type(err).__name__}: {str(err)[:300]}")
        u = message.usage
        cost = opus_cost(u)
        usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                 "cache_read_input_tokens": u.cache_read_input_tokens or 0,
                 "cache_creation_input_tokens": u.cache_creation_input_tokens or 0}
        ledger.settle(row, cost, tokens={"input_tokens": u.input_tokens, "cached_tokens": usage["cache_read_input_tokens"],
                                         "output_tokens": u.output_tokens}, response_id=message.id)
        if message.stop_reason in ("refusal", "max_tokens"):
            return Asked(None, cost, OPUS, usage, error=f"stop_reason {message.stop_reason}")
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            data = fill_nulls(parse_json(text), body["text"]["format"]["schema"])
            return Asked(out.model_validate(data), cost, OPUS, usage)
        except ValueError as err:
            return Asked(None, cost, OPUS, usage, error=f"unparsable answer: {str(err)[:200]}")

    return ask


def run_cell(cell: str, slugs: list[str], log=lambda line: print(line, file=sys.stderr)) -> dict[str, Any]:
    out_dir = CONTRAST_DIR / cell
    out_dir.mkdir(parents=True, exist_ok=True)
    if cell == "muse-p1":
        for slug in slugs:  # the r1 rerun, already made with this judge and prompt
            src = RESULTS_DIR / f"{slug}.json"
            if json.loads(src.read_text(encoding="utf-8"))["prompt_version"] != P1.name:
                raise SystemExit(f"{src} is not an {P1.name} result")
            shutil.copy2(src, out_dir / src.name)
        return {"cell": cell, "copied": len(slugs)}
    judge_name, prompt, effort = CELLS[cell]
    variant = VARIANTS[prompt]
    if judge_name == "opus":
        ask = opus_ask(anthropic_ledger())
    elif judge_name == "wonder":
        ask = meta_ask(WONDER, WONDER_CAP_USD, WONDER_RUN_ID, effort=effort, max_output_tokens=WONDER_MAX_TOKENS)
    else:
        ask = meta_ask("prod", META_CAP_USD, f"{RUN_ID}-{prompt}")
    finder = TextFinder()
    summary: dict[str, Any] = {"cell": cell, "cost_usd": 0.0, "done": [], "errors": {}}
    for slug in slugs:
        record = json.loads((REPO / "data" / "software" / f"{slug}.json").read_text(encoding="utf-8"))
        bundle = bundle_for(record)
        if bundle is None:
            summary["errors"][slug] = "no run with copied evidence"
            continue
        try:
            result = judge(bundle, ask, finder, variant=variant, log=log)
        except BudgetExceeded as err:
            summary["errors"][slug] = str(err)
            break
        (out_dir / f"{slug}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        summary["cost_usd"] = round(summary["cost_usd"] + result["cost_usd"], 6)
        summary["done"].append({"slug": slug, "cost_usd": result["cost_usd"], "errors": result["errors"]})
    return summary


def cell_dir(cell: str) -> Path:
    return EARLIER.get(cell, CONTRAST_DIR / cell)


def cell_numbers(cell: str) -> dict[str, Any]:
    d = compare(results_dir=cell_dir(cell))
    no = d["no_opposites"]
    c = d["criteria"]
    dims = c["1_dimensions"]
    return {
        "cell": cell, "passed": d["passed"],
        "dimensions": {k: f"{v['within_one']}/{v['comparable']}" for k, v in dims.items()},
        "dimensions_passed": all(v["passed"] for v in dims.values()),
        "comfortable_share": dims["comfortable"]["share"],
        "spearman": c["2_spearman"]["rho"], "spearman_n": c["2_spearman"]["n"],
        "probes": c["3_probes"]["scores"], "verdicts_two_apart": c["4_verdicts"]["two_apart"],
        "self_agreement": d["side"]["self_agreement"], "cost_usd": d["side"]["cost_usd"],
        "no_opposites": {"passed": no["passed"],
                         **{k: {"compared": v["compared"], "opposite": v["opposite"]}
                            for k, v in no.items() if isinstance(v, dict)}},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("cell", choices=list(CELLS))
    r.add_argument("--slug", action="append")
    sub.add_parser("table")
    args = parser.parse_args()
    if args.command == "run":
        print(json.dumps(run_cell(args.cell, args.slug or pilot_slugs(REPO)), ensure_ascii=False, indent=2))
    else:
        cells = [*EARLIER, *CELLS]
        print(json.dumps([cell_numbers(c) for c in cells if cell_dir(c).is_dir()], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
