"""Build the matching index the MCP Worker bundles (index "pickfit-index.v1").

The Worker never reads data/software/*.json directly: this module validates
every record against software.v1 (the pydantic model that generates
schema/software.v1.json, plus its cross-field checks) and writes one JSON file
with what find_software and get_install_guide need. Any bad record fails the
whole build, so bad data never reaches a deploy.

Only listed records are indexed, and only install guides that were actually
run (basis "replayed" or "human") are kept: README claims never reach users as
install steps. Each guide carries its run's feature coverage with the smoke
tests behind it (command, passed), so the Worker shows a feature as checked
only when one of those passed. An MCP server's guide also carries the handshake
its run saw (`mcp`: the launch argv a fresh box started, the tool names it
listed), from which the Worker writes the client config; the README's own MCP
facts (env vars, config snippets, tool names) ride along under the entry's `mcp`.
A GUI app's run carries what pickfit saw of its launch (`gui`: tier, the screen
the judge read, the display, whether the launch passed offline); the window
title is the app's own text and stays out of the index.
A hosted web app (kind web_app) has no install guides: its entry's `web` carries
the URL to open and the facts its strongest passed browser run recorded (account,
ads, third-party domains, whether entered data left the device, the PWA offline
result, the operations pickfit checked, the check date), or none before a run passed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pickfit.schema import SCHEMA_VERSION, SoftwareRecord, VerificationRun, is_passed
from pickfit.usage_guide import shown_guide
from pickfit.userpaths import SANDBOX_HOMES, UserCommand, expected_for_user, for_user, names_workdir

INDEX_VERSION = "pickfit-index.v1"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "software"
DEFAULT_OUT = REPO_ROOT / "worker" / "src" / "generated" / "index.json"
VERIFIED_BASES = ("replayed", "human")


class IndexBuildError(Exception):
    """One or more records are invalid; nothing was written."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class BuildResult:
    index: dict[str, Any]
    skipped: list[str] = field(default_factory=list)  # valid but not listed


def load_records(data_dir: Path) -> tuple[list[SoftwareRecord], str]:
    """Validate every <slug>.json under data_dir; return records and a digest of the files."""
    paths = sorted(data_dir.glob("*.json"))
    if not paths:
        raise IndexBuildError([f"no *.json records under {data_dir}"])
    problems: list[str] = []
    records: list[SoftwareRecord] = []
    digest = hashlib.sha256()
    for path in paths:
        raw = path.read_bytes()
        digest.update(path.name.encode() + b"\0" + raw + b"\0")
        try:
            record = SoftwareRecord.model_validate_json(raw)
        except ValidationError as err:
            problems.append(f"{path.name}: {err}")
            continue
        if record.slug != path.stem:
            problems.append(f"{path.name}: slug {record.slug!r} does not match the file name")
            continue
        records.append(record)
    for key in ("slug", "repo_id"):
        seen: dict[str, str] = {}
        for record in records:
            value = getattr(record, key)
            if value in seen:
                problems.append(f"{record.slug}: duplicate {key} {value!r} (also {seen[value]})")
            seen[value] = record.slug
    if problems:
        raise IndexBuildError(problems)
    return records, digest.hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _gui(run: VerificationRun) -> dict[str, Any] | None:
    """A GUI app's launch as pickfit saw it, and the goals it operated the app toward; never the window title or
    anything else the app chooses (an operation's observed line is pickfit's own)."""
    if run.gui is None:
        return None
    launch = next((t for t in run.smoke_tests if t.command == run.gui.command and t.passed), None)
    out = {"tier": run.gui.tier, "screen": run.gui.screen, "display": run.gui.display,
           "launch_offline": launch.offline if launch else None}
    if run.gui.operations:
        out["operations"] = [{"feature": o.feature, "check": o.check, "passed": o.passed, "replay": o.replay,
                              "goal": o.goal, "observed": o.observed} for o in run.gui.operations]
    return out


