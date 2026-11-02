"""Linux GUI comparison (11/3): why do desktop features go unchecked: environment, step budget, or model? Measure only.

    uv run python scripts/gui_compare.py census [--json out.json]
    uv run python scripts/gui_compare.py rerun --run <evidence run> --ops 18,24 --arm B --max-steps 60 [--model M]
    uv run python scripts/gui_compare.py tally --out results.jsonl

census (arm 0, no cost): every GUI operation in saved evidence (~/.pickfit/evidence/*/report.json for the
agent's operations, replay.json for the fresh box's), counted by why it stopped, with the step counts of the
operations whose check passed. For an operation that hit the step cap it also says whether the operator was
going in circles at the end (gui_operate.circling) and whether the screen was still changing in its last steps.

rerun (arms A-C): a fresh Modal box like the original run's (same runtime, display, no GPU), the agent's shell
commands that exited 0 before the operation rerun in order (installs, folders it made), then each chosen
operation (an index into the report's commands) run again by gui_operate.run_operation with the arm's model and
step budget. Operator and screen-reader calls go through call_meta, so the ledger's budgets and caps apply; the
run id starts with "compare-". Nothing is written to data/software. One JSON line per operation in --out.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from pickfit.verify.gui_operate import LOOP_WINDOW, Step, circling

EVIDENCE = Path.home() / ".pickfit" / "evidence"
TAIL = 8  # the last steps looked at for "still changing the screen"


def operations(node: Any) -> list[dict[str, Any]]:
    """Every operation dict (gui_operate.Operation.to_dict) inside a report, nested replays' first tries included."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if "stop" in node and "steps" in node and "goal" in node:
            found.append(node)
            if isinstance(node.get("first"), dict):
                found.extend(operations(node["first"]))
            return found
        for value in node.values():
            found.extend(operations(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(operations(value))
    return found


def steps_of(op: dict[str, Any]) -> list[Step]:
    return [Step(screenshot=None, sha256=s.get("sha256", ""), changed=bool(s.get("changed")), action=s.get("action"),
                 observation=s.get("observation") or "", why=s.get("why") or "", refused=s.get("refused"))
            for s in op.get("steps") or []]


def looping(steps: list[Step]) -> bool:
    """Whether circling() would have warned the operator at any step (it warns before the next action)."""
    return any(circling(steps[:i]) for i in range(LOOP_WINDOW, len(steps) + 1))


def row_of(run: str, source: str, op: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    steps = steps_of(op)
    tail = steps[-TAIL:]
    feature = op.get("feature")
    names = [f.get("feature") if isinstance(f, dict) else str(f) for f in report.get("features") or []]
    box = report.get("box") or {}
    return {
        "os": box.get("os"), "runner": box.get("runner"), "gpu": box.get("gpu"), "run": run, "slug": report.get("slug") or run.split("-2026")[0].removeprefix("verify-"), "source": source,
        "mode": op.get("mode"), "stop": op.get("stop"), "passed": bool(op.get("passed")), "steps": len(steps),
        "loop": looping(steps), "tail_changed": sum(s.changed for s in tail), "tail": len(tail),
        "feature": feature, "feature_name": names[feature - 1] if isinstance(feature, int) and 0 < feature <= len(names)
        else None, "goal": op.get("goal", "")[:300], "check": (op.get("check") or {}).get("kind"),
        "model": op.get("model"), "cost_usd": op.get("cost_usd") or 0.0, "error": (op.get("error") or "")[:200],
        "last": (steps[-1].observation[:200] if steps else ""),
    }


def census() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_dir in sorted(EVIDENCE.iterdir()):
        report_path = run_dir / "report.json"
        try:
            report = json.loads(report_path.read_text()) if report_path.exists() else {}
        except json.JSONDecodeError:
            report = {}
        for op in operations(report.get("commands") or []):
            rows.append(row_of(run_dir.name, "agent", op, report))
        replay_path = run_dir / "replay.json"
        if replay_path.exists():
            for op in operations(json.loads(replay_path.read_text())):
                rows.append(row_of(run_dir.name, "replay", op, report))
    return rows


def pct(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def summary(rows: list[dict[str, Any]]) -> str:
    operated = [r for r in rows if r["mode"] == "operated"]
    out = [f"[{', '.join(sorted({str(r['os']) for r in rows}))}] operations in evidence: {len(rows)} ({len(operated)} chosen by the model, "
           f"{len(rows) - len(operated)} recorded actions replayed)"]
    stops = Counter(r["stop"] for r in operated)
    out.append("model-operated, by stop: " + ", ".join(f"{k} {v}" for k, v in stops.most_common()))
    capped = [r for r in operated if r["stop"] == "step_cap"]
    out.append(f"  step_cap: {len(capped)}; looping at some point {sum(r['loop'] for r in capped)}; "
               f"screen still changing in >= half of the last {TAIL} steps {sum(2 * r['tail_changed'] >= r['tail'] for r in capped)}; "
               f"cap 18 (older runs) {sum(r['steps'] == 18 for r in capped)}, cap 28 {sum(r['steps'] == 28 for r in capped)}")
    done = [r for r in operated if r["stop"] == "done"]
    out.append(f"  done: {len(done)}, of which pickfit's check passed {sum(r['passed'] for r in done)}; "
               f"step_cap whose check passed anyway (the operator never said done) {sum(r['passed'] for r in capped)}")
    passed = [r["steps"] for r in operated if r["passed"]]
    if passed:
        out.append(f"passed operations (model-operated): {len(passed)}; steps median {statistics.median(passed):g}, "
                   f"p90 {pct(passed, 0.9)}, max {max(passed)}; over 18 steps {sum(s > 18 for s in passed)}, "
                   f"over 24 {sum(s > 24 for s in passed)}")
    apps = Counter(r["slug"] for r in capped)
    out.append(f"step_cap operations come from {len(apps)} apps: " + ", ".join(f"{k} {v}" for k, v in apps.most_common()))
    return "\n".join(out)


def rerun(run: str, ops: list[int], arm: str, model: str | None, max_steps: int, out: Path,
          memory_mb: int | None = None) -> None:
    from pickfit.verify import gui
    from pickfit.verify.box import BoxLimits
    from pickfit.verify.gui_operate import OperateArgs, run_operation
    from pickfit.verify.judge import read_screen_text
    from pickfit.verify.modal_box import ModalBox

    report = json.loads((EVIDENCE / run / "report.json").read_text())
    commands = report["commands"]
    box_info = report["box"]
    runtime = box_info["runner"].removeprefix("modal-")
    audio = "audio" in box_info.get("image", "")
    slug = report["slug"]
    run_id = f"compare-{arm}-{slug}-{time.strftime('%Y%m%d-%H%M%S')}"
    evidence = out.parent / run_id
    say = lambda line: print(f"[{arm} {slug}] {line}", flush=True)  # noqa: E731
    sized = {"memory_mb": memory_mb} if memory_mb else {}
    box = ModalBox(tags={"pickfit.run": run_id, "pickfit.role": "compare"}, runtime=runtime, display=True,
                   audio=audio, limits=BoxLimits(lifetime_s=110 * 60, **sized), log=say)
    began = time.monotonic()
    try:
        box.start()
        for i, cmd in enumerate(commands[:max(ops) + 1]):
            if i not in ops:
                if cmd["tool"] == "run_command" and cmd["exit_code"] == 0 and not cmd.get("timed_out"):
                    result = box.exec(cmd["command"], timeout_s=min(600, int(cmd.get("seconds") or 30) * 3 + 60))
                    say(f"setup {i}: exit {result.exit_code} · {cmd['command'][:90]}")
                continue
            spec = commands[i]["operate"]["spec"]
            args = OperateArgs.model_validate(spec)
            name = report.get("slug")
            model_id = model or (commands[i]["operate"].get("model") if arm != "C" else None)
            scope = {"run_id": run_id, "scope": f"compare:{slug}", "scope_cap_usd": 3.0}
            reader = read_screen_text(name, model="muse-spark-1.3", log=say, **scope)
            t0 = time.monotonic()
            result, op, _ = run_operation(box, args, f"c{i}", model=model_id, max_steps=max_steps, read_screen=reader,
                                          evidence_dir=evidence, log=say,
                                          timeout_s=args.wait_s + gui.SETTLE_S + gui.BLANK_WAIT_S + 90, **scope)
            original = commands[i]["operate"]
            row = {"arm": arm, "run": run, "slug": slug, "op": i, "feature": args.feature, "goal": args.goal[:200],
                   "model": op.model, "max_steps": max_steps, "stop": op.stop, "steps": len(op.steps),
                   "passed": op.passed, "result": op.result, "error": op.error, "cost_usd": round(op.cost_usd, 4),
                   "seconds": round(time.monotonic() - t0), "loop": looping(op.steps),
                   "original": {"stop": original.get("stop"), "steps": len(original.get("steps") or []),
                                "passed": original.get("passed"), "model": original.get("model")}}
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / f"op-{i}.json").write_text(json.dumps(op.to_dict(), indent=1, default=str) + "\n")
            with out.open("a") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
            say(f"op {i}: stop {op.stop}, {len(op.steps)} steps, passed {op.passed}, ${op.cost_usd:.3f}")
    finally:
        box_s = time.monotonic() - began
        box.close()
        with out.open("a") as fh:
            fh.write(json.dumps({"arm": arm, "run": run, "box_seconds": round(box_s),
                                 "box_usd": round(box_s * box.usd_per_second(), 4)}) + "\n")


def tally(out: Path) -> str:
    """Per arm: operations passed now (all failed before, by choice), steps used, how they stopped, and the spend
    the ledger recorded for the arm's run ids (model calls) plus the boxes' time."""
    import sqlite3

    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    ops = [r for r in rows if "stop" in r]
    boxes = [r for r in rows if "box_usd" in r]
    ledger = sqlite3.connect(Path.home() / ".pickfit" / "ledger.sqlite")
    lines = []
    for arm in sorted({r["arm"] for r in ops}):
        part = [r for r in ops if r["arm"] == arm]
        spend = ledger.execute("SELECT budget, ROUND(SUM(cost_usd), 4) FROM calls WHERE run_id LIKE ? GROUP BY budget",
                               (f"compare-{arm}-%",)).fetchall()
        box_usd = sum(b["box_usd"] for b in boxes if b["arm"] == arm)
        passed = [r for r in part if r["passed"]]
        lines.append(f"arm {arm}: {len(passed)}/{len(part)} passed (before: "
                     f"{sum(bool(r['original']['passed']) for r in part)}); stops "
                     + ", ".join(f"{k} {v}" for k, v in Counter(r["stop"] for r in part).most_common())
                     + f"; steps median {statistics.median([r['steps'] for r in part]):g}, max {max(r['steps'] for r in part)}"
                     + (f"; passed at steps {sorted(r['steps'] for r in passed)}" if passed else "")
                     + f"; looping {sum(r['loop'] for r in part)}; model spend "
                     + ", ".join(f"{b} ${c}" for b, c in spend) + f"; boxes ${box_usd:.2f}")
        for r in part:
            lines.append(f"  {r['slug']:22} op {r['op']:2} F{r['feature']} {r['stop']:9} {r['steps']:2} steps "
                         f"{'PASS' if r['passed'] else 'fail'} (before {r['original']['stop']} {r['original']['steps']}) "
                         f"{(r.get('result') or {}).get('why', '')[:90]}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("census")
    c.add_argument("--json", default=None)
    r = sub.add_parser("rerun")
    r.add_argument("--run", required=True)
    r.add_argument("--ops", required=True, help="indexes into the report's commands, comma separated")
    r.add_argument("--arm", required=True)
    r.add_argument("--model", default=None, help="the operator: default the original's (Muse Spark Open)")
    r.add_argument("--max-steps", type=int, default=28)
    r.add_argument("--memory-mb", type=int, default=None)
    r.add_argument("--out", required=True)
    t = sub.add_parser("tally")
    t.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "tally":
        print(tally(Path(args.out)))
        return 0
    if args.cmd == "rerun":
        rerun(args.run, [int(x) for x in args.ops.split(",")], args.arm, args.model, args.max_steps, Path(args.out),
              args.memory_mb)
        return 0
    if args.cmd == "census":
        rows = census()
        if args.json:
            Path(args.json).write_text(json.dumps(rows, indent=1) + "\n")
        for os_name in ("linux", "macos"):
            part = [r for r in rows if r["os"] == os_name]
            if part:
                print(summary(part) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
