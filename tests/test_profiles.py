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
from pickfit.profiles import open_source_from_license, slugify, write_features, write_profiles
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
        license: str | None = "MIT", model: str = MODEL, readme: str = README) -> str:
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
    db.save_details(key, {"readme": readme, "readme_path": "README.md", "files": ["src/main.rs"],
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


def test_guides_skip_checkout_steps_and_shells_of_another_os(db: PipelineDB, tmp_path: Path) -> None:
    readme_cmds = {
        "npm ci": "npm", "pip install -r requirements.txt": "pip", "uv pip install -e .": "uv",
        "git clone https://github.com/someone/tinyq": "source", "npm run dev": "npm",
        "pip install pytest": "pip", "brew install llama.cpp": "brew", "docker compose up -d": "docker",
        "curl -fsSL https://x.dev/install.sh | bash": "script", "irm https://x.dev/install.ps1 | iex": "script",
        "brew tap someone/tap": "brew", "brew install someone/tap/tinyq": "brew",
    }
    claims = [{"method": m, "command": c, "platforms": []} for c, m in readme_cmds.items()]
    add(db, 7, "someone/tinyq", extraction(
        install_methods=claims, platforms=cited(["macos", "linux", "windows"], "Works on macOS and Linux")),
        readme=README + "\n".join(f"    {c}" for c in readme_cmds))
    out = tmp_path / "software"
    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    install = read(out, "tinyq")["install"]
    assert [s["command"] for s in install["macos"]["steps"]] == ["brew tap someone/tap",
                                                                 "brew install someone/tap/tinyq"]
    assert [s["command"] for s in install["linux"]["steps"]] == ["curl -fsSL https://x.dev/install.sh | bash"]
    assert [s["command"] for s in install["windows"]["steps"]] == ["irm https://x.dev/install.ps1 | iex"]
    pointers = {e["field"] for e in read(out, "tinyq")["evidence"]}
    assert {"/install/macos/steps/0", "/install/macos/steps/1", "/install/windows/steps/0"} <= pointers


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


def test_a_show_hn_post_is_listed_as_a_source_but_backs_no_field(db: PipelineDB, tmp_path: Path) -> None:
    from pickfit.discover.showhn import Post

    key = add(db, 7, "someone/tinyq", extraction())
    post = Post(item_id="4242", title="Show HN: tinyq", link="https://github.com/someone/tinyq", points=12,
                comments=3, posted_at="2026-10-27T10:00:00+00:00", repo="someone/tinyq", categories=["dev_cli"])
    db.save_channel_hit(channel="show_hn", post=post, repo_id=key, outcome="candidate", known_before=False,
                        run_id="discover-show_hn-test", seen_at="2026-10-31T21:00:00+08:00")
    out = tmp_path / "software"
    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    record = read(out, "tinyq")
    assert record["sources"][-1] == {"id": "hn:4242", "kind": "hn",
                                     "url": "https://news.ycombinator.com/item?id=4242",
                                     "fetched_at": "2026-10-31T21:00:00+08:00"}
    assert not [e for e in record["evidence"] if e["source_id"] == "hn:4242"]
    # Writing again keeps one copy of it.
    assert write_profiles(db, model=MODEL, out_dir=out, now=NOW).unchanged == ["tinyq"]
    assert [s["id"] for s in read(out, "tinyq")["sources"]].count("hn:4242") == 1
    assert len(build_index(out, now=NOW).index["entries"]) == 1


def test_repeated_list_values_are_kept_once(db: PipelineDB, tmp_path: Path) -> None:
    keys = [cited("JQ_KEY", "jq-like"), cited("JQ_KEY", "jq-like")]
    add(db, 7, "someone/tinyq", extraction(prerequisites={**extraction()["prerequisites"], "api_keys": keys}))
    out = tmp_path / "software"
    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    assert read(out, "tinyq")["prerequisites"]["api_keys"] == ["JQ_KEY"]


FEATURES = [cited("query JSON Lines with a path", "A tiny jq-like query tool for JSON Lines."),
            cited("run fully offline", "fully offline"), cited("edit YAML", "edits YAML files")]


def test_new_records_list_the_quoted_features(db: PipelineDB, tmp_path: Path) -> None:
    add(db, 7, "someone/tinyq", extraction(features=FEATURES))
    out = tmp_path / "software"
    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    record = read(out, "tinyq")
    assert record["features"] == ["query JSON Lines with a path", "run fully offline"]
    evidence = {e["field"]: e for e in record["evidence"]}
    assert evidence["/features/1"]["quote"] == "fully offline" and evidence["/features/1"]["method"] == "model"
    assert build_index(out, now=NOW).index["entries"][0]["features"] == record["features"]


def test_features_only_touches_features_of_existing_records(db: PipelineDB, tmp_path: Path) -> None:
    key = add(db, 7, "someone/tinyq", extraction())
    out = tmp_path / "software"
    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    before = read(out, "tinyq")
    assert "features" not in before
    db.save_extraction(repo_id=key, run_id="extract-features", model=MODEL, reasoning_effort="low",
                       status="ok", sources_sha="y", result=extraction(features=FEATURES, summary=cited(
                           "Something else entirely.", "A tiny jq-like query tool for JSON Lines.")),
                       quote_failures=[], quotes_checked=9, error=None, usage=None, cost_usd=0.015,
                       cache_hit=False, response_id="r2", latency_s=1.0)
    later = datetime(2026, 10, 31, 9, 0, tzinfo=TAIPEI)
    summary = write_features(db, model=MODEL, out_dir=out, now=later)
    assert summary.written == ["tinyq"]
    after = read(out, "tinyq")
    assert after["features"] == ["query JSON Lines with a path", "run fully offline"]
    assert after["summary"] == before["summary"]  # nothing but the features changes
    assert {k: v for k, v in after.items() if k not in ("features", "evidence", "updated_at")} == \
        {k: v for k, v in before.items() if k not in ("evidence", "updated_at")}
    assert [e for e in after["evidence"] if not e["field"].startswith("/features/")] == before["evidence"]
    assert write_features(db, model=MODEL, out_dir=out, now=later).unchanged == ["tinyq"]


def test_features_only_reads_a_features_only_extraction(db: PipelineDB, tmp_path: Path) -> None:
    key = add(db, 7, "someone/tinyq", extraction())
    out = tmp_path / "software"
    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    assert write_features(db, model=MODEL, out_dir=out, now=NOW).skipped == {
        "tinyq": "no extraction with features by muse-spark-1.3"}
    db.save_extraction(repo_id=key, run_id="extract-features-x", model=MODEL, reasoning_effort="minimal",
                       status="features", sources_sha="y", result={"features": FEATURES[:2]}, quote_failures=[],
                       quotes_checked=2, error=None, usage=None, cost_usd=0.01, cache_hit=False, response_id="r3",
                       latency_s=1.0)
    assert write_features(db, model=MODEL, out_dir=out, now=NOW).written == ["tinyq"]
    assert read(out, "tinyq")["features"] == ["query JSON Lines with a path", "run fully offline"]
    # Profiles never build a record from a features-only row.
    assert write_profiles(db, model=MODEL, out_dir=out, now=NOW).unchanged == ["tinyq"]


def test_helpers() -> None:
    assert slugify("Unreal-MCP") == "unreal-mcp" and slugify("ELI_v2.0") == "eli-v2-0"
    assert open_source_from_license("AGPL-3.0") is True
    assert open_source_from_license("BUSL-1.1") is False
    assert open_source_from_license(None) is None


MCP_README = """# notes-mcp

An MCP server that searches your Markdown notes.

## Install

```sh
npm install -g notes-mcp
```

## Use with Claude Code

```sh
claude mcp add notes -- notes-mcp --root ~/notes
```

Set `NOTES_ROOT` to your notes folder. Transport: stdio.

Tools: `search_notes`, `read_note`.
"""


def mcp_extraction(**mcp_overrides: Any) -> dict[str, Any]:
    mcp = {
        "transports": cited(["stdio"], "Transport: stdio."),
        "launch_command": cited("notes-mcp --root ~/notes", "notes-mcp --root ~/notes"),
        "client_configs": [
            {"client": "claude_code", "snippet": "claude mcp add notes -- notes-mcp --root ~/notes"},
            {"client": "generic_json", "snippet": '{"mcpServers": {"notes": {"command": "made-up"}}}'},
        ],
        "env_vars": [{"name": "NOTES_ROOT", "required": False, "purpose": "your  notes folder"},
                     {"name": "INVENTED_KEY", "required": True, "purpose": None}],
        "tools": [cited("search_notes", "`search_notes`"), cited("read_note", "`read_note`"),
                  cited("delete_note", "`delete_note`")],
    }
    mcp.update(mcp_overrides)
    return extraction(
        name=cited("notes-mcp", "# notes-mcp"),
        summary=cited("Searches Markdown notes over MCP.", "An MCP server that searches your Markdown notes."),
        kind=cited("mcp_server_or_agent_plugin", "An MCP server"),
        category=cited("mcp_server", "An MCP server that searches your Markdown notes."),
        audience=cited("end_user", "npm install -g notes-mcp"),
        processing=NULL, platforms=NULL,
        prerequisites={"runtimes": [], "system_packages": [], "gpu": NULL, "apple_silicon_only": NULL,
                       "min_ram_gb": NULL, "network": NULL, "api_keys": []},
        install_methods=[{"method": "npm", "command": "npm install -g notes-mcp", "platforms": []}],
        smoke_test_candidates=[], use_cases=[], alternatives_to=[], mcp=mcp)


def test_mcp_server_gets_mcp_facts_its_sources_show(db: PipelineDB, tmp_path: Path) -> None:
    from pickfit.extract import Source, check_quotes
    from pickfit.schema import ExtractionResult

    # The quote check drops a snippet and an env var name the README does not hold.
    raw = ExtractionResult.model_validate(mcp_extraction())
    cleaned, failures, _ = check_quotes(raw, [Source("readme", "readme", None, MCP_README)])
    assert {f["path"] for f in failures} == {"/mcp/client_configs/1/snippet", "/mcp/env_vars/1/name",
                                             "/mcp/tools/2"}
    assert [c.client for c in cleaned.mcp.client_configs] == ["claude_code"]

    add(db, 21, "someone/notes-mcp", cleaned.model_dump(mode="json"), category="mcp_server", readme=MCP_README)
    out = tmp_path / "software"
    assert write_profiles(db, model=MODEL, out_dir=out, now=NOW).written == ["notes-mcp"]
    record = read(out, "notes-mcp")
    assert record["category"] == "mcp_server"
    assert record["mcp"] == {
        "transports": ["stdio"], "launch_command": "notes-mcp --root ~/notes",
        "client_configs": [{"client": "claude_code", "snippet": "claude mcp add notes -- notes-mcp --root ~/notes"}],
        "env_vars": [{"name": "NOTES_ROOT", "required": False, "purpose": "your notes folder"}],
        "tools": ["search_notes", "read_note"]}
    fields = {e["field"] for e in record["evidence"]}
    assert {"/mcp/transports", "/mcp/launch_command", "/mcp/client_configs/0", "/mcp/env_vars/0",
            "/mcp/tools/1"} <= fields


def test_only_mcp_servers_carry_mcp_facts(db: PipelineDB, tmp_path: Path) -> None:
    add(db, 22, "someone/tinyq", extraction())
    out = tmp_path / "software"
    write_profiles(db, model=MODEL, out_dir=out, now=NOW)
    assert "mcp" not in read(out, "tinyq")  # not even "mcp": null, so other records stay byte-identical
