"""The D1 client: literals, wrangler's command line and replies, and the SQLite stand-in."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from pickfit.d1 import D1, D1Error, SqliteD1, literal, sql, timestamp
from pickfit.ledger import TAIPEI
from queue_fakes import ROOT


def test_literals_quote_and_refuse() -> None:
    assert literal(None) == "NULL" and literal(True) == "1" and literal(3) == "3" and literal(0.25) == "0.25"
    assert literal("it's") == "'it''s'"
    assert literal("'); DROP TABLE submissions; --") == "'''); DROP TABLE submissions; --'"
    with pytest.raises(ValueError):
        literal("a\x00b")
    with pytest.raises(ValueError):
        literal(float("nan"))
    with pytest.raises(TypeError):
        literal(b"bytes")


def test_placeholders_are_filled_once() -> None:
    assert sql("SELECT ?1, ?2, ?1", "?2", 5) == "SELECT '?2', 5, '?2'"
    with pytest.raises(ValueError, match=r"\?3 has no parameter"):
        sql("SELECT ?3", 1)


def test_timestamps_match_the_worker() -> None:
    assert timestamp(datetime(2026, 10, 30, 18, 6, 40, tzinfo=TAIPEI)) == "2026-10-30T10:06:40.000Z"


class Wrangler:
    def __init__(self, *, code: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.reply = (code, stdout, stderr)
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        code, out, err = self.reply
        return subprocess.CompletedProcess(command, code, out, err)


def reply(results: list[dict[str, Any]], changes: int = 0, success: bool = True) -> str:
    return json.dumps([{"results": results, "success": success, "meta": {"changes": changes}}])


def test_d1_runs_wrangler_with_its_own_login(tmp_path: Path) -> None:
    wrangler = Wrangler(stdout="▲ [WARNING] something\n" + reply([{"id": "sub_1"}]))
    db = D1(worker_dir=tmp_path, run=wrangler)
    assert db.query("SELECT id FROM submissions") == [{"id": "sub_1"}]
    command, kwargs = wrangler.calls[0]
    assert command == ["npx", "--no-install", "wrangler", "d1", "execute", "pickfit", "--remote", "--json",
                       "--command", "SELECT id FROM submissions"]
    assert kwargs["cwd"] == tmp_path and kwargs["capture_output"] and "env" not in kwargs
    local = D1(remote=False, worker_dir=tmp_path, env="eval", run=Wrangler(stdout=reply([], changes=1)))
    assert local.execute("UPDATE x SET y = 1") == 1 and local.where == "local D1 pickfit (env eval)"
    # Local wrangler leaves changes out of meta, so counts that matter come from RETURNING rows.
    silent = Wrangler(stdout=json.dumps([{"results": [], "success": True, "meta": {"duration": 0}}]))
    assert D1(worker_dir=tmp_path, run=silent).execute("x") is None
    assert local._run.calls[0][0][6:7] == ["--local"] and local._run.calls[0][0][-2:] == ["--env", "eval"]


@pytest.mark.parametrize("wrangler, message", [
    (Wrangler(code=1, stderr="✘ [ERROR] Not logged in." + "x" * 5000), "wrangler exit 1: …x"),
    (Wrangler(stdout="not json"), "reply is not JSON"),
    (Wrangler(stdout=reply([], success=False)), "statement failed"),
])
def test_d1_errors_are_short(tmp_path: Path, wrangler: Wrangler, message: str) -> None:
    with pytest.raises(D1Error, match=message) as err:
        D1(worker_dir=tmp_path, run=wrangler).query("SELECT 1")
    assert len(str(err.value)) < 700


def test_d1_when_wrangler_is_missing(tmp_path: Path) -> None:
    def missing(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("npx")

    with pytest.raises(D1Error, match="wrangler did not run"):
        D1(worker_dir=tmp_path, run=missing).query("SELECT 1")


def test_sqlite_stand_in_has_the_workers_schema(tmp_path: Path) -> None:
    db = SqliteD1(tmp_path / "d1.sqlite", ROOT / "worker" / "migrations")
    db.execute(sql("INSERT INTO submissions (id, url, status, submitted_at, updated_at) VALUES "
                   "('sub_1', 'https://github.com/o/r', 'queued', ?1, ?1)", "2026-10-30T10:00:00.000Z"))
    assert db.execute("UPDATE submissions SET status = 'reading' WHERE status = 'queued'") == 1
    assert db.query("UPDATE submissions SET status = 'queued' WHERE status = 'reading' RETURNING id") == [
        {"id": "sub_1"}]
    assert db.query("UPDATE submissions SET status = 'reading' WHERE status = 'queued' RETURNING id") == [
        {"id": "sub_1"}]  # the RETURNING write above was committed
    assert db.query("SELECT status FROM submissions") == [{"status": "reading"}]
    with pytest.raises(D1Error, match="CHECK constraint"):
        db.execute("UPDATE submissions SET status = 'ready'")
    # Opening it again keeps the rows (migrations run once, on a new file).
    assert SqliteD1(tmp_path / "d1.sqlite").query("SELECT count(*) AS n FROM submissions") == [{"n": 1}]
