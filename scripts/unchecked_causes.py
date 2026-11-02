"""Why did desktop features end up not_checked with reason other or not_shown? Classify from saved evidence.

    uv run python scripts/unchecked_causes.py [--json out.json] [--ask-model]

For each desktop app's latest run per OS, every feature not_checked with reason other or not_shown is read
against the run's saved trace (~/.pickfit/evidence/<run id>/report.json): the agent's feature claim and the
commands it cited, every GUI operation for that feature (why it stopped, whether it looped, what pickfit's check
found), and the feature judge's verdict. Rules give one cause each; --ask-model sends the ones the rules leave
unknown to Muse Spark Open (Modal endpoint, ledger budget modal-llm). Reads data/software, writes nothing there.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from pickfit.env import REPO_ROOT
from pickfit.verify.gui_operate import LOOP_WINDOW, Step, circling

EVIDENCE = Path.home() / ".pickfit" / "evidence"

NEEDS_MODEL = re.compile(r"\b(GGUF|model (download|file)|models? (are|is) (large|multi)|[0-9.]+ ?GB|ollama|"
                         r"llama-server|embedding|weights|download of|needs? (a |local )?(LLM|model))", re.I)
NEEDS_INPUT = re.compile(r"\b(ROM|game data|save file|workspace file|media files?|torrent|magnet|sample "
                         r"(song|video)|needs? (an? )?(\w+ )?(file|project|document|book) )", re.I)
NEEDS_SERVICE = re.compile(r"\b(server|daemon|account|sign[ -]?in|log ?in|API key|IMAP|peer|phone|remote "
                           r"machine|internet|network|online)\b", re.I)
# A desktop piece the box lacks (said as missing, not just a dialog the operator struggled with).
DESKTOP = re.compile(r"\b(portal|no session bus|URI handler|handler error|xdg-open|chooser never opened|Wayland|compositor|layer-shell|"
                     r"tray|keyring|window manager)\b", re.I)
APP_ERROR = re.compile(r"\b(crash\w*|black (screen|rectangle|window)|blank|white screen|not responding|error "
                       r"(view|dialog|message)|shows Error|exception|segfault|froze|hang\w*|rendering glitch|"
                       r"renders as (solid|black))\b", re.I)
DEVICE = re.compile(r"permission|accessibility|input-monitoring|microphone|soundcard|no audio", re.I)
REPLAY = re.compile(r"did not pass again in a fresh box", re.I)
CHECK_DESIGN = re.compile(r"typed by the operator|on screen before the first action|raw-zip|compressed", re.I)
OFF_SCREEN = re.compile(r"\b(off[- ]screen|clipp\w+|cut off|outside the window|scrolled)\b", re.I)
# What an agent's note alone says (the trace may be gone, or the feature had no operation): first match wins.
NOTE_CAUSES = (
    (re.compile(r"its check passed, but the output does not show", re.I), "judge: command output did not show the feature"),
    (REPLAY, "replay: passed in the agent's box, not in the fresh box"),
    (re.compile(r"its check did not pass in the log", re.I), "check: the cited command's check failed"),
    (re.compile(r"\bloop", re.I), "operator loop"),
    (re.compile(r"step (cap|limit)|operator/step limits|\bsteps?\b.*\b(cap|limit)", re.I), "operator step cap"),
    (re.compile(r"\bmissed|hitbox|off-target", re.I), "operator misclicked"),
    (DEVICE, "needs an OS permission or device"),
    (OFF_SCREEN, "dialog or result off-screen (clipped)"),
    (CHECK_DESIGN, "check: expected text typed, already on screen, or inside a compressed file"),
    (re.compile(r"too small to|tool-capable model", re.I), "needs a model or download"),
    (re.compile(r"visual-only|no file[/,] ?(clipboard|or)|cannot be automated|manual input|lock-screen|not directly "
                r"testable|"
                r"System Settings|keep .* after|cannot simulate|global hotkey", re.I), "no checkable result (visual or system effect)"),
    (re.compile(r"no Linux desktop bundle|no \w+ app is installed|engine-only", re.I), "no desktop build in the box"),
    (DESKTOP, "missing desktop component"),
    (NEEDS_MODEL, "needs a model or download"),
    (NEEDS_INPUT, "needs input data"),
    (NEEDS_SERVICE, "needs a service or account"),
    (re.compile(r"no project|blocked|could not set|not reachable|did not expose|not found", re.I),
     "operator could not reach the feature"),
)


def note_cause(note: str) -> str | None:
    return next((cause for pattern, cause in NOTE_CAUSES if pattern.search(note)), None)


def latest_runs(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for run in record["verification"].get("runs", []):
        latest[run.get("os")] = run
    return latest


def targets() -> list[dict[str, Any]]:
    rows = []
    for path in sorted((REPO_ROOT / "data" / "software").glob("*.json")):
        record = json.loads(path.read_text())
        if record.get("kind") != "desktop_app":
            continue
        for os_name, run in latest_runs(record).items():
            for fc in run.get("features", []):
                if fc["status"] == "not_checked" and fc.get("reason") in ("other", "not_shown"):
                    rows.append({"slug": record["slug"], "os": os_name, "run": run.get("id"), "feature": fc["feature"],
                                 "reason": fc["reason"], "note": fc.get("note") or "",
                                 "log_path": (run.get("evidence") or {}).get("log_path")})
    return rows


def operations(report: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [(i, c["operate"]) for i, c in enumerate(report.get("commands") or []) if c.get("operate")]


def steps_of(op: dict[str, Any]) -> list[Step]:
    return [Step(screenshot=None, sha256=s.get("sha256", ""), changed=bool(s.get("changed")), action=s.get("action"),
                 observation=s.get("observation") or "", why=s.get("why") or "", refused=s.get("refused"))
            for s in op.get("steps") or []]


def looped(op: dict[str, Any]) -> bool:
    steps = steps_of(op)
    return any(circling(steps[:i]) for i in range(LOOP_WINDOW, len(steps) + 1))


def words_of(op: dict[str, Any]) -> str:
    """The operator's last words and pickfit's check line: what the screen and the check showed at the end."""
    steps = op.get("steps") or []
    last = " ".join(f"{s.get('observation') or ''} {s.get('why') or ''}" for s in steps[-4:])
    result = op.get("result") or {}
    return f"{last} {result.get('why') or ''} {result.get('line') or ''} {op.get('error') or ''}"


def classify(row: dict[str, Any]) -> tuple[str, str]:
    """(cause, the evidence it rests on)."""
    note = row["note"]
    if note.startswith("install-only run"):
        return "not attempted (install-only run)", note
    run_dir = EVIDENCE / (row["run"] or "")
    report_path = run_dir / "report.json"
    if not row["run"] or not report_path.exists():
        return f"{note_cause(note) or 'unknown'} (note only: no trace on this machine)", note[:200]
    report = json.loads(report_path.read_text())
    claims = {f.get("feature"): f for f in report.get("features") or [] if isinstance(f, dict)}
    claim = claims.get(row["feature"]) or {}
    number = claim.get("number")
    ops = [(i, op) for i, op in operations(report)
           if i in (claim.get("command_ids") or []) or (number is not None and op["spec"].get("feature") == number)]
    if row["reason"] == "not_shown":
        judged: list[str] = []
        judge_path = run_dir / "feature_judge.json"
        if judge_path.exists():
            judged = (json.loads(judge_path.read_text()).get("verdicts") or {}).get(row["feature"]) or []
        why = judged[1] if len(judged) > 1 else note
        if ops and all(op.get("passed") for _, op in ops):
            return "judge: GUI check passed, feature not shown", why[:200]
        return "judge: command output did not show the feature", why[:200]
    if not ops:
        return note_cause(note) or "not operated (no operation for it)", note[:200]
    _, last = ops[-1]
    text = f"{note} {words_of(last)}"
    stop, result = last.get("stop"), last.get("result") or {}
    if stop == "no_window":
        return "app showed no window", text[:200]
    if stop in ("error", "budget"):
        return f"harness: {stop}", (last.get("error") or "")[:200]
    if REPLAY.search(note):
        return "replay: passed in the agent's box, not in the fresh box", text[:200]
    if DESKTOP.search(note):
        return "missing desktop component", text[:200]
    if DEVICE.search(note):
        return "needs an OS permission or device", text[:200]
    if CHECK_DESIGN.search(f"{note} {result.get('why') or ''}"):
        return "check: expected text typed, already on screen, or inside a compressed file", text[:200]
    if APP_ERROR.search(f"{note} {words_of(last)}"):
        return "app crashed or showed an error", text[:200]
    if stop == "step_cap":
        return ("operator loop" if looped(last) else "operator step cap"), text[:200]
    if stop == "give_up":
        for pattern, cause in ((NEEDS_MODEL, "needs a model or download"), (NEEDS_SERVICE, "needs a service or account"),
                               (NEEDS_INPUT, "needs input data")):
            if pattern.search(text):
                return cause, text[:200]
        return "operator gave up", text[:200]
    why = str(result.get("why") or "")
    if OFF_SCREEN.search(text):
        return "check: result off-screen", text[:200]
    if stop == "done":
        return "check: operator said done, pickfit's check failed", why[:200]
    return note_cause(note) or "unknown", text[:200]


ASK = """\
A verification run tried to exercise one advertised feature of a desktop app and could not show it. From the \
evidence below (the agent's note, and how the GUI operation for it ended), name the most likely cause, one of: \
operator step cap, operator loop, missing desktop component, app crashed or showed an error, check too strict or \
result off-screen, needs a model or download, needs input data, needs a service or account, goal named a \
control the app lacks, unknown. Answer as JSON."""


def ask_model(row: dict[str, Any], evidence: str) -> tuple[str, str]:
    from pydantic import BaseModel

    from pickfit.meta import call_meta
    from pickfit.schema import meta_strict_schema

    class Cause(BaseModel):
        cause: str
        why: str

    body = {"instructions": ASK, "store": False,
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text":
                       f"App: {row['slug']} ({row['os']}). Feature: {row['feature']}.\n{evidence[:3000]}"}]}],
            "text": {"format": {"type": "json_schema", "name": "cause", "schema": meta_strict_schema(Cause),
                                "strict": True}}}
    result = call_meta("responses", body, stage="unchecked-causes", public_data_only=True, model="open-modal",
                       max_output_tokens=600, reasoning_effort="low", run_id="unchecked-causes",
                       output_model=Cause, cache=False)
    answer = result.parsed
    return (f"model: {answer.cause}", answer.why[:200]) if answer else ("unknown", "model answer unreadable")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--ask-model", action="store_true")
    args = ap.parse_args()
    rows = targets()
    for row in rows:
        row["cause"], row["basis"] = classify(row)
        if row["cause"] == "unknown" and args.ask_model:
            row["cause"], row["basis"] = ask_model(row, f"Agent's note: {row['note']}\nRules: {row['basis']}")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1) + "\n")
    print(f"{len(rows)} desktop features not_checked with reason other or not_shown (latest run per OS)")
    for os_name in ("linux", "macos"):
        part = [r for r in rows if r["os"] == os_name]
        print(f"\n{os_name}: {len(part)}")
        for cause, n in Counter(r["cause"] for r in part).most_common():
            print(f"  {n:4}  {cause}")
    print(f"\nruns with log_path set: {sum(bool(r['log_path']) for r in rows)} of {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
