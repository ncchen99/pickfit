"""scripts/guarded_write_back.py: a run is written only when the record loses nothing."""

from __future__ import annotations

import json
from pathlib import Path

from pickfit.schema import SoftwareRecord, VerificationRun
from scripts.guarded_write_back import why_not

FIXTURES = Path(__file__).parent / "fixtures"


def record() -> SoftwareRecord:
    return SoftwareRecord.model_validate_json((FIXTURES / "software_example.json").read_text(encoding="utf-8"))


def feature(name: str, checked: bool, test: int = 0) -> dict:
    return ({"feature": name, "status": "checked", "smoke_tests": [test]} if checked else
            {"feature": name, "status": "not_checked", "smoke_tests": [], "reason": "needs_gpu"})


def run_like(base: VerificationRun, **update) -> VerificationRun:
    data = json.loads(base.model_dump_json())
    data.update(update)
    return VerificationRun.model_validate(data)


def test_a_run_that_keeps_every_checked_feature_and_the_level_is_written():
    rec = record()
    old = rec.verification.runs[0]
    with_features = run_like(old, features=[feature("A", True), feature("B", False)])
    rec.verification.runs[0] = with_features
    assert why_not(run_like(old, features=[feature("A", True), feature("B", True)]), rec) is None
    assert "checked 1 feature(s) this one does not: A" in why_not(run_like(old, features=[feature("B", True)]), rec)
    assert "weaker" in why_not(run_like(old, level="install", features=[feature("A", True)]), rec)
    assert "unverified" in why_not(run_like(old, level="unverified", unverified_reason="needs_gpu", steps=[],
                                            smoke_tests=[], features=[], replayed=False), rec)


def test_a_run_on_another_os_never_competes():
    rec = record()
    other = run_like(rec.verification.runs[0], os="macos", arch="arm64")
    assert why_not(other, rec) is None


def test_a_feature_set_aside_for_the_box_keeps_that_reason():
    rec = record()
    old = rec.verification.runs[0]
    rec.verification.runs[0] = run_like(old, features=[feature("A", False)])  # needs_gpu
    vague = {"feature": "A", "status": "not_checked", "smoke_tests": [], "reason": "other"}
    assert "would lose its reason" in why_not(run_like(old, features=[vague]), rec)
    assert why_not(run_like(old, features=[feature("A", False)]), rec) is None
