"""`pickfit watch` (P5.2): turn submit_software rows into records, one repository at a time.

Every `interval_s` (60 s) the watcher reads queued rows of the Worker's D1
`submissions` table, claims each one (queued -> reading, only while it is still
queued, so two watchers never take the same row) and runs the single-record
pipeline:

  GitHub details -> rules -> prescreen (Claude Haiku, review by Claude Opus) -> extraction (Claude Opus)
  -> record -> verification on
  Modal (agent, fresh-box replay, judge) -> scores -> known vulnerabilities (OSV.dev, no model call) -> for a
  desktop app, the visual check of its screenshots (one model call)

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
the Worker applies to intake, from wrangler.jsonc); `max_usd` caps the whole
watch run; and where the user set a daily or total cap on the pipeline budget
(pickfit.ledger), a submission starts only while it has room for its worst case. Every job's timings, counted from submitted_at, land in
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
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pickfit.d1 import D1Error, Database, sql, timestamp
from pickfit.discover.github import normalize_repo
from pickfit.discover.rules import RULES_VERSION, classify
from pickfit.discover.store import PipelineDB, repo_key
from pickfit.installdocs import needs_install_docs
from pickfit.lanes import PARKED_PREFIX, due_lanes, parked_reason
from pickfit.ledger import TAIPEI, BudgetExceeded, Ledger, taipei_now
from pickfit.meta import PROD_MODEL
from pickfit.schema import LISTED_CATEGORIES, TOOL_KINDS, ExtractionResult, SoftwareRecord, is_passed
from pickfit.verify.batch import NEVER_RAN, not_in_box
from pickfit.verify.task import VerifyTask

MODEL = PROD_MODEL
EXTRACT_EFFORT = "minimal"
COVERED = LISTED_CATEGORIES  # every named category (schema.Category without "other")
# Category "other" is taken too when the kind is software people install and run (desktop and web apps, CLI tools
# and the like, as the directory already lists them); libraries and non-software stay out (11/3).
OTHER_KINDS = TOOL_KINDS
DEFAULT_INTERVAL_S = 60
DEFAULT_CONCURRENCY = 2
DEFAULT_MAX_USD = 30.0  # five submissions at their worst case (WORST_CASE_META_USD)
DEFAULT_HOURLY_CAP = 20  # the Worker's default when wrangler.jsonc has none
MAX_ATTEMPTS = 3
STALE_AFTER = timedelta(hours=1)  # a row left in reading/verifying this long lost its watcher
LANE_HOLD = timedelta(minutes=30)  # a lane whose box never started rests this long before its next try
# Room a submission needs before it starts: prescreen $0.30 + review $0.30 + extraction $1.50 +
# verification $3.00 + rubric $0.60 (each stage's own cap on Claude's prices), rounded up. A usual one costs
# far less; this is what --max-usd and a user-set cap are checked against. The names are the hackathon's.
WORST_CASE_META_USD = 6.0
WORST_CASE_BASETEN_USD = 0.0
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
    """Why a job needing `need` dollars from each ledger may not start (a daily or total cap the user set),
    or None. A ledger with no cap never blocks."""
    for name, ledger, need in needs:
        if ledger is None:
            continue
        spend = ledger.spend_summary()
        room = min(math.inf if spend["daily_cap_usd"] is None else spend["daily_cap_usd"] - spend["today_usd"],
                   math.inf if spend["total_cap_usd"] is None else spend["total_cap_usd"] - spend["total_usd"])
        if room < need:
            return f"{name} budget: ${room:.2f} left today or in total, a job may need ${need:.2f}"
    return None


# --- D1 ---------------------------------------------------------------------------


def queued(d1: Database, limit: int, *, sites: bool = False) -> list[dict[str, Any]]:
    """Queued submissions, oldest first: repositories, and with `sites` website rows too (a hosted web app, the web
    lane); without it they stay queued. The submitter's note is never read."""
    where = "url LIKE 'https://%'" if sites else "url LIKE 'https://github.com/%'"
    return d1.query(sql(f"SELECT id, url, submitted_at FROM submissions WHERE status = 'queued' AND {where} "
                        "ORDER BY submitted_at, id LIMIT ?1", limit))


def record_passed(record: SoftwareRecord) -> bool:
    """A passed install the record can be recommended on: a replayed guide; a web app is visited once, never
    replayed, so its passed visit is enough."""
    if record.kind == "web_app":
        return is_passed(record.verification.level)
    return is_passed(record.verification.level) and any(
        guide.basis == "replayed" for _, guide in record.install.guides())


def claim(d1: Database, submission_id: str, now: datetime) -> bool:
    return len(d1.query(sql("UPDATE submissions SET status = 'reading', reason = NULL, updated_at = ?2 "
                            "WHERE id = ?1 AND status = 'queued' RETURNING id", submission_id, timestamp(now)))) == 1


