"""Verification Coverage (cov.v1; docs/proposals/coverage.md, 念誠 11/19): how much pickfit verified, apart from quality.

Three things stay apart: the Software Quality Score (pickfit/score.py: how good the software is, from what was
verified), the known issues (security.assessment.level: what was found) and this, the coverage: what pickfit could
verify, what it could not, and why. Not verified is never a quality deduction and never a security problem.

compute_coverage(record) reads only fields the record already has (no I/O, no model call) and gives each dimension

    {status, measure, gaps, blocked_by, checked_at, harness_version}

with status verified | partial | unverified | not_applicable:

| dimension    | measures                                                          | applies to                       |
|--------------|-------------------------------------------------------------------|----------------------------------|
| install      | claimed platforms with a result (a passed run, a failed or        | every record                     |
|              | tool-fault result; one passed run stands for the others unless    |                                  |
|              | the kind is platform-specific: desktop_app, browser_extension);   |                                  |
|              | depth = the strongest passed level (R7)                           |                                  |
| function     | features listed that reached a verdict (checked, or failed with   | every record                     |
|              | the tool's own error); without a list, whether a check beyond     |                                  |
|              | --version passed; reliability n / (n + 1) (R6)                    |                                  |
| service      | an MCP server's handshake and tool call; a daemon started         | MCP servers, daemons, self-      |
|              |                                                                   | hosted web apps, service runs    |
| security     | packages checked against packages found, and the target read      | every record                     |
|              | (security.coverage_of / gaps_of; its gap codes, never redefined)  |                                  |
| docs         | the install-docs rubric was graded                                | not web_app (no README to        |
|              |                                                                   | install from)                    |
| usability    | ease.v1 was judged on a passed GUI or web run                     | desktop_app, web_app             |
| video        | a clip of pickfit operating the app was recorded                  | desktop_app, web_app             |
| repo_signals | GitHub signals read: stars, push and release dates, the file      | records with a repository        |
|              | tree, outside issues (reliability n / (n + 5) once counted, R6)   |                                  |

A dimension that could not start because an earlier one did not pass names it in `blocked_by` (function, service,
usability and video wait for install; video also for an operation) and carries no gap of its own: the earlier
dimension's gap is the reason, counted once.

Whose fault: the split in pickfit/verify/failure.py, reused as it is (fault_split()). A run the software itself
broke (suspected_tool_fault, a failed run, a feature that failed with the tool's own error) is a quality result:
the dimension is verified with that outcome, never a gap. A gap is only what pickfit could not do: the box's limits
(failure.py's output and prose limits), a platform with no host, an account or hardware it does not have, an
operation or check its harness could not finish, a step it has not taken yet. A reason failure.py says nothing
about the software for ("other", "budget_exceeded", "not_run") is a gap too, classified as below.

Gap taxonomy outside security (security's is pickfit/security.py's GAP_CODES, used as it is; a gap carries the same
fields there and here: code, category, dimension, ecosystem, platform, component, detail, capability, found,
first_seen, last_seen; GAP_CODES below has every code with its category and capability):

| category          | what pickfit lacks                                                                      |
|-------------------|-----------------------------------------------------------------------------------------|
| not_attempted     | it has not tried yet: never run, an install-only run, a feature the agent did not report  |
| sandbox_missing   | the box lacks something: root, a toolchain, a container engine, a GPU, a display, a     |
|                   | service, memory or disk                                                                  |
| no_host           | no host for the platform (macOS and Windows boxes are not routine)                       |
| needs_account     | an account, an API key or a paid plan                                                    |
| needs_hardware    | specific hardware (a microphone, a large GPU)                                            |
| harness_operation | the GUI operator could not finish, or a desktop piece is missing                         |
| check_unconfirmed | it tried, but its evidence did not hold: the fresh box's replay, the record's length    |
|                   | limit, a check the log does not show passing, the feature judge                          |
| docs_missing      | no README to grade                                                                       |
| timeout           | its time or money budget ran out                                                         |
| tool_error        | a tool or service pickfit uses failed (the GitHub API, the recorder)                      |
| unclassified      | none of these (an agent's free-text reason): to be sorted into new codes                 |

Capabilities (CAPABILITIES): each gap names the harness capability that would close it; a capability has an id, a
version (0: not built yet) with the day each version shipped, and the codes it closes. requeue() finds the records a
capability's version can now verify, and which dimension to run again.

quality_confidence() is scores.quality.confidence derived from the coverage (the share of the quality formula's
weight whose inputs were verified), so old readers keep working. The security dimension is never folded into it.

`pickfit coverage report | tasks | requeue | capabilities | show | rules` read data/software and never write it;
`report` writes a dated snapshot (runs/coverage/ by default, gitignored) for trends.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any

from pickfit import security as sec

VERSION = "cov.v1"
DIMENSIONS = ("install", "function", "service", "security", "docs", "usability", "video", "repo_signals")
STATUSES = ("verified", "partial", "unverified", "not_applicable")
PLATFORMS = ("linux", "macos", "windows", "web")
PASSED = ("inference", "service", "function", "install")  # schema.PASSED_LEVELS, strongest first
# A pass on one OS stands for the others (CLAUDE.md: CLI and MCP results on Linux match macOS and Windows), except
# for software whose interface is the platform's own.
PLATFORM_SPECIFIC_KINDS = frozenset({"desktop_app", "browser_extension"})
SERVICE_KINDS = frozenset({"mcp_server_or_agent_plugin", "server_daemon", "self_hosted_web_app"})
GUI_KINDS = frozenset({"desktop_app", "web_app"})

CATEGORIES = ("not_attempted", "sandbox_missing", "no_host", "needs_account", "needs_hardware", "harness_operation",
              "check_unconfirmed", "docs_missing", "timeout", "tool_error", "unclassified")


@dataclass(frozen=True)
class GapKind:
    dimension: str
    category: str
    capability: str  # `{platform}` is filled in from the gap
    when: str


def _k(dimension: str, category: str, capability: str, when: str) -> GapKind:
    return GapKind(dimension, category, capability, when)


# Stable codes outside security: <dimension>.<cause>. Box limits keep failure.py's and FeatureGap's names.
GAP_CODES: dict[str, GapKind] = {
    "install.not_run": _k("install", "not_attempted", "verify_backlog", "never verified, on a platform pickfit hosts"),
    "install.no_host": _k("install", "no_host", "host:{platform}", "never verified; it runs only on macOS or Windows "
                          "(or the run said macos_only, apple_silicon_only, windows_only)"),
    "install.platform_not_run": _k("install", "no_host", "host:{platform}", "a platform-specific app passed on one "
                                   "claimed platform, not run on this one"),
    "install.needs_root": _k("install", "sandbox_missing", "box_root", "the box has no root"),
    "install.needs_toolchain": _k("install", "sandbox_missing", "box_toolchain", "no compiler or language toolchain"),
    "install.needs_container": _k("install", "sandbox_missing", "box_container", "no Docker or Podman"),
    "install.needs_gpu": _k("install", "sandbox_missing", "box_gpu", "no GPU in the box"),
    "install.needs_more_resources": _k("install", "sandbox_missing", "box_resources", "memory, disk or time"),
    "install.gui_only": _k("install", "sandbox_missing", "box_display", "a GUI app the box set aside"),
    "install.model_too_large": _k("install", "needs_hardware", "box_large_gpu", "the model needs a larger machine"),
    "install.needs_account": _k("install", "needs_account", "test_accounts", "an account or key to install"),
    "install.needs_store": _k("install", "no_host", "windows_store", "only the Microsoft Store installs it"),
    "install.budget_exceeded": _k("install", "timeout", "run_budget", "the run's budget ran out"),
    "install.unclassified": _k("install", "unclassified", "triage", "the run named no cause pickfit can file"),
    "function.needs_account": _k("function", "needs_account", "test_accounts", "a feature needs an account or key"),
    "function.needs_gpu": _k("function", "sandbox_missing", "box_gpu", "a feature needs a GPU"),
    "function.needs_display": _k("function", "sandbox_missing", "box_display", "a feature needs a display"),
    "function.needs_desktop": _k("function", "harness_operation", "desktop_portal", "a desktop piece the display "
                                 "lacks: a file chooser portal, a URL handler"),
    "function.needs_hardware": _k("function", "needs_hardware", "hardware_sim", "a microphone, a camera, a device"),
    "function.needs_service": _k("function", "sandbox_missing", "service_fixtures", "a database, a model server, a "
                                 "running service"),
    "function.needs_more_resources": _k("function", "sandbox_missing", "box_resources", "memory, disk or time"),
    "function.needs_container": _k("function", "sandbox_missing", "box_container", "no Docker or Podman"),
    "function.needs_root": _k("function", "sandbox_missing", "box_root", "the box has no root"),
    "function.needs_toolchain": _k("function", "sandbox_missing", "box_toolchain", "no compiler or toolchain"),
    "function.other_os": _k("function", "no_host", "host:{platform}", "the feature is for another OS"),
    "function.operator_limit": _k("function", "harness_operation", "gui_operator", "the GUI operator ran out of "
                                  "steps, went in circles or gave up"),
    "function.check_not_met": _k("function", "harness_operation", "gui_operator", "the operator finished; pickfit's "
                                 "check did not find the result"),
    "function.app_error": _k("function", "unclassified", "triage", "the app showed no window or an error: the app "
                             "or the box, a person looks"),
    "function.install_only_run": _k("function", "not_attempted", "feature_checks", "the run was install-only"),
    "function.not_reported": _k("function", "not_attempted", "feature_checks", "the run did not try or report it"),
    "function.no_feature_check": _k("function", "not_attempted", "feature_checks", "no features listed, and no "
                                    "check beyond --version passed"),
    "function.not_shown": _k("function", "check_unconfirmed", "feature_judge", "the feature judge did not see the "
                             "output show it working"),
    "function.replay_failed": _k("function", "check_unconfirmed", "replay_stability", "its check passed in the "
                                 "agent's box, not again in a fresh box"),
    "function.check_too_long": _k("function", "check_unconfirmed", "record_long_checks", "its check is too long "
                                  "for the record"),
    "function.claim_unconfirmed": _k("function", "check_unconfirmed", "agent_checks", "the log shows no check that "
                                     "passed (or failed) as the agent said"),
    "function.sandbox_unknown": _k("function", "sandbox_missing", "triage", "its test failed because of the box, "
                                   "no limit named"),
    "function.unclassified": _k("function", "unclassified", "triage", "the agent's own reason (other)"),
    "service.no_handshake": _k("service", "not_attempted", "mcp_tool_call", "an MCP server passed without pickfit's "
                               "handshake"),
    "service.no_tool_call": _k("service", "not_attempted", "mcp_tool_call", "an MCP handshake, no tool call"),
    "service.needs_account": _k("service", "needs_account", "test_accounts", "its tools need an account or key"),
    "service.needs_service": _k("service", "sandbox_missing", "service_fixtures", "its tools need a backing service"),
    "service.not_started": _k("service", "not_attempted", "service_checks", "a service was not started and checked"),
    "security.not_run": _k("security", "not_attempted", "security_scan", "the security check never ran"),
    "security.v1_scope_unknown": _k("security", "not_attempted", "security_scan", "a sec.v1 check with findings; it "
                                    "did not say what it could not read (a sec.v2 rescan does)"),
    "docs.not_graded": _k("docs", "not_attempted", "docs_rubric", "a README, no rubric graded"),
    "docs.no_readme": _k("docs", "docs_missing", "docs_from_site", "no README among the sources"),
    "usability.not_judged": _k("usability", "not_attempted", "ease_judge", "a passed GUI or web run, no ease.v1 "
                               "judgment (usability is shown, not scored: EASE_SCORED off)"),
    "usability.first_look_only": _k("usability", "not_attempted", "ease_judge", "a first look, no operation scored"),
    "usability.stale": _k("usability", "not_attempted", "ease_judge", "judged on a run the record no longer has"),
    "usability.no_gui_run": _k("usability", "sandbox_missing", "box_display", "passed, but no GUI or browser run"),
    "video.not_recorded": _k("video", "not_attempted", "video_recording", "an operation passed, no clip recorded"),
    "repo_signals.not_scored": _k("repo_signals", "not_attempted", "score_records", "the record has no scores"),
    "repo_signals.no_snapshot": _k("repo_signals", "tool_error", "github_fetch", "no GitHub snapshot was read"),
    "repo_signals.no_file_tree": _k("repo_signals", "tool_error", "github_fetch", "no file tree in the snapshot"),
    "repo_signals.issues_not_fetched": _k("repo_signals", "tool_error", "github_fetch", "issues were not fetched"),
}
assert {k.category for k in GAP_CODES.values()} <= set(CATEGORIES)
assert not set(GAP_CODES) & set(sec.GAP_CODES)
assert all(code.startswith(kind.dimension + ".") for code, kind in GAP_CODES.items())

# The agent's reason for a feature (schema FeatureGap) as a code; operator_limit and the rest keep their names.
_FEATURE_REASONS = {r: f"function.{r}" for r in (
    "needs_account", "needs_gpu", "needs_display", "needs_desktop", "needs_hardware", "needs_service",
    "needs_more_resources", "needs_container", "needs_root", "needs_toolchain", "other_os", "operator_limit",
    "check_not_met", "app_error", "not_shown")}
# Notes pickfit's harness writes itself (verify/features.py, verify/agent.py): stable, so they can be filed.
_HARNESS_NOTES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^install-only run\b"), "function.install_only_run"),
    (re.compile(r"^the run did not report this feature"), "function.not_reported"),
    (re.compile(r"did not pass again in a fresh box"), "function.replay_failed"),
    (re.compile(r"is too long for the record"), "function.check_too_long"),
    (re.compile(r"^its check did not pass in the log|^no failed check in the log"), "function.claim_unconfirmed"),
    (re.compile(r"^its check passed, but the output does not show it"), "function.not_shown"),
]
# A run's or record's unverified reason as an install code (the box's limits keep failure.py's names).
_INSTALL_REASONS = {
    "needs_root": "install.needs_root", "needs_toolchain": "install.needs_toolchain",
    "needs_container": "install.needs_container", "needs_gpu": "install.needs_gpu",
    "needs_more_resources": "install.needs_more_resources", "gui_only": "install.gui_only",
    "model_too_large": "install.model_too_large", "needs_account": "install.needs_account",
    "needs_store": "install.needs_store", "budget_exceeded": "install.budget_exceeded",
    "macos_only": "install.no_host", "apple_silicon_only": "install.no_host", "windows_only": "install.no_host",
    "other": "install.unclassified",
}
_HOST_REASON_PLATFORM = {"macos_only": "macos", "apple_silicon_only": "macos", "windows_only": "windows"}


# failure.py's own words for the tool's fault: when no box limit shows, a failed claim is "suspected_tool_fault"
# (its docstring; pickfit/verify/result.py writes it).
SOFTWARE_FAULT = "suspected_tool_fault"


@cache
def fault_split() -> dict[str, frozenset[str]]:
    """pickfit/verify/failure.py's split of the unverified reasons, read as it is (never changed here):

    - box: the limits failure.py reads from a failing command's output or the agent's prose (output_limit,
      box_reason): pickfit's box, a gap;
    - software: the tool's own suspected fault: a quality result, never a gap;
    - placed: the other reasons failure.py writes back, about where the software runs or what it needs (macOS only,
      a GUI app, a model too large, the Store): a gap;
    - silent: the reasons failure.py says nothing about the software with (not WRITTEN_REASONS): a gap.
    Imported on first use: failure.py brings the replay and GUI modules with it."""
    from typing import get_args

    from pickfit.schema import UnverifiedReason
    from pickfit.verify import failure

    every = frozenset(get_args(UnverifiedReason.__value__))
    box = frozenset(name for name, _ in failure._OUTPUT_LIMITS) | frozenset(name for name, _ in failure._PROSE_LIMITS)
    software = frozenset({SOFTWARE_FAULT}) & failure.WRITTEN_REASONS
    placed = failure.WRITTEN_REASONS - box - software
    return {"box": box, "software": software, "placed": placed, "silent": every - failure.WRITTEN_REASONS}


# --- capabilities -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Capability:
    id: str
    versions: dict[int, str]  # version -> the day it shipped; {} or 0 alone: not built yet
    closes: tuple[str, ...]
    note: str
    issue: str | None = None  # loop/issues.md

    @property
    def version(self) -> int:
        return max(self.versions, default=0)

    def since(self, version: int | None = None) -> str | None:
        return self.versions.get(self.version if version is None else version)


def _cap(cid: str, versions: dict[int, str], closes: Iterable[str], note: str, issue: str | None = None) -> Capability:
    return Capability(cid, versions, tuple(closes), note, issue)


def _codes(capability: str) -> tuple[str, ...]:
    return tuple(c for c, k in GAP_CODES.items() if k.capability.split(":")[0] == capability)


_COVERAGE_CAPABILITIES = [
    _cap("verify_backlog", {1: "2026-10-30"}, _codes("verify_backlog"), "run the records never verified (watch, loop)"),
    _cap("host:macos", {1: "2026-11-02"}, ("install.no_host", "install.platform_not_run", "function.other_os"),
         "tart VMs on one Mac, not routine", "H-012"),
    _cap("host:windows", {1: "2026-11-17"}, ("install.no_host", "install.platform_not_run", "function.other_os"),
         "VirtualBox and EC2 Windows boxes, not routine", "H-010"),
    _cap("host", {1: "2026-10-30"}, ("function.other_os",), "a box for the platform the feature names (Linux: "
         "routine; macOS, Windows: host:macos, host:windows)"),
    _cap("windows_store", {}, _codes("windows_store"), "the Windows box is LTSC, no Store"),
    _cap("box_root", {}, _codes("box_root"), "system packages as root in the box", "H-003"),
    _cap("box_toolchain", {1: "2026-11-16"}, _codes("box_toolchain"), "the build box (pickfit verify --toolchain)",
         "H-002"),
    _cap("box_container", {}, _codes("box_container"), "a container engine in the box", "H-004"),
    _cap("box_resources", {}, _codes("box_resources"), "more memory, disk or time per command", "H-005"),
    _cap("box_gpu", {1: "2026-10-31"}, _codes("box_gpu"), "a GPU box (Tesla T4, A10)"),
    _cap("box_large_gpu", {}, _codes("box_large_gpu"), "a box for large models"),
    _cap("box_display", {1: "2026-10-31"}, _codes("box_display"), "Xvfb display boxes for GUI apps"),
    _cap("desktop_portal", {}, _codes("desktop_portal"), "file chooser portals, zenity, URL handlers", "H-007"),
    _cap("hardware_sim", {1: "2026-11-10"}, _codes("hardware_sim"), "a simulated microphone; other devices to come"),
    _cap("service_fixtures", {}, _codes("service_fixtures"), "databases and model servers a check can start"),
    _cap("test_accounts", {}, _codes("test_accounts"), "test accounts and keys pickfit may use"),
    _cap("gui_operator", {1: "2026-11-01"}, _codes("gui_operator"), "pickfit's GUI operator; a packaged computer-use "
         "operator replaces it", "H-006"),
    _cap("feature_checks", {1: "2026-11-01"}, _codes("feature_checks"), "a full run that checks each listed feature"),
    _cap("mcp_tool_call", {1: "2026-10-31"}, _codes("mcp_tool_call"), "pickfit's MCP probe with --call"),
    _cap("service_checks", {1: "2026-10-31"}, _codes("service_checks"), "background services checked in the box"),
    _cap("feature_judge", {1: "2026-11-02"}, _codes("feature_judge"), "a second call reads each checked feature"),
    _cap("replay_stability", {}, _codes("replay_stability"), "checks that hold in a fresh box"),
    _cap("record_long_checks", {}, _codes("record_long_checks"), "keep checks longer than COMMAND_MAX"),
    _cap("agent_checks", {1: "2026-11-01"}, _codes("agent_checks"), "the agent's checks, as the log shows them"),
    _cap("triage", {}, _codes("triage"), "a person (or a new code) files what the agent left as other"),
    _cap("run_budget", {1: "2026-10-30"}, _codes("run_budget"), "the run's budget"),
    _cap("security_scan", {1: "2026-11-03", 2: "2026-11-19"}, _codes("security_scan"), "pickfit security (sec.v2)"),
    _cap("docs_rubric", {1: "2026-10-29"}, _codes("docs_rubric"), "pickfit score grades the README"),
    _cap("docs_from_site", {}, _codes("docs_from_site"), "grade docs from the project's site when there is no README"),
    _cap("ease_judge", {1: "2026-11-02"}, _codes("ease_judge"), "pickfit usability (ease.v1, shown, not scored)"),
    _cap("video_recording", {1: "2026-11-12"}, _codes("video_recording"), "recorded replays cut into a clip"),
    _cap("github_fetch", {1: "2026-10-29"}, _codes("github_fetch"), "GitHub snapshots and issues"),
    _cap("score_records", {1: "2026-10-29"}, _codes("score_records"), "pickfit score"),
]


def _security_capabilities() -> list[Capability]:
    """One capability per base id in security.GAP_CODES (`adapter` for adapter:maven, adapter:nuget, ...): what
    closes each code is security.py's to say, so it is read from there, not written again."""
    by_base: dict[str, list[str]] = defaultdict(list)
    for code, (_, capability) in sec.GAP_CODES.items():
        by_base[capability.split(":")[0]].append(code)
    shipped = {"retry": {1: "2026-11-03"}}  # a clone that failed: run it again
    return [_cap(base, shipped.get(base, {}), codes, "pickfit/security.py gap taxonomy") for base, codes in
            sorted(by_base.items())]


