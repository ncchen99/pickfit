"""`pickfit watch` (P5.2): turn submit_software rows into records, one repository at a time.

Every `interval_s` (60 s) the watcher reads queued rows of the Worker's D1
`submissions` table, claims each one (queued -> reading, only while it is still
queued, so two watchers never take the same row) and runs the single-record
pipeline:

  GitHub details -> rules -> prescreen (Muse Spark Open on Baseten, review by
  muse-spark-1.3) -> extraction (muse-spark-1.3) -> record -> verification on
  Modal (agent, fresh-box replay, judge) -> scores -> known vulnerabilities (OSV.dev, no model call)

The record is built in runs/watch/<submission>/software/, so data/software
changes only when a record is finished: then it is copied in and committed
alone (one commit per record; a failed commit puts data/software back). From
that moment the job is `landed`: a later try of the same submission only
reports what is already there, it never runs the pipeline again or calls its
own record "already listed". D1 follows each step: reading -> verifying ->

- verifying with READY_REASON: every check passed and the commit is made;
  nothing is deployed unless `publish` (`--publish`) is on;
- listed: deployed, either by `--publish` or by anyone's `pickfit publish`
  (seen when the live Worker's data_sha256 equals data/software's), so
  find_software can recommend it;
- listed_unverified: committed without a verified install (never recommended);
- rejected: the reason is written by this program, never by a model, since it
  goes back to whoever submitted.

Refused before any model call: URLs that are not a GitHub repository, test
fixtures, private or missing repositories, repositories already in
data/software (they get the existing record's status) or taken by another
submission (also one still in flight), and whatever the rules reject. Any star
count is taken: pickfit lists any software, not only lesser-known tools.

Limits: at most SUBMIT_HOURLY_CAP submissions start per rolling hour (the cap
the Worker applies to intake, from wrangler.jsonc); a submission starts only
when the pipeline's Meta budget (daily and total, in the shared ledger) and
the Baseten budget have room for its worst case; `max_usd` caps the whole
watch run. Every job's timings, counted from submitted_at, land in
runs/watch/jobs/<submission>.json.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pickfit.d1 import D1Error, Database, sql, timestamp
from pickfit.discover.github import normalize_repo
from pickfit.discover.rules import RULES_VERSION, classify
from pickfit.discover.store import PipelineDB, repo_key
from pickfit.ledger import TAIPEI, BudgetExceeded, Ledger, taipei_now
from pickfit.schema import LISTED_CATEGORIES, TOOL_KINDS, ExtractionResult, SoftwareRecord, is_passed
from pickfit.verify.batch import NEVER_RAN, not_in_box
from pickfit.verify.task import VerifyTask

MODEL = "muse-spark-1.3"
EXTRACT_EFFORT = "minimal"
COVERED = LISTED_CATEGORIES  # dev_cli, local_ai, mcp_server
# Category "other" is taken too when the kind is software people install and run (desktop and web apps, CLI tools
# and the like, as the directory already lists them); libraries and non-software stay out (11/3).
OTHER_KINDS = TOOL_KINDS
DEFAULT_INTERVAL_S = 60
DEFAULT_CONCURRENCY = 2
DEFAULT_MAX_USD = 5.0
DEFAULT_HOURLY_CAP = 20  # the Worker's default when wrangler.jsonc has none
MAX_ATTEMPTS = 3
STALE_AFTER = timedelta(hours=1)  # a row left in reading/verifying this long lost its watcher
# Room a submission needs before it starts: prescreen review $0.05 + extraction $0.20 +
# verification $0.50 + rubric $0.10 (each stage's own cap), rounded up.
WORST_CASE_META_USD = 1.0
WORST_CASE_BASETEN_USD = 0.05
REASON_MAX = 300  # submissions.reason CHECK
DONE_EXTRACTIONS = ("ok", "quotes_dropped")
READY_REASON = "Installed, replayed in a fresh sandbox and checked; goes live at pickfit's next publish."

# The Worker's normalization (worker/src/submit.ts), so both sides agree on what a repository URL is.
_NOT_OWNERS = frozenset(
    "about apps blog collections contact customer-stories enterprise events explore features github-copilot "
    "issues login marketplace new notifications orgs organizations pricing pulls readme search security "
    "settings site sponsors topics trending users".split())
_GITHUB_REPO = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/"
                          r"([A-Za-z0-9._-]{1,100})(?:[/?#].*)?", re.I)


def normalize_repo_url(url: str) -> str | None:
    """https://github.com/<owner>/<repo>, lower case, or None when it is not a repository on github.com."""
    match = _GITHUB_REPO.fullmatch(url.strip())
    if not match:
        return None
    owner = match.group(1).lower()
    repo = re.sub(r"\.git$", "", match.group(2), flags=re.I).lower()
    if owner in _NOT_OWNERS or not repo or set(repo) == {"."}:
        return None
    return f"https://github.com/{owner}/{repo}"


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= REASON_MAX else text[:REASON_MAX - 1] + "…"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def stop_reason(outcome: Any) -> str | None:
    """Why the verification agent stopped (report.json in the run's evidence), or None."""
    try:
        report = json.loads((Path(outcome.evidence_dir) / "report.json").read_text(encoding="utf-8"))
        return report.get("stop_reason")
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def budget_blocked(needs: list[tuple[str, Ledger | None, float]]) -> str | None:
    """Why a job needing `need` dollars from each ledger may not start (daily or total cap), or None."""
    for name, ledger, need in needs:
        if ledger is None:
            continue
        spend = ledger.spend_summary()
        room = min(spend["daily_cap_usd"] - spend["today_usd"], spend["total_cap_usd"] - spend["total_usd"])
        if room < need:
            return f"{name} budget: ${room:.2f} left today or in total, a job may need ${need:.2f}"
    return None


