"""pickfit watch throughput (docs/proposals/throughput.md, 11/19): the rolling 24 h money cap, each lane's own slots,
people's submissions before harvest's, a finished job waking the loop, and the status that says why nothing starts.
Fakes only: a fake clock, a ledger in a temporary file, the D1 in SQLite, and a stand-in for the pipeline."""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from pickfit.ledger import Ledger
from pickfit.watch import (DEFAULT_DAILY_USD, WINDOWS_MAX_BOXES, WORST_CASE_META_USD, Job, Settings, Watcher,
                           env_defaults, harvest_submission_id, lane_reserves, p95, queued, submission_source)
from queue_fakes import checkout, d1, repo_item, submission, submit
from test_profiles import extraction
from test_watch import NOW, Pipeline
from test_watch_lanes import MAC_ONLY, WINDOWS_AND_MAC, Clock, FakeLane, mac_run

HARVEST = [f"sub_harvest{i:032x}" for i in range(6)]


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Any]:
    data_dir, worker_dir = checkout(tmp_path)
    return {"tmp": tmp_path, "data": data_dir, "worker": worker_dir, "d1": d1(tmp_path)}


def make(env: dict[str, Any], *, pipeline: Pipeline | None = None, lanes: dict[str, Any] | None = None,
         ledger: Ledger | None = None, clock: Any = None, lines: list[str] | None = None, site: bool = False,
         **settings: Any) -> Watcher:
    steps = (pipeline or Pipeline(env["tmp"])).steps()
    steps.lanes = lanes or {}
    if site:
        steps.site = object()  # the web lane is on; the stand-in process never reads a site
    settings.setdefault("lanes", ("linux", *(["web"] if site else []), *(lanes or {})))
    s = Settings(data_dir=env["data"], runs_dir=env["tmp"] / "runs", db_path=env["tmp"] / "runs" / "pipeline.db",
                 worker_dir=env["worker"], wake_settle_s=0, **settings)
    out = lines if lines is not None else []
    return Watcher(env["d1"], steps, s, meta_ledger=ledger, clock=clock or (lambda: NOW), log=out.append)


class Gate:
    """Stands in for Watcher.process: each claimed row waits until released, so a test sees what one tick starts."""

    def __init__(self) -> None:
        self.started: list[str] = []
        self.release = threading.Event()

    def __call__(self, sub: dict[str, Any]) -> str:
        self.started.append(sub["id"])
        assert self.release.wait(10), "the test never released its jobs"
        return sub["id"]


def ledger_with(env: dict[str, Any], usd: float, clock: Any) -> Ledger:
    ledger = Ledger(env["tmp"] / "ledger.sqlite", clock=clock)
    ledger.settle(ledger.reserve(usd, scope="earlier work"), usd)
    return ledger


def status(w: Watcher) -> dict[str, Any]:
    return json.loads(w.status_path.read_text(encoding="utf-8"))


# --- W1: money over a rolling 24 hours ------------------------------------------------------------------------


def test_the_money_cap_rolls_over_24_hours_and_says_which_numbers_hold_it(env: dict[str, Any]) -> None:
    clock = Clock()
    ledger = ledger_with(env, 75.0, clock)  # spent at NOW
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    lines: list[str] = []
    w = make(env, ledger=ledger, clock=clock, daily_usd=80, lines=lines)
    held = "rolling 24 h cap: $75.00 spent + $0.00 held for 0 running + $6.00 for the next > $80.00 (--daily-usd 80)"
    assert w.blocked() == held
    with ThreadPoolExecutor(2) as pool:
        assert w.tick(pool) == []
    assert any(line == f"[watch] not starting sub_1: {held}" for line in lines)
    linux = status(w)["lanes"]["linux"]
    assert (linux["running"], linux["queued"], linux["not_starting"]) == (0, 1, held)
    assert status(w)["money"]["spent_24h_usd"] == 75.0 and status(w)["money"]["cap_24h_usd"] == 80
    assert "[watch] linux 0/6, 1 queued (rolling 24 h cap)" in lines
    clock.now = NOW + timedelta(hours=23, minutes=59)
    assert w.blocked() == held
    clock.now = NOW + timedelta(hours=24, minutes=1)  # what was spent a day ago no longer counts: no restart needed
    assert w.blocked() is None


