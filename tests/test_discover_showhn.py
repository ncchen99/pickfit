"""Show HN discovery with mocked HN and GitHub APIs: no request ever leaves the process."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest

from pickfit.discover import showhn
from pickfit.discover.github import normalize_repo
from pickfit.discover.run import run_discover
from pickfit.discover.showhn import (
    HN,
    linked_repo,
    plain_text,
    post_categories,
    to_post,
)
from pickfit.discover.store import PipelineDB
from tests.test_discover import FakeGitHub, json_response, repo_item

TOKEN = "gho_test0123456789SECRET"
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
DAY = 86_400


@pytest.fixture(autouse=True)
def no_hn_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(showhn, "sleep", lambda s: None)


def hit(item_id: int, title: str, url: str | None = None, text: str | None = None, *,
        days_ago: float = 1, points: int = 3) -> dict[str, Any]:
    return {"objectID": str(item_id), "title": title, "url": url, "story_text": text, "points": points,
            "num_comments": 1, "created_at_i": int(NOW.timestamp() - days_ago * DAY), "author": "someone"}


# --- filters ---------------------------------------------------------------------


@pytest.mark.parametrize(("title", "text", "expected"), [
    ("Show HN: Ferret – an MCP server for your notes", "", ["mcp_server"]),
    ("Show HN: A Model Context Protocol bridge with a CLI", "", ["mcp_server", "dev_cli"]),
    ("Show HN: Wordmate – local speech-to-text for macOS", "", ["local_ai"]),
    ("Show HN: Run GGUF models from one binary", "", ["local_ai"]),
    ("Show HN: Hush", "Transcribes meetings offline with Whisper.", ["local_ai"]),
    ("Show HN: tuisheet, a terminal spreadsheet", "", ["dev_cli"]),
    ("Show HN: A cozy home for your Goodreads books", "", []),
    # "AI" or "agent" with a local word is not enough: the definition is about running models.
    ("Show HN: A self-hosted contact manager with AI search", "", []),
])
def test_post_categories_follow_the_category_definitions(title: str, text: str, expected: list[str]) -> None:
    assert post_categories(title, text) == expected


def test_linked_repo_prefers_the_link_and_strips_noise() -> None:
    assert linked_repo("Show HN: tinyq", "https://github.com/someone/tinyq.git", None) == "someone/tinyq"
    assert linked_repo("Show HN: x", "https://github.com/someone/tinyq/tree/main/cli", None) == "someone/tinyq"
    assert linked_repo("Show HN: x", "https://www.github.com/a/b.", "see https://github.com/c/d") == "a/b"
    assert linked_repo("Show HN: x", "https://github.com/marketplace/actions", None) is None
    assert linked_repo("Show HN: x", "https://example.com", None) is None


def test_a_repo_in_the_text_counts_when_alone_or_named_in_the_title() -> None:
    assert linked_repo("Show HN: Fraise", "https://getfraise.dev", "Code: https://github.com/FraiseHQ/fraise") \
        == "FraiseHQ/fraise"
    text = "Built on https://github.com/ggml-org/llama.cpp. Source: https://github.com/me/hush-app"
    assert linked_repo("Show HN: Hush App – offline notes", None, text) == "me/hush-app"
    # Two repos, neither named in the title: could be what it is built on, so none.
    assert linked_repo("Show HN: My weekend thing", None, text) is None


def test_plain_text_unescapes_hn_html_and_keeps_link_targets() -> None:
    raw = ('Source: <a href="https:&#x2F;&#x2F;github.com&#x2F;me&#x2F;hush" rel="nofollow">'
           'https:&#x2F;&#x2F;github.com&#x2F;me&#x2F;hu...</a><p>Runs offline')
    text = plain_text(raw)
    assert "https://github.com/me/hush " in text and "Runs offline" in text
    assert to_post(hit(1, "Show HN: Hush", None, raw)).repo == "me/hush"


# --- the HN client ----------------------------------------------------------------


class FakeHN:
    """Algolia and Firebase from a list of hits and a dict of items; records every request."""

    def __init__(self, hits: list[dict[str, Any]], items: dict[str, dict[str, Any] | None] | None = None,
                 fail_first: int = 0) -> None:
        self.hits, self.items, self.fail_first = hits, items or {}, fail_first
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.fail_first:
            self.fail_first -= 1
            return httpx2.Response(503)
        if request.url.host == "hn.algolia.com":
            assert request.url.params["tags"] == "show_hn"
            lo, hi = (int(f.split(">")[-1].split("=")[-1]) for f in request.url.params["numericFilters"].split(","))
            hits = [h for h in self.hits if lo < h["created_at_i"] <= hi]
            return json_response({"nbHits": len(hits), "hits": hits[:1000]})
        item_id = request.url.path.rsplit("/", 1)[1].removesuffix(".json")
        item = self.items.get(item_id, {"id": int(item_id), "score": 7, "descendants": 2})
        return json_response(item)

    def client(self, tmp_path: Path) -> HN:
        return HN(http=httpx2.Client(transport=httpx2.MockTransport(self)), trace_dir=tmp_path / "traces")


def test_show_hn_fetches_one_day_per_request_and_traces_it(tmp_path: Path) -> None:
    fake = FakeHN([hit(1, "a", days_ago=0.5), hit(2, "b", days_ago=2.5)])
    hn = fake.client(tmp_path)
    since, until = showhn.window(NOW, 3)
    assert [h["objectID"] for h in hn.show_hn(since, until)] == ["2", "1"]
    assert len(fake.requests) == 3
    trace = (tmp_path / "traces").glob("hn-*.jsonl")
    lines = [json.loads(line) for path in trace for line in path.read_text().splitlines()]
    assert [line["kind"] for line in lines] == ["algolia"] * 3 and all(line["status"] == 200 for line in lines)


def test_a_slice_over_the_page_limit_is_split(tmp_path: Path) -> None:
    hits = [hit(i, f"t{i}", days_ago=0.5 + i / 10_000) for i in range(1, 1201)]
    fake = FakeHN(hits)
    since, until = showhn.window(NOW, 1)
    assert len(list(fake.client(tmp_path).show_hn(since, until))) == 1200
    assert len(fake.requests) >= 3


def test_server_errors_are_retried(tmp_path: Path) -> None:
    fake = FakeHN([hit(1, "a")], fail_first=2)
    since, until = showhn.window(NOW, 2)
    assert len(list(fake.client(tmp_path).show_hn(since, until))) == 1


def test_client_errors_are_not_retried(tmp_path: Path) -> None:
    hn = HN(http=httpx2.Client(transport=httpx2.MockTransport(lambda r: httpx2.Response(400))),
            trace_dir=tmp_path / "traces")
    with pytest.raises(showhn.HNError):
        hn.item("1")
    assert hn.requests["firebase"] == 1


# --- end to end ---------------------------------------------------------------------


def github_route(repos: dict[str, dict[str, Any] | None]):
    readme = base64.b64encode(b"# tool\n\n## Install\n\n`cargo install tool`\n").decode()

    def route(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path.startswith("/repos/") and path.count("/") == 3:
            item = repos.get(path.removeprefix("/repos/").lower())
            return json_response(item) if item else json_response({"message": "Not Found"}, 404)
        if path.endswith("/readme"):
            return json_response({"path": "README.md", "encoding": "base64", "content": readme})
        if path.endswith("/releases"):
            return json_response([])
        if "/git/trees/" in path:
            return json_response({"tree": [{"path": "src/main.rs", "type": "blob"}], "truncated": False})
        raise AssertionError(path)
    return route


def test_run_discover_show_hn_end_to_end(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"
    db = PipelineDB(db_path)
    # Already in the pool under its current name, found earlier by a GitHub search.
    db.upsert_repo(normalize_repo(repo_item(10, "old/known")), category="dev_cli", query_id="dev_cli:cli")
    db.upsert_repo(normalize_repo(repo_item(10, "new/known")), category="dev_cli", query_id="dev_cli:cli")
    hits = [
        hit(1, "Show HN: Ferret – an MCP server for notes", "https://github.com/me/ferret"),
        hit(2, "Show HN: Known – a terminal tool", "https://github.com/old/known"),  # an earlier name
        hit(3, "Show HN: Ferret again, now a CLI too", "https://github.com/me/ferret", days_ago=0.5),
        hit(4, "Show HN: A cozy home for your books", "https://github.com/me/books"),  # no category words
        hit(5, "Show HN: Ghost – a TUI", "https://github.com/me/ghost"),  # killed after indexing
        hit(6, "Show HN: Famous – a CLI", "https://github.com/big/famous"),  # too many stars
        hit(7, "Show HN: Gone – a CLI", "https://github.com/me/gone"),  # repo deleted
        hit(8, "Show HN: A blog post about CLIs", "https://example.com/post"),  # no repo
        hit(9, "Show HN: Old – a CLI", "https://github.com/me/old", days_ago=40),  # outside the window
    ]
    fake_hn = FakeHN(hits, items={"5": {"id": 5, "dead": True}})
    repos = {"me/ferret": repo_item(1, "me/ferret"), "old/known": repo_item(10, "new/known"),
             "me/ghost": repo_item(5, "me/ghost"), "big/famous": repo_item(6, "big/famous", stargazers_count=5000),
             "me/old": repo_item(9, "me/old")}
    fake_gh = FakeGitHub(github_route(repos))
    lines: list[str] = []
    funnel = run_discover(token=TOKEN, db_path=db_path, channel="show_hn", days=30, now=NOW,
                          gh=fake_gh.client(tmp_path), hn=fake_hn.client(tmp_path), log=lines.append)

    summary = funnel["show_hn"]
    assert summary["posts"] == 8 and summary["github_repo"] == 7 and summary["category_words"] == 6
    assert summary["by_outcome"] == {"candidate": 3, "dead_or_deleted": 1, "too_popular": 1, "repo_missing": 1}
    assert (summary["repos_new"], summary["repos_known"]) == (1, 1)

    known = db.candidate("gh:10")
    assert "show_hn:dev_cli" in known["queries"] and known["aliases"] == ["old/known"]
    ferret = db.candidate("gh:1")
    assert ferret["category"] == "mcp_server" and ferret["categories"] == ["mcp_server", "dev_cli"]
    assert ferret["queries"] == ["show_hn:mcp_server", "show_hn:dev_cli"]
    assert db.candidate("gh:6") is None and db.candidate("gh:5") is None

    by_item = {h["item_id"]: h for h in db.channel_hits("show_hn")}
    assert by_item["1"]["item_url"] == "https://news.ycombinator.com/item?id=1"
    assert (by_item["1"]["repo_id"], by_item["1"]["known_before"], by_item["1"]["points"]) == ("gh:1", False, 7)
    assert by_item["3"]["known_before"] is False  # same repo, same run: still new to the pool
    assert (by_item["2"]["repo_id"], by_item["2"]["known_before"]) == ("gh:10", True)
    assert {h["outcome"] for h in by_item.values()} == {"candidate", "dead_or_deleted", "too_popular", "repo_missing"}
    assert "4" not in by_item and "8" not in by_item

    queries = {q["query_id"]: q for q in funnel["discover"]["queries"]}
    assert queries["show_hn:mcp_server"]["returned"] == 1 and queries["show_hn:mcp_server"]["new"] == 1
    assert queries["show_hn:dev_cli"]["returned"] == 2 and queries["show_hn:dev_cli"]["new"] == 0
    assert "tags=show_hn" in queries["show_hn:local_ai"]["q"] and queries["show_hn:local_ai"]["total_count"] == 8
    assert funnel["discover"]["by_channel"] == {"github_search": 1, "show_hn": 2}
    assert funnel["discover"]["channel_posts"]["show_hn"] == {"posts": 3, "repos": 2, "repos_new": 1}
    assert funnel["rules"]["checked"] == 2  # details fetched for both candidates
    # One GitHub repo lookup per distinct linked name, never the HN text.
    repo_calls = [r for r in fake_gh.requests if r.url.path.count("/") == 3 and r.url.path.startswith("/repos/")]
    assert len(repo_calls) == 4  # ferret (twice), known, famous, gone; not the dead post
    assert any(line.startswith("hn requests:") for line in lines)

    # A second run refreshes the same posts: no new candidates, provenance unchanged.
    again = run_discover(token=TOKEN, db_path=db_path, channel="show_hn", days=30, now=NOW,
                         gh=fake_gh.client(tmp_path), hn=fake_hn.client(tmp_path), log=lines.append)
    assert again["show_hn"]["repos_new"] == 0 and again["show_hn"]["repos_known"] == 2
    assert {h["item_id"]: h["known_before"] for h in db.channel_hits("show_hn")} == \
        {item_id: h["known_before"] for item_id, h in by_item.items()}


def test_unknown_channel_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_discover(token=TOKEN, db_path=tmp_path / "p.db", channel="reddit")
