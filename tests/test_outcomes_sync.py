"""`pickfit outcomes sync`: outside reports from D1 into records, counts only."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pickfit.cli import main
from pickfit.d1 import SqliteD1, sql
from pickfit.outcomes import load_exclude, sync
from pickfit.schema import SoftwareRecord

ROOT = Path(__file__).resolve().parents[1]
ISSUED = datetime.fromisoformat("2026-10-30T12:00:00+00:00")
NOW = datetime.fromisoformat("2026-11-01T20:00:00+08:00")
rec = lambda c: "rec_" + c * 32  # noqa: E731


def _db(tmp_path: Path, rows: list[tuple[Any, ...]]) -> SqliteD1:
    """(rec_id, slug, day, stage, success, reporter[, replaced_by, last_used]) as the Worker writes them."""
    db = SqliteD1(tmp_path / "d1.sqlite", ROOT / "worker" / "migrations")
    for i, (rec_id, slug, day, stage, success, reporter, *rest) in enumerate(rows):
        ts = (ISSUED + timedelta(days=day, seconds=i)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        db.execute(sql("INSERT INTO events (id, ts, type, rec_id, slug, stage, success, reporter, replaced_by, last_used, "
                       "note, client) VALUES (?1, ?2, 'outcome', ?3, ?4, ?5, ?6, ?7, ?8, ?9, 'a private note', 't')",
                       f"evt_{i}", ts, rec_id, slug, stage, success, reporter, *(rest + [None, None])[:2]))
    return db


def _data(tmp_path: Path) -> Path:
    data = tmp_path / "software"
    data.mkdir()
    shutil.copy(ROOT / "data" / "software" / "rei.json", data / "rei.json")
    return data


def _record(data: Path) -> dict[str, Any]:
    return json.loads((data / "rei.json").read_text(encoding="utf-8"))


ROWS = [
    (rec("1"), "rei", 1, "installed", 1, "external"),
    (rec("1"), "rei", 30, "still_using", 1, "external", None, "this_week"),
    (rec("1"), "rei", 60, "still_using", 0, "external", None, "older"),
    (rec("1"), "rei", 90, "still_using", 1, "external", None, "this_month"),  # used again: the latest wins
    (rec("2"), "rei", 40, "still_using", 0, "external", "other-cli"),
    (rec("3"), "rei", 2, "installed", 1, "dev"),  # our own runs
    (rec("4"), "rei", 2, "installed", 1, "eval"),
    (rec("5"), "rei", 3, "installed", 1, "external"),  # a check that forgot the header: --exclude
    (None, "rei", 4, "installed", 1, "external"),  # not counted by the Worker
    (rec("6"), "not-a-record", 5, "installed", 1, "external"),
]


def test_dry_run_prints_per_slug_and_writes_nothing(tmp_path: Path) -> None:
    data, lines = _data(tmp_path), []
    before = (data / "rei.json").read_text(encoding="utf-8")
    assert sync(data, _db(tmp_path, ROWS), now=NOW, dry_run=True, exclude={rec("5")}, log=lines.append) == 0
    assert (data / "rei.json").read_text(encoding="utf-8") == before
    assert lines[0] == ("D1: 9 counted outcome rows; left out as our own (reporter): dev 1, eval 1; "
                        "left out by --exclude: 1; outside reports for 2 slugs")
    assert lines[1] == "  not-a-record: reported, but not in " + str(data) + "; skipped"
    assert lines[2].startswith('  rei: installed 0->1; still_using 0->1; replaced 0->1; replaced_by {}->{"other-cli": 1} '
                               '· 3 outside reports · last_used {"this_month": 1, "unknown": 1} · quality 73.7 -> ')
    assert lines[-1] == "1 record would change (--dry-run: nothing written)"


def test_only_counts_reach_the_record(tmp_path: Path) -> None:
    data, db = _data(tmp_path), _db(tmp_path, ROWS)
    sync(data, db, now=NOW, exclude={rec("5")}, log=lambda _: None)
    record = _record(data)
    outcomes = record["outcomes"]
    assert outcomes["external"] == {"installed": 1, "install_failed": 0, "first_run_ok": 0, "first_run_failed": 0,
                                    "still_using": 1, "replaced": 1, "abandoned": 0}
    assert outcomes["eval"]["installed"] == outcomes["dev"]["installed"] == 0
    assert outcomes["last_report_at"] is None and outcomes["synced_at"] is None
    text = (data / "rei.json").read_text(encoding="utf-8")
    for leak in ("rec_", "2026-11-29T", "2027-01-28T", "a private note", '"client"', "this_month"):
        assert leak not in text
    # Three outside reports: usage_outcomes now has a score, and the record still validates.
    usage = record["scores"]["quality"]["components"]["usage_outcomes"]
    assert usage["score"] == pytest.approx((0.4 * 1 + 0.3 * 0.5) / 0.7, abs=1e-4)
    SoftwareRecord.model_validate(record)
    # A second run finds nothing to change.
    lines: list[str] = []
    sync(data, db, now=NOW, exclude={rec("5")}, log=lines.append)
    assert lines[-1] == "0 records changed"


def test_under_three_outside_reports_the_score_does_not_move(tmp_path: Path) -> None:
    data, lines = _data(tmp_path), []
    scores = _record(data)["scores"]
    sync(data, _db(tmp_path, ROWS[:2] + ROWS[5:7]), now=NOW, log=lines.append)
    assert lines[1].endswith('· 2 outside reports · last_used {"this_week": 1} · score unchanged')
    record = _record(data)
    assert record["outcomes"]["external"]["installed"] == 1 and record["outcomes"]["external"]["still_using"] == 1
    assert record["scores"] == scores


def test_a_free_text_replacement_is_kept_only_as_a_plain_name(tmp_path: Path) -> None:
    data = _data(tmp_path)
    rows = [(rec("1"), "rei", 40, "still_using", 0, "external", "Ollama"),
            (rec("2"), "rei", 41, "still_using", 0, "external", "my own script; see https://x.invalid/?a=b")]
    sync(data, _db(tmp_path, rows), now=NOW, log=lambda _: None)
    assert _record(data)["outcomes"]["replaced_by"] == {"Ollama": 1, "other": 1}


def test_reports_gone_from_d1_reset_the_record(tmp_path: Path) -> None:
    data = _data(tmp_path)
    sync(data, _db(tmp_path, ROWS[:2]), now=NOW, log=lambda _: None)
    (tmp_path / "d1.sqlite").unlink()
    lines: list[str] = []
    sync(data, _db(tmp_path, []), now=NOW, log=lines.append)
    assert lines[1] == "  rei: installed 1->0; still_using 1->0 · 0 outside reports · score unchanged"
    assert _record(data)["outcomes"]["external"]["installed"] == 0


def test_exclude_file_takes_rec_ids_only(tmp_path: Path) -> None:
    path = tmp_path / "exclude.txt"
    path.write_text(f"# our checks\n{rec('5')}\n\n", encoding="utf-8")
    assert load_exclude(path) == {rec("5")}
    path.write_text("evt_123\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a rec_id"):
        load_exclude(path)


def test_cli_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    data, db = _data(tmp_path), _db(tmp_path, ROWS[:2])
    monkeypatch.setattr("pickfit.d1.D1", lambda **_: db)
    assert main(["outcomes", "sync", "--dry-run", "--data", str(data)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "1 record would change (--dry-run: nothing written)"