def test_without_a_ledger_what_this_run_spent_rolls_off_too(env: dict[str, Any]) -> None:
    clock = Clock()
    w = make(env, clock=clock, daily_usd=10)
    w._spent(7.5)
    assert w.blocked().startswith("rolling 24 h cap: $7.50 spent")
    clock.now = NOW + timedelta(hours=25)
    assert w.blocked() is None and w.spent_usd == 7.5  # the run's own total stays, for --max-usd


def test_the_daily_cap_is_the_accounts_from_loop_budget_json(env: dict[str, Any]) -> None:
    budget = env["tmp"] / "loop" / "budget.json"
    budget.parent.mkdir()
    budget.write_text(json.dumps({"since": "2026-11-15T23:55:00+08:00", "model_usd": {"total": 100, "daily": 55},
                                  "box_usd": {"total": 25, "daily": 10}}))
    assert make(env, budget_path=budget).daily_cap() == (55.0, "loop/budget.json model_usd.daily")
    assert make(env, budget_path=budget, daily_usd=12).daily_cap() == (12, "--daily-usd 12")
    missing = make(env, budget_path=env["tmp"] / "nowhere" / "budget.json").daily_cap()
    assert missing == (DEFAULT_DAILY_USD, "the default (no model_usd.daily in budget.json)")
    assert make(env).daily_cap()[1] == "none"  # a library caller that sets nothing (ingest_candidates) keeps its own


def test_a_job_holds_its_lanes_p95_not_the_worst_case(env: dict[str, Any]) -> None:
    jobs = env["tmp"] / "runs" / "watch" / "jobs"
    jobs.mkdir(parents=True)

    def job(sid: str, lane: str | None, result: str | None, usd: float, minute: int) -> None:
        j = Job(submission_id=sid, url=f"https://github.com/someone/{sid}", submitted_at="2026-10-30T10:00:00Z",
                started_at=f"2026-10-30T10:{minute:02d}:00+08:00", lane=lane, result=result,
                cost_usd={"model": usd, "box": 1.0})
        (jobs / f"{sid}.json").write_text(json.dumps(j.__dict__))

    for i in range(1, 21):
        job(f"sub_l{i}", "linux", "ready", round(0.1 * i, 2), i)
    job("sub_r", None, "rejected", 0.0, 30)  # turned down before a lane: read in a linux slot, it counts there
    job("sub_p", "linux", "parked", 50.0, 31)  # not finished: does not count
    for i in range(3):
        job(f"sub_w{i}", "web", "ready", 0.3, 40 + i)
    w = make(env)
    reserves = w.refresh_reserves(force=True)
    assert reserves["linux"] == (1.9, "p95 of the last 21 jobs")
    assert reserves["web"] == (WORST_CASE_META_USD, "worst case (3 of 5 jobs to go by)")
    assert p95([0.2, 0.1, 5.0]) == 5.0 and p95([1.0]) == 1.0
    assert lane_reserves([])["windows"][0] == WORST_CASE_META_USD
    w.s.daily_usd = 2.0
    assert w.blocked() is None  # six worst cases would not fit in $2; one p95 does
    w.s.daily_usd = 1.5
    assert w.blocked() == ("rolling 24 h cap: $0.00 spent + $0.00 held for 0 running + $1.90 for the next "
                           "> $1.50 (--daily-usd 1.5)")


def test_max_usd_still_caps_one_run_when_asked(env: dict[str, Any]) -> None:
    w = make(env, max_usd=4.0)
    w._spent(3.0)
    assert w.blocked() == "this run's cap: $3.00 spent + $0.00 held for 0 running + $6.00 for the next > --max-usd 4.00"


