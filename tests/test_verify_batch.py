"""Batch selection from a read-only pipeline database, and the parallel runner."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pickfit.discover.store import PipelineDB
from pickfit.meta import OPEN_MODEL
from pickfit.verify.batch import (
    load_candidates,
    recheck_slugs,
    record_slugs,
    run_batch,
    slug_for,
    verified_slugs,
)

FIXTURES = Path(__file__).parent / "fixtures" / "verify"


def extraction(**changes: Any) -> dict[str, Any]:
    data = json.loads((FIXTURES / "graphtty.json").read_text(encoding="utf-8"))["extraction"]
    for path, value in changes.items():
        node = data
        *parents, leaf = path.split("__")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return data


def add(db: PipelineDB, repo_id: int, full_name: str, result: dict[str, Any] | None, *, model: str = "muse-spark-1.3",
        status: str = "ok", rule_passed: bool = True, readme: str | None = "# readme\n") -> None:
    db.upsert_repo({"id": repo_id, "full_name": full_name, "html_url": f"https://github.com/{full_name}"},
                   category="dev_cli", query_id="q1", seen_at="2026-10-29T00:00:00+08:00")
    key = f"gh:{repo_id}"
    with db._write() as conn:
        conn.execute("UPDATE candidates SET readme = ?, rule_passed = ? WHERE repo_id = ?",
                     (readme, int(rule_passed), key))
    db.save_extraction(repo_id=key, run_id="x", model=model, reasoning_effort="minimal", status=status,
                       sources_sha="s", result=result, quote_failures=[], quotes_checked=0, error=None,
                       usage=None, cost_usd=0.0, cache_hit=False, response_id=None, latency_s=None)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "pipeline.db"
    db = PipelineDB(path)
    add(db, 1, "acme/graphtty", extraction())
    add(db, 2, "acme/keyed", extraction(prerequisites__api_keys=[{"value": "OPENAI_API_KEY",
                                                                   "quote": "OPENAI_API_KEY"}]))
    add(db, 3, "acme/gui", extraction(kind={"value": "desktop_app", "quote": "app"}))
    add(db, 4, "acme/macos", extraction(platforms={"value": ["macos"], "quote": "macOS"}))
    add(db, 5, "acme/nopath", extraction(install_methods=[{"method": "brew", "command": "brew install x",
                                                            "platforms": []}]))
    add(db, 6, "acme/rejected", extraction(), rule_passed=False)
    add(db, 7, "acme/failed", None, status="error")
    add(db, 8, "acme/noreadme", extraction(), readme=None)
    # Two extractions: the 1.3 one wins over a later contributor one.
    add(db, 9, "other/graphtty", extraction(name={"value": "contributor", "quote": "# graphtty"}),
        model="muse-spark-1.3-contributor")
    add(db, 9, "other/graphtty", extraction(name={"value": "standard", "quote": "# graphtty"}))
    add(db, 9, "other/graphtty", extraction(name={"value": "later contributor", "quote": "# graphtty"}),
        model="muse-spark-1.3-contributor")
    return path


def test_selection_ranks_demo_first_and_sets_aside_with_reasons(db_path: Path):
    items, skipped = load_candidates(db_path, limit=10)
    assert [i.full_name for i in items] == ["acme/graphtty", "other/graphtty", "acme/keyed"]
    assert [i.task.slug for i in items] == ["graphtty", "other-graphtty", "keyed"]
    assert items[0].priority > items[2].priority  # an API key costs priority
    other = items[1]
    assert other.extraction_model == "muse-spark-1.3" and other.task.extraction.name.value == "standard"
    assert other.task.repo_url == "https://github.com/other/graphtty" and other.task.readme == "# readme\n"
    reasons = {s["full_name"]: s["reason"] for s in skipped}
    assert reasons == {"acme/gui": "GUI app", "acme/macos": "platforms macos only",
                       "acme/nopath": "no install path the Linux box can run", "acme/noreadme": "no README stored"}


def test_selection_filters_and_limits(db_path: Path):
    items, _ = load_candidates(db_path, limit=1)
    assert [i.full_name for i in items] == ["acme/graphtty"]
    items, _ = load_candidates(db_path, limit=10, repos=["gh:2"])
    assert [i.full_name for i in items] == ["acme/keyed"]
    items, skipped = load_candidates(db_path, limit=10, skip_slugs={"graphtty"})
    assert "graphtty" not in [i.task.slug for i in items]
    assert {"slug": "graphtty", "reason": "already has a run (use --force)"}.items() <= skipped[0].items()


def test_a_muse_spark_open_extraction_is_used_when_it_is_the_only_one_or_asked_for(db_path: Path):
    db = PipelineDB(db_path)
    add(db, 9, "other/graphtty", extraction(name={"value": "open", "quote": "# graphtty"}), model=OPEN_MODEL)
    add(db, 11, "acme/openonly", extraction(), model=OPEN_MODEL)
    items, _ = load_candidates(db_path, limit=10)
    models = {i.full_name: (i.extraction_model, i.task.extraction.name.value) for i in items}
    assert models["other/graphtty"] == ("muse-spark-1.3", "standard")  # 1.3 still wins by default
    assert models["acme/openonly"][0] == OPEN_MODEL
    items, _ = load_candidates(db_path, limit=10, extraction_model=OPEN_MODEL)
    assert {i.full_name: i.task.extraction.name.value for i in items} == {
        "other/graphtty": "open", "acme/openonly": "graphtty"}


def test_gpu_tools_are_set_aside_unless_the_boxes_have_a_gpu(db_path: Path):
    db = PipelineDB(db_path)
    add(db, 10, "acme/cuda", extraction(prerequisites__gpu={"value": "required", "quote": "NVIDIA GPU"}))
    items, skipped = load_candidates(db_path, limit=10)
    assert {"full_name": "acme/cuda", "reason": "needs a GPU"}.items() <= next(
        s for s in skipped if s["full_name"] == "acme/cuda").items()
    items, _ = load_candidates(db_path, limit=10, repos=["gh:10"], gpu=True)
    assert [i.full_name for i in items] == ["acme/cuda"]


def test_database_is_opened_read_only(db_path: Path):
    db_path.chmod(0o444)
    try:
        load_candidates(db_path, limit=5)
    finally:
        db_path.chmod(0o644)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM extractions").fetchone()[0] == 11  # nothing written


def test_existing_records_decide_the_slug(db_path: Path, tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "gt.json").write_text(json.dumps({"repo_id": "gh:9", "slug": "graphtty-other"}))
    (data / "bad.json").write_text("{")
    known = record_slugs(data)
    assert known == {"gh:9": "graphtty-other"}
    items, _ = load_candidates(db_path, limit=10, known_slugs=known)
    assert {i.full_name: i.task.slug for i in items}["other/graphtty"] == "graphtty-other"


def test_slug_for_keeps_slugs_unique():
    taken: set[str] = set()
    assert slug_for("Acme/My.Tool", taken) == "my-tool"
    assert slug_for("other/my_tool", taken) == "other-my-tool"


def test_run_batch_runs_in_parallel_and_survives_errors(db_path: Path, tmp_path: Path):
    items, _ = load_candidates(db_path, limit=3)
    running, peak = 0, 0
    lock = threading.Lock()

    def verify(task, log):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        log("working")
        time.sleep(0.05)
        with lock:
            running -= 1
        if task.slug == "keyed":
            raise RuntimeError("box exploded")
        level = "function" if task.slug == "graphtty" else "unverified"
        return SimpleNamespace(notes=[], summary=lambda: {"slug": task.slug, "level": level, "replayed": True,
                                                          "seconds": 40.0, "cost_usd": 0.01})

    lines: list[str] = []
    summary = run_batch(items, verify, concurrency=3, runs_dir=tmp_path, log=lines.append, meta={"db": "x"})
    assert peak == 3
    assert (summary["tools"], summary["passed"], summary["errors"]) == (3, 1, 1)
    assert summary["levels"] == {"function": 1, "unverified": 1, "None": 1}
    assert summary["cost_usd"] == 0.02 and summary["seconds_median"] == 40.0
    saved = json.loads(Path(summary["path"]).read_text(encoding="utf-8"))
    assert [r["slug"] for r in saved["items"]] == ["graphtty", "other-graphtty", "keyed"]
    assert saved["items"][2]["error"] == "RuntimeError: box exploded"
    assert "[graphtty] working" in lines


def test_verified_slugs_reads_outcomes(tmp_path: Path):
    for name, slug in (("verify-x-20261029-001103-ab12", "x"), ("verify-y-20261029-020000-cd34", "y")):
        run = tmp_path / "verify" / name
        run.mkdir(parents=True)
        (run / "outcome.json").write_text(json.dumps({"slug": slug}))
    (tmp_path / "verify" / "broken").mkdir()
    (tmp_path / "verify" / "broken" / "outcome.json").write_text("{")
    assert verified_slugs(tmp_path) == {"x", "y"}
    assert verified_slugs(tmp_path, since="20261029-01") == {"y"}


def test_a_new_release_requeues_a_record_whose_runs_did_not_pass(tmp_path: Path):
    def record(slug: str, level: str, checked_at: str | None, released: str | None) -> None:
        runs = [{"id": f"verify-{slug}"}] if checked_at else []
        data = {"slug": slug, "verification": {"level": level, "checked_at": checked_at, "runs": runs},
                "last_release": {"published_at": released} if released else None}
        (tmp_path / f"{slug}.json").write_text(json.dumps(data))

    record("fixed", "failed", "2026-10-29T02:44:43+08:00", "2026-11-01T09:00:00Z")
    record("boxed", "unverified", "2026-10-29T02:44:43+08:00", "2026-11-01T09:00:00Z")
    record("same-release", "failed", "2026-10-29T02:44:43+08:00", "2026-10-27T19:03:47Z")
    record("passed", "function", "2026-10-29T02:44:43+08:00", "2026-11-01T09:00:00Z")
    record("never-run", "unverified", None, "2026-11-01T09:00:00Z")
    runs = tmp_path / "runs"
    assert recheck_slugs(tmp_path, runs) == {"fixed", "boxed"}
    def attempt(run_id: str, slug: str, stop: str | None) -> None:
        folder = runs / "verify" / run_id
        folder.mkdir(parents=True)
        (folder / "outcome.json").write_text(json.dumps({"slug": slug, "level": "unverified", "written": False}))
        if stop:
            (folder / "report.json").write_text(json.dumps({"stop_reason": stop}))

    # A recheck that never ran (the model 404ed, the box did not start, no report) does not settle it.
    attempt("verify-fixed-20261101-180000-ab12", "fixed", "model_error")
    attempt("verify-boxed-20261101-180000-ab12", "boxed", None)
    assert recheck_slugs(tmp_path, runs) == {"fixed", "boxed"}
    # One that ran settles it, written back or not (it ended unverified "other").
    attempt("verify-fixed-20261101-190000-cd34", "fixed", "finished")
    assert recheck_slugs(tmp_path, runs) == {"boxed"}


def test_features_of_a_features_only_extraction_join_the_extraction_that_built_the_record(db_path: Path):
    db = PipelineDB(db_path)
    feats = {"features": [{"value": "render a graph", "quote": "graphtty graph.json"}]}
    add(db, 1, "acme/graphtty", feats, status="features")
    (item,) = [i for i in load_candidates(db_path, limit=10)[0] if i.repo_id == "gh:1"]
    assert [f.value for f in item.task.extraction.features] == ["render a graph"]
    assert item.task.extraction.kind.value == "cli_tool"  # everything else is the earlier extraction
    # A full extraction made after it, with features of its own, wins.
    add(db, 1, "acme/graphtty", extraction(features=[{"value": "theme it", "quote": "graphtty"}]))
    (item,) = [i for i in load_candidates(db_path, limit=10)[0] if i.repo_id == "gh:1"]
    assert [f.value for f in item.task.extraction.features] == ["theme it"]
