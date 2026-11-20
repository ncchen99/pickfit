"""scripts/reclassify_categories.py (11/20): old catch-all records moved to their subject category, nothing else."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from queue_fakes import EXAMPLE

from pickfit.schema import LISTED_CATEGORIES, SoftwareRecord

SPEC = importlib.util.spec_from_file_location(
    "reclassify_categories", Path(__file__).resolve().parent.parent / "scripts" / "reclassify_categories.py")
rc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rc)  # type: ignore[union-attr]
NOW = "2026-11-20T15:00:00+08:00"
SUBJECTS = {"infra_devops", "security_net", "data_db", "productivity_docs", "media_files"}


def record(slug: str, category: str) -> dict:
    data = json.loads(json.dumps(EXAMPLE))
    data.update(slug=slug, repo_id=f"gh:{abs(hash(slug)) % 10**6}", category=category)
    data["evidence"] = [*data.get("evidence", []), {"field": "/category", "source_id": "readme", "quote": "a JSON processor",
                                                     "method": "model", "model": "muse-spark-1.3",
                                                     "checked_at": "2026-11-04T13:28:34+08:00"}]
    return json.loads(SoftwareRecord.model_validate(data).model_dump_json())


def write(root: Path, data: dict) -> Path:
    path = root / f"{data['slug']}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_the_table_only_moves_catch_alls_into_subject_categories() -> None:
    assert rc.MOVES and len(rc.MOVES) == len(set(rc.MOVES))
    for slug, (frm, to) in rc.MOVES.items():
        assert frm in ("other", "dev_cli") and to in SUBJECTS and to in LISTED_CATEGORIES, slug


def test_only_category_its_evidence_and_updated_at_change() -> None:
    before = record("jq", "dev_cli")
    after = rc.reclassify(before, "data_db", NOW)
    assert after["category"] == "data_db" and after["updated_at"] == NOW and after["slug"] == "jq"
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"category", "evidence", "updated_at"}
    cat = [e for e in after["evidence"] if e["field"] == "/category"]
    assert cat == [{**[e for e in before["evidence"] if e["field"] == "/category"][0], "method": "rule",
                    "model": None, "checked_at": NOW}]
    assert [e for e in after["evidence"] if e["field"] != "/category"] == \
        [e for e in before["evidence"] if e["field"] != "/category"]
    for key in ("scores", "security", "verification", "install", "features"):
        assert after.get(key) == before.get(key)
    SoftwareRecord.model_validate(after)


def test_a_record_not_in_the_expected_category_is_left_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "MOVES", {"jq": ("dev_cli", "data_db"), "k9s": ("dev_cli", "infra_devops"),
                                      "gone": ("other", "media_files"), "tilt": ("dev_cli", "infra_devops")})
    write(tmp_path, record("jq", "dev_cli"))
    write(tmp_path, record("k9s", "local_ai"))
    write(tmp_path, record("tilt", "infra_devops"))
    moves, skipped = rc.plan(tmp_path)
    assert moves == [("jq", "dev_cli", "data_db")]
    assert skipped == {"k9s": "is local_ai, expected dev_cli: left alone", "gone": "no such record",
                       "tilt": "already infra_devops"}


def test_a_dry_run_writes_nothing_and_a_run_writes_valid_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                 capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(rc, "MOVES", {"jq": ("dev_cli", "data_db"), "handbrake": ("other", "media_files")})
    paths = [write(tmp_path, record("jq", "dev_cli")), write(tmp_path, record("handbrake", "other"))]
    raw = [p.read_bytes() for p in paths]
    assert rc.main(["--data-dir", str(tmp_path), "--dry-run", "--now", NOW]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [p.read_bytes() for p in paths] == raw
    assert report["moved"] == 2 and report["listed_after"]["data_db"] == 1 and report["listed_after"]["media_files"] == 1
    assert rc.main(["--data-dir", str(tmp_path), "--now", NOW]) == 0
    capsys.readouterr()
    for path, want in zip(paths, ("data_db", "media_files")):
        rec = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
        assert rec.category == want and rec.slug == path.stem
    assert rc.main(["--data-dir", str(tmp_path), "--now", NOW]) == 0  # again: nothing left to move
    assert json.loads(capsys.readouterr().out)["moved"] == 0