# --- D1 ---------------------------------------------------------------------------


def queued(d1: Database, limit: int) -> list[dict[str, Any]]:
    """Queued repository submissions, oldest first. Website rows (a hosted web app) stay queued for the web
    pipeline. The submitter's note is never read."""
    return d1.query(sql("SELECT id, url, submitted_at FROM submissions WHERE status = 'queued' "
                        "AND url LIKE 'https://github.com/%' ORDER BY submitted_at, id LIMIT ?1", limit))


def claim(d1: Database, submission_id: str, now: datetime) -> bool:
    return len(d1.query(sql("UPDATE submissions SET status = 'reading', reason = NULL, updated_at = ?2 "
                            "WHERE id = ?1 AND status = 'queued' RETURNING id", submission_id, timestamp(now)))) == 1


def set_status(d1: Database, submission_id: str, status: str, now: datetime, *, slug: str | None = None,
               reason: str | None = None) -> None:
    d1.execute(sql("UPDATE submissions SET status = ?2, slug = ?3, reason = ?4, updated_at = ?5 WHERE id = ?1",
                   submission_id, status, slug, _clip(reason) if reason else None, timestamp(now)))


def requeue_stale(d1: Database, now: datetime, running: set[str]) -> list[str]:
    """Rows a crashed watcher left in reading or verifying go back to queued (not ready ones)."""
    rows = d1.query(sql("SELECT id FROM submissions WHERE status IN ('reading', 'verifying') "
                        "AND updated_at < ?1 AND (reason IS NULL OR reason <> ?2)",
                        timestamp(now - STALE_AFTER), READY_REASON))
    back = [r["id"] for r in rows if r["id"] not in running]
    for sid in back:
        d1.execute(sql("UPDATE submissions SET status = 'queued', reason = NULL, updated_at = ?2 "
                       "WHERE id = ?1 AND status IN ('reading', 'verifying')", sid, timestamp(now)))
    return back


# --- one job ------------------------------------------------------------------------


@dataclass
class Job:
    submission_id: str
    url: str
    submitted_at: str
    started_at: str
    failures: int = 0  # earlier tries that ended in a temporary problem (budget waits do not count)
    full_name: str | None = None
    repo_id: str | None = None
    slug: str | None = None
    status: str = "reading"  # the D1 status last written
    reason: str | None = None
    result: str | None = None  # ready | listed | listed_unverified | rejected | retry | waiting
    level: str | None = None
    run_id: str | None = None
    landed: bool = False  # the record is in data/software (and committed, unless --no-commit)
    commit: str | None = None
    publish_check: list[str] | None = None  # problems `pickfit publish --dry-run` would report
    stages: dict[str, float] = field(default_factory=dict)  # seconds
    cost_usd: dict[str, float] = field(default_factory=dict)  # meta, baseten, box
    ready_at: str | None = None
    listed_at: str | None = None
    seconds_to_ready: float | None = None  # from submitted_at
    seconds_to_listed: float | None = None
    notes: list[str] = field(default_factory=list)

    def spent(self, kind: str, usd: float) -> None:
        self.cost_usd[kind] = round(self.cost_usd.get(kind, 0.0) + (usd or 0.0), 6)

    def summary(self) -> str:
        took = f" · {self.seconds_to_ready:.0f}s from submission to ready" if self.seconds_to_ready else ""
        if self.seconds_to_listed:
            took += f", {self.seconds_to_listed:.0f}s to listed"
        stages = ", ".join(f"{k} {v:.0f}s" for k, v in self.stages.items())
        cost = ", ".join(f"{k} ${v:.4f}" for k, v in sorted(self.cost_usd.items()))
        return (f"{self.submission_id} · {self.full_name or self.url} · {self.result} ({self.status})"
                f"{' · ' + self.slug if self.slug else ''}{took} · {stages or '-'} · {cost or '$0'}"
                + (f" · {self.reason}" if self.reason and self.result != "ready" else ""))


class Rejected(Exception):
    """The submission is refused for good; the message goes back to the submitter."""


class Retry(Exception):
    """A temporary problem: the submission goes back to the queue (up to MAX_ATTEMPTS tries)."""


class _AlreadyListed(Exception):
    """The repository is already a record: its status is written and nothing else happens."""


