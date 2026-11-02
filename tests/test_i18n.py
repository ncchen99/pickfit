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


def test_worker_translations_keep_only_sentences_the_index_still_has(tmp_path):
    save(tmp_path, "x", {"Converts files offline.": "離線轉換檔案。", "An old summary.": "舊的摘要。"})
    index = {"entries": [{"slug": "x", "summary": "Converts files offline."}, {"slug": "y", "summary": "Other."}]}
    assert worker_translations(index, tmp_path) == {"x": {"Converts files offline.": "離線轉換檔案。"}}
    assert json.loads((tmp_path / "x.json").read_text())["lang"] == "zh-TW"
