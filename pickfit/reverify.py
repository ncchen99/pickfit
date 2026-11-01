"""`pickfit reverify` (P5.3): a reported failure -> a fresh sandbox run -> corrected steps -> git diff.

report_outcome (Worker) queues (slug, os) in D1 `reverify_queue` when a user
reports install_failed or first_run_failed with a valid rec_id, an OS and an
error excerpt. Anyone who called find_software holds a rec_id, so a report is
untrusted: it decides only that a fresh check runs, never what gets written.
This takes the pending rows, oldest first, and for each one:

1. claims it on this machine (a lock file, so `pickfit reverify` and
   `pickfit watch --reverify` never pay twice for one report), and reads the
   report (stage, OS, arch, reporter) and the record from data/software;
2. fetches the repository's README and files from GitHub again, so the run
   sees the project as it is now; the newest extraction is reused unless the
   sources changed (then muse-spark-1.3 reads them again);
3. runs the full verification in a fresh box (agent, replay, judge), telling
   the agent which of pickfit's steps failed where. The report's free text
   (error excerpt, note) never reaches the model; the excerpt is kept in the
   result for the person who reads it;
4. writes back only a passed, replayed run whose steps differ from the
   record's for that OS (for first_run_failed, also its check and first task),
   and only when every package and URL in them is grounded: named in the README,
   in pickfit's earlier steps, or this repository itself. Anything else is held
   for a person, unwritten. The write goes through result.write_back, so its
   rules hold: the pipeline never writes failed, and a stronger passed run on
   the same OS, arch and method is kept. The record's `git diff` is printed and
   saved under runs/reverify/, and the record is committed alone (unless
   `commit` is off); a failed commit puts the file back. Deploying stays a
   person's `pickfit publish`, after reading the diff;
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
import os
import re
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pickfit.d1 import D1Error, Database, sql, timestamp
from pickfit.discover.github import normalize_repo
from pickfit.discover.store import PipelineDB, repo_key
from pickfit.ledger import taipei_now
from pickfit.schema import ExtractionResult, InstallGuide, SoftwareRecord, is_passed
from pickfit.verify.batch import NEVER_RAN, not_in_box
from pickfit.verify.result import install_guide, write_back
from pickfit.verify.task import ReportedFailure, VerifyTask
from pickfit.watch import DONE_EXTRACTIONS, MODEL, git, stop_reason

MAX_ATTEMPTS = 3
EXTRACTION_MODELS = (MODEL, "muse-spark-1.3-contributor")  # what the pipeline database may hold, best first
LEVEL_ORDER = ("inference", "service", "function", "install")
STAGES = ("install_failed", "first_run_failed")
CLAIM_STALE_S = 2 * 3600  # a claim older than this lost its process (a run takes at most about 25 minutes)

_URL = re.compile(r"https?://[^\s'\"`<>()\[\]]+")
# A package manager installing or running packages: the words after it, up to the next shell separator.
# A runner (npx, uvx, pipx run, ...) takes one package; the words after it are the tool's own arguments.
_INSTALL = re.compile(
    r"(?:^|[\s;&|(])(?:sudo\s+)?(?:(?P<runner>npx|bunx|uvx|pipx\s+run|uv\s+tool\s+run)"
    r"|python3?\s+-m\s+pip\s+install|pip3?\s+install|pipx\s+install|uv\s+tool\s+install|uv\s+pip\s+install"
    r"|npm\s+(?:install|i|add)|pnpm\s+(?:add|install|i)|yarn\s+(?:global\s+)?add|bun\s+(?:add|install|i)"
    r"|cargo\s+(?:install|binstall)|go\s+install|brew\s+install|gem\s+install)(?=\s|$)(?P<args>[^;&|]*)")
_PLAIN_VERSION = re.compile(r"^v?\d+(?:\.\d+)*$")
_LOCAL_URL = re.compile(r"^https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(?:[:/]|$)", re.I)
_VERSION = re.compile(r"(?<=.)@[^/]*$|\[.*?\]|[=<>!~]=?.*$")
_NAME_SEPARATORS = re.compile(r"[-_.]+")


def _norm(text: str) -> str:
    """Package-name normalization (PyPI's, applied everywhere): case and -_. runs do not matter."""
    return _NAME_SEPARATORS.sub("-", text.lower())


def ungrounded(commands: list[str], trusted: str, full_name: str) -> list[str]:
    """Why some of `commands` cannot be trusted: packages or URLs that `trusted` (README, earlier
    steps, names) does not mention and that are not this repository's own. Empty when all are grounded."""
    corpus, normed = trusted.lower(), _norm(trusted)
    own = (f"https://github.com/{full_name}/", f"https://raw.githubusercontent.com/{full_name}/",
           f"https://api.github.com/repos/{full_name}/", f"https://codeload.github.com/{full_name}/")
    problems: list[str] = []
    for command in commands:
        for url in _URL.findall(command):
            url = url.rstrip(".,;:'\"")
            if _LOCAL_URL.match(url):
                continue  # a check of the tool's own local server fetches nothing
            if url.lower() not in corpus and not (url.lower() + "/").startswith(tuple(o.lower() for o in own)):
                problems.append(f"{url} is not in the README, pickfit's earlier steps or this repository")
        for match in _INSTALL.finditer(command):
            words = [w.strip("'\"") for w in match.group("args").split()]
            # Flags, flag values that are paths or versions, and URLs (checked above) name no package.
            names = [w for w in words if w and not w.startswith(("-", "$", "~", "/", "."))
                     and "://" not in w and not _PLAIN_VERSION.match(w) and not set(w) & set("<>")]
            for word in names[:1] if match.group("runner") else names:
                name = _norm(_VERSION.sub("", word)).strip("-")
                if name.startswith(_norm(f"github.com/{full_name}")):
                    continue  # go install github.com/<this repo>/...
                if name and not re.search(rf"(?<![a-z0-9-]){re.escape(name)}(?![a-z0-9])", normed):
                    problems.append(f"{word} (in `{command[:120]}`) is not named in the README or pickfit's "
                                    "earlier steps")
    return problems


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
    reports = [Report(**row) for row in rows]
    for report in reports:  # D1's CHECKs cover os and arch; reason is plain text there
        if report.reason not in STAGES:
            report.reason = "install_failed"
        if report.arch not in ("arm64", "x86_64"):
            report.arch = None
    return reports


def mark_done(d1: Database, report: Report, now: datetime) -> int:
    return len(d1.query(sql("UPDATE reverify_queue SET done_at = ?4 WHERE slug = ?1 AND os = ?2 "
                            "AND first_event_id = ?3 AND done_at IS NULL RETURNING slug",
                            report.slug, report.os, report.first_event_id, timestamp(now))))


@dataclass
class Result:
    slug: str
    os: str
    event_id: str
    reporter: str | None
    # rewritten | unchanged | held | not_passed | kept | no_box | no_record | busy | retry | gave_up
    outcome: str
    stage: str | None = None
    error_excerpt: str | None = None  # the reporter's text, for the person reading this; never sent to a model
    level: str | None = None
    run_id: str | None = None
    run_os: str | None = None
    old_steps: list[str] | None = None
    new_steps: list[str] | None = None
    old_first_task: str | None = None
    new_first_task: str | None = None
    held: list[str] = field(default_factory=list)  # why the new steps wait for a person
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
    verify(task, log) -> verify.pipeline.Outcome (nothing written back);
    display: verify gives a GUI app a box with a virtual display."""

    github: Any
    extract: Callable[[dict[str, Any], str], list[dict[str, Any]]]
    verify: Callable[[VerifyTask, Callable[[str], None]], Any]
    display: bool = False


def live_steps(*, runner: str = "modal") -> Steps:
    from pickfit.discover.github import GitHub, github_token
    from pickfit.extract import extract_with_retries
    from pickfit.verify.agent import AgentLimits
    from pickfit.verify.cli import LIFETIME_MARGIN_S, box_factory
    from pickfit.verify.pipeline import verify_task
    from pickfit.watch import EXTRACT_EFFORT

    limits = AgentLimits()
    lifetime = int(limits.max_seconds) + LIFETIME_MARGIN_S
    display = runner == "modal"
    boxes = {False: box_factory(runner, lifetime),
             True: box_factory(runner, lifetime, display=True) if display else None}
    images: set[bool] = set()

    def verify(task: VerifyTask, log: Callable[[str], None]) -> Any:
        gui = display and task.extraction.kind.value == "desktop_app"
        if runner == "modal" and gui not in images:
            from pickfit.verify.modal_box import ensure_published_image

            ensure_published_image(display=gui)
            images.add(gui)
        return verify_task(task, boxes[gui], model=MODEL, limits=limits, log=log, write=False)

    return Steps(github=GitHub(github_token()),
                 extract=lambda c, run_id: extract_with_retries(c, model=MODEL, run_id=run_id,
                                                                reasoning_effort=EXTRACT_EFFORT),
                 verify=verify, display=display)


def commands(guide: InstallGuide | None) -> list[str] | None:
    return [" ".join(step.command.split()) for step in guide.steps] if guide else None


def trusted_text(record: SoftwareRecord, readme: str) -> str:
    """What new steps may draw on: the README as it is now, every guide pickfit recorded, the names."""
    parts = [readme, record.slug, record.name, record.repo.full_name, *record.aliases]
    for _, guide in record.install.guides():
        parts += [step.command for step in guide.steps]
        parts += [guide.first_task or "", guide.check.command if guide.check else ""]
    return "\n".join(parts)


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

    def _claim(self, report: Report) -> Path | None:
        """A lock file for this report on this machine, or None when another process holds it."""
        claims = self.out_dir / "claims"
        claims.mkdir(exist_ok=True)
        path = claims / f"{report.slug}-{report.os}.lock"
        try:
            if time.time() - path.stat().st_mtime > CLAIM_STALE_S:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            return None
        with os.fdopen(fd, "w") as f:
            f.write(f"{os.getpid()} {report.first_event_id}\n")
        return path

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
                        outcome="retry", stage=report.reason, error_excerpt=report.error_excerpt)
        claim = self._claim(report)
        if claim is None:
            result.outcome = "busy"
            log("another pickfit process is re-verifying this report")
            return result
        try:
            log(f"reverify · {report.reason} on {report.os}{'/' + report.arch if report.arch else ''} · "
                f"event {report.first_event_id} · reporter {report.reporter or 'unknown'}")
            try:
                self._check(report, result, log)
            except Exception as err:  # noqa: BLE001 - one bad row must not stop the queue
                result.outcome = "retry"
                result.notes.append(f"{type(err).__name__}: {str(err)[:300]}")
                log(f"problem: {result.notes[-1]}")
            self._settle(report, result, log)
        except Exception as err:  # noqa: BLE001 - bookkeeping (attempts file, result file) must not raise either
            result.notes.append(f"{type(err).__name__}: {str(err)[:300]}")
            log(f"problem: {result.notes[-1]}")
        finally:
            claim.unlink(missing_ok=True)
        result.seconds = round(time.monotonic() - began, 1)
        log(f"result · {result.outcome} · level {result.level or '-'} · {result.seconds:.0f}s · "
            f"model ${result.cost_usd:.4f} · box ${result.box_usd:.4f}"
            + "".join(f"\n  note: {n}" for n in [*result.notes, *(f"held: {h}" for h in result.held)]))
        if result.diff:
            log(f"git diff ({result.diff_path}):\n{result.diff}")
        return result

    def _settle(self, report: Report, result: Result, log: Callable[[str], None]) -> None:
        """Count a failed try, mark the row done when the check was conclusive, save the result."""
        if result.outcome == "retry" and self._count_attempt(report.first_event_id) >= MAX_ATTEMPTS:
            result.outcome = "gave_up"
            result.notes.append(f"no conclusive run after {MAX_ATTEMPTS} tries; a person should look")
        if result.outcome != "retry":
            try:
                result.done = mark_done(self.d1, report, self.clock()) == 1
            except D1Error as err:  # a rewrite is committed; the next run finds those steps unchanged
                result.notes.append(f"D1 not updated, the report stays queued: {err}")
        stamp = self.clock().strftime("%Y%m%d-%H%M%S")
        path = self.out_dir / f"{report.slug}-{report.os}-{stamp}.json"
        path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _check(self, report: Report, result: Result, log: Callable[[str], None]) -> None:
        path = self.data_dir / f"{report.slug}.json"
        if not path.exists():
            result.outcome = "no_record"
            result.notes.append(f"{path.name} is not in {self.data_dir}")
            return
        record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
        if record.repo is None:
            result.outcome = "gave_up"
            result.notes.append("a hosted web app has no repository: the web verifier re-checks it, not this loop")
            return
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
        readme = candidate["readme"] or ""
        ex = ExtractionResult.model_validate(extraction["result"])
        why = not_in_box(ex, display=self.steps.display)
        if why:  # nothing to learn from a box that cannot run it: say so instead of paying for one
            result.outcome = "no_box"
            result.notes.append(f"pickfit's Linux box cannot run it ({why}); a person should check on {report.os}")
            return
        task = VerifyTask(slug=record.slug, repo_url=record.repo.url, readme=readme, extraction=ex,
                          category=record.category,
                          reported=ReportedFailure(stage=report.reason, os=report.os, arch=report.arch,
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
        if guide and guide.basis != "readme_claim":
            result.old_steps, result.old_first_task = commands(guide), guide.first_task
        if not (is_passed(run.level) and run.replayed):
            result.outcome = "not_passed"
            result.notes.append(f"the fresh run did not pass ({run.level}"
                                f"{', ' + run.unverified_reason if run.unverified_reason else ''}); the record is "
                                "unchanged (the pipeline never writes failed), so a person should check")
            return
        new = install_guide(run)
        result.new_steps, result.new_first_task = commands(new), new.first_task
        same = result.new_steps == result.old_steps
        if report.reason == "first_run_failed":  # the fix may be in the first task, not in the install
            same = same and result.new_first_task == result.old_first_task
        if same:
            result.outcome = "unchanged"
            result.notes.append(f"the recorded {run.os} steps still work in a fresh box")
            return
        result.held = ungrounded([*result.new_steps, *([new.first_task] if new.first_task else [])],
                                 trusted_text(record, readme), record.repo.full_name)
        if result.held:
            result.outcome = "held"
            result.notes.append("new steps not written: something in them is not grounded; a person decides")
            return
        with self.git_lock:
            self._write(report, record, outcome, path, result)

    def _write(self, report: Report, record: SoftwareRecord, outcome: Any, path: Path, result: Result) -> None:
        run = outcome.run
        before = path.read_bytes()
        written, note = write_back(run, record.slug, self.data_dir)
        result.notes.append(f"write-back: {note}")
        if not written:
            result.outcome = "kept"
            return
        try:
            result.diff = git(self.data_dir, "diff", "--", path.name)
            diff_path = self.out_dir / f"{report.slug}-{report.os}-{self.clock().strftime('%Y%m%d-%H%M%S')}.diff"
            diff_path.write_text(result.diff, encoding="utf-8")
            result.diff_path = str(diff_path)
            if self.commit:
                git(self.data_dir, "add", "--", path.name)
                git(self.data_dir, "commit", "-q", "-m",
                    f"Re-verify {record.slug} after a reported {report.reason} on {report.os}\n\n"
                    f"Event {report.first_event_id} (reporter {report.reporter or 'unknown'}); fresh run "
                    f"{outcome.run_id}, {run.level}, replayed. The {run.os} install steps changed.", "--", path.name)
                result.commit = git(self.data_dir, "rev-parse", "--short", "HEAD").strip()
        except Exception:
            # Put the record back, so the report stays pending and the next try writes it again.
            if self.commit:
                subprocess.run(["git", "reset", "-q", "--", path.name], cwd=self.data_dir, capture_output=True)
            path.write_bytes(before)
            result.diff = result.diff_path = None
            raise
        result.outcome = "rewritten"

    def _extraction(self, candidate: dict[str, Any], run_id: str, result: Result) -> dict[str, Any]:
        from pickfit.extract import FEATURES_STATUS, build_sources, sources_sha

        current = sources_sha(build_sources(candidate))
        stored = [e for model in EXTRACTION_MODELS
                  if (e := self.db.last_extraction(candidate["repo_id"], model, exclude=(FEATURES_STATUS,)))
                  and e["status"] in DONE_EXTRACTIONS]
        same = next((e for e in stored if e["sources_sha"] == current), None)
        if same:
            return self._with_features(same)
        rows = self.steps.extract(candidate, run_id)
        for row in rows:
            self.db.save_extraction(**row)
            result.cost_usd += row["cost_usd"]
        if rows and rows[-1]["status"] in DONE_EXTRACTIONS:
            fresh = self.db.last_extraction(candidate["repo_id"], MODEL, exclude=(FEATURES_STATUS,))
            assert fresh is not None
            return self._with_features(fresh)
        if stored:  # the README changed but could not be read again: the older reading still says what the tool is
            result.notes.append("extraction of the current README failed; used the stored one")
            return self._with_features(stored[0])
        raise RuntimeError("no extraction of this repository")

    def _with_features(self, extraction: dict[str, Any]) -> dict[str, Any]:
        """The extraction with the features of a newer features-only reading, as the batch merges them, so the
        agent checks the features the record lists (an extraction from before features has none)."""
        from pickfit.extract import feature_rows

        extra = feature_rows(self.db, extraction["repo_id"], extraction["model"])
        if extra is None or (extraction["result"].get("features") and extra["id"] <= extraction["id"]):
            return extraction
        return {**extraction, "result": {**extraction["result"], "features": extra["result"]["features"]}}
