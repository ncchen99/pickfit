"""Send the same requests to Claude on Anthropic's API and on Amazon Bedrock, and compare what comes back.

pickfit.bedrock_messages was written from AWS's and Anthropic's pages and tested against a fake; nothing in it has
met Bedrock. This is the first real meeting (docs/proposals/aws.md, A1), for whoever holds both keys to run once:

    uv run python scripts/bedrock_compare.py --dry-run     # the requests it would send; no call
    uv run python scripts/bedrock_compare.py               # paid: about US$0.6, half on each bill

It needs ANTHROPIC_API_KEY, PICKFIT_BEDROCK_ACCESS_KEY_ID and PICKFIT_BEDROCK_SECRET_ACCESS_KEY, and the model
enabled in the AWS account (its first invocation there must come from an identity with AWS Marketplace
permissions, not from the narrow key). Every call goes through call_meta with its provider named, so both sides
are in the ledger (budgets "pipeline" and "bedrock") and the trace, under one scope cap (--max-usd).

The cases are the request shapes the pipeline sends, each asked of both providers:

- single: a judge's call, instructions and a JSON schema and an image. Same answer shape, same input count?
- agent: two turns of a tool loop, the history sent again. Does the first turn write the prefix to the cache and
  the second read it, by the same counts on both sides? (Bedrock gets an explicit breakpoint where the direct API
  gets automatic caching: this is where they could differ.)
- hour: the extraction's hour-long cache, twice. Does Bedrock say how much was written for an hour
  (usage.cache_creation), or does pickfit have to assume it?
- switch: a conversation begun on one provider and continued on the other, as after a fall back. Does the second
  turn succeed with the first provider's thinking blocks in its history?

The tool loop's message asks for a version, not for anything about the machine: on 2026-11-22 Bedrock's Claude
declined "find out which shell this is" 7 times in 8 (category cyber) and the direct API never did, and a turn
the direct API answers in Bedrock's place compares nothing. Such a turn is listed and left out of the comparison.

Each prompt starts with the time of the run, so a second run does not read the first one's cache. Exit 0 when the
two sides agree, 1 when something differs or failed (the table says what), 2 when the cap stopped it.
"""

from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pickfit import anthropic_messages, bedrock_messages  # noqa: E402
from pickfit.ledger import BudgetExceeded, taipei_now  # noqa: E402
from pickfit.meta import PROD_MODEL, MetaResult, call_meta  # noqa: E402

PROVIDERS = ("anthropic", "bedrock")
DEFAULT_MAX_USD = 2.0
SCOPE = "bedrock-compare"
TOLERANCE = 0.02  # input counts may differ by the tool preamble each platform adds
SLACK = 32  # tokens: the same preamble against a small count (a second turn's 139 written against 150)
CALLS = 14  # single 2, agent 4, hour 4, switch 4
TOOLS = [{"type": "function", "name": "run_command", "description": "Run one shell command in the sandbox.",
          "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"],
                         "additionalProperties": False}}]
VERDICT = {"type": "object", "additionalProperties": False, "required": ["verdict", "reason"],
           "properties": {"verdict": {"type": "string", "enum": ["pass", "fail"]}, "reason": {"type": "string"}}}


def png(size: int = 64, rgb: tuple[int, int, int] = (40, 120, 200)) -> str:
    """A flat-colour PNG as a data: URL, made here so that the request carries a real image."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = (b"\x00" + bytes(rgb) * size) * size
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(data).decode()


def prefix(nonce: str, role: str) -> str:
    """About 5K tokens of instructions, the same on both sides and long enough for any model's cache minimum."""
    rules = "\n".join(f"Rule {n}: when a check numbered {n} is asked for, answer only from what the request shows, "
                      f"name the line you used, and never guess the output of a command you did not see."
                      for n in range(1, 151))
    return f"Run {nonce}. You are the {role} of a software catalogue's verification pipeline.\n{rules}"


def _native(result: MetaResult, seen: list[dict[str, Any]]) -> dict[str, Any]:
    """The usage of the Message behind a result, as the platform sent it (recorded by the from_message hook)."""
    return next((m.get("usage") or {} for m in seen if m.get("id") == result.response_id), {})


def summary(result: MetaResult, asked: str, seen: list[dict[str, Any]]) -> dict[str, Any]:
    usage = result.usage
    return {"provider": result.provider, "fell_back": result.provider != asked, "status": result.status,
            "items": [item.get("type") for item in result.output_items],
            "tool_calls": [call.name for call in result.tool_calls], "parsed": result.parse_error is None,
            "input": usage.input_tokens if usage else None, "cache_read": usage.cached_tokens if usage else None,
            "cache_write": usage.cache_write_tokens if usage else None,
            "cache_write_1h": usage.cache_write_1h_tokens if usage else None,
            "output": usage.output_tokens if usage else None, "usd": round(result.cost_usd, 6),
            "native_usage_keys": sorted(_native(result, seen))}


