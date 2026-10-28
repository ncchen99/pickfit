"""Meta model usage report for the README and the video (P5.5), as Markdown.

Usage:
    uv run python scripts/meta_usage.py
    uv run python scripts/meta_usage.py --runs runs --runs ../<worktree>/runs --out usage.md

Sources:
- the shared ledger (~/.pickfit/ledger.sqlite, PICKFIT_LEDGER overrides): every request
  call_meta made from any worktree, with tokens and cost from the API's own usage;
- the traces (<runs>/traces/*.jsonl, one line per attempt): latency and finish status;
- verification runs (<runs>/verify/*/outcome.json and report.json): pass rate and time per run;
- the records (data/software/*.json): verification level per tool.

Only spending is reported, never credit balances. The Worker's own Meta budget lives in its
D1 database and the evaluation's Anthropic spend is separate; neither is in this ledger.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from pickfit.env import get_env
from pickfit.ledger import DEFAULT_PATH, taipei_now
from pickfit.schema import PASSED_LEVELS

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKENS = ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens")
BILLED = ("settled", "unknown", "no_usage")  # a request that reached the API and may be billed


# --- loading ----------------------------------------------------------------------------------


def ledger_rows(path: Path, budget: str = "pipeline", since: str | None = None) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM calls WHERE budget = ?" + (" AND day >= ?" if since else "") + " ORDER BY id"
        return [dict(r) for r in conn.execute(query, (budget, since) if since else (budget,))]
    finally:
        conn.close()


def trace_rows(runs_dirs: Iterable[Path], since: str | None = None) -> list[dict[str, Any]]:
    """Model-call trace lines from every runs dir, each attempt once."""
    seen: set[tuple[Any, ...]] = set()
    rows = []
    for runs in runs_dirs:
        for path in sorted((runs / "traces").glob("*.jsonl")):
            if path.name.startswith("github-") or (since and path.stem < since):
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (row.get("ts"), row.get("request_hash"), row.get("attempt"), row.get("run_id"))
                if "model" in row and key not in seen:
                    seen.add(key)
                    rows.append(row)
    return rows


def verify_runs(runs_dirs: Iterable[Path]) -> list[dict[str, Any]]:
    """outcome.json of every verification run, with the agent model from report.json."""
    runs: dict[str, dict[str, Any]] = {}
    for base in runs_dirs:
        for outcome_path in sorted((base / "verify").glob("*/outcome.json")):
            outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
            report_path = outcome_path.with_name("report.json")
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
            outcome["model"] = report.get("model")
            runs.setdefault(outcome.get("run_id") or outcome_path.parent.name, outcome)
    return list(runs.values())


def record_levels(data_dir: Path) -> Counter[str]:
    levels: Counter[str] = Counter()
    for path in sorted(data_dir.glob("*.json")):
        verification = json.loads(path.read_text(encoding="utf-8")).get("verification") or {}
        level = verification.get("level") or "unverified"
        reason = verification.get("unverified_reason")
        levels[f"{level} ({reason})" if level == "unverified" and reason else level] += 1
    return levels


# --- aggregation ------------------------------------------------------------------------------


def _spend(row: dict[str, Any]) -> float:
    return row["reserved_usd"] if row["status"] == "reserved" else row["cost_usd"]


def group(rows: list[dict[str, Any]], key: Any) -> dict[Any, dict[str, Any]]:
    out: dict[Any, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "cache_hits": 0, "failed": 0, "cost": 0.0,
                                                          **dict.fromkeys(TOKENS, 0)})
    for row in rows:
        g = out[key(row)]
        g["cost"] += _spend(row)
        if row["status"] == "cache":
            g["cache_hits"] += 1
            continue
        if row["status"] not in BILLED:
            g["failed"] += row["status"] == "error"
            continue
        g["calls"] += 1
        for t in TOKENS:
            g[t] += row[t] or 0
    return dict(out)


def hit_rate(g: dict[str, Any]) -> float | None:
    return g["cached_tokens"] / g["input_tokens"] if g["input_tokens"] else None


def latencies(traces: list[dict[str, Any]], key: Any) -> dict[Any, list[float]]:
    out: dict[Any, list[float]] = defaultdict(list)
    for t in traces:
        if t.get("status") == "ok" and not t.get("cache_hit") and t.get("latency_s") is not None:
            out[key(t)].append(t["latency_s"])
    return out


def pct(values: list[float], q: float) -> float | None:
    """The q-quantile with linear interpolation (q=0.5 is the median)."""
    if not values:
        return None
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def passed(run: dict[str, Any]) -> bool:
    return run.get("level") in PASSED_LEVELS and bool(run.get("replayed"))


# --- formatting -------------------------------------------------------------------------------


def usd(v: float | None) -> str:
    return "–" if v is None else f"${v:,.2f}" if v >= 1 else f"${v:.4f}"


def num(v: int | float | None) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:,.1f}"
    return f"{v:,}"


def share(a: float | None) -> str:
    return "–" if a is None else f"{a:.0%}"


def secs(v: float | None) -> str:
    return "–" if v is None else f"{v:.0f} s" if v >= 10 else f"{v:.1f} s"


def table(header: list[str], rows: list[list[str]], right: Iterable[int] = ()) -> str:
    right = set(right)
    align = ["---:" if i in right else "---" for i in range(len(header))]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(align) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _token_cells(g: dict[str, Any]) -> list[str]:
    return [num(g["calls"]), num(g["input_tokens"]), num(g["cached_tokens"]), share(hit_rate(g)),
            num(g["output_tokens"]), num(g["reasoning_tokens"]), usd(g["cost"])]


TOKEN_HEADER = ["requests", "input tokens", "cached", "cache hit", "output tokens", "reasoning", "cost"]


def report(rows: list[dict[str, Any]], traces: list[dict[str, Any]], runs: list[dict[str, Any]],
           levels: Counter[str], *, now: datetime, sources: dict[str, str]) -> str:
    # The ledger is the record of what was sent; a trace line it does not know (a unit test that
    # wrote to a real runs/ directory, a call billed to another ledger) is left out.
    known = {r["response_id"] for r in rows if r.get("response_id")}
    traces = [t for t in traces if t.get("response_id") in known]
    total = group(rows, lambda r: "all").get("all") or group([], lambda r: "all")
    by_model = group(rows, lambda r: r["model"] or "?")
    by_stage = group(rows, lambda r: (r["stage"] or "?", r["model"] or "?"))
    by_day = group(rows, lambda r: r["day"])
    lat_stage = latencies(traces, lambda t: (t.get("stage") or "?", t.get("model") or "?"))
    lat_all = [v for vs in lat_stage.values() for v in vs]
    incomplete = sum(1 for t in traces if t.get("status") == "ok" and t.get("finish") == "incomplete")
    ok_traces = sum(1 for t in traces if t.get("status") == "ok")
    days = sorted(by_day)

    n_runs = len(runs)
    n_passed = sum(1 for r in runs if passed(r))
    tools = {r.get("slug") for r in runs}
    tools_passed = {r.get("slug") for r in runs if passed(r)}
    run_secs = [r["seconds"] for r in runs if r.get("seconds") is not None]
    run_meta = [r["cost_usd"] for r in runs if r.get("cost_usd") is not None]
    run_box = [r["box_usd"] for r in runs if r.get("box_usd") is not None]
    n_records = sum(levels.values())
    records_passed = sum(n for level, n in levels.items() if level in PASSED_LEVELS)

    out = [f"# Meta model usage\n\nGenerated {now.strftime('%Y-%m-%d %H:%M')} (Taipei) from the shared ledger, "
           "the call traces and the verification runs. Spending only; credit balances are not reported.\n"]
    out.append("## Headline\n")
    headline = [
        f"**{num(total['calls'])} Meta API requests** ({', '.join(sorted(by_model))}) "
        f"over {len(days)} day(s) ({days[0] if days else '–'} – {days[-1] if days else '–'}), **{usd(total['cost'])}** in total.",
        f"**{num(total['input_tokens'])} input tokens**, {num(total['cached_tokens'])} of them served from Meta's "
        f"prompt cache (**{share(hit_rate(total))} cache hit**); {num(total['output_tokens'])} output tokens, "
        f"{num(total['reasoning_tokens'])} of them reasoning.",
    ]
    if total["cache_hits"]:
        headline.append(f"{num(total['cache_hits'])} more calls were answered from pickfit's local response "
                        "cache during development ($0).")
    if n_runs:
        headline.append(
            f"**Verification: {n_passed} of {n_runs} sandbox runs passed and replayed ({share(n_passed / n_runs)})**; "
            f"{len(tools_passed)} of {len(tools)} tools passed at least once. Median **{secs(pct(run_secs, 0.5))} per run** "
            f"(p90 {secs(pct(run_secs, 0.9))}), median Meta cost {usd(pct(run_meta, 0.5))} per run.")
    if n_records:
        headline.append(f"Records: {records_passed} of {n_records} in data/software carry a passed, replayed run.")
    if lat_all:
        headline.append(f"Median request latency {secs(pct(lat_all, 0.5))} (p90 {secs(pct(lat_all, 0.9))}) "
                        f"over {len(lat_all):,} traced requests.")
    out.append("\n".join(f"- {h}" for h in headline) + "\n")

    out.append("## By model\n")
    out.append(table(["model", *TOKEN_HEADER, "share of cost"],
                     [[f"`{m}`", *_token_cells(g), share(g["cost"] / total["cost"] if total["cost"] else None)]
                      for m, g in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"])],
                     right=range(1, 9)) + "\n")

    out.append("## By stage\n")
    stage_rows = []
    for (stage, model), g in sorted(by_stage.items(), key=lambda kv: -kv[1]["cost"]):
        lat = lat_stage.get((stage, model), [])
        stage_rows.append([f"`{stage}`", f"`{model}`", *_token_cells(g), secs(pct(lat, 0.5)),
                           usd(g["cost"] / g["calls"]) if g["calls"] else "–"])
    out.append(table(["stage", "model", *TOKEN_HEADER, "median latency", "cost / request"], stage_rows,
                     right=range(2, 11)) + "\n")
    out.append("Stages: `extract` reads a README into a profile; `verify` is the sandbox agent's turns; "
               "`verify-judge` reads the redrawn screenshots; `score-rubric` grades the documentation; "
               "the rest are probes and smoke tests.\n")

    out.append("## By day\n")
    out.append(table(["day (Taipei)", *TOKEN_HEADER],
                     [[d, *_token_cells(by_day[d])] for d in days], right=range(1, 8)) + "\n")

    if runs:
        out.append("## Verification runs\n")
        by_model_runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in runs:
            by_model_runs[f"{r.get('runner') or '?'} · {r.get('model') or '?'}"].append(r)
        rows_v = []
        for key, rs in sorted(by_model_runs.items()):
            p = sum(1 for r in rs if passed(r))
            secs_k = [r["seconds"] for r in rs if r.get("seconds") is not None]
            rows_v.append([key, num(len(rs)), num(p), share(p / len(rs)), secs(pct(secs_k, 0.5)),
                           secs(pct(secs_k, 0.9)), usd(pct([r["cost_usd"] for r in rs if r.get("cost_usd") is not None], 0.5))])
        out.append(table(["runner · agent model", "runs", "passed + replayed", "pass rate", "median time",
                          "p90 time", "median Meta $"], rows_v, right=range(1, 7)) + "\n")
        levels_runs = Counter(r.get("level") for r in runs)
        out.append("Run results: " + ", ".join(f"{k} {v}" for k, v in levels_runs.most_common()) + ". "
                   "A run passes only when the command log, a fresh-box replay and the screen judge all agree.\n")
        phases: dict[str, list[float]] = defaultdict(list)
        for r in runs:
            for name, value in (r.get("phases") or {}).items():
                if isinstance(value, (int, float)) and not name.endswith("_box_s"):
                    phases[name].append(value)
        if phases:
            out.append(table(["phase", "median", "p90", "runs"],
                             [[name, secs(pct(v, 0.5)), secs(pct(v, 0.9)), num(len(v))] for name, v in phases.items()],
                             right=(1, 2, 3)) + "\n")
        out.append(f"Sandbox (Modal) cost per run, estimated by the runner: median {usd(pct(run_box, 0.5))}, "
                   f"total {usd(sum(run_box))} over {len(run_box)} runs.\n")

    if n_records:
        out.append("## Records by verification level\n")
        out.append(table(["level", "records"], [[k, num(v)] for k, v in levels.most_common()], right=(1,)) + "\n")

    out.append("## Notes\n")
    notes = [f"{name}: `{value}`" for name, value in sources.items()]
    notes += [f"Traced requests that finished incomplete (ran out of output tokens): {incomplete} of {ok_traces}.",
              "Requests count every attempt that reached the API; a request refused before generation (4xx) is "
              "counted as failed and costs $0.",
              "Cost is priced from each response's usage at the published per-token rates; cached input is "
              "billed at the cached rate."]
    out.append("\n".join(f"- {n}" for n in notes) + "\n")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=None, help="ledger file (default PICKFIT_LEDGER or ~/.pickfit)")
    parser.add_argument("--runs", type=Path, action="append",
                        help="a runs directory with traces/ and verify/ (repeatable; default runs/)")
    parser.add_argument("--data", type=Path, default=REPO_ROOT / "data" / "software", help="records directory")
    parser.add_argument("--since", help="only this Taipei day and later (YYYY-MM-DD)")
    parser.add_argument("--out", type=Path, default=None, help="write the Markdown here instead of stdout")
    args = parser.parse_args(argv)
    ledger = args.ledger or Path(get_env("PICKFIT_LEDGER") or DEFAULT_PATH)
    runs_dirs = args.runs or [REPO_ROOT / "runs"]
    text = report(ledger_rows(ledger, since=args.since), trace_rows(runs_dirs, args.since), verify_runs(runs_dirs),
                  record_levels(args.data), now=taipei_now(),
                  sources={"ledger": "~/.pickfit/ledger.sqlite" if ledger == DEFAULT_PATH else str(ledger),
                           "runs": ", ".join(_short(p) for p in runs_dirs), "records": _short(args.data)})
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"meta_usage: wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


def _short(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve()).replace(str(Path.home()), "~")


if __name__ == "__main__":
    sys.exit(main())
