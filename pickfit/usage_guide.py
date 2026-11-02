"""Usage guides: the words a person reads on a tool page, written from the record and its run.

For each advertised feature a plain title, and for a feature a passed run checked, one to three steps
that say how to use it, taken from what the run did (the smoke test's command, or the goal pickfit
operated a GUI app or web app toward). A one-line hint says how to start the tool once installed.
The text adds words, never claims: to_guide keeps steps only for features the run checked, and the
record keeps the guide as a snapshot. Records change after it is written (a re-verification replaces
the run, an extraction changes the features), so the index shows it through shown_guide(): a title only
for a feature the record still lists, steps only while a passed run still checks that feature.

The product writes these with a Meta model (call_meta, default muse-spark-1.3). `--provider anthropic`
writes them with Claude instead; 念誠 chose that for the 11/2 backfill of records that already existed
(the tool page changed after the data was built). Every guide records the model that wrote it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pickfit.schema import SoftwareRecord, UsageGuide, VerificationRun, is_passed, meta_strict_schema

STAGE = "usage_guide"
ANTHROPIC_MODEL = "claude-opus-5-5"
# claude-opus-5-5 per million tokens (input, output); thinking is billed as output.
ANTHROPIC_PRICE = (4.00, 20.00)
EXCERPT_MAX = 400
MAX_OUTPUT_TOKENS = 4000

INSTRUCTIONS = """\
You write the short help text on a software catalog's tool page. A reader has just installed the tool \
and wants to know what it does and how to use each feature. They do not care how the catalog tested it.

You get the tool's profile, its advertised features, and what a test run did with each feature. Write:

- features: one entry per advertised feature, in the order given, with `feature` copied exactly.
  - title: the feature in plain words, sentence case, at most 60 characters. Say what the reader can do \
("Set how long and how often breaks are"). Keep the meaning; add nothing the feature text does not say.
  - steps: only for a feature marked CHECKED, 1 to 3 short imperative steps saying how to use it, \
based only on what the run did. Otherwise an empty list.
    - Command-line tools: put the command in backticks. Use only commands the run ran; do not add \
variants it did not run (such as the same command without a flag). Keep the tool's own subcommands and flags exactly \
as the run used them; replace files, paths and values the test made up (temporary paths, /Users/sbx, \
/tmp/..., /root/..., random words such as pickfit1bf935, sample numbers) with a placeholder such as <file> \
or <your text>.
    - GUI and web apps: say where to click or type (window, tab, section, field) as the run's goal and \
result describe it. Use the app's own labels when given.
    - Never mention the test, the catalog, a sandbox, a virtual machine, a model, check files, waiting \
for an autosave, or test values.
- open_hint: one sentence on how to start the tool once installed, or null when nothing useful can be \
said. GUI apps: where it appears (Applications, the menu bar, the system tray) and what opens first. \
Command-line tools: the first command to run, in backticks. Do not repeat the install command. \
Say "Applications", not a sandbox path such as ~/Applications.

