"""A run's grants and each feature's fidelity in the record (loop/proposals/privileges-schema.patch)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from pickfit import schema
from pickfit.schema import FeatureCheck, Fidelity, Grant, GrantKind, SoftwareRecord, VerificationRun
from pickfit.verify import grants as grants_mod
from pickfit.verify import result as result_mod
from pickfit.verify.grants import Ask, Provided, Providers
from pickfit.verify.result import install_guide, saved_grants
from test_verify_grants import (  # noqa: F401 (isolated: the same fixture, for this module's tests)
    FEATURES,
    Boxes,
    Packages,
    bare_record,
    graphtty,
    isolated,
    judge_answer,
    request,
    verify,
    work,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_the_record_and_the_harness_name_the_same_kinds_and_fidelities():
    assert get_args(GrantKind.__value__) == grants_mod.KINDS
    assert set(get_args(Fidelity.__value__)) == set(grants_mod.FIDELITIES)
    assert schema.GRANTS_MAX == result_mod.GRANTS_MAX
    assert result_mod._HAS_GRANTS and result_mod._HAS_FIDELITY
    name = Grant.model_fields["name"].metadata[0].pattern
    assert name == grants_mod.NAME.pattern  # what the desk accepts is what a record can hold


def endpoint(box: Any, ask: Ask) -> Provided:
    return Provided(True, "OPENAI_BASE_URL=http://127.0.0.1:8090/v1", markers=("127.0.0.1:8090",))


def test_a_run_records_what_it_was_given_and_what_each_feature_was_checked_against(tmp_path: Path):
    features = [{"feature": 1, "status": "checked", "command_ids": [4], "reason": None, "failure": None, "note": ""},
                {"feature": 2, "status": "not_checked", "command_ids": [], "reason": "needs_root", "failure": None,
                 "note": "fonts need sudo"}]
    feature_judge = judge_answer({"features": [{"number": 1, "verdict": "shows_it_working", "why": "an arrow"}]})
    path = bare_record(tmp_path / "data")
    replies = [*work(request("system_package", "libxcb1"), request("model_endpoint", "stand-in"),
                     request("root", "sudo"), features=features), judge_answer(), feature_judge]
    providers = Providers({"system_package": Packages(), "model_endpoint": endpoint})
    outcome, _, _ = verify(tmp_path, replies, Boxes(services=True), task=graphtty(FEATURES), providers=providers,
                           write=True, data_dir=path.parent)
    run = outcome.run
    assert outcome.passed and outcome.written
    assert [g.model_dump() for g in run.grants] == [
        {"kind": "system_package", "name": "libxcb1", "tier": 2, "requested_by": "agent", "shown_in_guide": True},
        {"kind": "model_endpoint", "name": "stand-in", "tier": 3, "requested_by": "agent", "shown_in_guide": True}]
    by_name = {f.feature: f for f in run.features}
    assert by_name["render a graph as ASCII art"].fidelity == "stand_in"  # checked, but against a stand-in
    assert (by_name["export to SVG"].reason, by_name["export to SVG"].fidelity) == ("needs_root", None)
    # Round trip: the run's own file, then the record.
    saved = VerificationRun.model_validate_json(
        (outcome.evidence_dir / "verification_run.json").read_text(encoding="utf-8"))
    assert saved == run and saved.grants == run.grants
    record = SoftwareRecord.model_validate_json(path.read_text(encoding="utf-8"))
    kept = record.verification.runs[0]
    assert kept.grants == run.grants and {f.feature: f.fidelity for f in kept.features} == {
        "render a graph as ASCII art": "stand_in", "export to SVG": None}
    assert record.install.linux.manual_steps[0] == "sudo apt-get install -y libxcb1"
    # With only the record at hand, the guide's lines come from the five fields and the policy table.
    assert [(g.kind, g.name) for g in saved_grants(kept)] == [("system_package", "libxcb1"),
                                                             ("model_endpoint", "stand-in")]
    assert install_guide(kept).manual_steps[0] == "First, as an administrator: sudo apt-get install -y libxcb1"


def test_old_records_load_with_no_grants_and_are_written_back_unchanged():
    text = (FIXTURES / "software_example.json").read_text(encoding="utf-8")
    record = SoftwareRecord.model_validate_json(text)
    assert all(run.grants == [] for run in record.verification.runs)
    assert all(f.fidelity is None for run in record.verification.runs for f in run.features)
    dumped = record.model_dump(mode="json")
    assert dumped == json.loads(text)  # no migration: neither field is written until a run has one
    assert "grants" not in json.dumps(dumped) and "fidelity" not in json.dumps(dumped)


def test_what_a_record_refuses():
    grant = {"kind": "system_package", "name": "libxcb1", "tier": 2, "requested_by": "agent", "shown_in_guide": True}
    Grant.model_validate(grant)
    for change in ({"kind": "kernel_module"}, {"tier": 6}, {"tier": 0}, {"requested_by": "readme"},
                   {"name": "libxcb1; rm -rf ~"}, {"name": ""}):
        with pytest.raises(ValidationError):
            Grant.model_validate({**grant, **change})
    with pytest.raises(ValidationError, match="no fidelity"):
        FeatureCheck(feature="export to SVG", status="not_checked", reason="needs_root", fidelity="stand_in")
    with pytest.raises(ValidationError):
        FeatureCheck(feature="export to SVG", status="checked", smoke_tests=[0], fidelity="verified")
    run = json.loads((FIXTURES / "software_example.json").read_text(encoding="utf-8"))["verification"]["runs"][0]
    VerificationRun.model_validate({**run, "grants": [grant]})
    with pytest.raises(ValidationError, match="each grant once"):
        VerificationRun.model_validate({**run, "grants": [grant, grant]})
