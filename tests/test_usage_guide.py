"""Usage guides: steps only for a feature a run checked, the record's own features only, the writer recorded,
and a guide that went stale (its run replaced, its features changed) never breaks a write."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from pickfit.index import _entry as build_entry
from pickfit.profiles import _keep_verified_work
from pickfit.schema import SoftwareRecord
from pickfit.usage_guide import (Generated, GuideFeatureOut, GuideOut, best_run, render_input, shown_guide,
                                 to_guide, with_guide)
from pickfit.verify.result import write_back

FIXTURE = Path(__file__).resolve().parents[1] / "worker" / "test" / "fixtures" / "software" / "fixture-llm-runner.json"
CHECKED, UNCHECKED = "serve an OpenAI-compatible API", "pull models from a registry"
RUN = "run-20261028-linux-1"


def raw() -> dict:
    return json.loads(FIXTURE.read_text())


def test_fixture_guide_is_valid_and_reaches_the_index():
    record = SoftwareRecord.model_validate(raw())
    assert record.usage_guide is not None and record.usage_guide.model == "fixture-model"
    entry = build_entry(record)
    assert entry["usage_guide"]["features"][0]["title"] == "Serve models over an OpenAI-style API"
    assert entry["usage_guide"]["features"][0]["steps"]


def test_a_feature_named_twice_is_refused():
    data = raw()
    data["usage_guide"]["features"][1]["feature"] = CHECKED
    with pytest.raises(ValidationError, match="at most once"):
        SoftwareRecord.model_validate(data)


def test_the_page_shows_steps_only_for_a_feature_a_passed_run_checks_and_only_listed_features():
    data = raw()
    data["usage_guide"]["features"][1]["steps"] = ["Run `fixture-llm-runner pull <model>`."]  # its test failed
    data["usage_guide"]["features"].append({"feature": "fly to the moon", "title": "Fly", "steps": ["Go."]})
    shown = shown_guide(SoftwareRecord.model_validate(data))
    assert [(f["feature"], bool(f["steps"])) for f in shown["features"]] == [(CHECKED, True), (UNCHECKED, False)]


def test_a_write_back_that_replaces_the_guides_run_still_writes(tmp_path: Path):
    data = raw()
    (tmp_path / "fixture-llm-runner.json").write_text(json.dumps(data), encoding="utf-8")
    old = next(r for r in SoftwareRecord.model_validate(data).verification.runs if r.id == RUN)
    # The same (os, arch, method) passes again under a new id, and this time the feature is not checked.
    features = [f.model_copy(update={"status": "not_checked", "reason": "not_attempted", "failure": None, "smoke_tests": []})
                if f.feature == CHECKED else f for f in old.features]
    new = old.model_copy(update={"id": "run-20261103-linux-9", "features": features})
    written, why = write_back(new, "fixture-llm-runner", tmp_path)
    assert written, why
    record = SoftwareRecord.model_validate_json((tmp_path / "fixture-llm-runner.json").read_text(encoding="utf-8"))
    assert record.usage_guide is not None and record.usage_guide.run_id == RUN  # kept as written, now stale
    shown = shown_guide(record)
    assert all(not f["steps"] for f in shown["features"]), "no run checks the feature any more"


def test_new_features_leave_the_guide_valid_and_drop_what_went():
    data = raw()
    data["features"] = [CHECKED, "run models on a GPU"]  # a features-only extraction replaced the list
    record = SoftwareRecord.model_validate(data)
    assert [f["feature"] for f in shown_guide(record)["features"]] == [CHECKED]


def test_a_rebuilt_record_keeps_its_guide():
    existing = raw()
    rebuilt = {k: v for k, v in existing.items() if k not in ("usage_guide", "verification", "scores")}
    rebuilt.update(install={}, sources=list(existing["sources"]), evidence=[])
    _keep_verified_work(rebuilt, existing)
    assert rebuilt["usage_guide"] == existing["usage_guide"]


def test_to_guide_keeps_the_records_features_and_drops_steps_the_run_cannot_back():
    data = raw()
    del data["usage_guide"]
    record = SoftwareRecord.model_validate(data)
    run = best_run(record)
    assert run is not None and run.id == RUN
    out = GuideOut(open_hint="  Run `fixture-llm-runner serve`.  ", features=[
        GuideFeatureOut(feature=CHECKED, title="Serve models", steps=["Run `fixture-llm-runner serve`.", " "]),
        GuideFeatureOut(feature=UNCHECKED, title="Download models", steps=["Made up."]),
        GuideFeatureOut(feature="not in the record", title="Invented", steps=["Nope."]),
    ])
    guide = to_guide(record, run, Generated(out, "some-model", 0.01), datetime(2026, 11, 2, tzinfo=timezone.utc))
    assert guide["model"] == "some-model" and guide["run_id"] == run.id
    assert guide["open_hint"] == "Run `fixture-llm-runner serve`."
    assert [(f["feature"], f["steps"]) for f in guide["features"]] == [
        (CHECKED, ["Run `fixture-llm-runner serve`."]), (UNCHECKED, [])]
    text = with_guide(data, guide)
    keys = list(json.loads(text))
    assert keys.index("usage_guide") == keys.index("why_worth_it") + 1
    assert "CHECKED" in render_input(record, run) and f"- {UNCHECKED}: not checked" in render_input(record, run)
