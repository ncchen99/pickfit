"""Feature coverage: which of a tool's advertised features a verification exercised.

The extraction lists the 2-4 main features the README advertises, each with its quote. The agent
gets them numbered (F1, F2, ...) and reports, in finish, for each one: the smoke tests that
exercise it (checked), why this box cannot exercise it (not_checked, with a reason), or the check
that ran after a working install and failed (test_failed, sandbox or tool). As with the level, the
claim is an upper bound and the command log decides (resolve_features):

- checked needs a cited smoke test that passed in the log and is more than --version/--help;
  otherwise the feature is not_checked ("other", saying why);
- test_failed needs a cited command that ran after the install steps and failed (non-zero or
  unexpected exit, a timeout, or a crash in its output). A box limit at the end of its output
  (failure.output_limit) makes the failure the sandbox's, whatever the agent said; otherwise the
  agent's word stands, and without one it is the sandbox's: the tool is never blamed unasked;
- a feature finish does not mention is not_checked, not_attempted.

The fresh-box replay reruns every passing check, so a checked feature stays checked only if one of
its checks passes there too, and reruns each failed feature check once, online, so a failure is
kept only if it repeats (coverage). The record's FeatureCheck cites the run's smoke tests by
index, and the schema holds it to them: checked exactly when a cited smoke test passed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, get_args

from pydantic import BaseModel, field_validator

from pickfit.schema import SETUP_MAX, FeatureCheck, FeatureFailure, FeatureGap, FeatureStatus, SetupStep, SmokeTest

if TYPE_CHECKING:
    from pickfit.verify.agent import CommandRecord
    from pickfit.verify.replay import CheckResult, FailedRerun
    from pickfit.verify.verdict import LogVerdict

GAPS: tuple[str, ...] = get_args(FeatureGap.__value__)
# Checks that show the tool starts, not that a feature works: --version/--help, an MCP handshake alone.
NOT_FEATURE_KINDS = frozenset({"version", "mcp"})
# For an MCP server only a tool call through pickfit's probe exercises a feature (mcp.py).
MCP_FEATURE_KINDS = frozenset({"mcp_call"})
_CRASH = re.compile(r"Traceback \(most recent call last\)|panicked at|Segmentation fault|"
                    r": command not found|No module named |Error: Cannot find module")
NOTE_CHARS = 300

FINISH_FEATURES = {
    "type": "array",
    "description": (
        "One entry for every feature the task lists (F1, F2, ...). checked: command_ids are the smoke "
        "tests that exercise it (never only --version or --help). not_checked: this box cannot exercise "
        "it; set reason. test_failed: its check ran after a working install and failed; command_ids are "
        "those checks (also cited as smoke tests, with their setup_ids), and failure says whether only "
        "this box explains it (sandbox) or the tool's own error would hit a user too (tool)."),
    "items": {"type": "object", "properties": {
        "feature": {"type": "integer", "description": "Its number in the task: 1 for F1."},
        "status": {"type": "string", "enum": list(get_args(FeatureStatus.__value__))},
        "command_ids": {"type": "array", "items": {"type": "integer"}},
        "reason": {"type": ["string", "null"], "enum": [*GAPS, None], "description": (
            "not_checked: needs_account (an account or API key), needs_gpu, needs_display (a GUI or "
            "browser), needs_hardware (a microphone, camera, device), needs_service (an outside service "
            "or server pickfit does not run), needs_more_resources (too big or slow for this box, or more "
            "than one machine), needs_container (Docker or Podman), needs_root (sudo, system services), "
            "needs_toolchain (a source build with Rust, Go or a C compiler), other_os, not_attempted (the "
            "commands ran out before it), other (say why in note).")},
        "failure": {"type": ["string", "null"], "enum": [*get_args(FeatureFailure.__value__), None]},
        "note": {"type": "string", "description": "A few words: why not, or the error it showed."}},
        "required": ["feature", "status", "command_ids", "reason", "failure", "note"],
        "additionalProperties": False},
}

GUIDE = """\
Feature checks: the task lists the tool's main advertised features (F1, F2, ...). They are what the \
smoke tests are for: after one --version or --help check (not both, and not again), spend the commands \
on one check per feature, its README example as written or the smallest input that uses it; a README \
example that uses no listed feature can wait. Plan these from the README, which is free to read, not from --help runs. Let each \
check print its result to stdout (it is shown to you); do not send it to a file to read back. Write an \
input file in a run_command of its own (a heredoc that exits 0) and cite it in setup_ids of every check \
and server that reads it: a fresh box runs only the cited commands. Checks that do not depend on each \
other can go in one turn as several run_command calls. Cite every feature check as a smoke test, also \
one that failed: with expected_exit_code 0 and the expected_signal the feature should have printed, never \
with the error it showed (a failure is not a passing check). In finish, report each \
listed feature: checked, not_checked with the reason when this box cannot exercise it, or test_failed \
when its check failed after a working install. Never invent an account, an API key or an outside \
service's answer to get a feature through; that is not_checked. If commands run short, keep the install \
check and one README example first, then cover as many features as the budget allows; report the rest \
as not_attempted."""

MCP_GUIDE = """\
Feature checks for an MCP server go through pickfit's probe, never through ad-hoc commands: exercise each \
listed feature with one probe tools/call of the tool that does it (--call <tool> --args '<JSON>'), when that \
tool needs no account and changes nothing outside the box, and cite it as a smoke test with expected_signal \
"tools/call: ok". The handshake alone checks no feature. A feature whose tools all need an account, a key \
or an outside service is not_checked with that reason."""