def _visual(record: SoftwareRecord) -> dict[str, Any] | None:
    """Desktop and web apps: the visual deduction that is in the quality score (scores.quality.visual, which the
    record's validation ties to its own current visual check): "defect" (the total took 5% off, with the app-caused
    defects listed), "clean", or "not_checked" (no current check, so nothing is taken off). None for other kinds."""
    if record.kind not in ("desktop_app", "web_app"):
        return None
    visual = record.scores.quality.visual if record.scores else None
    check = record.visual_check
    if visual is None or check is None:
        return {"status": "not_checked"}
    defects = [{"kind": d.kind, "problem": d.problem, "quote": d.quote} for d in check.defects if d.cause == "app"]
    return {"status": "defect" if visual.factor < 1 else "clean", "factor": visual.factor, "defects": defects[:6],
            "checked_at": _iso(check.checked_at)[:10], "model": check.model}


def _security(record: SoftwareRecord) -> dict[str, Any]:
    """Known high or critical vulnerabilities in what a fresh install brings (record field security, sec.v1):
    "vulnerable" (quality capped at 79, the advisories listed, malicious ones first), "clean", or "unchecked" with
    why (no repository or package, a lockfile pickfit cannot read, nothing resolved). A record not run yet is
    "unchecked" too, reason "not_run"."""
    check = record.security
    if check is None:
        return {"status": "unchecked", "reason": "not_run"}
    out: dict[str, Any] = {"status": check.status, "checked_at": _iso(check.checked_at)[:10]}
    if check.status == "unchecked":
        out["reason"] = check.unchecked_reason
        return out
    out["packages_checked"] = check.packages_checked
    if check.findings:
        out["count"] = max(check.findings_total, len(check.findings))
        if check.advisories_total:  # distinct vulnerabilities; count is findings (one per package version)
            out["advisories"] = check.advisories_total
        out["findings"] = [{"package": f.package, "version": f.version, "advisory": f.advisory, "severity": f.severity,
                            "fixed_in": f.fixed_in, "summary": f.summary, "malicious": f.malicious}
                           for f in check.findings[:10]]
    return out


def _web(record: SoftwareRecord) -> dict[str, Any] | None:
    """A web app's URL and what its strongest passed browser run saw (latest first on a tie); check is None
    until a run passed. Operations' observed lines are pickfit's own."""
    if record.web is None:
        return None
    passed = [r for r in record.verification.runs if r.web is not None and is_passed(r.level)]
    best = max(passed, key=lambda r: (r.level == "function", r.checked_at), default=None)
    check = None
    if best is not None and best.web is not None:
        web = best.web
        check = {
            "run_id": best.id,
            "level": best.level,
            "checked_at": _iso(best.checked_at),
            "evidence_url": best.evidence.evidence_url,
            "browser": web.browser,
            "account_needed": web.account_needed,
            "ads_seen": web.ads_seen,
            "third_party_domains": web.third_party_domains,
            "third_party_hosts": web.third_party_hosts,
            "data_sent": web.data_sent,
            "data_sent_note": web.data_sent_note,
            "pwa": web.pwa,
            "offline": web.offline,
            "operations": [{"feature": o.feature, "check": o.check, "passed": o.passed, "goal": o.goal,
                            "observed": o.observed} for o in web.operations],
            "features": _feature_coverage(best),
        }
    return {"url": record.web.url, "check": check}


def _video(run: VerificationRun) -> dict[str, Any] | None:
    """A run's verification clip and the raw recordings it was cut from (files the Worker serves from R2 at
    /video/<slug>/<file>; the poster is the clip's name with .jpg)."""
    v = run.video
    if v is None:
        return None
    out = {"clip": v.clip, "clip_sha256": v.clip_sha256, "seconds": v.seconds, "recorded_at": _iso(v.recorded_at),
           "features": list(v.features),
           "raw": [{"file": r.file, "sha256": r.sha256, "seconds": r.seconds,
                    "feature_index": _raw_feature_index(run, list(v.features), r.smoke_test)} for r in v.raw]}
    # Chapters (start_s, title, feature) come from the video step; passed through as they are.
    chapters = getattr(v, "chapters", None)
    if chapters:
        out["chapters"] = [c if isinstance(c, dict) else c.model_dump(mode="json") for c in chapters]
    return out