@dataclass
class Steps:
    """The networked and paid parts of the pipeline; tests replace them with fakes.

    github: .repo(full_name) -> repo JSON or None, .details(normalized repo) -> details
    prescreen(candidate, run_id) -> prescreen rows (screen, maybe review)
    extract(candidate, run_id) -> extraction rows, one per attempt
    verify(task, data_dir, log) -> verify.pipeline.Outcome, written back into data_dir
    score(data_dir, slug) -> None, or the error that kept the record from being scored
    display: verify gives a GUI app (kind desktop_app) a box with a virtual display
    security(data_dir, slug) -> None, or why the known-vulnerability check could not run; the record stays "unchecked"
    """

    github: Any
    prescreen: Callable[[dict[str, Any], str], list[dict[str, Any]]]
    extract: Callable[[dict[str, Any], str], list[dict[str, Any]]]
    verify: Callable[[VerifyTask, Path, Callable[[str], None]], Any]
    score: Callable[[Path, str], str | None]
    display: bool = False
    security: Callable[[Path, str], str | None] | None = None


def live_steps(*, runner: str = "modal") -> Steps:
    """The real pipeline: GitHub, Baseten and Meta through the ledger, Modal boxes."""
    from pickfit.discover.github import GitHub, github_token
    from pickfit.extract import extract_with_retries
    from pickfit.prescreen import screen_and_review
    from pickfit.score import score_records
    from pickfit.verify.agent import AgentLimits
    from pickfit.verify.cli import LIFETIME_MARGIN_S, box_factory
    from pickfit.verify.pipeline import verify_task

    limits = AgentLimits()
    lifetime = int(limits.max_seconds) + LIFETIME_MARGIN_S
    display = runner == "modal"
    boxes = {False: box_factory(runner, lifetime),
             True: box_factory(runner, lifetime, display=True) if display else None}
    image_lock = threading.Lock()
    images: set[bool] = set()

    def verify(task: VerifyTask, data_dir: Path, log: Callable[[str], None]) -> Any:
        gui = display and task.extraction.kind.value == "desktop_app"
        if runner == "modal":
            with image_lock:  # build or fetch each image once, not in every thread
                if gui not in images:
                    from pickfit.verify.modal_box import ensure_published_image

                    ensure_published_image(display=gui)
                    images.add(gui)
        return verify_task(task, boxes[gui], model=MODEL, limits=limits, log=log, write=True, data_dir=data_dir)

    def score(data_dir: Path, slug: str) -> str | None:
        from pickfit.discover.run import pipeline_db_path

        summary = score_records(data_dir, db_path=pipeline_db_path(), model=MODEL, slugs=[slug], concurrency=1)
        return summary.errors.get(slug)

    def security(data_dir: Path, slug: str) -> str | None:
        from pickfit.security import Advisories, check, write_security

        path = data_dir / f"{slug}.json"
        now = taipei_now()
        try:
            write_security(path, check(json.loads(path.read_text(encoding="utf-8")), Advisories(), now=now), now)
        except Exception as err:  # noqa: BLE001 - OSV.dev or a clone being down must not lose a finished run
            return f"{type(err).__name__}: {str(err)[:200]}"
        return None

    return Steps(github=GitHub(github_token()),
                 prescreen=lambda c, run_id: screen_and_review(c, run_id=run_id),
                 extract=lambda c, run_id: extract_with_retries(c, model=MODEL, run_id=run_id,
                                                                reasoning_effort=EXTRACT_EFFORT),
                 verify=verify, score=score, display=display, security=security)