def set_status(d1: Database, submission_id: str, status: str, now: datetime, *, slug: str | None = None,
               reason: str | None = None) -> None:
    d1.execute(sql("UPDATE submissions SET status = ?2, slug = ?3, reason = ?4, updated_at = ?5 WHERE id = ?1",
                   submission_id, status, slug, _clip(reason) if reason else None, timestamp(now)))


def claim_parked(d1: Database, submission_id: str, now: datetime) -> bool:
    """A parked row (verifying, waiting for its lane) is taken by one watcher only."""
    return len(d1.query(sql("UPDATE submissions SET reason = NULL, updated_at = ?2 WHERE id = ?1 AND "
                            "status = 'verifying' AND reason LIKE ?3 RETURNING id", submission_id, timestamp(now),
                            PARKED_PREFIX + "%"))) == 1


def requeue_stale(d1: Database, now: datetime, running: set[str]) -> list[str]:
    """Rows a crashed watcher left in reading or verifying go back to queued (not ready or parked ones)."""
    rows = d1.query(sql("SELECT id FROM submissions WHERE status IN ('reading', 'verifying') "
                        "AND updated_at < ?1 AND (reason IS NULL OR (reason <> ?2 AND reason NOT LIKE ?3))",
                        timestamp(now - STALE_AFTER), READY_REASON, PARKED_PREFIX + "%"))
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
    result: str | None = None  # ready | listed | listed_unverified | rejected | retry | waiting | parked
    lane: str | None = None  # where it was verified or waits: linux, windows, macos, web (pickfit.lanes)
    parked_at: str | None = None  # when it first waited for its lane
    lane_tries: int = 0  # lane boxes that never started for it
    level: str | None = None
    run_id: str | None = None
    landed: bool = False  # the record is in data/software (and committed, unless --no-commit)
    commit: str | None = None
    publish_check: list[str] | None = None  # problems `pickfit publish --dry-run` would report
    stages: dict[str, float] = field(default_factory=dict)  # seconds
    cost_usd: dict[str, float] = field(default_factory=dict)  # model, box (to 11/4: meta, baseten, box)
    ready_at: str | None = None
    listed_at: str | None = None
    seconds_to_ready: float | None = None  # from submitted_at
    seconds_to_listed: float | None = None
    notes: list[str] = field(default_factory=list)
    e2e: str | None = None  # pickfit's end-to-end test run it belongs to (pickfit.e2e): every step, nothing published

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


class _Parked(Exception):
    """The record is read and waits for its lane (Windows, macOS): its status is written, the job is saved."""