def _raw_feature_index(run: VerificationRun, features: list[str], smoke_test: int) -> int | None:
    """Which of the clip's features a raw recording shows (an index, so a translated page still matches it):
    the checked feature whose passed check is that smoke test."""
    name = next((f.feature for f in run.features if f.status == "checked" and smoke_test in f.smoke_tests), None)
    return features.index(name) if name in features else None


def _run_summary(run: VerificationRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "level": run.level,
        "os": run.os,
        "arch": run.arch,
        "method": run.method,
        "runner": run.runner,
        "replayed": run.replayed,
        "checked_at": _iso(run.checked_at),
        "tool_version": run.tool_version,
        "evidence_url": run.evidence.evidence_url,
        "gui": _gui(run),
        "gpu": run.gpu,
        "microphone": run.microphone,
        "video": _video(run),
    }


def works_offline(run: VerificationRun, first_task: str | None = None) -> bool | None:
    """Whether it works with the network off after install; None when nothing ran offline.

    The first task decides when it ran offline (that is what users are told to run);
    otherwise every passing smoke test must have passed offline.
    """
    for test in run.smoke_tests:
        if first_task and test.passed and test.command == first_task and test.offline is not None:
            return test.offline
    checked = [t.offline for t in run.smoke_tests if t.passed and t.offline is not None]
    return all(checked) if checked else None


def _first_task_setup(run: VerificationRun, first_task: str | None) -> list[dict[str, Any]]:
    """What the first task needs to run first (its input file, a server), from the run's smoke test."""
    for test in run.smoke_tests:
        if first_task and test.passed and test.command == first_task:
            return [{"command": s.command, "background": s.background} for s in test.setup]
    return []


def _feature_coverage(run: VerificationRun) -> list[dict[str, Any]]:
    """The run's feature checks, each with the smoke tests it cites (command and whether it passed)."""
    return [{"feature": f.feature, "status": f.status, "reason": f.reason, "failure": f.failure, "note": f.note,
             "checks": [{"command": run.smoke_tests[i].command, "passed": run.smoke_tests[i].passed}
                        for i in f.smoke_tests]}
            for f in run.features]


# The note scripts/note_tmp_launch.py put on two records (11/1). The Worker now writes those launch commands with a
# placeholder for the test's files, so it no longer applies to what a user sees; the records keep it.
LAUNCH_NOTE = "The sandbox run's launch command points at files it created in /tmp for the test."


def _user_guide(guide: dict[str, Any], os_name: str) -> dict[str, Any]:
    """The guide's commands as a user runs them (userpaths.for_user: the sandbox home as $HOME); the guide's own
    steps, first task, setup and check stay exactly as the run executed them."""
    where: dict[str, UserCommand] = {}

    def user(label: str, command: str) -> str:
        where[label] = for_user(command, os_name)
        return where[label].command

    check = guide["check"]
    out = {
        "steps": [{"command": user(f"step {i}", s["command"]), "purpose": s["purpose"]}
                  for i, s in enumerate(guide["steps"], start=1)],
        "first_task_setup": [{"command": user(f"setup {i}", s["command"]), "background": s["background"]}
                             for i, s in enumerate(guide["first_task_setup"], start=1)],
        "first_task": user("first task", guide["first_task"]) if guide["first_task"] else None,
        "check": {"command": user("check", check["command"]),
                  "expected_signal": expected_for_user(check["expected_signal"], os_name)} if check else None,
    }
    commands = [s["command"] for s in guide["steps"] + guide["first_task_setup"]] + \
        [c for c in (guide["first_task"], check and check["command"]) if c]
    out["changed"] = any(u.changed for u in where.values())
    out["not_portable"] = [label for label, u in where.items() if not u.portable]
    out["needs_workdir"] = any(names_workdir(c, os_name) for c in commands)
    out["sandbox_home"] = SANDBOX_HOMES.get(os_name) if out["changed"] or out["not_portable"] else None
    return out


