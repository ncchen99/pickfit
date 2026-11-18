"""pickfit e2e: test submissions run every step and are never published. Fakes only: the site, D1, GitHub, the
sandboxes; the watcher is the real one."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from pickfit import e2e
from pickfit.index import load_records
from pickfit.lanes import Policy
from pickfit.watch import Settings, Watcher
from queue_fakes import EXAMPLE, checkout, d1, git, submission, submit
from test_profiles import extraction
from test_watch import NOW, Pipeline
from test_watch_lanes import MAC_ONLY, FakeLane, mac_run, make, work

TINYQ = "https://github.com/someone/tinyq"


# One listed record that is not a test fixture (its host is not .invalid), so the publish plan check passes.
LISTED = {**EXAMPLE, "repo": {**EXAMPLE["repo"], "url": "https://github.com/example/frobtail"}}


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Any]:
    data_dir, worker_dir = checkout(tmp_path, {"frobtail": LISTED})
    return {"tmp": tmp_path, "data": data_dir, "worker": worker_dir, "d1": d1(tmp_path), "runs": tmp_path / "runs"}


def commits(data_dir: Path) -> int:
    return int(git(data_dir.parent.parent, "rev-list", "--count", "HEAD").strip())


# --- markers ------------------------------------------------------------------------------------------------------


def test_a_marker_names_its_run_until_it_expires(tmp_path: Path) -> None:
    e2e.mark(tmp_path, "https://GitHub.com/Someone/TinyQ.git", "e2e-1", NOW)
    assert e2e.marked(tmp_path, TINYQ, NOW + timedelta(minutes=5)) == "e2e-1"  # normalized like the Worker's row
    assert e2e.marked(tmp_path, TINYQ, NOW + e2e.MARK_FOR + timedelta(seconds=1)) is None
    assert e2e.marked(tmp_path, "https://github.com/someone/other", NOW) is None
    e2e.unmark(tmp_path, "e2e-1")
    assert e2e.marked(tmp_path, TINYQ, NOW) is None


def test_lane_names() -> None:
    assert e2e.lanes_from("default") == ("reject", "linux", "web")
    assert e2e.lanes_from("all") == e2e.ALL
    assert e2e.lanes_from("linux-web") == ("linux", "web") == e2e.lanes_from("linux,web")
    with pytest.raises(ValueError):
        e2e.lanes_from("linux-bsd")


# --- the watcher with a test submission ----------------------------------------------------------------------------


def test_a_test_submission_runs_every_step_and_never_lands(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_t", TINYQ)
    e2e.mark(env["runs"], TINYQ, "e2e-1", NOW)
    pipeline = Pipeline(env["tmp"])
    before = commits(env["data"])
    lines: list[str] = []
    [job] = make(env, pipeline, {}, lines=lines, names=("linux",)).run(once=True)
    row = submission(env["d1"], "sub_t")
    assert (job.e2e, job.result, job.lane, job.level) == ("e2e-1", e2e.PASSED, "linux", "function")
    assert pipeline.calls == ["prescreen", "extract", "verify", "score"]  # the same steps as a real one
    assert row["status"] == "rejected" and row["reason"].startswith(e2e.REASON + "would be listed as verified")
    assert not job.landed and job.commit is None and not (env["data"] / "tinyq.json").exists()
    assert commits(env["data"]) == before
    assert (env["runs"] / "e2e" / "e2e-1" / "records" / "tinyq.json").exists()
    assert job.publish_check == []  # the plan check ran on a copy with the record added
    assert any("end-to-end test e2e-1" in line for line in lines)


def test_an_unmarked_submission_is_not_a_test(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_r", TINYQ)
    e2e.mark(env["runs"], "https://github.com/someone/other", "e2e-1", NOW)
    [job] = make(env, Pipeline(env["tmp"]), {}, names=("linux",)).run(once=True)
    assert job.e2e is None and job.result == "ready" and (env["data"] / "tinyq.json").exists()


def test_a_test_does_not_take_the_repository_from_a_real_submission(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_t", TINYQ)
    e2e.mark(env["runs"], TINYQ, "e2e-1", NOW)
    pipeline = Pipeline(env["tmp"])
    make(env, pipeline, {}, names=("linux",)).run(once=True)
    e2e.unmark(env["runs"], "e2e-1")
    env["d1"].execute("DELETE FROM submissions WHERE id = 'sub_t'")  # the test's cleanup
    submit(env["d1"], "sub_real", TINYQ, at="2026-10-30T11:00:00.000Z")
    [job] = make(env, Pipeline(env["tmp"]), {}, names=("linux",)).run(once=True)  # a fresh sandbox run
    assert job.result == "ready" and job.e2e is None  # not "Same repository as an earlier submission"


def test_a_refused_test_keeps_pickfits_own_reason(env: dict[str, Any]) -> None:
    url = "https://github.com/someone/missing"
    submit(env["d1"], "sub_x", url)
    e2e.mark(env["runs"], url, "e2e-1", NOW)
    [job] = make(env, Pipeline(env["tmp"]), {}, names=("linux",)).run(once=True)
    row = submission(env["d1"], "sub_x")
    assert job.result == "rejected" and row["status"] == "rejected" and not row["reason"].startswith(e2e.REASON)


def test_a_mac_test_does_not_wait_for_a_full_batch(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_m", TINYQ)
    e2e.mark(env["runs"], TINYQ, "e2e-1", NOW)
    mac = FakeLane("macos", "macos", env["tmp"], mac_run("run-mac-1"),
                   policy=Policy(min_batch=10, max_wait=timedelta(hours=24)))
    lines: list[str] = []
    jobs = make(env, Pipeline(env["tmp"], result=extraction(**MAC_ONLY)), {"macos": mac}, lines=lines).run(once=True)
    job = jobs[-1]
    assert (job.result, job.lane) == (e2e.PASSED, "macos") and work(mac) == ["available", "verify"]
    assert any("an end-to-end test is waiting" in line for line in lines)
    assert submission(env["d1"], "sub_m")["reason"].startswith(e2e.REASON + "would be listed as verified")


def test_a_website_test_claims_its_visit_in_its_own_file(env: dict[str, Any]) -> None:
    from test_web_intake import URL, Fakes

    submit(env["d1"], "sub_w", URL)
    e2e.mark(env["runs"], URL, "e2e-1", NOW)
    fakes = Fakes()
    asked: list[Path] = []
    real = fakes.steps()
    steps = Pipeline(env["tmp"]).steps()
    steps.site = replace(real, with_visits=lambda path: asked.append(path) or real)
    s = Settings(data_dir=env["data"], runs_dir=env["runs"], db_path=env["runs"] / "pipeline.db",
                 worker_dir=env["worker"], lanes=("linux", "web"))
    [job] = Watcher(env["d1"], steps, s, clock=lambda: NOW, log=lambda line: None).run(once=True)
    assert asked == [env["runs"] / "e2e" / "e2e-1" / "visits.jsonl"]
    assert (job.result, job.lane) == (e2e.PASSED, "web") and not (env["data"] / "word-pad.json").exists()


# --- the runner, end to end with a fake site ------------------------------------------------------------------------


class FakeSite:
    """The website and the MCP: each submission inserts the row the Worker would; a listed URL inserts none."""

    def __init__(self, db: Any, *, listed: set[str] = frozenset(), sha: str | None = None) -> None:
        self.db, self.listed, self.sha = db, set(listed), sha
        self.base = "https://pickfit.test"
        self.n = 0
        self.calls: list[tuple[str, str]] = []

    def _insert(self, url: str) -> str | None:
        url = e2e.normalize(url) or url
        if url in self.listed:
            return None
        self.n += 1
        sid = f"sub_e2e{self.n}"
        submit(self.db, sid, url)
        return sid

    def submit_form(self, url: str) -> tuple[str | None, str]:
        self.calls.append(("form", url))
        sid = self._insert(url)
        return sid, f"/submit/{sid}" if sid else "/submit"

    def submit_mcp(self, url: str) -> dict[str, Any]:
        self.calls.append(("mcp", url))
        sid = self._insert(url)
        return {"submission_id": sid, "status": "queued" if sid else "listed", "already_submitted": not sid}

    def status_page(self, sid: str) -> int:
        return 200

    def data_sha(self) -> str | None:
        return self.sha


TEST_CANARIES = {
    "reject": e2e.Canary("reject", ("https://github.com/someone/missing",), "rejected", timedelta(minutes=30), "mcp",
                         "refusal"),
    "linux": e2e.Canary("linux", ("https://github.com/someone/listed", TINYQ), "passed", timedelta(minutes=75), "web",
                        "linux"),
}


def runner(env: dict[str, Any], site: FakeSite, pipeline: Pipeline, **kw: Any) -> e2e.Runner:
    clock = {"t": NOW}

    def now() -> Any:
        clock["t"] += timedelta(seconds=1)
        return clock["t"]

    watcher = make(env, pipeline, {}, names=("linux",), clock=now)
    ticks = {"n": 0}

    def sleep(_s: float) -> None:  # the watcher on the machine, polled once between the runner's looks
        ticks["n"] += 1
        if ticks["n"] == 1:
            watcher.run(once=True)

    r = e2e.Runner(env["d1"], site, runs_dir=env["runs"], data_dir=env["data"], lanes=("reject", "linux"),
                   hosts=[site], clock=now, sleep=sleep, log=kw.pop("log", lambda line: None), **kw)
    r.main_ref, r.fetch = "main", False
    return r


def test_a_run_submits_follows_judges_and_cleans_up(env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(e2e, "CANARIES", TEST_CANARIES)
    _, sha = load_records(env["data"])
    site = FakeSite(env["d1"], listed={"https://github.com/someone/listed"}, sha=sha)
    before = commits(env["data"])
    report = runner(env, site, Pipeline(env["tmp"])).run()
    by = {r.lane: r for r in report.lanes}
    assert report.ok, [(r.lane, r.detail) for r in report.lanes] + [report.publish_leg]
    assert by["reject"].outcome == "passed" and by["reject"].status == "rejected"
    assert by["linux"].url == TINYQ and by["linux"].job_lane == "linux" and by["linux"].level == "function"
    assert site.calls[0] == ("mcp", "https://github.com/someone/missing")  # the reject canary goes through the MCP
    assert ("form", "https://github.com/someone/listed") in site.calls  # listed: the next candidate is used
    # Nothing published, nothing left behind.
    assert commits(env["data"]) == before and [p.name for p in env["data"].glob("*.json")] == ["frobtail.json"]
    assert env["d1"].query("SELECT id FROM submissions") == []
    assert list((env["runs"] / "watch" / "jobs").glob("*.json")) == []
    out = env["runs"] / "e2e" / report.run
    assert (out / "jobs" / f"{by['linux'].submission_id}.json").exists() and (out / "records" / "tinyq.json").exists()
    assert json.loads((out / "report.json").read_text())["ok"] is True
    assert e2e.marked(env["runs"], TINYQ, NOW) is None


def test_a_person_s_submission_of_a_canary_is_left_alone(env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(e2e, "CANARIES", {"linux": replace(TEST_CANARIES["linux"], urls=(TINYQ,))})
    submit(env["d1"], "sub_person", TINYQ)
    site = FakeSite(env["d1"])
    r = runner(env, site, Pipeline(env["tmp"]))
    r.lanes = ("linux",)
    report = r.run()
    [lane] = report.lanes
    assert lane.outcome == "skipped" and "a person submitted it (sub_person" in lane.detail and not report.ok
    assert submission(env["d1"], "sub_person")["status"] == "queued" and site.calls == []


def test_an_earlier_runs_leftover_row_is_replaced(env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(e2e, "CANARIES", {"linux": replace(TEST_CANARIES["linux"], urls=(TINYQ,))})
    submit(env["d1"], "sub_old", TINYQ)
    env["d1"].execute(f"UPDATE submissions SET status = 'rejected', reason = '{e2e.REASON}would be listed' "
                      "WHERE id = 'sub_old'")
    _, sha = load_records(env["data"])
    r = runner(env, FakeSite(env["d1"], sha=sha), Pipeline(env["tmp"]))
    r.lanes = ("linux",)
    report = r.run()
    assert report.ok and report.lanes[0].submission_id != "sub_old"


def test_a_host_serving_other_records_fails_the_publish_leg(env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(e2e, "CANARIES", {"reject": TEST_CANARIES["reject"]})
    site = FakeSite(env["d1"], sha="0" * 64)
    r = runner(env, site, Pipeline(env["tmp"]))
    r.lanes = ("reject",)
    report = r.run()
    assert report.lanes[0].outcome == "passed" and not report.publish_leg["ok"] and not report.ok
    assert "https://pickfit.test" in report.publish_leg["detail"]
