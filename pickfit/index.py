"""Build the matching index the MCP Worker bundles (index "pickfit-index.v1").

The Worker never reads data/software/*.json directly: this module validates
every record against software.v1 (the pydantic model that generates
schema/software.v1.json, plus its cross-field checks) and writes one JSON file
with what find_software and get_install_guide need. Any bad record fails the
whole build, so bad data never reaches a deploy.

Only listed records are indexed, and only install guides that were actually
run (basis "replayed" or "human") are kept: README claims never reach users as
install steps. An MCP server's guide also carries the handshake its run saw
(`mcp`: the launch argv a fresh box started, the tool names it listed), from
which the Worker writes the client config; the README's own MCP facts (env
vars, config snippets, tool names) ride along under the entry's `mcp`. A GUI
app's run carries what pickfit saw of its launch (`gui`: tier, the screen the
judge read, the display, whether the launch passed offline); the window title
is the app's own text and stays out of the index.
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
    """A GUI app's launch as pickfit saw it; never the window title, which the app chooses."""
    if run.gui is None:
        return None
    launch = next((t for t in run.smoke_tests if t.command == run.gui.command and t.passed), None)
    return {"tier": run.gui.tier, "screen": run.gui.screen, "display": run.gui.display,
            "launch_offline": launch.offline if launch else None}


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


def load_jobs(jobs_dir: Path) -> dict[str, list[str]]:
    """slug -> the jobs scripts/tool_jobs.py found in its README (data/jobs/<slug>.json); none is fine."""
    jobs: dict[str, list[str]] = {}
    for path in sorted(jobs_dir.glob("*.json")) if jobs_dir.is_dir() else []:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("slug") == path.stem:
            jobs[path.stem] = [j["job"] for j in data.get("jobs", []) if isinstance(j.get("job"), str)]
    return jobs


def _entry(record: SoftwareRecord, jobs: list[str] | None = None) -> dict[str, Any]:
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
            "pitfalls": [p.model_dump() for p in run.pitfalls],
            "run": _run_summary(run),
            "mcp": run.mcp.model_dump() if run.mcp else None,
        }
    scores = record.scores
    return {
        "slug": record.slug,
        "name": record.name,
        "summary": record.summary,
        "why_worth_it": record.why_worth_it,
        "category": record.category,
        "kind": record.kind,
        "maturity": record.maturity,
        "tags": record.tags,
        "use_cases": record.use_cases,
        # Matched by the shortlist and the rules fallback, never shown on a card (worker relevance.ts).
        "jobs": jobs or [],
        "alternatives_to": record.alternatives_to,
        "homepage": record.homepage,
        "repo_url": record.repo.url,
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
        "scores": {
            "quality": scores.quality.total,
            "popularity": scores.popularity.score,
            "treasure": scores.treasure.is_treasure,
            "treasure_value": scores.treasure.value,
            "formula_version": scores.formula_version,
        } if scores else None,
        "sources": [s.url for s in record.sources if s.url][:5],
    }


def build_index(data_dir: Path = DEFAULT_DATA_DIR, now: datetime | None = None,
                jobs_dir: Path | None = None) -> BuildResult:
    """jobs_dir defaults to the data directory's sibling `jobs` (data/jobs next to data/software)."""
    records, digest = load_records(data_dir)
    jobs = load_jobs(jobs_dir if jobs_dir is not None else data_dir.parent / "jobs")
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
        "entries": [_entry(r, jobs.get(r.slug)) for r in sorted(listed, key=lambda r: r.slug)],
    }
    return BuildResult(index=index, skipped=[r.slug for r in records if r.status != "listed"])


def write_index(index: dict[str, Any], out: Path = DEFAULT_OUT) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
