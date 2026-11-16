"""`pickfit discover --repo`: a named repository goes into the pipeline database without a search (H-001).

A record written on another machine has no candidate and no extraction in this machine's database, so
`pickfit verify --batch --repo` finds nothing to verify. Adding the repository by name (GitHub facts, README,
files, the rule label; no model call) and extracting it makes the record selectable again.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from pickfit.cli import main
from pickfit.discover.run import add_repos
from pickfit.discover.store import PipelineDB
from pickfit.verify.batch import load_candidates, record_categories, record_slugs
from queue_fakes import EXAMPLE, FakeGitHub, repo_item

FIXTURES = Path(__file__).parent / "fixtures" / "verify"
FULL_NAME = EXAMPLE["repo"]["full_name"]
REPO_ID = int(EXAMPLE["repo_id"].removeprefix("gh:"))
README = "# frobtail\n\n## Install\n\n```sh\npipx install frobtail\n```\n\n## Usage\n\nfrobtail app.jsonl --level warn\n"
DETAILS = {"readme": README, "readme_path": "README.md", "releases": [], "files": ["frobtail/cli.py"],
           "files_truncated": False, "manifests": {}}


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    path = tmp_path / "software"
    path.mkdir()
    record = {**copy.deepcopy(EXAMPLE), "category": "local_ai"}  # not the category a search would have given
    (path / "frobtail.json").write_text(json.dumps(record), encoding="utf-8")
    return path


def github(**repos: dict[str, Any]) -> FakeGitHub:
    repos = repos or {FULL_NAME: repo_item(REPO_ID, FULL_NAME)}
    return FakeGitHub(repos, {name: DETAILS for name in repos})


def extract(db: PipelineDB, repo_id: str) -> None:
    """What `pickfit extract --repo` stores, without the model call."""
    result = json.loads((FIXTURES / "graphtty.json").read_text(encoding="utf-8"))["extraction"]
    db.save_extraction(repo_id=repo_id, run_id="x", model="muse-spark-1.3", reasoning_effort="minimal", status="ok",
                       sources_sha="s", result=result, quote_failures=[], quotes_checked=0, error=None, usage=None,
                       cost_usd=0.0, cache_hit=False, response_id=None, latency_s=None)


def select(db_path: Path, data_dir: Path, repo: str) -> list[str]:
    items, _ = load_candidates(db_path, limit=5, repos=[repo], known_slugs=record_slugs(data_dir),
                               known_categories=record_categories(data_dir))
    return [f"{item.task.slug}:{item.category}" for item in items]


def test_a_record_from_another_machine_is_selectable_once_its_repository_is_added(tmp_path: Path, data_dir: Path):
    db_path = tmp_path / "pipeline.db"
    db = PipelineDB(db_path)
    assert select(db_path, data_dir, FULL_NAME) == []  # H-001: the batch has nothing to verify

    rows = add_repos(github(), db, [FULL_NAME], data_dir=data_dir)

    assert rows == [{"name": FULL_NAME, "outcome": "added", "repo_id": EXAMPLE["repo_id"], "full_name": FULL_NAME,
                     "record": "frobtail", "category": "local_ai", "rule_label": "tool", "rule_passed": True}]
    candidate = db.candidate(EXAMPLE["repo_id"])
    assert candidate["readme"] == README and candidate["files"] == ["frobtail/cli.py"]
    assert candidate["category"] == "local_ai"  # the record's own category, as the batch reads it
    assert select(db_path, data_dir, FULL_NAME) == []  # still nothing: it has not been extracted
    extract(db, EXAMPLE["repo_id"])
    assert select(db_path, data_dir, FULL_NAME) == ["frobtail:local_ai"]
    assert select(db_path, data_dir, EXAMPLE["repo_id"]) == ["frobtail:local_ai"]


def test_a_url_names_a_repository_and_one_without_a_record_is_other(tmp_path: Path, data_dir: Path):
    db = PipelineDB(tmp_path / "pipeline.db")
    gh = github(**{"acme/newtool": repo_item(77, "acme/newtool")})
    rows = add_repos(gh, db, ["https://github.com/acme/newtool/", "not a repository"], data_dir=data_dir)
    assert [(r["name"], r["outcome"]) for r in rows] == [("https://github.com/acme/newtool/", "added"),
                                                         ("not a repository", "not_a_repository")]
    assert rows[0]["full_name"] == "acme/newtool" and rows[0]["record"] is None and rows[0]["category"] == "other"
    assert gh.calls == ["repo acme/newtool", "details acme/newtool"]
    assert db.candidate("gh:77")["rule_passed"] is True


def test_a_repository_that_is_gone_or_replaced_is_not_added(tmp_path: Path, data_dir: Path):
    db = PipelineDB(tmp_path / "pipeline.db")
    # The record's name now answers with another repository's id: a deleted repo whose name was taken.
    gh = github(**{FULL_NAME: repo_item(555, FULL_NAME)})
    rows = add_repos(gh, db, [FULL_NAME, "acme/gone"], data_dir=data_dir)
    assert [(r["name"], r["outcome"]) for r in rows] == [(FULL_NAME, "another_repository"), ("acme/gone", "not_found")]
    assert rows[0]["record"] == "frobtail" and rows[0]["repo_id"] == "gh:555"
    assert db.candidates() == [] and "details" not in " ".join(gh.calls)


def test_a_renamed_repository_keeps_its_record_and_adding_again_refreshes(tmp_path: Path, data_dir: Path):
    db = PipelineDB(tmp_path / "pipeline.db")
    renamed = repo_item(REPO_ID, "example/frobtail-ng")  # GitHub follows the old name to the new one
    gh = FakeGitHub({FULL_NAME: renamed}, {"example/frobtail-ng": DETAILS})
    first = add_repos(gh, db, [FULL_NAME], data_dir=data_dir)
    assert (first[0]["outcome"], first[0]["full_name"], first[0]["record"]) == ("added", "example/frobtail-ng",
                                                                               "frobtail")
    gh._details["example/frobtail-ng"] = {**DETAILS, "readme": README + "\nMore.\n"}
    again = add_repos(gh, db, [FULL_NAME], data_dir=data_dir)
    assert again[0]["outcome"] == "refreshed"
    assert db.candidate(EXAMPLE["repo_id"])["readme"].endswith("More.\n")
    assert len(db.candidates()) == 1


def test_the_command_prints_one_row_per_name(tmp_path: Path, data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    import pickfit.discover.github as gh_module
    import pickfit.verify.result as result_module

    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("GH_TOKEN", "gho_test0123456789SECRET")
    monkeypatch.setattr(result_module, "DATA_DIR", data_dir)
    fake = github()
    fake.close = lambda: None
    monkeypatch.setattr(gh_module, "GitHub", lambda token, **kwargs: fake)
    assert main(["discover", "--repo", FULL_NAME]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert [(r["outcome"], r["record"]) for r in printed] == [("added", "frobtail")]
    assert PipelineDB(tmp_path / "runs" / "pipeline.db").candidate(EXAMPLE["repo_id"])["rule_passed"] is True
    assert main(["discover", "--repo", "acme/gone"]) == 1  # nothing added: the exit code says so
