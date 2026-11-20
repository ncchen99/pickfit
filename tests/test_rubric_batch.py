"""pickfit score-batch: the docs rubric graded through a Message Batch (pickfit/rubric_batch.py), 11/20."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_profiles import MODEL
from test_score import LATER, items, setup_records

from pickfit import msg_batch, rubric_batch, score
from pickfit.meta import MetaResult
from pickfit.schema import DocsRubricItems, SoftwareRecord


@pytest.fixture(autouse=True)
def _no_live_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "MODEL_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def answer(points: int = 2) -> MetaResult:
    return MetaResult(provider="anthropic", model=MODEL, endpoint="responses", text=json.dumps(items(points)),
                      tool_calls=[], output_items=[], usage=None, cost_usd=0.02, response_id="r",
                      status="completed", reasoning_summary=None, cache_hit=False, attempts=1, request_hash="h",
                      raw={}, parsed=DocsRubricItems.model_validate(items(points)))


def no_model_call(*_: Any, **__: Any) -> Any:
    raise AssertionError("score-batch must not make a plain rubric call")


def answered(requests: Any, **_: Any) -> dict[str, msg_batch.BatchOutcome]:
    return {r.key: msg_batch.BatchOutcome(key=r.key, result=answer()) for r in requests}


def test_the_rubric_goes_in_one_batch_and_the_record_is_written_from_its_answer(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, out = setup_records(tmp_path)
    monkeypatch.setattr(score, "grade_docs", no_model_call)
    monkeypatch.setattr(score, "call_meta", no_model_call, raising=False)
    sent: list[list[msg_batch.BatchRequest]] = []

    def fake_run(requests, **kwargs):
        requests = list(requests)
        sent.append(requests)
        return answered(requests)

    monkeypatch.setattr(msg_batch, "run", fake_run)
    result = rubric_batch.score_with_batch(out, db_path=db_path, model=MODEL, now=LATER, use_github=False,
                                           use_registries=False)
    assert [r.key for r in sent[0]] == ["score:tinyq"]
    req = sent[0][0]
    assert (req.stage, req.endpoint, req.output_model) == ("score-rubric", "responses", DocsRubricItems)
    assert req.body == score.rubric_body(result.collected["score:tinyq"].sources)  # the plain call's request
    scores = SoftwareRecord.model_validate_json((out / "tinyq.json").read_text(encoding="utf-8")).scores
    assert scores.docs_rubric is not None and scores.docs_rubric.model == MODEL
    summary = result.to_dict()
    assert summary["rubrics_batched"] == 1 and summary["second_pass"]["written"] == 1
    assert summary["first_pass"]["errors"] == {}  # the deferral is not reported as an error
    assert summary["batch"] == {"answered": 1, "via": {"batch": 1}, "cost_usd": 0.02}


def test_a_dry_run_collects_and_sends_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, out = setup_records(tmp_path)
    before = (out / "tinyq.json").read_bytes()
    monkeypatch.setattr(msg_batch, "run", no_model_call)
    result = rubric_batch.score_with_batch(out, db_path=db_path, model=MODEL, now=LATER, use_github=False,
                                           use_registries=False, dry_run=True)
    assert list(result.collected) == ["score:tinyq"] and result.outcomes == {}
    assert result.to_dict()["estimated_batch_usd"] == round(rubric_batch.MEAN_RUBRIC_USD / 2, 2)
    assert (out / "tinyq.json").read_bytes() == before


def test_an_unanswered_request_leaves_the_record_as_it_was(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, out = setup_records(tmp_path)
    before = (out / "tinyq.json").read_bytes()
    monkeypatch.setattr(msg_batch, "run", lambda requests, **_: {
        r.key: msg_batch.BatchOutcome(key=r.key, error="expired", via="none") for r in requests})
    result = rubric_batch.score_with_batch(out, db_path=db_path, model=MODEL, now=LATER, use_github=False,
                                           use_registries=False)
    assert result.to_dict()["second_pass"]["errors"] == {"tinyq": "expired"}
    assert (out / "tinyq.json").read_bytes() == before  # no rubric before, none now: nothing to score it with


def test_a_record_that_needs_no_new_rubric_is_scored_in_the_first_pass(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, out = setup_records(tmp_path)
    monkeypatch.setattr(msg_batch, "run", answered)
    rubric_batch.score_with_batch(out, db_path=db_path, model=MODEL, now=LATER, use_github=False,
                                  use_registries=False)
    monkeypatch.setattr(msg_batch, "run", no_model_call)  # the README has not changed: the rubric is reused
    again = rubric_batch.score_with_batch(out, db_path=db_path, model=MODEL, now=LATER, use_github=False,
                                          use_registries=False)
    assert again.collected == {} and again.second is None


def test_the_command_is_registered() -> None:
    from pickfit.cli import main

    with pytest.raises(SystemExit) as exit_:
        main(["score-batch", "--help"])
    assert exit_.value.code == 0
