"""zh-TW text for the web page: which sentences of an index entry get translated, and where they live.

data/i18n/zh-TW/<slug>.json holds {"strings": {English: Chinese}} for one tool, written by
scripts/translate_zh.py. The Worker swaps a sentence only when the map has exactly that
English text (worker/src/i18n.ts), so a record that changed shows its new English until
it is translated again. Only prose is collected: never commands, names, URLs, tags or
any value the code compares. The records themselves are never touched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

LANG = "zh-TW"

# Keys whose string values (or lists of strings) are sentences a person reads on the page.
PROSE_KEYS = frozenset({
    "summary", "why_worth_it", "use_cases", "features", "feature", "note", "purpose",
    "manual_steps", "actually_needed", "goal", "observed", "pricing_note", "data_sent_note", "api_keys",
})
CODE = re.compile(r"[a-z0-9_]+")
# Subtrees that hold commands, outputs or ids: never walked (same idea as KEEP in worker/src/i18n.ts).
SKIP_KEYS = frozenset({"checks", "steps_raw", "launch", "client_configs", "smoke_tests", "first_task_setup"})


def i18n_dir(data_dir: Path) -> Path:
    """data/software -> data/i18n/zh-TW (a fixtures directory gets its own sibling)."""
    return data_dir.parent / "i18n" / LANG


def prose(entry: dict[str, Any]) -> list[str]:
    """Every distinct sentence of one index entry the page may show, in a stable order."""
    seen: dict[str, None] = {}

    def add(text: Any) -> None:
        # snake_case codes (needs_gpu, other) are values the page maps to its own words: never prose.
        if isinstance(text, str) and text.strip() and not CODE.fullmatch(text) and not text.startswith(("http://", "https://")):
            seen.setdefault(text, None)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in SKIP_KEYS:
                    continue
                if key in PROSE_KEYS:
                    if isinstance(item, list):
                        for x in item:
                            add(x) if isinstance(x, str) else walk(x)
                    else:
                        add(item)
                        if isinstance(item, (dict, list)):
                            walk(item)
                elif isinstance(item, (dict, list)):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(entry)
    return list(seen)


def load(directory: Path, slug: str) -> dict[str, str]:
    path = directory / f"{slug}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("strings", {})


def save(directory: Path, slug: str, strings: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    body = {"lang": LANG, "slug": slug, "strings": dict(sorted(strings.items()))}
    (directory / f"{slug}.json").write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def worker_translations(index: dict[str, Any], directory: Path) -> dict[str, dict[str, str]]:
    """{slug: {English: Chinese}} for the Worker, only sentences the index still has."""
    out: dict[str, dict[str, str]] = {}
    for entry in index["entries"]:
        known = load(directory, entry["slug"])
        if not known:
            continue
        wanted = {text: known[text] for text in prose(entry) if text in known}
        if wanted:
            out[entry["slug"]] = wanted
    return out
