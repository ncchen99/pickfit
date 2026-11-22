"""Compare a control and a treatment result file and print a Markdown report.

    uv run python eval/v2/score.py eval/v2/results/run1/control.json eval/v2/results/run1/treatment.json
    uv run python eval/v2/score.py <control> <treatment> --out eval/v2/results/run1/report.md

Only records with valid=true count. A task counts toward a paired metric only when both groups
have a valid record for it, so neither side gains from the other's infrastructure failures.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

TRACK_NAMES = {"A": "A agent capability", "B": "B human web", "C": "C human-agent creative",
               "H": "H build it yourself / built-in"}


def load_group(path: Path) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if "records" not in doc or "group" not in doc:
        raise ValueError(f"{path}: needs 'group' and 'records'")
    ids = [r["task_id"] for r in doc["records"]]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate task_id")
    return doc


def paired(control: dict[str, Any], treatment: dict[str, Any]) -> list[tuple[dict, dict]]:
    by_id = {r["task_id"]: r for r in treatment["records"]}
    pairs = []
    for c in control["records"]:
        t = by_id.get(c["task_id"])
        if t is not None and c.get("valid") and t.get("valid"):
            pairs.append((c, t))
    return sorted(pairs, key=lambda p: p[0]["task_id"])


def rate(values: list[bool | None]) -> tuple[int, int]:
    known = [v for v in values if v is not None]
    return sum(1 for v in known if v), len(known)


def pct(hit: int, total: int) -> str:
    return "n/a" if total == 0 else f"{hit}/{total} ({100 * hit / total:.0f}%)"


def median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    traps = [r for r in records if r.get("honesty_trap")]
    return {
        "n": len(records),
        "first_try": rate([r["first_try_working"] for r in records]),
        "tokens_in": sum(r["tokens_in"] for r in records),
        "tokens_out": sum(r["tokens_out"] for r in records),
        "median_tokens": median([r["tokens_in"] + r["tokens_out"] for r in records]),
        "cost_usd": sum(r["cost_usd"] for r in records),
        "elapsed_s": sum(r["elapsed_s"] for r in records),
        "median_elapsed_s": median([r["elapsed_s"] for r in records]),
        "honest_traps": rate([r["decision_honest"] for r in traps]),
        "decision_all": rate([r["decision_honest"] for r in records]),
        "over_installs": sum(1 for r in traps if r.get("installs")),
    }


def delta(a: float, b: float, unit: str = "", digits: int = 0) -> str:
    diff = b - a
    rel = "" if a == 0 else f" ({100 * diff / a:+.0f}%)"
    return f"{diff:+,.{digits}f}{unit}{rel}"


def mark(value: bool | None) -> str:
    return {True: "yes", False: "no", None: "–"}[value]


def report(control: dict[str, Any], treatment: dict[str, Any]) -> str:
    pairs = paired(control, treatment)
    cs = summarize([c for c, _ in pairs])
    ts = summarize([t for _, t in pairs])
    c_all, t_all = len(control["records"]), len(treatment["records"])
    lines = [
        "# pickfit eval v2: agent without vs with pickfit",
        "",
        f"Paired tasks (valid in both groups): **{len(pairs)}** "
        f"(control records {c_all}, treatment records {t_all}).",
    ]
    if control.get("meta", {}).get("synthetic") or treatment.get("meta", {}).get("synthetic"):
        lines += ["", "> Synthetic fixture data, not a real run."]
    pp = lambda r: 0.0 if r[1] == 0 else 100 * r[0] / r[1]  # noqa: E731
    lines += [
        "",
        "## Core metrics",
        "",
        "| Metric | Without pickfit | With pickfit | Difference |",
        "|---|---|---|---|",
        f"| 1. Working on the first try | {pct(*cs['first_try'])} | {pct(*ts['first_try'])} | "
        f"{pp(ts['first_try']) - pp(cs['first_try']):+.0f} pts |",
        f"| 2a. Tokens in / out (total) | {cs['tokens_in']:,} / {cs['tokens_out']:,} | "
        f"{ts['tokens_in']:,} / {ts['tokens_out']:,} | "
        f"{delta(cs['tokens_in'] + cs['tokens_out'], ts['tokens_in'] + ts['tokens_out'])} |",
        f"| 2b. Median tokens per task | {cs['median_tokens']:,.0f} | {ts['median_tokens']:,.0f} | "
        f"{delta(cs['median_tokens'], ts['median_tokens'])} |",
        f"| 2c. Cost (USD, total) | ${cs['cost_usd']:.2f} | ${ts['cost_usd']:.2f} | "
        f"{delta(cs['cost_usd'], ts['cost_usd'], digits=2)} |",
        f"| 2d. Wall-clock (median s / total s) | {cs['median_elapsed_s']:.0f} / {cs['elapsed_s']:.0f} | "
        f"{ts['median_elapsed_s']:.0f} / {ts['elapsed_s']:.0f} | "
        f"{delta(cs['median_elapsed_s'], ts['median_elapsed_s'], 's')} median |",
        f"| 3. Honest on build-it-yourself / built-in tasks | {pct(*cs['honest_traps'])} | "
        f"{pct(*ts['honest_traps'])} | {pp(ts['honest_traps']) - pp(cs['honest_traps']):+.0f} pts |",
        f"| 3b. Installed something on those tasks | {cs['over_installs']} | {ts['over_installs']} | "
        f"{ts['over_installs'] - cs['over_installs']:+d} |",
        f"| Acceptable decision, all tasks | {pct(*cs['decision_all'])} | {pct(*ts['decision_all'])} | "
        f"{pp(ts['decision_all']) - pp(cs['decision_all']):+.0f} pts |",
        "",
        "## By track",
        "",
        "| Track | Tasks | First try (without) | First try (with) | Median tokens (without → with) | "
        "Median s (without → with) |",
        "|---|---|---|---|---|---|",
    ]
    for track, name in TRACK_NAMES.items():
        sub = [(c, t) for c, t in pairs if c["track"] == track]
        if not sub:
            continue
        a, b = summarize([c for c, _ in sub]), summarize([t for _, t in sub])
        lines.append(f"| {name} | {len(sub)} | {pct(*a['first_try'])} | {pct(*b['first_try'])} | "
                     f"{a['median_tokens']:,.0f} → {b['median_tokens']:,.0f} | "
                     f"{a['median_elapsed_s']:.0f} → {b['median_elapsed_s']:.0f} |")
    lines += [
        "",
        "## Per task",
        "",
        "| Task | Track | First try (without / with) | Decision (without / with) | Honest (without / with) | "
        "Tokens (without / with) | Seconds (without / with) | pickfit calls |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c, t in pairs:
        lines.append(
            f"| {c['task_id']} | {c['track']} | {mark(c['first_try_working'])} / {mark(t['first_try_working'])} | "
            f"{c.get('decision') or '–'} / {t.get('decision') or '–'} | "
            f"{mark(c['decision_honest'])} / {mark(t['decision_honest'])} | "
            f"{c['tokens_in'] + c['tokens_out']:,} / {t['tokens_in'] + t['tokens_out']:,} | "
            f"{c['elapsed_s']:.0f} / {t['elapsed_s']:.0f} | {t.get('pickfit_calls', 0)} |")
    excluded = sorted({r["task_id"] for r in control["records"] + treatment["records"]}
                      - {c["task_id"] for c, _ in pairs})
    if excluded:
        lines += ["", "## Not paired", ""]
        for tid in excluded:
            reasons = [f"{doc['group']}: {r.get('invalid_reason') or 'invalid'}"
                       for doc in (control, treatment) for r in doc["records"]
                       if r["task_id"] == tid and not r.get("valid")]
            missing = [doc["group"] for doc in (control, treatment)
                       if tid not in {r["task_id"] for r in doc["records"]}]
            reasons += [f"{g}: no record" for g in missing]
            lines.append(f"- {tid}: " + "; ".join(reasons))
    lines += ["", "One run per task per group; differences on a handful of tasks are within noise.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Markdown comparison of two v2 eval result files")
    parser.add_argument("control", type=Path)
    parser.add_argument("treatment", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    control, treatment = load_group(args.control), load_group(args.treatment)
    if control["group"] != "control" or treatment["group"] != "treatment":
        print("warning: files are not labelled control/treatment in that order", file=sys.stderr)
    text = report(control, treatment)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