def guide(mcp: bool = False) -> str:
    """The task's feature-check guide; an MCP server's adds how its probe exercises a feature."""
    return f"{GUIDE}\n{MCP_GUIDE}" if mcp else GUIDE


def _null_string(value: Any) -> Any:
    return None if isinstance(value, str) and value.strip().lower() in {"", "null", "none", "n/a"} else value


class FinishFeature(BaseModel):
    """One feature as finish reports it; checked against the log before it counts."""

    feature: int
    status: FeatureStatus
    command_ids: list[int] = []
    reason: FeatureGap | None = None
    failure: FeatureFailure | None = None
    note: str | None = None

    @field_validator("reason", "failure", "note", mode="before")
    @classmethod
    def _null_strings(cls, value: Any) -> Any:
        return _null_string(value)

    @field_validator("reason", mode="before")
    @classmethod
    def _known_reason(cls, value: Any) -> Any:
        return "other" if isinstance(value, str) and value not in GAPS else value


@dataclass
class ResolvedFeature:
    """What the command log supports for one listed feature, before the replay."""

    number: int
    feature: str
    status: str
    command_ids: list[int] = field(default_factory=list)  # checked: passing checks; test_failed: failed ones
    reason: str | None = None
    failure: str | None = None
    note: str | None = None
    claimed: str | None = None  # the agent's status, when it gave one
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def labels(task_features: list[Any]) -> list[str]:
    """The listed features' labels, in order (Cited values from the extraction)."""
    return [str(f.value) for f in task_features if f.value]


def render(task_features: list[Any]) -> list[str]:
    """Task lines: one per feature, with the README passage that advertises it."""
    lines = []
    for i, f in enumerate(task_features, 1):
        if f.value:
            lines.append(f'F{i}. {f.value} (README: "{_one_line(f.quote or "", 160)}")')
    return lines


def _clip(text: str | None, limit: int = NOTE_CHARS) -> str | None:
    if not text:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _one_line(text: str, limit: int) -> str:
    return _clip(text, limit) or ""


def failed_run(record: CommandRecord | Any, expected_exit_code: int = 0) -> bool:
    """A check that failed: an exit other than expected, a timeout, or a crash in its output."""
    if record.timed_out or record.exit_code is None:
        return bool(record.timed_out)
    return record.exit_code != expected_exit_code or bool(_CRASH.search(f"{record.stdout}\n{record.stderr}"))