def _entry(record: SoftwareRecord) -> dict[str, Any]:
    runs = {run.id: run for run in record.verification.runs}
    install: dict[str, Any] = {}
    for os_name, guide in record.install.guides():
        if guide.basis not in VERIFIED_BASES:
            continue
        run = runs[guide.run_id or ""]  # SoftwareRecord checked the run exists and passed
        install[os_name] = {
            "basis": guide.basis,
            "method": guide.method,
            "steps": [step.model_dump() for step in guide.steps],
            "manual_steps": guide.manual_steps,
            "check": guide.check.model_dump() if guide.check else None,
            "first_task": guide.first_task,
            "first_task_setup": _first_task_setup(run, guide.first_task),
            "works_offline": works_offline(run, guide.first_task),
            "pitfalls": [p.model_dump() for p in run.pitfalls if p.readme_said != LAUNCH_NOTE],
            "features": _feature_coverage(run),
            "run": _run_summary(run),
            "mcp": run.mcp.model_dump() if run.mcp else None,
        }
        install[os_name]["user"] = _user_guide(install[os_name], run.os)
    scores = record.scores
    return {
        "slug": record.slug,
        "name": record.name,
        "summary": record.summary,
        "why_worth_it": record.why_worth_it,
        "usage_guide": shown_guide(record),
        "category": record.category,
        "kind": record.kind,
        "maturity": record.maturity,
        "tags": record.tags,
        "use_cases": record.use_cases,
        "alternatives_to": record.alternatives_to,
        "features": record.features,
        "homepage": record.homepage,
        "repo_url": record.repo.url if record.repo else None,
        "platforms": record.platforms,
        "prerequisites": record.prerequisites.model_dump(),
        "pricing": record.pricing.model,
        "pricing_note": record.pricing.note,
        "open_source": record.open_source,
        "license": record.license,
        "processing": record.processing,
        "last_release": _iso(record.last_release.published_at)[:10] if record.last_release else None,
        "verification": {
            "level": record.verification.level,
            "checked_at": _iso(record.verification.checked_at),
            "passed_runs": [_run_summary(r) for r in record.verification.runs if is_passed(r.level)],
        },
        "install": install,
        "mcp": record.mcp.model_dump() if record.mcp else None,
        "web": _web(record),
        "visual": _visual(record),
        "security": _security(record),
        "scores": {
            "quality": scores.quality.total,
            "popularity": scores.popularity.score,
            "treasure": scores.treasure.is_treasure,
            "treasure_value": scores.treasure.value,
            "formula_version": scores.formula_version,
            "confidence": scores.quality.confidence,
            # The parts of the quality score with weight but no data: they drop out, which is why confidence is below 1.
            "unmeasured": [name for name, part in scores.quality.components if part is not None
                           and part.weight > 0 and part.score is None],
        } if scores else None,
        "sources": [s.url for s in record.sources if s.url][:5],
    }


def build_index(data_dir: Path = DEFAULT_DATA_DIR, now: datetime | None = None) -> BuildResult:
    records, digest = load_records(data_dir)
    listed = [r for r in records if r.status == "listed"]
    try:
        data_dir_label = str(data_dir.resolve().relative_to(REPO_ROOT))
    except ValueError:
        data_dir_label = str(data_dir)
    index = {
        "index_version": INDEX_VERSION,
        "schema_version": SCHEMA_VERSION,
        "built_at": _iso(now or datetime.now(UTC)),
        "data_dir": data_dir_label,
        "data_sha256": digest,
        "count": len(listed),
        "entries": [_entry(r) for r in sorted(listed, key=lambda r: r.slug)],
    }
    return BuildResult(index=index, skipped=[r.slug for r in records if r.status != "listed"])


def write_index(index: dict[str, Any], out: Path = DEFAULT_OUT) -> None:
    """The index, and beside it the web page's zh-TW sentences for the same entries (zh-TW.json)."""
    from pickfit.i18n import LANG, i18n_dir, worker_translations

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    data_dir = Path(index["data_dir"])
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir
    translations = worker_translations(index, i18n_dir(data_dir))
    (out.parent / f"{LANG}.json").write_text(json.dumps(translations, ensure_ascii=False) + "\n", encoding="utf-8")
