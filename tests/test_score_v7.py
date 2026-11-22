"""Formula b3.v7 (docs/proposals/scoring.md as reworked by docs/proposals/coverage.md, 11/19): stored inputs, rubric
versions and reuse, known security findings under settings whose defaults are today's rules, the treasure and cap
rules as settings, confidence from the coverage, history, and the migration and recompute scripts; no network."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_extract import FakeMeta, ok
from test_profiles import MODEL, README, add, extraction
from test_score import LATER, NOW, fake_grade, feature, issue, items, run, setup_records, verification, with_features

import pickfit.env
from pickfit import coverage, extract, meta, schema
from pickfit import score as score_module
from pickfit.cli import main
from pickfit.discover.store import PipelineDB
from pickfit.extract import build_sources, input_sha, sources_sha
from pickfit.ledger import Caps, Ledger
from pickfit.schema import DocsRubric, DocsRubricItems, Scores, SoftwareRecord, required_treasure_block
from pickfit.score import (
    FORMULA_VERSION,
    HISTORY_KEPT,
    compose_quality,
    github_inputs,
    hygiene_from_inputs,
    hygiene_score,
    issue_inputs,
    maintenance_penalty,
    maintenance_score,
    refresh_scores,
    remember,
    repository_components,
    responsiveness_detail,
    rubric_reuse,
    sandbox_score,
    score_records,
    security_effect,
    snapshot_time,
    stale_fixes,
    treasure,
    treasure_block_of,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "default-ledger.sqlite"))
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(meta, "sleep", lambda s: None)


def scored(tmp_path: Path, **kwargs: Any) -> tuple[Path, Path, dict[str, Any]]:
    db_path, out = setup_records(tmp_path, **kwargs)
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW,
                  grade=fake_grade())
    return db_path, out, json.loads((out / "tinyq.json").read_text(encoding="utf-8"))


SEVEN = {"sandbox_verification": 1.0, "feature_results": None, "install_docs": 0.5, "maintenance": 0.5,
         "engineering_hygiene": 0.5, "responsiveness": None, "usage_outcomes": None}


# --- R6 and R7 moved to Verification Coverage ---------------------------------------------------------------------


def test_missing_data_leaves_the_denominator_and_depth_is_not_a_quality_result() -> None:
    q = compose_quality(SEVEN, 10, None)
    assert q["total"] == round(100 * (20 * 1.0 + 25 * 0.5 + 10 * 0.5 + 5 * 0.5) / 60, 1)  # no category mean
    assert q["confidence"] == 0.6 and set(q["components"]["feature_results"]) == {"score", "weight"}
    for level in ("install", "function", "service", "inference"):
        assert sandbox_score(verification(run(level=level))) == 1.0
    # How far a run got and how much a component rests on are the coverage's measures instead.
    record = {"slug": "x", "kind": "cli_tool", "category": "dev_cli", "platforms": ["linux"],
              "verification": {"level": "install", "runs": [with_features(feature("a", "checked"), level="install")]}}
    function = coverage.compute_coverage(record)["dimensions"]["function"]
    assert function["measure"]["depth"] == "install" and function["measure"]["reliability"] == 0.5
    assert not hasattr(score_module, "QUALITY_PRIORS") and not hasattr(score_module, "SANDBOX_DEPTH")


# --- R5: known findings only, under settings whose defaults are today's rules ---------------------------------------


def sec(level: str | None = None, status: str = "vulnerable", state: str | None = None, **assessment: Any
        ) -> dict[str, Any]:
    out: dict[str, Any] = {"status": status, "checked_at": "2026-11-10T00:00:00+08:00", "findings": []}
    if level:
        out["assessment"] = {"level": level, **assessment}
    if state:
        out["coverage"] = {"state": state, "packages_checked": 0 if state == "unchecked" else 10,
                           "packages_found": 20, "gaps": []}
    return out


@pytest.mark.parametrize(("security", "effect", "cap"), [
    (sec("blocked"), "unlisted", "known_vulnerability"),
    (sec("exposed"), "capped", "known_vulnerability"),
    (sec("conditional"), "note", None),  # rule 1 (11/20): conditional is not capped, it gets a line on the page
    (sec("present_unreachable", status="clean"), "none", None),
    (sec("not_shipped", status="clean"), "none", None),
    (sec("none", status="unchecked", state="partial"), "none", None),  # an unknown is never a problem
    (sec("none", status="unchecked", state="unchecked"), "none", None),
    (sec(status="vulnerable"), "capped", "known_vulnerability"),  # sec.v1, no assessment: its rule
    (sec(status="clean"), "none", None),
    (sec(status="unchecked"), "none", None),
    (None, "none", None),
])
def test_by_default_the_cap_is_todays_and_no_unknown_deducts(security: Any, effect: str, cap: str | None) -> None:
    got = security_effect(security)
    assert got["effect"] == effect and got["deduction"] == 0.0
    assert schema.binding_cap("cli_tool", False, "function", security) == cap
    assert required_treasure_block(security, "function") is None
    # Rule 1 (11/20): blocked and exposed are capped; conditional still reads vulnerable but is not capped.
    assert schema.SECURITY_CAP_LEVELS == schema.WARN_LEVELS - {"conditional"}


def test_the_r5_candidates_are_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schema, "SECURITY_CAP_LEVELS", frozenset())
    monkeypatch.setattr(schema, "SECURITY_NO_TREASURE_LEVELS", frozenset({"blocked", "exposed"}))
    monkeypatch.setattr(score_module, "SECURITY_EXPOSED_DEDUCTION", 10.0)
    full = {**SEVEN, "feature_results": 1.0, "install_docs": 1.0, "maintenance": 1.0, "engineering_hygiene": 1.0,
            "responsiveness": 1.0}
    clean = compose_quality(full, 10, None, security=security_effect(sec(status="clean")))
    exposed = compose_quality(full, 10, schema.binding_cap("cli_tool", False, "function", sec("exposed")),
                              security=security_effect(sec("exposed")))
    assert exposed["cap"] is None and exposed["raw_total"] == clean["total"] == 100.0
    assert exposed["total"] == 90.0 and exposed["security"] == {"level": "exposed", "basis": "assessment",
                                                               "effect": "deducted", "deduction": 10.0}
    assert required_treasure_block(sec("exposed"), "function") == "security_exposed"
    assert required_treasure_block(sec("blocked"), "function") == "security_blocked"
    assert required_treasure_block(sec("conditional"), "function") is None
    assert security_effect(sec("conditional"))["effect"] == "note"  # no cap any more: a line on the page
    blocked = treasure(exposed | {"total": 95.0}, 20.0, blocked="security_exposed")
    assert blocked == {"is_treasure": False, "value": 76.0, "blocked_by": "security_exposed"}
    monkeypatch.setattr(schema, "SECURITY_CAP_LEVELS", frozenset({"blocked", "exposed"}))  # conditional uncapped
    assert schema.binding_cap("cli_tool", False, "function", sec("conditional")) is None
    assert schema.binding_cap("cli_tool", False, "function", sec("exposed")) == "known_vulnerability"
    assert schema.binding_cap("cli_tool", False, "function", sec(status="vulnerable")) == "known_vulnerability"


def test_a_scored_record_follows_its_assessment_and_the_settings(tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, data = scored(tmp_path)
    data["scores"]["popularity"]["signals"]["stars"] = 1  # keep it under the popularity line
    for level, capped in (("conditional", False), ("exposed", True), ("blocked", True), ("not_shipped", False)):
        data["security"] = sec(level)
        refresh_scores(data, LATER)
        q, t = data["scores"]["quality"], data["scores"]["treasure"]
        assert (q["cap_reason"] == "known_vulnerability") is capped and q["security"]["level"] == level
        assert "blocked_by" not in t
        Scores.model_validate(data["scores"])  # the record's security field is sec.v1's until S1 lands
    monkeypatch.setattr(schema, "SECURITY_CAP_LEVELS", schema.WARN_LEVELS)  # the rule before 11/20
    data["security"] = sec("conditional")
    refresh_scores(data, LATER)
    assert data["scores"]["quality"]["cap_reason"] == "known_vulnerability"
    assert data["scores"]["quality"]["security"]["effect"] == "capped"


def test_a_fix_out_for_ninety_days_comes_off_maintenance_only_when_switched_on(monkeypatch: pytest.MonkeyPatch
                                                                              ) -> None:
    def finding(days: int, level: str = "exposed") -> dict[str, Any]:
        return {"fix_published_at": (datetime(2026, 11, 10) - timedelta(days=days)).isoformat() + "+08:00",
                "level": level}

    security = sec("exposed", assessed_at="2026-11-10T00:00:00+08:00") | {"observation": {"findings": [
        finding(120), finding(30), finding(200, "not_shipped")]}}
    assert stale_fixes(security) == 1  # 30 days is not yet late; a part that is not shipped does not count
    assert score_module.STALE_FIX_PENALTY == 0.0 and maintenance_penalty(0.9, security) == (0.9, None)  # off
    monkeypatch.setattr(score_module, "STALE_FIX_PENALTY", 0.3)
    assert maintenance_penalty(0.9, security) == (0.6, 0.3)
    assert maintenance_penalty(0.2, security) == (0.0, 0.2)
    assert maintenance_penalty(0.9, sec(status="vulnerable")) == (0.9, None)  # sec.v1 findings carry no date
    assert maintenance_penalty(None, security) == (None, None)


# --- the treasure and cap rules: settings, today's rules by default --------------------------------------------------


def test_unchecked_can_be_a_treasure_unless_the_setting_is_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, data = scored(tmp_path)
    assert schema.UNCHECKED_CAN_BE_TREASURE is True  # R9 default: today's rule
    assert required_treasure_block(None, "function") is None
    assert required_treasure_block(sec(status="unchecked"), "function") is None
    monkeypatch.setattr(schema, "UNCHECKED_CAN_BE_TREASURE", False)
    for security in (None, sec(status="unchecked"), sec("none", status="unchecked", state="unchecked")):
        assert required_treasure_block(security, "function") == "security_unchecked"
    assert required_treasure_block(sec("none", status="unchecked", state="partial"), "function") is None  # some read
    assert required_treasure_block(sec(status="clean"), "function") is None
    with pytest.raises(ValueError, match="blocked_by must be 'security_unchecked'"):
        SoftwareRecord.model_validate(data)  # stored scores must be refreshed when the setting changes
    refresh_scores(data, LATER)
    assert data["scores"]["treasure"]["blocked_by"] == "security_unchecked"
    assert data["scores"]["treasure"]["is_treasure"] is False
    SoftwareRecord.model_validate(data)


def test_the_unverified_cap_can_become_a_coverage_rule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, out = setup_records(tmp_path, verified=False)
    score_records(out, db_path=tmp_path / "pipeline.db", model=MODEL, use_github=False, use_registries=False, now=NOW,
                  grade=fake_grade())
    data = json.loads((out / "tinyq.json").read_text(encoding="utf-8"))
    q = data["scores"]["quality"]
    t = data["scores"]["treasure"]
    # Rule 6 (the default since 11/19): no 69 cap; it keeps its own score and order but cannot be a treasure.
    assert q["cap_reason"] is None and q["total"] == q["raw_total"]
    assert t["blocked_by"] == "unverified" and t["is_treasure"] is False
    SoftwareRecord.model_validate(data)
    monkeypatch.setattr(schema, "UNVERIFIED_CAP", True)  # the rule before 11/19
    refresh_scores(data, LATER)
    q = data["scores"]["quality"]
    assert q["cap_reason"] == "unverified" and q["total"] == min(q["raw_total"], 69.0)
    SoftwareRecord.model_validate(data)


def test_coverage_thresholds_block_a_treasure_only_when_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, data = scored(tmp_path)
    assert treasure_block_of(data) is None  # a function-level record passes the default (P2-01) threshold
    monkeypatch.setattr(schema, "TREASURE_MIN_FUNCTION_COVERAGE", 0.5)
    assert coverage.dimension_share(coverage.compute_coverage(data)["dimensions"]["function"]) == 1.0
    assert treasure_block_of(data) is None
    data["verification"]["runs"][0]["level"] = "install"  # no feature list and only an install check
    data["verification"]["level"] = "install"
    assert treasure_block_of(data) == "function_coverage"
    refresh_scores(data, LATER)
    assert data["scores"]["treasure"]["blocked_by"] == "function_coverage"
    SoftwareRecord.model_validate(data)
    monkeypatch.setattr(schema, "TREASURE_MIN_FUNCTION_COVERAGE", None)
    with pytest.raises(ValueError, match="follows no rule that is on"):
        SoftwareRecord.model_validate(data)  # switched off again: refresh_scores clears it
    refresh_scores(data, LATER)
    assert "blocked_by" not in data["scores"]["treasure"]
    monkeypatch.setattr(schema, "TREASURE_MIN_SECURITY_COVERAGE", 0.8)
    assert treasure_block_of(data | {"security": sec("none", status="unchecked", state="partial")}  # 10 of 20
                             ) == "security_coverage"
    assert treasure_block_of(data | {"security": sec(status="clean")}) is None


# --- confidence from the coverage ----------------------------------------------------------------------------------


def test_confidence_is_derived_from_the_coverage_and_is_the_same_number(tmp_path: Path) -> None:
    _, _, data = scored(tmp_path)
    q = data["scores"]["quality"]
    had = sum(c["weight"] for c in q["components"].values() if c["score"] is not None) / 100
    assert q["confidence"] == round(had, 2)
    weights = {k: c["weight"] for k, c in q["components"].items()}
    assert coverage.quality_confidence(coverage.compute_coverage(data), weights) == q["confidence"]
    data["security"] = sec("none", status="unchecked", state="unchecked")
    refresh_scores(data, LATER)
    assert data["scores"]["quality"]["confidence"] == q["confidence"]  # security is never in it


# --- the defaults move no published quality total -------------------------------------------------------------------


def test_with_the_default_settings_b3_v6_scores_keep_their_totals_and_treasure(tmp_path: Path) -> None:
    _, _, data = scored(tmp_path)
    old = copy.deepcopy(data)
    old["scores"]["formula_version"] = "b3.v6"
    for key in ("inputs", "history"):
        old["scores"].pop(key, None)
    old["scores"]["quality"] = {k: v for k, v in old["scores"]["quality"].items() if k not in ("raw_total", "security")}
    before = copy.deepcopy(old["scores"])
    note = refresh_scores(old, LATER)
    assert note == f"scores moved from formula b3.v6 to {FORMULA_VERSION}, refreshed from the record"
    after = old["scores"]
    for key in ("total", "confidence", "cap", "cap_reason", "components"):
        assert after["quality"][key] == before["quality"][key], key
    assert after["treasure"] == before["treasure"] and after["popularity"] == before["popularity"]  # dev_cli: own refs
    assert after["history"][0]["formula_version"] == "b3.v6" and after["inputs"]["github"] is None
    SoftwareRecord.model_validate(old)
    for status in ("vulnerable", "unchecked", "clean"):  # sec.v1 as the records hold it: the same cap as before
        assert schema.binding_cap("cli_tool", False, "function", {"status": status}) == (
            "known_vulnerability" if status == "vulnerable" else None)


def test_pickfit_coverage_rules_compares_every_candidate_without_writing(tmp_path: Path, capsys: Any) -> None:
    _, out, data = scored(tmp_path)
    before = (out / "tinyq.json").read_bytes()
    assert coverage.rules_available()
    assert main(["coverage", "rules", "--data-dir", str(out), "--all-statuses", "--now",
                 "2026-11-19T12:00:00+08:00"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert set(result["rules"]["rules"]) == set(coverage.CANDIDATE_RULES)
    assert result["rules"]["default"]["treasures"] == int(data["scores"]["treasure"]["is_treasure"])
    for rule in result["rules"]["rules"].values():
        assert {"treasures", "gained", "lost", "at_69.0", "at_79.0", "settings"} <= set(rule)
    assert (out / "tinyq.json").read_bytes() == before
    assert schema.UNVERIFIED_CAP is False and schema.SECURITY_NO_TREASURE_LEVELS == frozenset()  # restored


# --- R1, R10: stored inputs, recomputed with no call, and history ----------------------------------------------------


def snapshot(pushed: str = "2026-10-20T00:00:00Z") -> dict[str, Any]:
    return {"full_name": "a/tool", "details_at": "2026-10-28T19:00:00+08:00", "details_pushed_at": pushed,
            "repo": {"full_name": "a/tool", "stargazers_count": 42, "forks_count": 3, "open_issues_count": 2,
                     "created_at": "2026-03-01T00:00:00Z", "pushed_at": pushed},
            "releases": [{"tag": "v1.1", "published_at": "2026-10-01T00:00:00Z", "prerelease": False,
                          "body": "Fixes the parser and adds --watch.", "assets": [{"name": "a", "downloads": 7}]},
                         {"tag": "v1.0", "published_at": "2026-06-01T00:00:00Z", "prerelease": False, "body": "",
                          "assets": []}],
            "files": [".github/workflows/ci.yml", "tests/test_a.py", "Cargo.lock", "src/main.rs",
                      "vendor/x/CHANGELOG.md"], "files_truncated": False}


def test_the_repository_components_come_out_the_same_from_the_stored_inputs() -> None:
    snap = snapshot()
    as_of = snapshot_time(snap, NOW)
    gh = json.loads(json.dumps(github_inputs(snap, "pipeline_db", as_of)))
    assert gh["files"] == {"count": 5, "truncated": False, "ci": ".github/workflows/ci.yml", "tests": "tests/test_a.py",
                           "changelog": None, "lockfile": "Cargo.lock"}  # a vendored changelog is not the project's
    assert [r["downloads"] for r in gh["releases"]] == [7, None] and gh["releases"][0]["notes_chars"] == 34
    for open_source in (True, None):
        assert hygiene_from_inputs(gh, open_source) == hygiene_score(snap, open_source)
    items = [issue(closed_days=2), issue(), issue("OWNER", closed_days=1), issue(pr=True)]
    inputs = {"github": gh, "issues": issue_inputs(items, NOW)}
    assert inputs["issues"]["pull_requests"] == 1 and len(inputs["issues"]["items"]) == 3
    components, penalty = repository_components(inputs, open_source=True, security=None)
    assert components["maintenance"] == maintenance_score(snap, as_of)
    assert components["responsiveness"] == responsiveness_detail(items, as_of)[0]
    assert responsiveness_detail(items, as_of)[1] == 2 and penalty is None


def test_scores_store_their_inputs_and_refresh_recomputes_from_them(tmp_path: Path) -> None:
    _, _, data = scored(tmp_path)
    scores = data["scores"]
    assert scores["formula_version"] == FORMULA_VERSION and scores["inputs"]["github"]["source"] == "pipeline_db"
    assert scores["inputs"]["issues"] is None and scores["inputs"].get("legacy") is None  # --no-github
    assert refresh_scores(data, LATER) is None  # the same inputs give the same scores
    before = scores["quality"]["components"]["maintenance"]["score"]
    data["scores"]["inputs"]["github"]["pushed_at"] = "2025-01-01T00:00:00Z"  # an old push, as stored
    assert refresh_scores(data, LATER) == "scores refreshed from the record"
    assert data["scores"]["quality"]["components"]["maintenance"]["score"] == round(before - 0.35, 4)  # no call
    SoftwareRecord.model_validate(data)


def test_a_record_scored_before_b3_v7_keeps_its_components_as_legacy_and_its_history(tmp_path: Path) -> None:
    _, _, data = scored(tmp_path)
    old = data["scores"]
    comps = old["quality"]["components"]
    legacy = {**old, "formula_version": "b3.v6",
              "quality": {k: v for k, v in old["quality"].items() if k not in ("raw_total", "security")}
              | {"components": {k: {"score": c["score"], "weight": c["weight"]} for k, c in comps.items()}}}
    legacy.pop("inputs")
    legacy["quality"]["components"]["responsiveness"]["score"] = 0.75  # measured from issues, never stored
    data["scores"] = legacy
    note = refresh_scores(data, LATER)
    assert note == f"scores moved from formula b3.v6 to {FORMULA_VERSION}, refreshed from the record"
    inputs = data["scores"]["inputs"]
    assert inputs["github"] is None and inputs["legacy"]["responsiveness"] == 0.75
    assert data["scores"]["quality"]["components"]["responsiveness"]["score"] == 0.75
    assert data["scores"]["history"][0]["formula_version"] == "b3.v6"
    SoftwareRecord.model_validate(data)


def test_history_keeps_the_newest_few() -> None:
    scores = {"formula_version": "b3.v1", "computed_at": "2026-10-29T00:00:00+08:00", "quality": {"total": 70.0},
              "popularity": {"score": 20.0}, "treasure": {"is_treasure": False}}
    for i in range(HISTORY_KEPT + 2):
        scores["formula_version"] = f"b3.v{i}"
        remember(scores)
    assert len(scores["history"]) == HISTORY_KEPT and scores["history"][0]["formula_version"] == f"b3.v{HISTORY_KEPT + 1}"


def test_the_backfill_fills_github_inputs_from_the_pipeline_database(tmp_path: Path,
                                                                     capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.migrate_score_inputs import main as backfill

    db_path, out, data = scored(tmp_path)
    data["scores"].pop("inputs")
    data["scores"]["formula_version"] = "b3.v6"
    data["scores"]["quality"].pop("raw_total"), data["scores"]["quality"].pop("security")
    data["scores"]["quality"] = compose_quality({k: c["score"] for k, c in data["scores"]["quality"][
        "components"].items()}, 10, None)
    data["scores"]["treasure"] = treasure(data["scores"]["quality"], data["scores"]["popularity"]["score"])
    path = out / "tinyq.json"
    path.write_text(json.dumps(data))
    SoftwareRecord.model_validate(data)
    assert backfill(["--data-dir", str(out), "--db", str(db_path)]) == 0
    assert json.loads(capsys.readouterr().out)["records"] == {"github from pipeline_db": 1}
    assert "inputs" not in json.loads(path.read_text())["scores"]  # a dry run writes nothing
    assert backfill(["--data-dir", str(out), "--db", str(db_path), "--write"]) == 0
    capsys.readouterr()
    written = json.loads(path.read_text())
    assert written["scores"]["inputs"]["github"]["source"] == "pipeline_db"
    assert written["scores"]["formula_version"] == "b3.v6"  # only inputs: --refresh moves it
    assert "moved from formula b3.v6" in refresh_scores(written, LATER)
    SoftwareRecord.model_validate(written)


# --- R2, R3: rubric versions and reuse ------------------------------------------------------------------------------


def rubric_for(snap: dict[str, Any], **fields: Any) -> DocsRubric:
    sources = build_sources(snap)
    return DocsRubric(model=MODEL, checked_at=NOW, sources_sha=sources_sha(sources),
                      items=DocsRubricItems.model_validate(items(2)), **fields)


def readme_snapshot(readme: str = README) -> dict[str, Any]:
    return {"full_name": "someone/tinyq", "readme": readme, "readme_path": "README.md", "releases": [],
            "repo": {"full_name": "someone/tinyq", "html_url": "https://github.com/someone/tinyq",
                     "default_branch": "main"}}


def test_a_rubric_is_reused_while_its_raw_text_is_the_same_whatever_the_renderer(monkeypatch: pytest.MonkeyPatch
                                                                                ) -> None:
    snap = readme_snapshot()
    stamped = rubric_for(snap, input_sha=input_sha(snap), prompt_version="rubric-p1", renderer_version="r1")
    assert rubric_reuse(stamped, snap, build_sources(snap)) is stamped
    monkeypatch.setattr(extract, "README_MAX_CHARS", 20)  # only the renderer changed
    assert rubric_reuse(stamped, snap, build_sources(snap)) is stamped
    changed = readme_snapshot(README + "\nNew: --watch\n")
    assert rubric_reuse(stamped, changed, build_sources(changed)) is None  # the README changed: grade again
    assert rubric_reuse(stamped, snap, build_sources(snap), regrade_before="rubric-p2") is None  # asked for
    assert rubric_reuse(stamped, snap, build_sources(snap), regrade_before="p9") is stamped  # extraction's family
    assert rubric_reuse(stamped, snap, build_sources(snap), regrade_models=frozenset({MODEL})) is None


def test_a_rubric_from_before_versions_is_stamped_as_current(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = readme_snapshot()
    legacy = rubric_for(snap)
    same = rubric_reuse(legacy, snap, build_sources(snap))
    assert (same.input_sha, same.prompt_version, same.renderer_version, same.grader) == (
        input_sha(snap), "rubric-p1", "r1", "meta")
    monkeypatch.setattr(extract, "README_MAX_CHARS", 20)
    drifted = rubric_reuse(legacy, snap, build_sources(snap))
    assert drifted is not None and drifted.renderer_version == "r0"  # nothing graded again by itself
    assert rubric_reuse(legacy, snap, build_sources(snap), regrade_before="r1") is None  # unless asked


def test_grading_stores_the_prompt_input_renderer_and_grader(tmp_path: Path) -> None:
    db_path, out = setup_records(tmp_path)
    calls: list[str] = []
    score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW,
                  grade=fake_grade(calls=calls))
    rubric = json.loads((out / "tinyq.json").read_text())["scores"]["docs_rubric"]
    candidate = PipelineDB(db_path).candidate(json.loads((out / "tinyq.json").read_text())["repo_id"])
    assert rubric["input_sha"] == input_sha(candidate) and calls == ["score:tinyq"]
    again = score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=LATER,
                          grade=fake_grade(calls=calls), regrade_models=[MODEL])
    assert again.graded == 1 and calls == ["score:tinyq", "score:tinyq"]
    with pytest.raises(ValueError, match="refresh-before"):
        score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=LATER,
                      grade=fake_grade(), regrade_before="v2")


def test_grade_docs_records_its_versions(tmp_path: Path) -> None:
    from test_score import reply

    import httpx2
    import openai

    client = openai.OpenAI(api_key="sk-test-0123456789", base_url="https://api.meta.ai/v1", max_retries=0,
                           http_client=httpx2.Client(transport=httpx2.MockTransport(lambda r: reply(items(2)))))
    ledger = Ledger(tmp_path / "ledger.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))
    snap = readme_snapshot()
    graded = score_module.grade_docs(build_sources(snap), model=MODEL, run_id="score-t", scope="score:tinyq", now=NOW,
                                     client=client, ledger=ledger, runs_dir=tmp_path / "runs", input_sha=input_sha(snap))
    r = graded.rubric
    assert (r.prompt_version, r.renderer_version, r.grader, r.input_sha) == ("rubric-p1", "r1", "meta", input_sha(snap))


# --- R4: the extraction call grades the rubric too (off by default) ----------------------------------------------------


def test_the_merged_rubric_is_off_by_default_and_rides_on_the_extraction_when_on(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert extract.RUBRIC_IN_EXTRACTION is False
    db_path = tmp_path / "pipeline.db"
    db = PipelineDB(db_path)
    key = add(db, 7, "someone/tinyq", extraction())
    sources = build_sources(db.candidate(key))
    plain = extract.build_body(sources)
    merged = extract.build_body(sources, with_rubric=True)
    assert "docs_rubric" not in json.dumps(plain["text"]) and "docs_rubric" in json.dumps(merged["text"])
    assert merged["instructions"].startswith(plain["instructions"]) and "what_it_does" in merged["instructions"]
    assert merged["text"]["format"]["name"] == "software_extraction_rubric"
    answer = extraction() | {"docs_rubric": items(2) | {"troubleshooting_uninstall": {"score": 2, "quote": "made up"}}}
    server = FakeMeta(ok(answer))
    ledger = Ledger(tmp_path / "ledger.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))
    monkeypatch.setattr(extract, "RUBRIC_IN_EXTRACTION", True)
    summary = extract.run_extract(limit=5, db_path=db_path, client=server.client(), ledger=ledger, model=MODEL,
                                  runs_dir=tmp_path / "runs", log=lambda line: None, force=True)
    assert summary["by_status"] in ({"ok": 1}, {"quotes_dropped": 1})
    row = db.last_extraction(key, MODEL, statuses=("ok", "quotes_dropped"))
    assert "docs_rubric" not in row["result"] and row["rubric"]["prompt_version"] == "merged-p1"
    assert row["rubric"]["unquoted"] == ["troubleshooting_uninstall"]  # the quote check applies as in a rubric call
    assert row["rubric"]["input_sha"] == input_sha(db.candidate(key))
    # Scoring then takes that rubric instead of a call of its own.
    out = tmp_path / "software"
    from pickfit.profiles import write_profiles

    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    calls: list[str] = []
    summary = score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=NOW,
                            grade=fake_grade(calls=calls))
    assert calls == [] and summary.rows[0]["rubric"] == "from_extraction" and summary.reused == 1
    stored = json.loads((out / "tinyq.json").read_text())["scores"]["docs_rubric"]
    assert stored["prompt_version"] == "merged-p1"


def test_the_comparison_tool_only_plans_without_run_and_measures_agreement(capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.compare_rubric import compare, main as compare_main

    assert compare_main(["--mode", "merged"]) == 0  # no --run: no database, no call
    plan = json.loads(capsys.readouterr().out)
    assert plan["records"] == 30 and plan["estimated_usd"] == round(30 * (0.038 + 0.068), 2)
    assert compare_main(["--mode", "prompt", "--new-prompt", "x.txt"]) == 0
    assert json.loads(capsys.readouterr().out)["estimated_usd"] == round(50 * 2 * 0.038, 2)
    low = items(2) | {"what_it_does": {"score": 0, "quote": None}, "prerequisites": {"score": 1, "quote": "q"}}
    result = compare([("a", items(2), items(2)), ("b", items(2), low)])
    assert result["agreement"]["what_it_does"] == 0.5 and result["agreement"]["license_and_platforms"] == 1.0
    assert result["moved_2_points_or_more"] == [{"slug": "b", "before": 16, "after": 13}]
    assert result["mean_abs_install_docs"] == round((0 + 3 / 16) / 2, 4)


# --- the local recompute ----------------------------------------------------------------------------------------------


def test_the_recompute_moves_b3_v6_records_and_writes_only_its_out_dir(tmp_path: Path) -> None:
    from scripts.recompute_scores import main as recompute

    _, out, data = scored(tmp_path)
    before = (out / "tinyq.json").read_text()
    reports = tmp_path / "reports"
    assert recompute(["--data-dir", str(out), "--out", str(reports)]) == 0
    assert (out / "tinyq.json").read_text() == before  # the records are only read
    summary = json.loads((reports / "summary.json").read_text())
    assert summary["records"] == 1 and summary["validation_errors"] == []
    assert set(summary["R9"]) >= {"option_1_no_unchecked", "option_2_keep_unchecked (default)"}
    assert (reports / "changes.md").read_text().startswith("共 ")
    assert recompute(["--data-dir", str(out), "--out", str(reports), "--assume", "vulnerable=exposed"]) == 0


def test_b3_v7_scores_move_to_b3_v8_by_refresh_with_the_new_cadence_and_survival_discount(tmp_path: Path) -> None:
    """b3.v8 (brief 15.4, 15.6) changes only record-derived parts (maintenance cadence from the stored GitHub inputs,
    confidence by standing), so b3.v7 scores move by refresh_scores and what b3.v7 gave is kept in history."""
    assert FORMULA_VERSION == "b3.v8" and "b3.v7" in score_module.REFRESHABLE_FROM
    db_path, out = setup_records(tmp_path)
    score_module.score_records(out, db_path=db_path, model=MODEL, use_github=False, use_registries=False, now=LATER,
                               grade=fake_grade())
    record = json.loads((out / "tinyq.json").read_text())
    current = copy.deepcopy(record["scores"])
    old = {**record["scores"], "formula_version": "b3.v7"}
    moved = {**record, "standing": "new", "scores": old}
    assert refresh_scores(moved, LATER) == "scores moved from formula b3.v7 to b3.v8, refreshed from the record"
    assert moved["scores"]["history"][0]["formula_version"] == "b3.v7"
    assert moved["scores"]["quality"]["total"] == current["quality"]["total"]
    assert moved["scores"]["quality"]["confidence"] == round(
        current["quality"]["confidence"] * score_module.NEW_CONFIDENCE_FACTOR, 2)
    SoftwareRecord.model_validate(moved)