class _LaneDown(Exception):
    """A lane's box never started: the job parks again and the lane rests (LANE_HOLD)."""


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
    visual(data_dir, slug, log) -> (cost, why it did not finish or None) for a desktop app; the record stays unchecked
    docs(candidate) -> pickfit.installdocs.read_docs' result: the install pages a README points to, read only
        when the README itself holds no install path the sandbox can run
    lanes: name -> pickfit.lanes.Lane for records the Linux box cannot run (windows, macos); their jobs park
    site: pickfit.web_intake's steps for website submissions (the web lane), or None
    """

    github: Any
    prescreen: Callable[[dict[str, Any], str], list[dict[str, Any]]]
    extract: Callable[[dict[str, Any], str], list[dict[str, Any]]]
    verify: Callable[[VerifyTask, Path, Callable[[str], None]], Any]
    score: Callable[[Path, str], str | None]
    display: bool = False
    security: Callable[[Path, str], str | None] | None = None
    visual: Callable[[Path, str, Callable[[str], None]], tuple[float, str | None]] | None = None
    docs: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    lanes: dict[str, Any] = field(default_factory=dict)
    site: Any = None


def live_steps(*, runner: str = "modal") -> Steps:
    """The real pipeline: GitHub, Claude through the ledger, and boxes of `runner` (desktop apps get a display
    box on Modal and on EC2, whose display image passes the same limits test; with docker they are verified as
    far as a box without one goes)."""
    from pickfit.discover.github import GitHub, github_token
    from pickfit.extract import extract_with_retries
    from pickfit.prescreen import screen_and_review
    from pickfit.score import score_records
    from pickfit.verify.agent import AgentLimits
    from pickfit.verify.cli import LIFETIME_MARGIN_S, box_factory
    from pickfit.verify.pipeline import verify_task

    limits = AgentLimits()
    lifetime = int(limits.max_seconds) + LIFETIME_MARGIN_S
    display = runner in ("modal", "ec2")
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
        elif runner == "ec2":
            with image_lock:  # bake or find the AMI once
                if gui not in images:
                    from pickfit.verify.ec2_machine import ensure_image
                    from pickfit.verify.linux_box import image_recipe

                    ensure_image(recipe=image_recipe("vm", gui))
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

    def visual(data_dir: Path, slug: str, log: Callable[[str], None]) -> tuple[float, str | None]:
        from pickfit.discover.github import runs_dir
        from pickfit.usability import visual_one

        try:
            return visual_one(data_dir / f"{slug}.json", runs_dir() / "verify", log)
        except Exception as err:  # noqa: BLE001 - OCR, a budget or a model answer must not lose a finished run
            return 0.0, f"{type(err).__name__}: {str(err)[:200]}"

    github = GitHub(github_token())

    def docs(candidate: dict[str, Any]) -> dict[str, Any]:
        from pickfit.discover.webapps import Fetcher
        from pickfit.installdocs import read_docs

        return read_docs(candidate, fetch=Fetcher(), file_text=github.file_text)

    return Steps(github=github,
                 prescreen=lambda c, run_id: screen_and_review(c, run_id=run_id),
                 extract=lambda c, run_id: extract_with_retries(c, model=MODEL, run_id=run_id,
                                                                reasoning_effort=EXTRACT_EFFORT),
                 verify=verify, score=score, display=display, security=security, visual=visual, docs=docs)


def lane_status(jobs_dir: Path, lanes: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Read-only, for `pickfit watch --status`: each lane's parked jobs, their oldest wait, whether a batch is due,
    and the lane's own view (a Mac lane's hosts and rentals)."""
    now = now or taipei_now()
    parked: dict[str, list[Job]] = {}
    for path in sorted(jobs_dir.glob("*.json")):
        try:
            job = Job(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            continue
        if job.result == "parked" and job.lane:
            parked.setdefault(job.lane, []).append(job)
    out: dict[str, Any] = {}
    for name in sorted(set(parked) | set(lanes)):
        jobs, lane = parked.get(name, []), lanes.get(name)
        when = [_parse_time(j.parked_at or j.started_at) for j in jobs]
        entry: dict[str, Any] = {
            "parked": [{"id": j.submission_id, "url": j.url, "slug": j.slug, "parked_at": j.parked_at} for j in jobs],
            "oldest_wait_hours": round((now - min(when)).total_seconds() / 3600, 1) if when else None}
        if lane is not None:
            entry["due"] = lane.policy.due(when, now)
            entry.update(lane.status())
        out[name] = entry
    return out


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
    lanes: tuple[str, ...] = ("linux",)  # pickfit.lanes.ALL_LANES to take Windows, macOS and website submissions
    publish_mode: str = "deploy"  # deploy: run the deploy here; push: push the commits, the branch's CI deploys
    update_check_s: float = 0  # >0: when idle, this often see whether origin/main has new program code (restart)


class Watcher:
    def __init__(self, d1: Database, steps: Steps, settings: Settings, *, meta_ledger: Ledger | None = None,
                 baseten_ledger: Ledger | None = None, clock: Callable[[], datetime] | None = None,
                 log: Callable[[str], None] = print, publish_fn: Callable[..., int] | None = None,
                 reverifier: Any = None, live_sha: Callable[[], str | None] | None = None,
                 push_fn: Callable[..., Any] | None = None) -> None:
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
        self._push_fn = push_fn
        self.restart_wanted = False  # a push brought new code: finish what runs, start nothing, return from run()
        from pickfit.publish import upstream_code

        self._checked_code = time.monotonic()  # the last look at origin/main's program code (update_check_s)
        self._upstream_code: Callable[[Path], list[str] | None] = upstream_code
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
        self.lanes = {name: lane for name, lane in steps.lanes.items() if name in settings.lanes}
        self._lane_batches: dict[str, Future[list[Job]]] = {}  # one batch thread per lane
        self._lane_running: set[str] = set()  # parked submissions a lane is verifying now
        self._lane_hold: dict[str, datetime] = {}  # lane -> no batch before this (its box never started)
        self._lane_pools = {name: ThreadPoolExecutor(max_workers=max(1, lane.concurrency))
                            for name, lane in self.lanes.items()}
        self._batch_pool = ThreadPoolExecutor(max_workers=max(1, len(self.lanes)))  # each lane's batch loop
        for job in self.saved_jobs():  # a parked record keeps its slug and its repository across restarts
            if job.result == "parked":
                if job.slug:
                    self._slugs_in_flight.add(job.slug)
                if job.repo_id:
                    self._repos_in_flight[job.repo_id] = job.url

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
            lane_running = set(self._lane_running)
        started = {j.submission_id for j in self.saved_jobs() if _parse_time(j.started_at) >= hour_ago} | running
        if len(started) >= self.s.hourly_cap:
            return (f"hourly cap: {len(started)} submissions started in the last hour "
                    f"(SUBMIT_HOURLY_CAP {self.s.hourly_cap})")
        return self._money_blocked(len(running) + len(lane_running))

    def _money_blocked(self, busy: int) -> str | None:
        """Why one more job may not start while `busy` others may still spend their worst case, or None."""
        if self.spent_usd + (busy + 1) * WORST_CASE_META_USD > self.s.max_usd:
            return f"this run's cap: ${self.spent_usd:.2f} spent of --max-usd {self.s.max_usd:.2f}"
        jobs = busy + 1  # the ones in flight may still spend their worst case
        return budget_blocked([("Model pipeline", self.meta_ledger, WORST_CASE_META_USD * jobs),
                               ("Baseten", self.baseten_ledger, WORST_CASE_BASETEN_USD * jobs)])

    # -- the pipeline for one submission

    def process(self, sub: dict[str, Any]) -> Job:
        """Run one claimed submission to its end (or until it parks for its lane); never raises."""
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
            from pickfit import e2e

            job.e2e = e2e.marked(self.s.runs_dir, job.url, self.now())
        log(f"start · {job.url} · try {job.failures + 1}{' · resuming a landed record' if resume else ''}"
            f"{f' · end-to-end test {job.e2e}: every step runs, nothing is published' if job.e2e else ''}")
        self._guard(job, log, (lambda: self._report_landed(job, log)) if resume else (lambda: self._run(job, log)))
        return job

    def _guard(self, job: Job, log: Callable[[str], None], work: Callable[[], None], *, parked: bool = False) -> None:
        """Run `work` for `job`; whatever happens the D1 row ends in a known state and the job is saved.
        `parked`: the job came out of its lane's queue, so a wait sends it back there, not to the D1 queue."""
        before = sum(job.cost_usd.get(k, 0.0) for k in ("model", "meta", "baseten"))
        try:
            work()
        except (_AlreadyListed, _Parked):
            pass
        except _LaneDown as err:  # the machine's problem, not the software's: wait for the lane again
            log(f"{err}; parked again, the {job.lane} lane rests {LANE_HOLD}")
            self._park_quietly(job, log)
            if job.lane:
                self._lane_hold[job.lane] = self.now() + LANE_HOLD
        except Rejected as err:
            self._finish(job, "rejected", "rejected", str(err), log)
        except BudgetExceeded as err:
            log(f"budget: {err}")
            if err.cap.startswith("scope"):  # one stage used up its own cap: that try failed
                self._fail(job, f"budget: {err}", log)
            elif parked and job.lane:
                self._park_quietly(job, log)
            else:
                self._finish(job, "waiting", "queued", "Waiting for pickfit's model budget; it continues later.", log)
        except Exception as err:  # noqa: BLE001 - Retry, IndexBuildError, a bug: the row must not stay in reading
            self._fail(job, f"{type(err).__name__}: {str(err)[:300]}", log)
        finally:
            with self._state_lock:
                if job.result != "parked":  # a parked record keeps its slug and repository until its lane runs it
                    if job.slug:
                        self._slugs_in_flight.discard(job.slug)
                    if job.repo_id and self._repos_in_flight.get(job.repo_id) == job.url:
                        self._repos_in_flight.pop(job.repo_id)
                self.spent_usd += sum(job.cost_usd.get(k, 0.0) for k in ("model", "meta", "baseten")) - before
            self._save(job)
        log(f"{'parked' if job.result == 'parked' else 'done'} · {job.summary()}")

    # -- lanes: Windows and macOS records wait for their machines (pickfit.lanes)

    def _lane_for(self, ex: ExtractionResult) -> tuple[str | None, str | None]:
        """(lane, None) for the first lane whose box can run it, else (None, why the Linux box cannot)."""
        why = not_in_box(ex, display=self.steps.display)
        if why is None:
            return "linux", None
        for name in ("windows", "macos"):
            lane = self.lanes.get(name)
            if lane is not None and not_in_box(ex, os=lane.os, display=lane.display) is None:
                return name, None
        return None, why

    def _park(self, job: Job, lane: str, log: Callable[[str], None]) -> None:
        """The record waits in runs/watch/<submission>/software/ for its lane; raises _Parked."""
        job.lane = lane
        job.parked_at = job.parked_at or self.now().isoformat()
        self._park_quietly(job, log)
        log(f"parked for the {lane} lane ({self.lanes[lane].policy.describe()})")
        raise _Parked()

    def _park_quietly(self, job: Job, log: Callable[[str], None]) -> None:
        job.result = "parked"
        try:
            self._status(job, "verifying", reason=parked_reason(job.lane or "", self.lanes[job.lane].policy))
        except D1Error as err:
            job.notes.append(f"D1 status not written: {err}")
            log(f"D1 status not written: {err}")

    def parked_jobs(self, lane: str | None = None) -> list[Job]:
        return [j for j in self.saved_jobs() if j.result == "parked" and (lane is None or j.lane == lane)]

    def resume(self, job: Job, lane: Any) -> Job:
        """Verify a parked job in its lane and finish it; never raises."""
        log = self._say(job.submission_id)
        log(f"resume · {lane.name} lane · parked {job.parked_at}")

        def work() -> None:
            if not claim_parked(self.d1, job.submission_id, self.now()):
                job.result = "elsewhere"
                job.notes.append("its D1 row was no longer parked when the lane came to it: left alone")
                return
            record_dir = self.s.runs_dir / "watch" / job.submission_id / "software"
            candidate = self.db.candidate(job.repo_id) if job.repo_id else None
            extraction = self.db.last_extraction(job.repo_id, MODEL) if job.repo_id else None
            path = record_dir / f"{job.slug}.json"
            if candidate is None or extraction is None or not path.exists():
                raise Retry("the parked record or its extraction is gone")
            record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
            ex = ExtractionResult.model_validate(extraction["result"])
            job.status = "verifying"
            self._verify_and_land(job, self._task(job, candidate, ex, record), record_dir, lane.verify, log,
                                  lane=lane.name)

        self._guard(job, log, work, parked=True)
        return job

    def _task(self, job: Job, candidate: dict[str, Any], ex: ExtractionResult, record: SoftwareRecord) -> VerifyTask:
        return VerifyTask(slug=job.slug, repo_url=record.repo.url, readme=candidate["readme"], extraction=ex,
                          category=record.category, guides=candidate.get("docs") or [])

    def _verify_and_land(self, job: Job, task: VerifyTask, record_dir: Path, verify: Callable[..., Any],
                         log: Callable[[str], None], *, lane: str = "linux") -> None:
        with self._stage(job, "verify"):
            outcome = verify(task, record_dir, log)
        job.lane = lane
        job.run_id, job.level = outcome.run_id, outcome.run.level
        job.spent("model", outcome.cost_usd)
        job.spent("box", getattr(outcome, "box_usd", 0.0))
        stop = stop_reason(outcome)
        if stop in NEVER_RAN:
            if lane == "linux":
                raise Retry(f"verification never got going ({stop})")
            job.lane_tries += 1
            job.notes.append(f"the {lane} box never got going ({stop})")
            if job.lane_tries < MAX_ATTEMPTS:
                raise _LaneDown(f"the {lane} box never got going ({stop})")
            self._tail(job, record_dir, f"pickfit's {lane} sandbox did not start for it ({stop}, "
                                        f"{job.lane_tries} tries)", log)
            return
        run = outcome.run
        self._tail(job, record_dir, f"the sandbox run did not pass ({run.unverified_reason or run.level})", log)

    def _tail(self, job: Job, record_dir: Path, not_passed: str | None, log: Callable[[str], None]) -> None:
        """Scores, the vulnerability check, the visual check, then the record lands."""
        with self._stage(job, "score"):
            error = self.steps.score(record_dir, job.slug)
        if error:
            raise Retry(f"scores: {error}")
        self._security(job, record_dir, log)
        self._visual(job, record_dir, log)
        self._land(job, record_dir, not_passed, log)

    def _fail(self, job: Job, what: str, log: Callable[[str], None]) -> None:
        job.failures += 1
        job.notes.append(what)
        log(f"problem: {what}")
        if job.failures >= MAX_ATTEMPTS and not job.landed:  # a landed record is there: keep reporting it
            what = "site" if job.lane == "web" else "repository"
            self._finish(job, "rejected", "rejected",
                         f"pickfit could not finish reading this {what} after {job.failures} tries.", log)
        else:
            self._finish(job, "retry", "queued", "A temporary problem; pickfit will try again.", log)

    def _finish(self, job: Job, result: str, status: str, reason: str | None, log: Callable[[str], None]) -> None:
        job.result = result
        try:
            self._status(job, status, reason=reason)
        except D1Error as err:
            job.notes.append(f"D1 status not written: {err}")
            log(f"D1 status not written: {err}")

    def _sites(self) -> bool:
        return "web" in self.s.lanes and self.steps.site is not None

    def _run_site(self, job: Job, log: Callable[[str], None]) -> None:
        """A website submission (the web lane, pickfit.web_intake): read the site into a web_app record, visit it
        once, land it. Costs are counted as they are paid (`spend`), so a refusal after a paid step loses none."""
        from pickfit import web_intake

        job.lane = "web"
        job.full_name = job.full_name or job.url
        rid = web_intake.site_record_id(job.url)
        if rid:
            with self._state_lock:
                taking = self._repos_in_flight.get(rid)
                if taking and taking != job.url:
                    raise Rejected(f"Same site as another submission pickfit is reading now ({taking}).")
                self._repos_in_flight[rid] = job.url
            job.repo_id = rid
        run_id = f"watch-{job.submission_id.removeprefix('sub_')[:12]}-{self.now().strftime('%Y%m%d-%H%M%S')}"
        record_dir = self.s.runs_dir / "watch" / job.submission_id / "software"

        def claim_slug(slug: str) -> bool:
            with self._state_lock:
                if slug in self._slugs_in_flight or (self.s.data_dir / f"{slug}.json").exists():
                    return False
                self._slugs_in_flight.add(slug)
            job.slug = slug
            return True

        with self._state_lock:
            taken = {p.stem for p in self.s.data_dir.glob("*.json")} | self._slugs_in_flight
        site_steps = self.steps.site
        if job.e2e and site_steps.with_visits is not None:  # its visit never counts against a real submission
            from pickfit import e2e

            site_steps = site_steps.with_visits(e2e.run_dir(self.s.runs_dir, job.e2e) / "visits.jsonl")
        try:
            with self._stage(job, "read"):
                read = web_intake.read_site(job.url, submission_id=job.submission_id, run_id=run_id,
                                            record_dir=record_dir, data_dir=self.s.data_dir, db_path=self.s.db_path,
                                            taken_slugs=taken, steps=site_steps, log=log,
                                            claim_slug=claim_slug, spend=job.spent)
        except web_intake.AlreadyListed as err:
            job.slug = err.slug
            if err.status != "listed":
                raise Rejected("Reviewed before and not listed.") from None
            job.result = "listed" if is_passed(err.level or "") else "listed_unverified"
            self._status(job, job.result, reason="Already in pickfit's directory.")
            raise _AlreadyListed() from None
        except web_intake.Refused as err:
            raise Rejected(str(err)) from None
        except web_intake.TryLater as err:
            raise Retry(str(err)) from None
        job.notes += read.notes
        if read.record_id != job.repo_id:  # the site redirected to another address
            with self._state_lock:
                taking = self._repos_in_flight.get(read.record_id)
                if taking and taking != job.url:
                    raise Rejected(f"Same site as another submission pickfit is reading now ({taking}).")
                if job.repo_id and self._repos_in_flight.get(job.repo_id) == job.url:
                    self._repos_in_flight.pop(job.repo_id)
                self._repos_in_flight[read.record_id] = job.url
            job.repo_id = read.record_id
        job.slug = read.slug
        log(f"record {job.slug} [web_app] {read.url}")
        self._status(job, "verifying")
        try:
            with self._stage(job, "verify"):
                visit = web_intake.verify_site_record(record_dir, read.slug, steps=site_steps, log=log,
                                                      spend=job.spent)
        except web_intake.Refused as err:
            raise Rejected(str(err)) from None
        except web_intake.TryLater as err:
            raise Retry(str(err)) from None
        job.level, job.run_id = visit.level, visit.run_id
        if visit.detail:
            job.notes.append(f"visit: {visit.detail}"[:500])
        self._tail(job, record_dir, f"the site visit did not pass ({visit.why})" if visit.why else None, log)

    def _run(self, job: Job, log: Callable[[str], None]) -> None:
        url = normalize_repo_url(job.url)
        if url is None and self._sites() and not re.match(r"(?:https?://)?(?:www\.)?github\.com/", job.url, re.I):
            return self._run_site(job, log)
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
        if self.steps.docs and not candidate.get("docs") and needs_install_docs(extraction["result"]):
            # The README names no install path the sandbox can run: read the install guide it points to.
            with self._stage(job, "docs"):
                docs = self.steps.docs(candidate)
            self.db.save_install_docs(job.repo_id, docs)
            log(f"install guide: {len(docs['pages'])} page(s) read"
                + "".join(f" · {p['url']}" for p in docs["pages"]))
            if docs["pages"]:
                candidate = self.db.candidate(job.repo_id)
                with self._stage(job, "extract"):
                    extraction = self._extract(candidate, run_id, job)
                job.notes.append(f"install guide read: {', '.join(p['url'] for p in docs['pages'])}")
        record_dir = self.s.runs_dir / "watch" / job.submission_id / "software"
        record = self._write_record(job, candidate, extraction, record_dir)
        log(f"record {job.slug} [{record.category}/{record.kind}]")
        self._status(job, "verifying")

        ex = ExtractionResult.model_validate(extraction["result"])
        lane, why = self._lane_for(ex)
        if lane is None:
            others = [n for n in ("windows", "macos") if n in self.lanes]
            where = "pickfit's Linux sandbox" if not others else f"pickfit's Linux, {' and '.join(others)} sandboxes"
            job.notes.append(f"not verified: {why}")
            log(f"no sandbox run: {why}")
            self._tail(job, record_dir, f"{where} cannot run it ({why})", log)
        elif lane == "linux":
            self._verify_and_land(job, self._task(job, candidate, ex, record), record_dir, self.steps.verify, log)
        else:
            self._park(job, lane, log)

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

    def _visual(self, job: Job, record_dir: Path, log: Callable[[str], None]) -> None:
        """A desktop app's visual check, from the screenshots its run just took. A web app has no submission path yet,
        and a check that cannot finish leaves the record marked unchecked."""
        if self.steps.visual is None or not job.run_id:
            return
        if json.loads((record_dir / f"{job.slug}.json").read_text(encoding="utf-8")).get("kind") != "desktop_app":
            return
        with self._stage(job, "visual"):
            cost, error = self.steps.visual(record_dir, job.slug, log)
        job.spent("model",cost)
        if error:
            job.notes.append(f"visual check did not finish: {error}")
            log(f"visual check did not finish: {error}")

    def _refuse_known(self, job: Job) -> None:
        """A repository another submission took (or is taking) is refused; one already in data/software
        takes that record's status."""
        for other in self.saved_jobs():
            if other.e2e:  # a test submission never took the repository
                continue
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
            job.spent("model", row["cost_usd"])
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
            job.spent("model",row["cost_usd"])
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
        passed = record_passed(record)
        if job.e2e:
            return self._land_test(job, record_dir, record, passed, not_passed, log)
        target = self.s.data_dir / f"{job.slug}.json"
        with self._git_lock, self._stage(job, "commit"):
            for path in self.s.data_dir.glob("*.json"):  # one record per repository, or the index refuses them all
                try:
                    if json.loads(path.read_text(encoding="utf-8")).get("repo_id") == job.repo_id:
                        raise Rejected(f"Already in pickfit's directory as {path.stem}.")
                except (OSError, ValueError):
                    continue
            if target.exists():  # another record took the slug meanwhile: never overwrite it
                raise Retry(f"{target.name} appeared in {self.s.data_dir.name} meanwhile")
            shutil.copyfile(record_dir / f"{job.slug}.json", target)
            try:
                if self.s.commit:
                    took = (self.now() - _parse_time(job.submitted_at)).total_seconds()
                    git(self.s.data_dir, "add", "--", target.name)
                    git(self.s.data_dir, "commit", "-q", "-m",
                        # No submission id: it is the submitter's key to their status page, and the repository
                        # is public.
                        f"Add {job.slug} from a submission (pickfit watch)\n\n{job.url}\n"
                        f"Verification {record.verification.level}"
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

    def _land_test(self, job: Job, record_dir: Path, record: SoftwareRecord, passed: bool, not_passed: str | None,
                   log: Callable[[str], None]) -> None:
        """An end-to-end test's finished record (pickfit.e2e): the checks a landing makes, and the publish plan check
        (`pickfit publish --dry-run`'s) on a copy of data/software with it added; then it is kept in the run's folder,
        never in data/software, never committed or pushed. Its D1 row ends as rejected, with a reason that says what a
        real submission would have got."""
        import tempfile

        from pickfit import e2e
        from pickfit.publish import plan

        with self._stage(job, "publish check"):
            for path in self.s.data_dir.glob("*.json"):
                try:
                    if json.loads(path.read_text(encoding="utf-8")).get("repo_id") == job.repo_id:
                        raise Rejected(f"Already in pickfit's directory as {path.stem}.")
                except (OSError, ValueError):
                    continue
            with tempfile.TemporaryDirectory(prefix="pickfit-e2e-") as tmp:
                copy = Path(tmp) / "software"
                shutil.copytree(self.s.data_dir, copy, ignore=shutil.ignore_patterns(".*"))
                if (copy / f"{job.slug}.json").exists():
                    raise Retry(f"{job.slug}.json appeared in {self.s.data_dir.name} meanwhile")
                shutil.copyfile(record_dir / f"{job.slug}.json", copy / f"{job.slug}.json")
                job.publish_check = plan(copy, self.s.worker_dir, allow_dirty=True).problems
        kept = e2e.run_dir(self.s.runs_dir, job.e2e or "") / "records"
        kept.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(record_dir / f"{job.slug}.json", kept / f"{job.slug}.json")
        job.level = record.verification.level
        job.result = e2e.PASSED if passed else e2e.UNVERIFIED
        if passed:
            would = f"would be listed as verified ({job.level}) from the {job.lane or 'linux'} lane"
        else:
            why = not_passed or f"the sandbox run did not pass ({record.verification.unverified_reason or job.level})"
            would = f"would be listed without a verified install: {why}"
        problems = f"; publish check: {'; '.join(job.publish_check)}" if job.publish_check else ""
        self._status(job, "rejected", reason=f"{e2e.REASON}{would}{problems}.")
        log(f"end-to-end test: {would}{problems} · kept in {kept}")

    def _report_landed(self, job: Job, log: Callable[[str], None], not_passed: str | None = None) -> None:
        """Write the D1 status a landed record has: ready (or listed once deployed), or listed_unverified."""
        record = SoftwareRecord.model_validate_json((self.s.data_dir / f"{job.slug}.json").read_text(encoding="utf-8"))
        job.level = record.verification.level
        passed = record_passed(record)
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

        if self.s.publish_mode == "push":
            return self._push(jobs, log)
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

    def _push(self, jobs: list[Job], log: Callable[[str], None]) -> None:
        """Push the record commits; the branch's CI deploys them, and _mark_deployed lists them once the live
        Worker serves this data. New program code from the branch asks the watcher to restart (restart_wanted)."""
        from pickfit.publish import push_publish

        push = self._push_fn or push_publish
        with self._git_lock:
            began = time.monotonic()
            pushed = push(self.s.data_dir, self.s.worker_dir, out=log)
            took = round(time.monotonic() - began, 1)
        if pushed.code != 0:
            for job in jobs:
                job.notes.append("push failed; the record stays committed and ready")
            return
        for job in jobs:
            job.stages["publish"] = took
            job.notes.append(f"pushed {(pushed.head or '')[:10]}; CI deploys it")
        if pushed.code_changed:
            self.restart_wanted = True
            log("the branch brought new program code: no new work starts, and watch stops once what runs is done")

    def _check_code(self) -> None:
        self._checked_code = time.monotonic()
        with self._git_lock:
            changed = self._upstream_code(self.s.data_dir)
        if changed:
            self.restart_wanted = True
            self.log(f"[watch] origin/main has new program code ({', '.join(changed[:5])}): restarting for it")

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
            lane_running = set(self._lane_running)
        free = 0 if self.restart_wanted else self.s.concurrency - len(running)
        try:
            back = requeue_stale(self.d1, now, running | lane_running)
            todo = queued(self.d1, free, sites=self._sites()) if free > 0 else []
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
        if not self.restart_wanted:
            started += [f"lane:{name}" for name in self._tick_lanes()]
        return started

    def _tick_lanes(self) -> list[str]:
        """Start a batch in each lane that is due (or holds a machine) and has parked jobs; let idle lanes go."""
        if not self.lanes:
            return []
        now = self.now()
        with self._state_lock:
            for name in [n for n, f in self._lane_batches.items() if f.done()]:
                finished = self._lane_batches.pop(name)
                if finished.exception() is not None:
                    self.log(f"[{name}] batch failed: {type(finished.exception()).__name__}: {finished.exception()}")
            busy = set(self._lane_batches)
            running = set(self._lane_running)
        parked: dict[str, list[datetime]] = {}
        for job in self.parked_jobs():
            if job.lane in self.lanes and job.submission_id not in running:
                parked.setdefault(job.lane, []).append(_parse_time(job.parked_at or job.started_at))
        free: dict[str, Any] = {}
        for name, lane in self.lanes.items():
            if name in busy:
                continue
            if name not in parked:
                try:
                    lane.idle(self._say(name))
                except Exception as err:  # noqa: BLE001 - a provider being down must not stop the watcher
                    self.log(f"[{name}] could not let its machines go: {type(err).__name__}: {str(err)[:200]}")
                continue
            if self._lane_hold.get(name) and now < self._lane_hold[name]:
                continue
            free[name] = lane
        due = due_lanes(parked, free, now)
        for job in self.parked_jobs():  # an end-to-end test does not wait for a full batch
            if job.e2e and job.lane in free and job.lane not in due and job.submission_id not in running:
                due[job.lane] = "an end-to-end test is waiting"
        started = []
        for name, why in due.items():
            self.log(f"[{name}] batch of {len(parked[name])}: {why}")
            with self._state_lock:
                self._lane_batches[name] = self._batch_pool.submit(self._lane_batch, name)
            started.append(name)
        return started

    def _lane_batch(self, name: str) -> list[Job]:
        """Make the lane ready (a Mac may be rented and set up first), then run its parked jobs, newly parked
        ones too, until none is left, the money says stop or the lane goes down."""
        lane, log = self.lanes[name], self._say(name)
        try:
            why = lane.available(log)
        except Exception as err:  # noqa: BLE001 - a provider or host problem must not stop the watcher
            why = f"{type(err).__name__}: {str(err)[:300]}"
        if why:
            log(f"not ready: {why}; next try in {LANE_HOLD}")
            self._lane_hold[name] = self.now() + LANE_HOLD
            return []
        done: list[Job] = []
        while True:
            with self._state_lock:
                running = set(self._lane_running)
            todo = [j for j in self.parked_jobs(name) if j.submission_id not in running]
            if not todo or (self._lane_hold.get(name) and self.now() < self._lane_hold[name]):
                return done
            futures = []
            for job in sorted(todo, key=lambda j: j.parked_at or ""):
                with self._state_lock:
                    busy = len(self._running) + len(self._lane_running)
                stop = self._money_blocked(busy)
                if stop:
                    log(f"not starting {job.submission_id}: {stop}")
                    break
                with self._state_lock:
                    self._lane_running.add(job.submission_id)
                futures.append(self._lane_pools[name].submit(self._lane_job, job, lane))
            if not futures:
                return done
            done += [f.result() for f in futures]

    def _lane_job(self, job: Job, lane: Any) -> Job:
        try:
            return self.resume(job, lane)
        finally:
            with self._state_lock:
                self._lane_running.discard(job.submission_id)

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
            return budget_blocked([("Model pipeline", self.meta_ledger, WORST_CASE_META_USD * (busy + 1))])

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
                        batches = list(self._lane_batches.values())
                    done += [f.result() for f in futures]
                    if reverify is not None:
                        reverify.result()
                    for batch in batches:
                        done += batch.result()
                    # A report that stays pending (busy, retry) waits for the next run; so does a lane's leftover.
                    if not [sid for sid in started if sid != "reverify" and not sid.startswith("lane:")]:
                        return done
                    continue
                with self._state_lock:
                    busy = [f for f in [*self._running.values(), *self._lane_batches.values()] if not f.done()]
                if not busy and not self.restart_wanted and self.s.update_check_s > 0 and \
                        time.monotonic() - self._checked_code >= self.s.update_check_s:
                    self._check_code()
                if self.restart_wanted:
                    if not busy:
                        self.log("[watch] stopping so the new code runs (exit 75 asks the service to restart)")
                        return done
                sleep(max(0.0, self.s.interval_s - (time.monotonic() - began)))
