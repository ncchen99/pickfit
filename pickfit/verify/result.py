"""Turn one verification (agent log, replay, judge) into a VerificationRun, and write it back.

The level is the weakest of three: what the agent's command log supports, what
the fresh-box replay supports, and the judge's reading of the screenshots (a
passed level needs the verdict "working"). A claim the replay or the judge does
not back becomes unverified ("other") with the reason in blocking_error, so it
is checked again instead of trusted. Steps and smoke tests are the commands as
the replay ran them; the model's own words only survive as pitfalls and the
tool version, and the version only if some output printed it.

The pipeline never makes a run failed; only a person's run (method human), or a
check of the published package by hand (artifact_check), can. A failed claim is
unverified: with the box limit its error shows, else "suspected_tool_fault",
with what the log, a fresh box and the structure probe found (failure.py) as
evidence in blocking_error and a failed smoke test.
A step that only works around the box (a shim) keeps a run from passing.

An MCP server's run also carries the handshake the replay's probe check saw (tool
names, server name, whether it ran offline) and the probe's notes; a passed MCP
run without one is unverified, never install.

write_back() updates data/software/<slug>.json for a passed, replayed run, or an
unverified run whose reason describes the software; never for a failed run. The
run replaces the earlier run on the same OS, arch and method, except that a run
that did not pass is never written on an OS with a passed run, nor over a failed
run, and a weaker pass never replaces a stronger one. A passed run's
steps become that OS's install guide; existing scores are refreshed for the new
runs (refresh_scores, no model call).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pickfit.env import REPO_ROOT
from pickfit.ledger import taipei_now
from pickfit.schema import (
    COMMAND_MAX,
    PASSED_LEVELS,
    SETUP_MAX,
    Check,
    InstallGuide,
    InstallStep,
    Judge,
    McpHandshake,
    Pitfall,
    RunEvidence,
    SetupStep,
    SmokeTest,
    SoftwareRecord,
    Verification,
    VerificationRun,
    best_level,
    is_passed,
)
from pickfit.score import refresh_scores
from pickfit.verify.failure import (
    WRITTEN_REASONS,
    cited_workarounds,
    error_tail,
    failure_reason,
    own_error,
    structural_defect,
    tool_command,
)
from pickfit.verify.mcp import handshake as mcp_handshake
from pickfit.verify.mcp import pitfalls as mcp_pitfalls
from pickfit.verify.mcp import probe_kind
from pickfit.verify.verdict import MCP_KINDS, split_last, unread_scripts, weaker

if TYPE_CHECKING:
    from pickfit.verify.agent import CommandRecord, VerifyReport
    from pickfit.verify.failure import FailureCheck
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


def _record_check(command: str) -> tuple[str, list[SetupStep]] | None:
    """A check as the record holds it: (command, setup that must run first), or None.

    A command over COMMAND_MAX that is `first && last` (or `;`, a newline) keeps
    `last` as the command and `first` as a setup step, which runs the same work.
    """
    if len(command) <= COMMAND_MAX:
        return command, []
    split = split_last(command)
    if split is None:
        return None
    first, last = split
    if not last or len(last) > COMMAND_MAX or len(first) > SETUP_MAX:
        return None
    return last, [SetupStep(command=first)]


def build_run(report: VerifyReport, replay: ReplayResult | None, judge: JudgeResult | None, *,
              evidence_dir: Path, screenshots: list[Path] | None = None,
              judge_cost_usd: float = 0.0, confirm: FailureCheck | None = None,
              checked_at: datetime | None = None, mcp: bool = False) -> tuple[VerificationRun, list[str]]:
    """The VerificationRun for one verification, plus notes on why the level was lowered.

    checked_at is when its last box ran; it defaults to now, right after the boxes ran.
    mcp: the software is an MCP server; its run needs the handshake from the replay.
    """
    notes: list[str] = []
    verdict = report.verdict or {}
    finish = report.finish or {}
    level = verdict.get("level") or "unverified"
    reason = verdict.get("unverified_reason") if level == "unverified" else None
    if not report.verdict:
        reason = "budget_exceeded" if report.stop_reason == "budget" else "other"
        notes.append(f"the agent did not finish ({report.stop_reason}{': ' + report.error if report.error else ''})")
    elif is_passed(verdict.get("claimed_level", "")) and not is_passed(level):
        problems = verdict.get("problems") or []
        notes.append("the command log does not support the claimed "
                     f"{verdict['claimed_level']}: {'; '.join(problems[:3]) or 'no passing check'}")
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

    evidence: CommandRecord | None = None
    # A command that only works around the box makes the run neither the tool's pass nor its failure.
    purposes = {s["command_id"]: s.get("purpose") for s in finish.get("steps") or []}
    workarounds = cited_workarounds(verdict, report.commands, purposes)
    if workarounds:
        notes += workarounds
        if is_passed(level) or level == "failed":
            level, reason = "unverified", "other"
            blocking = "; ".join([*workarounds, *([blocking] if blocking else [])])
    elif level == "failed" or verdict.get("claimed_level") == "failed":
        # The pipeline never writes failed (a person's run does): a failed claim is the box's limit when
        # the error shows one, else a suspicion, with what the log, a fresh box and the probe found.
        suspect, why_not = tool_command(verdict, report.commands)
        limit = failure_reason(verdict, report.commands, blocking)
        found: list[str] = []
        if suspect is not None:
            error, why = own_error(suspect)
            found.append(f"command {suspect.command_id} exits {suspect.exit_code}"
                         + (f" with {error}" if error else f" ({why})"))
            evidence = suspect  # kept as a failed smoke test: the command, its exit code, its error
        else:
            found.append(f"nothing checked further ({why_not})")
        if confirm is not None:
            found.append("it failed again in a fresh box" if confirm.reproduced else f"fresh box: {confirm.error}")
            defect = structural_defect(confirm.structure)
            if defect:
                found.append(f"probe: {defect}")
        level, reason = "unverified", limit or "suspected_tool_fault"
        if limit:
            notes.append(f"the box, not the software, explains the failure ({limit})")
        else:
            note = f"suspected tool fault, not proven: {'; '.join(found)}"
            notes.append(note)
            blocking = f"{note}; {blocking}" if blocking else note

    by_id = {c.command_id: c for c in report.commands if c.command_id is not None}
    step_ids = verdict.get("step_ids") or []
    if replay and replay.steps:
        step_commands = [s.command for s in replay.steps]
    else:
        step_commands = [by_id[i].command for i in step_ids if i in by_id]
    steps: list[InstallStep] = []
    in_guide: list[int] = []  # the command ids of `steps`, in order
    for cid, command in zip(step_ids, step_commands):
        if len(command) > COMMAND_MAX:
            notes.append(f"step {cid} is longer than {COMMAND_MAX} characters")
            if is_passed(level):
                level, reason = "unverified", "other"
            continue
        steps.append(InstallStep(command=command, purpose=_clip(purposes.get(cid), 200)))
        in_guide.append(cid)

    smoke: list[SmokeTest] = []
    if replay and replay.checks:
        for c in replay.checks:
            if c.run is None:
                continue
            setup = [SetupStep(command=s.command, background=s.tool == "run_background",
                               port=s.port if s.tool == "run_background" else None)
                     for s in c.setup if len(s.command) <= SETUP_MAX]
            fitted = _record_check(c.command)
            if fitted is None or len(setup) < len(c.setup):
                notes.append(f"smoke test {c.command_id} is too long for the record")
                continue
            command, before = fitted
            smoke.append(SmokeTest(
                command=command, expected_signal=_clip(c.expected_signal, 300) or "",
                exit_code=c.run.exit_code, passed=c.passed,
                observed_excerpt=_clip(_excerpt(c.run.stdout, c.run.stderr, c.expected_signal), 300),
                setup=setup + before, offline=c.offline if c.passed else None))
    else:
        for c in verdict.get("checks") or []:
            fitted = _record_check(c["command"])
            if fitted is None:
                continue
            command, before = fitted
            setup = [SetupStep(command=by_id[i].command, background=by_id[i].tool == "run_background",
                               port=by_id[i].port if by_id[i].tool == "run_background" else None)
                     for i in c["setup_ids"] if i in by_id and len(by_id[i].command) <= SETUP_MAX]
            smoke.append(SmokeTest(command=command, expected_signal=_clip(c["expected_signal"], 300) or "",
                                   exit_code=c["exit_code"], passed=c["passed"],
                                   observed_excerpt=_clip(c.get("observed_excerpt"), 300),
                                   setup=setup + before))
    failing = evidence
    fitted = _record_check(failing.command) if failing else None
    if failing and fitted and not any(t.command == fitted[0] for t in smoke):
        smoke.append(SmokeTest(command=fitted[0], expected_signal="", exit_code=failing.exit_code, passed=False,
                               observed_excerpt=_clip(error_tail(failing.stdout, failing.stderr, 4), 300),
                               setup=fitted[1]))
    if is_passed(level) and level != "install" and not any(t.passed for t in smoke):
        level = "unverified" if mcp else "install"
        reason = "other" if mcp else reason
        notes.append("no passing smoke test fits the record")
    handshake, probe_notes = _mcp_handshake(replay) if mcp else (None, [])
    if mcp and is_passed(level):
        if handshake is None:
            notes.append("no completed MCP handshake in the replay")
            level, reason = "unverified", "other"
        elif level == "service" and handshake.called_tool is None:
            level = "function"
            notes.append("no tool call passed in the replay; the handshake supports function")
    if level == "unverified" and notes and not blocking:
        blocking = "; ".join(notes)

    if level == "unverified" and reason is None:
        reason = "other"
    outputs = [f"{c.stdout}\n{c.stderr}" for c in report.commands]
    method = infer_install_method([s.command for s in steps], finish.get("install_method"))
    pitfalls = [Pitfall(readme_said=_clip(p["readme_said"], 300) or "-",
                        actually_needed=_clip(p["actually_needed"], 300) or "-", kind=p.get("kind"))
                for p in finish.get("pitfalls") or []]
    # A downloaded script the install ran, or brought in, before anything read it: a note, not a block,
    # whatever the agent's own pitfalls say. Steps are numbered as the install guide lists them.
    for unread in unread_scripts(verdict.get("step_ids") or [], report.commands):
        at = f"install step {in_guide.index(unread.step_id) + 1}" if unread.step_id in in_guide else "an install step"
        if unread.how == "piped":
            said = f"{at} runs {unread.name} straight from the network"
            needed = "the box ran it without saving or reading it first"
        elif unread.how == "ran":
            said, needed = f"{at} runs {unread.name}", f"the box ran {unread.name}, downloaded, without reading it first"
        else:
            said = f"{at} runs {unread.via}, which may run {unread.name}"
            needed = f"the box had {unread.name} downloaded beside it, and nothing read it first"
        notes.append(f"{said}: unread")
        pitfalls.append(Pitfall(readme_said=_clip(said, 300) or "-", kind="note",
                                actually_needed=f"nothing to change; a note: {needed}, so pickfit did not inspect it"))
    pitfalls += probe_notes
    run = VerificationRun(
        id=report.run_id, level=level, unverified_reason=reason, os=report.box.get("os", "linux"),
        arch=report.box.get("arch", "x86_64"), method="sandbox", runner=report.box.get("runner"),
        image=_clip(report.box.get("image"), 120), checked_at=checked_at or taipei_now(),
        tool_version=_printed(finish.get("tool_version"), outputs),
        install_method=method if steps else None, replayed=replayed, steps=steps,
        smoke_tests=smoke,
        pitfalls=pitfalls,
        blocking_error=_clip(blocking, 500),
        judge=Judge(verdict=judge.verdict, observed=_clip(judge.observed, 300) or "", model=judge.model)
        if judge else None,
        evidence=RunEvidence(trace_path=_rel(evidence_dir / "report.json"),
                             screenshot_paths=[p for p in map(_rel, screenshots or []) if p]),
        actor_model=report.model, cost_usd=round(report.cost_usd + judge_cost_usd, 6),
        mcp=handshake if is_passed(level) else None)
    return run, notes


def _mcp_handshake(replay: ReplayResult | None) -> tuple[McpHandshake | None, list[Pitfall]]:
    """The handshake the replay's best passing probe check shows (a tool call first), and the probe's notes."""
    probes = [c for c in (replay.checks if replay else []) if c.passed and c.run and c.kind in MCP_KINDS]
    probes.sort(key=lambda c: (c.kind != "mcp_call", not c.offline))
    for check in probes:
        background = [s.command for s in check.setup if s.tool == "run_background"]
        found = mcp_handshake(check.run.stdout, check.command, offline=any(c.offline for c in probes),
                              background=background)
        if found is not None:
            return found, mcp_pitfalls(check.run.stdout)
    return None, []


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
    """The Linux install guide a passed, replayed run supports.

    pickfit's MCP probe exists only in its boxes, so a probe check is never the guide's check or first
    task; an MCP server's guide points to the client config instead (the index builds it from run.mcp).
    """
    users = [t for t in run.smoke_tests if probe_kind(t.command) is None]
    passing = [t for t in users if t.passed and t.expected_signal]
    check = next((t for t in passing if t.exit_code == 0), passing[0] if passing else None)
    examples = [t for t in users
                if t.passed and not re.search(r"--?(?:version|help)\b|^\S+\s+-[Vh]$", t.command)]
    # The first task shown to users: one that also worked with the network off, if any did.
    example = next((t for t in examples if t.offline), examples[0] if examples else None)
    return InstallGuide(
        basis="replayed", run_id=run.id, method=run.install_method or "other", steps=run.steps,
        check=Check(command=check.command, expected_signal=check.expected_signal) if check else None,
        first_task=example.command[:300] if example else None)


def _unwritable(run: VerificationRun) -> str | None:
    """Why a run says nothing a record should keep, or None."""
    if run.level == "failed":
        return "the pipeline never writes failed (a person's run does)"
    if is_passed(run.level):
        return None if run.replayed else f"level {run.level}, replayed False"
    if run.unverified_reason in WRITTEN_REASONS:
        return None
    return f"unverified ({run.unverified_reason}) says nothing about the software"


def write_back(run: VerificationRun, slug: str, data_dir: Path = DATA_DIR) -> tuple[bool, str]:
    """Record a run in data/software/<slug>.json; (written, why)."""
    why = _unwritable(run)
    if why:
        return False, f"not written: {why}"
    path = data_dir / f"{slug}.json"
    if not path.exists():
        return False, f"not written: {_rel(path) or path} does not exist yet"
    record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
    if not is_passed(run.level):
        held = next((r for r in record.verification.runs if r.os == run.os and is_passed(r.level)), None)
        if held:
            return False, f"not written: {run.level} would sit beside the passed {run.os} run {held.id}"
        failed = next((r for r in record.verification.runs if (r.os, r.arch, r.method) == (run.os, run.arch, run.method)
                       and r.level == "failed"), None)
        if failed:
            return False, f"not written: {run.level} would replace the failed run {failed.id}; only a pass does"
    same = next((r for r in record.verification.runs if (r.os, r.arch, r.method) == (run.os, run.arch, run.method)
                 and is_passed(r.level)), None)
    if same and is_passed(run.level) and PASSED_LEVELS.index(run.level) > PASSED_LEVELS.index(same.level):
        return False, f"not written: {run.level} would replace the stronger {same.level} run {same.id}"
    runs = [r for r in record.verification.runs if (r.os, r.arch, r.method) != (run.os, run.arch, run.method)]
    runs.append(run)
    level = best_level(runs)
    newest = max((r for r in runs if r.level == "unverified"), key=lambda r: r.checked_at, default=None)
    verification = Verification(level=level, unverified_reason=newest.unverified_reason if level == "unverified"
                                and newest else None, checked_at=max(r.checked_at for r in runs), runs=runs)
    data: dict[str, Any] = record.model_dump(mode="json")
    data["verification"] = verification.model_dump(mode="json")
    if is_passed(run.level):
        data["install"] = {**data["install"], run.os: install_guide(run).model_dump(mode="json")}
    now = taipei_now()
    data["updated_at"] = now.isoformat()
    # The sandbox component and the quality cap follow the runs: recompute them, no model call.
    scores_note = refresh_scores(data, now)
    updated = SoftwareRecord.model_validate(data)
    note = f"written; {scores_note}" if scores_note else "written"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(updated.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return True, note
