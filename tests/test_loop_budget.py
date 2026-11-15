"""scripts/loop_budget.py: what counts against the loop's caps, and when one is reached."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("loop_budget", ROOT / "scripts" / "loop_budget.py")
loop_budget = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(loop_budget)

SINCE = "2026-11-15T23:55:00+08:00"
NOW = datetime.fromisoformat("2026-11-16T10:00:00+08:00")


def budget(tmp_path: Path, **over) -> Path:
    loop = tmp_path / "loop"
    loop.mkdir(exist_ok=True)
    body = {"since": SINCE, "model_usd": {"total": 100, "daily": 40}, "box_usd": {"total": 25, "daily": 10},
            "item_usd": 5, **over}
    (loop / "budget.json").write_text(json.dumps(body))
    return loop


def ledger(tmp_path: Path, rows: list[tuple[str, str, float, float]]) -> Path:
    """rows: (ts, status, reserved_usd, cost_usd), in the shared ledger's own columns."""
    path = tmp_path / "ledger.sqlite"
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE calls (ts TEXT, day TEXT, budget TEXT, status TEXT, reserved_usd REAL, cost_usd REAL)")
        conn.executemany("INSERT INTO calls VALUES (?, ?, 'pipeline', ?, ?, ?)",
                         [(ts, ts[:10], status, reserved, cost) for ts, status, reserved, cost in rows])
    return path


def run_dir(tmp_path: Path, name: str, box_usd: float | None, written: str) -> None:
    folder = tmp_path / "runs" / "verify" / name
    folder.mkdir(parents=True)
    outcome = folder / "outcome.json"
    outcome.write_text(json.dumps({"cost_usd": 0.2, **({"box_usd": box_usd} if box_usd is not None else {})}))
    stamp = datetime.fromisoformat(written).timestamp()
    os.utime(outcome, (stamp, stamp))


def report(tmp_path, loop, rows=(), now=NOW):
    return loop_budget.report(loop, ledger=ledger(tmp_path, list(rows)), runs_dir=tmp_path / "runs", now=now)


def test_only_what_was_spent_since_the_caps_were_set_counts(tmp_path):
    loop = budget(tmp_path)
    run_dir(tmp_path, "verify-old-20261105", 3.0, "2026-11-05T03:00:00+08:00")
    run_dir(tmp_path, "verify-a-20261116", 0.04, "2026-11-16T00:30:00+08:00")
    run_dir(tmp_path, "verify-b-20261116", 0.06, "2026-11-16T09:00:00+08:00")
    run_dir(tmp_path, "verify-c-20261116", None, "2026-11-16T09:30:00+08:00")  # a run with no box estimate
    rep = report(tmp_path, loop, [
        ("2026-11-05T03:37:07.339990+08:00", "done", 0, 168.08),   # the hackathon's spending
        ("2026-11-15T23:40:50.048342+08:00", "done", 0, 0.30),     # before `since`
        ("2026-11-15T23:58:20.739686+08:00", "done", 0, 0.25),     # after it, yesterday
        ("2026-11-16T09:00:00.000000+08:00", "done", 0, 1.50),
        ("2026-11-16T09:59:00.000000+08:00", "reserved", 0.75, 0),  # an open call counts at its reservation
    ])
    assert rep["model"] == {"spent": 2.5, "cap": 100.0, "today": 2.25, "daily_cap": 40.0}
    assert rep["box"] == {"spent": 0.1, "cap": 25.0, "today": 0.1, "daily_cap": 10.0}
    assert rep["reached"] == []
    assert loop_budget.line(rep) == ("LOOP_BUDGET model=$2.50/100 (today $2.25/40) box=$0.10/25 (today $0.10/10)")


def test_a_total_or_a_daily_cap_is_reached(tmp_path):
    loop = budget(tmp_path, model_usd={"total": 100, "daily": 2}, box_usd={"total": 0.1, "daily": 10})
    run_dir(tmp_path, "verify-a", 0.1, "2026-11-16T00:30:00+08:00")
    rep = report(tmp_path, loop, [("2026-11-16T09:00:00.000000+08:00", "done", 0, 2.0)])
    assert rep["reached"] == ["model today ($2.00 of $2)", "box total ($0.10 of $0.1)"]
    assert "reached: model today" in loop_budget.line(rep)
    # The next day the daily cap has room again; the total does not.
    later = report(tmp_path, loop, [("2026-11-16T09:00:00.000000+08:00", "done", 0, 2.0)],
                   now=datetime.fromisoformat("2026-11-17T08:00:00+08:00"))
    assert later["reached"] == ["box total ($0.10 of $0.1)"]


def test_no_ledger_and_no_runs_is_nothing_spent(tmp_path):
    loop = budget(tmp_path)
    rep = loop_budget.report(loop, ledger=tmp_path / "none.sqlite", runs_dir=tmp_path / "runs", now=NOW)
    assert rep["model"]["spent"] == 0 and rep["box"]["spent"] == 0 and rep["reached"] == []


@pytest.mark.parametrize("body", [
    "not json",
    json.dumps({"since": SINCE, "model_usd": {"total": 100}}),
    json.dumps({"since": "2026-11-15T23:55:00", "model_usd": {"total": 1, "daily": 1},
                "box_usd": {"total": 1, "daily": 1}}),
    json.dumps({"since": SINCE, "model_usd": {"total": -1, "daily": 1}, "box_usd": {"total": 1, "daily": 1}}),
])
def test_a_budget_that_does_not_say_its_caps_is_an_error(tmp_path, body, capsys):
    loop = tmp_path / "loop"
    loop.mkdir()
    (loop / "budget.json").write_text(body)
    with pytest.raises(loop_budget.BudgetError):
        loop_budget.load(loop)
    assert loop_budget.main(["--loop-dir", str(loop), "status"]) == 2


def test_status_exit_code(tmp_path, capsys):
    loop = budget(tmp_path, box_usd={"total": 0.05, "daily": 10})
    run_dir(tmp_path, "verify-a", 0.06, "2026-11-16T00:30:00+08:00")
    argv = ["--loop-dir", str(loop), "--ledger", str(tmp_path / "none.sqlite"), "--runs-dir", str(tmp_path / "runs")]
    assert loop_budget.main([*argv, "status"]) == 0
    assert loop_budget.main([*argv, "status", "--exit-code"]) == 4
    assert "reached: box total" in capsys.readouterr().out


def test_the_committed_budget_and_the_loop_settings_agree():
    """The ledger's own daily stop (PICKFIT_PIPELINE_DAILY_CAP_USD, set for loop sessions) is the model
    account's daily cap: one number, kept in two files because Claude Code reads the env from settings."""
    caps = loop_budget.load(ROOT / "loop")["caps"]
    settings = json.loads((ROOT / "loop" / "settings.json").read_text())
    assert float(settings["env"]["PICKFIT_PIPELINE_DAILY_CAP_USD"]) == caps["model"]["daily"]
