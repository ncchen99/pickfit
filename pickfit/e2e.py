"""pickfit's end-to-end test: submissions through the live website and MCP that run the whole pipeline on the watch
machine and are never published, so a run adds no software and can be repeated.

    pickfit e2e [--lanes default|all|reject,linux,web,windows,macos] [--keep] [--dry-run]

Run it where `pickfit watch` runs, with the watcher's environment (deploy/watch: `systemctl start pickfit-e2e@default`).
For each lane it takes the first canary URL that pickfit does not list and that no person has submitted, marks it in
runs/e2e/canaries.json, submits it the way a person does (the website form; the reject canary goes through the MCP's
submit_software), and follows it: the D1 row, the public status page, then the watcher's job file.

A marked submission runs every step a real one does, its lane and sandbox included, up to the finished record and
`pickfit publish`'s plan check on a copy of data/software. It never lands in data/software, is never committed or
pushed, and its D1 row ends as rejected with a reason starting with REASON. A website canary's visit is claimed in
runs/e2e/<run>/visits.jsonl, so it never counts against a real submission of that site. At the end the D1 rows are
deleted and the job files moved into runs/e2e/<run>/, so the next run starts the same way.

The publish leg is checked without publishing: the data both public hosts serve against origin/main's records.

Paid: each lane's verification (model and sandbox, about US$1-6 a lane); a later run reuses the prescreen and the
extraction, so it costs less. windows needs AWS credentials on the machine; macos a Mac host the watcher knows.
"""

from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from pickfit.d1 import Database, sql

E2E_DIR = "e2e"
MARKERS = "canaries.json"
SUBMITTED = "submitted.jsonl"  # every canary submission id, so a leftover row is known as one
MARK_FOR = timedelta(hours=8)
REASON = "pickfit end-to-end test, not published: "
PASSED = "e2e_passed"  # Job.result of a canary that would have been listed as verified
UNVERIFIED = "e2e_unverified"  # Job.result of a canary that would have been listed without a verified install
TERMINAL = ("rejected", "listed", "listed_unverified")
USER_AGENT = "pickfit-e2e (+https://pickfit.app/about)"
POLL_S = 20.0


@dataclass(frozen=True)
class Canary:
    lane: str  # the watcher's lane it must take (reject: none, it must be refused)
    urls: tuple[str, ...]  # candidates; the first one pickfit does not list and nobody submitted is used
    expect: str  # passed | rejected
    timeout: timedelta
    via: str  # web: the website form; mcp: the MCP's submit_software
    what: str  # what it exercises


CANARIES: dict[str, Canary] = {
    "reject": Canary("reject", ("https://github.com/sindresorhus/awesome", "https://github.com/github/gitignore"),
                     "rejected", timedelta(minutes=30), "mcp",
                     "MCP submit_software, D1, the watcher's read and its refusal (cheap: no sandbox)"),
    "linux": Canary("linux", ("https://github.com/sharkdp/hexyl", "https://github.com/so-fancy/diff-so-fancy"),
                    "passed", timedelta(minutes=75), "web",
                    "the website form, D1, read, prescreen, extraction, the Linux sandbox and its replay, scores, "
                    "the vulnerability check, the record and the publish plan check"),
    # Real open-source web apps, no account, that pickfit does not list and whose robots.txt and terms allow
    # automated visits (checked 11/18). Not a demo page: demo.playwright.dev/todomvc says it is "just a demo
    # ... for testing", and pickfit's reading rightly refuses it as demo_prototype.
    "web": Canary("web", ("https://regexr.com", "https://dillinger.io"),
                  "passed", timedelta(minutes=75), "web",
                  "a website submission: robots.txt, terms, the screen, extraction and one visit in a microVM"),
    "windows": Canary("windows", ("https://github.com/lptstr/winfetch",), "passed", timedelta(hours=2), "web",
                      "a Windows-only tool: parked for the Windows lane, verified on EC2"),
    "macos": Canary("macos", ("https://github.com/rgcr/m-cli",), "passed", timedelta(hours=3), "web",
                    "a macOS-only tool: parked for the macOS lane (due at once for a test), verified on a Mac host"),
}
ALL = tuple(CANARIES)
DEFAULT = ("reject", "linux", "web")


