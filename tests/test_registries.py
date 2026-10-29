"""Registry and Hacker News signals: names from commands and manifests, the repo-link check; no network."""

from __future__ import annotations

from typing import Any

import httpx2
import pytest

from pickfit.registries import (
    Registries,
    RegistryError,
    command_names,
    links_repo,
    manifest_names,
)


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
    assert not links_repo(["https://github.com/tinyq/unrelated"], ["someone/tinyq-new", "tinyq"])  # bare name
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


def server(routes: dict[str, Any]) -> httpx2.Client:
    def handler(request: httpx2.Request) -> httpx2.Response:
        found = routes.get(f"{request.url.host}{request.url.path}")
        if isinstance(found, httpx2.Response):
            return found
        return httpx2.Response(200, json=found) if found is not None else httpx2.Response(404)
    return httpx2.Client(transport=httpx2.MockTransport(handler))


LINKED = {"info": {"project_urls": {"Source": "https://github.com/someone/tinyq"}}}


def test_a_count_the_source_does_not_have_is_unknown_not_zero() -> None:
    reg = Registries(http=server({"pypi.org/pypi/tinyq/json": LINKED,
                                  "registry.npmjs.org/tinyq/latest": {"repository": "github:someone/tinyq",
                                                                      "homepage": "https://github.com/someone/tinyq"},
                                  "api.npmjs.org/downloads/point/last-month/tinyq": {"downloads": 0}}),
                     min_interval_s={})
    sig = reg.lookup("someone/tinyq", names={"pypi": {"tinyq"}})  # pypistats 404: not indexed yet
    assert sig.packages == ["pypi:tinyq"] and sig.registries_count == 1 and sig.monthly_downloads is None
    assert reg.lookup("someone/tinyq", names={"npm": {"tinyq"}}).monthly_downloads == 0  # a real 0 stays 0
    both = reg.lookup("someone/tinyq", names={"npm": {"tinyq"}, "pypi": {"tinyq"}})
    assert both.registries_count == 2 and both.monthly_downloads is None  # npm alone would be a partial sum


def test_pypistats_month_not_filled_in_yet_uses_the_week_as_a_lower_bound() -> None:
    reg = Registries(http=server({"pypi.org/pypi/tinyq/json": LINKED, "pypistats.org/api/packages/tinyq/recent":
                                  {"data": {"last_day": 19, "last_month": 0, "last_week": 114}}}), min_interval_s={})
    assert reg.lookup("someone/tinyq", names={"pypi": {"tinyq"}}).monthly_downloads == 114


def test_a_failed_registry_leaves_downloads_unknown_too(monkeypatch: Any) -> None:
    import pickfit.registries

    monkeypatch.setattr(pickfit.registries.time, "sleep", lambda s: None)
    reg = Registries(http=server({"registry.npmjs.org/tinyq/latest": {"repository": "github:someone/tinyq",
                                                                      "homepage": "https://github.com/someone/tinyq"},
                                  "api.npmjs.org/downloads/point/last-month/tinyq": {"downloads": 1200},
                                  "pypi.org/pypi/tinyq/json": LINKED,
                                  "pypistats.org/api/packages/tinyq/recent": httpx2.Response(
                                      429, headers={"retry-after": "Wed, 29 Oct 2026 12:00:00 GMT"})}),
                     min_interval_s={})
    sig = reg.lookup("someone/tinyq", names={"npm": {"tinyq"}, "pypi": {"tinyq"}})
    assert sig.monthly_downloads is None and sig.registries_count is None and sig.packages == ["npm:tinyq"]
    assert sig.errors == ["pypi:tinyq: pypistats.org: HTTP 429"]  # an HTTP-date Retry-After does not crash


def test_request_errors_become_registry_errors() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.TooManyRedirects("loop", request=request)

    reg = Registries(http=httpx2.Client(transport=httpx2.MockTransport(handler)), min_interval_s={})
    with pytest.raises(RegistryError, match="too many redirects"):
        reg.get_json("https://crates.io/api/v1/crates/tinyq")
    sig = reg.lookup("someone/tinyq", names={"crates": {"tinyq"}})
    assert sig.registries_count is None and sig.hn_top_score is None and len(sig.errors) == 3


def test_hn_counts_a_homepage_only_when_it_is_the_projects_own() -> None:
    queries: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        queries.append(request.url.params["query"])
        return httpx2.Response(200, json={"hits": []})

    reg = Registries(http=httpx2.Client(transport=httpx2.MockTransport(handler)), min_interval_s={})
    for homepage in ("https://janedoe.com", "https://tinyq.dev", "https://janedoe.github.io/tinyq/",
                     "https://www.acme.io/products/other"):
        reg.hn_top_score("someone/tinyq", ["tinyq"], homepage)
    assert queries == ["github.com/someone/tinyq", "github.com/someone/tinyq", "tinyq.dev",
                       "github.com/someone/tinyq", "janedoe.github.io/tinyq", "github.com/someone/tinyq"]
