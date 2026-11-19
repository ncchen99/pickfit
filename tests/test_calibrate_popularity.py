"""scripts/calibrate_popularity.py: in-category P95 over rule-passed candidates; no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_profiles import add, extraction

from pickfit.discover.store import PipelineDB
from scripts.calibrate_popularity import main, percentile


def test_percentile_interpolates() -> None:
    assert percentile([10, 20, 30, 40], 50) == 25 and percentile([5], 95) == 5


def test_refs_are_the_p95_per_category(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = PipelineDB(tmp_path / "pipeline.db")
    for i in range(1, 6):
        add(db, i, f"someone/tool{i}", extraction())
    add(db, 9, "someone/engine", extraction(), category="local_ai")
    assert main(["--db", str(tmp_path / "pipeline.db")]) == 0
    out = capsys.readouterr().out
    refs = json.loads(out[out.index("{"):])
    assert out.startswith("dev_cli: 5 rule-passed candidates") and refs["dev_cli"]["stars"] == 42
    assert set(refs) == {"dev_cli", "local_ai"} and "hn_top_score" not in refs["dev_cli"]  # no --registries


def test_small_categories_by_extraction_use_the_pooled_refs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = PipelineDB(tmp_path / "pipeline.db")
    for i in range(1, 4):
        add(db, i, f"someone/tool{i}", extraction())
    # Found by a dev_cli query, extracted as data_db: it counts as data_db.
    add(db, 9, "someone/sqlview", extraction(category={"value": "data_db", "quote": "A tiny jq-like query tool"}))
    assert main(["--db", str(tmp_path / "pipeline.db"), "--by", "extraction", "--min", "2"]) == 0
    out = capsys.readouterr().out
    refs = json.loads(out[out.index("{"):])
    assert "data_db: 1 rule-passed candidates, fewer than 2: scored against _all" in out
    assert set(refs) == {"dev_cli", "_all"} and refs["_all"]["stars"] == 42
    assert main(["--db", str(tmp_path / "pipeline.db"), "--seen-before", "2000-01-01"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out[out.index("{"):]) == {}  # nothing first seen that early
