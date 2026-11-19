"""pickfit.translate and the publish step: only missing sentences are asked for, answers land per tool,
and a failed translation never stops a deploy."""

import json

import pytest

import pickfit.publish as publish_mod
import pickfit.translate as translate
from pickfit.i18n import load, save
from pickfit.ledger import Ledger
from batch_fakes import FakeBatches, fake_client, succeeded, user_text


ENTRIES = [
    {"slug": "a", "summary": "Converts files offline.", "use_cases": ["convert a file"]},
    {"slug": "b", "summary": "Plays music.", "use_cases": []},
]


def test_missing_skips_known_sentences_unless_retranslating(tmp_path):
    save(tmp_path, "a", {"Converts files offline.": "離線轉換檔案。"})
    known, todo = translate.missing(ENTRIES, tmp_path)
    assert todo == [("a", "convert a file"), ("b", "Plays music.")]
    assert known["a"] == {"Converts files offline.": "離線轉換檔案。"}
    _, again = translate.missing(ENTRIES, tmp_path, retranslate=True)
    assert len(again) == 3


def test_batches_keep_to_the_character_limit():
    todo = [("a", "x" * 30), ("a", "y" * 30), ("b", "z" * 30)]
    assert [len(g) for g in translate.batches(todo, 60)] == [2, 1]


def test_run_saves_answers_and_counts_failures(tmp_path, monkeypatch):
    def fake(batch, run_id, max_usd, effort, model):
        assert (model, effort) == ("claude", "low")  # the defaults: Claude Opus at the effort it was measured at
        if batch[0][0] == "b":
            raise RuntimeError("model down")
        return {i: f"中文{i}" for i in range(len(batch))}, 0.01

    monkeypatch.setattr(translate, "translate_batch", fake)
    known, todo = translate.missing(ENTRIES, tmp_path)
    groups = [[p for p in todo if p[0] == "a"], [p for p in todo if p[0] == "b"]]
    totals = translate.run(groups, known, tmp_path, concurrency=1, out=lambda _: None)
    assert (totals.sentences, totals.requests, totals.failed) == (2, 1, 1)
    assert load(tmp_path, "a") == {"Converts files offline.": "中文0", "convert a file": "中文1"}
    assert load(tmp_path, "b") == {}


def test_answers_drop_out_of_range_and_empty_items():
    text = json.dumps({"items": [{"i": 0, "zh": " 好 "}, {"i": 5, "zh": "多"}, {"i": 1, "zh": "  "}]})
    assert translate.answers(text, 2) == {0: "好"}


def test_publish_translation_never_raises(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no credits")

    monkeypatch.setattr(translate, "run", boom)
    lines: list[str] = []
    data = tmp_path / "software"
    data.mkdir()
    publish_mod.translate_new({"entries": ENTRIES}, data, dry_run=False, out=lines.append)
    assert any("skipped (RuntimeError: no credits)" in line for line in lines)
    publish_mod.translate_new({"entries": ENTRIES}, data, dry_run=True, out=lines.append)
    assert lines[-1] == "publish: dry run; would translate 3 sentence(s) of 2 tool(s) into zh-TW"


def test_a_batch_run_sends_every_request_at_once_and_saves_what_came_back(tmp_path):
    def answer(params):
        said = json.loads(user_text(params).split("\n\n", 1)[1])
        if said[0]["tool"] == "b":
            return {"type": "errored", "error": {"type": "error", "error": {"type": "invalid_request_error"}}}
        return succeeded(json.dumps({"items": [{"i": item["i"], "zh": f"中文{item['i']}"} for item in said]}))

    batches = FakeBatches(answer)
    known, todo = translate.missing(ENTRIES, tmp_path)
    groups = [[p for p in todo if p[0] == "a"], [p for p in todo if p[0] == "b"]]
    options = {"client": fake_client(batches), "ledger": Ledger(tmp_path / "l.sqlite"), "sleep": lambda s: None,
               "resend": False}
    totals = translate.run(groups, known, tmp_path, out=lambda _: None, batch=True, batch_options=options)
    assert len(batches.created) == 1 and len(batches.created[0]) == 2  # one batch for both requests
    params = batches.created[0][0]["params"]
    assert params["model"] == "claude-opus-5-5" and params["output_config"]["effort"] == "low"
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert (totals.sentences, totals.requests, totals.failed) == (2, 1, 1)
    assert load(tmp_path, "a") == {"Converts files offline.": "中文0", "convert a file": "中文1"}
    assert load(tmp_path, "b") == {}


def test_only_claude_requests_go_in_a_batch(tmp_path):
    with pytest.raises(ValueError, match="message batch"):
        translate.run([], {}, tmp_path, model="open-modal", batch=True)
