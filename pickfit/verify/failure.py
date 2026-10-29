"""Runs that did not pass: whose fault it is, and whether the failure repeats. No model call.

- failure_limit(): a failure the box explains (a toolchain it forbids, root, a container
  engine, a GPU, its memory, disk or time) is pickfit's limit, not the software's, so the
  run becomes unverified with that reason instead of failed. The failing command's own
  output decides (output_limit); only when the log names no failing command and no check
  passed does the agent's description (box_reason).
- sandbox_only() and cited_workarounds(): a command that only works around the box (a
  shim for nvidia-smi, a fake docker) is not part of a user's install, so a run that
  cites one, as a step, a setup or a check, neither passes nor fails.
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

# What a box limit prints. The box has no compiler, Rust or Go, no root, no Docker daemon,
# 2 GiB of memory (Node's heap stops near 1 GiB) and a time limit per command.
_TOOL = r"(?:rustc|rustup|cargo|go|gcc|cc|g\+\+|c\+\+|clang|make|cmake|javac|java|mvn|gradle|dotnet|zig)"
_OUTPUT_LIMITS: list[tuple[str, re.Pattern[str]]] = [
    ("needs_container", re.compile(
        r"cannot connect to the docker daemon|docker\.sock|neither docker nor podman"
        r"|\b(?:docker|podman)\b(?::| is)? (?:command )?not (?:found|installed)|no container (?:engine|runtime)", re.I)),
    ("needs_root", re.compile(
        r"are you root\?|must be run as root|requires? root|run (?:it )?with sudo|\bsudo: |system has not been booted"
        r" with systemd|failed to connect to bus|EACCES: permission denied, \w+ '/(?:usr|etc|var|opt)/"
        r"|permission denied[^\n]{0,40}\s/(?:usr|etc|var|opt|lib)/|linux/\w+\.h: no such file|kernel headers", re.I)),
    ("needs_toolchain", re.compile(
        rf"\b{_TOOL}(?::| is)? (?:command )?not (?:found|installed)|can't find rust compiler"
        r"|command '(?:[\w-]*-)?(?:gcc|cc|g\+\+|c\+\+)' failed|unable to execute '(?:gcc|cc)'"
        rf"|(?:linker|compiler) [`'\"]?(?:cc|gcc)[`'\"]? not found|please install (?:rust|go|a c compiler|gcc)"
        r"|\b(?:rust|rustc|cargo|golang|go toolchain|go 1\.\d+)\b[^\n]{0,30}\b(?:is )?(?:required|not found|missing)",
        re.I)),
    ("needs_gpu", re.compile(
        r"libcuda\.so|cuda driver version is insufficient|no cuda-capable device|found no nvidia driver"
        r"|nvidia-smi has failed|torch\.cuda\.is_available\(\) is false|no gpu (?:found|detected|available)", re.I)),
    ("needs_more_resources", re.compile(
        r"heap out of memory|reached heap limit|cannot allocate memory|\bmemoryerror\b|out of memory"
        r"|no space left on device|disk quota exceeded|file size limit exceeded", re.I)),
]

# The same limits as an agent describes them: a need, not a mention ("needs Rust 1.91+", "no root
# to install linux-headers", "neither docker nor podman", "aborts in V8 (exit 134)").
_NEED = r"(?:no|neither|nor|without|needs?|requires?|required|absent|missing|forbidden|unavailable)"
_PROSE_LIMITS: list[tuple[str, re.Pattern[str]]] = [
    ("needs_container", re.compile(
        rf"\b{_NEED}\b[^.;]{{0,30}}\b(?:docker|podman|container (?:engine|runtime))\b"
        r"|\b(?:docker|podman)\b[^.;]{0,20}\b(?:not (?:available|installed|present)|unavailable|missing|absent)\b",
        re.I)),
    ("needs_root", re.compile(
        r"\bkernel[- ]headers\b|\blinux-headers\b|\b(?:no|without|needs?|requires?|requiring)\s+(?:root|sudo"
        r"|superuser)\b|\bas root\b|\broot (?:access|privileges?|permissions?)\b"
        rf"|\b{_NEED}\b[^.;]{{0,20}}\b(?:apt(?:-get)? install|dpkg|systemd)\b", re.I)),
    ("needs_toolchain", re.compile(
        rf"\b{_NEED}\b[^.;]{{0,25}}\b(?:rust(?:c|up)?|cargo|go(?:lang)? ?(?:1\.\d+|toolchain)|toolchain"
        r"|jdk|dotnet|\.net sdk|zig|a c compiler|gcc)\b"
        r"|\b(?:rust(?:c|up)?|cargo|golang|toolchain)\b[^.;]{0,40}\b(?:absent|missing|not (?:available|installed)"
        r"|forbidden)\b", re.I)),
    ("needs_gpu", re.compile(rf"\b{_NEED}\b[^.;]{{0,30}}\b(?:a |an )?(?:gpu|cuda|nvidia)\b", re.I)),
    ("needs_more_resources", re.compile(
        r"heap (?:limit|out of memory)|out of memory|\boom\b|\bv8\b[^.;]{0,30}\babort|abort[^.;]{0,30}\bv8\b"
        r"|no space left|disk (?:is )?full|ran out of (?:memory|disk)", re.I)),
]
# Quoted text, code spans and import errors name things; they are not the box's limits.
_MENTIONS = re.compile(r"`[^`]*`|'[^']*'|\"[^\"]*\"|(?:ModuleNotFoundError|ImportError)[^.;]*", re.I)


def box_reason(text: str | None) -> str | None:
    """The UnverifiedReason when an agent's description of a failure states a need the box cannot meet."""
    plain = _MENTIONS.sub(" ", text or "")
    return next((reason for reason, pattern in _PROSE_LIMITS if pattern.search(plain)), None)


