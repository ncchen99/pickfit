"""Each harvest source against a recorded-shape answer from its API: what it asks for and the hits it makes.

The shapes follow the real APIs as read on 2026-11-19. When a source changes its format, the live probe
(`pickfit harvest probe`, tests/test_harvest_probe.py) is what notices; these keep the parsing honest.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest

from pickfit.harvest import sources
from pickfit.harvest.leads import LeadsDB
from pickfit.harvest.sources import Ctx, SourceError

NOW = datetime(2026, 11, 19, 4, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources, "sleep", lambda s: None)


class FakeResponse:
    def __init__(self, body: Any = None, text: str = "") -> None:
        self.body, self.text = body, text

    def json(self) -> Any:
        return self.body


class FakeGitHub:
    """The bits of pickfit.discover.github.GitHub the sources use."""

    def __init__(self, gets: dict[str, Any] | None = None, searches: dict[str, list[dict]] | None = None) -> None:
        self.gets, self.searches = gets or {}, searches or {}
        self.requests: Counter[str] = Counter()
        self.calls: list[tuple[str, dict | None]] = []

    def _get(self, kind: str, path: str, params: dict | None = None, accept: str = "") -> FakeResponse | None:
        self.requests[kind] += 1
        self.calls.append((path, params))
        body = self.gets.get(path)
        if body is None:
            return None
        return FakeResponse(text=body) if isinstance(body, str) else FakeResponse(body)

    def search_repositories(self, query: Any, *, per_page: int, sort: str) -> dict[str, Any]:
        self.requests["search"] += 1
        self.calls.append(("search", {"q": query.q}))
        return {"items": self.searches.get(query.q.split()[0].removeprefix("topic:"), [])}


def _ctx(tmp_path: Path, routes: dict[str, Any] | None = None, gh: FakeGitHub | None = None,
         **kw: Any) -> tuple[Ctx, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        for prefix, body in (routes or {}).items():
            if str(request.url).startswith(prefix):
                body = body(request) if callable(body) else body
                if isinstance(body, httpx2.Response):
                    return body
                return httpx2.Response(200, text=body) if isinstance(body, str) else httpx2.Response(200, json=body)
        return httpx2.Response(404)

    ctx = Ctx(db=LeadsDB(tmp_path / "h.db"), http=httpx2.Client(transport=httpx2.MockTransport(handler)), gh=gh,
              now=NOW, log=lambda s: None, **kw)
    return ctx, seen


def _keys(hits: list) -> list:
    return [h.key_url()[0] if h.key_url() else None for h in hits]


def test_npm_reads_repository_links_and_monthly_downloads(tmp_path: Path) -> None:
    def search(request: httpx2.Request) -> dict:
        if request.url.params["text"] != "keywords:mcp-server":
            return {"objects": []}
        return {"objects": [
            {"package": {"name": "@o/tool", "description": "a tool",
                         "links": {"npm": "https://www.npmjs.com/package/@o/tool",
                                   "repository": "git+https://github.com/O/Tool.git"}},
             "downloads": {"monthly": 1234}},
            {"package": {"name": "nolinks", "links": {}}, "downloads": {}}]}

    ctx, seen = _ctx(tmp_path, {sources.NPM_SEARCH: search})
    hits = list(sources.npm(ctx))
    assert _keys(hits) == ["gh:o/tool", None]
    assert hits[0].signal == 1234.0 and hits[0].kind_hint == "mcp_server" and hits[0].link.endswith("@o/tool")
    assert seen[0].headers["user-agent"].startswith("pickfit")
    assert len(seen) == len(sources.NPM_QUERIES)  # a short page ends each query


def test_homebrew_skips_deprecated_and_takes_install_counts(tmp_path: Path) -> None:
    formulae = [{"name": "rg", "desc": "search", "homepage": "https://github.com/BurntSushi/ripgrep",
                 "urls": {"stable": {"url": "https://github.com/BurntSushi/ripgrep/archive/14.tar.gz"}}},
                {"name": "old", "deprecated": True, "urls": {}, "homepage": "https://github.com/o/old"}]
    installs = {"items": [{"formula": "rg", "count": "12,345"}]}
    ctx, _ = _ctx(tmp_path, {sources.BREW_FORMULA: formulae, sources.BREW_INSTALLS: installs})
    hits = list(sources.homebrew(ctx))
    assert _keys(hits) == ["gh:burntsushi/ripgrep"]
    assert hits[0].signal == 12345.0 and hits[0].platforms == ["macos", "linux"]


def test_homebrew_without_install_counts_still_runs(tmp_path: Path) -> None:
    ctx, _ = _ctx(tmp_path, {sources.BREW_FORMULA: [{"name": "a", "urls": {}, "homepage": "https://github.com/o/a"}],
                             sources.BREW_INSTALLS: httpx2.Response(403)})
    assert [h.signal for h in sources.homebrew(ctx)] == [None]


def test_winget_reads_new_package_manifests(tmp_path: Path) -> None:
    gh = FakeGitHub(gets={"/search/commits": {"items": [
        {"commit": {"message": "New package: Foo.Bar version 1.2.0 (#123)"}},
        {"commit": {"message": "New package: Foo.Bar version 1.2.0"}},  # the same package again
        {"commit": {"message": "Update: Other.Thing version 2"}}]}})
    manifest = ("PackageIdentifier: Foo.Bar\nPublisherUrl: https://foo.example\n"
                "PackageUrl: https://github.com/foo/bar\nShortDescription: Does things\n")
    ctx, seen = _ctx(tmp_path, {"https://raw.githubusercontent.com/microsoft/winget-pkgs/master/": manifest}, gh=gh)
    hits = list(sources.winget(ctx))
    assert _keys(hits) == ["gh:foo/bar"] and hits[0].title == "Does things" and hits[0].platforms == ["windows"]
    assert seen[0].url.path.endswith("manifests/f/Foo/Bar/1.2.0/Foo.Bar.locale.en-US.yaml")
    assert 'committer-date:>=2026-11-12' in gh.calls[0][1]["q"]


def test_winget_stops_at_the_limit(tmp_path: Path) -> None:
    items = [{"commit": {"message": f"New package: P.N{i} version 1"}} for i in range(100)]
    gh = FakeGitHub(gets={"/search/commits": {"items": items}})
    ctx, seen = _ctx(tmp_path, {"https://raw.githubusercontent.com/": "PackageUrl: https://github.com/o/r\n"},
                     gh=gh, limit=3)
    assert len(list(sources.winget(ctx))) == 3
    assert len(seen) == 3 and len(gh.calls) == 1  # no more manifests, no second search page


def test_awesome_keeps_github_links_only_and_skips_other_lists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sources, "AWESOME_LISTS", (("o/awesome-tools", "cli_tool", ("linux",)),
                                                   ("o/missing", "tui", ())))
    readme = ("# Tools\n- [rg](https://github.com/BurntSushi/ripgrep) - search\n"
              "- [list](https://github.com/x/awesome-more)\n- [self](https://github.com/o/awesome-tools)\n"
              "- [site](https://example.com)\n")
    gh = FakeGitHub(gets={"/repos/o/awesome-tools/readme": readme})
    ctx, _ = _ctx(tmp_path, gh=gh)
    hits = list(sources.awesome(ctx))
    assert _keys(hits) == ["gh:burntsushi/ripgrep"]
    assert hits[0].title is None and hits[0].platforms == ["linux"]  # no list text kept


def test_github_rising_asks_for_new_starred_repos(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sources, "RISING_TOPICS", (("tui", "tui"), ("macos", "desktop_app")))
    gh = FakeGitHub(searches={"tui": [{"full_name": "o/t", "html_url": "https://github.com/o/t",
                                       "description": "d", "stargazers_count": 80}],
                              "macos": [{"full_name": "o/m", "html_url": "https://github.com/o/m",
                                         "stargazers_count": 60}]})
    ctx, _ = _ctx(tmp_path, gh=gh)
    hits = list(sources.github_rising(ctx))
    assert _keys(hits) == ["gh:o/t", "gh:o/m"] and hits[1].platforms == ["macos"] and hits[0].signal == 80.0
    assert "created:>=2026-10-05" in gh.calls[0][1]["q"] and "stars:>=50" in gh.calls[0][1]["q"]


def test_hn_keeps_github_stories_and_show_hn_sites(tmp_path: Path) -> None:
    def search(request: httpx2.Request) -> dict:
        return {"hits": [{"objectID": "1", "url": "https://github.com/o/r", "title": "R", "points": 50,
                          "_tags": ["story"]},
                         {"objectID": "2", "url": "https://app.example.org", "title": "Show HN: App",
                          "points": 30, "_tags": ["story", "show_hn"]},
                         {"objectID": "3", "url": "https://news.example.org/a", "points": 90, "_tags": ["story"]}]}

    ctx, seen = _ctx(tmp_path, {sources.ALGOLIA: search}, days=1)
    hits = list(sources.hacker_news(ctx))
    assert _keys(hits) == ["gh:o/r", "web:https://app.example.org/"]
    assert hits[1].kind_hint == "web_app" and hits[0].link == "https://news.ycombinator.com/item?id=1"
    assert "points>=20" in seen[0].url.params["numericFilters"]


def test_sources_needing_github_say_so(tmp_path: Path) -> None:
    ctx, _ = _ctx(tmp_path)
    for source in (sources.winget, sources.awesome, sources.github_rising):
        with pytest.raises(SourceError, match="GH_TOKEN"):
            list(source(ctx))


def test_get_retries_server_errors_then_gives_up(tmp_path: Path) -> None:
    calls = []

    def flaky(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        return httpx2.Response(503) if len(calls) < 3 else httpx2.Response(200, json={"crates": []})

    ctx, _ = _ctx(tmp_path, {sources.CRATES: flaky})
    assert list(sources.crates(ctx)) == [] and len(calls) >= 3
    ctx, _ = _ctx(tmp_path, {sources.CRATES: httpx2.Response(403)})
    with pytest.raises(SourceError, match="HTTP 403"):
        list(sources.crates(ctx))
