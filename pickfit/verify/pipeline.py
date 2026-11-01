"""One verification end to end: agent, replay, judge, VerificationRun.

1. The agent installs and smoke-tests the tool in one box (network on).
2. The command log decides the claimed level (verdict.py).
3. If that level passed, a fresh box replays the steps online and the smoke
   tests offline, then reruns failed feature checks once (replay.py).
4. If the replay passed, the screen judge reads its outputs (judge.py); a GUI
   launch's real screenshot goes to the GUI judge, and the worse verdict wins.
   When the tool is seen working, the feature judge reads whether each checked
   feature's output shows that feature working (feature_judge.py).
   A failed claim whose failing command is the tool's own, run after every
   install step succeeded, gets a fresh box that reruns the steps and that
   command, then probes the installed package's own structure (failure.py, no
   model). That is evidence only: the pipeline never writes failed.
5. result.py turns the three into a VerificationRun, saved next to the
   agent's report; write_back() updates data/software/<slug>.json when asked.

Boxes come from a factory, so the same flow runs on DockerBox or ModalBox.
The agent and the judge share the per-run cap of the `verify:<slug>` scope.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pickfit.meta import resolve_model
from pickfit.schema import VerificationRun, is_passed
from pickfit.verify.agent import DEFAULT_MODE, AgentLimits, HistoryMode, VerifyAgent, VerifyReport, new_run_id
from pickfit.verify.box import Box, BoxError
from pickfit.verify.feature_judge import judge_features
from pickfit.verify.features import failed_ids, judge_items
from pickfit.verify.failure import (
    FailureCheck,
    cited_workarounds,
    confirm_failure,
    failure_plan,
    output_limit,
    tool_command,
)
from pickfit.verify.judge import OPEN_JUDGE_MODEL, JudgeResult, judge_checks, judge_gui, judge_model_for, merge
from pickfit.verify.mcp import is_mcp
from pickfit.verify.replay import Replayer, ReplayResult, judged_launch, plan_from
from pickfit.verify.result import DATA_DIR, build_run, save_run, write_back
from pickfit.verify.task import VerifyTask

BoxFactory = Callable[[str, str], Box]  # (run_id, role: agent, replay, confirm) -> a box not yet started


@dataclass
class Outcome:
    slug: str
    run_id: str
    run: VerificationRun
    notes: list[str]
    evidence_dir: Path
    seconds: float
    cost_usd: float
    phases: dict[str, float] = field(default_factory=dict)  # seconds per phase
    box_usd: float = 0.0  # estimated sandbox cost (Modal); model cost is cost_usd
    written: bool = False
    write_note: str | None = None

    @property
    def passed(self) -> bool:
        return is_passed(self.run.level)

    def summary(self) -> dict[str, Any]:
        r = self.run
        return {"slug": self.slug, "run_id": self.run_id, "level": r.level, "replayed": r.replayed,
                "judge": r.judge.verdict if r.judge else None, "unverified_reason": r.unverified_reason,
                "blocking_error": r.blocking_error, "seconds": self.seconds, "cost_usd": self.cost_usd,
                "box_usd": round(self.box_usd, 5),
                "phases": self.phases, "runner": r.runner, "written": self.written,
                "evidence": str(self.evidence_dir)}


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _display_name(task: VerifyTask) -> str:
    name = task.extraction.name.value if task.extraction is not None else None
    return str(name) if name else task.slug


def _kind(task: VerifyTask) -> str | None:
    return task.extraction.kind.value if task.extraction is not None else None


def _start(box: Box) -> float:
    began = time.monotonic()
    box.start()
    return round(time.monotonic() - began, 1)


def _judge_features(task: VerifyTask, report: VerifyReport, replay: ReplayResult, evidence_dir: Path, *,
                    model: str | None, run_id: str, limits: AgentLimits, log: Callable[[str], None],
                    notes: list[str], **call_kwargs: Any) -> tuple[dict[str, tuple[str, str]] | None, float]:
    """The feature judge's verdicts on the checked features, and its cost. A failed call confirms none."""
    quotes = {str(f.value): f.quote or "" for f in task.extraction.features if f.value} if task.extraction else {}
    items = judge_items(report.features, quotes, replay.checks)
    if not items:
        return None, 0.0
    try:
        judged = judge_features(_display_name(task), items, model=model, run_id=run_id, scope=f"verify:{task.slug}",
                                scope_cap_usd=limits.scope_cap_usd, log=log, **call_kwargs)
    except Exception as err:  # budget or API failure: no feature is confirmed
        notes.append(f"feature judge failed: {type(err).__name__}: {err}")
        log(f"  feature judge failed: {err}")
        return {}, 0.0
    _dump(evidence_dir / "feature_judge.json", judged.to_dict())
    return judged.verdicts, judged.cost_usd


