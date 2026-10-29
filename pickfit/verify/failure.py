"""Runs that did not pass: whose fault it is, and whether the failure repeats. No model call.

- box_reason(): a failure the box explains (a toolchain it forbids, root, a container
  engine, a GPU stack) is pickfit's limit, not the software's, so the run becomes
  unverified with that reason instead of failed.
- failure_plan() and confirm_failure(): a suspected software failure is believed only
  when a fresh box (network on) runs the cited steps, then the failing command, and
  the failing command exits with the same non-zero code (or times out) again.
- WRITTEN_REASONS: the unverified reasons worth writing back to a record; "other",
  "budget_exceeded" and "not_run" say nothing about the software.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, get_args

from pickfit.schema import UnverifiedReason
from pickfit.verify.box import Box, BoxError
from pickfit.verify.replay import RanCommand, ReplayCommand, Replayer

if TYPE_CHECKING:
    from pickfit.verify.agent import CommandRecord
    from pickfit.verify.task import VerifyTask
    from pickfit.verify.verdict import LogVerdict

WRITTEN_REASONS: frozenset[str] = frozenset(get_args(UnverifiedReason.__value__)) - {
    "not_run", "budget_exceeded", "other"}

# A need near a box limit: "needs Rust 1.91+", "no root to install linux-headers", "neither docker nor podman".
_NEED = r"(?:no|not|neither|nor|without|needs?|requires?|required|absent|missing|forbidden|unavailable)"
_BOX_LIMITS: list[tuple[str, re.Pattern[str]]] = [
    ("needs_container", re.compile(
        rf"\b{_NEED}\b[^.;]{{0,40}}\b(?:docker|podman|container (?:engine|runtime))\b"
        r"|\b(?:docker|podman)\b[^.;]{0,30}\b(?:not (?:available|installed|found|present)|command not found"
        r"|unavailable|missing|absent)\b|\bno container (?:engine|runtime)\b", re.I)),
    ("needs_root", re.compile(
        r"\bsudo\b|\bapt(?:-get)? install\b|\bdpkg\b|\bkernel[- ]headers\b|\blinux-headers\b|\bsystemctl\b"
        r"|\b(?:no|without|needs?|requires?|requiring)\s+(?:root|superuser)\b|\bas root\b"
        r"|\broot (?:access|privileges?|permissions?)\b", re.I)),
    ("needs_toolchain", re.compile(
        rf"\b{_NEED}\b[^.;]{{0,25}}\b(?:rust(?:c|up)?|cargo|go(?:lang)? ?(?:1\.\d+|toolchain)|toolchain"
        r"|jdk|dotnet|\.net sdk|zig)\b"
        r"|\b(?:rust(?:c|up)?|cargo|golang|toolchain)\b[^.;]{0,40}\b(?:absent|missing|not (?:available|installed)"
        r"|forbidden)\b", re.I)),
    ("needs_gpu", re.compile(
        rf"\b{_NEED}\b[^.;]{{0,40}}\b(?:gpu|cuda|nvidia|rocm)\b|\bgpu (?:stack|driver)\b", re.I)),
]


def box_reason(text: str | None) -> str | None:
    """The UnverifiedReason when a failure's description names a limit of the box, else None."""
    for reason, pattern in _BOX_LIMITS:
        if text and pattern.search(text):
            return reason
    return None


# ---------------------------------------------------------------- confirming a failure


@dataclass(frozen=True)
class FailurePlan:
    steps: tuple[ReplayCommand, ...]  # the cited steps that ran before the failure
    setups: tuple[ReplayCommand, ...]  # what the failing check needed first
    failing: ReplayCommand
    exit_code: int | None  # as the agent saw it
    timed_out: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def failure_plan(verdict: LogVerdict, commands: list[CommandRecord]) -> FailurePlan | None:
    """What to rerun to see the failure again, or None when the log names no failing command."""
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    failing = by_id.get(verdict.failing_id) if verdict.failing_id is not None else None
    if failing is None:
        return None

    def command(cid: int) -> ReplayCommand:
        c = by_id[cid]
        return ReplayCommand(cid, c.tool, c.command, c.port, c.wait_s, c.seconds)

    fid = failing.command_id
    steps = [i for i in verdict.step_ids if i < fid]
    check = next((c for c in verdict.checks if c.command_id == fid), None)
    setups = [i for i in (check.setup_ids if check else []) if i < fid and i not in steps and i in by_id]
    return FailurePlan(steps=tuple(command(i) for i in steps), setups=tuple(command(i) for i in setups),
                       failing=command(fid), exit_code=failing.exit_code, timed_out=failing.timed_out)


@dataclass
class FailureCheck:
    reproduced: bool
    steps: list[RanCommand] = field(default_factory=list)
    failing: RanCommand | None = None
    error: str | None = None  # why it did not reproduce
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def confirm_failure(box: Box, plan: FailurePlan, task: VerifyTask, *,
                    log: Callable[[str], None] = print) -> FailureCheck:
    """Rerun the plan in one fresh, started box, with the network on. Exit codes decide."""
    began = time.monotonic()
    result = FailureCheck(reproduced=False)
    replayer = Replayer(box, log=log)
    try:
        box.set_network(True)
        box.write_file("README.md", task.readme)
        for name, content in task.files.items():
            box.write_file(name, content)
        for step in (*plan.steps, *plan.setups):
            ran = replayer.rerun(step)
            result.steps.append(ran)
            if not ran.ok:
                result.error = f"command {step.command_id} exited {ran.exit_code} before the failing command"
                break
        else:
            ran = replayer.rerun(plan.failing)
            result.failing = ran
            if plan.timed_out and ran.timed_out:
                result.reproduced = True
            elif ran.ok:
                result.error = f"command {plan.failing.command_id} passed in a fresh box"
            elif (ran.exit_code, ran.timed_out) != (plan.exit_code, plan.timed_out):
                was = "a timeout" if plan.timed_out else f"exit {plan.exit_code}"
                now = "a timeout" if ran.timed_out else f"exit {ran.exit_code}"
                result.error = f"command {plan.failing.command_id} failed differently ({now}, was {was})"
            else:
                result.reproduced = True
    except BoxError as err:
        result.error = f"box error: {err}"
    result.seconds = round(time.monotonic() - began, 1)
    said = "repeated" if result.reproduced else f"not repeated ({result.error})"
    log(f"  failure {said} · {result.seconds:.0f}s")
    return result
