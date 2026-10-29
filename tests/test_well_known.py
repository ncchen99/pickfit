"""Reference records for well-known tools: the selection rule, the record flag, never a treasure."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from pickfit.discover.store import PipelineDB
from pickfit.discover.well_known import ANALYTICS_URL, BASIS, evidence, github_repo, listing, ranked_pool
from pickfit.index import build_index
from pickfit.schema import SoftwareRecord
from pickfit.score import treasure

EXAMPLE = Path(__file__).parent / "fixtures" / "software_example.json"
WORKER_FIXTURES = Path(__file__).resolve().parent.parent / "worker" / "test" / "fixtures" / "software"

ANALYTICS = {
    "start_date": "2025-10-29",
    "end_date": "2026-10-29",
    "items": [
        {"number": 1, "formula": "gh", "count": "3,066,867"},
        {"number": 2, "formula": "someone/tap/opencode", "count": "671,740"},  # a tap
        {"number": 3, "formula": "whisper-cpp", "count": "85,607"},  # counted under an old name
        {"number": 4, "formula": "gnu-sed", "count": "50,000"},  # not on GitHub
        {"number": 5, "formula": "gh@2", "count": "40,000"},  # the same repo as gh
        {"number": 6, "formula": "ollama", "count": "35,000"},
    ],
}


def _formula(name: str, stable: str, **extra) -> dict:
    return {"name": name, "aliases": [], "oldnames": [], "urls": {"stable": {"url": stable}}, "homepage": None,
            "license": "MIT", "desc": f"{name} desc", **extra}


FORMULAE = [
    _formula("gh", "https://github.com/cli/cli/archive/refs/tags/v2.83.0.tar.gz", homepage="https://cli.github.com/"),
    _formula("whisper.cpp", "https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v1.8.2.tar.gz",
             oldnames=["whisper-cpp"]),
    _formula("gnu-sed", "https://ftp.gnu.org/gnu/sed/sed-4.9.tar.xz", homepage="https://www.gnu.org/software/sed/"),
    _formula("gh@2", "https://ftp.example.org/gh-2.tar.gz", urls={"stable": {"url": "https://ftp.example.org/x"},
                                                                    "head": {"url": "https://github.com/cli/cli.git"}}),
    _formula("ollama", "https://github.com/ollama/ollama.git"),
]


def test_github_repo_from_stable_head_or_homepage():
    assert github_repo(FORMULAE[0]) == "cli/cli"
    assert github_repo(FORMULAE[3]) == "cli/cli"  # head URL, .git dropped
    assert github_repo({"urls": {}, "homepage": "https://github.com/jqlang/jq"}) == "jqlang/jq"
    assert github_repo(FORMULAE[2]) is None


def test_ranked_pool_keeps_analytics_ranks_and_one_row_per_repo():
    pool = ranked_pool(ANALYTICS, FORMULAE, max_rank=5)
    assert [(r["rank"], r["formula"], r["repo"], r["count"]) for r in pool] == [
        (1, "gh", "cli/cli", 3066867),
        (3, "whisper.cpp", "ggml-org/whisper.cpp", 85607),  # rank 2 is a tap, rank 4 not on GitHub
    ]
    assert [r["formula"] for r in ranked_pool(ANALYTICS, FORMULAE, max_rank=6)][-1] == "ollama"


def _well_known(rank: int = 23) -> dict:
    row = {"formula": "ollama", "rank": rank, "count": 655153}
    return evidence(row, ANALYTICS, 1000, "2026-10-29T09:00:00Z")


def _reference(example: dict) -> dict:
    """The example record (a treasure by its scores) as a well-known reference record."""
    doc = copy.deepcopy(example)
    doc["well_known"] = _well_known()
    doc["scores"]["treasure"] = treasure(doc["scores"]["quality"]["total"], doc["scores"]["popularity"]["score"], True)
    return doc


@pytest.fixture
def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_reference_record_validates_and_is_never_a_treasure(example):
    assert example["scores"]["treasure"]["is_treasure"] is True  # quality 81, popularity 14
    doc = _reference(example)
    assert doc["scores"]["treasure"] == {"is_treasure": False, "value": 69.71, "excluded": "well_known"}
    record = SoftwareRecord.model_validate(doc)
    assert record.well_known.basis == BASIS
    assert record.well_known.source_url == ANALYTICS_URL
    assert record.model_dump(mode="json") == doc
    # Long-tail records keep their shape: no well_known or excluded keys at all.
    assert "well_known" not in SoftwareRecord.model_validate(example).model_dump(mode="json")


@pytest.mark.parametrize("mutate", [
    lambda d: d["scores"]["treasure"].pop("excluded"),  # flagged but not excluded
    lambda d: d.pop("well_known"),  # excluded but not flagged
    lambda d: d["scores"]["treasure"].update(is_treasure=True),  # excluded yet a treasure
    lambda d: d["well_known"].update(rank=1001),  # beyond its own threshold
    lambda d: d["well_known"].update(package="homebrew:Some Tap/x"),
])
def test_inconsistent_reference_records_are_rejected(example, mutate):
    doc = _reference(example)
    mutate(doc)
    with pytest.raises(ValidationError):
        SoftwareRecord.model_validate(doc)


def test_store_keeps_evidence_and_lists_by_rank(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    for repo_id, name, rank in ((7, "ggml-org/llama.cpp", 72), (8, "ollama/ollama", 23)):
        db.upsert_repo({"id": repo_id, "full_name": name, "owner": name.split("/")[0]}, category="well_known",
                       query_id="well_known:homebrew")
        db.save_well_known(f"gh:{repo_id}", _well_known(rank) | {"package": f"homebrew:{name.split('/')[1]}"})
    rows = listing(db)
    assert [(r["rank"], r["full_name"]) for r in rows] == [(23, "ollama/ollama"), (72, "ggml-org/llama.cpp")]
    assert rows[0]["screen_category"] is None and rows[0]["extracted_category"] is None


def test_index_entry_carries_the_flag(tmp_path):
    data_dir = tmp_path / "software"
    shutil.copytree(WORKER_FIXTURES, data_dir)
    path = data_dir / "fixture-llm-runner.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["well_known"] = _well_known()
    doc["scores"]["treasure"] = treasure(doc["scores"]["quality"]["total"], doc["scores"]["popularity"]["score"], True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    entries = {e["slug"]: e for e in build_index(data_dir).index["entries"]}
    assert entries["fixture-llm-runner"]["well_known"] == {
        "package": "homebrew:ollama", "rank": 23, "count": 655153, "period_end": "2026-10-29"}
    assert entries["fixture-llm-runner"]["scores"]["treasure"] is False
    assert entries["fixture-json-query"]["well_known"] is None
