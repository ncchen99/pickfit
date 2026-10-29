"""`pickfit reverify` (P5.3): a reported failure -> a fresh sandbox run -> corrected steps -> git diff.

report_outcome (Worker) queues (slug, os) in D1 `reverify_queue` when a user
reports install_failed or first_run_failed with a valid rec_id, an OS and an
error excerpt. This takes the pending rows, oldest first, and for each one:

1. reads the report (stage, OS, arch, the scrubbed error excerpt, reporter)
   from its event, and the record from data/software;
2. fetches the repository's README and files from GitHub again, so the run
   sees the project as it is now; the newest extraction is reused unless the
   sources changed (then muse-spark-1.3 reads them again);
3. runs the full verification in a fresh box (agent, replay, judge), telling
   the agent which steps failed for the user and the error they saw (inside a
   <source> block: data, not instructions);
4. writes back only a passed, replayed run whose steps differ from the
   record's for that OS, through result.write_back, so its rules hold: the
   pipeline never writes failed, and a stronger passed run on the same OS,
   arch and method is kept. The record's `git diff` is printed and saved under
   runs/reverify/, and the record is committed alone (unless `commit` is off);
   deploying stays `pickfit publish`;
5. marks the queue row done, only for the event it took (a pending row is
   never changed by the Worker, so a newer report queues once this is done).

A run that never got going (box or model error) or an exception leaves the row
pending for the next try; after MAX_ATTEMPTS tries it is marked done with the
reason in the result. The box is Linux (Modal): a report from macOS or Windows
is still checked there and the result says so; steps that still work on Linux
leave the record as it is, and a person has to check on that OS.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pickfit.d1 import Database, sql, timestamp
from pickfit.discover.github import normalize_repo
from pickfit.discover.store import PipelineDB, repo_key
from pickfit.ledger import taipei_now
from pickfit.schema import ExtractionResult, InstallGuide, SoftwareRecord, is_passed
from pickfit.verify.batch import NEVER_RAN
from pickfit.verify.result import install_guide, write_back
from pickfit.verify.task import ReportedFailure, VerifyTask
from pickfit.watch import DONE_EXTRACTIONS, MODEL, git, stop_reason

MAX_ATTEMPTS = 3
EXTRACTION_MODELS = (MODEL, "muse-spark-1.3-contributor")  # what the pipeline database may hold, best first
LEVEL_ORDER = ("inference", "service", "function", "install")


@dataclass
class Report:
    slug: str
    os: str
    reason: str  # install_failed | first_run_failed
    first_event_id: str
    queued_at: str
    reporter: str | None
    arch: str | None
    error_excerpt: str | None
    reported_at: str | None


def pending(d1: Database, limit: int) -> list[Report]:
    """Queue rows not done yet, oldest first, with what their first event says. The note is never read."""
    rows = d1.query(sql(
        "SELECT q.slug, q.os, q.reason, q.first_event_id, q.queued_at, e.reporter, e.arch, e.error_excerpt, "
        "e.ts AS reported_at FROM reverify_queue q LEFT JOIN events e ON e.id = q.first_event_id "
        "WHERE q.done_at IS NULL ORDER BY q.queued_at, q.slug LIMIT ?1", limit))
    return [Report(**row) for row in rows]


def mark_done(d1: Database, report: Report, now: datetime) -> int:
    return d1.execute(sql("UPDATE reverify_queue SET done_at = ?4 WHERE slug = ?1 AND os = ?2 "
                          "AND first_event_id = ?3 AND done_at IS NULL",
                          report.slug, report.os, report.first_event_id, timestamp(now)))


@dataclass
class Result:
    slug: str
    os: str
    event_id: str
    reporter: str | None
    # rewritten | unchanged | not_passed | kept | no_record | retry | gave_up
    outcome: str
    level: str | None = None
    run_id: str | None = None
    run_os: str | None = None
    old_steps: list[str] | None = None
    new_steps: list[str] | None = None
    diff: str | None = None
    diff_path: str | None = None
    commit: str | None = None
    done: bool = False
    seconds: float = 0.0
    cost_usd: float = 0.0
    box_usd: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class Steps:
    """github: .repo(full_name), .details(repo); extract(candidate, run_id) -> rows;
    verify(task, log) -> verify.pipeline.Outcome (nothing written back)."""

    github: Any
    extract: Callable[[dict[str, Any], str], list[dict[str, Any]]]
    verify: Callable[[VerifyTask, Callable[[str], None]], Any]


def live_steps(*, runner: str = "modal") -> Steps:
    from pickfit.discover.github import GitHub, github_token
    from pickfit.extract import extract_with_retries
    from pickfit.verify.agent import AgentLimits
    from pickfit.verify.cli import LIFETIME_MARGIN_S, box_factory
    from pickfit.verify.pipeline import verify_task
    from pickfit.watch import EXTRACT_EFFORT

    limits = AgentLimits()
    make_box = box_factory(runner, int(limits.max_seconds) + LIFETIME_MARGIN_S)
    ready: list[bool] = []

    def verify(task: VerifyTask, log: Callable[[str], None]) -> Any:
        if runner == "modal" and not ready:
            from pickfit.verify.modal_box import ensure_published_image

            ensure_published_image()
            ready.append(True)
        return verify_task(task, make_box, model=MODEL, limits=limits, log=log, write=False)

    return Steps(github=GitHub(github_token()),
                 extract=lambda c, run_id: extract_with_retries(c, model=MODEL, run_id=run_id,
                                                                reasoning_effort=EXTRACT_EFFORT),
                 verify=verify)


def commands(guide: InstallGuide | None) -> list[str] | None:
    return [" ".join(step.command.split()) for step in guide.steps] if guide else None


def followed_guide(record: SoftwareRecord, os_name: str) -> tuple[str, InstallGuide] | None:
    """The guide get_install_guide gave a user on os_name (worker/src/catalog.ts bestGuide):
    that OS's run-backed guide if any, else the strongest, newest one."""
    runs = {run.id: run for run in record.verification.runs}
    guides = [(name, guide) for name, guide in record.install.guides()
              if guide.basis in ("replayed", "human") and guide.run_id in runs]
    if not guides:
        return None

    def rank(item: tuple[str, InstallGuide]) -> tuple[int, int, float]:
        run = runs[item[1].run_id or ""]
        level = LEVEL_ORDER.index(run.level) if run.level in LEVEL_ORDER else len(LEVEL_ORDER)
        return (0 if run.os == os_name else 1, level, -run.checked_at.timestamp())
    return min(guides, key=rank)


