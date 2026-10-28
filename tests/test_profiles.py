"""Records from stored extractions: API facts from GitHub, model values with quotes; no network."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from pickfit.discover.github import normalize_repo
from pickfit.discover.store import PipelineDB
from pickfit.index import build_index
from pickfit.ledger import TAIPEI
from pickfit.profiles import open_source_from_license, slugify, write_profiles
from pickfit.schema import SoftwareRecord

MODEL = "muse-spark-1.3"
NOW = datetime(2026, 10, 29, 9, 0, tzinfo=TAIPEI)
README = """# tinyq

A tiny jq-like query tool for JSON Lines.

## Install

```sh
brew install someone/tap/tinyq
cargo install tinyq
```

## Usage

```sh
echo '{"a":1}' | tinyq .a
```

Prints `1`. Works on **macOS and Linux**, fully offline.
"""


def cited(value: Any, quote: str | None) -> dict[str, Any]:
    return {"value": value, "quote": quote}


NULL = cited(None, None)


def extraction(**overrides: Any) -> dict[str, Any]:
    data = {
        "name": cited("tinyq", "# tinyq"),
        "summary": cited("Queries JSON Lines from the terminal.", "A tiny jq-like query tool for JSON Lines."),
        "kind": cited("cli_tool", "A tiny jq-like query tool"),
        "category": cited("dev_cli", "A tiny jq-like query tool for JSON Lines."),
        "audience": cited("end_user", "cargo install tinyq"),
        "maturity": NULL,
        "processing": cited("local", "fully offline"),
        "pricing": NULL,
        "platforms": cited(["macos", "linux"], "Works on macOS and Linux"),
        "prerequisites": {
            "runtimes": [], "system_packages": [], "gpu": NULL, "apple_silicon_only": NULL,
            "min_ram_gb": NULL, "network": cited("none", "fully offline"), "api_keys": [],
        },
        "install_methods": [
            {"method": "brew", "command": "brew install someone/tap/tinyq", "platforms": []},
            {"method": "cargo", "command": "cargo install tinyq", "platforms": []},
        ],
        "smoke_test_candidates": [{"command": "echo '{\"a\":1}' | tinyq .a", "expected_output": "1"}],
        "manual_steps": [],
        "use_cases": [cited("query a JSON Lines file", "query tool for JSON Lines")],
        "alternatives_to": [cited("jq", "jq-like")],
    }
    data.update(overrides)
    return data


def add(db: PipelineDB, repo_id: int, full_name: str, result: dict[str, Any], *,
        category: str = "dev_cli", releases: list[dict[str, Any]] | None = None,
        license: str | None = "MIT", model: str = MODEL) -> str:
    owner, name = full_name.split("/")
    item = {"id": repo_id, "full_name": full_name, "name": name, "owner": {"login": owner},
            "html_url": f"https://github.com/{full_name}", "description": "Query JSON Lines",
            "homepage": "https://tinyq.dev", "topics": ["cli", "JSON", "not a tag!"],
            "created_at": "2026-03-01T00:00:00Z", "pushed_at": "2026-10-20T00:00:00Z",
            "default_branch": "main", "stargazers_count": 42,
            "license": {"spdx_id": license} if license else None}
    db.upsert_repo(normalize_repo(item), category=category, query_id=f"{category}:x",
                   seen_at="2026-10-28T19:00:00+08:00")
    key = f"gh:{repo_id}"
    if releases is None:
        releases = [{"tag": "v0.2.0-rc1", "name": None, "prerelease": True,
                     "published_at": "2026-10-10T00:00:00Z",
                     "url": f"https://github.com/{full_name}/releases/tag/v0.2.0-rc1", "body": "", "assets": []},
                    {"tag": "v0.1.0", "name": None, "prerelease": False,
                     "published_at": "2026-10-01T00:00:00Z",
                     "url": f"https://github.com/{full_name}/releases/tag/v0.1.0", "body": "First.",
                     "assets": []}]
    db.save_details(key, {"readme": README, "readme_path": "README.md", "files": ["src/main.rs"],
                          "files_truncated": False, "manifests": {}, "releases": releases},
                    pushed_at="2026-10-20T00:00:00Z")
    db.save_rules(key, label="tool", passed=True, reasons=[], version="test")
    db.save_extraction(repo_id=key, run_id="extract-test", model=model, reasoning_effort="minimal",
                       status="ok", sources_sha="x", result=result, quote_failures=[], quotes_checked=9,
                       error=None, usage=None, cost_usd=0.015, cache_hit=False, response_id="r",
                       latency_s=1.0)
    return key


@pytest.fixture
def db(tmp_path: Path) -> PipelineDB:
    return PipelineDB(tmp_path / "pipeline.db")


def read(out: Path, slug: str) -> dict[str, Any]:
    return json.loads((out / f"{slug}.json").read_text(encoding="utf-8"))


def test_record_takes_facts_from_the_api_and_values_from_the_model(db: PipelineDB, tmp_path: Path) -> None:
    add(db, 7, "someone/tinyq", extraction())
    out = tmp_path / "software"
    summary = write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    assert summary.written == ["tinyq"] and not summary.skipped
    record = read(out, "tinyq")
    SoftwareRecord.model_validate(record)
    # API facts: license, newest non-prerelease release, repo dates, topics that are valid tags.
    assert record["license"] == "MIT" and record["open_source"] is True
    assert record["last_release"] == {"tag": "v0.1.0", "published_at": "2026-10-01T00:00:00Z",
                                      "url": "https://github.com/someone/tinyq/releases/tag/v0.1.0"}
    assert record["repo"]["created_at"] == "2026-03-01T00:00:00Z"
    assert record["tags"] == ["cli", "json"] and record["homepage"] == "https://tinyq.dev"
    assert record["verification"] == {"level": "unverified", "unverified_reason": "not_run",
                                      "checked_at": None, "runs": []}
    evidence = {e["field"]: e for e in record["evidence"]}
    for pointer in ("/license", "/last_release", "/repo", "/tags"):
        assert evidence[pointer]["method"] in ("api", "rule") and evidence[pointer]["quote"] is None
    assert evidence["/last_release"]["source_id"] == "release:v0.1.0"
    # Model values keep their quote, the source it is in, and the model id.
    assert evidence["/summary"] == {"field": "/summary", "source_id": "readme",
                                    "quote": "A tiny jq-like query tool for JSON Lines.",
                                    "method": "model", "model": MODEL,
                                    "checked_at": evidence["/summary"]["checked_at"]}
    assert evidence["/platforms"]["quote"] == "Works on macOS and Linux"
    assert {s["id"] for s in record["sources"]} == {"github_api", "readme", "release:v0.1.0"}
    assert record["first_seen_at"] == "2026-10-28T19:00:00+08:00"
    # The index loads it and serves no README-claim install steps.
    entry = build_index(out, now=NOW).index["entries"][0]
    assert entry["slug"] == "tinyq" and entry["install"] == {}


def test_readme_install_claims_become_unverified_guides_per_os(db: PipelineDB, tmp_path: Path) -> None:
    add(db, 7, "someone/tinyq", extraction())
    out = tmp_path / "software"
    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    install = {os: g for os, g in read(out, "tinyq")["install"].items() if g}
    assert set(install) == {"macos", "linux"}  # no Windows: the README names macOS and Linux
    assert install["macos"]["method"] == "brew" and install["linux"]["method"] == "cargo"
    assert all(g["basis"] == "readme_claim" and g["run_id"] is None for g in install.values())
    assert install["linux"]["check"] == {"command": "echo '{\"a\":1}' | tinyq .a", "expected_signal": "1"}


def test_only_end_user_tools_in_the_chosen_categories_are_written(db: PipelineDB, tmp_path: Path) -> None:
    add(db, 1, "a/lib", extraction(kind=cited("library_sdk", "A tiny jq-like query tool")))
    add(db, 2, "a/app", extraction(category=cited("other", "A tiny jq-like query tool")))
    add(db, 3, "a/imp", extraction(audience=cited("import_only", "cargo install tinyq")))
    add(db, 4, "a/ok", extraction())
    out = tmp_path / "software"
    summary = write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    assert summary.written == ["ok"]
    assert summary.skipped == {"a/lib": "not_a_tool: kind library_sdk", "a/app": "category: other",
                               "a/imp": "not_a_tool: import_only"}
    assert write_profiles(db, model=MODEL, out_dir=out, categories=("other",), now=NOW).written == ["app"]


def test_unknown_category_falls_back_to_the_discovery_query(db: PipelineDB, tmp_path: Path) -> None:
    add(db, 7, "someone/tinyq", extraction(category=NULL), category="local_ai")
    out = tmp_path / "software"
    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    record = read(out, "tinyq")
    assert record["category"] == "local_ai"
    assert {e["field"]: e["method"] for e in record["evidence"]}["/category"] == "rule"


def test_other_models_extractions_and_prerelease_only_repos(db: PipelineDB, tmp_path: Path) -> None:
    add(db, 1, "a/devonly", extraction(), model="muse-spark-1.3-contributor")
    rc = [{"tag": "v1.0.0-rc1", "name": None, "prerelease": True, "published_at": "2026-10-10T00:00:00Z",
           "url": "https://github.com/a/rc/releases/tag/v1.0.0-rc1", "body": "", "assets": []}]
    add(db, 2, "a/rc", extraction(), releases=rc, license=None)
    out = tmp_path / "software"
    summary = write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    assert summary.written == ["rc"]
    record = read(out, "rc")
    assert record["last_release"] is None and record["license"] is None and record["open_source"] is None


def test_slug_clash_uses_the_owner_and_rewrites_keep_slug_and_verification(db: PipelineDB,
                                                                           tmp_path: Path) -> None:
    add(db, 1, "alice/phantom", extraction())
    add(db, 2, "bob/phantom", extraction())
    out = tmp_path / "software"
    assert write_profiles(db, model=MODEL, out_dir=out, now=NOW).written == ["phantom", "bob-phantom"]
    # Verification (P3) wrote a run into the record; writing again must keep it.
    record = read(out, "bob-phantom")
    run = {"id": "verify-1", "level": "install", "os": "linux", "arch": "x86_64", "method": "sandbox",
           "checked_at": "2026-10-30T10:00:00+08:00", "replayed": True,
           "steps": [{"command": "cargo install tinyq", "purpose": None}],
           "evidence": {"trace_path": "runs/verify/verify-1/report.json"}}
    record["verification"] = {"level": "install", "unverified_reason": None,
                              "checked_at": "2026-10-30T10:00:00+08:00", "runs": [run]}
    record["install"]["linux"] = {"basis": "replayed", "run_id": "verify-1", "method": "cargo",
                                  "steps": [{"command": "cargo install tinyq", "purpose": None}]}
    (out / "bob-phantom.json").write_text(json.dumps(record), encoding="utf-8")
    again = write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    assert again.unchanged == ["phantom"]
    kept = read(out, "bob-phantom")
    assert kept["verification"]["level"] == "install" and kept["install"]["linux"]["basis"] == "replayed"
    assert kept["install"]["macos"]["basis"] == "readme_claim"
    assert len(build_index(out, now=NOW).index["entries"]) == 2


def test_helpers() -> None:
    assert slugify("Unreal-MCP") == "unreal-mcp" and slugify("ELI_v2.0") == "eli-v2-0"
    assert open_source_from_license("AGPL-3.0") is True
    assert open_source_from_license("BUSL-1.1") is False
    assert open_source_from_license(None) is None
