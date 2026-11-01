"""Package stores as discovery sources (Flathub, Homebrew Cask) with mocked catalogs and GitHub."""

from __future__ import annotations

import base64
import gzip
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest

from pickfit.discover import cask, flathub
from pickfit.discover.github import normalize_repo
from pickfit.discover.listings import (
    Listing,
    github_repo,
    needs_account,
    open_license,
    percentile,
    pick,
    search_store,
)
from pickfit.discover.rules import classify
from pickfit.discover.run import run_discover
from pickfit.discover.store import PipelineDB, _channels
from tests.test_discover import FakeGitHub, json_response, repo_item

NOW = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)


# --- rules on the store's own text ---------------------------------------------------------


@pytest.mark.parametrize(("expression", "expected"), [
    ("GPL-3.0-or-later", True),
    ("MIT OR Apache-2.0", True),
    ("MIT OR LicenseRef-proprietary", True),
    ("GPL-2.0+ and LicenseRef-proprietary", False),
    ("LicenseRef-proprietary=https://example.com/eula", False),
    ("CC-BY-NC-SA-4.0", False),
    ("CC-BY-ND-4.0", False),
    ("BUSL-1.1", False),
    ("CC-BY-SA-4.0", True),
    (None, False),
    ("", False),
])
def test_open_license(expression: str | None, expected: bool) -> None:
    assert open_license(expression) is expected


@pytest.mark.parametrize(("text", "expected"), [
    ("Note: Riff requires a Spotify Premium account.", True),
    ("You must have an existing premium Spotify subscription to use it.", True),
    ("Login required.", True),
    ("Works offline. No account required.", False),
    ("You don't need a YouTube account to use NewPipe.", False),
    ("No subscription, no watermark, and no account required.", False),
    ("Track the balance of your bank accounts.", False),
])
def test_needs_account_only_on_a_stated_requirement(text: str, expected: bool) -> None:
    assert needs_account(text) is expected


def test_github_repo_skips_packaging_accounts() -> None:
    assert github_repo("https://github.com/flathub/org.example.App", "https://github.com/me/app/issues") == "me/app"
    assert github_repo(None, "https://gitlab.gnome.org/World/app") is None


def test_percentile_is_nearest_rank() -> None:
    assert percentile([1, 2, 3, 4, 5], 0.25) == 2
    assert percentile([1, 2, 3, 4, 5], 0.75) == 4
    assert percentile([7], 0.5) == 7


# --- Flathub catalog --------------------------------------------------------------------------

CATALOG = """<?xml version="1.0" encoding="UTF-8"?>
<components version="0.8" origin="flatpak">
  <component type="desktop-application">
    <id>io.github.me.Tally</id>
    <name>Tally</name>
    <name xml:lang="de">Zähler</name>
    <summary>Count things offline</summary>
    <project_license>GPL-3.0-or-later</project_license>
    <description>
      <p>Tally counts things.</p>
      <p xml:lang="de">Tally zählt Dinge.</p>
      <ul><li>Fast</li><li>Small</li></ul>
    </description>
    <developer><name>Me</name></developer>
    <url type="homepage">https://tally.example.org</url>
    <url type="vcs-browser">https://github.com/me/tally</url>
    <categories><category>Utility</category></categories>
    <releases>
      <release version="1.0" timestamp="1700000000"/>
      <release version="1.2" timestamp="1790000000"><description><p>Faster.</p></description></release>
      <release version="2.0-beta" timestamp="1795000000" type="development"/>
    </releases>
    <bundle type="flatpak" runtime="org.gnome.Platform/x86_64/49">app/io.github.me.Tally/x86_64/stable</bundle>
    <custom><value key="flathub::verification::verified">true</value></custom>
  </component>
  <component type="runtime"><id>org.gnome.Platform</id><name>GNOME</name></component>
  <component type="console-application"><id>org.example.cli</id><name>cli</name></component>
</components>
"""


def test_parse_catalog_keeps_untranslated_text_and_the_newest_stable_release() -> None:
    listings = flathub.parse_catalog(gzip.compress(CATALOG.encode()))
    assert [(x.item_id, x.kind) for x in listings] == [("io.github.me.Tally", "gui"), ("org.example.cli", "other")]
    x = listings[0]
    assert x.name == "Tally" and x.summary == "Count things offline"
    assert x.description == "Tally counts things.\n- Fast\n- Small"
    assert (x.version, x.released_at) == ("1.2", "2026-09-21T14:13:20Z")
    assert x.facts["release_notes"] == "Faster."
    assert (x.github, x.upstream) == ("me/tally", "https://github.com/me/tally")
    assert x.url == "https://flathub.org/apps/io.github.me.Tally"
    assert x.install_command == "flatpak install flathub io.github.me.Tally"
    assert x.facts["developer"] == "Me" and x.facts["verified_developer"] is True