def _box_limit(record: CommandRecord | Any) -> str | None:
    from pickfit.verify.failure import output_limit

    return output_limit(record.stdout, record.stderr, record.exit_code, record.timed_out)


def _as_gap(limit: str | None) -> str | None:
    return limit if limit in GAPS else ("other" if limit else None)


def resolve_features(names: list[str], claims: list[FinishFeature], verdict: LogVerdict,
                     commands: list[CommandRecord], *, mcp: bool = False) -> list[ResolvedFeature]:
    """Each listed feature as the command log supports it; the agent's claim is only an upper bound.

    mcp: the software is an MCP server, so only a tool call through pickfit's probe covers a feature.
    """
    by_id = {c.command_id: c for c in commands if c.command_id is not None}
    checks = {c.command_id: c for c in verdict.checks}
    after_install = max(verdict.step_ids, default=0)
    first: dict[int, FinishFeature] = {}
    for claim in claims:
        first.setdefault(claim.feature, claim)
    resolved = []
    for number, name in enumerate(names, 1):
        claim = first.get(number)
        out = ResolvedFeature(number, name, "not_checked", reason="not_attempted",
                              note="the run did not report this feature")
        if claim is None:
            resolved.append(out)
            continue
        out.claimed, out.note = claim.status, _clip(claim.note)
        if claim.status == "checked":
            passing = [cid for cid in claim.command_ids if cid in checks and checks[cid].passed
                       and checks[cid].kind not in NOT_FEATURE_KINDS
                       and (not mcp or checks[cid].kind in MCP_FEATURE_KINDS)]
            if passing:
                out.status, out.command_ids, out.reason = "checked", passing, None
            else:
                out.reason = "other"
                out.problems.append("no cited smoke test that passed exercises it ("
                                    + ("only a tool call through pickfit's probe does)" if mcp else
                                       "--version/--help and an MCP handshake do not)"))
                out.note = _clip(f"its check did not pass in the log; {claim.note or ''}")
        elif claim.status == "test_failed":
            failing = [cid for cid in claim.command_ids if cid in by_id and by_id[cid].tool == "run_command"
                       and cid > after_install and not (cid in checks and checks[cid].passed)
                       and failed_run(by_id[cid], checks[cid].expected_exit_code if cid in checks else 0)]
            if failing:
                limit = next((found for cid in failing if (found := _box_limit(by_id[cid]))), None)
                out.status, out.command_ids = "test_failed", failing
                if limit:  # the box's limit shows, whatever the agent said
                    out.failure, out.reason = "sandbox", _as_gap(limit)
                    if claim.failure == "tool":
                        out.problems.append(f"the output shows a limit of the box ({limit}), not the tool's error")
                elif claim.failure == "tool":
                    out.failure, out.reason = "tool", None
                else:  # the tool is never blamed unasked
                    out.failure = "sandbox"
                    out.reason = claim.reason if claim.reason not in (None, "not_attempted") else None
            else:
                out.reason = "other"
                out.problems.append("no cited command ran after the install and failed")
                out.note = _clip(f"no failed check in the log; {claim.note or ''}")
        else:
            out.reason = claim.reason or "other"
        resolved.append(out)
    return resolved


Fit = Callable[[str], "tuple[str, list[SetupStep]] | None"]


def _failed_smoke(again: FailedRerun, fit: Fit) -> SmokeTest | None:
    """A failed feature check as the record keeps it: the fresh box's run, with its setup."""
    from pickfit.verify.failure import error_tail

    fitted = fit(again.command)
    setup = [SetupStep(command=s.command, background=s.tool == "run_background",
                       port=s.port if s.tool == "run_background" else None)
             for s in again.setup if len(s.command) <= SETUP_MAX]
    if again.run is None or fitted is None or len(setup) < len(again.setup):
        return None
    command, before = fitted
    return SmokeTest(command=command, expected_signal="", exit_code=again.run.exit_code, passed=False,
                     observed_excerpt=_clip(error_tail(again.run.stdout, again.run.stderr, 4)),
                     setup=setup + before, offline=None)