# --- W2: each lane's own slots, people before harvest ----------------------------------------------------------


def test_each_lane_starts_its_own_number_at_once(env: dict[str, Any]) -> None:
    for i in range(5):
        submit(env["d1"], f"sub_r{i}", f"https://github.com/someone/tool{i}", at=f"2026-10-30T10:00:0{i}.000Z")
    for i in range(3):
        submit(env["d1"], f"sub_w{i}", f"https://site{i}.example.com/", at=f"2026-10-30T10:01:0{i}.000Z")
    w = make(env, concurrency=2, web_concurrency=1, site=True)
    gate = Gate()
    w.process = gate  # type: ignore[method-assign]
    with ThreadPoolExecutor(8) as pool:
        assert w.tick(pool) == ["sub_r0", "sub_r1", "sub_w0"]
        assert w.tick(pool) == []  # every slot is taken
        lanes = status(w)["lanes"]
        assert (lanes["linux"]["running"], lanes["linux"]["limit"], lanes["linux"]["queued"]) == (2, 2, 3)
        assert (lanes["web"]["running"], lanes["web"]["limit"], lanes["web"]["queued"]) == (1, 1, 2)
        assert lanes["linux"]["not_starting"] == "slots: 2 of 2 running"
        assert status(w)["money"]["held_usd"] == 3 * WORST_CASE_META_USD
        gate.release.set()
    assert w.busy() == 0 and status(w)["money"]["held_usd"] == 3 * WORST_CASE_META_USD  # as of that tick
    with ThreadPoolExecutor(8) as pool:
        w.tick(pool)  # the slots the first jobs freed take the next rows
    assert gate.started[3:] == ["sub_r2", "sub_r3", "sub_w1"]


def test_people_go_first_and_harvest_keeps_to_its_slots(env: dict[str, Any]) -> None:
    for i, sid in enumerate(HARVEST[:4]):  # queued before the people's rows
        submit(env["d1"], sid, f"https://github.com/harvest/tool{i}", at=f"2026-10-30T09:00:0{i}.000Z")
    submit(env["d1"], "sub_u0", "https://github.com/people/one", at="2026-10-30T10:00:00.000Z")
    submit(env["d1"], "sub_u1", "https://github.com/people/two", at="2026-10-30T10:00:01.000Z")
    assert [r["id"] for r in queued(env["d1"], 3, lane="linux")] == ["sub_u0", "sub_u1", HARVEST[0]]
    lines: list[str] = []
    w = make(env, concurrency=6, harvest_slots=2, lines=lines)
    gate = Gate()
    w.process = gate  # type: ignore[method-assign]
    with ThreadPoolExecutor(8) as pool:
        assert w.tick(pool) == ["sub_u0", "sub_u1", HARVEST[0], HARVEST[1]]
        linux = status(w)["lanes"]["linux"]
        assert (linux["harvest_running"], linux["queued"], linux["queued_harvest"]) == (2, 2, 2)
        assert linux["not_starting"] == "harvest quota: 2 of 2 harvest slots in use"
        assert status(w)["harvest"]["running"] == 2
        gate.release.set()


def test_harvest_leaves_one_slot_of_each_lane_to_people(env: dict[str, Any]) -> None:
    for i, sid in enumerate(HARVEST[:4]):
        submit(env["d1"], sid, f"https://github.com/harvest/tool{i}", at=f"2026-10-30T09:00:0{i}.000Z")
    w = make(env, concurrency=3, harvest_slots=10)
    gate = Gate()
    w.process = gate  # type: ignore[method-assign]
    with ThreadPoolExecutor(8) as pool:
        assert w.tick(pool) == HARVEST[:2]
        assert status(w)["lanes"]["linux"]["not_starting"] == \
            "harvest quota: linux keeps 1 of its 3 slots for people's submissions"
        submit(env["d1"], "sub_u0", "https://github.com/people/one", at="2026-10-30T11:00:00.000Z")
        assert w.tick(pool) == ["sub_u0"]  # a person's row still gets in
        gate.release.set()


