"""Turn one verification (agent log, replay, judge) into a VerificationRun, and write it back.

The level is the weakest of three: what the agent's command log supports, what
the fresh-box replay supports, and the judge's reading of the screenshots (a
passed level needs the verdict "working"). A claim the replay or the judge does
not back becomes unverified ("other") with the reason in blocking_error, so it
is checked again instead of trusted. Steps and smoke tests are the commands as
the replay ran them; the model's own words only survive as pitfalls and the
tool version, and the version only if some output printed it.

write_back() updates data/software/<slug>.json only for a passed, replayed run:
the run replaces the earlier run on the same OS, arch and method, and the
Linux install guide becomes the replayed steps.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from pickfit.env import REPO_ROOT
from pickfit.ledger import taipei_now
from pickfit.schema import (
    COMMAND_MAX,
    Check,
    InstallGuide,
    InstallStep,
    Judge,
    Pitfall,
    RunEvidence,
    SmokeTest,
    SoftwareRecord,
    Verification,
    VerificationRun,
    best_level,
    is_passed,
)
from pickfit.verify.verdict import last_command, weaker

if TYPE_CHECKING:
    from pickfit.verify.agent import VerifyReport
    from pickfit.verify.judge import JudgeResult
    from pickfit.verify.replay import ReplayResult

DATA_DIR = REPO_ROOT / "data" / "software"

# First command of an install step -> install method (InstallMethod).
_METHOD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("uv", re.compile(r"^\s*uv\s+tool\s+install\b")),
    ("pipx", re.compile(r"^\s*pipx\s+install\b")),
    ("pip", re.compile(r"^\s*(?:python3?\s+-m\s+)?(?:pip3?|uv\s+pip)\s+install\b")),
    ("npm", re.compile(r"^\s*(?:npm\s+(?:i|install)\b|npx\b|pnpm\s+add\b|yarn\s+global\b)")),
    ("cargo", re.compile(r"^\s*cargo\s+(?:install|binstall)\b")),
    ("go", re.compile(r"^\s*go\s+install\b")),
    ("script", re.compile(r"(?:curl|wget)\b[^|]*\|\s*(?:ba|z)?sh\b")),
    ("binary", re.compile(r"(?:curl|wget)\b.*(?:releases/download|\.tar\.gz|\.tgz|\.zip|\.tar\.xz)")),
    ("source", re.compile(r"^\s*git\s+clone\b")),
]


def infer_install_method(commands: list[str], claimed: str | None = None) -> str:
    for command in commands:
        for method, pattern in _METHOD_PATTERNS:
            if pattern.search(command):
                return method
    return claimed or "other"


def _rel(path: Path | str | None) -> str | None:
    """Repo-relative path for evidence, or None when the file lives outside the repo."""
    if path is None:
        return None
    try:
        rel = Path(path).resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return None
    return rel.as_posix()


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _printed(version: str | None, outputs: list[str]) -> str | None:
    if not version:
        return None
    version = version.strip()
    return version[:60] if any(version in out for out in outputs) else None


def _record_command(command: str) -> str | None:
    """The command as the record can hold it: whole, else its last top-level command."""
    if len(command) <= COMMAND_MAX:
        return command
    last = last_command(command).strip()
    return last if 0 < len(last) <= COMMAND_MAX else None


def build_run(report: VerifyReport, replay: ReplayResult | None, judge: JudgeResult | None, *,
              evidence_dir: Path, screenshots: list[Path] | None = None,
              judge_cost_usd: float = 0.0) -> tuple[VerificationRun, list[str]]:
    """The VerificationRun for one verification, plus notes on why the level was lowered."""
    notes: list[str] = []
    verdict = report.verdict or {}
    finish = report.finish or {}
    level = verdict.get("level") or "unverified"
    reason = verdict.get("unverified_reason") if level == "unverified" else None
    if not report.verdict:
        reason = "budget_exceeded" if report.stop_reason == "budget" else "other"
        notes.append(f"the agent did not finish ({report.stop_reason}{': ' + report.error if report.error else ''})")
    blocking = finish.get("blocking_error")

    replayed = bool(replay and replay.passed)
    if is_passed(level):
        if not replayed:
            notes.append(f"replay did not pass: {replay.error if replay else 'not run'}")
            level, reason = "unverified", "other"
        else:
            level = weaker(level, replay.level)
            if judge is None or judge.verdict != "working":
                seen = f"{judge.verdict}: {judge.observed}" if judge else "no judge verdict"
                notes.append(f"the screen judge did not confirm it ({seen})")
                level, reason = "unverified", "other"
    if level == "unverified" and notes and not blocking:
        blocking = "; ".join(notes)

    by_id = {c.command_id: c for c in report.commands if c.command_id is not None}
    step_ids = verdict.get("step_ids") or []
    if replay and replay.steps:
        step_commands = [s.command for s in replay.steps]
    else:
        step_commands = [by_id[i].command for i in step_ids if i in by_id]
    steps: list[InstallStep] = []
    purposes = {s["command_id"]: s.get("purpose") for s in finish.get("steps") or []}
    for cid, command in zip(step_ids, step_commands):
        if len(command) > COMMAND_MAX:
            notes.append(f"step {cid} is longer than {COMMAND_MAX} characters")
            if is_passed(level):
                level, reason = "unverified", "other"
            continue
        steps.append(InstallStep(command=command, purpose=_clip(purposes.get(cid), 200)))

    smoke: list[SmokeTest] = []
    if replay and replay.checks:
        for c in replay.checks:
            command = _record_command(c.command)
            if command is None or c.run is None:
                continue
            smoke.append(SmokeTest(
                command=command, expected_signal=_clip(c.expected_signal, 300) or "",
                exit_code=c.run.exit_code, passed=c.passed,
                observed_excerpt=_clip(_excerpt(c.run.stdout, c.run.stderr, c.expected_signal), 300)))
    else:
        for c in verdict.get("checks") or []:
            command = _record_command(c["command"])
            if command is None:
                continue
            smoke.append(SmokeTest(command=command, expected_signal=_clip(c["expected_signal"], 300) or "",
                                   exit_code=c["exit_code"], passed=c["passed"],
                                   observed_excerpt=_clip(c.get("observed_excerpt"), 300)))
    if is_passed(level) and level != "install" and not any(t.passed for t in smoke):
        level = "install"
        notes.append("no passing smoke test fits the record")

    if level == "unverified" and reason is None:
        reason = "other"
    outputs = [f"{c.stdout}\n{c.stderr}" for c in report.commands]
    method = infer_install_method([s.command for s in steps], finish.get("install_method"))
    if level == "failed" and not blocking:
        blocking = finish.get("summary") or "not given"
    run = VerificationRun(
        id=report.run_id, level=level, unverified_reason=reason, os=report.box.get("os", "linux"),
        arch=report.box.get("arch", "x86_64"), method="sandbox", runner=report.box.get("runner"),
        image=_clip(report.box.get("image"), 120), checked_at=taipei_now(),
        tool_version=_printed(finish.get("tool_version"), outputs),
        install_method=method if steps else None, replayed=replayed, steps=steps,
        smoke_tests=smoke,
        pitfalls=[Pitfall(readme_said=_clip(p["readme_said"], 300) or "-",
                          actually_needed=_clip(p["actually_needed"], 300) or "-")
                  for p in finish.get("pitfalls") or []],
        blocking_error=_clip(blocking, 500),
        judge=Judge(verdict=judge.verdict, observed=_clip(judge.observed, 300) or "", model=judge.model)
        if judge else None,
        evidence=RunEvidence(trace_path=_rel(evidence_dir / "report.json"),
                             screenshot_paths=[p for p in map(_rel, screenshots or []) if p]),
        actor_model=report.model, cost_usd=round(report.cost_usd + judge_cost_usd, 6))
    return run, notes


def _excerpt(stdout: str, stderr: str, signal: str) -> str:
    lines = [ln.strip() for ln in f"{stdout}\n{stderr}".splitlines() if ln.strip()]
    key = " ".join(signal.split()).lower()
    for line in lines:
        if key and key in " ".join(line.split()).lower():
            return line
    return lines[-1] if lines else ""


def save_run(run: VerificationRun, evidence_dir: Path) -> Path:
    path = evidence_dir / "verification_run.json"
    path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- write-back


def install_guide(run: VerificationRun) -> InstallGuide:
    """The Linux install guide a passed, replayed run supports."""
    passing = [t for t in run.smoke_tests if t.passed and t.expected_signal]
    check = next((t for t in passing if t.exit_code == 0), passing[0] if passing else None)
    example = next((t for t in run.smoke_tests if t.passed and not re.search(r"--?(?:version|help)\b|^\S+\s+-[Vh]$",
                                                                         t.command)), None)
    return InstallGuide(
        basis="replayed", run_id=run.id, method=run.install_method or "other", steps=run.steps,
        check=Check(command=check.command, expected_signal=check.expected_signal) if check else None,
        first_task=example.command[:300] if example else None)


def write_back(run: VerificationRun, slug: str, data_dir: Path = DATA_DIR) -> tuple[bool, str]:
    """Record a passed, replayed run in data/software/<slug>.json; (written, why)."""
    if not (is_passed(run.level) and run.replayed):
        return False, f"not written: level {run.level}, replayed {run.replayed}"
    path = data_dir / f"{slug}.json"
    if not path.exists():
        return False, f"not written: {_rel(path) or path} does not exist yet"
    record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
    runs = [r for r in record.verification.runs if (r.os, r.arch, r.method) != (run.os, run.arch, run.method)]
    runs.append(run)
    level = best_level(runs)
    verification = Verification(level=level, unverified_reason=None if level != "unverified" else "other",
                                checked_at=max(r.checked_at for r in runs), runs=runs)
    data: dict[str, Any] = record.model_dump(mode="json")
    data["verification"] = verification.model_dump(mode="json")
    data["install"] = {**data["install"], run.os: install_guide(run).model_dump(mode="json")}
    data["updated_at"] = taipei_now().isoformat()
    note = "written"
    try:
        updated = SoftwareRecord.model_validate(data)
    except ValidationError as err:
        if data.get("scores") is None or "scores" not in str(err):
            raise
        data["scores"] = None  # quality caps follow the verification level: rescore later
        updated = SoftwareRecord.model_validate(data)
        note = "written; scores cleared because the verification level changed"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(updated.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return True, note
