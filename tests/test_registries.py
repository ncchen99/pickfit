"""Registry and Hacker News signals: names from commands and manifests, the repo-link check; no network."""

from __future__ import annotations

from typing import Any

import httpx2

from pickfit.registries import Registries, command_names, links_repo, manifest_names


def test_command_names_take_packages_not_paths_urls_or_arguments() -> None:
    names = command_names([
        "npm i -g --ignore-scripts @trymuxr/cli@latest",
        'uv tool install "servebench[mock]" 2>&1',
        'export PATH="$HOME/.bun/bin:$PATH" && bun add -g @drakulavich/kesha-voice-kit',
        "npx -y pondok-ai init --preset standard",
        "pip install https://github.com/x/y/releases/download/v1/y-0.9.4-py3-none-any.whl",
        "uv tool install git+https://github.com/a/b.git",
        "cd repo && python3 -m pip install -r requirements.txt && python3 -m pip install --no-deps .",
        "uv pip install --python ~/venv/bin/python netifaces-plus",
        "cargo install --git https://github.com/a/b", "cargo install rho", "pipx install mafdet",
        "brew install someone/tap/tool", "brew install ripgrep",
    ])
    assert names == {"npm": {"@trymuxr/cli", "@drakulavich/kesha-voice-kit", "pondok-ai"},
                     "pypi": {"servebench", "netifaces-plus", "mafdet"}, "crates": {"rho"},
                     "homebrew": {"ripgrep"}}


def test_manifest_names_skip_private_packages_and_workspaces() -> None:
    assert manifest_names({"package.json": '{"name": "Penthera"}', "pyproject.toml": '[project]\nname = "Foo_Bar"\n',
                           "Cargo.toml": "[workspace]\nmembers = []\n"}) == {
        "npm": {"penthera"}, "pypi": {"foo-bar"}, "crates": set(), "homebrew": set()}
    assert manifest_names({"package.json": '{"name": "mono", "private": true}', "setup.cfg": "[metadata]\nname = tq\n"}
                          )["pypi"] == {"tq"}


def test_links_repo_matches_the_repo_and_not_a_prefix() -> None:
    repos = ["someone/tinyq", "someone/old-name"]
    assert links_repo(["git+https://github.com/Someone/TinyQ.git"], repos)
    assert links_repo(["https://github.com/someone/old-name#readme"], repos)
    assert links_repo(["git@github.com:someone/tinyq.git"], repos)
    assert not links_repo(["https://github.com/someone/tinyq-fork", "https://tinyq.dev", None], repos)


def registry_server(calls: list[str]) -> httpx2.Client:
    docs: dict[str, Any] = {
        "registry.npmjs.org/tinyq/latest": {"repository": {"url": "git+https://github.com/someone/tinyq.git"}},
        "registry.npmjs.org/other/latest": {"repository": "github:someone-else/other", "homepage": "https://x.dev"},
        "api.npmjs.org/downloads/point/last-month/tinyq": {"downloads": 1200},
        "pypi.org/pypi/tinyq/json": {"info": {"project_urls": {"Source": "https://github.com/someone/tinyq"}}},
        "pypistats.org/api/packages/tinyq/recent": {"data": {"last_month": 300}},
        "hn.algolia.com/api/v1/search": {"hits": [
            {"url": "https://github.com/someone/tinyq", "points": 12},
            {"url": "https://github.com/someone/tinyq-fork", "points": 400}]},
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        key = f"{request.url.host}{request.url.path}"
        calls.append(key)
        if request.url.host == "crates.io":
            return httpx2.Response(503)
        return httpx2.Response(200, json=docs[key]) if key in docs else httpx2.Response(404)

    return httpx2.Client(transport=httpx2.MockTransport(handler))


def test_lookup_counts_packages_that_link_back_and_sums_their_downloads() -> None:
    calls: list[str] = []
    reg = Registries(http=registry_server(calls), min_interval_s={})
    sig = reg.lookup("someone/tinyq", homepage="https://github.com/someone/tinyq",
                     names={"npm": {"other", "tinyq"}, "pypi": {"tinyq"}})
    assert sig.packages == ["npm:tinyq", "pypi:tinyq"] and sig.registries_count == 2
    assert sig.monthly_downloads == 1500 and sig.hn_top_score == 12 and sig.errors == []
    assert "formulae.brew.sh/api/formula/tinyq.json" in calls  # the repo name is tried on Homebrew


def test_a_failed_registry_leaves_the_count_unknown(monkeypatch: Any) -> None:
    import pickfit.registries

    monkeypatch.setattr(pickfit.registries.time, "sleep", lambda s: None)
    reg = Registries(http=registry_server([]), min_interval_s={}, pypi_downloads=False)
    sig = reg.lookup("someone/tinyq", names={"crates": {"tinyq"}, "pypi": {"tinyq"}})
    assert sig.registries_count is None and sig.errors and sig.errors[0].startswith("crates:tinyq")
    assert sig.packages == ["pypi:tinyq"] and sig.monthly_downloads is None  # pypistats was off
