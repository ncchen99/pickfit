"""Usage guides: steps only for a feature the run checked, the record's own features only, the writer recorded."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from pickfit.index import _entry as build_entry
from pickfit.schema import SoftwareRecord
from pickfit.usage_guide import Generated, GuideFeatureOut, GuideOut, best_run, render_input, to_guide, with_guide

FIXTURE = Path(__file__).resolve().parents[1] / "worker" / "test" / "fixtures" / "software" / "fixture-llm-runner.json"
CHECKED, UNCHECKED = "serve an OpenAI-compatible API", "pull models from a registry"


def raw() -> dict:
    return json.loads(FIXTURE.read_text())


def test_fixture_guide_is_valid_and_reaches_the_index():
    record = SoftwareRecord.model_validate(raw())
    assert record.usage_guide is not None and record.usage_guide.model == "fixture-model"
    entry = build_entry(record)
    assert entry["usage_guide"]["features"][0]["title"] == "Serve models over an OpenAI-style API"


def test_steps_for_a_feature_the_run_did_not_check_are_refused():
    data = raw()
    data["usage_guide"]["features"][1]["steps"] = ["Run `fixture-llm-runner pull <model>`."]
    with pytest.raises(ValidationError, match="its run did not check it"):
        SoftwareRecord.model_validate(data)


def test_a_feature_the_record_does_not_list_is_refused():
    data = raw()
    data["usage_guide"]["features"][1]["feature"] = "fly to the moon"
    with pytest.raises(ValidationError, match="the record's features"):
        SoftwareRecord.model_validate(data)


def test_run_id_must_be_a_passed_run():
    data = raw()
    data["usage_guide"]["run_id"] = "run-that-never-happened"
    with pytest.raises(ValidationError, match="not a passed run"):
        SoftwareRecord.model_validate(data)


def test_to_guide_keeps_the_records_features_and_drops_steps_the_run_cannot_back():
    data = raw()
    del data["usage_guide"]
    record = SoftwareRecord.model_validate(data)
    run = best_run(record)
    assert run is not None and run.id == "run-20261028-linux-1"
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