def verify_task(task: VerifyTask, make_box: BoxFactory, *, model: str | None = None,
                mode: HistoryMode = DEFAULT_MODE, limits: AgentLimits = AgentLimits(),
                runs_dir: Path | str | None = None, log: Callable[[str], None] = print,
                write: bool = False, data_dir: Path = DATA_DIR, keep_agent_box: bool = False,
                run_id: str | None = None, **call_kwargs: Any) -> Outcome:
    """Verify one tool; returns the VerificationRun and where its evidence is."""
    began = time.monotonic()
    run_id = run_id or new_run_id(task.slug)
    phases: dict[str, float] = {}
    box = make_box(run_id, "agent")
    agent = VerifyAgent(task, box, model=model, mode=mode, limits=limits, run_id=run_id, log=log,
                        runs_dir=runs_dir, **call_kwargs)
    report: VerifyReport
    box_began = time.monotonic()
    try:
        phases["agent_box_start"] = _start(box)
        report = agent.run()
    except BoxError as err:
        report = agent.report
        report.stop_reason, report.error = "box_error", str(err)
        log(f"agent box failed: {err}")
    finally:
        if keep_agent_box:
            log(f"agent box kept: {getattr(box, 'name', box)}")
        else:
            box.close()
    phases["agent"] = report.seconds
    phases["agent_box_s"] = round(time.monotonic() - box_began, 1)  # what the sandbox is billed for
    box_usd = box.usd_per_second() * phases["agent_box_s"]
    evidence_dir = agent.runs_dir / "verify" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if report.report_path is None:  # the agent never saved (its box failed to start)
        _dump(evidence_dir / "report.json", report.to_dict())

    replay: ReplayResult | None = None
    judge: JudgeResult | None = None
    verdicts: dict[str, tuple[str, str]] | None = None  # the feature judge's, when it ran
    feature_cost = 0.0
    confirm: FailureCheck | None = None
    notes: list[str] = []
    plan_failure = None
    if agent.verdict is not None and agent.verdict.level == "failed":  # a box spent only on the tool's failure
        finish = report.finish or {}
        cited = agent.verdict.to_dict()
        purposes = {s["command_id"]: s.get("purpose") for s in finish.get("steps") or []}
        suspect, _ = tool_command(cited, report.commands)
        if suspect is not None and not cited_workarounds(cited, report.commands, purposes) and \
                not output_limit(suspect.stdout, suspect.stderr, suspect.exit_code, suspect.timed_out):
            plan_failure = failure_plan(agent.verdict, report.commands)
    if plan_failure is not None:
        confirm_box = make_box(run_id, "confirm")
        box_began = time.monotonic()
        try:
            phases["confirm_box_start"] = _start(confirm_box)
            confirm = confirm_failure(confirm_box, plan_failure, task, log=log)
        except BoxError as err:
            confirm = FailureCheck(reproduced=False, error=f"box error: {err}")
            log(f"confirm box failed: {err}")
        finally:
            confirm_box.close()
        phases["confirm"] = confirm.seconds
        phases["confirm_box_s"] = round(time.monotonic() - box_began, 1)
        box_usd += confirm_box.usd_per_second() * phases["confirm_box_s"]
        _dump(evidence_dir / "confirm.json", {"plan": plan_failure.to_dict(), "result": confirm.to_dict()})
    if agent.verdict is not None and is_passed(agent.verdict.level):
        plan = plan_from(agent.verdict, report.commands, rerun_failed=failed_ids(report.features))
        replay_box = make_box(run_id, "replay")
        box_began = time.monotonic()
        try:
            phases["replay_box_start"] = _start(replay_box)
            replay = Replayer(replay_box, log=log, evidence_dir=evidence_dir).run(plan, task)
        except BoxError as err:
            replay = ReplayResult(passed=False, level=None, offline=False, error=f"box error: {err}")
            log(f"replay box failed: {err}")
        finally:
            replay_box.close()
        phases["replay"] = replay.seconds
        phases["replay_box_s"] = round(time.monotonic() - box_began, 1)
        box_usd += replay_box.usd_per_second() * phases["replay_box_s"]
        _dump(evidence_dir / "replay.json", {"plan": plan.to_dict(), "result": replay.to_dict()})
        if replay.passed:
            judge_model = judge_model_for(model)
            judge_args = dict(model=judge_model, run_id=run_id, scope=f"verify:{task.slug}",
                              scope_cap_usd=limits.scope_cap_usd, log=log, **call_kwargs)
            try:
                parts = [judge_checks(_display_name(task), replay.checks, evidence_dir, **judge_args)]
                launched = judged_launch(replay.checks)
                if launched is not None and launched.passed:  # a window without a readable screenshot cannot pass
                    parts.append(judge_gui(_display_name(task), launched, evidence_dir, **judge_args) or JudgeResult(
                        verdict="inconclusive", observed="the GUI launch left no screenshot to judge",
                        error_text=None, matches_expected_signal=False, model=resolve_model(judge_model)))
                judge = merge([p for p in parts if p is not None])
            except Exception as err:  # budget or API failure: no verdict, so nothing passes on it
                notes.append(f"judge failed: {type(err).__name__}: {err}")
                log(f"  judge failed: {err}")
            if judge is not None:
                phases["judge"] = judge.latency_s
                _dump(evidence_dir / "judge.json", judge.to_dict())
            if judge is not None and judge.verdict == "working":
                verdicts, feature_cost = _judge_features(task, report, replay, evidence_dir, model=judge_model,
                                                         run_id=run_id, limits=limits, log=log, notes=notes,
                                                         **call_kwargs)

    judge_cost = (judge.cost_usd if judge else 0.0) + feature_cost
    run, build_notes = build_run(report, replay, judge, evidence_dir=evidence_dir,
                                 screenshots=[Path(p) for p in (judge.annotated or judge.screenshots)] if judge else [],
                                 judge_cost_usd=judge_cost, confirm=confirm,
                                 gui_app=_kind(task) == "desktop_app", mcp=is_mcp(task),
                                 feature_verdicts=verdicts)
    notes += build_notes
    save_run(run, evidence_dir)
    outcome = Outcome(slug=task.slug, run_id=run_id, run=run, notes=notes, evidence_dir=evidence_dir,
                      seconds=round(time.monotonic() - began, 1), cost_usd=run.cost_usd or 0.0, phases=phases,
                      box_usd=box_usd)
    if write:
        outcome.written, outcome.write_note = write_back(run, task.slug, data_dir)
        log(f"write-back: {outcome.write_note}")
    flags = f"replayed {run.replayed} · judge {run.judge.verdict if run.judge else '-'}"
    offline = f" · offline {replay.offline}" if replay and replay.passed else ""
    log(f"result · {task.slug} · level {run.level} · {flags}{offline} · {outcome.seconds:.0f}s · "
        f"model ${outcome.cost_usd:.4f} · box ${box_usd:.4f} · {evidence_dir / 'verification_run.json'}")
    for note in notes:
        log(f"  note: {note}")
    _dump(evidence_dir / "outcome.json", {**outcome.summary(), "notes": notes,
                                          "offline": replay.offline if replay else None})
    return outcome