CAPABILITIES: dict[str, Capability] = {c.id: c for c in [*_COVERAGE_CAPABILITIES, *_security_capabilities()]}
assert all(code in GAP_CODES or code in sec.GAP_CODES for c in CAPABILITIES.values() for code in c.closes)
assert {c for cap in CAPABILITIES.values() for c in cap.closes} >= set(GAP_CODES) | set(sec.GAP_CODES)


def capability_base(capability: str | None) -> str:
    return (capability or "").split(":")[0]


def registry_entry(capability: str | None) -> Capability | None:
    """The registry's entry for a gap's capability string: exact (host:macos), else its base (adapter:maven)."""
    if not capability:
        return None
    return CAPABILITIES.get(capability) or CAPABILITIES.get(capability_base(capability))


def parse_capability(spec: str) -> tuple[str, int | None]:
    """ID[@VERSION] -> (id, version or None). Refuses an id the registry does not know."""
    cid, _, version = spec.partition("@")
    if registry_entry(cid) is None:
        raise ValueError(f"unknown capability {cid!r}; `pickfit coverage capabilities` lists them")
    if version and not re.fullmatch(r"v?\d+", version):
        raise ValueError(f"a capability version is a number, e.g. {cid}@2")
    return cid, int(version.lstrip("v")) if version else None


