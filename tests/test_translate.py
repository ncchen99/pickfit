"""pickfit.translate and the publish step: only missing sentences are asked for, answers land per tool,
and a failed translation never stops a deploy."""

import json

import pickfit.publish as publish_mod
import pickfit.translate as translate
from pickfit.i18n import load, save


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
    def fake(batch, run_id, max_usd, effort):
        if batch[0][0] == "b":
            raise RuntimeError("model down")
        return {i: f"中文{i}" for i in range(len(batch))}, 0.01

    monkeypatch.setattr(translate, "translate_open", fake)
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
