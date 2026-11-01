"""Shared spending ledger: caps, settlement, summaries and concurrency (no network)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import threading
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import pickfit.env
from pickfit.env import REPO_ROOT
from pickfit.ledger import (
    BASETEN_CAPS,
    PIPELINE_CAPS,
    BudgetExceeded,
    Caps,
    Ledger,
    default_ledger,
    pipeline_caps,
    pipeline_daily_cap,
    taipei_date,
)

OCT28_NOON_TAIPEI = datetime(2026, 10, 28, 4, 0, tzinfo=UTC)
OCT29_EARLY_TAIPEI = datetime(2026, 10, 28, 16, 30, tzinfo=UTC)  # 00:30 on 10/29 in Taipei


def fixed(moment: datetime):
    return lambda: moment


@pytest.fixture(autouse=True)
def no_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never read the real repo .env from tests."""
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "ledger.sqlite"


def test_daily_cap_schedule():
    assert pipeline_daily_cap(date(2026, 10, 28)) == 3.0
    assert pipeline_daily_cap(date(2026, 10, 29)) == 25.0
    assert pipeline_daily_cap(date(2026, 10, 30)) == 25.0
    assert pipeline_daily_cap(date(2026, 10, 31)) == 80.0
    assert pipeline_daily_cap(date(2026, 11, 1)) == 45.0
    assert pipeline_daily_cap(date(2026, 11, 2)) == 45.0
    assert pipeline_daily_cap(date(2026, 11, 3)) == 25.0
    assert PIPELINE_CAPS.total_usd == 120.0


