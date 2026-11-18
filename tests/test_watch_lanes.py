"""pickfit watch lanes: Windows and macOS records park, and their lane runs them when its policy says so.
Fakes only (the same D1, GitHub and verify fakes as test_watch)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from pickfit.lanes import AT_ONCE, PARKED_PREFIX, Policy, due_lanes
from pickfit.schema import SoftwareRecord, VerificationRun
from pickfit.watch import LANE_HOLD, MAX_ATTEMPTS, READY_REASON, Settings, Watcher, lane_status, requeue_stale
from queue_fakes import FakeVerify, checkout, d1, passed_run, repo_item, submission, submit, unverified_run
from test_profiles import cited, extraction
from test_watch import NOW, Pipeline

MAC_ONLY = {"platforms": cited(["macos"], "Works on macOS and Linux")}
WINDOWS_AND_MAC = {"platforms": cited(["macos", "windows"], "Works on macOS and Linux")}


def mac_run(run_id: str) -> VerificationRun:
    run = passed_run(run_id, ["cargo install tinyq"], method="cargo").model_dump(mode="json")
    run["os"] = "macos"
    return VerificationRun.model_validate(run)


def mac_unverified(run_id: str) -> VerificationRun:
    run = unverified_run(run_id).model_dump(mode="json")
    run["os"] = "macos"
    return VerificationRun.model_validate(run)


def work(lane: FakeLane) -> list[str]:
    """What the lane was asked to do, leaving out the idle calls of ticks when nothing was parked yet."""
    return [c for c in lane.calls if c != "idle"]


class FakeLane:
    def __init__(self, name: str, os: str, tmp: Path, *runs: VerificationRun, policy: Policy = AT_ONCE,
                 available: str | None = None, live: bool = False, stop: str = "finish") -> None:
        self.name, self.os, self.display, self.policy, self.concurrency = name, os, True, policy, 1
        self.verifier = FakeVerify(tmp, *runs, stop=stop)
        self.calls: list[str] = []
        self.why, self.up = available, live

    def live(self) -> bool:
        return self.up

    def available(self, log: Any) -> str | None:
        self.calls.append("available")
        return self.why

    def verify(self, task: Any, data_dir: Path, log: Any) -> Any:
        self.calls.append("verify")
        return self.verifier(task, data_dir, log)

    def idle(self, log: Any) -> None:
        self.calls.append("idle")

    def status(self) -> dict[str, Any]:
        return {"fake": True}


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> Any:
        return self.now


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Any]:
    data_dir, worker_dir = checkout(tmp_path)
    return {"tmp": tmp_path, "data": data_dir, "worker": worker_dir, "d1": d1(tmp_path)}


def make(env: dict[str, Any], pipeline: Pipeline, lanes: dict[str, FakeLane], *, clock: Clock | None = None,
         lines: list[str] | None = None, names: tuple[str, ...] = ("linux", "windows", "macos")) -> Watcher:
    steps = pipeline.steps()
    steps.lanes = lanes
    s = Settings(data_dir=env["data"], runs_dir=env["tmp"] / "runs", db_path=env["tmp"] / "runs" / "pipeline.db",
                 worker_dir=env["worker"], lanes=names)
    out = lines if lines is not None else []
    return Watcher(env["d1"], steps, s, clock=clock or (lambda: NOW), log=out.append)


def two_repos() -> dict[str, dict[str, Any]]:
    return {"someone/tinyq": repo_item(7, "someone/tinyq"), "other/macq": repo_item(8, "other/macq")}


# --- parking -------------------------------------------------------------------------


def test_a_mac_only_app_parks_until_its_batch_is_due(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    pipeline = Pipeline(env["tmp"], result=extraction(**MAC_ONLY))
    mac = FakeLane("macos", "macos", env["tmp"], mac_run("run-mac-1"),
                   policy=Policy(min_batch=2, max_wait=timedelta(hours=24)))
    [job] = make(env, pipeline, {"macos": mac}).run(once=True)
    row = submission(env["d1"], "sub_1")
    assert (job.result, job.lane, row["status"]) == ("parked", "macos", "verifying")
    assert row["reason"].startswith(PARKED_PREFIX + "next macOS batch") and "2 Mac apps" in row["reason"]
    assert "verify" not in pipeline.calls and work(mac) == []  # one of two waiting: no batch
    assert not (env["data"] / "tinyq.json").exists()
    assert (env["tmp"] / "runs" / "watch" / "sub_1" / "software" / "tinyq.json").exists()
    # A parked row is not a crashed watcher's: it stays parked however long it waits.
    assert requeue_stale(env["d1"], NOW + timedelta(hours=30), set()) == []


def test_a_batch_starts_once_enough_wait_and_lands_each_record(env: dict[str, Any]) -> None:
    pipeline = Pipeline(env["tmp"], repos=two_repos(), result=extraction(**MAC_ONLY))
    mac = FakeLane("macos", "macos", env["tmp"], mac_run("run-mac-1"), mac_run("run-mac-2"),
                   policy=Policy(min_batch=2, max_wait=timedelta(hours=24)))
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    submit(env["d1"], "sub_2", "https://github.com/other/macq", at="2026-10-30T10:01:00.000Z")
    jobs = make(env, pipeline, {"macos": mac}).run(once=True)
    assert work(mac) == ["available", "verify", "verify"]
    finished = {j.submission_id: j for j in jobs if j.result != "parked"}
    assert {j.result for j in finished.values()} == {"ready"}
    for sid in ("sub_1", "sub_2"):
        row = submission(env["d1"], sid)
        assert (row["status"], row["reason"]) == ("verifying", READY_REASON)
    record = SoftwareRecord.model_validate_json((env["data"] / "tinyq.json").read_text())
    assert record.install.macos.basis == "replayed" and record.verification.level == "function"
    assert finished["sub_1"].lane == "macos" and finished["sub_1"].parked_at


def test_the_oldest_wait_starts_a_batch_of_one(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    pipeline = Pipeline(env["tmp"], result=extraction(**MAC_ONLY))
    mac = FakeLane("macos", "macos", env["tmp"], mac_run("run-mac-1"),
                   policy=Policy(min_batch=10, max_wait=timedelta(hours=24)))
    clock = Clock()
    w = make(env, pipeline, {"macos": mac}, clock=clock)
    w.run(once=True)
    clock.now = NOW + timedelta(hours=23)
    w.run(once=True)
    assert work(mac) == []  # not due yet
    clock.now = NOW + timedelta(hours=24, minutes=1)
    jobs = w.run(once=True)
    assert "verify" in mac.calls and jobs[-1].result == "ready"


def test_a_live_lane_runs_a_parked_job_at_once(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    mac = FakeLane("macos", "macos", env["tmp"], mac_run("run-mac-1"), policy=Policy(min_batch=10,
                   max_wait=timedelta(hours=24)), live=True)
    jobs = make(env, Pipeline(env["tmp"], result=extraction(**MAC_ONLY)), {"macos": mac}).run(once=True)
    assert [j.result for j in jobs] == ["parked", "ready"]


def test_windows_comes_before_macos_and_linux_before_both(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    win = FakeLane("windows", "windows", env["tmp"], mac_run("run-win-1"))
    mac = FakeLane("macos", "macos", env["tmp"], mac_run("run-mac-1"), live=True)
    jobs = make(env, Pipeline(env["tmp"], result=extraction(**WINDOWS_AND_MAC)), {"windows": win, "macos": mac}
                ).run(once=True)
    assert jobs[0].lane == "windows" and "verify" in win.calls and "verify" not in mac.calls
    # A tool the Linux box runs never reaches a lane.
    submit(env["d1"], "sub_2", "https://github.com/other/macq")
    pipeline = Pipeline(env["tmp"], repos=two_repos())
    w = make(env, pipeline, {"windows": win, "macos": mac})
    [job] = [j for j in w.run(once=True) if j.submission_id == "sub_2"]
    assert job.lane == "linux" and "verify" in pipeline.calls


def test_a_lane_that_is_off_leaves_the_old_behaviour(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    mac = FakeLane("macos", "macos", env["tmp"], mac_run("run-mac-1"), live=True)
    pipeline = Pipeline(env["tmp"], result=extraction(**MAC_ONLY))
    make(env, pipeline, {"macos": mac}, names=("linux",)).run(once=True)
    row = submission(env["d1"], "sub_1")
    assert row["status"] == "listed_unverified" and "Linux sandbox cannot run it (platforms macos only)" in row["reason"]
    assert work(mac) == []


def test_a_lane_that_is_not_ready_rests_and_keeps_its_jobs(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    mac = FakeLane("macos", "macos", env["tmp"], mac_run("run-mac-1"), available="no Mac host is ready")
    lines: list[str] = []
    clock = Clock()
    w = make(env, Pipeline(env["tmp"], result=extraction(**MAC_ONLY)), {"macos": mac}, clock=clock, lines=lines)
    w.run(once=True)
    assert work(mac) == ["available"] and any("not ready: no Mac host is ready" in line for line in lines)
    w.run(once=True)
    assert work(mac) == ["available"]  # resting
    clock.now = NOW + LANE_HOLD + timedelta(seconds=1)
    mac.why = None
    jobs = w.run(once=True)
    assert jobs[-1].result == "ready" and submission(env["d1"], "sub_1")["reason"] == READY_REASON


def test_a_lane_box_that_never_starts_parks_again_then_gives_up(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    runs = [mac_unverified(f"run-mac-{i}") for i in range(MAX_ATTEMPTS)]
    mac = FakeLane("macos", "macos", env["tmp"], *runs, stop="box_error")
    clock = Clock()
    w = make(env, Pipeline(env["tmp"], result=extraction(**MAC_ONLY)), {"macos": mac}, clock=clock)
    jobs = w.run(once=True)
    assert jobs[-1].result == "parked" and jobs[-1].lane_tries == 1
    assert submission(env["d1"], "sub_1")["reason"].startswith(PARKED_PREFIX)
    for i in range(1, MAX_ATTEMPTS):
        clock.now = NOW + (LANE_HOLD + timedelta(seconds=1)) * i
        jobs = w.run(once=True)
    row = submission(env["d1"], "sub_1")
    assert row["status"] == "listed_unverified"
    assert row["reason"] == "Added without a verified install: pickfit's macos sandbox did not start for it (box_error, 3 tries)."
    assert (env["data"] / "tinyq.json").exists()


def test_a_parked_record_keeps_its_slug_across_a_restart(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    mac = FakeLane("macos", "macos", env["tmp"], policy=Policy(min_batch=5, max_wait=timedelta(days=9)))
    make(env, Pipeline(env["tmp"], result=extraction(**MAC_ONLY)), {"macos": mac}).run(once=True)
    again = make(env, Pipeline(env["tmp"]), {"macos": mac})
    assert "tinyq" in again._slugs_in_flight


def test_idle_lanes_are_told_so(env: dict[str, Any]) -> None:
    mac = FakeLane("macos", "macos", env["tmp"])
    make(env, Pipeline(env["tmp"]), {"macos": mac}).run(once=True)
    assert mac.calls == ["idle"]


def test_status_lists_each_lanes_parked_jobs(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    mac = FakeLane("macos", "macos", env["tmp"], policy=Policy(min_batch=3, max_wait=timedelta(hours=24)))
    make(env, Pipeline(env["tmp"], result=extraction(**MAC_ONLY)), {"macos": mac}).run(once=True)
    status = lane_status(env["tmp"] / "runs" / "watch" / "jobs", {"macos": mac}, now=NOW + timedelta(hours=2))
    assert [p["id"] for p in status["macos"]["parked"]] == ["sub_1"]
    assert status["macos"]["oldest_wait_hours"] == 2.0 and status["macos"]["due"] is None
    assert status["macos"]["fake"] is True
    json.dumps(status)


def test_policy_and_due_lanes() -> None:
    p = Policy(min_batch=3, max_wait=timedelta(hours=24))
    assert p.due([], NOW) is None and p.due([NOW], NOW) is None
    assert "3 waiting" in p.due([NOW] * 3, NOW)
    assert "waited 25.0 h" in p.due([NOW - timedelta(hours=25)], NOW)
    assert AT_ONCE.due([NOW], NOW) and AT_ONCE.describe() == "at once"
    lane = FakeLane("macos", "macos", Path("."), policy=p)
    assert due_lanes({"macos": [NOW]}, {"macos": lane}, NOW) == {}
    lane.up = True
    assert due_lanes({"macos": [NOW]}, {"macos": lane}, NOW) == {"macos": "a machine is up"}


def parse(argv: list[str]) -> Any:
    import argparse

    from pickfit.cli import _add_queue_commands

    parser = argparse.ArgumentParser()
    _add_queue_commands(parser.add_subparsers(dest="command"))
    return parser.parse_args(argv)


def test_the_watch_command_builds_its_lanes_from_flags() -> None:
    from pickfit.cli import _watch_lanes

    args = parse(["watch", "--mac-batch", "4", "--mac-max-wait-hours", "12", "--mac-rent", "--mac-max-rentals", "2"])
    assert args.lanes == "linux,windows,macos,web"
    lanes = _watch_lanes(args, ("linux", "windows", "macos"))
    assert set(lanes) == {"windows", "macos"}
    mac = lanes["macos"]
    assert (mac.policy.min_batch, mac.policy.hours, mac.rent, mac.max_rentals, mac.root_from_provider) == (
        4, 12.0, True, 2, False)
    assert lanes["windows"].os == "windows" and lanes["windows"].policy.describe() == "at once"
    assert _watch_lanes(parse(["watch"]), ("linux",)) == {}


def test_the_watch_command_refuses_unknown_lanes_or_no_linux(capsys: pytest.CaptureFixture[str]) -> None:
    from pickfit.cli import main

    assert main(["watch", "--lanes", "macos", "--status", "--local"]) == 2
    assert main(["watch", "--lanes", "linux,bsd", "--status", "--local"]) == 2
    assert "always has linux" in capsys.readouterr().err


# --- the web lane: website submissions (pickfit.web_intake, with its own fakes) ----------------------


def web_watcher(env: dict[str, Any], fakes: Any, *, lines: list[str] | None = None) -> Watcher:
    steps = Pipeline(env["tmp"]).steps()
    steps.site = fakes.steps()
    s = Settings(data_dir=env["data"], runs_dir=env["tmp"] / "runs", db_path=env["tmp"] / "runs" / "pipeline.db",
                 worker_dir=env["worker"], lanes=("linux", "web"))
    return Watcher(env["d1"], steps, s, clock=lambda: NOW, log=(lines if lines is not None else []).append)


def test_a_website_submission_is_read_visited_once_and_lands(env: dict[str, Any]) -> None:
    from test_web_intake import URL, Fakes

    submit(env["d1"], "sub_w", URL)
    fakes = Fakes()
    [job] = web_watcher(env, fakes).run(once=True)
    row = submission(env["d1"], "sub_w")
    assert (job.result, job.lane, job.slug, job.level) == ("ready", "web", "word-pad", "function")
    assert (row["status"], row["reason"]) == ("verifying", READY_REASON)
    assert fakes.calls == ["screen", "extract", "verify"]
    record = SoftwareRecord.model_validate_json((env["data"] / "word-pad.json").read_text())
    assert record.kind == "web_app" and record.verification.level == "function"
    assert job.cost_usd["model"] > 0 and job.cost_usd["box"] > 0


def test_a_refused_website_gets_pickfits_reason(env: dict[str, Any]) -> None:
    from test_web_intake import URL, Fakes, decision

    submit(env["d1"], "sub_w", URL)
    web_watcher(env, Fakes(screen=decision(False, account="needed"))).run(once=True)
    row = submission(env["d1"], "sub_w")
    assert (row["status"], row["reason"]) == ("rejected", "It needs an account for its main use.")


def test_a_website_that_keeps_failing_is_rejected_as_a_site(env: dict[str, Any]) -> None:
    from test_web_intake import URL, Fakes

    submit(env["d1"], "sub_w", URL)
    jobs = web_watcher(env, Fakes(extract_status="error")).run(once=True)
    assert [j.result for j in jobs] == ["retry"] * (MAX_ATTEMPTS - 1) + ["rejected"]
    assert submission(env["d1"], "sub_w")["reason"] == f"pickfit could not finish reading this site after {MAX_ATTEMPTS} tries."


def test_without_the_web_lane_a_website_waits(env: dict[str, Any]) -> None:
    from test_web_intake import URL, Fakes

    submit(env["d1"], "sub_w", URL)
    w = web_watcher(env, Fakes())
    w.s.lanes = ("linux",)
    assert w.run(once=True) == [] and submission(env["d1"], "sub_w")["status"] == "queued"


# --- publishing by push: the record commits go to origin/main, whose CI deploys them ----------------


def remote_for(env: dict[str, Any]) -> Path:
    """A bare origin the checkout pushes to, holding its first commit."""
    from queue_fakes import git

    repo = env["data"].parent.parent
    origin = env["tmp"] / "origin.git"
    git(env["tmp"], "init", "-q", "--bare", "-b", "main", str(origin))
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "origin", "main")
    return origin


def pusher(calls: list[Any]) -> Any:
    from pickfit.publish import push_publish

    def push(data_dir: Path, worker_dir: Path, out: Any) -> Any:
        pushed = push_publish(data_dir, worker_dir, out=out, translate=False)
        calls.append(pushed)
        return pushed
    return push


def test_push_mode_pushes_the_record_and_lists_it_only_once_deployed(env: dict[str, Any]) -> None:
    from queue_fakes import git

    origin = remote_for(env)
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    calls: list[Any] = []
    live = {"sha": None}
    s = Settings(data_dir=env["data"], runs_dir=env["tmp"] / "runs", db_path=env["tmp"] / "runs" / "p.db",
                 worker_dir=env["worker"], publish=True, publish_mode="push")
    w = Watcher(env["d1"], Pipeline(env["tmp"]).steps(), s, clock=lambda: NOW, log=lambda line: None,
                push_fn=pusher(calls), live_sha=lambda: live["sha"])
    [job] = w.run(once=True)
    assert [c.code for c in calls] == [0] and calls[0].code_changed is False
    assert git(origin, "log", "-1", "--format=%s", "main").strip() == "Add tinyq from a submission (pickfit watch)"
    assert "sub_1" not in git(origin, "log", "-1", "--format=%B", "main")  # the submitter's key stays private
    assert job.result == "ready" and submission(env["d1"], "sub_1")["reason"] == READY_REASON
    # CI deployed it: the live Worker serves this data, so the next tick lists it.
    from pickfit.index import load_records

    live["sha"] = load_records(env["data"])[1]
    w.run(once=True)
    assert submission(env["d1"], "sub_1")["status"] == "listed"


def test_push_mode_rebases_onto_new_work_and_restarts_for_new_code(env: dict[str, Any]) -> None:
    from queue_fakes import git

    origin = remote_for(env)
    other = env["tmp"] / "other"
    git(env["tmp"], "clone", "-q", str(origin), str(other))
    git(other, "config", "user.email", "o@example.invalid")
    git(other, "config", "user.name", "o")
    (other / "pickfit").mkdir()
    (other / "pickfit" / "new.py").write_text("x = 1\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "new code")
    git(other, "push", "-q", "origin", "main")
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    calls: list[Any] = []
    s = Settings(data_dir=env["data"], runs_dir=env["tmp"] / "runs", db_path=env["tmp"] / "runs" / "p.db",
                 worker_dir=env["worker"], publish=True, publish_mode="push", interval_s=0)
    w = Watcher(env["d1"], Pipeline(env["tmp"]).steps(), s, clock=lambda: NOW, log=lambda line: None,
                push_fn=pusher(calls))
    ticks: list[int] = []

    def sleep(seconds: float) -> None:  # the job runs in a thread: give it real time
        import time

        ticks.append(1)
        assert len(ticks) < 400, "watch did not stop for the new code"
        time.sleep(0.05)

    w.run(sleep=sleep)  # returns by itself once the push brought new code and nothing runs
    assert calls[0].code == 0 and calls[0].code_changed is True and w.restart_wanted
    assert git(origin, "log", "--format=%s", "main").split("\n")[:2] == [
        "Add tinyq from a submission (pickfit watch)", "new code"]


def test_push_mode_keeps_a_conflicting_commit_local(env: dict[str, Any]) -> None:
    from pickfit.publish import push_publish
    from queue_fakes import git

    origin = remote_for(env)
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    s = Settings(data_dir=env["data"], runs_dir=env["tmp"] / "runs", db_path=env["tmp"] / "runs" / "p.db",
                 worker_dir=env["worker"])
    Watcher(env["d1"], Pipeline(env["tmp"]).steps(), s, clock=lambda: NOW, log=lambda line: None).run(once=True)
    other = env["tmp"] / "other"
    git(env["tmp"], "clone", "-q", str(origin), str(other))
    git(other, "config", "user.email", "o@example.invalid")
    git(other, "config", "user.name", "o")
    (other / "data" / "software").mkdir(parents=True, exist_ok=True)
    (other / "data" / "software" / "tinyq.json").write_text("{}\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "a different tinyq")
    git(other, "push", "-q", "origin", "main")
    lines: list[str] = []
    pushed = push_publish(env["data"], env["worker"], out=lines.append, translate=False)
    assert pushed.code == 1 and any("conflicted; aborted" in line for line in lines)
    repo = env["data"].parent.parent
    assert git(repo, "status", "--porcelain") == "" and "rebase" not in git(repo, "status")
    assert git(origin, "log", "-1", "--format=%s", "main").strip() == "a different tinyq"


def test_an_idle_watcher_restarts_for_new_code_on_main(env: dict[str, Any]) -> None:
    s = Settings(data_dir=env["data"], runs_dir=env["tmp"] / "runs", db_path=env["tmp"] / "runs" / "p.db",
                 worker_dir=env["worker"], interval_s=0, update_check_s=0.01)
    w = Watcher(env["d1"], Pipeline(env["tmp"]).steps(), s, clock=lambda: NOW, log=lambda line: None)
    looks: list[int] = []

    def upstream(data_dir: Path) -> list[str]:
        looks.append(1)
        return [] if len(looks) < 2 else ["pickfit/watch.py"]

    w._upstream_code = upstream

    def sleep(seconds: float) -> None:
        import time

        assert len(looks) < 50
        time.sleep(0.02)

    w.run(sleep=sleep)
    assert w.restart_wanted and len(looks) == 2


def test_upstream_code_sees_program_files_only(env: dict[str, Any]) -> None:
    from pickfit.publish import upstream_code
    from queue_fakes import git

    origin = remote_for(env)
    other = env["tmp"] / "other"
    git(env["tmp"], "clone", "-q", str(origin), str(other))
    git(other, "config", "user.email", "o@example.invalid")
    git(other, "config", "user.name", "o")
    (other / "notes.md").write_text("words\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "docs")
    git(other, "push", "-q", "origin", "main")
    assert upstream_code(env["data"]) == []
    (other / "pyproject.toml").write_text("[project]\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "deps")
    git(other, "push", "-q", "origin", "main")
    assert upstream_code(env["data"]) == ["pyproject.toml"]


def test_the_services_watch_command_parses() -> None:
    """deploy/watch/pickfit-watch.service runs flags the CLI has, and publishes by push."""
    import shlex

    unit = (Path(__file__).resolve().parent.parent / "deploy" / "watch" / "pickfit-watch.service").read_text()
    line = unit.split("ExecStart=", 1)[1].split("\nRestart=", 1)[0].replace("\\\n", " ")
    argv = shlex.split(line)
    args = parse(argv[argv.index("pickfit") + 1:])
    assert args.publish == "push" and args.update_check_hours == 6 and args.lanes == "linux,windows,macos,web"
    assert "--mac-rent" not in argv  # renting a Mac stays a choice someone makes
