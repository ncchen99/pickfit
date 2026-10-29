"""Replay: a fresh box reruns the recorded steps, with the smoke tests offline (P3.5).

No model is involved. The plan comes from the log verdict: the cited steps and
the checks that passed, each as the exact command the agent ran. In a new box:

1. write the README and the sample files, as the agent had them;
2. run the steps in order with the network on; stop at the first failure;
3. run the checks' setup commands (input files, background servers) online;
4. cut the network and run every check: install online, smoke test offline;
5. turn the network back on and rerun any check that failed offline; one that
   passes then is marked as needing the network.

The replay passes when every step succeeds and the passing checks still
support a passed level; that level caps the run's level.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from pickfit.verify.box import Box, BoxError, ExecResult, background_script
from pickfit.verify.verdict import ResolvedCheck, evaluate_check, supported_level

if TYPE_CHECKING:
    from pickfit.verify.agent import CommandRecord
    from pickfit.verify.task import VerifyTask
    from pickfit.verify.verdict import LogVerdict

COMMAND_TIMEOUT_S = 600
BACKGROUND_WAIT_S = 90


def replay_timeout(recorded_s: float | None) -> int:
    """A rerun gets 4x the recorded time plus 30 s (at least 60 s, at most 10 minutes).

    A check that hangs with the network off (it took 0.5 s online) must not hold the
    replay for the full 10 minutes, twice.
    """
    if recorded_s is None:
        return COMMAND_TIMEOUT_S
    return int(min(COMMAND_TIMEOUT_S, max(60, recorded_s * 4 + 30)))


@dataclass(frozen=True)
class ReplayCommand:
    command_id: int
    tool: str  # run_command or run_background
    command: str
    port: int | None = None
    wait_s: int | None = None
    seconds: float | None = None  # how long it took for the agent


@dataclass(frozen=True)
class ReplayCheck:
    run: ReplayCommand
    setup_ids: tuple[int, ...]
    expected_exit_code: int
    expected_signal: str
    kind: str


@dataclass(frozen=True)
class ReplayPlan:
    steps: tuple[ReplayCommand, ...]
    setups: tuple[ReplayCommand, ...]  # setup commands that are not checks themselves, in id order
    checks: tuple[ReplayCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_from(verdict: LogVerdict, commands: list[CommandRecord]) -> ReplayPlan:
    """The steps and the passing checks of a log verdict, as commands to rerun."""
    by_id = {c.command_id: c for c in commands if c.command_id is not None}

    def command(cid: int) -> ReplayCommand:
        c = by_id[cid]
        return ReplayCommand(cid, c.tool, c.command, c.port, c.wait_s, c.seconds)

    checks = [c for c in verdict.checks if c.passed]
    check_ids = {c.command_id for c in checks}
    setup_ids = sorted({s for c in checks for s in c.setup_ids} - check_ids - set(verdict.step_ids))
    steps = set(verdict.step_ids)
    return ReplayPlan(
        steps=tuple(command(i) for i in verdict.step_ids),
        setups=tuple(command(i) for i in setup_ids),
        checks=tuple(ReplayCheck(command(c.command_id), tuple(s for s in c.setup_ids if s not in steps),
                                 c.expected_exit_code, c.expected_signal, c.kind) for c in checks))


@dataclass
class RanCommand:
    command_id: int
    command: str
    exit_code: int
    seconds: float
    timed_out: bool
    stdout: str
    stderr: str
    network: bool  # whether the network was on

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass
class CheckResult:
    command_id: int
    command: str
    kind: str
    expected_exit_code: int
    expected_signal: str
    passed: bool
    offline: bool  # passed with the network off
    run: RanCommand | None = None  # the run that decided it (offline, or the online retry)
    problems: list[str] = field(default_factory=list)
    offline_problems: list[str] = field(default_factory=list)  # why it failed offline, when retried
    setup: list[ReplayCommand] = field(default_factory=list)  # what ran first, in order


@dataclass
class ReplayResult:
    passed: bool
    level: str | None
    offline: bool  # every passing check passed with the network off
    steps: list[RanCommand] = field(default_factory=list)
    setups: list[RanCommand] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    error: str | None = None
    seconds: float = 0.0
    box: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Replayer:
    """Runs one ReplayPlan in one fresh, started Box."""

    def __init__(self, box: Box, *, log: Callable[[str], None] = print,
                 command_timeout_s: int = COMMAND_TIMEOUT_S) -> None:
        self.box = box
        self.log = log
        self.timeout = command_timeout_s

    def rerun(self, cmd: ReplayCommand) -> RanCommand:
        if cmd.tool == "run_background":
            wait = min(cmd.wait_s or 30, BACKGROUND_WAIT_S)
            result = self.box.exec(background_script(cmd.command, cmd.port, wait, f"replay-{cmd.command_id}",
                                                     detach=self.box.detach),
                                   wait + 15)
        else:
            result = self.box.exec(cmd.command, min(self.timeout, replay_timeout(cmd.seconds)))
        return self._ran(cmd, result)

    def _ran(self, cmd: ReplayCommand, result: ExecResult) -> RanCommand:
        ran = RanCommand(cmd.command_id, cmd.command, result.exit_code, result.seconds, result.timed_out,
                         result.stdout, result.stderr, self.box.network_enabled)
        status = "timed out" if ran.timed_out else f"exit {ran.exit_code}"
        net = "online" if ran.network else "offline"
        self.log(f"  replay [{cmd.command_id}] {_one_line(cmd.command)} → {status} · {ran.seconds:.1f}s · {net}")
        return ran

    def _check(self, check: ReplayCheck) -> tuple[RanCommand, bool, list[str]]:
        ran = self.rerun(check.run)
        ok, problems = evaluate_check(ran, check.expected_exit_code, check.expected_signal)
        return ran, ok, problems

    def run(self, plan: ReplayPlan, task: VerifyTask) -> ReplayResult:
        began = time.monotonic()
        result = ReplayResult(passed=False, level=None, offline=False,
                              box={"runner": self.box.runner, "image": self.box.image,
                                   "start_s": getattr(self.box, "start_s", None)})
        try:
            self._run(plan, task, result)
        except BoxError as err:
            result.passed, result.error = False, f"box error: {err}"
        result.seconds = round(time.monotonic() - began, 1)
        verdict = "passed" if result.passed else f"failed ({result.error})"
        self.log(f"  replay {verdict} · level {result.level} · offline {result.offline} · {result.seconds:.0f}s")
        return result

    def _run(self, plan: ReplayPlan, task: VerifyTask, result: ReplayResult) -> None:
        box = self.box
        box.set_network(True)
        box.write_file("README.md", task.readme)
        for name, content in task.files.items():
            box.write_file(name, content)
        if not plan.steps:
            result.error = "no steps to replay"
            return
        for step in plan.steps:
            ran = self.rerun(step)
            result.steps.append(ran)
            if not ran.ok:
                result.error = f"step {step.command_id} exited {ran.exit_code}: {_one_line(step.command)}"
                return
        for setup in plan.setups:
            ran = self.rerun(setup)
            result.setups.append(ran)
            if not ran.ok:
                result.error = f"setup {setup.command_id} exited {ran.exit_code}: {_one_line(setup.command)}"
                return
        box.set_network(False)
        known = {c.command_id: c for c in (*plan.setups, *(k.run for k in plan.checks))}
        for check in plan.checks:
            ran, ok, problems = self._check(check)
            result.checks.append(CheckResult(
                check.run.command_id, check.run.command, check.kind, check.expected_exit_code,
                check.expected_signal, passed=ok, offline=ok, run=ran, problems=problems,
                setup=[known[i] for i in check.setup_ids if i in known]))
        failed = [c for c in result.checks if not c.passed]
        if failed:
            box.set_network(True)
            by_id = {c.run.command_id: c for c in plan.checks}
            for outcome in failed:
                ran, ok, problems = self._check(by_id[outcome.command_id])
                outcome.offline_problems, outcome.problems = outcome.problems, problems
                outcome.run, outcome.passed = ran, ok
        box.set_network(True)
        background = {s.command_id for s in plan.setups if s.tool == "run_background"}
        resolved = [ResolvedCheck(
            command_id=c.command_id, command=c.command, tool="", setup_ids=[], expected_signal=c.expected_signal,
            expected_exit_code=c.expected_exit_code, exit_code=c.run.exit_code if c.run else None,
            passed=c.passed, kind=c.kind) for c in result.checks]
        serves = any(c.passed and (set(by.setup_ids) & background or by.run.tool == "run_background")
                     for c, by in zip(result.checks, plan.checks))
        result.level = supported_level(True, resolved, serves)
        result.passed = result.level is not None
        passing = [c for c in result.checks if c.passed]
        result.offline = bool(passing) and all(c.offline for c in passing)
        if not result.passed:
            result.error = "no check passed in the replay"


def _one_line(text: str, limit: int = 100) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
