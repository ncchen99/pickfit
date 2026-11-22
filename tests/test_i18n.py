"""pickfit.i18n: which sentences the web page's zh-TW file may hold, and what write_index puts beside the index."""

import json

from pickfit.i18n import prose, save, worker_translations


def test_prose_takes_sentences_and_skips_commands_names_and_codes():
    entry = {
        "slug": "x",
        "name": "X Tool",
        "summary": "Converts files offline.",
        "use_cases": ["convert a file"],
        "install": {"linux": {
            "steps": [{"command": "pipx install x", "purpose": "Install it with pipx"}],
            "manual_steps": ["Open the settings"],
            "first_task": "x --help",
            "features": [{"feature": "batch convert", "reason": "needs_gpu", "note": None,
                          "checks": [{"command": "x a b", "passed": True}]}],
            "pitfalls": [{"readme_said": "pip install x", "actually_needed": "use pipx instead", "kind": "note"}],
        }},
        "homepage": "https://example.com",
        "tags": ["cli"],
    }
    assert prose(entry) == [
        "Converts files offline.", "convert a file", "Install it with pipx", "Open the settings", "batch convert",
        "use pipx instead",
    ]


def test_a_features_fidelity_is_a_code_the_page_words_itself_never_a_sentence_to_translate():
    entry = {"install": {"linux": {"features": [
        {"feature": "send mail over SMTP", "status": "checked", "reason": None, "note": None, "fidelity": "stand_in",
         "checks": [{"command": "x send", "passed": True}]}]}},
        "coverage": {"dimensions": {"function": {"status": "verified", "done": 1, "of": 1, "stand_in": 1}}}}
    assert prose(entry) == ["send mail over SMTP"]


def test_a_video_s_captions_and_chapter_titles_are_translated_like_the_page_s_sentences():
    video = {"clip": "x-20261119-1000.mp4", "raw": [{"file": "x-20261119-1000-raw-1.mp4", "sha256": "a" * 64}],
             "features": ["write a note"],
             "chapters": [{"start_s": 0.0, "title": "Write a note", "feature": "write a note", "raw": 0, "raw_s": 1.5}],
             "captions": [{"start_s": 0.0, "end_s": 2.0, "text": "Start Notes"},
                          {"start_s": 2.0, "end_s": 5.5, "text": 'Click “New”, then type "hello"'}]}
    entry = {"slug": "x", "install": {"linux": {"run": {"video": video}}}}
    assert prose(entry) == ["write a note", "Write a note", "Start Notes", 'Click “New”, then type "hello"']


def test_worker_translations_keep_only_sentences_the_index_still_has(tmp_path):
    save(tmp_path, "x", {"Converts files offline.": "離線轉換檔案。", "An old summary.": "舊的摘要。"})
    index = {"entries": [{"slug": "x", "summary": "Converts files offline."}, {"slug": "y", "summary": "Other."}]}
    assert worker_translations(index, tmp_path) == {"x": {"Converts files offline.": "離線轉換檔案。"}}
    assert json.loads((tmp_path / "x.json").read_text())["lang"] == "zh-TW"


def test_a_capabilitys_label_is_prose_and_its_items_are_not():
    entry = {"slug": "x", "capabilities": [{"label": "convert JSON to other formats", "items": ["csv", "YAML 1.2"]}]}
    assert prose(entry) == ["convert JSON to other formats"]