def lanes_from(text: str) -> tuple[str, ...]:
    """default, all, or lane names separated by commas or dashes (a systemd instance name has no commas)."""
    text = (text or "default").strip()
    if text == "default":
        return DEFAULT
    if text == "all":
        return ALL
    names = tuple(dict.fromkeys(n for n in text.replace("-", ",").split(",") if n.strip()))
    unknown = [n for n in names if n not in CANARIES]
    if unknown or not names:
        raise ValueError(f"lanes are default, all or {','.join(ALL)} (got {text})")
    return names


def normalize(url: str) -> str | None:
    """The URL as the Worker writes it into D1: a GitHub repository, or a web app's https address."""
    from pickfit.watch import normalize_repo_url
    from pickfit.web_intake import normalize_web_url

    return normalize_repo_url(url) or normalize_web_url(url)


# --- markers: which submissions are tests (read by pickfit.watch) ------------------------------------------------


def e2e_dir(runs_dir: Path) -> Path:
    return runs_dir / E2E_DIR


def run_dir(runs_dir: Path, run: str) -> Path:
    return e2e_dir(runs_dir) / run


def _read_markers(runs_dir: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads((e2e_dir(runs_dir) / MARKERS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [m for m in data if isinstance(m, dict)] if isinstance(data, list) else []


def _write_markers(runs_dir: Path, markers: list[dict[str, Any]]) -> None:
    path = e2e_dir(runs_dir) / MARKERS
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{secrets.token_hex(3)}.tmp")
    tmp.write_text(json.dumps(markers, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def mark(runs_dir: Path, url: str, run: str, now: datetime) -> None:
    """From now until MARK_FOR later, a submission of `url` is this run's test submission."""
    url = normalize(url) or url
    markers = [m for m in _read_markers(runs_dir) if m.get("url") != url]
    markers.append({"url": url, "run": run, "at": now.isoformat(), "until": (now + MARK_FOR).isoformat()})
    _write_markers(runs_dir, markers)


def unmark(runs_dir: Path, run: str, url: str | None = None) -> None:
    keep = [m for m in _read_markers(runs_dir) if m.get("run") != run or (url is not None and m.get("url") != url)]
    _write_markers(runs_dir, keep)


def marked(runs_dir: Path, url: str, now: datetime) -> str | None:
    """The end-to-end run a submission of `url` belongs to, or None (a real submission)."""
    url = normalize(url) or url
    for m in _read_markers(runs_dir):
        try:
            live = datetime.fromisoformat(m["at"]) <= now <= datetime.fromisoformat(m["until"])
        except (KeyError, TypeError, ValueError):
            continue
        if m.get("url") == url and live:
            return str(m.get("run"))
    return None


def _submitted_ids(runs_dir: Path) -> set[str]:
    path = e2e_dir(runs_dir) / SUBMITTED
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    out = set()
    for line in lines:
        try:
            out.add(json.loads(line)["id"])
        except (ValueError, KeyError, TypeError):
            continue
    return out


def _note_submitted(runs_dir: Path, sid: str, url: str, run: str) -> None:
    path = e2e_dir(runs_dir) / SUBMITTED
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": sid, "url": url, "run": run}) + "\n")


# --- the public site, as a person's browser and an MCP client use it ---------------------------------------------


class SiteError(RuntimeError):
    pass


class Site:
    """https://pickfit.app (or another host serving the same Worker code)."""

    def __init__(self, base: str = "https://pickfit.app", *, opener: Callable[..., Any] | None = None,
                 timeout: float = 30.0) -> None:
        self.base = base.rstrip("/")
        self._open = opener or urllib.request.urlopen
        self.timeout = timeout

    def _request(self, path: str, *, data: bytes | None = None, headers: dict[str, str] | None = None) -> Any:
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data is not None else "GET",
                                     headers={"User-Agent": USER_AGENT, **(headers or {})})
        return self._open(req, timeout=self.timeout)

    def submit_form(self, url: str) -> tuple[str | None, str]:
        """(submission id, the page's final path): the form on /submit, posted from the site's own page as a
        browser does, following its 303 to /submit/<id>. No id: pickfit lists it already (or the form refused it)."""
        body = urllib.parse.urlencode({"url": url}).encode()
        try:
            with self._request("/submit", data=body, headers={"Origin": self.base, "Accept": "text/html",
                                                              "Content-Type": "application/x-www-form-urlencoded"}) as r:
                final = urllib.parse.urlsplit(r.geturl()).path
        except urllib.error.HTTPError as err:
            raise SiteError(f"POST /submit answered {err.code}") from None
        except OSError as err:
            raise SiteError(f"POST /submit failed: {err}") from None
        sid = final.rstrip("/").rsplit("/", 1)[-1] if final.startswith("/submit/sub_") else None
        return sid, final

    def submit_mcp(self, url: str) -> dict[str, Any]:
        """The MCP's submit_software, as an MCP client calls it: its structured result."""
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "submit_software", "arguments": {"url": url}}}
        try:
            with self._request("/mcp", data=json.dumps(call).encode(),
                               headers={"Content-Type": "application/json",
                                        "Accept": "application/json, text/event-stream"}) as r:
                text = r.read(200_000).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as err:
            raise SiteError(f"POST /mcp answered {err.code}") from None
        except OSError as err:
            raise SiteError(f"POST /mcp failed: {err}") from None
        payload = None
        for line in text.splitlines():  # streamable HTTP: one `data:` line, or plain JSON
            if line.startswith("data:"):
                payload = line[5:].strip()
        try:
            message = json.loads(payload or text)
        except ValueError:
            raise SiteError(f"the MCP answer was not JSON: {text[:200]}") from None
        result = message.get("result") or {}
        if message.get("error") or result.get("isError"):
            raise SiteError(f"submit_software failed: {json.dumps(message)[:300]}")
        if isinstance(result.get("structuredContent"), dict):
            return result["structuredContent"]
        for part in result.get("content") or []:
            try:
                return json.loads(part.get("text") or "")
            except ValueError:
                continue
        raise SiteError(f"submit_software gave no result: {json.dumps(message)[:300]}")

    def status_page(self, sid: str) -> int:
        try:
            with self._request(f"/submit/{sid}", headers={"Accept": "text/html"}) as r:
                return r.status
        except urllib.error.HTTPError as err:
            return err.code
        except OSError:
            return 0

    def data_sha(self) -> str | None:
        try:
            with self._request("/", headers={"Accept": "application/json"}) as r:
                return json.loads(r.read(100_000)).get("data_sha256")
        except (OSError, ValueError):
            return None


# --- one run -----------------------------------------------------------------------------------------------------


@dataclass
class LaneResult:
    lane: str
    expect: str
    via: str
    url: str | None = None
    submission_id: str | None = None
    outcome: str = "failed"  # passed | failed | skipped
    detail: str = ""
    status: str | None = None  # the D1 status it ended in
    reason: str | None = None
    job_result: str | None = None
    job_lane: str | None = None
    level: str | None = None
    status_page: int | None = None
    seconds: float | None = None
    cost_usd: dict[str, float] = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)  # D1 statuses seen, in order


@dataclass
class Report:
    run: str
    started_at: str
    lanes: list[LaneResult]
    publish_leg: dict[str, Any]
    finished_at: str | None = None
    kept: bool = False

    @property
    def ok(self) -> bool:
        return all(r.outcome == "passed" for r in self.lanes) and self.publish_leg.get("ok", False)


def _row(d1: Database, sid: str) -> dict[str, Any] | None:
    rows = d1.query(sql("SELECT id, url, status, slug, reason, submitted_at FROM submissions WHERE id = ?1", sid))
    return rows[0] if rows else None


def _row_for(d1: Database, url: str) -> dict[str, Any] | None:
    rows = d1.query(sql("SELECT id, url, status, reason FROM submissions WHERE url = ?1", url))
    return rows[0] if rows else None


def _job(runs_dir: Path, sid: str) -> dict[str, Any] | None:
    try:
        return json.loads((runs_dir / "watch" / "jobs" / f"{sid}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sweep(runs_dir: Path, d1: Database, log: Callable[[str], None]) -> list[str]:
    """Earlier runs' leftovers: canary job files the watcher finished go to their run's folder; a parked canary
    whose D1 row is gone is put aside the same way, so the watcher never runs it."""
    moved = []
    for path in sorted((runs_dir / "watch" / "jobs").glob("*.json")):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        run = job.get("e2e")
        if not run:
            continue
        sid = job["submission_id"]
        if job.get("result") == "parked":
            try:
                if _row(d1, sid) is not None:
                    continue
            except Exception:  # noqa: BLE001 - D1 down: leave it for the next sweep
                continue
        elif job.get("result") in (None, "retry", "waiting"):
            continue
        _put_aside(runs_dir, run, sid)
        moved.append(sid)
    if moved:
        log(f"e2e: put aside {len(moved)} earlier test job(s): {', '.join(moved)}")
    return moved


def _put_aside(runs_dir: Path, run: str, sid: str) -> None:
    dest = run_dir(runs_dir, run)
    (dest / "jobs").mkdir(parents=True, exist_ok=True)
    job = runs_dir / "watch" / "jobs" / f"{sid}.json"
    if job.exists():
        job.replace(dest / "jobs" / job.name)
    work = runs_dir / "watch" / sid
    if work.exists():
        shutil.move(str(work), str(dest / "watch" / sid))


def _committed_since(data_dir: Path, since: datetime, needle: str) -> list[str]:
    """Commits since `since` whose message names `needle` (a test record must never be committed)."""
    try:
        out = subprocess.run(["git", "log", f"--since={since.isoformat()}", "--format=%h %s%n%b%x00"],
                             cwd=data_dir, capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, OSError):
        return []
    return [c.split(" ", 1)[0] for c in out.split("\x00") if needle in c]


def _main_records(data_dir: Path, ref: str) -> tuple[Path, Path, str]:
    """data/software as `ref` has it, unpacked in a temporary folder: (the temporary folder, the records in it, ref's
    short commit)."""
    import io
    import tarfile
    import tempfile

    def git(*args: str, cwd: Path = data_dir) -> bytes:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True).stdout

    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    rel = data_dir.resolve().relative_to(root.resolve()).as_posix()
    head = git("rev-parse", "--short", ref).decode().strip()
    tmp = Path(tempfile.mkdtemp(prefix="pickfit-e2e-"))
    tree = git("archive", "--format=tar", ref, rel, cwd=root)  # archive paths are relative to where it runs
    with tarfile.open(fileobj=io.BytesIO(tree), mode="r:") as tar:
        tar.extractall(tmp, filter="data")
    return tmp, tmp / rel, head


def publish_leg(site_hosts: list[Site], data_dir: Path, *, ref: str = "origin/main", fetch: bool = True) -> dict[str, Any]:
    """Without publishing: do the public hosts serve origin/main's records? A mismatch is a deploy that did not reach
    a host (pickfit.app and workers.dev are the same Cloudflare Worker, deployed by the CI), or one still
    running for a push of the last few minutes."""
    from pickfit.index import IndexBuildError, load_records

    if fetch:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=data_dir, capture_output=True)
    try:
        tmp, records, head = _main_records(data_dir, ref)
    except (subprocess.CalledProcessError, OSError, ValueError) as err:
        return {"ok": False, "detail": f"could not read {ref}'s records: {err}"}
    try:
        _, sha = load_records(records)
    except IndexBuildError as err:
        return {"ok": False, "detail": f"{ref}'s records do not build: {err}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    hosts = {site.base: site.data_sha() for site in site_hosts}
    stale = [base for base, live in hosts.items() if live != sha]
    return {"ok": not stale, "ref": ref, "commit": head, "data_sha256": sha, "hosts": hosts,
            "detail": "every host serves origin/main's records" if not stale else
            f"{', '.join(stale)} serve(s) other records than {ref} ({head}): its deploy did not reach them"}


class Runner:
    def __init__(self, d1: Database, site: Site, *, runs_dir: Path, data_dir: Path, lanes: tuple[str, ...],
                 hosts: list[Site] | None = None, keep: bool = False, clock: Callable[[], datetime] | None = None,
                 sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print,
                 poll_s: float = POLL_S, timeouts: dict[str, timedelta] | None = None) -> None:
        from pickfit.ledger import taipei_now

        self.d1, self.site, self.runs_dir, self.data_dir, self.lanes = d1, site, runs_dir, data_dir, lanes
        self.hosts = hosts if hosts is not None else [site]
        self.keep, self.sleep, self.log, self.poll_s = keep, sleep, log, poll_s
        self.clock = clock or taipei_now
        self.timeouts = timeouts or {}
        self.run_id = f"e2e-{self.clock().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
        self.started = self.clock()
        self._job_data: dict[str, Any] | None = None
        self.main_ref, self.fetch = "origin/main", True  # whose records the public hosts must serve

    # -- choosing and submitting

    def _choose(self, canary: Canary, result: LaneResult) -> None:
        """Submit the first usable candidate; sets url and submission_id, or leaves them None with the why."""
        ours = _submitted_ids(self.runs_dir)
        why = []
        for candidate in canary.urls:
            url = normalize(candidate) or candidate
            row = _row_for(self.d1, url)
            if row is not None:
                if row["id"] in ours or (row.get("reason") or "").startswith(REASON):
                    self.d1.execute(sql("DELETE FROM submissions WHERE id = ?1", row["id"]))
                    self.log(f"e2e [{canary.lane}] removed an earlier test row {row['id']} for {url}")
                else:
                    why.append(f"{url}: a person submitted it ({row['id']}, {row['status']})")
                    continue
            mark(self.runs_dir, url, self.run_id, self.clock())
            try:
                sid = self._submit(canary, url)
            except SiteError:
                unmark(self.runs_dir, self.run_id, url)
                raise
            if sid is None:
                unmark(self.runs_dir, self.run_id, url)
                why.append(f"{url}: pickfit lists it")
                continue
            _note_submitted(self.runs_dir, sid, url, self.run_id)
            result.url, result.submission_id = url, sid
            self.log(f"e2e [{canary.lane}] submitted {url} via {canary.via}: {sid}")
            return
        result.outcome, result.detail = "skipped", "no candidate left: " + "; ".join(why)

    def _submit(self, canary: Canary, url: str) -> str | None:
        if canary.via == "mcp":
            out = self.site.submit_mcp(url)
            if out.get("already_submitted") and out.get("submission_id"):
                raise SiteError(f"submit_software found an existing row for {url} ({out['submission_id']})")
            return out.get("submission_id")
        sid, _ = self.site.submit_form(url)
        return sid

    # -- following

    def _follow(self, canary: Canary, result: LaneResult, deadline: datetime) -> None:
        began = self.clock()
        sid = result.submission_id
        assert sid is not None
        while True:
            row = _row(self.d1, sid)
            if row is None:
                result.detail = "its D1 row disappeared"
                return
            step = row["status"] + (" (waiting for its lane)" if (row.get("reason") or "").startswith(
                "Waiting for pickfit's") else "")
            if not result.steps or result.steps[-1] != step:
                result.steps.append(step)
                self.log(f"e2e [{canary.lane}] {sid}: {step}")
            if row["status"] in TERMINAL:
                result.status, result.reason = row["status"], row.get("reason")
                break
            if self.clock() >= deadline:
                result.status, result.reason = row["status"], row.get("reason")
                result.detail = f"timed out after {canary.timeout} at {step}"
                result.seconds = round((self.clock() - began).total_seconds(), 1)
                self._read_job(result)
                return
            self.sleep(self.poll_s)
        result.seconds = round((self.clock() - began).total_seconds(), 1)
        for _ in range(6):  # the watcher saves its job right after the status write
            if self._read_job(result):
                break
            self.sleep(5)
        result.status_page = self.site.status_page(sid)
        self._judge(canary, result)

    def _read_job(self, result: LaneResult) -> bool:
        job = _job(self.runs_dir, result.submission_id or "")
        if not job or job.get("result") in (None, "retry", "waiting", "parked"):
            return False
        result.job_result, result.job_lane, result.level = job.get("result"), job.get("lane"), job.get("level")
        result.cost_usd = job.get("cost_usd") or {}
        self._job_data = job
        return True

    def _judge(self, canary: Canary, result: LaneResult) -> None:
        problems = []
        if result.status_page != 200:
            problems.append(f"its status page answered {result.status_page}")
        reason = result.reason or ""
        if canary.expect == "rejected":
            if result.status != "rejected" or reason.startswith(REASON):
                problems.append(f"expected a refusal, got {result.status} ({reason})")
        else:
            job = getattr(self, "_job_data", None) or {}
            if result.status == "listed" or result.status == "listed_unverified":
                problems.append(f"a test submission was {result.status}: it must never be listed")
            if job.get("e2e") != self.run_id:
                problems.append("the watcher did not take it as this run's test submission")
            if result.job_result != PASSED:
                problems.append(f"not verified: {reason or result.job_result}")
            if result.job_lane != canary.lane:
                problems.append(f"took the {result.job_lane} lane, not {canary.lane}")
            if job.get("publish_check"):
                problems.append(f"the publish plan check found: {'; '.join(job['publish_check'])[:300]}")
            slug = job.get("slug")
            if slug and not (run_dir(self.runs_dir, self.run_id) / "records" / f"{slug}.json").exists():
                problems.append("its record was not kept in the run's folder")
            if slug and (self.data_dir / f"{slug}.json").exists() and job.get("repo_id") and json.loads(
                    (self.data_dir / f"{slug}.json").read_text(encoding="utf-8")).get("repo_id") == job["repo_id"]:
                problems.append(f"its record is in {self.data_dir.name}: a test must never land")
            commits = _committed_since(self.data_dir, self.started, result.url or "")
            if commits:
                problems.append(f"committed in {', '.join(commits)}: a test must never be committed")
        self._job_data = None
        result.outcome = "failed" if problems else "passed"
        result.detail = "; ".join(problems) or (
            f"refused as expected: {reason}" if canary.expect == "rejected" else
            f"verified on the {result.job_lane} lane ({result.level}), not published")

    # -- the whole run

    def run(self) -> Report:
        self.started = self.clock()
        report = Report(run=self.run_id, started_at=self.started.isoformat(), lanes=[], publish_leg={}, kept=self.keep)
        self.log(f"e2e {self.run_id}: lanes {', '.join(self.lanes)} · {self.site.base} · nothing is published")
        sweep(self.runs_dir, self.d1, self.log)
        chosen: list[tuple[Canary, LaneResult, datetime]] = []
        for name in self.lanes:
            canary = CANARIES[name]
            result = LaneResult(lane=name, expect=canary.expect, via=canary.via)
            report.lanes.append(result)
            try:
                self._choose(canary, result)
            except SiteError as err:
                result.detail = str(err)
                continue
            if result.submission_id:
                chosen.append((canary, result, self.clock() + self.timeouts.get(name, canary.timeout)))
        for canary, result, deadline in chosen:  # all were submitted at once; follow each in turn
            try:
                self._follow(canary, result, deadline)
            except Exception as err:  # noqa: BLE001 - D1 down, say: the report says so, cleanup still runs
                result.detail = f"{type(err).__name__}: {str(err)[:300]}"
        report.publish_leg = publish_leg(self.hosts, self.data_dir, ref=self.main_ref, fetch=self.fetch)
        if not self.keep:
            self._clean(report)
        report.finished_at = self.clock().isoformat()
        out = run_dir(self.runs_dir, self.run_id)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(asdict(report) | {"ok": report.ok}, ensure_ascii=False,
                                                    indent=2) + "\n", encoding="utf-8")
        for r in report.lanes:
            cost = sum(r.cost_usd.values())
            self.log(f"e2e [{r.lane}] {r.outcome.upper()} · {r.url or '-'} · {r.detail}"
                     + (f" · {r.seconds:.0f}s" if r.seconds else "") + (f" · ${cost:.2f}" if cost else ""))
        self.log(f"e2e publish leg: {'ok' if report.publish_leg.get('ok') else 'FAILED'} · "
                 f"{report.publish_leg.get('detail')}")
        self.log(f"e2e {self.run_id}: {'PASSED' if report.ok else 'FAILED'} · report {out / 'report.json'}")
        return report

    def _clean(self, report: Report) -> None:
        ids = [r.submission_id for r in report.lanes if r.submission_id]
        for sid in ids:
            try:
                self.d1.execute(sql("DELETE FROM submissions WHERE id = ?1", sid))
            except Exception as err:  # noqa: BLE001 - the next run removes it (it is in submitted.jsonl)
                self.log(f"e2e: could not delete {sid} from D1: {err}")
        unmark(self.runs_dir, self.run_id)
        for r in report.lanes:
            job = _job(self.runs_dir, r.submission_id or "") if r.submission_id else None
            if job and job.get("result") not in (None, "retry", "waiting"):
                _put_aside(self.runs_dir, self.run_id, r.submission_id)
        if ids:
            self.log(f"e2e: removed {len(ids)} test row(s) from D1")