def test_total_cap_setting_can_only_lower_it(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PICKFIT_PIPELINE_TOTAL_CAP_USD", raising=False)
    monkeypatch.setattr("pickfit.ledger.get_env", lambda name, default=None, path=None: None)
    assert pipeline_caps().total_usd == 120.0
    monkeypatch.setattr("pickfit.ledger.get_env", lambda name, default=None, path=None: "5")
    assert pipeline_caps().total_usd == 5.0
    assert pipeline_caps().daily_usd(date(2026, 11, 1)) == 45.0
    for bad in ("200", "-1", "five"):
        monkeypatch.setattr("pickfit.ledger.get_env", lambda name, default=None, path=None, v=bad: v)
        with pytest.raises(ValueError):
            pipeline_caps()


def test_baseten_daily_cap_is_raised_on_11_1_and_11_2_only():
    assert BASETEN_CAPS.total_usd == 100.0
    assert BASETEN_CAPS.daily_usd(date(2026, 10, 31)) == 25.0
    assert BASETEN_CAPS.daily_usd(date(2026, 11, 1)) == 70.0
    assert BASETEN_CAPS.daily_usd(date(2026, 11, 2)) == 35.0
    assert BASETEN_CAPS.daily_usd(date(2026, 11, 3)) == 25.0


def test_taipei_date_crosses_midnight_at_utc_16():
    assert taipei_date(fixed(datetime(2026, 10, 28, 15, 59, tzinfo=UTC))) == "2026-10-28"
    assert taipei_date(fixed(OCT29_EARLY_TAIPEI)) == "2026-10-29"


def test_ledger_uses_wal(db: Path):
    Ledger(db)
    assert sqlite3.connect(db).execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_reserve_then_settle_to_actual_cost(db: Path):
    ledger = Ledger(db, clock=fixed(OCT28_NOON_TAIPEI))
    row = ledger.reserve(0.50, run_id="r1", stage="extract", scope="extract:tinyq",
                         provider="meta", model="muse-spark-1.3")
    assert ledger.spend_summary()["today_usd"] == 0.5  # the open reservation counts
    ledger.settle(row, 0.0123, tokens={"input_tokens": 1000, "output_tokens": 200}, response_id="resp_1")

    summary = ledger.spend_summary()
    assert summary["today"] == "2026-10-28"
    assert summary["today_usd"] == pytest.approx(0.0123)
    assert summary["total_usd"] == pytest.approx(0.0123)
    assert summary["daily_cap_usd"] == 3.0
    assert summary["open_reservations_usd"] == 0
    assert summary["by_model"] == {"muse-spark-1.3": pytest.approx(0.0123)}
    assert summary["by_stage"] == {"extract": pytest.approx(0.0123)}
    assert summary["billed_tokens"]["input_tokens"] == 1000


def test_release_frees_the_reservation(db: Path):
    ledger = Ledger(db, clock=fixed(OCT28_NOON_TAIPEI))
    row = ledger.reserve(2.0, stage="verify")
    ledger.release(row)
    assert ledger.spend_summary()["today_usd"] == 0
    ledger.reserve(2.9, stage="verify")  # the whole $3 day is available again


def test_daily_cap_blocks_before_it_is_exceeded(db: Path):
    ledger = Ledger(db, clock=fixed(OCT28_NOON_TAIPEI))
    ledger.settle(ledger.reserve(2.9), 2.9)
    with pytest.raises(BudgetExceeded) as info:
        ledger.reserve(0.2)
    assert info.value.cap == "daily"
    assert ledger.spend_summary()["calls"] == 1  # nothing was recorded for the refused call


def test_daily_cap_is_per_taipei_day_and_rises_on_oct29(db: Path):
    today = Ledger(db, clock=fixed(OCT28_NOON_TAIPEI))
    today.settle(today.reserve(2.9), 2.9)
    next_day = Ledger(db, clock=fixed(OCT29_EARLY_TAIPEI))
    next_day.reserve(20.0)  # new Taipei day, $25 cap
    summary = next_day.spend_summary()
    assert summary["today"] == "2026-10-29"
    assert summary["daily_cap_usd"] == 25.0
    assert summary["today_usd"] == pytest.approx(20.0)
    assert summary["total_usd"] == pytest.approx(22.9)


def test_total_cap(db: Path):
    ledger = Ledger(db, caps=Caps(total_usd=1.0, daily_usd=lambda d: 100.0))
    ledger.settle(ledger.reserve(0.9), 0.9)
    with pytest.raises(BudgetExceeded) as info:
        ledger.reserve(0.2)
    assert info.value.cap == "total"


def test_scope_cap_only_counts_that_scope(db: Path):
    ledger = Ledger(db, clock=fixed(OCT28_NOON_TAIPEI))
    ledger.settle(ledger.reserve(0.3, scope="verify:tinyq", scope_cap_usd=0.5), 0.3)
    ledger.settle(ledger.reserve(0.3, scope="verify:other", scope_cap_usd=0.5), 0.3)
    with pytest.raises(BudgetExceeded) as info:
        ledger.reserve(0.3, scope="verify:tinyq", scope_cap_usd=0.5)
    assert info.value.cap == "scope verify:tinyq"
    ledger.reserve(0.1, scope="verify:tinyq", scope_cap_usd=0.5)  # still fits


def test_scope_cap_is_per_run(db: Path):
    ledger = Ledger(db, clock=fixed(OCT28_NOON_TAIPEI))
    ledger.settle(ledger.reserve(0.45, run_id="r1", scope="verify:tinyq", scope_cap_usd=0.5), 0.45)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(0.1, run_id="r1", scope="verify:tinyq", scope_cap_usd=0.5)
    ledger.reserve(0.5, run_id="r2", scope="verify:tinyq", scope_cap_usd=0.5)  # re-verification: full cap


def test_context_tokens_by_response_id(db: Path):
    ledger = Ledger(db)
    ledger.settle(ledger.reserve(0.1), 0.05, tokens={"input_tokens": 900, "output_tokens": 100},
                  response_id="resp_1")
    ledger.settle(ledger.reserve(0.1), 0.1, response_id="resp_2", status="no_usage")
    assert ledger.context_tokens("resp_1") == 1000
    assert ledger.context_tokens("resp_2") is None  # no token counts recorded
    assert ledger.context_tokens("resp_missing") is None


def test_scope_cap_needs_a_scope(db: Path):
    with pytest.raises(ValueError):
        Ledger(db).reserve(0.1, scope_cap_usd=0.5)


def test_cache_hit_is_free_and_counted(db: Path):
    ledger = Ledger(db, clock=fixed(OCT28_NOON_TAIPEI))
    ledger.record_cache_hit(stage="extract", model="muse-spark-1.3", tokens={"input_tokens": 999})
    summary = ledger.spend_summary()
    assert summary["total_usd"] == 0
    assert summary["cache_hits"] == 1
    assert summary["billed_tokens"]["input_tokens"] == 0  # cache hits are not billed tokens


def test_threads_cannot_overspend(db: Path):
    """20 threads, each with its own Ledger (own connections), race for a $1 total cap."""
    caps = Caps(total_usd=1.0, daily_usd=lambda d: 100.0)
    Ledger(db, caps=caps)
    wins: list[int] = []
    losses: list[int] = []
    start = threading.Barrier(20)

    def worker(i: int) -> None:
        ledger = Ledger(db, caps=caps)
        start.wait()
        try:
            ledger.reserve(0.1, stage="race", scope=f"t{i}")
            wins.append(i)
        except BudgetExceeded:
            losses.append(i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(wins) == 10 and len(losses) == 10
    assert Ledger(db, caps=caps).spend_summary()["total_usd"] == pytest.approx(1.0)


_CHILD = """
import sys
from pickfit.ledger import BudgetExceeded, Caps, Ledger
ledger = Ledger(sys.argv[1], caps=Caps(total_usd=1.0, daily_usd=lambda d: 100.0))
won = 0
for _ in range(10):
    try:
        ledger.reserve(0.05, stage="race")
        won += 1
    except BudgetExceeded:
        pass
print(won)
"""


def test_processes_cannot_overspend(db: Path):
    """4 processes x 10 reservations of $0.05 against a $1 cap: exactly 20 succeed."""
    Ledger(db)
    procs = [subprocess.Popen([sys.executable, "-c", _CHILD, str(db)], cwd=REPO_ROOT,
                              stdout=subprocess.PIPE, text=True) for _ in range(4)]
    won = sum(int(p.communicate(timeout=60)[0].strip()) for p in procs)
    assert won == 20


def test_default_ledger_honors_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "custom.sqlite"))
    assert default_ledger().path == tmp_path / "custom.sqlite"