def run_cases(ask, nonce: str) -> dict[str, dict[str, Any]]:
    """{case: {provider or "a->b": [one summary per call]}}. `ask(provider, body, **options)` makes one call."""
    out: dict[str, dict[str, Any]] = {"single": {}, "agent": {}, "hour": {}, "switch": {}}
    judge = {"instructions": prefix(nonce, "judge"), "store": False,
             "input": [{"role": "user", "content": [
                 {"type": "input_text", "text": "Check 7: is the picture a single flat colour? Answer as JSON."},
                 {"type": "input_image", "image_url": png()}]}],
             "text": {"format": {"type": "json_schema", "name": "verdict", "schema": VERDICT, "strict": True}}}
    first = {"instructions": prefix(nonce, "agent"), "tools": TOOLS, "reasoning": {"summary": "auto"},
             "input": [{"role": "user", "content": "Check 12: print the version of the tool under test. Call "
                                                 "run_command once, with `tinyq --version`."}]}
    extract = {"instructions": prefix(nonce, "reader"), "prompt_cache_retention": "1h"}

    def second(turn_one: MetaResult) -> dict[str, Any]:
        outputs = [{"type": "function_call_output", "call_id": call.call_id, "output": "tinyq 1.4.2"}
                   for call in turn_one.tool_calls]
        return {**first, "input": [*first["input"], *turn_one.output_items, *outputs,
                                   {"role": "user", "content": "Now say in one sentence what you found."}]}

    for provider in PROVIDERS:
        out["single"][provider] = [ask(provider, judge, effort="low")]
        one = ask(provider, first, conversation=True)
        out["agent"][provider] = [one, ask(provider, second(one), conversation=True)]
        out["hour"][provider] = [ask(provider, {**extract, "input": f"Check {n}: reply with the number {n}."},
                                     effort="low") for n in (3, 4)]
    for begun, continued in (PROVIDERS, PROVIDERS[::-1]):
        one = ask(begun, {**first, "instructions": prefix(nonce, f"agent begun on {begun}")}, conversation=True)
        two = {**second(one), "instructions": prefix(nonce, f"agent begun on {begun}")}
        out["switch"][f"{begun}->{continued}"] = [one, ask(continued, two, conversation=True)]
    return out


def differences(cases: dict[str, dict[str, list[dict[str, Any]]]]) -> list[str]:
    """What the two sides disagree on, and what a case exists to show."""
    found: list[str] = []

    def close(a: int | None, b: int | None) -> bool:
        return a == b or (a is not None and b is not None
                          and abs(a - b) <= max(SLACK, TOLERANCE * max(a, b, 1)))

    def shape(call: dict[str, Any], field: str) -> Any:
        # Whether the model thought before answering varies from one run to the next on either side.
        return [item for item in call[field] if item != "reasoning"] if field == "items" else call[field]

    for case, sides in cases.items():
        for key, calls in sides.items():
            found += [f"{case}/{key} call {n}: answered by {c['provider']}, not as asked (Bedrock gave way)"
                      for n, c in enumerate(calls, 1) if c["fell_back"]]
            found += [f"{case}/{key} call {n}: status {c['status']}" for n, c in enumerate(calls, 1)
                      if c["status"] != "completed"]
        if case == "switch":
            continue
        direct, bedrock = sides["anthropic"], sides["bedrock"]
        for n, (a, b) in enumerate(zip(direct, bedrock, strict=True), 1):
            if b["fell_back"]:
                continue  # the direct API answered in Bedrock's place: there is no Bedrock answer to compare
            for field in ("items", "tool_calls", "parsed"):
                if shape(a, field) != shape(b, field):
                    found.append(f"{case} call {n}: {field} {a[field]} on the direct API, {b[field]} on Bedrock")
            for field in ("input", "cache_read", "cache_write", "cache_write_1h"):
                if not close(a[field], b[field]):
                    found.append(f"{case} call {n}: {field} {a[field]} on the direct API, {b[field]} on Bedrock")
    agent = cases["agent"]["bedrock"]
    if any(c["fell_back"] for c in agent):
        found.append("agent: the cache across a tool loop was not shown, since Bedrock gave way on a turn "
                     "(the trace has the usage of what Bedrock itself answered or declined)")
    elif not agent[0]["cache_write"] or not agent[1]["cache_read"]:
        found.append("agent: Bedrock did not write the first turn to the cache and read it on the second "
                     "(the explicit breakpoint is not doing what automatic caching does)")
    hour = cases["hour"]["bedrock"]
    if "cache_creation" not in hour[0]["native_usage_keys"]:
        found.append("hour: Bedrock's usage has no cache_creation breakdown, so bedrock_messages.with_usage's "
                     "assumption (every write to an hour's request is an hour's) is what prices it")
    return found


