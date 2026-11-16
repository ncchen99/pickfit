"""The nine categories (the hackathon's four and the five subject categories of 2026-11-15) are one list,
and every place that names categories follows it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import get_args

import pytest

from pickfit import webrecords as wr
from pickfit.discover.github import TOPICS, build_queries
from pickfit.discover.showhn import post_categories
from pickfit.discover.store import CATEGORY_PRIORITY
from pickfit.prescreen import INSTRUCTIONS, PrescreenResult
from pickfit.schema import (
    CATEGORY_DESCRIPTION,
    CATEGORY_GUIDE,
    LISTED_CATEGORIES,
    Category,
    ExtractionResult,
    SoftwareRecord,
    meta_strict_schema,
)
from pickfit.score import POPULARITY_REFS, popularity, popularity_refs

NEW = ("infra_devops", "security_net", "data_db", "productivity_docs", "media_files")
ALL = ("dev_cli", "local_ai", "mcp_server", *NEW, "other")
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"


def test_the_category_set_is_the_four_of_the_hackathon_and_five_subjects():
    assert get_args(Category.__value__) == ALL
    assert LISTED_CATEGORIES == ALL[:-1], '"other" is the one category that is not named'
    assert {name for name, _ in CATEGORY_GUIDE} == set(ALL)
    # The order a model tries them in: what it is, then its subject, then the general developer tools.
    order = [name for name, _ in CATEGORY_GUIDE]
    assert order[:2] == ["mcp_server", "local_ai"] and order[2:7] == list(NEW) and order[7:] == ["dev_cli", "other"]


def test_the_models_are_told_every_category_in_the_same_words():
    for name, what in CATEGORY_GUIDE:
        assert f"{name}: {what}" in CATEGORY_DESCRIPTION
        assert f"{name}: {what}" in INSTRUCTIONS, "the prescreen is given the guide extraction is given"
    assert "{category_guide}" not in INSTRUCTIONS
    extraction = meta_strict_schema(ExtractionResult)["properties"]["category"]
    assert extraction["description"] == CATEGORY_DESCRIPTION
    assert extraction["properties"]["value"]["enum"] == [*ALL, None]
    assert meta_strict_schema(PrescreenResult)["properties"]["category"]["enum"] == list(ALL)


@pytest.mark.parametrize("category", NEW)
def test_the_prescreen_and_the_published_schemas_take_a_new_category(category: str):
    screened = PrescreenResult(usable_software=True, kind="cli_tool", category=category, confidence=0.9, reason="r")
    assert screened.category == category
    for name in ("software.v1.json", "extraction.v1.json"):  # the files scripts/export_schema.py writes
        enums = category_enums(json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8")))
        assert enums and all(category in enum for enum in enums), name


def category_enums(node: object) -> list[list[object]]:
    """Every enum in a JSON schema that lists categories (it has dev_cli in it)."""
    if isinstance(node, list):
        return [found for item in node for found in category_enums(item)]
    if not isinstance(node, dict):
        return []
    own = [node["enum"]] if isinstance(node.get("enum"), list) and "dev_cli" in node["enum"] else []
    return own + [found for value in node.values() for found in category_enums(value)]


@pytest.mark.parametrize("category", NEW)
def test_a_record_validates_in_a_new_category(category: str):
    path = SCHEMA_DIR.parent / "worker" / "test" / "fixtures" / "software" / "fixture-json-query.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["category"] = category
    assert SoftwareRecord.model_validate(data).category == category
    data["category"] = "games"
    with pytest.raises(ValueError):
        SoftwareRecord.model_validate(data)


def test_a_category_without_its_own_pool_is_scored_against_dev_clis_references():
    signals = {"stars": 40, "forks": 5, "monthly_downloads": 20000, "release_downloads": 900, "dependents": None,
               "hn_top_score": 0, "registries_count": 1}
    for category in (*NEW, "other"):
        assert category not in POPULARITY_REFS and popularity_refs(category) is POPULARITY_REFS["dev_cli"]
        # A tool that moves out of dev_cli into its subject keeps its popularity, and so its treasure status.
        assert popularity(signals, category, 200) == popularity(signals, "dev_cli", 200)
    assert popularity_refs("mcp_server") is POPULARITY_REFS["mcp_server"]


def test_discovery_has_queries_and_a_priority_for_every_named_category():
    assert set(TOPICS) == set(LISTED_CATEGORIES)
    assert list(TOPICS)[:3] == ["dev_cli", "local_ai", "mcp_server"], "the hackathon's queries keep their order"
    queries = build_queries(__import__("datetime").date(2026, 11, 15), categories=["data_db"])
    assert {q.category for q in queries} == {"data_db"} and "data_db:sqlite+cli" in {q.id for q in queries}
    assert next(q for q in queries if q.id == "data_db:sqlite+cli").q.startswith("topic:sqlite topic:cli ")
    assert CATEGORY_PRIORITY == ("mcp_server", "local_ai", *NEW, "dev_cli")
    # Found by a subject query and a terminal query: the subject is the more specific.
    assert post_categories("Show HN: A TUI for Postgres", "") == ["data_db", "dev_cli"]


def test_the_command_line_takes_the_new_categories():
    from pickfit.cli import _add_pipeline_commands
    from pickfit.verify.cli import add_parser

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    _add_pipeline_commands(sub)
    add_parser(sub)
    assert parser.parse_args(["verify", "--batch", "3", "--category", "security_net"]).category == ["security_net"]
    assert parser.parse_args(["profiles", "--category", "media_files", "--category", "other"]).category == [
        "media_files", "other"]
    assert parser.parse_args(["discover", "--category", "infra_devops"]).category == ["infra_devops"]
    with pytest.raises(SystemExit):
        parser.parse_args(["verify", "--batch", "3", "--category", "other"])  # "other" is never a batch's filter


def test_a_web_app_keeps_any_category_but_mcp_server():
    assert wr.WEB_CATEGORIES == set(ALL) - {"mcp_server"}


def test_the_worker_names_the_same_categories_in_the_same_order():
    """The Worker's list (worker/src/catalog.ts) drives its enum, filters, labels and shelves; a category
    the pipeline writes and the Worker does not know would fail the tool's own schema."""
    import re

    source = (SCHEMA_DIR.parent / "worker" / "src" / "catalog.ts").read_text(encoding="utf-8")
    declared = re.search(r"export const NAMED_CATEGORIES = \[([^\]]*)\] as const;", source)
    assert declared, "worker/src/catalog.ts no longer declares NAMED_CATEGORIES as one literal list"
    assert tuple(re.findall(r"'([a-z_]+)'", declared.group(1))) == LISTED_CATEGORIES
    assert "export const CATEGORIES = [...NAMED_CATEGORIES, 'other'] as const;" in source
