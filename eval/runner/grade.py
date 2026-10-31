"""Model graders for the blind L1 batch (eval/README.md 9.1 C4 and 9.2 B).

The same fixed instructions (eval/prompts/grader_l1.md, between the RUBRIC markers) and
the same blind items go to two graders, each on its own budget:

  claude  the fixed-version Claude grader of 9.1 C4 (config: grader_model, grader_effort).
          Claude Opus 5.5 takes no temperature; the model id and effort are what is fixed.
          Spend counts toward caps_usd.grading ($20, shared with E and section 5 judgements).
  muse    the Muse Spark third grader of 9.2 B: meta-models/muse-spark-open-1026 on Baseten,
          temperature 0. Spend counts toward caps_usd.baseten_grading ($5).

Both only describe: 念誠's verdicts count; `agree` lists agreement and every disagreement.
No grader sees a group, a round or pickfit's name (the batch comes from blind.py).

  grade.py run   --batch BATCH.jsonl --grader claude|muse --out GRADES.jsonl [--limit N]
  grade.py agree --batch BATCH.jsonl --human HUMAN.csv --grades claude=G1.jsonl muse=G2.jsonl --out AGREE.json
  grade.py smoke --grader claude|muse --dir DIR   one tiny real call (own ledger in DIR): key, model, cost

Run with: uv run --with pyyaml==6.0.2 --with anthropic==2.3.0 python eval/runner/grade.py ...
(the Muse grader uses the openai package pickfit already depends on).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "eval"
CONFIG_PATH = EVAL / "runner" / "config.json"
RUBRIC_PATH = EVAL / "prompts" / "grader_l1.md"
LEDGER = EVAL / "results" / "grading-spend.json"
TAIPEI = dt.timezone(dt.timedelta(hours=8))
VERDICTS = ("pass", "fail", "unknown", "needs_l2")

# USD per million tokens (input, output, cached input). Anthropic first-party rates (claude-api skill,
# 2026-10-06 table); Baseten rate as pickfit/meta.py records it for the same model.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "meta-models/muse-spark-open-1026": (1.25, 4.25, 0.15),
}
MAX_OUTPUT_TOKENS = 8000
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {"type": "array", "items": {
            "type": "object",
            "properties": {"check": {"type": "string"}, "verdict": {"type": "string", "enum": list(VERDICTS)},
                           "reason": {"type": "string"}},
            "required": ["check", "verdict", "reason"], "additionalProperties": False}},
        "overall": {"type": "string", "enum": list(VERDICTS)},
    },
    "required": ["checks", "overall"],
    "additionalProperties": False,
}


def now() -> str:
    return dt.datetime.now(TAIPEI).isoformat(timespec="seconds")


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def rubric(path: Path = RUBRIC_PATH) -> str:
    text = path.read_text(encoding="utf-8")
    return text.split("<!-- RUBRIC START -->", 1)[1].split("<!-- RUBRIC END -->", 1)[0].strip()


def item_prompt(item: dict[str, Any]) -> str:
    """The user message: the question, its [L1] checks, the pick and any evidence. Nothing that names a group."""
    q = item["question"]
    lines = [f"Question {q['id']} ({q.get('kind', 'find_software')}):", q["prompt"].strip(), "",
             "Hard conditions:", json.dumps(q.get("constraints") or {}, ensure_ascii=False, indent=1), "",
             "Checks to grade:"]
    lines += [f"- {c}" for c in q["l1_checks"]]
    pick = item["pick"]
    lines += ["", f"Recommended: {pick['tool']}", f"Install method given: {pick.get('install') or '(none given)'}"]
    if pick.get("kind") in ("keep_current", "custom_script"):
        lines.append(f"Pick type: {pick['kind'].replace('_', ' ')}")
    for ev in item.get("evidence") or []:
        lines += ["", f"Evidence from {ev['source']} (fetched {ev.get('fetched_at', '?')}):", ev["text"].strip()]
    return "\n".join(lines)


def parse_json_reply(text: str) -> dict[str, Any] | None:
    """The JSON object in a reply; Baseten does not enforce the schema, so look for the outermost object."""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except ValueError:
        return None


def cost(model: str, usage: dict[str, int]) -> float:
    rate_in, rate_out, rate_cached = PRICES[model]
    cached = usage.get("cached_input_tokens", 0)
    return ((usage.get("input_tokens", 0) - cached) * rate_in + cached * rate_cached
            + usage.get("output_tokens", 0) * rate_out) / 1_000_000


def estimate(model: str, system: str, user: str) -> float:
    """Worst case for one call: about 3 characters a token in, the full output limit out."""
    rate_in, rate_out, _ = PRICES[model]
    return ((len(system) + len(user)) / 3 * rate_in + MAX_OUTPUT_TOKENS * rate_out) / 1_000_000


# --- the two graders ---------------------------------------------------------------------


def call_claude(config: dict[str, Any], system: str, user: str) -> dict[str, Any]:
    import anthropic  # uv run --with anthropic==2.3.0

    sys.path.insert(0, str(ROOT))
    from pickfit.env import read_env

    client = anthropic.Anthropic(api_key=read_env(["ANTHROPIC_API_KEY"])["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=config["grader_model"], max_tokens=MAX_OUTPUT_TOKENS, system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": config["grader_effort"], "format": {"type": "json_schema", "schema": RESULT_SCHEMA}},
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    u = response.usage
    return {"model": response.model, "text": text, "stop_reason": response.stop_reason, "request_id": response._request_id,
            "usage": {"input_tokens": u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
                      "cached_input_tokens": u.cache_read_input_tokens or 0, "output_tokens": u.output_tokens}}


def call_muse(config: dict[str, Any], system: str, user: str) -> dict[str, Any]:
    import openai  # pickfit's own dependency

    sys.path.insert(0, str(ROOT))
    from pickfit.env import read_env

    client = openai.OpenAI(base_url=config["muse_base_url"], api_key=read_env(["BASETEN_API_KEY"])["BASETEN_API_KEY"])
    response = client.chat.completions.create(
        model=config["muse_model"], temperature=0, max_tokens=MAX_OUTPUT_TOKENS,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    u = response.usage
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    return {"model": response.model, "text": response.choices[0].message.content or "",
            "stop_reason": response.choices[0].finish_reason, "request_id": response.id,
            "usage": {"input_tokens": u.prompt_tokens, "cached_input_tokens": cached, "output_tokens": u.completion_tokens}}


GRADERS: dict[str, tuple[str, str, Callable[..., dict[str, Any]]]] = {
    # grader: (config key of the model, cap key, call)
    "claude": ("grader_model", "grading", call_claude),
    "muse": ("muse_model", "baseten_grading", call_muse),
}


# --- spend ledger --------------------------------------------------------------------------


def read_ledger(path: Path = LEDGER) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"spent_usd": {}, "calls": []}


def record(entry: dict[str, Any], cap_key: str, path: Path = LEDGER) -> None:
    ledger = read_ledger(path)
    ledger["spent_usd"][cap_key] = round(ledger["spent_usd"].get(cap_key, 0.0) + entry["cost_usd"], 6)
    ledger["calls"].append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class OverCap(Exception):
    pass


def grade_items(items: list[dict[str, Any]], grader: str, config: dict[str, Any], out: Path,
                ledger: Path = LEDGER, call: Callable[..., dict[str, Any]] | None = None,
                log: Callable[[str], None] = print) -> int:
    """Grade every item not yet in OUT (resumable). Stops before a call that could pass the cap."""
    model_key, cap_key, default_call = GRADERS[grader]
    call = call or default_call
    model = config[model_key]
    cap = float(config["caps_usd"][cap_key])
    system = rubric()
    rubric_sha = hashlib.sha256(system.encode("utf-8")).hexdigest()
    done = {json.loads(line)["item_id"] for line in out.read_text(encoding="utf-8").splitlines()} if out.exists() else set()
    graded = 0
    for item in items:
        if item["item_id"] in done:
            continue
        user = item_prompt(item)
        spent = read_ledger(ledger)["spent_usd"].get(cap_key, 0.0)
        if spent + estimate(model, system, user) > cap:
            raise OverCap(f"{grader}: ${spent:.2f} spent, the next call could pass the ${cap} cap ({cap_key})")
        reply = call(config, system, user)
        result = parse_json_reply(reply["text"])
        valid = isinstance(result, dict) and result.get("overall") in VERDICTS
        usd = round(cost(model, reply["usage"]), 6)
        row = {"item_id": item["item_id"], "grader": grader, "model": reply["model"], "at": now(),
               "rubric_sha256": rubric_sha, "overall": result.get("overall") if valid else None,
               "checks": result.get("checks") if valid else None, "parse_error": None if valid else reply["text"][:500],
               "stop_reason": reply["stop_reason"], "request_id": reply["request_id"], "usage": reply["usage"],
               "cost_usd": usd}
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        record({"at": row["at"], "grader": grader, "model": reply["model"], "item_id": item["item_id"],
                "cost_usd": usd, "usage": reply["usage"]}, cap_key, ledger)
        graded += 1
        log(f"{grader} {item['item_id']}: {row['overall']} ${usd:.4f}")
    return graded


# --- agreement -----------------------------------------------------------------------------


def read_human(path: Path) -> dict[str, str]:
    """念誠's verdicts: the l1-form CSV from blind.py (item_id, ..., overall)."""
    with path.open(encoding="utf-8") as fh:
        return {row["item_id"]: row["overall"].strip() for row in csv.DictReader(fh) if row.get("overall", "").strip()}