def render(cases: dict[str, dict[str, list[dict[str, Any]]]], found: list[str]) -> str:
    lines = [f"{'case':<8}{'side':<20}{'call':>4} {'status':<11}{'input':>8}{'read':>8}{'write':>8}{'1h':>7}"
             f"{'output':>8}{'usd':>10}  items"]
    for case, sides in cases.items():
        for side, calls in sides.items():
            for n, c in enumerate(calls, 1):
                lines.append(f"{case:<8}{side:<20}{n:>4} {str(c['status']):<11}{c['input']!s:>8}{c['cache_read']!s:>8}"
                             f"{c['cache_write']!s:>8}{c['cache_write_1h']!s:>7}{c['output']!s:>8}{c['usd']:>10.4f}"
                             f"  {','.join(map(str, c['items']))}")
    total = {p: sum(c["usd"] for sides in cases.values() for calls in sides.values() for c in calls
                    if c["provider"] == p) for p in PROVIDERS}
    lines.append(f"spent: US${total['anthropic']:.4f} on Anthropic's API, US${total['bedrock']:.4f} on Bedrock")
    lines += ["the two sides agree"] if not found else ["differences:", *(f"- {line}" for line in found)]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default=PROD_MODEL, help=f"the model, on both sides ({PROD_MODEL})")
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD, help="both sides together stop past this")
    parser.add_argument("--out", type=Path, help="write the comparison as JSON here")
    parser.add_argument("--dry-run", action="store_true", help="list the calls; make none")
    args = parser.parse_args(argv)
    nonce = taipei_now().isoformat(timespec="seconds")
    run_id = f"bedrock-compare-{nonce}"
    seen: list[dict[str, Any]] = []
    if args.dry_run:
        print(f"{CALLS} calls to {args.model}, {CALLS // 2} on each provider: a judge's single call with an image, "
              "two turns of a tool loop, the hour-long cache twice, and a conversation begun on one provider and "
              f"continued on the other (both ways). Each carries about {len(prefix(nonce, 'judge')) // 4} tokens of "
              f"instructions. About US$0.6 in all at {PROD_MODEL}'s prices; the cap is US${args.max_usd:.2f}.")
        return 0

    def ask(provider: str, body: dict[str, Any], *, effort: str = "medium", conversation: bool = False) -> MetaResult:
        return call_meta("responses", body, stage=SCOPE, public_data_only=True, max_output_tokens=2000,
                         model=args.model, provider=provider, reasoning_effort=effort, scope=SCOPE,
                         scope_cap_usd=args.max_usd, run_id=run_id, cache=False, conversation=conversation)

    # Each Message is recorded as its platform sent it, before pickfit reshapes it: Bedrock's on its way into
    # with_usage (which may add the cache breakdown), the direct API's on its way into from_message. _native takes
    # the first record of an id, so Bedrock's is the untouched one.
    read, fill = anthropic_messages.from_message, bedrock_messages.with_usage

    def recording_read(message: dict[str, Any], plan: Any) -> dict[str, Any]:
        seen.append(message)
        return read(message, plan)

    def recording_fill(message: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any]:
        seen.append(message)
        return fill(message, kwargs)

    anthropic_messages.from_message, bedrock_messages.with_usage = recording_read, recording_fill
    try:
        results = run_cases(ask, nonce)
    except BudgetExceeded as err:
        print(f"stopped by the cap: {err}", file=sys.stderr)
        return 2
    finally:
        anthropic_messages.from_message, bedrock_messages.with_usage = read, fill
    asked = {"anthropic->bedrock": PROVIDERS, "bedrock->anthropic": PROVIDERS[::-1]}
    cases = {case: {side: [summary(r, asked.get(side, (side, side))[n], seen) for n, r in enumerate(calls)]
                    for side, calls in sides.items()} for case, sides in results.items()}
    found = differences(cases)
    print(render(cases, found))
    if args.out:
        args.out.write_text(json.dumps({"run_id": run_id, "model": args.model, "cases": cases,
                                        "differences": found}, indent=2, ensure_ascii=False), encoding="utf-8")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