def matches_capability(gap_capability: str | None, cid: str) -> bool:
    """A gap needs capability `cid`: the same string, or `cid` is its base (adapter matches adapter:maven)."""
    return bool(gap_capability) and (gap_capability == cid or capability_base(gap_capability) == cid)


# --- record fields ----------------------------------------------------------------------------------------------------


def _g(obj: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if obj is None:
            return default
        obj = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    return default if obj is None else obj


def _day(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()[:10]
    return str(value)[:10] or None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _passed(run: dict[str, Any]) -> bool:
    return run.get("level") in PASSED


def _strongest(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    passed = [r for r in runs if _passed(r)]
    return min(passed, key=lambda r: (PASSED.index(r["level"]), -_ts(r))) if passed else None


def _ts(run: dict[str, Any]) -> float:
    try:
        return datetime.fromisoformat(str(run.get("checked_at"))).timestamp()
    except ValueError:
        return 0.0


def _harness(run: dict[str, Any] | None) -> str | None:
    if not run:
        return None
    parts = [p for p in (run.get("runner"), run.get("image")) if p]
    return "/".join(parts)[:160] or None


def _plain(record: Any) -> dict[str, Any]:
    if isinstance(record, dict):
        return record
    return record.model_dump(mode="json")


INSTALL_ECOSYSTEM = {"npm": "npm", "pip": "pypi", "pipx": "pypi", "uv": "pypi", "cargo": "crates", "go": "go",
                     "brew": "homebrew", "binary": "binary", "docker": "docker"}
_LOCK_ECOSYSTEM = [(re.compile(r"(?:^|/)(?:package-lock\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|yarn\.lock|"
                               r"bun\.lockb?)$"), "npm"),
                   (re.compile(r"(?:^|/)Cargo\.lock$"), "crates"), (re.compile(r"(?:^|/)go\.(?:mod|sum)$"), "go"),
                   (re.compile(r"(?:^|/)(?:pyproject\.toml|uv\.lock|poetry\.lock|Pipfile\.lock|requirements[\w.-]*"
                               r"\.txt)(?: \(resolved today\))?$"), "pypi")]
_SEC_ECOSYSTEM = {"npm": "npm", "pypi": "pypi", "crates": "crates", "go": "go"}


def ecosystems_of(record: dict[str, Any]) -> list[str]:
    """The package ecosystems a record's software comes from: what its security check read (lockfiles, registry
    packages, findings, gaps) and how pickfit installed it. ["unknown"] when nothing says."""
    found: set[str] = set()
    security = record.get("security") or {}
    for source in security.get("sources") or []:
        if m := re.match(r"^(\w+):\S+", source):
            found.add(_SEC_ECOSYSTEM.get(m.group(1), m.group(1)))
            continue
        found |= {eco for pattern, eco in _LOCK_ECOSYSTEM if pattern.search(source)}
    for finding in security.get("findings") or []:
        prefix = str(finding.get("package") or "").split(":", 1)[0]
        if prefix:
            found.add(_SEC_ECOSYSTEM.get(prefix, prefix))
    for name in ((security.get("observation") or {}).get("packages") or {}):
        found.add(_SEC_ECOSYSTEM.get(name, name))
    for g in sec.gaps_of(record):
        if g.get("ecosystem") and g["ecosystem"] != "unknown":
            found.add(g["ecosystem"])
    for run in (record.get("verification") or {}).get("runs") or []:
        if eco := INSTALL_ECOSYSTEM.get(run.get("install_method") or ""):
            found.add(eco)
    return sorted(found) or ["unknown"]


def platforms_of(record: dict[str, Any]) -> list[str]:
    """The platforms a record claims: web for a hosted web app; else its platforms, else those its runs used."""
    if record.get("kind") == "web_app":
        return ["web"]
    claimed = [p for p in record.get("platforms") or [] if p in PLATFORMS]
    if claimed:
        return sorted(set(claimed), key=PLATFORMS.index)
    ran = {r.get("os") for r in (record.get("verification") or {}).get("runs") or [] if r.get("os")}
    return sorted(ran, key=PLATFORMS.index) or ["unknown"]


def _run_platform(record: dict[str, Any], run: dict[str, Any]) -> str:
    return "web" if record.get("kind") == "web_app" or run.get("web") else str(run.get("os") or "unknown")


# --- gaps -------------------------------------------------------------------------------------------------------------


def make_gap(code: str, *, platform: str | None = None, ecosystem: str = "unknown", component: str | None = None,
             detail: str = "", found: int | None = None, first_seen: str | None = None,
             last_seen: str | None = None) -> dict[str, Any]:
    """A gap outside security, with the same fields as security.gap() plus dimension and platform."""
    kind = GAP_CODES[code]
    capability = kind.capability.format(platform=platform or "unknown")
    return {"code": code, "category": kind.category, "dimension": kind.dimension, "ecosystem": ecosystem,
            "platform": platform, "component": component, "detail": " ".join(str(detail).split())[:300],
            "capability": capability, "found": found, "first_seen": first_seen, "last_seen": last_seen or first_seen}


def _security_gap(g: dict[str, Any]) -> dict[str, Any]:
    """A gap from pickfit/security.py, as it is, with the dimension and platform fields every gap has here."""
    out = {k: g.get(k) for k in ("code", "category", "ecosystem", "component", "detail", "capability", "found",
                                 "first_seen", "last_seen")}
    if not out.get("capability") and g.get("code") in sec.GAP_CODES:  # a dry run's gap may carry only the code
        out["capability"] = sec.gap(g["code"], g.get("ecosystem") or "unknown", detail=g.get("detail") or "")[
            "capability"]
        out["category"] = out.get("category") or sec.GAP_CODES[g["code"]][0]
    return out | {"dimension": "security", "platform": None, "ecosystem": out.get("ecosystem") or "unknown",
                  "detail": out.get("detail") or ""}


def _merge(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One gap per (code, platform, component): the earliest first_seen, the latest last_seen."""
    out: dict[tuple[Any, ...], dict[str, Any]] = {}
    for g in gaps:
        key = (g["code"], g.get("platform"), g.get("component"))
        if key not in out:
            out[key] = dict(g)
            continue
        kept = out[key]
        days = [d for d in (kept.get("first_seen"), g.get("first_seen")) if d]
        kept["first_seen"] = min(days) if days else None
        days = [d for d in (kept.get("last_seen"), g.get("last_seen")) if d]
        kept["last_seen"] = max(days) if days else None
    return list(out.values())


def feature_gap_code(feature: dict[str, Any]) -> str | None:
    """The gap a feature that reached no verdict stands for; None for checked or failed with the tool's own error
    (a quality result). A harness note decides first: the agent's reason is vaguer than what pickfit wrote."""
    status, reason, failure = feature.get("status"), feature.get("reason"), feature.get("failure")
    if status == "checked" or (status == "test_failed" and failure == "tool"):
        return None
    note = str(feature.get("note") or "")
    if reason in (None, "other", "not_attempted"):
        for pattern, code in _HARNESS_NOTES:
            if pattern.search(note):
                return code
    if status == "test_failed":  # failure sandbox: the box's limit, when named
        return _FEATURE_REASONS.get(reason or "", "function.sandbox_unknown")
    if reason == "not_attempted":
        return "function.not_reported"
    return _FEATURE_REASONS.get(reason or "", "function.unclassified")


# --- dimensions -------------------------------------------------------------------------------------------------------


def _dimension(status: str, measure: dict[str, Any] | None = None, gaps: list[dict[str, Any]] | None = None, *,
               blocked_by: str | None = None, checked_at: Any = None, harness_version: str | None = None
               ) -> dict[str, Any]:
    return {"status": status, "measure": measure or {}, "gaps": _merge(gaps or []), "blocked_by": blocked_by,
            "checked_at": _iso(checked_at), "harness_version": harness_version}


def _ratio(done: int, of: int | None, unit: str, **extra: Any) -> dict[str, Any]:
    share = None if not of else round(done / of, 4)
    return {"done": done, "of": of, "unit": unit, "share": share, **extra}


def _status_of(done: int, of: int | None) -> str:
    if of is None:
        return "partial" if done else "unverified"
    if of == 0:
        return "unverified"
    return "verified" if done >= of else "partial" if done else "unverified"


def _install(record: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    verification = record.get("verification") or {}
    claimed = platforms_of(record)
    specific = record.get("kind") in PLATFORM_SPECIFIC_KINDS
    split = fault_split()
    result: dict[str, str] = {}
    tried: set[str] = set()
    gaps: list[dict[str, Any]] = []
    for run in runs:
        where = _run_platform(record, run)
        day = _day(run.get("checked_at"))
        level, reason = run.get("level"), run.get("unverified_reason")
        if level in PASSED:
            result[where] = "verified"
        elif level == "failed":
            result.setdefault(where, "failed")
        elif reason in split["software"]:
            result.setdefault(where, "tool_fault")
        else:
            code = _INSTALL_REASONS.get(reason or "", "install.unclassified")
            platform = _HOST_REASON_PLATFORM.get(reason or "", where)
            gaps.append(make_gap(code, platform=platform,
                                 ecosystem=INSTALL_ECOSYSTEM.get(run.get("install_method") or "", "unknown"),
                                 component=run.get("id"), detail=run.get("blocking_error") or reason or "",
                                 first_seen=day))
            tried.add(where)
    passed_somewhere = "verified" in result.values()
    resulted = bool(result)  # a pass, or the software's own failure: a result that stands for the other platforms
    by_platform: dict[str, str] = {}
    for platform in claimed:
        if platform in result:
            by_platform[platform] = result[platform]
        elif resulted and not specific:
            by_platform[platform] = "proxy"
        else:
            by_platform[platform] = "unverified" if platform in tried else "not_run"
    if resulted and specific:
        day = _day(verification.get("checked_at"))
        gaps += [make_gap("install.platform_not_run", platform=p, component=p, first_seen=day,
                          detail="result on " + ", ".join(f"{k} ({v})" for k, v in sorted(result.items())))
                 for p, v in by_platform.items() if v == "not_run" and p != "unknown"]
    if not runs:
        reason = verification.get("unverified_reason") or "not_run"
        day = _day(record.get("updated_at") or record.get("first_seen_at"))
        first = _day(record.get("first_seen_at")) or day
        if reason == "not_run":
            hostable = [p for p in claimed if p in ("linux", "web", "unknown")]
            if hostable:
                gaps.append(make_gap("install.not_run", platform=hostable[0], first_seen=first, last_seen=day,
                                     detail="never verified"))
            else:
                gaps += [make_gap("install.no_host", platform=p, component=p, first_seen=first, last_seen=day,
                                  detail=f"claims only {', '.join(claimed)}") for p in claimed]
        elif reason in split["software"]:
            by_platform = {p: "tool_fault" for p in claimed}
        else:
            code = _INSTALL_REASONS.get(reason, "install.unclassified")
            gaps.append(make_gap(code, platform=_HOST_REASON_PLATFORM.get(reason, claimed[0]), first_seen=first,
                                 last_seen=day, detail=reason))
    results = {"verified", "proxy", "failed", "tool_fault"}
    done = sum(1 for v in by_platform.values() if v in results)
    strongest = _strongest(runs)
    outcome = ("passed" if passed_somewhere else "failed" if "failed" in result.values() or
               verification.get("level") == "failed" else "tool_fault" if "tool_fault" in by_platform.values()
               else None)
    measure = _ratio(done, len(by_platform), "platform", outcome=outcome,
                     depth=strongest["level"] if strongest else None, by_platform=by_platform)
    latest = max(runs, key=_ts) if runs else None
    return _dimension(_status_of(done, len(by_platform)), measure, gaps, checked_at=verification.get("checked_at"),
                      harness_version=_harness(strongest or latest))


def _features(passed: list[dict[str, Any]]) -> tuple[list[str], set[str], set[str], dict[str, dict[str, Any]]]:
    """Over the passed runs (feature_score's view): the labels in order, those checked, those that failed with the
    tool's own error, and for each label the entry of the strongest run that has it."""
    order: list[str] = []
    checked: set[str] = set()
    broken: set[str] = set()
    best: dict[str, dict[str, Any]] = {}
    for run in sorted(passed, key=lambda r: (PASSED.index(r["level"]), -_ts(r))):
        for f in run.get("features") or []:
            name = f["feature"]
            if name not in order:
                order.append(name)
            if f.get("status") == "checked":
                checked.add(name)
            elif f.get("status") == "test_failed" and f.get("failure") == "tool":
                broken.add(name)
            best.setdefault(name, f | {"_run": run})
    return order, checked, broken, best


def _function(record: dict[str, Any], runs: list[dict[str, Any]], install: dict[str, Any]) -> dict[str, Any]:
    passed = [r for r in runs if _passed(r)]
    strongest = _strongest(runs)
    if not passed:
        return _dimension("unverified", _ratio(0, len(record.get("features") or []) or 1, "feature", depth=None),
                          blocked_by="install", checked_at=install["checked_at"])
    order, checked, broken, best = _features(passed)
    depth = strongest["level"]
    if not order:  # no list: did a check beyond --version pass (R7's depth)?
        done = int(depth != "install")
        gaps = [] if done else [make_gap("function.no_feature_check", platform=_run_platform(record, strongest),
                                         component=strongest.get("id"), first_seen=_day(strongest.get("checked_at")),
                                         detail="only an install check passed")]
        return _dimension(_status_of(done, 1), _ratio(done, 1, "check", depth=depth, judged=0, reliability=None),
                          gaps, checked_at=strongest.get("checked_at"), harness_version=_harness(strongest))
    judged = checked | broken
    gaps = []
    for name in order:
        if name in judged:
            continue
        f = best[name]
        code = feature_gap_code(f) or "function.unclassified"
        run = f["_run"]
        # other_os: the feature is for an OS other than the run's, which the record does not name.
        platform = None if code == "function.other_os" else _run_platform(record, run)
        gaps.append(make_gap(code, platform=platform, component=name,
                             ecosystem=INSTALL_ECOSYSTEM.get(run.get("install_method") or "", "unknown"),
                             detail=f.get("note") or f.get("reason") or "", first_seen=_day(run.get("checked_at"))))
    n = len(judged)
    measure = _ratio(n, len(order), "feature", depth=depth, judged=n, checked=len(checked), failed_by_tool=len(broken),
                     reliability=round(n / (n + 1), 4))
    latest = max(passed, key=_ts)
    return _dimension(_status_of(n, len(order)), measure, gaps, checked_at=latest.get("checked_at"),
                      harness_version=_harness(strongest))


def _is_mcp(record: dict[str, Any], runs: list[dict[str, Any]]) -> bool:
    return bool(record.get("mcp")) or record.get("kind") == "mcp_server_or_agent_plugin" or any(
        r.get("mcp") for r in runs)


def _service(record: dict[str, Any], runs: list[dict[str, Any]], install: dict[str, Any]) -> dict[str, Any]:
    mcp = _is_mcp(record, runs)
    service_run = any(r.get("level") in ("service", "inference") for r in runs)
    if not (mcp or record.get("kind") in SERVICE_KINDS or service_run):
        return _dimension("not_applicable")
    passed = [r for r in runs if _passed(r)]
    if not passed:
        return _dimension("unverified", _ratio(0, 2 if mcp else 1, "step"), blocked_by="install",
                          checked_at=install["checked_at"])
    strongest = _strongest(runs)
    reasons = Counter(f.get("reason") for r in passed for f in r.get("features") or [] if f.get("status") != "checked")
    platform = _run_platform(record, strongest)
    day = _day(strongest.get("checked_at"))
    gaps: list[dict[str, Any]] = []
    if mcp:
        handshake = any(r.get("mcp") for r in passed)
        call = any(_g(r, "mcp", "called_tool") for r in passed)
        done = int(handshake) + int(call)
        if not handshake:
            gaps.append(make_gap("service.no_handshake", platform=platform, component=strongest.get("id"),
                                 first_seen=day, detail=f"passed at {strongest['level']} without pickfit's probe"))
        elif not call:
            code = ("service.needs_account" if reasons.get("needs_account") else
                    "service.needs_service" if reasons.get("needs_service") else "service.no_tool_call")
            gaps.append(make_gap(code, platform=platform, component=strongest.get("id"), first_seen=day,
                                 detail="handshake only"))
        measure = _ratio(done, 2, "step", handshake=handshake, tool_call=call, depth=strongest["level"])
        return _dimension(_status_of(done, 2), measure, gaps, checked_at=strongest.get("checked_at"),
                          harness_version=_harness(strongest))
    done = int(strongest["level"] in ("service", "inference"))
    if not done:
        code = "service.needs_service" if reasons.get("needs_service") else "service.not_started"
        gaps.append(make_gap(code, platform=platform, component=strongest.get("id"), first_seen=day,
                             detail=f"strongest run: {strongest['level']}"))
    return _dimension(_status_of(done, 1), _ratio(done, 1, "step", depth=strongest["level"]), gaps,
                      checked_at=strongest.get("checked_at"), harness_version=_harness(strongest))


def _security(record: dict[str, Any]) -> dict[str, Any]:
    check = record.get("security")
    if check is None:
        return _dimension("unverified", _ratio(0, None, "package"),
                          [make_gap("security.not_run", first_seen=_day(record.get("updated_at")))])
    state = sec.coverage_of(record)
    gaps = [_security_gap(g) for g in sec.gaps_of(record)]
    coverage = check.get("coverage")
    version = "/".join(p for p in (check.get("version"), _g(check, "assessment", "policy_version")) if p) or None
    if coverage is not None:
        measure = _ratio(int(coverage.get("packages_checked") or 0), int(coverage.get("packages_found") or 0),
                         "package", target=coverage.get("target"))
    else:  # sec.v1: what a fresh install brought; what it skipped was not recorded
        checked = int(check.get("packages_checked") or 0)
        measure = _ratio(checked, checked if state == "complete" else None, "package", target="fresh_install")
        if state == "partial" and not gaps:
            gaps = [make_gap("security.v1_scope_unknown", first_seen=_day(check.get("checked_at")),
                             detail="sec.v1 found advisories; what it could not read was not recorded")]
    status = {"complete": "verified", "partial": "partial", "unchecked": "unverified"}[state]
    if status == "verified" and measure["share"] is None:
        measure["share"] = 1.0
    return _dimension(status, measure, gaps, checked_at=check.get("checked_at"), harness_version=version)


def _docs(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("kind") == "web_app":
        return _dimension("not_applicable")
    rubric = _g(record, "scores", "docs_rubric")
    if rubric:
        version = rubric.get("prompt_version") or f"model:{rubric.get('model')}"
        return _dimension("verified", _ratio(1, 1, "rubric", model=rubric.get("model")), checked_at=rubric.get(
            "checked_at"), harness_version=version)
    has_readme = any(s.get("kind") == "readme" for s in record.get("sources") or [])
    code = "docs.not_graded" if has_readme else "docs.no_readme"
    return _dimension("unverified", _ratio(0, 1, "rubric"),
                      [make_gap(code, component="README", first_seen=_day(record.get("updated_at")))])


def _operated(run: dict[str, Any]) -> bool:
    return bool(_g(run, "gui", "operations") or _g(run, "web", "operations"))


def _usability(record: dict[str, Any], runs: list[dict[str, Any]], install: dict[str, Any]) -> dict[str, Any]:
    if record.get("kind") not in GUI_KINDS:
        return _dimension("not_applicable")
    passed = [r for r in runs if _passed(r)]
    if not passed:
        return _dimension("unverified", _ratio(0, 1, "judgment"), blocked_by="install",
                          checked_at=install["checked_at"])
    screen = [r for r in passed if r.get("gui") or r.get("web")]
    day = _day(record.get("updated_at"))
    if not screen:
        return _dimension("unverified", _ratio(0, 1, "judgment"),
                          [make_gap("usability.no_gui_run", platform=_run_platform(record, passed[0]),
                                    first_seen=_day(passed[0].get("checked_at")), detail="no GUI or browser run")])
    usability = record.get("usability")
    if not usability:
        return _dimension("unverified", _ratio(0, 1, "judgment"),
                          [make_gap("usability.not_judged", platform=_run_platform(record, screen[0]),
                                    component=screen[0].get("id"), first_seen=day)])
    current = usability.get("run_id") in {r.get("id") for r in screen}
    if not current:
        code = "usability.stale"
    elif usability.get("score") is None:
        code = "usability.first_look_only"
    else:
        return _dimension("verified", _ratio(1, 1, "judgment", score=usability.get("score")),
                          checked_at=usability.get("checked_at"),
                          harness_version="/".join(p for p in (usability.get("version"),
                                                               usability.get("prompt_version")) if p))
    return _dimension("partial" if current else "unverified", _ratio(0, 1, "judgment"),
                      [make_gap(code, component=usability.get("run_id"), first_seen=_day(usability.get("checked_at")))],
                      checked_at=usability.get("checked_at"), harness_version=usability.get("version"))


def _video(record: dict[str, Any], runs: list[dict[str, Any]], install: dict[str, Any]) -> dict[str, Any]:
    if record.get("kind") not in GUI_KINDS:
        return _dimension("not_applicable")
    passed = [r for r in runs if _passed(r)]
    if not passed:
        return _dimension("unverified", _ratio(0, 1, "clip"), blocked_by="install", checked_at=install["checked_at"])
    recorded = [r for r in runs if r.get("video")]
    operated = [r for r in passed if _operated(r)]
    if recorded:
        clip = recorded[0]["video"]
        return _dimension("verified", _ratio(len(recorded), max(len(recorded), len(operated)), "clip"),
                          checked_at=clip.get("recorded_at"), harness_version=clip.get("model"))
    if not operated:
        return _dimension("unverified", _ratio(0, 1, "clip"), blocked_by="function",
                          checked_at=install["checked_at"])
    run = operated[0]
    return _dimension("unverified", _ratio(0, len(operated), "clip"),
                      [make_gap("video.not_recorded", platform=_run_platform(record, run), component=run.get("id"),
                                first_seen=_day(run.get("checked_at")))])


REPO_PARTS = ("popularity", "maintenance", "engineering_hygiene", "responsiveness")
ISSUE_PSEUDO_COUNT = 5  # R6: responsiveness on n outside issues is trusted n / (n + 5)
ISSUES_UNKNOWN = 2  # a responsiveness kept from before scores.inputs rests on 2 or more issues; how many is unknown


def _outside_issues(issues: dict[str, Any], as_of: Any) -> int | None:
    """Outside issues responsiveness judged, from stored inputs (scores.inputs, which comes with the scoring patch):
    pickfit/score.py's own rule, imported late; None when it is not there."""
    from pickfit import score

    detail, shape = getattr(score, "responsiveness_detail", None), getattr(score, "_issue_items", None)
    if detail is None or shape is None or not as_of:
        return None
    try:
        return detail(shape(issues), datetime.fromisoformat(str(as_of).replace("Z", "+00:00")))[1]
    except (TypeError, ValueError):
        return None


def _responsiveness_part(score: float | None, inputs: dict[str, Any]) -> str:
    """measured; thin (read, fewer than 2 outside issues: the repository has little to say); missing (not fetched).
    Scores from before scores.inputs (or kept from them as inputs.legacy) cannot tell thin from not fetched: thin."""
    if score is not None:
        return "measured"
    if not inputs or inputs.get("legacy") or inputs.get("issues") is not None:
        return "thin"
    return "missing"


def _repo_signals(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("repo") is None:
        return _dimension("not_applicable")
    scores = record.get("scores")
    if not scores:
        return _dimension("unverified", _ratio(0, len(REPO_PARTS), "signal"),
                          [make_gap("repo_signals.not_scored", first_seen=_day(record.get("updated_at")))])
    comps = _g(scores, "quality", "components") or {}
    web = record.get("kind") == "web_app"
    inputs = scores.get("inputs") or {}
    github, issues = inputs.get("github"), inputs.get("issues")
    day = _day(scores.get("computed_at"))
    stars = _g(scores, "popularity", "signals", "stars")
    parts: dict[str, str] = {"popularity": "measured" if stars is not None else "missing"}
    gaps: list[dict[str, Any]] = []
    reliability: dict[str, float] = {}
    if not web:
        for name in ("maintenance", "engineering_hygiene"):
            parts[name] = "measured" if _g(comps, name, "score") is not None else "missing"
        resp = _g(comps, "responsiveness", "score")
        parts["responsiveness"] = _responsiveness_part(resp, inputs)
        n = _outside_issues(issues, (github or issues or {}).get("fetched_at")) if issues else None
        n = n if n is not None else (ISSUES_UNKNOWN if resp is not None else 0)
        reliability["responsiveness"] = round(n / (n + ISSUE_PSEUDO_COUNT), 4)
        if parts["maintenance"] == "missing" and parts["engineering_hygiene"] == "missing":
            gaps.append(make_gap("repo_signals.no_snapshot", component="github", first_seen=day))
        elif parts["engineering_hygiene"] == "missing":
            gaps.append(make_gap("repo_signals.no_file_tree", component="github", first_seen=day))
        if parts["responsiveness"] == "missing":
            gaps.append(make_gap("repo_signals.issues_not_fetched", component="issues", first_seen=day))
    if parts["popularity"] == "missing" and not gaps:
        gaps.append(make_gap("repo_signals.no_snapshot", component="github", first_seen=day))
    done = sum(1 for v in parts.values() if v in ("measured", "thin"))
    version = "/".join(p for p in (scores.get("formula_version"), inputs.get("version")) if p)
    measure = _ratio(done, len(parts), "signal", parts=parts, reliability=reliability or None)
    when = (github or {}).get("fetched_at") or scores.get("computed_at")
    return _dimension(_status_of(done, len(parts)), measure, gaps, checked_at=when, harness_version=version)


def compute_coverage(record: Any) -> dict[str, Any]:
    """The record's coverage (cov.v1), from its own fields only. Pure: no I/O, no model call."""
    data = _plain(record)
    runs = list((data.get("verification") or {}).get("runs") or [])
    install = _install(data, runs)
    dims = {
        "install": install,
        "function": _function(data, runs, install),
        "service": _service(data, runs, install),
        "security": _security(data),
        "docs": _docs(data),
        "usability": _usability(data, runs, install),
        "video": _video(data, runs, install),
        "repo_signals": _repo_signals(data),
    }
    return {"version": VERSION, "slug": data.get("slug"), "category": data.get("category"), "kind": data.get("kind"),
            "platforms": platforms_of(data), "ecosystems": ecosystems_of(data), "dimensions": dims,
            "summary": summarize(dims)}


def dimension_share(dim: dict[str, Any]) -> float | None:
    """0-1 for an applicable dimension: verified 1, unverified 0, partial its measure (0.5 when it has none)."""
    status = dim["status"]
    if status == "not_applicable":
        return None
    if status == "verified":
        return 1.0
    if status == "unverified":
        return 0.0
    share = (dim.get("measure") or {}).get("share")
    return 0.5 if share is None else float(share)


def summarize(dims: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """What pickfit verified, in one line a page can show: the mean share over applicable dimensions, with counts."""
    shares = [s for d in dims.values() if (s := dimension_share(d)) is not None]
    counts = Counter(d["status"] for d in dims.values())
    codes = sorted({g["code"] for d in dims.values() for g in d["gaps"]})
    return {"verified_share": round(sum(shares) / len(shares), 4) if shares else None,
            **{s: counts.get(s, 0) for s in STATUSES}, "gap_codes": codes}


def gaps_in(coverage: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for dim in coverage["dimensions"].values():
        yield from dim["gaps"]


# --- quality.confidence, from the coverage ----------------------------------------------------------------------------


def quality_inputs(coverage: dict[str, Any], usage_reports: int = 0, usage_min: int = 3) -> dict[str, bool]:
    """Which quality components rest on something pickfit verified (or, usage_outcomes, people reported): the
    sandbox run had a result the formula reads (passed, or failed by a person's run), features reached a verdict, the
    rubric was graded, the repository's signals were measured, the browser run passed, usability was judged."""
    dims = coverage["dimensions"]
    install, function, repo = dims["install"]["measure"], dims["function"]["measure"], dims["repo_signals"]["measure"]
    parts = repo.get("parts") or {}
    passed = install.get("outcome") == "passed"
    return {
        "sandbox_verification": install.get("outcome") in ("passed", "failed"),
        "feature_results": bool(function.get("judged")),
        "install_docs": dims["docs"]["status"] == "verified",
        "maintenance": parts.get("maintenance") == "measured",
        "engineering_hygiene": parts.get("engineering_hygiene") == "measured",
        "responsiveness": parts.get("responsiveness") == "measured",
        "usage_outcomes": usage_reports >= usage_min,
        "browser_facts": passed and coverage.get("kind") == "web_app",
        "usability": dims["usability"]["status"] == "verified",
    }


def quality_confidence(coverage: dict[str, Any], weights: dict[str, float], usage_reports: int = 0) -> float:
    """scores.quality.confidence from the coverage: the share of the quality formula's weight (`weights`, the weights
    the formula applied, components with weight 0 left out) whose inputs were verified. The security dimension is
    never in it: what a scan could not read says nothing about how good the software is."""
    inputs = quality_inputs(coverage, usage_reports)
    return round(sum(w for name, w in weights.items() if w > 0 and inputs.get(name)) / 100, 2)


# --- over many records: report, tasks, requeue ------------------------------------------------------------------------


def load_records(data_dir: Path, status: str | None = "listed") -> list[dict[str, Any]]:
    out = []
    for path in sorted(Path(data_dir).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if status is None or raw.get("status") == status:
            out.append(raw)
    return out


def coverages(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [compute_coverage(r) for r in records]


def _group_rows(covs: list[dict[str, Any]], key: Callable[[dict[str, Any]], Iterable[str]]
                ) -> dict[str, dict[str, Any]]:
    """Per group: records, mean verified share, and each dimension's status counts."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cov in covs:
        for name in key(cov):
            groups[name].append(cov)
    out: dict[str, dict[str, Any]] = {}
    for name, members in groups.items():
        shares = [c["summary"]["verified_share"] for c in members if c["summary"]["verified_share"] is not None]
        dims = {d: dict(Counter(c["dimensions"][d]["status"] for c in members)) for d in DIMENSIONS}
        out[name] = {"records": len(members), "verified_share": round(sum(shares) / len(shares), 4) if shares else None,
                     "dimensions": dims}
    return dict(sorted(out.items(), key=lambda kv: (-kv[1]["records"], kv[0])))


def blocked_by_code(covs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per gap code: the records it blocks (a record counts once per code), with where it hits."""
    rows: dict[str, dict[str, Any]] = {}
    for cov in covs:
        seen: dict[str, dict[str, Any]] = {}
        for g in gaps_in(cov):
            seen.setdefault(g["code"], g)
        for code, g in seen.items():
            row = rows.setdefault(code, {"code": code, "category": g["category"], "dimension": g["dimension"],
                                         "records": 0, "categories": Counter(), "platforms": Counter(),
                                         "ecosystems": Counter(), "capabilities": Counter(), "examples": [],
                                         "packages_hidden": 0})
            row["records"] += 1
            row["categories"][cov["category"]] += 1
            platforms = {x.get("platform") for x in gaps_in(cov) if x["code"] == code and x.get("platform")}
            for p in platforms or cov["platforms"]:
                row["platforms"][p] += 1
            ecos = {x.get("ecosystem") for x in gaps_in(cov) if x["code"] == code and x.get("ecosystem") not in
                    (None, "unknown")}
            for e in ecos or cov["ecosystems"]:
                row["ecosystems"][e] += 1
            for x in gaps_in(cov):
                if x["code"] == code:
                    row["capabilities"][x.get("capability") or "unknown"] += 1
                    row["packages_hidden"] += x.get("found") or 0
            if len(row["examples"]) < 5:
                row["examples"].append(cov["slug"])
    ranked = sorted(rows.values(), key=lambda r: (-r["records"], r["code"]))
    return {r["code"]: r | {k: dict(r[k].most_common()) for k in ("categories", "platforms", "ecosystems",
                                                                   "capabilities")} for r in ranked}


def report(records: Iterable[dict[str, Any]], *, as_of: str | None = None) -> dict[str, Any]:
    """Coverage over the records, grouped by software category, platform, ecosystem and dimension; the gap codes by
    records blocked. Pure: reads only the records given."""
    covs = coverages(records)
    by_dimension = {d: dict(Counter(c["dimensions"][d]["status"] for c in covs)) for d in DIMENSIONS}
    unknown = Counter()
    for cov in covs:
        for d in DIMENSIONS:
            dim = cov["dimensions"][d]
            if dim["status"] in ("partial", "unverified"):
                cats = {g["category"] for g in dim["gaps"]} or {f"blocked_by_{dim['blocked_by']}"
                                                              if dim["blocked_by"] else "unclassified"}
                for cat in cats:
                    unknown[f"{d}:{cat}"] += 1
    shares = [c["summary"]["verified_share"] for c in covs if c["summary"]["verified_share"] is not None]
    return {
        "version": VERSION, "as_of": as_of or date.today().isoformat(), "records": len(covs),
        "verified_share": round(sum(shares) / len(shares), 4) if shares else None,
        "by_dimension": by_dimension,
        "unknown_by_dimension_and_category": dict(unknown.most_common()),
        "by_category": _group_rows(covs, lambda c: [c["category"] or "unknown"]),
        "by_platform": _group_rows(covs, lambda c: c["platforms"]),
        "by_ecosystem": _group_rows(covs, lambda c: c["ecosystems"]),
        "gap_codes": blocked_by_code(covs),
    }


def weakest(rep: dict[str, Any], group: str, *, min_records: int = 10, top: int = 5) -> list[tuple[str, dict]]:
    rows = [(k, v) for k, v in rep[group].items() if v["records"] >= min_records and v["verified_share"] is not None]
    return sorted(rows, key=lambda kv: (kv[1]["verified_share"], -kv[1]["records"]))[:top]


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def _top(counter: dict[str, int], n: int = 3) -> str:
    return ", ".join(f"{k} {v}" for k, v in list(counter.items())[:n]) or "-"


def render_report(rep: dict[str, Any], previous: dict[str, Any] | None = None) -> str:
    """The report as markdown: where pickfit verifies least, by group and dimension, and what blocks it."""
    lines = [f"# Verification coverage {rep['as_of']} ({rep['records']} records, cov.v1)", "",
             f"Mean verified share: {_pct(rep['verified_share'])}"
             + (f" (previous snapshot {previous['as_of']}: {_pct(previous.get('verified_share'))})"
                if previous else ""),
             "", "## By dimension", "", "| dimension | verified | partial | unverified | not applicable |",
             "|---|---|---|---|---|"]
    for d in DIMENSIONS:
        row = rep["by_dimension"][d]
        lines.append(f"| {d} | " + " | ".join(str(row.get(s, 0)) for s in STATUSES) + " |")
    for group, title in (("by_category", "software category"), ("by_platform", "platform"),
                         ("by_ecosystem", "ecosystem")):
        lines += ["", f"## By {title}", "", f"| {title} | records | verified share | "
                  + " | ".join(DIMENSIONS) + " |", "|---|---|---|" + "---|" * len(DIMENSIONS)]
        for name, row in rep[group].items():
            cells = []
            for d in DIMENSIONS:
                counts = row["dimensions"][d]
                applicable = sum(v for k, v in counts.items() if k != "not_applicable")
                cells.append(f"{counts.get('verified', 0)}/{applicable}" if applicable else "-")
            lines.append(f"| {name} | {row['records']} | {_pct(row['verified_share'])} | " + " | ".join(cells) + " |")
    lines += ["", "## Weakest (mean verified share, groups of 10 or more)", ""]
    for group, title in (("by_category", "Categories"), ("by_platform", "Platforms"), ("by_ecosystem", "Ecosystems")):
        lines.append(f"- {title}: " + "; ".join(f"{k} {_pct(v['verified_share'])} ({v['records']})"
                                               for k, v in weakest(rep, group)))
    lines += ["", "## Gap codes by records blocked", "",
              "| # | code | dimension | category | records | capability | categories | platforms | ecosystems |",
              "|---|---|---|---|---|---|---|---|---|"]
    for i, row in enumerate(rep["gap_codes"].values(), 1):
        lines.append(f"| {i} | {row['code']} | {row['dimension']} | {row['category']} | {row['records']} | "
                     f"{_top(row['capabilities'], 2)} | {_top(row['categories'])} | {_top(row['platforms'])} | "
                     f"{_top(row['ecosystems'])} |")
    lines += ["", "## Unverified or partial, by dimension and reason", ""]
    lines += [f"- {k}: {v}" for k, v in rep["unknown_by_dimension_and_category"].items()]
    return "\n".join(lines) + "\n"


SNAPSHOT_DIR = Path("runs") / "coverage"


def write_snapshot(rep: dict[str, Any], path: Path) -> Path:
    """The report as JSON, for trends: runs/coverage/<date>.json by default (gitignored). Never the records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def previous_snapshot(directory: Path, before: str) -> dict[str, Any] | None:
    """The newest snapshot in `directory` dated before `before` (YYYY-MM-DD), for the trend line."""
    found = sorted(p for p in directory.glob("*.json")
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem) and p.stem < before)
    return json.loads(found[-1].read_text(encoding="utf-8")) if found else None


def tasks(records: Iterable[dict[str, Any]], *, dimension: str | None = None, platform: str | None = None
          ) -> list[dict[str, Any]]:
    """Harness work, ranked by the records each gap code blocks: what to build (the registry's capability, its
    version and issue), where it hits, and examples. Read only; loop/issues.md is a person's to edit."""
    rep = report(records)
    out = []
    for row in rep["gap_codes"].values():
        if dimension and row["dimension"] != dimension:
            continue
        if platform and platform not in row["platforms"]:
            continue
        capability = task_capability(row["capabilities"])
        entry = registry_entry(capability)
        out.append({"rank": len(out) + 1, "code": row["code"], "dimension": row["dimension"],
                    "category": row["category"], "records_blocked": row["records"],
                    "categories": row["categories"], "platforms": row["platforms"], "ecosystems": row["ecosystems"],
                    "packages_hidden": row["packages_hidden"], "examples": row["examples"],
                    "capability": capability, "capabilities": row["capabilities"],
                    "capability_version": entry.version if entry else None,
                    "capability_note": entry.note if entry else None, "issue": entry.issue if entry else None,
                    "task": _task_line(row, capability, entry)})
    return out


def task_capability(capabilities: dict[str, int]) -> str | None:
    """The capability a task builds: the one its gaps name; when they name several of one family that the registry
    knows by its base (adapter:maven, adapter:nuget), the base; else the most common."""
    if not capabilities:
        return None
    bases = {capability_base(c) for c in capabilities}
    if len(capabilities) > 1 and len(bases) == 1 and next(iter(bases)) in CAPABILITIES:
        return next(iter(bases))
    return next(iter(capabilities))


def _task_line(row: dict[str, Any], capability: str | None, entry: Capability | None) -> str:
    kind = GAP_CODES.get(row["code"])
    when = kind.when if kind else f"security: {row['category']}"
    which = f" [{_top(row['capabilities'], 4)}]" if len(row["capabilities"]) > 1 else ""
    if entry is None:
        return f"file {row['code']} under a capability ({when})"
    if entry.version == 0:
        return f"build {capability}{which} ({entry.note}): unblocks {row['records']} records ({when})"
    return (f"{capability} v{entry.version} exists{which} ({entry.note}); rerun the {row['records']} records it "
            f"blocks, or extend it ({when})")


def render_tasks(rows: list[dict[str, Any]], fmt: str = "md") -> str:
    if fmt == "jsonl":
        return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    lines = ["| # | code | records | capability (version) | categories | platforms | ecosystems | examples |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cap = f"{r['capability']} (v{r['capability_version']})" if r["capability_version"] is not None else str(
            r["capability"])
        lines.append(f"| {r['rank']} | {r['code']} | {r['records_blocked']} | {cap}"
                     + (f" {r['issue']}" if r["issue"] else "") + f" | {_top(r['categories'])} | "
                     f"{_top(r['platforms'])} | {_top(r['ecosystems'])} | {', '.join(r['examples'][:3])} |")
    lines += ["", *(f"{r['rank']}. {r['task']}" for r in rows)]
    return "\n".join(lines) + "\n"


# How to verify one dimension again: a hint per dimension, for the person or loop that runs it. Paid ones say so.
RERUN = {
    "install": "uv run python scripts/loop_state.py add --kind reverify --target {slug}  # a full verify run (paid)",
    "function": "uv run python scripts/loop_state.py add --kind reverify --target {slug}  # a full verify run (paid)",
    "service": "uv run python scripts/loop_state.py add --kind reverify --target {slug}  # a full verify run (paid)",
    "security": "uv run pickfit security --slug {slug} --write  # $0",
    "docs": "uv run pickfit score --slug {slug} --force  # grades the README (paid)",
    "usability": "uv run pickfit usability --slug {slug} --write  # paid",
    "video": "uv run python scripts/loop_state.py add --kind reverify --target {slug}  # a verify run records it",
    "repo_signals": "uv run pickfit score --slug {slug} --no-registries  # GitHub; grades a README that changed",
}


def requeue(records: Iterable[dict[str, Any]], spec: str) -> dict[str, Any]:
    """The records and dimensions a capability can verify again, never writing anything.

    A record is listed when one of its gaps needs the capability (`adapter` matches adapter:maven) and, for a version
    that has shipped, the dimension was checked before that version's day (checked since, the gap is the
    capability's limit, not its absence). A version not built yet lists every record that waits for it. Each row
    carries what the record's scores are now (quality, cap, treasure), so a change in eligibility can be followed."""
    cid, version = parse_capability(spec)
    entry = registry_entry(cid)
    assert entry is not None
    version = entry.version if version is None else version
    since = entry.since(version)
    rows = []
    for record in records:
        cov = compute_coverage(record)
        for name, dim in cov["dimensions"].items():
            hits = [g for g in dim["gaps"] if matches_capability(g.get("capability"), cid)]
            if not hits:
                continue
            checked = _day(dim.get("checked_at"))  # None: never checked, so it waits whatever the version
            if since and checked and checked >= since:
                continue  # checked with this version already: the gap is the capability's limit, not its absence
            scores = record.get("scores") or {}
            rows.append({"slug": cov["slug"], "dimension": name, "codes": sorted({g["code"] for g in hits}),
                         "capabilities": sorted({g["capability"] for g in hits}), "checked_at": checked,
                         "harness_version": dim.get("harness_version"),
                         "quality": _g(scores, "quality", "total"), "cap_reason": _g(scores, "quality", "cap_reason"),
                         "treasure": bool(_g(scores, "treasure", "is_treasure")),
                         "rerun": RERUN[name].format(slug=cov["slug"])})
    built = version <= entry.version and entry.version > 0
    return {"capability": cid, "version": version, "registry_version": entry.version, "since": since,
            "built": built, "dry_run": True, "records": len({r["slug"] for r in rows}),
            "by_dimension": dict(Counter(r["dimension"] for r in rows)), "rows": rows}


def render_requeue(result: dict[str, Any], fmt: str = "md") -> str:
    if fmt == "jsonl":
        return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in result["rows"])
    state = (f"v{result['version']} shipped {result['since']}" if result["built"] else
             f"v{result['version']} not built yet (registry: v{result['registry_version']}): these wait for it")
    lines = [f"# Requeue for {result['capability']} ({state}); dry run, nothing written", "",
             f"{result['records']} records; by dimension: {_top(result['by_dimension'], 8)}", "",
             "| slug | dimension | codes | checked | quality | treasure | rerun |", "|---|---|---|---|---|---|---|"]
    for r in result["rows"]:
        quality = "-" if r["quality"] is None else str(r["quality"])
        cap = f" ({r['cap_reason']})" if r["cap_reason"] else ""
        lines.append(f"| {r['slug']} | {r['dimension']} | {', '.join(r['codes'])} | {r['checked_at'] or '-'} | "
                     f"{quality}{cap} | {'yes' if r['treasure'] else 'no'} | `{r['rerun']}` |")
    return "\n".join(lines) + "\n"


def render_capabilities() -> str:
    lines = ["| capability | version | since | closes | issue | note |", "|---|---|---|---|---|---|"]
    for cap in CAPABILITIES.values():
        lines.append(f"| {cap.id} | {cap.version} | {cap.since() or '-'} | {', '.join(cap.closes)} | "
                     f"{cap.issue or '-'} | {cap.note} |")
    return "\n".join(lines) + "\n"


def render_taxonomy() -> str:
    lines = ["| code | dimension | category | capability | when |", "|---|---|---|---|---|"]
    for code, kind in GAP_CODES.items():
        lines.append(f"| {code} | {kind.dimension} | {kind.category} | {kind.capability} | {kind.when} |")
    return "\n".join(lines) + "\n"


# --- security estimate overlay (a dry run of sec.v2, before the coordinator's rescan) ---------------------------------


def with_security_estimate(records: list[dict[str, Any]], estimate: dict[str, Any]) -> list[dict[str, Any]]:
    """Copies of the records whose security is what a sec.v2 dry run estimated (rows of slug -> level, coverage,
    status, checked, found, gaps; the security workstream's gaps-dryrun.json), in memory only, so coverage and the
    treasure rules can be read as they will stand after the rescan. Records the estimate lacks stay as they are."""
    rows = estimate.get("rows", estimate)
    out = []
    for record in records:
        row = rows.get(record.get("slug"))
        if not row or "error" in row:
            out.append(record)
            continue
        old = record.get("security") or {}
        gaps = [_security_gap(g) for g in row.get("gaps") or []]
        estimated = {"version": "sec.v2", "status": row["status"], "checked_at": old.get("checked_at"),
                     "sources": old.get("sources") or [], "packages_checked": row.get("checked", 0),
                     "findings": old.get("findings") or [],
                     "assessment": {"level": row["level"], "policy_version": "sec.v2"},
                     "coverage": {"state": row["coverage"], "packages_checked": row.get("checked", 0),
                                  "packages_found": max(row.get("found", 0), row.get("checked", 0)), "gaps": gaps,
                                  "target": None},
                     "estimated": True}
        out.append(record | {"security": estimated})
    return out


# --- treasure and cap rules (needs the scoring patch's settings) ------------------------------------------------------

# Candidate rules for 念誠's decision (docs/proposals/coverage.md: report the distribution, decide later). Each is a set
# of settings in pickfit/schema.py and pickfit/score.py; the defaults are today's rules.
CANDIDATE_RULES: dict[str, dict[str, Any]] = {
    "conditional_uncapped": {"schema.SECURITY_CAP_LEVELS": frozenset({"blocked", "exposed"})},
    "exposed_no_treasure": {"schema.SECURITY_CAP_LEVELS": frozenset(),
                            "schema.SECURITY_NO_TREASURE_LEVELS": frozenset({"blocked", "exposed"}),
                            "score.SECURITY_EXPOSED_DEDUCTION": 10.0},
    "unchecked_no_treasure": {"schema.UNCHECKED_CAN_BE_TREASURE": False},
    "security_coverage_80": {"schema.TREASURE_MIN_SECURITY_COVERAGE": 0.8},
    "function_coverage_50": {"schema.TREASURE_MIN_FUNCTION_COVERAGE": 0.5},
    "unverified_uncapped": {"schema.UNVERIFIED_CAP": False},
}


def rules_available() -> bool:
    from pickfit import schema

    return hasattr(schema, "UNVERIFIED_CAP") and hasattr(schema, "SECURITY_CAP_LEVELS")


@contextmanager
def settings(values: dict[str, Any]) -> Iterator[None]:
    """The scoring settings set to `values` ("schema.NAME" or "score.NAME") for the duration; restored after."""
    from pickfit import schema, score

    modules = {"schema": schema, "score": score}
    before = {}
    try:
        for key, value in values.items():
            module, name = key.split(".", 1)
            if not hasattr(modules[module], name):
                raise KeyError(f"{key} is not a setting here (is the scoring patch applied?)")
            before[key] = getattr(modules[module], name)
            setattr(modules[module], name, value)
        yield
    finally:
        for key, value in before.items():
            module, name = key.split(".", 1)
            setattr(modules[module], name, value)


def _score_row(record: dict[str, Any], now: datetime) -> dict[str, Any]:
    from pickfit.score import refresh_scores

    data = copy.deepcopy(record)
    refresh_scores(data, now)
    scores = data.get("scores") or {}
    return {"slug": record["slug"], "total": _g(scores, "quality", "total"),
            "treasure": bool(_g(scores, "treasure", "is_treasure")),
            "blocked_by": _g(scores, "treasure", "blocked_by"), "cap_reason": _g(scores, "quality", "cap_reason")}


def evaluate_rules(records: list[dict[str, Any]], now: datetime,
                   rules: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Every record rescored (in memory, refresh_scores on a copy) under today's settings and under each candidate
    rule: treasures gained and lost, and how many sit at exactly 69.0 and 79.0. Never writes."""
    if not rules_available():
        raise RuntimeError("the treasure and cap settings come with loop/proposals/coverage-scoring-b3v7.patch")
    rules = CANDIDATE_RULES if rules is None else rules

    def run() -> list[dict[str, Any]]:
        return [_score_row(r, now) for r in records]

    def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        totals = Counter(r["total"] for r in rows)
        return {"treasures": sum(r["treasure"] for r in rows), "at_69.0": totals.get(69.0, 0),
                "at_79.0": totals.get(79.0, 0), "distinct": len(totals)}

    base = run()
    out = {"default": stats(base), "rules": {}}
    by_slug = {r["slug"]: r for r in base}
    for name, values in rules.items():
        with settings(values):
            rows = run()
        gained = sorted(r["slug"] for r in rows if r["treasure"] and not by_slug[r["slug"]]["treasure"])
        lost = sorted(r["slug"] for r in rows if by_slug[r["slug"]]["treasure"] and not r["treasure"])
        out["rules"][name] = stats(rows) | {"settings": {k: sorted(v) if isinstance(v, frozenset) else v
                                                         for k, v in values.items()},
                                            "gained": len(gained), "lost": len(lost), "gained_slugs": gained[:20],
                                            "lost_slugs": lost[:20], "blocked_by": dict(
                                                Counter(r["blocked_by"] for r in rows if r["blocked_by"]))}
    return out


def distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Unknowns for the treasure decision: per dimension, the records partial or unverified, by gap category, software
    category and platform (a record counts once per category it has in that dimension)."""
    rows: Counter[tuple[str, str, str, str]] = Counter()
    for cov in coverages(records):
        for d in DIMENSIONS:
            dim = cov["dimensions"][d]
            if dim["status"] not in ("partial", "unverified"):
                continue
            cats = {g["category"] for g in dim["gaps"]} or {f"blocked_by_{dim['blocked_by']}" if dim["blocked_by"]
                                                          else "unclassified"}
            for cat in cats:
                for platform in cov["platforms"]:
                    rows[(d, cat, cov["category"] or "unknown", platform)] += 1
    return {"rows": [{"dimension": d, "gap_category": c, "category": s, "platform": p, "records": n}
                     for (d, c, s, p), n in sorted(rows.items(), key=lambda kv: (DIMENSIONS.index(kv[0][0]),
                                                                                  -kv[1], kv[0]))]}


# --- CLI --------------------------------------------------------------------------------------------------------------


def add_parser(sub: Any) -> None:
    c = sub.add_parser("coverage", help="Verification Coverage: what pickfit verified, what it could not and why "
                                        "(reads data/software, never writes it; $0)")
    csub = c.add_subparsers(dest="coverage_command", required=True)

    def common(p: Any) -> None:
        p.add_argument("--data-dir", default="data/software", help="records (default data/software)")
        p.add_argument("--all-statuses", action="store_true", help="hidden and removed records too (default listed)")
        p.add_argument("--security-estimate", default=None, metavar="JSON",
                       help="read security from a sec.v2 dry run (rows of slug -> level, coverage, gaps), in memory")

    r = csub.add_parser("report", help="coverage by category, platform, ecosystem and dimension; gap codes by records "
                                       "blocked; writes a dated JSON snapshot")
    common(r)
    r.add_argument("--json", action="store_true", help="print the report as JSON instead of markdown")
    r.add_argument("--snapshot", default=None, metavar="PATH",
                   help=f"where to write the snapshot (default {SNAPSHOT_DIR}/<date>.json, gitignored)")
    r.add_argument("--no-snapshot", action="store_true", help="write no snapshot")
    r.add_argument("--date", default=None, help="the snapshot's date, YYYY-MM-DD (default today)")
    t = csub.add_parser("tasks", help="harness work ranked by records blocked (markdown or JSONL); edits nothing")
    common(t)
    t.add_argument("--format", choices=("md", "jsonl"), default="md")
    t.add_argument("--dimension", choices=DIMENSIONS, default=None)
    t.add_argument("--platform", choices=(*PLATFORMS, "unknown"), default=None)
    t.add_argument("--limit", type=int, default=None)
    q = csub.add_parser("requeue", help="the records and dimensions a capability can verify again (dry run)")
    common(q)
    q.add_argument("--capability", required=True, metavar="ID[@VERSION]")
    q.add_argument("--format", choices=("md", "jsonl"), default="md")
    csub.add_parser("capabilities", help="the capability registry and the gap taxonomy")
    s = csub.add_parser("show", help="one record's coverage as JSON")
    common(s)
    s.add_argument("slug")
    u = csub.add_parser("rules", help="unknowns by dimension, reason, category and platform, and what each candidate "
                                      "treasure or cap rule would do (needs the scoring patch for the rules)")
    common(u)
    u.add_argument("--now", default=None, help="computed_at for the in-memory rescoring (ISO time)")
    c.set_defaults(func=main_coverage)


def _records(args: Any) -> list[dict[str, Any]]:
    records = load_records(Path(args.data_dir), None if args.all_statuses else "listed")
    if args.security_estimate:
        estimate = json.loads(Path(args.security_estimate).read_text(encoding="utf-8"))
        records = with_security_estimate(records, estimate)
    return records


def main_coverage(args: Any) -> int:
    command = args.coverage_command
    if command == "capabilities":
        print(render_capabilities() + "\n" + render_taxonomy(), end="")
        return 0
    records = _records(args)
    if command == "report":
        day = args.date or date.today().isoformat()
        rep = report(records, as_of=day)
        target = Path(args.snapshot) if args.snapshot else SNAPSHOT_DIR / f"{day}.json"
        previous = previous_snapshot(target.parent, day) if target.parent.exists() else None
        print(json.dumps(rep, ensure_ascii=False, indent=1) if args.json else render_report(rep, previous))
        if not args.no_snapshot:
            print(f"snapshot: {write_snapshot(rep, target)}", file=sys.stderr)
        return 0
    if command == "tasks":
        rows = tasks(records, dimension=args.dimension, platform=args.platform)
        print(render_tasks(rows[: args.limit] if args.limit else rows, args.format), end="")
        return 0
    if command == "requeue":
        try:
            result = requeue(records, args.capability)
        except ValueError as err:
            print(f"pickfit coverage: {err}", file=sys.stderr)
            return 2
        print(render_requeue(result, args.format), end="")
        return 0
    if command == "show":
        found = [r for r in records if r.get("slug") == args.slug]
        if not found:
            print(f"pickfit coverage: no record {args.slug!r}", file=sys.stderr)
            return 2
        print(json.dumps(compute_coverage(found[0]), ensure_ascii=False, indent=1))
        return 0
    if command == "rules":
        out: dict[str, Any] = {"distribution": distribution(records)}
        if rules_available():
            from pickfit.ledger import taipei_now

            now = datetime.fromisoformat(args.now) if args.now else taipei_now()
            out["rules"] = evaluate_rules(records, now)
        else:
            out["rules"] = None
            print("pickfit coverage: the candidate rules need loop/proposals/coverage-scoring-b3v7.patch; "
                  "printing the distribution only", file=sys.stderr)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    return 2