def test_a_broken_catalog_raises() -> None:
    with pytest.raises(flathub.FlathubError):
        flathub.parse_catalog(b"not gzip")


# --- Homebrew Cask -------------------------------------------------------------------------------


def a_cask(token: str, *, url: str = "https://github.com/me/tally/releases/download/v1/Tally.dmg",
           artifacts: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
    return {"token": token, "name": [token.title()], "desc": "Count things", "homepage": "https://tally.example.org",
            "url": url, "version": "1.2", "artifacts": artifacts or [{"app": ["Tally.app"]}, {"zap": []}],
            "deprecated": False, "disabled": False, "depends_on": {"macos": {">=": ["13"]}}, **extra}


def test_cask_kinds_from_artifacts() -> None:
    assert cask.cask_kind(a_cask("a")) == "gui"
    assert cask.cask_kind(a_cask("b", artifacts=[{"binary": ["bin/b"]}])) == "cli"
    assert cask.cask_kind(a_cask("c", artifacts=[{"pkg": ["c.pkg"]}, {"uninstall": []}])) == "installer"
    assert cask.cask_kind(a_cask("d", artifacts=[{"font": ["d.ttf"]}])) == "other"


def test_cask_listing_and_install_counts() -> None:
    report = {"items": [{"cask": "tally", "count": "1,234"}, {"cask": "tally", "count": "6"}]}
    counts = cask.install_counts(report)
    assert counts == {"tally": 1240}
    [x] = cask.parse([a_cask("tally", deprecated=True)], {"30d": {"tally": 9}, "365d": counts})
    assert x.github == "me/tally" and x.kind == "gui" and x.deprecated
    assert x.installs == {"30d": 9, "90d": 0, "365d": 1240}
    assert x.install_command == "brew install --cask tally"
    assert x.url == "https://formulae.brew.sh/cask/tally"


# --- one run against a store ---------------------------------------------------------------------


def gql_node(repo_id: int, full_name: str, *, stars: int = 100, license: str | None = "MIT",
             pushed: str = "2026-10-20T00:00:00Z", archived: bool = False) -> dict[str, Any]:
    owner, name = full_name.split("/")
    return {"databaseId": repo_id, "nameWithOwner": full_name, "name": name, "url": f"https://github.com/{full_name}",
            "description": "An app", "homepageUrl": None, "primaryLanguage": {"name": "Rust"},
            "repositoryTopics": {"nodes": [{"topic": {"name": "gtk"}}]}, "stargazerCount": stars,
            "forkCount": 1, "issues": {"totalCount": 2}, "pullRequests": {"totalCount": 1},
            "createdAt": "2024-01-01T00:00:00Z", "updatedAt": pushed, "pushedAt": pushed,
            "isArchived": archived, "isDisabled": False, "isFork": False, "isTemplate": False,
            "defaultBranchRef": {"name": "main"}, "diskUsage": 10, "hasIssuesEnabled": True,
            "owner": {"login": owner}, "licenseInfo": {"spdxId": license} if license else None}


class StoreGitHub(FakeGitHub):
    """GraphQL repository lookups from `nodes` (lowercased owner/name), and REST details."""

    def __init__(self, nodes: dict[str, dict[str, Any]]) -> None:
        super().__init__(self.answer)
        self.nodes = nodes

    def answer(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path == "/graphql":
            query = json.loads(request.content)["query"]
            data = {alias: self.nodes.get(f"{owner}/{name}".lower()) for alias, owner, name in
                    re.findall(r'(r\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)', query)}
            return json_response({"data": data, "errors": [{"type": "NOT_FOUND"}] if None in data.values() else []})
        if path.endswith("/readme"):
            return json_response({"encoding": "base64", "path": "README.md",
                                  "content": base64.b64encode(b"# App\n## Install\nflatpak install").decode()})
        if path.endswith("/releases"):
            return json_response([])
        if "/git/trees/" in path:
            return json_response({"tree": [{"path": "src/main.rs", "type": "blob"}], "truncated": False})
        return json_response({}, 404)


def listing(item_id: str, github: str | None, **extra: Any) -> Listing:
    base = {"source": "flathub", "item_id": item_id, "name": item_id.rsplit(".", 1)[-1],
            "url": f"https://flathub.org/apps/{item_id}", "kind": "gui", "summary": "An app",
            "license": "MIT", "github": github, "released_at": "2026-10-01T00:00:00Z"}
    return Listing(**{**base, **extra})


def test_search_store_applies_the_rules_in_order_and_merges_known_repos(tmp_path: Path) -> None:
    db = PipelineDB(tmp_path / "pipeline.db")
    db.upsert_repo(normalize_repo(repo_item(7, "Old/Seven")), category="local_ai", query_id="local_ai:ollama")
    nodes = {f"me/app{i}": gql_node(100 + i, f"me/app{i}", stars=10 * i) for i in range(1, 6)}
    nodes["old/seven"] = gql_node(7, "New/Seven", stars=30)  # renamed since GitHub search found it
    nodes["me/gone"] = gql_node(9, "me/gone", archived=True)
    gh = StoreGitHub(nodes)
    apps = [listing(f"a.app{i}", f"me/app{i}") for i in range(1, 6)] + [
        listing("a.seven", "Old/Seven"),
        listing("a.closed", "me/app1", license="LicenseRef-proprietary"),
        listing("a.stale", "me/app1", released_at="2024-01-01T00:00:00Z"),
        listing("a.paid", "me/app1", description="Requires a Foo Premium account."),
        listing("a.gitlab", None),
        listing("a.missing", "me/nothing"),
        listing("a.archived", "me/gone"),
        listing("a.font", "me/app1", kind="other"),
    ]
    stats = search_store("flathub", apps, gh.client(tmp_path), db, catalog="catalog", now=NOW, run_id="r1",
                         log=lambda line: None)
    out = {x["item_id"]: x for x in db.listings("flathub")}
    assert {k: v["outcome"] for k, v in out.items() if not k.startswith("a.app")} == {
        "a.seven": "candidate", "a.closed": "not_open_source", "a.stale": "unmaintained",
        "a.paid": "needs_account", "a.gitlab": "no_popularity_signal", "a.missing": "repo_missing",
        "a.archived": "unmaintained", "a.font": "not_software"}
    # Stars 10..50 and 30: P25 = 20, P75 = 40.
    assert stats.band == (20, 40)
    assert [out[f"a.app{i}"]["outcome"] for i in range(1, 6)] == [
        "below_band", "candidate", "candidate", "candidate", "above_band"]
    assert (stats.repos_new, stats.repos_known) == (3, 1)
    seven = db.candidate("gh:7")
    assert seven["full_name"] == "New/Seven" and "Old/Seven" in seven["aliases"]
    assert seven["queries"] == ["local_ai:ollama", "flathub:a.seven"]
    assert seven["category"] == "local_ai"  # a store adds "other", which never wins
    assert [x["item_id"] for x in seven["listings"]] == ["a.seven"]
    assert out["a.seven"]["known_before"] is True and out["a.app3"]["known_before"] is False
    assert db.candidate("gh:101") is None  # below the band: recorded, not a candidate
    assert _channels(seven["queries"]) == {"github_search", "flathub"}
    funnel = db.funnel()
    assert funnel["discover"]["listings"]["flathub"]["repos"] == 4
    assert funnel["discover"]["listings"]["flathub"]["repos_new"] == 3
    assert funnel["discover"]["by_channel"]["flathub"] == 4
    [query] = funnel["discover"]["queries"]
    assert query["query_id"] == "flathub" and "between P25 and P75 = 20..40" in query["q"]
    # A second run keeps whether a repo was known at first sight.
    search_store("flathub", apps, gh.client(tmp_path), db, catalog="catalog", now=NOW, run_id="r2",
                 log=lambda line: None)
    assert {x["item_id"]: x["known_before"] for x in db.listings("flathub")}["a.app3"] is False


def test_cask_rules_use_github_license_pushes_and_installs(tmp_path: Path) -> None:
    db = PipelineDB(tmp_path / "pipeline.db")
    nodes = {"me/ok": gql_node(1, "me/ok"), "me/nolicense": gql_node(2, "me/nolicense", license=None),
             "me/old": gql_node(3, "me/old", pushed="2024-05-01T00:00:00Z")}
    gh = StoreGitHub(nodes)

    def a(token: str, repo: str | None, **extra: Any) -> Listing:
        return Listing(**{"source": "homebrew_cask", "item_id": token, "name": token, "kind": "cli",
                          "url": f"https://formulae.brew.sh/cask/{token}", "github": repo,
                          "installs": {"30d": 5, "90d": 20, "365d": 80}, **extra})

    apps = [a("ok", "me/ok"), a("nolicense", "me/nolicense"), a("old", "me/old"), a("closed", None),
            a("ok@beta", "me/ok"), a("idle", "me/ok", installs={"30d": 0, "90d": 0, "365d": 80}),
            a("gone", "me/ok", deprecated=True)]
    search_store("homebrew_cask", apps, gh.client(tmp_path), db, catalog="cask.json", now=NOW, run_id="r1",
                 log=lambda line: None)
    assert {x["item_id"]: x["outcome"] for x in db.listings("homebrew_cask")} == {
        "ok": "candidate", "nolicense": "not_open_source", "old": "unmaintained", "closed": "license_unknown",
        "ok@beta": "variant", "idle": "unused", "gone": "deprecated"}


def test_pick_is_a_seeded_order_with_one_app_per_repo(tmp_path: Path) -> None:
    db = PipelineDB(tmp_path / "pipeline.db")
    nodes = {f"me/app{i}": gql_node(100 + i, f"me/app{i}", stars=50) for i in range(6)}
    apps = [listing(f"a.app{i}", f"me/app{i}") for i in range(6)] + [listing("a.twin", "me/app0")]
    search_store("flathub", apps, StoreGitHub(nodes).client(tmp_path), db, catalog="c", now=NOW, run_id="r",
                 log=lambda line: None)
    first = [x["item_id"] for x in pick(db, "flathub", 3, "s1")]
    assert first == [x["item_id"] for x in pick(db, "flathub", 3, "s1")]
    assert first != [x["item_id"] for x in pick(db, "flathub", 3, "s2")]
    every = pick(db, "flathub", 10, "s1")
    assert len(every) == 6 and len({x["repo_id"] for x in every}) == 6


def test_store_channel_fetches_details_only_for_the_pick(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "pipeline.db"
    db = PipelineDB(db_path)
    db.upsert_repo(normalize_repo(repo_item(1, "other/tool")), category="dev_cli", query_id="dev_cli:cli")
    nodes = {f"me/app{i}": gql_node(100 + i, f"me/app{i}", stars=50) for i in range(4)}
    apps = [listing(f"a.app{i}", f"me/app{i}") for i in range(4)]
    monkeypatch.setattr(flathub, "fetch_catalog", lambda http=None: b"")
    monkeypatch.setattr(flathub, "parse_catalog", lambda data: apps)
    gh = StoreGitHub(nodes)
    funnel = run_discover(token="x", db_path=db_path, channel="flathub", gh=gh.client(tmp_path), now=NOW,
                          pick_n=2, seed="s", log=lambda line: None)
    assert len(funnel["pick"]) == 2 and all(p["rule_passed"] for p in funnel["pick"])
    assert funnel["flathub"]["candidates"] == 4
    readmes = {r.url.path for r in gh.requests if r.url.path.endswith("/readme")}
    assert readmes == {f"/repos/{p['repo']}/readme" for p in funnel["pick"]}  # not other/tool, not the rest
    assert PipelineDB(db_path).candidate("gh:1")["details_at"] is None


# --- store and rules -------------------------------------------------------------------------------


def test_needs_details_is_for_github_rows_only(tmp_path: Path) -> None:
    db = PipelineDB(tmp_path / "pipeline.db")
    db.upsert_repo(normalize_repo(repo_item(1)), category="dev_cli", query_id="q")
    with db._write() as conn:
        conn.execute("INSERT INTO candidates (repo_id, full_name, category, repo, first_seen_at, last_seen_at) "
                     "VALUES ('flathub:org.example.App', 'org.example.App', 'other', '{}', 't', 't')")
    assert [r["repo_id"] for r in db.needs_details()] == ["gh:1"]


def test_a_listed_repo_has_a_strong_tool_signal_and_needs_no_readme() -> None:
    c = {"repo": normalize_repo(repo_item(1, description="A GTK app")), "readme": None, "files": ["src/main.vala"],
         "files_truncated": False, "manifests": {}, "releases": [],
         "listings": [{"source": "flathub", "item_id": "a.b"}]}
    result = classify(c)
    assert result.passed and result.label == "tool"
    assert "+listed:flathub" in result.reasons
    assert classify({**c, "listings": []}).reasons == ["reject:no_readme"]