def test_harvest_starts_only_while_money_stays_free_for_people(env: dict[str, Any]) -> None:
    clock = Clock()
    ledger = ledger_with(env, 8.0, clock)
    submit(env["d1"], HARVEST[0], "https://github.com/harvest/tool0", at="2026-10-30T09:00:00.000Z")
    submit(env["d1"], "sub_u0", "https://github.com/people/one", at="2026-10-30T10:00:00.000Z")
    w = make(env, ledger=ledger, clock=clock, daily_usd=24, user_reserve_usd=10)
    gate = Gate()
    w.process = gate  # type: ignore[method-assign]
    with ThreadPoolExecutor(4) as pool:
        assert w.tick(pool) == ["sub_u0"]  # 8 + 6 = 14 of 24
        assert status(w)["lanes"]["linux"]["not_starting"] == (
            "rolling 24 h cap: $8.00 spent + $6.00 held for 1 running + $6.00 for the next + $10.00 kept for "
            "people's submissions > $24.00 (--daily-usd 24)")
        gate.release.set()


def test_the_harvest_hook_makes_ids_the_status_page_takes_and_no_person_can_get(env: dict[str, Any]) -> None:
    sid = harvest_submission_id()
    assert re.fullmatch(r"sub_[a-z0-9]{1,64}", sid)  # worker/src/web.ts's /submit/<id> page
    assert submission_source({"id": sid}) == "harvest"
    assert submission_source({"id": "sub_" + "0123456789abcdef" * 2}) == "user"  # the Worker's newId("sub")


def test_windows_never_runs_more_than_two_boxes(env: dict[str, Any]) -> None:
    class SlowLane(FakeLane):
        def __init__(self, *args: Any) -> None:
            super().__init__(*args)
            self.running = self.most = 0
            self.lock = threading.Lock()

        def verify(self, task: Any, data_dir: Path, log: Any) -> Any:
            with self.lock:
                self.running += 1
                self.most = max(self.most, self.running)
            time.sleep(0.2)
            try:
                return super().verify(task, data_dir, log)
            finally:
                with self.lock:
                    self.running -= 1

    repos = {f"someone/win{i}": repo_item(30 + i, f"someone/win{i}") for i in range(3)}
    for i in range(3):
        submit(env["d1"], f"sub_{i}", f"https://github.com/someone/win{i}", at=f"2026-10-30T10:00:0{i}.000Z")
    win = SlowLane("windows", "windows", env["tmp"], *(mac_run(f"run-win-{i}") for i in range(3)))
    w = make(env, pipeline=Pipeline(env["tmp"], repos=repos, result=extraction(**WINDOWS_AND_MAC)),
             lanes={"windows": win}, windows_concurrency=5)
    assert w.slot_limit("windows") == WINDOWS_MAX_BOXES == 2
    jobs = w.run(once=True)
    assert sorted(j.result for j in jobs if j.result != "parked") == ["ready"] * 3
    assert win.most == 2


# --- W3: a finished job wakes the loop ------------------------------------------------------------------------


