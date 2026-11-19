"""pickfit harvest: leads from fake sources, dedup against records, and the feed into D1."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from pickfit.harvest import sources
from pickfit.harvest.leads import Hit, LeadsDB, known_keys, priority
from pickfit.harvest.run import default_sources, feed, run_harvest
from tests.queue_fakes import d1, submit

NOW = datetime(2026, 11, 19, 4, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources, "sleep", lambda s: None)


def test_hit_keys() -> None:
    assert Hit("s", "1", ["git+ssh://git@github.com/Foo/Bar.git"]).key_url() == ("gh:foo/bar", "https://github.com/Foo/Bar")
    assert Hit("s", "1", ["git@github.com:a/b"]).key_url() == ("gh:a/b", "https://github.com/a/b")
    assert Hit("s", "1", ["https://example.com/app"]).key_url() is None  # not a web app source
    assert Hit("s", "1", ["https://Example.com/app/"], allow_web=True).key_url() == (
        "web:https://example.com/app", "https://example.com/app")
    assert Hit("s", "1", ["https://github.com/topics/cli"]).key_url() is None


def test_merge_sources_and_rank(tmp_path: Path) -> None:
    db = LeadsDB(tmp_path / "h.db")
    db.add([Hit("npm", "x", ["https://github.com/o/x"], signal=10),
            Hit("awesome", "l:o/x", ["https://github.com/o/x"], kind_hint="cli_tool", platforms=["linux"]),
            Hit("crates", "y", ["https://github.com/o/y"], kind_hint="desktop_app", platforms=["windows"]),
            Hit("hn", "1", ["https://site.example.org"], allow_web=True, kind_hint="web_app")])
    ranked = db.ranked()
    assert [r["key"] for r in ranked][0] == "gh:o/x"  # two sources, cli, linux
    x = ranked[0]
    assert x["kind_hint"] == "cli_tool" and x["sources"] == ["awesome", "npm"] and x["platforms"] == ["linux"]
    # A lead with no platform hint is kept by any platform filter.
    assert {r["key"] for r in db.ranked(platforms={"windows"})} == {"gh:o/y", "web:https://site.example.org/"}
    assert priority("mcp_server", [], [0.0], ["awesome"]) > priority("desktop_app", ["macos"], [0.0], ["awesome"])
    # The most downloaded npm package alone ranks below the same kind seen by two sources.
    assert priority("cli_tool", [], [1.0], ["npm"]) < priority("cli_tool", [], [0.0, 0.0], ["awesome", "hn"])
    db.close()


def test_known_keys_and_mark(tmp_path: Path) -> None:
    data = tmp_path / "software"
    data.mkdir()
    (data / "a.json").write_text(json.dumps({"slug": "a", "repo": {"full_name": "O/A"}}))
    (data / "w.json").write_text(json.dumps({"slug": "w", "repo": None, "web": {"url": "https://w.example.org"}}))
    known = known_keys(data, None)
    assert known == {"gh:o/a": "record:a", "web:https://w.example.org/": "record:w"}
    db = LeadsDB(tmp_path / "h.db")
    db.add([Hit("npm", "a", ["https://github.com/o/a"]), Hit("npm", "b", ["https://github.com/o/b"])])
    assert db.mark_known(known) == 1
    assert [r["key"] for r in db.ranked()] == ["gh:o/b"]
    db.close()


def _client(routes: dict[str, object]) -> httpx2.Client:
    def handler(request: httpx2.Request) -> httpx2.Response:
        for prefix, body in routes.items():
            if str(request.url).startswith(prefix):
                body = body(request) if callable(body) else body
                return httpx2.Response(200, json=body)
        return httpx2.Response(404)
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def test_mcp_registry_pages_and_checkpoint(tmp_path: Path) -> None:
    calls = []

    def registry(request: httpx2.Request) -> dict:
        calls.append(dict(request.url.params))
        if "cursor" not in request.url.params:
            return {"servers": [{"server": {"name": "io.github.o/a", "repository": {"url": "https://github.com/o/a"}}},
                                {"server": {"name": "x/gone", "repository": {"url": "https://github.com/o/gone"}},
                                 "_meta": {"io.modelcontextprotocol.registry/official": {"status": "deleted"}}}],
                    "metadata": {"nextCursor": "io.github.o/a:1"}}
        return {"servers": [{"server": {"name": "remote/only", "remotes": [{"url": "https://r.example"}]}}],
                "metadata": {}}

    report = run_harvest(["mcp_registry"], db_path=tmp_path / "h.db", data_dir=tmp_path, pipeline_db=None, now=NOW,
                         http=_client({sources.MCP_REGISTRY: registry}), env={}, log=lambda s: None)
    assert report["sources"]["mcp_registry"] == {"hits": 1, "new_leads": 1, "requests": 2, "error": None}
    db = LeadsDB(tmp_path / "h.db")
    assert db.get_state("mcp_registry.updated_since") == "2026-11-19T03:50:00Z"
    assert db.ranked()[0]["kind_hint"] == "mcp_server"
    db.close()
    run_harvest(["mcp_registry"], db_path=tmp_path / "h.db", data_dir=tmp_path, pipeline_db=None, now=NOW,
                http=_client({sources.MCP_REGISTRY: registry}), env={}, log=lambda s: None)
    assert calls[-2]["updated_since"] == "2026-11-19T03:50:00Z"


def test_failing_source_does_not_stop_the_run(tmp_path: Path) -> None:
    report = run_harvest(["crates", "x"], db_path=tmp_path / "h.db", data_dir=tmp_path, pipeline_db=None, now=NOW,
                         http=_client({sources.CRATES: {"crates": [
                             {"id": "tool", "repository": "https://github.com/o/tool", "recent_downloads": 50}]}}),
                         env={}, log=lambda s: None)
    assert report["sources"]["crates"]["new_leads"] == 1
    assert "X_BEARER_TOKEN" in report["sources"]["x"]["error"]


def test_x_stays_within_paid_reads(tmp_path: Path) -> None:
    seen = []

    def search(request: httpx2.Request) -> dict:
        q = len(seen)
        seen.append(int(request.url.params["max_results"]))
        return {"data": [{"id": f"{q}-{i}", "public_metrics": {"like_count": 50 if i == 0 else 1},
                          "entities": {"urls": [{"expanded_url": f"https://github.com/o/r{q}-{i}"}]}}
                         for i in range(seen[-1])]}

    report = run_harvest(["x"], db_path=tmp_path / "h.db", data_dir=tmp_path, pipeline_db=None, now=NOW,
                         http=_client({sources.X_SEARCH: search}), env={"X_BEARER_TOKEN": "t"}, x_max_reads=50,
                         log=lambda s: None)
    assert sum(seen) <= 50
    assert report["sources"]["x"]["new_leads"] == len(seen)  # one liked post per query


def test_bluesky_keeps_only_github_links(tmp_path: Path) -> None:
    post = {"uri": "at://did:plc:a/app.bsky.feed.post/3k", "author": {"handle": "a.bsky.social"}, "likeCount": 3,
            "record": {"facets": [{"features": [{"$type": "app.bsky.richtext.facet#link",
                                                 "uri": "https://github.com/o/tool"}]}]}}
    other = {"uri": "at://did:plc:b/app.bsky.feed.post/4k", "record": {}, "embed": {"external": {"uri": "https://x.org"}}}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("createSession"):
            return httpx2.Response(200, json={"accessJwt": "j"})
        return httpx2.Response(200, json={"posts": [post, other]})

    report = run_harvest(["bluesky"], db_path=tmp_path / "h.db", data_dir=tmp_path, pipeline_db=None, now=NOW,
                         http=httpx2.Client(transport=httpx2.MockTransport(handler)),
                         env={"BSKY_HANDLE": "h", "BSKY_APP_PASSWORD": "p"}, log=lambda s: None)
    assert report["sources"]["bluesky"]["new_leads"] == 1
    db = LeadsDB(tmp_path / "h.db")
    src = db.conn.execute("SELECT link, title FROM lead_sources").fetchone()
    assert tuple(src) == ("https://bsky.app/profile/a.bsky.social/post/3k", None)  # no post text kept
    db.close()


def test_feed_keeps_room_for_people(tmp_path: Path) -> None:
    database = d1(tmp_path)
    for i in range(12):
        submit(database, f"sub_p{i}", f"https://github.com/p/{i}", at="2026-11-19T03:30:00.000Z")
    submit(database, "sub_old", "https://github.com/o/b", at="2026-11-01T00:00:00.000Z")
    db = LeadsDB(tmp_path / "h.db")
    db.add([Hit("npm", n, [f"https://github.com/O/{n}"], kind_hint="cli_tool") for n in "abcdef"])
    db.close()
    dry = feed(database, n=10, hourly_cap=20, apply=False, db_path=tmp_path / "h.db", now=NOW, log=lambda s: None)
    assert len(dry) == 3  # 20 - 5 reserve - 12 this hour
    assert database.query("SELECT count(*) AS n FROM submissions")[0]["n"] == 13  # dry run wrote nothing
    rows = feed(database, n=10, hourly_cap=20, apply=True, db_path=tmp_path / "h.db", now=NOW, log=lambda s: None)
    urls = {r["url"] for r in rows}
    assert "https://github.com/o/b" not in urls and len(rows) == 3  # o/b was submitted before
    assert all(u == u.lower() for u in urls)
    queued = database.query("SELECT url, note FROM submissions WHERE note LIKE 'harvest:%'")
    assert len(queued) == 3 and queued[0]["note"] == "harvest: npm"
    db = LeadsDB(tmp_path / "h.db")
    assert db.summary()["by_status"] == {"fed": 3, "known": 1, "new": 2}
    db.close()


def test_social_sources_join_when_keyed() -> None:
    assert "bluesky" not in default_sources({}) and "x" not in default_sources({})
    assert default_sources({"BSKY_HANDLE": "h", "BSKY_APP_PASSWORD": "p", "X_BEARER_TOKEN": "t"})[-2:] == ["bluesky", "x"]