def coverage(resolved: list[dict[str, Any]], smoke_index: dict[int, int], smoke: list[SmokeTest],
             reruns: list[FailedRerun], fit: Fit, verdicts: dict[str, tuple[str, str]] | None = None
             ) -> tuple[list[FeatureCheck], list[str]]:
    """The run's FeatureChecks from the agent's resolved features and what the fresh box showed.

    smoke_index maps a command_id to its index in `smoke` (the replay's checks, as the record keeps
    them). A failed feature check that failed again in the fresh box is appended to `smoke` as a
    failed smoke test; `fit` makes a command fit the record (or None when it cannot).
    verdicts: the feature judge's (label -> (verdict, why)); when given, a feature stays checked only
    when it says shows_it_working, and one it did not judge is not checked (not_shown).
    """
    again = {r.command_id: r for r in reruns}
    checks: list[FeatureCheck] = []
    notes: list[str] = []
    for item in resolved:
        name, status = item["feature"], item["status"]
        if status == "checked":
            held = [smoke_index[cid] for cid in item["command_ids"] if cid in smoke_index
                    and smoke[smoke_index[cid]].passed]
            if held and verdicts is not None and verdicts.get(name, ("", ""))[0] != "shows_it_working":
                why = verdicts.get(name, ("", "the feature judge gave no verdict"))[1]
                notes.append(f"feature {name!r}: the feature judge did not see it working ({why})")
                checks.append(FeatureCheck(feature=name, status="not_checked", reason="not_shown",
                                           note=_clip(f"its check passed, but the output does not show it: {why}")))
                continue
            if held:
                checks.append(FeatureCheck(feature=name, status="checked", smoke_tests=held))
                continue
            kept = any(cid in smoke_index for cid in item["command_ids"])
            why = "did not pass again in a fresh box" if kept else "is too long for the record"
            notes.append(f"feature {name!r}: its check {why}")
            checks.append(FeatureCheck(feature=name, status="not_checked", reason="other",
                                       note=f"its check passed in the agent's box but {why}"))
        elif status == "test_failed":
            held: list[int] = []
            excerpt = None
            for cid in item["command_ids"]:
                rerun = again.get(cid)
                if rerun is None or not rerun.reproduced:
                    continue
                if cid not in smoke_index:
                    test = _failed_smoke(rerun, fit)
                    if test is None:
                        continue
                    smoke_index[cid] = len(smoke)
                    smoke.append(test)
                held.append(smoke_index[cid])
                excerpt = excerpt or smoke[smoke_index[cid]].observed_excerpt
            if held:
                checks.append(FeatureCheck(feature=name, status="test_failed", smoke_tests=held,
                                           failure=item["failure"], reason=item["reason"],
                                           note=_clip(item["note"] or excerpt)))
                continue
            notes.append(f"feature {name!r}: its failed check did not fail again in the fresh box")
            checks.append(FeatureCheck(feature=name, status="not_checked", reason="other",
                                       note="its check failed in the agent's box but not again in a fresh box"))
        else:
            checks.append(FeatureCheck(feature=name, status="not_checked", reason=item["reason"] or "other",
                                       note=_clip(item["note"])))
    return checks, notes


def judge_items(resolved: list[dict[str, Any]], quotes: dict[str, str], checks: list[CheckResult]
                ) -> list[tuple[str, str, list[CheckResult]]]:
    """What the feature judge reads: each checked feature with its README quote and the replay's passing
    checks cited for it. A feature with no such check is not judged (coverage leaves it unchecked)."""
    passing = {c.command_id: c for c in checks if c.passed and c.run is not None}
    items = []
    for item in resolved:
        cited = [passing[cid] for cid in item["command_ids"] if cid in passing]
        if item["status"] == "checked" and cited:
            items.append((item["feature"], quotes.get(item["feature"], ""), cited))
    return items


def failed_ids(resolved: list[dict[str, Any]]) -> list[int]:
    """The commands of failed feature checks, for the replay to rerun once."""
    return sorted({cid for item in resolved if item["status"] == "test_failed" for cid in item["command_ids"]})