Write plain English: short sentences, no marketing words, no exclamation marks.
"""


class GuideFeatureOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature: str = Field(description="The feature exactly as given.")
    title: str
    steps: list[str]


class GuideOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    open_hint: str | None
    features: list[GuideFeatureOut]


# --- Input ---------------------------------------------------------------------------------------


def _checked(run: VerificationRun) -> set[str]:
    return {f.feature for f in run.features if f.status == "checked"}


def best_run(record: SoftwareRecord) -> VerificationRun | None:
    """The passed run the steps rest on: most features checked, then an operated GUI app, then the latest."""
    passed = [r for r in record.verification.runs if is_passed(r.level)]
    if not passed:
        return None
    return max(passed, key=lambda r: (len(_checked(r)), r.gui is not None and r.gui.tier == "action_checked",
                                      r.checked_at))


def _cut(text: str | None) -> str:
    text = (text or "").strip()
    return text if len(text) <= EXCERPT_MAX else text[:EXCERPT_MAX] + "…"


def render_input(record: SoftwareRecord, run: VerificationRun | None) -> str:
    """The record and its run as plain text for the model."""
    lines = [f"Name: {record.name}", f"Summary: {record.summary}", f"Kind: {record.kind}",
             f"Category: {record.category}", f"Claims to run on: {', '.join(record.platforms) or 'not stated'}"]
    if record.use_cases:
        lines.append("Use cases: " + "; ".join(record.use_cases))
    if record.mcp and record.mcp.tools:
        lines.append("MCP tools it lists: " + ", ".join(record.mcp.tools[:20]))
    if run is None:
        lines.append("\nNo test run passed, so no feature is CHECKED.")
    else:
        lines.append(f"\nTest run on {run.os} ({run.level}).")
        if run.steps:
            lines.append("Install commands that worked: " + " ; ".join(s.command for s in run.steps))
        guide = getattr(record.install, run.os or "", None)
        if guide and guide.first_task:
            lines.append(f"First command the run tried: {guide.first_task}")
        if run.mcp:
            lines.append(f"An MCP client connected; tools: {', '.join(run.mcp.tools[:20])}"
                         + (f"; it called {run.mcp.called_tool}" if run.mcp.called_tool else ""))
    lines.append("\nAdvertised features:")
    coverage = {f.feature: f for f in run.features} if run else {}
    gui_ops = {op.smoke_test: op for op in (run.gui.operations if run and run.gui else [])}
    web_ops = {op.smoke_test: op for op in (run.web.operations if run and run.web else [])}
    for name in record.features:
        f = coverage.get(name)
        if f is None or f.status != "checked":
            lines.append(f"- {name}: not checked")
            continue
        lines.append(f"- {name}: CHECKED")
        for i in f.smoke_tests:
            if run is None or i >= len(run.smoke_tests) or not run.smoke_tests[i].passed:
                continue
            op = gui_ops.get(i) or web_ops.get(i)
            if op is not None:
                lines.append(f"  - The run operated the app toward this goal: {_cut(op.goal)}")
                lines.append(f"    Result: {_cut(op.observed)}")
            else:
                t = run.smoke_tests[i]
                for s in t.setup:
                    lines.append(f"  - setup: {s.command}")
                lines.append(f"  - command: {t.command}")
                lines.append(f"    expected: {_cut(t.expected_signal)}")
                if t.observed_excerpt:
                    lines.append(f"    output: {_cut(t.observed_excerpt)}")
    return "\n".join(lines)


# --- Calls ---------------------------------------------------------------------------------------


@dataclass
class Generated:
    out: GuideOut
    model: str
    cost_usd: float
    usage: dict[str, int] = field(default_factory=dict)


def _call_anthropic(text: str, client: Any) -> Generated:
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=INSTRUCTIONS,
        output_config={"effort": "low",
                       "format": {"type": "json_schema", "schema": meta_strict_schema(GuideOut)}},
        messages=[{"role": "user", "content": text}],
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"stop_reason {response.stop_reason}")
    body = next(b.text for b in response.content if b.type == "text")
    u = response.usage
    cost = (u.input_tokens * ANTHROPIC_PRICE[0] + u.output_tokens * ANTHROPIC_PRICE[1]) / 1e6
    return Generated(GuideOut.model_validate_json(body), ANTHROPIC_MODEL, cost,
                     {"input": u.input_tokens, "output": u.output_tokens})


def _call_meta(text: str, model: str | None, run_id: str) -> Generated:
    from pickfit.meta import call_meta

    body = {"instructions": INSTRUCTIONS,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": text}]}],
            "text": {"format": {"type": "json_schema", "name": "usage_guide",
                                "schema": meta_strict_schema(GuideOut), "strict": True}},
            "store": False}
    meta = call_meta("responses", body, stage=STAGE, public_data_only=True, max_output_tokens=MAX_OUTPUT_TOKENS,
                     model=model or "prod", reasoning_effort="low", run_id=run_id, output_model=GuideOut)
    if meta.parsed is None:
        raise RuntimeError(f"no parsed output: {meta.parse_error}")
    return Generated(meta.parsed, meta.model, meta.cost_usd)


# --- Records -------------------------------------------------------------------------------------


def to_guide(record: SoftwareRecord, run: VerificationRun | None, gen: Generated, now: datetime) -> dict[str, Any]:
    """The usage_guide field: the model's words, kept only for the record's own features, steps only where checked."""
    checked = _checked(run) if run else set()
    by_name = {f.feature: f for f in gen.out.features}
    features = []
    for name in record.features:
        f = by_name.get(name)
        if f is None or not f.title.strip():
            continue
        steps = [s.strip()[:200] for s in f.steps if s.strip()][:4] if name in checked else []
        features.append({"feature": name, "title": f.title.strip()[:80], "steps": steps})
    hint = (gen.out.open_hint or "").strip()[:200] or None
    return {"model": gen.model, "generated_at": now.isoformat(), "run_id": run.id if run and checked else None,
            "open_hint": hint, "features": features}


def with_guide(raw: dict[str, Any], guide: dict[str, Any]) -> str:
    """The record file with usage_guide set (after why_worth_it) as the schema writes it, so a later
    model_dump of the record does not show it as changed; every other field as it was read."""
    guide = UsageGuide.model_validate(guide).model_dump(mode="json")
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "usage_guide":
            continue
        out[key] = value
        if key == "why_worth_it":
            out["usage_guide"] = guide
    SoftwareRecord.model_validate(out)
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def shown_guide(record: SoftwareRecord) -> dict[str, Any] | None:
    """The guide as the page may show it now: the record's current features only, and steps only for a
    feature some passed run still checks. None when nothing of it applies any more."""
    guide = record.usage_guide
    if guide is None:
        return None
    checked = {f.feature for r in record.verification.runs if is_passed(r.level) for f in r.features if f.status == "checked"}
    features = [{"feature": f.feature, "title": f.title, "steps": list(f.steps) if f.feature in checked else []}
                for f in guide.features if f.feature in record.features]
    if not features and not guide.open_hint:
        return None
    return {**guide.model_dump(mode="json"), "features": features}


def wants_guide(record: SoftwareRecord, force: bool) -> bool:
    if record.status != "listed" or not record.features:
        return False
    if force or record.usage_guide is None:
        return True
    run = best_run(record)
    return record.usage_guide.run_id != (run.id if run and _checked(run) else None)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pickfit usage-guide", description=__doc__.split("\n\n")[0])
    p.add_argument("--data-dir", default="data/software")
    p.add_argument("--slug", action="append", help="only this record (repeatable)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--provider", choices=["meta", "anthropic"], default="meta")
    p.add_argument("--model", default=None, help='meta: "prod" (default), "dev" or a model id')
    p.add_argument("--max-usd", type=float, default=5.0, help="stop starting new calls past this spend")
    p.add_argument("--concurrency", type=int, default=6)
    p.add_argument("--force", action="store_true", help="rewrite guides that are already current")
    p.add_argument("--dry-run", action="store_true", help="print the first input and write nothing")
    args = p.parse_args(argv)

    data = Path(args.data_dir)
    paths = sorted(data.glob("*.json")) if not args.slug else [data / f"{s}.json" for s in args.slug]
    todo = []
    for path in paths:
        record = SoftwareRecord.model_validate_json(path.read_bytes())
        if wants_guide(record, args.force or bool(args.slug)):
            todo.append((path, record))
    todo = todo[: args.limit] if args.limit else todo
    if args.dry_run:
        if todo:
            print(render_input(todo[0][1], best_run(todo[0][1])))
        print(f"\n{len(todo)} records would get a guide", file=sys.stderr)
        return 0

    client = None
    if args.provider == "anthropic":
        import anthropic

        from pickfit.env import get_env
        client = anthropic.Anthropic(api_key=get_env("ANTHROPIC_API_KEY"))
    run_id = f"usage-guide-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    log_dir = Path("runs") / "usage-guide"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = (log_dir / f"{run_id}.jsonl").open("a", encoding="utf-8")
    spent, written, errors = 0.0, 0, {}

    def one(path: Path, record: SoftwareRecord) -> tuple[Path, SoftwareRecord, VerificationRun | None, Generated]:
        run = best_run(record)
        text = render_input(record, run)
        gen = _call_anthropic(text, client) if client else _call_meta(text, args.model, run_id)
        return path, record, run, gen

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        pending = iter(todo)
        futures = {pool.submit(one, *item): item[1].slug for item in [next(pending) for _ in range(min(args.concurrency, len(todo)))]}
        while futures:
            done = next(as_completed(futures))
            slug = futures.pop(done)
            try:
                path, record, run, gen = done.result()
                spent += gen.cost_usd
                raw = json.loads(path.read_text(encoding="utf-8"))
                text = with_guide(raw, to_guide(record, run, gen, datetime.now(timezone.utc)))
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(text, encoding="utf-8")
                os.replace(tmp, path)
                written += 1
                log.write(json.dumps({"slug": slug, "model": gen.model, "cost_usd": round(gen.cost_usd, 6),
                                      "usage": gen.usage}) + "\n")
                print(f"  written  {slug:<40} ${gen.cost_usd:.4f}  total ${spent:.2f}", file=sys.stderr)
            except Exception as err:  # noqa: BLE001 - one record's failure is reported, the rest go on
                errors[slug] = f"{type(err).__name__}: {str(err)[:300]}"
                print(f"  error    {slug:<40} {errors[slug]}", file=sys.stderr)
            if spent < args.max_usd:
                nxt = next(pending, None)
                if nxt is not None:
                    futures[pool.submit(one, *nxt)] = nxt[1].slug
    log.close()
    print(json.dumps({"written": written, "errors": errors, "cost_usd": round(spent, 4), "todo": len(todo),
                      "seconds": round(time.monotonic() - started, 1), "log": str(log.name)}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