def output_limit(output: str, exit_code: int | None, timed_out: bool) -> str | None:
    """The UnverifiedReason when a failing command's own output shows a limit of the box."""
    if timed_out or exit_code == 137:  # ran past the box's time limit, or was killed (out of memory)
        return "needs_more_resources"
    return next((reason for reason, pattern in _OUTPUT_LIMITS if pattern.search(output)), None)


def failure_limit(blocking_error: str | None, failing: CommandRecord | RanCommand | None,
                  check_passed: bool) -> str | None:
    """The box limit behind a failed claim, or None.

    The failing command's output decides when the log names one. Without one, the agent's
    description does, unless a check passed: then the tool ran, and no box limit stopped it.
    """
    if failing is not None:
        return output_limit(f"{failing.stdout}\n{failing.stderr}", failing.exit_code, failing.timed_out)
    return None if check_passed else box_reason(blocking_error)


def failed_claim_limit(verdict: dict[str, Any], commands: list[CommandRecord],
                       blocking_error: str | None) -> str | None:
    """failure_limit() for a log verdict (as a dict) and the agent's command log."""
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    fid = verdict.get("failing_id")
    passed = any(c.get("passed") for c in verdict.get("checks") or [])
    return failure_limit(blocking_error, by_id.get(fid) if fid is not None else None, passed)


# A file named like a system command, written or linked into a directory on the box's PATH.
_FAKED = r"nvidia-smi|rocm-smi|nvcc|lspci|docker|podman|sudo|systemctl|journalctl|uname|lsb_release|apt-get|apt|dpkg"
_USER_BIN = r"(?:~|\$HOME|\$\{HOME\}|/home/[^/\s'\"]+)/(?:\.local/bin|\.cargo/bin|go/bin|bin)/"
_SHIM_PATH = re.compile(rf"['\"]?{_USER_BIN}(?P<name>{_FAKED})(?=$|[\s'\";&|)])")
_WRITES = re.compile(r">|\btee\b|\bln\b|\bcp\b|\bmv\b|\binstall\b|\bchmod\b|\s-o\s|\s-O\s|--output\b")
_SANDBOX_PURPOSE = re.compile(
    rf"\b(?:sandbox|box)[- ]only\b|\bonly (?:for|in|inside) (?:the |this )?(?:sandbox|box)\b|\bgvisor\b"
    rf"|\bwork(?:s|ed|ing)?[- ]?around (?:the |this )?(?:box|sandbox)\b"
    rf"|\b(?:shim|fake|stub|mock)\b[^.;]{{0,30}}\b(?:{_FAKED})\b|\b(?:{_FAKED})\b[^.;]{{0,30}}\b(?:shim|fake|stub|mock)\b",
    re.I)


def sandbox_only(command: str, purpose: str | None = None) -> str | None:
    """Why a command only works around the box (it fakes a system command, or says so), else None."""
    shim = _SHIM_PATH.search(command)
    if shim and _WRITES.search(command):
        return f"it replaces the system command {shim.group('name')}"
    if purpose and _SANDBOX_PURPOSE.search(purpose):
        return f"its purpose says so ({' '.join(purpose.split())[:80]})"
    return None


def cited_workarounds(verdict: dict[str, Any], commands: list[CommandRecord],
                      step_purposes: dict[int, str | None] | None = None) -> list[str]:
    """Every cited command (step, check setup, check, failing command) that only works around the box."""
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    roles: dict[int, str] = {}
    for check in verdict.get("checks") or []:
        roles.setdefault(check["command_id"], "check")
        for sid in check.get("setup_ids") or []:
            roles.setdefault(sid, "setup")
    for sid in verdict.get("step_ids") or []:
        roles[sid] = "step"
    if verdict.get("failing_id") is not None:
        roles.setdefault(verdict["failing_id"], "failing command")
    found = []
    for cid, role in sorted(roles.items()):
        record = by_id.get(cid)
        cited = (step_purposes or {}).get(cid) if role == "step" else None
        purpose = " / ".join(p for p in (cited, record.purpose if record else None) if p) or None
        why = sandbox_only(record.command, purpose) if record else None
        if why:
            found.append(f"{role} {cid} only works around the box: {why}")
    return found


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