def hourly_cap(worker_dir: Path) -> int:
    """SUBMIT_HOURLY_CAP from wrangler.jsonc, the same number the Worker applies to intake."""
    from pickfit.publish import check_wrangler

    _, variables = check_wrangler(worker_dir)
    try:
        return int(variables.get("SUBMIT_HOURLY_CAP", DEFAULT_HOURLY_CAP))
    except (TypeError, ValueError):
        return DEFAULT_HOURLY_CAP


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def live_data_sha(worker_dir: Path) -> Callable[[], str | None]:
    """data_sha256 of what the deployed Worker serves (GET / on its first ALLOWED_HOSTS name), or None."""
    from pickfit.publish import check_wrangler

    _, variables = check_wrangler(worker_dir)
    host = str(variables.get("ALLOWED_HOSTS", "")).split(",")[0].strip()

    def fetch() -> str | None:
        if not host:
            return None
        # Cloudflare answers Python's default user agent with 403.
        request = urllib.request.Request(f"https://{host}/", headers={"User-Agent": "pickfit-watch"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read(100_000)).get("data_sha256")
        except (OSError, ValueError):
            return None
    return fetch


@dataclass
class Settings:
    data_dir: Path
    runs_dir: Path
    db_path: Path
    worker_dir: Path
    commit: bool = True
    publish: bool = False
    hourly_cap: int = DEFAULT_HOURLY_CAP
    max_usd: float = DEFAULT_MAX_USD
    concurrency: int = DEFAULT_CONCURRENCY
    interval_s: float = DEFAULT_INTERVAL_S


class Watcher:
    def __init__(self, d1: Database, steps: Steps, settings: Settings, *, meta_ledger: Ledger | None = None,
                 baseten_ledger: Ledger | None = None, clock: Callable[[], datetime] | None = None,
                 log: Callable[[str], None] = print, publish_fn: Callable[..., int] | None = None,
                 reverifier: Any = None, live_sha: Callable[[], str | None] | None = None) -> None:
        if settings.publish and not settings.commit:
            raise ValueError("--publish needs commits: pickfit publish deploys committed data only")
        if settings.publish and reverifier is not None:
            raise ValueError("--publish with --reverify would deploy steps rewritten from a user's report "
                             "unread; read the diff, then run pickfit publish yourself")
        self.d1 = d1
        self.steps = steps
        self.s = settings
        self.meta_ledger = meta_ledger
        self.baseten_ledger = baseten_ledger
        self.clock = clock or (lambda: taipei_now())
        self.log = log
        self._publish_fn = publish_fn
        self.db = PipelineDB(settings.db_path)
        self.jobs_dir = settings.runs_dir / "watch" / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._git_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._running: dict[str, Future[Job]] = {}
        self._slugs_in_flight: set[str] = set()
        self._repos_in_flight: dict[str, str] = {}  # repo_id -> the submission URL taking it
        self._live_sha = live_sha or (lambda: None)
        self._log_lock = threading.Lock()
        self.spent_usd = 0.0
        self.reverifier = reverifier  # pickfit.reverify.Reverifier: also take the reverify queue
        self._reverify: Future[Any] | None = None
        if reverifier is not None:
            reverifier.git_lock = self._git_lock

    # -- bookkeeping

    def now(self) -> datetime:
        return self.clock().astimezone(TAIPEI)

    def _say(self, prefix: str) -> Callable[[str], None]:
        def say(line: str) -> None:
            with self._log_lock:
                self.log(f"[{prefix}] {line}")
        return say

    def _job_path(self, submission_id: str) -> Path:
        return self.jobs_dir / f"{submission_id}.json"

    def _saved(self, submission_id: str) -> Job | None:
        try:
            return Job(**json.loads(self._job_path(submission_id).read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def _save(self, job: Job) -> None:
        path = self._job_path(job.submission_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(job), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def saved_jobs(self) -> list[Job]:
        jobs = []
        for path in sorted(self.jobs_dir.glob("*.json")):
            job = self._saved(path.stem)
            if job:
                jobs.append(job)
        return jobs

    @contextmanager
    def _stage(self, job: Job, name: str) -> Iterator[None]:
        began = time.monotonic()
        try:
            yield
        finally:
            job.stages[name] = round(job.stages.get(name, 0.0) + time.monotonic() - began, 1)

    def _status(self, job: Job, status: str, *, reason: str | None = None) -> None:
        set_status(self.d1, job.submission_id, status, self.now(), slug=job.slug, reason=reason)
        job.status, job.reason = status, reason

    # -- gate: hourly cap and budgets

    def blocked(self) -> str | None:
        """Why no new submission may start now, or None."""
        hour_ago = self.now() - timedelta(hours=1)
        with self._state_lock:
            running = set(self._running)
        started = {j.submission_id for j in self.saved_jobs() if _parse_time(j.started_at) >= hour_ago} | running
        if len(started) >= self.s.hourly_cap:
            return (f"hourly cap: {len(started)} submissions started in the last hour "
                    f"(SUBMIT_HOURLY_CAP {self.s.hourly_cap})")
        if self.spent_usd + (len(running) + 1) * WORST_CASE_META_USD > self.s.max_usd:
            return f"this run's cap: ${self.spent_usd:.2f} spent of --max-usd {self.s.max_usd:.2f}"
        jobs = len(running) + 1  # the ones in flight may still spend their worst case
        return budget_blocked([("Meta pipeline", self.meta_ledger, WORST_CASE_META_USD * jobs),
                               ("Baseten", self.baseten_ledger, WORST_CASE_BASETEN_USD * jobs)])

    # -- the pipeline for one submission

    def process(self, sub: dict[str, Any]) -> Job:
        """Run one claimed submission to its end; never raises."""
        sid = sub["id"]
        log = self._say(sid)
        earlier = self._saved(sid)
        resume = bool(earlier and earlier.landed and earlier.slug and
                      (self.s.data_dir / f"{earlier.slug}.json").exists())
        if resume:
            job = earlier
            job.notes.append("landed on an earlier try: reporting it, not running the pipeline again")
        else:
            job = Job(submission_id=sid, url=sub["url"], submitted_at=sub["submitted_at"],
                      started_at=self.now().isoformat(), failures=earlier.failures if earlier else 0)
        log(f"start · {job.url} · try {job.failures + 1}{' · resuming a landed record' if resume else ''}")
        try:
            if resume:
                self._report_landed(job, log)
            else:
                self._run(job, log)
        except _AlreadyListed:
            pass
        except Rejected as err:
            self._finish(job, "rejected", "rejected", str(err), log)
        except BudgetExceeded as err:
            log(f"budget: {err}")
            if err.cap.startswith("scope"):  # one stage used up its own cap: that try failed
                self._fail(job, f"budget: {err}", log)
            else:
                self._finish(job, "waiting", "queued", "Waiting for pickfit's model budget; it continues later.", log)
        except Exception as err:  # noqa: BLE001 - Retry, IndexBuildError, a bug: the row must not stay in reading
            self._fail(job, f"{type(err).__name__}: {str(err)[:300]}", log)
        finally:
            with self._state_lock:
                if job.slug:
                    self._slugs_in_flight.discard(job.slug)
                if job.repo_id and self._repos_in_flight.get(job.repo_id) == job.url:
                    self._repos_in_flight.pop(job.repo_id)
                self.spent_usd += sum(job.cost_usd.get(k, 0.0) for k in ("meta", "baseten"))
            self._save(job)
        log(f"done · {job.summary()}")
        return job

    def _fail(self, job: Job, what: str, log: Callable[[str], None]) -> None:
        job.failures += 1
        job.notes.append(what)
        log(f"problem: {what}")
        if job.failures >= MAX_ATTEMPTS and not job.landed:  # a landed record is there: keep reporting it
            self._finish(job, "rejected", "rejected",
                         f"pickfit could not finish reading this repository after {job.failures} tries.", log)
        else:
            self._finish(job, "retry", "queued", "A temporary problem; pickfit will try again.", log)

    def _finish(self, job: Job, result: str, status: str, reason: str | None, log: Callable[[str], None]) -> None:
        job.result = result
        try:
            self._status(job, status, reason=reason)
        except D1Error as err:
            job.notes.append(f"D1 status not written: {err}")
            log(f"D1 status not written: {err}")

    def _run(self, job: Job, log: Callable[[str], None]) -> None:
        url = normalize_repo_url(job.url)
        if url is None:
            raise Rejected("pickfit accepts only GitHub repository URLs, like https://github.com/owner/repo.")
        owner, name = url.removeprefix("https://github.com/").split("/")
        if owner == "fixture" or name.startswith("fixture-"):
            raise Rejected("Test fixtures are never listed.")
        with self._stage(job, "github"):
            item = self.steps.github.repo(f"{owner}/{name}")
        if item is None:
            raise Rejected("Not found on GitHub; pickfit reads public repositories only.")
        if item.get("private"):
            raise Rejected("A private repository; pickfit reads public repositories only.")
        repo = normalize_repo(item)
        job.full_name, job.repo_id = repo["full_name"], repo_key(item["id"])
        self._refuse_known(job)

        with self._stage(job, "github"):
            details = self.steps.github.details(repo)
        query_id = f"submission:{job.submission_id}"
        self.db.upsert_repo(repo, category="other", query_id=query_id)
        self.db.save_details(job.repo_id, details, pushed_at=repo.get("pushed_at"))
        candidate = self.db.candidate(job.repo_id)
        rule = classify(candidate)
        self.db.save_rules(job.repo_id, label=rule.label, passed=rule.passed, reasons=rule.reasons,
                           version=RULES_VERSION)
        if not rule.passed:
            why = [r.removeprefix("reject:") for r in rule.reasons if r.startswith("reject:")]
            raise Rejected(f"Did not pass pickfit's rules ({', '.join(why) or rule.label}).")

        run_id = f"watch-{job.submission_id.removeprefix('sub_')[:12]}-{self.now().strftime('%Y%m%d-%H%M%S')}"
        with self._stage(job, "prescreen"):
            decision = self._prescreen(candidate, run_id, job)
        if decision is not None:
            answer = (decision["review"] or decision["screen"])["result"] or {}
            if decision["keep"] is False:
                raise Rejected(f"pickfit's prescreen read it as {answer.get('kind') or 'something'}, "
                               "not software people install and run.")
            if answer.get("category") in COVERED:  # the record falls back to it when the README does not say
                self.db.upsert_repo(repo, category=answer["category"], query_id=query_id)
                candidate = self.db.candidate(job.repo_id)
        else:
            job.notes.append("prescreen failed; extraction decides")

        with self._stage(job, "extract"):
            extraction = self._extract(candidate, run_id, job)
        record_dir = self.s.runs_dir / "watch" / job.submission_id / "software"
        record = self._write_record(job, candidate, extraction, record_dir)
        log(f"record {job.slug} [{record.category}/{record.kind}]")
        self._status(job, "verifying")

        ex = ExtractionResult.model_validate(extraction["result"])
        why = not_in_box(ex, display=self.steps.display)
        not_passed = f"pickfit's Linux sandbox cannot run it ({why})" if why else None
        if why:
            job.notes.append(f"not verified: {why}")
            log(f"no sandbox run: {why}")
        else:
            task = VerifyTask(slug=job.slug, repo_url=record.repo.url, readme=candidate["readme"], extraction=ex,
                              category=record.category)
            with self._stage(job, "verify"):
                outcome = self.steps.verify(task, record_dir, log)
            job.run_id, job.level = outcome.run_id, outcome.run.level
            job.spent("meta", outcome.cost_usd)
            job.spent("box", getattr(outcome, "box_usd", 0.0))
            stop = stop_reason(outcome)
            if stop in NEVER_RAN:
                raise Retry(f"verification never got going ({stop})")
            run = outcome.run
            not_passed = f"the sandbox run did not pass ({run.unverified_reason or run.level})"
        with self._stage(job, "score"):
            error = self.steps.score(record_dir, job.slug)
        if error:
            raise Retry(f"scores: {error}")
        self._security(job, record_dir, log)
        self._land(job, record_dir, not_passed, log)

    def _security(self, job: Job, record_dir: Path, log: Callable[[str], None]) -> None:
        """The known-vulnerability check, as `pickfit security --write` does it: a finding caps quality, a malicious
        package stops the listing, and a check that could not run leaves the record marked unchecked."""
        if self.steps.security is None:
            return
        with self._stage(job, "security"):
            error = self.steps.security(record_dir, job.slug)
        if error:
            job.notes.append(f"security check did not run: {error}")
            log(f"security check did not run: {error}")
            return
        data = json.loads((record_dir / f"{job.slug}.json").read_text(encoding="utf-8"))
        log(f"security: {(data.get('security') or {}).get('status')}")
        if data.get("status") == "hidden":
            raise Rejected("A package it installs is reported as malicious on OSV.dev.")

    def _refuse_known(self, job: Job) -> None:
        """A repository another submission took (or is taking) is refused; one already in data/software
        takes that record's status."""
        for other in self.saved_jobs():
            if other.repo_id == job.repo_id and other.submission_id != job.submission_id and \
                    (other.landed or other.result not in (None, "retry", "waiting", "rejected")):
                raise Rejected(f"Same repository as an earlier submission ({other.url}).")
        with self._state_lock:
            taking = self._repos_in_flight.get(job.repo_id)
            if taking and taking != job.url:
                raise Rejected(f"Same repository as another submission pickfit is reading now ({taking}).")
            self._repos_in_flight[job.repo_id] = job.url
        for path in sorted(self.s.data_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("repo_id") != job.repo_id:
                continue
            job.slug = data["slug"]
            if data.get("status") != "listed":
                raise Rejected("Reviewed before and not listed.")
            verified = is_passed((data.get("verification") or {}).get("level") or "")
            job.result = "listed" if verified else "listed_unverified"
            self._status(job, job.result, reason="Already in pickfit's directory.")
            raise _AlreadyListed()

    def _prescreen(self, candidate: dict[str, Any], run_id: str, job: Job) -> dict[str, Any] | None:
        from pickfit.prescreen import build_sources, sources_sha

        done = self.db.prescreen_decisions().get(candidate["repo_id"])
        if done and done["screen"] and done["sources_sha"] == sources_sha(build_sources(candidate)):
            job.notes.append("prescreen reused")
            return done
        for row in self.steps.prescreen(candidate, run_id):
            self.db.save_prescreen(**row)
            job.spent("baseten" if row["role"] == "screen" else "meta", row["cost_usd"])
        return self.db.prescreen_decisions().get(candidate["repo_id"])

    def _extract(self, candidate: dict[str, Any], run_id: str, job: Job) -> dict[str, Any]:
        from pickfit.extract import build_sources, sources_sha

        last = self.db.last_extraction(candidate["repo_id"], MODEL)
        if last and last["status"] in DONE_EXTRACTIONS and last["sources_sha"] == sources_sha(build_sources(candidate)):
            job.notes.append("extraction reused")
            return last
        rows = self.steps.extract(candidate, run_id)
        for row in rows:
            self.db.save_extraction(**row)
            job.spent("meta", row["cost_usd"])
        final = rows[-1] if rows else None
        if final is None or final["status"] not in DONE_EXTRACTIONS:
            raise Retry(f"extraction {final['status'] if final else 'did not run'}")
        last = self.db.last_extraction(candidate["repo_id"], MODEL)
        assert last is not None
        return last

    def _write_record(self, job: Job, candidate: dict[str, Any], extraction: dict[str, Any],
                      record_dir: Path) -> SoftwareRecord:
        from pydantic import ValidationError

        from pickfit.profiles import build_record, render, slugify

        with self._state_lock:
            taken = {p.stem for p in self.s.data_dir.glob("*.json")} | self._slugs_in_flight
            slug = slugify(candidate["repo"].get("name") or candidate["full_name"].split("/")[1])
            if not slug or slug in taken:
                slug = slugify(candidate["full_name"].replace("/", "-"))
            if not slug or slug in taken:
                raise Retry(f"slug {slug or '(empty)'} is taken")
            self._slugs_in_flight.add(slug)
        job.slug = slug
        try:
            record = build_record(candidate, extraction, slug=slug, now=self.now())
        except (ValueError, ValidationError) as err:
            reason = str(err).splitlines()[0]
            if reason.startswith("not_a_tool"):
                raise Rejected("pickfit lists tools people install and run; this reads as a library or "
                               "something else.") from None
            if reason == "no_summary":
                raise Rejected("pickfit could not tell from the README what the tool does.") from None
            raise Rejected("pickfit could not build a valid record from what the README says.") from None
        if record.category not in COVERED and record.kind not in OTHER_KINDS:
            raise Rejected("pickfit lists software people install and run (CLI tools, desktop and web apps, "
                           "local AI tools, MCP servers); this reads as a library or something else.")
        if record_dir.exists():
            shutil.rmtree(record_dir)
        record_dir.mkdir(parents=True)
        (record_dir / f"{slug}.json").write_text(render(record), encoding="utf-8")
        return record

    def _land(self, job: Job, record_dir: Path, not_passed: str | None, log: Callable[[str], None]) -> None:
        """Validate the finished record, copy it into data/software, commit it, report ready or unverified."""
        from pickfit.index import build_index
        from pickfit.publish import fixture_entries, plan

        built = build_index(record_dir, now=self.now())  # IndexBuildError if the record is invalid
        if fixture_entries(built.index):
            raise Rejected("Test fixtures are never listed.")
        record = SoftwareRecord.model_validate_json((record_dir / f"{job.slug}.json").read_text(encoding="utf-8"))
        passed = is_passed(record.verification.level) and any(
            guide.basis == "replayed" for _, guide in record.install.guides())
        target = self.s.data_dir / f"{job.slug}.json"
        with self._git_lock, self._stage(job, "commit"):
            for path in self.s.data_dir.glob("*.json"):  # one record per repository, or the index refuses them all
                try:
                    if json.loads(path.read_text(encoding="utf-8")).get("repo_id") == job.repo_id:
                        raise Rejected(f"Already in pickfit's directory as {path.stem}.")
                except (OSError, ValueError):
                    continue
            shutil.copyfile(record_dir / f"{job.slug}.json", target)
            try:
                if self.s.commit:
                    took = (self.now() - _parse_time(job.submitted_at)).total_seconds()
                    git(self.s.data_dir, "add", "--", target.name)
                    git(self.s.data_dir, "commit", "-q", "-m",
                        f"Add {job.slug} from a submission (pickfit watch)\n\n{job.url}\n"
                        f"Submission {job.submission_id}; verification {record.verification.level}"
                        f"{', replayed' if passed else ''}; {took:.0f}s after submission.", "--", target.name)
                    job.commit = git(self.s.data_dir, "rev-parse", "--short", "HEAD").strip()
            except Exception:  # nothing half-done stays behind: the next try starts from a clean data/software
                if self.s.commit:
                    subprocess.run(["git", "reset", "-q", "--", target.name], cwd=self.s.data_dir,
                                   capture_output=True)
                target.unlink(missing_ok=True)
                raise
            job.landed = True
            self._save(job)  # from here on a failed status write resumes instead of running again
            job.publish_check = plan(self.s.data_dir, self.s.worker_dir, allow_dirty=not self.s.commit).problems
        self._report_landed(job, log, not_passed)

    def _report_landed(self, job: Job, log: Callable[[str], None], not_passed: str | None = None) -> None:
        """Write the D1 status a landed record has: ready (or listed once deployed), or listed_unverified."""
        record = SoftwareRecord.model_validate_json((self.s.data_dir / f"{job.slug}.json").read_text(encoding="utf-8"))
        job.level = record.verification.level
        passed = is_passed(record.verification.level) and any(
            guide.basis == "replayed" for _, guide in record.install.guides())
        if not passed:
            job.result = "listed_unverified"
            why = not_passed or f"the sandbox run did not pass ({record.verification.unverified_reason or job.level})"
            self._status(job, "listed_unverified", reason=f"Added without a verified install: {why}.")
            return
        if job.listed_at:  # deployed on an earlier try; only its status write failed
            job.result = "listed"
            self._status(job, "listed", reason=None)
            return
        job.ready_at = job.ready_at or self.now().isoformat()
        job.seconds_to_ready = job.seconds_to_ready or round(
            (self.now() - _parse_time(job.submitted_at)).total_seconds(), 1)
        job.result = "ready"
        self._status(job, "verifying", reason=READY_REASON)
        if job.publish_check:
            log(f"publish dry run: {len(job.publish_check)} problem(s): {'; '.join(job.publish_check)[:300]}")
        else:
            log(f"ready to publish ({job.commit or 'not committed'}) · {job.seconds_to_ready:.0f}s after submission")
        if self.s.publish:
            self._publish([job], log)

    def _publish(self, jobs: list[Job], log: Callable[[str], None]) -> None:
        from pickfit.publish import publish

        deploy = self._publish_fn or publish
        with self._git_lock:
            began = time.monotonic()
            # The real publish also translates the new record's page sentences into zh-TW (pickfit/translate.py).
            extra = {} if self._publish_fn else {"translate": True}
            code = deploy(self.s.data_dir, self.s.worker_dir, out=log, **extra)
            took = round(time.monotonic() - began, 1)
        if code != 0:
            for job in jobs:
                job.notes.append(f"publish failed (exit {code})")
            log(f"publish failed (exit {code}); the records stay committed and ready")
            return
        for job in jobs:
            job.stages["publish"] = took
        self._mark_listed(jobs)
        self._mark_deployed()  # earlier ready records went out with this deploy too

    def _mark_listed(self, jobs: list[Job]) -> None:
        for job in jobs:
            job.listed_at = job.listed_at or self.now().isoformat()
            job.seconds_to_listed = round((_parse_time(job.listed_at) - _parse_time(job.submitted_at)).total_seconds(),
                                          1)
            job.result = "listed"
            self._status(job, "listed", reason=None)

    def _mark_deployed(self) -> list[str]:
        """Ready records the live Worker now serves (its data_sha256 is data/software's) become listed."""
        from pickfit.index import IndexBuildError, load_records

        with self._state_lock:
            running = set(self._running)
        ready = [j for j in self.saved_jobs() if j.result == "ready" and j.submission_id not in running]
        if not ready:
            return []
        try:
            _, local = load_records(self.s.data_dir)
        except IndexBuildError:
            return []
        if self._live_sha() != local:
            return []
        try:
            self._mark_listed(ready)
        except D1Error as err:
            self.log(f"[watch] deployed, but D1 not updated yet: {err}")
            return []
        finally:
            for job in ready:
                self._save(job)
        self.log(f"[watch] deployed, now listed: {', '.join(j.slug or j.submission_id for j in ready)}")
        return [j.submission_id for j in ready]

    # -- the loop

    def tick(self, pool: ThreadPoolExecutor) -> list[str]:
        """Start what may start now; returns the submission ids started."""
        now = self.now()
        with self._state_lock:
            for sid in [s for s, f in self._running.items() if f.done()]:
                self._running.pop(sid)
            running = set(self._running)
        free = self.s.concurrency - len(running)
        try:
            back = requeue_stale(self.d1, now, running)
            todo = queued(self.d1, free) if free > 0 else []
        except D1Error as err:
            self.log(f"[watch] D1 unreachable: {err}")
            return []
        if back:
            self.log(f"[watch] back to the queue (no watcher for {STALE_AFTER}): {', '.join(back)}")
        self._mark_deployed()
        started: list[str] = []
        for sub in todo:
            why = self.blocked()
            if why:
                self.log(f"[watch] not starting {sub['id']}: {why}")
                break
            try:
                if not claim(self.d1, sub["id"], self.now()):
                    continue  # another watcher took it
            except D1Error as err:
                self.log(f"[watch] D1 unreachable: {err}")
                break
            with self._state_lock:
                self._running[sub["id"]] = pool.submit(self.process, sub)
            started.append(sub["id"])
        if self.reverifier is not None and self._start_reverify(pool):
            started.append("reverify")
        return started

    def _start_reverify(self, pool: ThreadPoolExecutor) -> bool:
        """One reported failure at a time, in a free slot, when the budget allows."""
        with self._state_lock:
            if self._reverify is not None and not self._reverify.done():
                return False
            finished, self._reverify = self._reverify, None
            busy = len(self._running)
        if finished is not None and finished.exception() is not None:
            self.log(f"[watch] reverify failed: {type(finished.exception()).__name__}: {finished.exception()}")
        if busy >= self.s.concurrency:
            return False
        try:
            if not self.reverifier.pending_count():
                return False
        except D1Error as err:
            self.log(f"[watch] D1 unreachable: {err}")
            return False

        def blocked() -> str | None:
            if self.spent_usd + (busy + 1) * WORST_CASE_META_USD > self.s.max_usd:
                return f"this run's cap: ${self.spent_usd:.2f} spent of --max-usd {self.s.max_usd:.2f}"
            return budget_blocked([("Meta pipeline", self.meta_ledger, WORST_CASE_META_USD * (busy + 1))])

        def work() -> list[Any]:
            try:
                results = self.reverifier.run(1, blocked=blocked)
            except Exception as err:  # noqa: BLE001 - D1 unreachable while listing the queue, say
                self.log(f"[watch] reverify failed: {type(err).__name__}: {str(err)[:300]}")
                return []
            with self._state_lock:
                self.spent_usd += sum(r.cost_usd for r in results)
            return results

        with self._state_lock:
            self._reverify = pool.submit(work)
        return True

    def run(self, *, once: bool = False, sleep: Callable[[float], None] = time.sleep) -> list[Job]:
        """Poll until interrupted; with once, take what is queued now, wait for it, and stop."""
        done: list[Job] = []
        with ThreadPoolExecutor(max_workers=max(1, self.s.concurrency)) as pool:
            while True:
                began = time.monotonic()
                started = self.tick(pool)
                if once:
                    with self._state_lock:
                        futures = list(self._running.values())
                        reverify = self._reverify
                    done += [f.result() for f in futures]
                    if reverify is not None:
                        reverify.result()
                    if not [sid for sid in started if sid != "reverify"]:
                        return done  # a report that stays pending (busy, retry) waits for the next run
                    continue
                sleep(max(0.0, self.s.interval_s - (time.monotonic() - began)))
