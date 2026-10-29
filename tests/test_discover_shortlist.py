"""The pre-extraction shortlist: GitHub-snapshot signals only, no model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pickfit.discover.github import normalize_repo
from pickfit.discover.shortlist import box_fit, shortlist
from pickfit.discover.store import PipelineDB
from tests.test_discover import repo_item


def candidate(readme: str = "# tool", files: list[str] | None = None, manifests: dict[str, str] | None = None,
              assets: list[str] | None = None, rule_label: str = "tool") -> dict[str, Any]:
    releases = [{"tag": "v1", "assets": [{"name": a, "downloads": 0} for a in assets]}] if assets else []
    return {"repo": normalize_repo(repo_item(1)), "readme": readme, "files": files or ["README.md"],
            "manifests": manifests or {}, "releases": releases, "rule_label": rule_label}


def names(signals: list[str]) -> set[str]:
    return {s.split(":", 1)[1] for s in signals}


def test_cli_runner_scores_above_desktop_app() -> None:
    cli, cli_signals = box_fit(candidate(
        readme="# q\n\n`pipx install q`\n\nTalks to a local Ollama model at localhost:11434.",
        manifests={"pyproject.toml": "[project]\nname='q'\n[project.scripts]\nq = 'q:main'\n"},
        files=["pyproject.toml", "q/__init__.py"]))
    app, app_signals = box_fit(candidate(
        readme="# App\n\nA desktop app for chatting with local models through Ollama.",
        files=["src-tauri/tauri.conf.json", "src/App.tsx"], assets=["App_1.0_aarch64.dmg", "App_1.0_x64.msi"]))
    assert names(cli_signals) == {"entry_point", "tool_install_command", "local_server", "local_runner"}
    assert "gui_project" in names(app_signals)
    assert cli > app


def test_gui_companion_in_a_subdirectory_counts_less_than_a_gui_product() -> None:
    _, top = box_fit(candidate(files=["src-tauri/Cargo.toml"]))
    _, sub = box_fit(candidate(files=["crates/cli/src/main.rs", "desktop/src-tauri/Cargo.toml"]))
    assert "gui_project" in names(top)
    assert {"nested_entry_point", "gui_subproject"} <= names(sub)


def test_requirements_and_web_apps_count_against() -> None:
    _, gpu = box_fit(candidate(readme="Requires an NVIDIA GPU with 8 GB."))
    _, apple = box_fit(candidate(readme="Apple Silicon only."))
    _, web = box_fit(candidate(files=["docker-compose.yml", "frontend/package.json"]))
    assert "gpu_required" in names(gpu)
    assert "apple_only" in names(apple)
    assert "web_app" in names(web)


def test_linux_binaries_but_not_installer_files() -> None:
    _, linux = box_fit(candidate(assets=["tool-x86_64-unknown-linux-gnu.tar.gz"]))
    _, installers = box_fit(candidate(assets=["Tool-1.0.AppImage", "Tool.dmg"]))
    assert "linux_binaries" in names(linux)
    assert "linux_binaries" not in names(installers)
    assert "gui_assets_only" in names(installers)


def test_shortlist_skips_extracted_and_known_repos(tmp_path: Path) -> None:
    db = PipelineDB(tmp_path / "pipeline.db")
    for repo_id, name in ((1, "a/cli"), (2, "a/app"), (3, "a/done"), (4, "a/known")):
        db.upsert_repo(normalize_repo(repo_item(repo_id, name)), category="local_ai", query_id="q")
    cli = {"readme": "# cli\n`pipx install cli`", "readme_path": "README.md", "releases": [],
           "files": ["pyproject.toml"], "files_truncated": False,
           "manifests": {"pyproject.toml": "[project.scripts]\ncli = 'cli:main'\n"}}
    app = {**cli, "readme": "# app\nA desktop app.", "files": ["src-tauri/x"], "manifests": {}}
    for repo_id, details in (("gh:1", cli), ("gh:2", app), ("gh:3", cli), ("gh:4", cli)):
        db.save_details(repo_id, details, pushed_at="2026-10-20T00:00:00Z")
        db.save_rules(repo_id, label="tool", passed=True, reasons=[], version="test")
    db.save_extraction(repo_id="gh:3", run_id="r", model="muse-spark-1.3", reasoning_effort="minimal",
                       status="ok", sources_sha="x", result={}, quote_failures=[], quotes_checked=0,
                       error=None, usage=None, cost_usd=0.0, cache_hit=False, response_id=None, latency_s=1.0)
    ranked = shortlist(db, category="local_ai", skip_repo_ids={"gh:4"})
    assert [r.full_name for r in ranked] == ["a/cli", "a/app"]
    assert shortlist(db, category="dev_cli") == []


def test_description_about_local_models_counts_for_and_coding_agents_against() -> None:
    runner = candidate()
    runner["repo"]["description"] = "Pure-Go local LLM inference from GGUF files"
    agent = candidate()
    agent["repo"]["description"] = "Open source coding agent for your terminal"
    assert "local_focus" in names(box_fit(runner)[1])
    assert "coding_agent" in names(box_fit(agent)[1])
    assert box_fit(runner)[0] > box_fit(agent)[0]