def read_grades(path: Path) -> dict[str, str | None]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {r["item_id"]: r["overall"] for r in rows}


def agreement(human: dict[str, str], graders: dict[str, dict[str, str | None]]) -> dict[str, Any]:
    """Pairwise agreement on the overall verdict, over items every party graded; every disagreement listed."""
    parties = {"念誠": human, **graders}
    names = list(parties)
    common = sorted(set.intersection(*(set(v) for v in parties.values()))) if parties else []
    pairs = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            same = sum(1 for k in common if parties[a][k] == parties[b][k])
            pairs[f"{a}~{b}"] = {"agree": same, "of": len(common), "rate": round(same / len(common), 3) if common else None}
    disagreements = [{"item_id": k, **{n: parties[n][k] for n in names}} for k in common
                     if len({parties[n][k] for n in names}) > 1]
    missing = {n: sorted(set(human) - set(parties[n])) for n in graders}
    return {"items_all_graded": len(common), "pairs": pairs, "disagreements": disagreements,
            "not_graded_by": missing, "note": "descriptive only (9.2 B.2): 念誠's verdicts count"}


# --- commands ------------------------------------------------------------------------------


def read_batch(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


SMOKE_ITEM = {
    "item_id": "SMOKE", "question": {"id": "smoke", "kind": "find_software",
                                     "prompt": "I need a free command-line tool on Linux that prints the lines of a file in reverse order.",
                                     "constraints": {"os": "linux", "budget": "free"},
                                     "l1_checks": ["[L1] The tool exists and is free; it reverses the line order of a file"]},
    "pick": {"tool": "tac (GNU coreutils)", "install": "preinstalled on Ubuntu (coreutils)"},
    "evidence": [{"source": "coreutils manual", "text": "tac: concatenate and print files in reverse (last line first)."}],
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/runner/grade.py")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--batch", required=True, type=Path)
    r.add_argument("--grader", required=True, choices=list(GRADERS))
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--limit", type=int)
    a = sub.add_parser("agree")
    a.add_argument("--batch", required=True, type=Path)
    a.add_argument("--human", required=True, type=Path)
    a.add_argument("--grades", nargs="+", required=True, help="name=GRADES.jsonl")
    a.add_argument("--out", required=True, type=Path)
    s = sub.add_parser("smoke")
    s.add_argument("--grader", required=True, choices=list(GRADERS))
    s.add_argument("--dir", type=Path, required=True, help="where the reply and its own spend ledger go (not eval/results)")
    args = parser.parse_args(argv)
    config = load_config()
    if args.command == "agree":
        graders = {spec.split("=", 1)[0]: read_grades(Path(spec.split("=", 1)[1])) for spec in args.grades}
        report = agreement(read_human(args.human), graders)
        report["batch_sha256"] = hashlib.sha256(args.batch.read_bytes()).hexdigest()
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report["pairs"], ensure_ascii=False))
        return 0
    if args.command == "smoke":
        args.dir.mkdir(parents=True, exist_ok=True)
        out, ledger = args.dir / f"smoke-{args.grader}.jsonl", args.dir / "smoke-spend.json"
        out.unlink(missing_ok=True)
        grade_items([SMOKE_ITEM], args.grader, config, out, ledger)
        print(out.read_text(encoding="utf-8"))
        return 0
    try:
        grade_items(read_batch(args.batch)[: args.limit], args.grader, config, args.out)
    except OverCap as err:
        print(f"stopped: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