def test_a_job_that_ends_takes_the_next_row_without_waiting_for_the_poll(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/one")
    submit(env["d1"], "sub_2", "https://github.com/someone/two", at="2026-10-30T10:00:01.000Z")
    w = make(env, concurrency=1, interval_s=3600)
    finished: list[str] = []

    def process(sub: dict[str, Any]) -> str:
        finished.append(sub["id"])
        return sub["id"]

    w.process = process  # type: ignore[method-assign]
    waits: list[tuple[int, bool]] = []

    def wait_for(seconds: float) -> bool:
        woke = w._wake.wait(min(seconds, 5))  # never the hour itself in a test
        waits.append((round(seconds), woke))
        if len(finished) == 2:
            w.restart_wanted = True  # nothing runs: run() returns
        return woke

    began = time.monotonic()
    w.run(wait_for=wait_for)
    assert finished == ["sub_1", "sub_2"] and waits[0] == (3600, True)
    assert time.monotonic() - began < 5


# --- W4: why nothing starts, lane by lane ---------------------------------------------------------------------


def test_the_status_says_why_a_parked_lane_waits(env: dict[str, Any]) -> None:
    from pickfit.lanes import Policy

    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    mac = FakeLane("macos", "macos", env["tmp"], mac_run("run-mac-1"),
                   policy=Policy(min_batch=3, max_wait=timedelta(hours=24)))
    lines: list[str] = []
    w = make(env, pipeline=Pipeline(env["tmp"], result=extraction(**MAC_ONLY)), lanes={"macos": mac}, lines=lines)
    w.run(once=True)
    macos = status(w)["lanes"]["macos"]
    assert (macos["parked"], macos["running"], macos["limit"]) == (1, 0, 1)
    assert macos["not_starting"] == "waiting for its batch: it starts when 3 wait or the oldest has waited 24 h"
    assert "[watch] linux 0/6 · macos 0/1, 1 parked (waiting for its batch)" in lines


def test_the_status_says_when_a_lane_rests(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_1", "https://github.com/someone/tinyq")
    mac = FakeLane("macos", "macos", env["tmp"], mac_run("run-mac-1"), available="no Mac host is ready")
    w = make(env, pipeline=Pipeline(env["tmp"], result=extraction(**MAC_ONLY)), lanes={"macos": mac})
    w.run(once=True)
    w.run(once=True)
    assert status(w)["lanes"]["macos"]["not_starting"] == "lane hold: rests until 18:36 (not ready: no Mac host is ready)"


# --- W6: settings from the service's environment --------------------------------------------------------------


def test_the_throughput_settings_come_from_the_environment() -> None:
    defaults = env_defaults({})
    assert defaults == {"concurrency": 6, "web_concurrency": 2, "windows_concurrency": 2, "harvest_slots": 4,
                        "user_reserve_usd": 10.0, "daily_usd": None, "hourly_cap": 0}
    got = env_defaults({"PICKFIT_WATCH_LINUX_CONCURRENCY": "8", "PICKFIT_WATCH_DAILY_USD": "60",
                        "PICKFIT_WATCH_HARVEST_SLOTS": " ", "PICKFIT_WATCH_WEB_CONCURRENCY": ""})
    assert (got["concurrency"], got["daily_usd"], got["harvest_slots"], got["web_concurrency"]) == (8, 60.0, 4, 2)
    with pytest.raises(ValueError, match="PICKFIT_WATCH_LINUX_CONCURRENCY must be an integer"):
        env_defaults({"PICKFIT_WATCH_LINUX_CONCURRENCY": "eight"})
    with pytest.raises(ValueError, match="PICKFIT_WATCH_DAILY_USD must be 0 or more"):
        env_defaults({"PICKFIT_WATCH_DAILY_USD": "-1"})


def test_the_watch_command_leaves_unset_flags_to_the_environment() -> None:
    from test_watch_lanes import parse

    args = parse(["watch"])
    assert (args.concurrency, args.web_concurrency, args.daily_usd, args.max_usd, args.hourly_cap) == (
        None, None, None, None, None)
    args = parse(["watch", "--concurrency", "8", "--windows-concurrency", "2", "--daily-usd", "40"])
    assert (args.concurrency, args.windows_concurrency, args.daily_usd) == (8, 2, 40.0)


def test_a_row_stays_in_its_lane_query(env: dict[str, Any]) -> None:
    submit(env["d1"], "sub_r", "https://github.com/someone/tinyq")
    submit(env["d1"], "sub_w", "https://wordpad.example.com/")
    assert [r["id"] for r in queued(env["d1"], 5, lane="linux")] == ["sub_r"]
    assert [r["id"] for r in queued(env["d1"], 5, lane="web")] == ["sub_w"]
    assert submission(env["d1"], "sub_w")["status"] == "queued"
