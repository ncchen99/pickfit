"""A web visit as a verification run in the web_app format, and its write-back (P3.12)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from pickfit.schema import SoftwareRecord
from pickfit.verify.web_record import match_feature, target_from_record, web_run, web_write_back, write_back_saved

FIXTURE = Path(__file__).parent / "fixtures" / "record_web_app.json"
URL = "https://fixture-sketch.example.invalid/"
FEATURES = ["draw diagrams", "export as PNG or SVG"]


def visit(**over: Any) -> dict[str, Any]:
    result = {
        "run_id": "web-fixture-sketch-20261102-010000-ab12", "slug": "fixture-web-sketch", "url": URL,
        "site": "example.invalid", "checked_at": "2026-11-02T01:00:00+08:00", "level": "function", "reason": None,
        "user_agent": "Mozilla/5.0 HeadlessChrome/156.0.1 Safari/537.36 pickfit-verifier/0.1",
        "install": {"url": URL, "title": "Sketch"},
        "install_judge": {"screen": "landing_page", "observed": "The editor with a toolbar and a blank canvas.",
                          "ads_visible": False, "core_needs_account": False},
        "function": {"steps": 6, "outcome": {"feature": "Draw diagrams", "result_kind": "text_on_page",
                                             "result_text": "Box pickfitab12", "blocked_by": "nothing", "notes": ""},
                     "check": {"passed": True, "kind": "text_on_page", "text": "Box pickfitab12"},
                     "typed": ["pickfitab12 box"]},
        "function_judge": {"feature_shown": True, "feature": "draw diagrams", "observed": "A labelled box appeared.",
                           "result_visible": "Box pickfitab12"},
        "network": {"third_party_sites": ["gstatic.com", "googleapis.com"], "third_party_count": 2, "ads": False,
                    "data_left_device": False, "traced": ["pickfitab12 box"], "leaks": []},
        "account_required": False, "pwa": True, "works_offline": "works",
        "offline_check": {"passed": True, "kind": "text_on_page", "text": "Box pickfitab13", "by": "agent offline",
                          "steps": 4},
        "offline_function_judge": {"feature_shown": True, "observed": "Offline, a box appeared."},
        "operator": {"models": {"meta-models/Muse-Spark-Open-816B-A42B": 9}},
        "costs": {"operator_usd": 0.1, "judge_usd": 0.02, "sandbox_usd": 0.02},
    }
    result.update(over)
    return result


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "software"
    d.mkdir()
    record = json.loads(FIXTURE.read_text())
    record["verification"] = {"level": "unverified", "unverified_reason": "not_run", "checked_at": None, "runs": []}
    (d / "fixture-web-sketch.json").write_text(json.dumps(record))
    return d


def test_a_function_visit_becomes_a_valid_web_run(tmp_path: Path):
    run = web_run(visit(), FEATURES, tmp_path)
    assert run is not None and run.level == "function" and not run.replayed
    web = run.web
    assert web.screen == "main_ui" and web.offline == "verified" and web.data_sent == "none"
    assert web.third_party_domains == 2 and web.third_party_hosts == ["gstatic.com", "googleapis.com"]
    assert [op.passed for op in web.operations] == [True, True] and web.operations[0].feature == "draw diagrams"
    assert run.smoke_tests[0].command == f"open {URL}" and run.smoke_tests[2].offline is True
    assert {f.feature: f.status for f in run.features} == {"draw diagrams": "checked",
                                                           "export as PNG or SVG": "not_checked"}
    assert "HeadlessChrome" not in web.browser and web.browser.startswith("Chromium 156")


def test_an_operation_the_judge_refused_leaves_install(tmp_path: Path):
    run = web_run(visit(level="function", function_judge={"feature_shown": False, "observed": "Nothing changed."},
                        works_offline=None, pwa=False), FEATURES, tmp_path)
    assert run.level == "install" and not run.web.operations[0].passed and run.web.offline == "not_tested"
    assert all(f.status == "not_checked" for f in run.features)


def test_data_sent_is_observed_unknown_or_none_as_the_requests_say(tmp_path: Path):
    seen = visit(network={"third_party_sites": [], "third_party_count": 0, "data_left_device": True,
                          "traced": ["Naruto"], "leaks": [{"host": "api.bgm.tv", "sent": True}]})
    assert web_run(seen, FEATURES, tmp_path).web.data_sent == "observed"
    short = visit(network={"third_party_sites": [], "data_left_device": None, "traced": [], "leaks": []})
    assert web_run(short, FEATURES, tmp_path).web.data_sent == "unknown"


def test_only_passed_visits_become_runs(tmp_path: Path):
    for level in ("unverified", "skipped", "error"):
        assert web_run(visit(level=level), FEATURES, tmp_path) is None


def test_write_back_keeps_install_empty_and_validates(data_dir: Path, tmp_path: Path):
    run = web_run(visit(), FEATURES, tmp_path)
    written, why = web_write_back(run, "fixture-web-sketch", data_dir)
    assert written, why
    record = SoftwareRecord.model_validate_json((data_dir / "fixture-web-sketch.json").read_text())
    assert record.verification.level == "function" and not record.install.guides()
    assert record.verification.runs[-1].id == run.id


def test_write_back_refuses_a_run_for_another_site_or_a_weaker_one(data_dir: Path, tmp_path: Path):
    other = web_run(visit(url="https://elsewhere.example.org/"), FEATURES, tmp_path)
    assert not web_write_back(other, "fixture-web-sketch", data_dir)[0]
    assert web_write_back(web_run(visit(), FEATURES, tmp_path), "fixture-web-sketch", data_dir)[0]
    weaker = web_run(visit(run_id="web-fixture-sketch-20261102-020000-cd34", function_judge={"feature_shown": False}),
                     FEATURES, tmp_path)
    written, why = web_write_back(weaker, "fixture-web-sketch", data_dir)
    assert not written and "stronger" in why


def test_saved_unverified_visit_is_not_written(data_dir: Path, tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "web_result.json").write_text(json.dumps(visit(level="unverified", reason="sign-in wall")))
    written, why = write_back_saved("fixture-web-sketch", run_dir, data_dir)
    assert not written and "unverified" in why


def test_targets_come_from_web_app_records():
    record = SoftwareRecord.model_validate_json(FIXTURE.read_text())
    target = target_from_record(record)
    assert target.url == URL and target.features == FEATURES and "diagram" in target.use_case


def test_feature_labels_match_by_words():
    assert match_feature("Export as PNG", FEATURES) == "export as PNG or SVG"
    assert match_feature("Something else entirely", FEATURES) is None


def test_record_targets_pick_web_apps_without_a_browser_run(data_dir: Path, tmp_path: Path):
    from pickfit.verify.web_record import record_targets

    assert [t.slug for t in record_targets([], data_dir)] == ["fixture-web-sketch"]
    web_write_back(web_run(visit(), FEATURES, tmp_path), "fixture-web-sketch", data_dir)
    assert record_targets([], data_dir) == []
    assert [t.slug for t in record_targets(["fixture-web-sketch"], data_dir)] == ["fixture-web-sketch"]


def test_hidden_records_are_neither_visited_nor_written(data_dir: Path, tmp_path: Path):
    from pickfit.verify.web_record import record_targets

    path = data_dir / "fixture-web-sketch.json"
    record = json.loads(path.read_text())
    record["status"], record["status_reason"] = "hidden", "will not be recommended"
    path.write_text(json.dumps(record))
    assert record_targets([], data_dir) == [] and record_targets(["fixture-web-sketch"], data_dir) == []
    written, why = web_write_back(web_run(visit(), FEATURES, tmp_path), "fixture-web-sketch", data_dir)
    assert not written and "hidden" in why