class Reverifier:
    def __init__(self, d1: Database, steps: Steps, *, data_dir: Path, runs_dir: Path, db_path: Path,
                 commit: bool = True, clock: Callable[[], datetime] | None = None,
                 log: Callable[[str], None] = print, git_lock: threading.Lock | None = None) -> None:
        self.d1 = d1
        self.steps = steps
        self.data_dir = data_dir
        self.out_dir = runs_dir / "reverify"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.db = PipelineDB(db_path)
        self.commit = commit
        self.clock = clock or (lambda: taipei_now())
        self.log = log
        self.git_lock = git_lock or threading.Lock()  # shared with pickfit watch's commits

    def _attempts_path(self) -> Path:
        return self.out_dir / "attempts.json"

    def _attempts(self) -> dict[str, int]:
        try:
            return json.loads(self._attempts_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _count_attempt(self, event_id: str) -> int:
        attempts = self._attempts()
        attempts[event_id] = attempts.get(event_id, 0) + 1
        self._attempts_path().write_text(json.dumps(attempts, indent=2) + "\n", encoding="utf-8")
        return attempts[event_id]

    def pending_count(self) -> int:
        return len(pending(self.d1, 1))

    def run(self, limit: int = 5, blocked: Callable[[], str | None] | None = None) -> list[Result]:
        """Re-verify up to `limit` pending reports; `blocked` (a budget check) can stop before each one."""
        results = []
        for report in pending(self.d1, limit):
            why = blocked() if blocked else None
            if why:
                self.log(f"[reverify] not starting {report.slug}/{report.os}: {why}")
                break
            results.append(self.one(report))
        return results

    def one(self, report: Report) -> Result:
        """Re-verify one queued report; never raises."""
        began = time.monotonic()
        log = lambda line: self.log(f"[{report.slug}/{report.os}] {line}")  # noqa: E731
        result = Result(slug=report.slug, os=report.os, event_id=report.first_event_id, reporter=report.reporter,
                        outcome="retry")
        log(f"reverify · {report.reason} on {report.os}{'/' + report.arch if report.arch else ''} · "
            f"event {report.first_event_id} · reporter {report.reporter or 'unknown'}")
        try:
            self._check(report, result, log)
        except Exception as err:  # noqa: BLE001 - one bad row must not stop the queue
            result.outcome = "retry"
            result.notes.append(f"{type(err).__name__}: {str(err)[:300]}")
            log(f"problem: {result.notes[-1]}")
        if result.outcome == "retry" and self._count_attempt(report.first_event_id) >= MAX_ATTEMPTS:
            result.outcome = "gave_up"
            result.notes.append(f"no conclusive run after {MAX_ATTEMPTS} tries; a person should look")
        if result.outcome != "retry":
            result.done = mark_done(self.d1, report, self.clock()) == 1
        result.seconds = round(time.monotonic() - began, 1)
        stamp = self.clock().strftime("%Y%m%d-%H%M%S")
        path = self.out_dir / f"{report.slug}-{report.os}-{stamp}.json"
        path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log(f"result · {result.outcome} · level {result.level or '-'} · {result.seconds:.0f}s · "
            f"model ${result.cost_usd:.4f} · box ${result.box_usd:.4f}"
            + "".join(f"\n  note: {n}" for n in result.notes))
        if result.diff:
            log(f"git diff ({result.diff_path}):\n{result.diff}")
        return result

    def _check(self, report: Report, result: Result, log: Callable[[str], None]) -> None:
        path = self.data_dir / f"{report.slug}.json"
        if not path.exists():
            result.outcome = "no_record"
            result.notes.append(f"{path.name} is not in {self.data_dir}")
            return
        record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
        item = self.steps.github.repo(record.repo.full_name)
        if item is None or repo_key(item["id"]) != record.repo_id:
            result.outcome = "gave_up"
            result.notes.append(f"{record.repo.full_name} is gone from GitHub or is another repository now")
            return
        repo = normalize_repo(item)
        details = self.steps.github.details(repo)
        self.db.upsert_repo(repo, category=record.category, query_id=f"reverify:{report.first_event_id}")
        self.db.save_details(record.repo_id, details, pushed_at=repo.get("pushed_at"))
        candidate = self.db.candidate(record.repo_id)
        run_id = f"reverify-{report.slug[:40]}-{self.clock().strftime('%Y%m%d-%H%M%S')}"
        extraction = self._extraction(candidate, run_id, result)

        followed = followed_guide(record, report.os)
        task = VerifyTask(slug=record.slug, repo_url=record.repo.url, readme=candidate["readme"] or "",
                          extraction=ExtractionResult.model_validate(extraction["result"]),
                          reported=ReportedFailure(stage=report.reason, os=report.os, arch=report.arch,
                                                   error_excerpt=report.error_excerpt,
                                                   steps=tuple(commands(followed[1]) or []) if followed else (),
                                                   guide_os=followed[0] if followed else None))
        outcome = self.steps.verify(task, log)
        run = outcome.run
        result.level, result.run_id, result.run_os = run.level, outcome.run_id, run.os
        result.cost_usd += outcome.cost_usd
        result.box_usd += getattr(outcome, "box_usd", 0.0)
        if report.os != run.os:
            result.notes.append(f"reported on {report.os}; this box runs {run.os}, so {report.os} itself "
                                "was not re-run")
        stop = stop_reason(outcome)
        if stop in NEVER_RAN:
            result.notes.append(f"the agent never got going ({stop})")
            return  # stays pending: retry
        guide = getattr(record.install, run.os)
        result.old_steps = commands(guide) if guide and guide.basis != "readme_claim" else None
        if not (is_passed(run.level) and run.replayed):
            result.outcome = "not_passed"
            result.notes.append(f"the fresh run did not pass ({run.level}"
                                f"{', ' + run.unverified_reason if run.unverified_reason else ''}); the record is "
                                "unchanged (the pipeline never writes failed), so a person should check")
            return
        result.new_steps = commands(install_guide(run))
        if result.new_steps == result.old_steps:
            result.outcome = "unchanged"
            result.notes.append(f"the recorded {run.os} steps still work in a fresh box")
            return
        with self.git_lock:
            self._write(report, record, outcome, path, result)

    def _write(self, report: Report, record: SoftwareRecord, outcome: Any, path: Path, result: Result) -> None:
        run = outcome.run
        written, note = write_back(run, record.slug, self.data_dir)
        result.notes.append(f"write-back: {note}")
        if not written:
            result.outcome = "kept"
            return
        result.outcome = "rewritten"
        result.diff = git(self.data_dir, "diff", "--", path.name)
        diff_path = self.out_dir / f"{report.slug}-{report.os}-{self.clock().strftime('%Y%m%d-%H%M%S')}.diff"
        diff_path.write_text(result.diff, encoding="utf-8")
        result.diff_path = str(diff_path)
        if self.commit:
            git(self.data_dir, "add", "--", path.name)
            git(self.data_dir, "commit", "-q", "-m",
                f"Re-verify {record.slug} after a reported {report.reason} on {report.os}\n\n"
                f"Event {report.first_event_id} (reporter {report.reporter or 'unknown'}); fresh run {outcome.run_id}, "
                f"{run.level}, replayed. The {run.os} install steps changed.", "--", path.name)
            result.commit = git(self.data_dir, "rev-parse", "--short", "HEAD").strip()

    def _extraction(self, candidate: dict[str, Any], run_id: str, result: Result) -> dict[str, Any]:
        from pickfit.extract import build_sources, sources_sha

        current = sources_sha(build_sources(candidate))
        stored = [e for model in EXTRACTION_MODELS
                  if (e := self.db.last_extraction(candidate["repo_id"], model)) and e["status"] in DONE_EXTRACTIONS]
        same = next((e for e in stored if e["sources_sha"] == current), None)
        if same:
            return same
        rows = self.steps.extract(candidate, run_id)
        for row in rows:
            self.db.save_extraction(**row)
            result.cost_usd += row["cost_usd"]
        if rows and rows[-1]["status"] in DONE_EXTRACTIONS:
            fresh = self.db.last_extraction(candidate["repo_id"], MODEL)
            assert fresh is not None
            return fresh
        if stored:  # the README changed but could not be read again: the older reading still says what the tool is
            result.notes.append("extraction of the current README failed; used the stored one")
            return stored[0]
        raise RuntimeError("no extraction of this repository")
