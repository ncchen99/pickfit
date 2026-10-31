"""Tests for eval/runner/grade.py with fake graders (no model calls)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import grade  # noqa: E402

CONFIG = {"grader_model": "claude-opus-5-5", "grader_effort": "high", "muse_model": "meta-models/muse-spark-open-1026",
          "muse_base_url": "https://x", "caps_usd": {"grading": 20.0, "baseten_grading": 5.0}}


def items(n: int) -> list[dict]:
    return [{"item_id": f"L1-{i:04d}", "question": {"id": "q05", "prompt": "convert pdf", "constraints": {"os": "linux"},
                                                     "l1_checks": ["[L1] exists", "[L1] free"]},
             "pick": {"tool": f"tool-{i}", "install": "pip install x"}} for i in range(n)]


def fake(text: str, out_tokens: int = 100):
    calls = []

    def call(config, system, user):
        calls.append({"system": system, "user": user})
        return {"model": "m", "text": text, "stop_reason": "end_turn", "request_id": "r",
                "usage": {"input_tokens": 1000, "cached_input_tokens": 0, "output_tokens": out_tokens}}
    return call, calls


def test_the_rubric_is_sent_word_for_word_and_nothing_names_a_group(tmp_path: Path) -> None:
    call, calls = fake('{"checks": [], "overall": "pass"}')
    grade.grade_items(items(2), "muse", CONFIG, tmp_path / "g.jsonl", tmp_path / "ledger.json", call, lambda *_: None)
    assert calls[0]["system"] == grade.rubric() and "RUBRIC" not in calls[0]["system"]
    for c in calls:
        low = c["user"].lower()
        assert "pickfit" not in low and "control" not in low and "experimental" not in low
        assert "[L1] free" in c["user"] and "pip install x" in c["user"]


def test_rows_costs_and_resume(tmp_path: Path) -> None:
    call, calls = fake('Here: {"checks": [{"check": "exists", "verdict": "pass", "reason": "repo"}], "overall": "pass"}')
    out, ledger = tmp_path / "g.jsonl", tmp_path / "ledger.json"
    assert grade.grade_items(items(3), "muse", CONFIG, out, ledger, call, lambda *_: None) == 3
    assert grade.grade_items(items(3), "muse", CONFIG, out, ledger, call, lambda *_: None) == 0  # resumable
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [r["overall"] for r in rows] == ["pass"] * 3 and len(calls) == 3
    assert rows[0]["cost_usd"] == pytest.approx((1000 * 1.25 + 100 * 4.25) / 1e6)
    spent = json.loads(ledger.read_text())["spent_usd"]
    assert spent == {"baseten_grading": pytest.approx(3 * rows[0]["cost_usd"])}


def test_a_reply_that_is_not_the_json_shape_is_kept_not_guessed(tmp_path: Path) -> None:
    call, _ = fake("I think it passes.")
    out = tmp_path / "g.jsonl"
    grade.grade_items(items(1), "claude", CONFIG, out, tmp_path / "l.json", call, lambda *_: None)
    row = json.loads(out.read_text())
    assert row["overall"] is None and row["parse_error"].startswith("I think")


def test_stops_before_a_call_that_could_pass_the_cap(tmp_path: Path) -> None:
    call, calls = fake('{"checks": [], "overall": "fail"}', out_tokens=8000)
    tight = dict(CONFIG, caps_usd={"grading": 20.0, "baseten_grading": 0.08})
    with pytest.raises(grade.OverCap):
        grade.grade_items(items(5), "muse", tight, tmp_path / "g.jsonl", tmp_path / "l.json", call, lambda *_: None)
    spent = json.loads((tmp_path / "l.json").read_text())["spent_usd"]["baseten_grading"]
    assert spent <= 0.08 and len(calls) >= 1


def test_agreement_is_descriptive_and_lists_every_disagreement() -> None:
    human = {"a": "pass", "b": "fail", "c": "pass"}
    report = grade.agreement(human, {"claude": {"a": "pass", "b": "pass", "c": "pass"},
                                     "muse": {"a": "pass", "b": "fail"}})
    assert report["items_all_graded"] == 2
    assert report["pairs"]["念誠~claude"] == {"agree": 1, "of": 2, "rate": 0.5}
    assert report["pairs"]["念誠~muse"]["rate"] == 1.0
    assert report["disagreements"] == [{"item_id": "b", "念誠": "fail", "claude": "pass", "muse": "fail"}]
    assert report["not_graded_by"]["muse"] == ["c"]


def test_registered_grader_settings() -> None:
    config = json.loads(grade.CONFIG_PATH.read_text())
    assert config["muse_model"] == "meta-models/muse-spark-open-1026"
    assert config["muse_base_url"] == "https://inference.baseten.co/v1"
    assert config["caps_usd"]["baseten_grading"] == 5.0 and config["caps_usd"]["grading"] == 20.0
