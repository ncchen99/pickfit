"""pickfit harvest: leads from fake sources, dedup against records, and the feed into D1."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from pickfit.discover.store import PipelineDB
from pickfit.harvest import check, sources
from pickfit.harvest.leads import Hit, LeadsDB, known_keys, priority
from pickfit.harvest.run import default_sources, feed, run_harvest
from pickfit.watch import HARVEST_ID_PREFIX, submission_source
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
    dry = feed(database, n=10, hourly_cap=20, apply=False, db_path=tmp_path / "h.db", now=NOW, screened_only=False,
               log=lambda s: None)
    assert len(dry) == 3  # 20 - 5 reserve - 12 this hour
    assert database.query("SELECT count(*) AS n FROM submissions")[0]["n"] == 13  # dry run wrote nothing
    rows = feed(database, n=10, hourly_cap=20, apply=True, db_path=tmp_path / "h.db", now=NOW, screened_only=False,
                log=lambda s: None)
    urls = {r["url"] for r in rows}
    assert "https://github.com/o/b" not in urls and len(rows) == 3  # o/b was submitted before
    assert all(u == u.lower() for u in urls)
    queued = database.query("SELECT id, url, note FROM submissions WHERE note LIKE 'harvest:%'")
    assert len(queued) == 3 and queued[0]["note"] == "harvest: npm"
    # The watch tells harvest rows from people's by this prefix (HARVEST_ID_PREFIX), and the status page still takes them.
    assert all(q["id"].startswith(HARVEST_ID_PREFIX) and re.fullmatch(r"sub_[a-z0-9]{1,64}", q["id"]) for q in queued)
    assert {r["id"] for r in rows} == {q["id"] for q in queued}
    assert {submission_source(q) for q in queued} == {"harvest"} and submission_source({"id": "sub_p0"}) == "user"  # people's rows stay people's
    db = LeadsDB(tmp_path / "h.db")
    assert db.summary()["by_status"] == {"fed": 3, "known": 1, "new": 2}
    db.close()


def test_social_sources_join_when_keyed() -> None:
    assert "bluesky" not in default_sources({}) and "x" not in default_sources({})
    assert default_sources({"BSKY_HANDLE": "h", "BSKY_APP_PASSWORD": "p", "X_BEARER_TOKEN": "t"})[-2:] == ["bluesky", "x"]


def test_author_published_registries_are_one_voice() -> None:
    vendor = priority("mcp_server", [], [0.0] * 3, ["awesome", "mcp_registry", "npm"])
    assert vendor == priority("mcp_server", [], [0.0] * 2, ["awesome", "npm"])
    assert vendor < priority("mcp_server", [], [0.0] * 3, ["awesome", "homebrew", "npm"])
    assert priority("cli_tool", [], [0.0], ["awesome"], screen_keep=True) > priority(
        "cli_tool", [], [0.0, 0.0], ["awesome", "hn"])  # a kept screen beats one more voice
    assert priority("cli_tool", [], [0.0], ["awesome"], quiet=True) < priority("cli_tool", [], [0.0], ["awesome"])


class FakeGitHub:
    def __init__(self, repos: dict[str, dict | None]) -> None:
        self.data = repos
        self.asked: list[list[str]] = []

    def repos(self, names: list[str]) -> dict[str, dict | None]:
        self.asked.append(names)
        return {n: self.data.get(n) for n in names}


def _repo(full_name: str, pushed: str = "2026-11-01T00:00:00Z", **flags: bool) -> dict:
    return {"full_name": full_name, "html_url": f"https://github.com/{full_name}", "stargazers_count": 10,
            "pushed_at": pushed, "description": "a tool", **flags}


def test_check_skips_gone_archived_stale_and_merges_renames(tmp_path: Path) -> None:
    db = LeadsDB(tmp_path / "h.db")
    db.add([Hit("awesome", n, [f"https://github.com/o/{n}"], kind_hint="cli_tool")
            for n in ("gone", "arch", "fork", "old", "quiet", "moved", "new-name", "was-known", "ok")])
    db.add([Hit("npm", "moved", ["https://github.com/o/moved"], signal=5)])
    gh = FakeGitHub({"o/arch": _repo("o/arch", archived=True), "o/fork": _repo("o/fork", fork=True),
                     "o/old": _repo("o/old", pushed="2024-01-01T00:00:00Z"),
                     "o/quiet": _repo("o/quiet", pushed="2025-06-01T00:00:00Z"),
                     "o/moved": _repo("O/New-Name"), "o/new-name": _repo("O/New-Name"),
                     "o/was-known": _repo("o/recorded"), "o/ok": _repo("o/ok")})
    out = check.check(db, n=50, gh=gh, known={"gh:o/recorded": "record:rec"}, now=NOW, log=lambda s: None)
    assert out["gone"] == out["archived"] == out["fork"] == out["stale"] == 1 and out["renamed"] == 2
    status = dict(db.conn.execute("SELECT key, status FROM leads").fetchall())
    assert status["gh:o/moved"] == "skipped" and status["gh:o/new-name"] == "new"
    assert status["gh:o/recorded"] == "known"  # renamed onto something pickfit has
    ranked = {r["key"]: r for r in db.ranked(quiet_before=check.quiet_before(NOW))}
    assert ranked["gh:o/new-name"]["sources"] == ["awesome", "npm"]  # the old name's sources moved over
    assert set(ranked) == {"gh:o/new-name", "gh:o/quiet", "gh:o/ok"}
    assert ranked["gh:o/quiet"]["priority"] < ranked["gh:o/ok"]["priority"]
    assert check.check(db, n=50, gh=gh, known={}, now=NOW, log=lambda s: None) == {}  # nothing left unchecked
    db.close()


def test_screen_stores_prescreens_and_feed_takes_only_kept(tmp_path: Path) -> None:
    db = LeadsDB(tmp_path / "h.db")
    db.add([Hit("awesome", n, [f"https://github.com/o/{n}"], kind_hint="cli_tool")
            for n in ("tool", "lib", "ruled", "rec")])
    gh = FakeGitHub({f"o/{n}": _repo(f"o/{n}") for n in ("tool", "lib", "ruled", "rec")})
    pipeline_db = tmp_path / "pipeline.db"
    PipelineDB(pipeline_db)

    def add(gh, pdb, names, *, data_dir, log):
        rows = []
        for i, name in enumerate(names):
            short = name.split("/")[1]
            rows.append({"name": name, "outcome": "added", "repo_id": f"gh:{i}", "full_name": name,
                         "record": "rec-slug" if short == "rec" else None,
                         "rule_passed": short != "ruled", "rule_label": "reject" if short == "ruled" else "pass"})
        return rows

    def prescreen(*, limit, repo_ids, review, concurrency, db_path, log):
        pdb = PipelineDB(db_path)
        for repo_id in repo_ids:
            name = next(r for r in add(None, None, sorted(gh.data), data_dir=None, log=None)
                        if r["repo_id"] == repo_id)["name"]
            keep = name.endswith("tool")
            pdb.save_prescreen(repo_id=repo_id, run_id="r", role="screen", provider="anthropic", model="haiku",
                               reasoning_effort="low", status="ok", sources_sha="s",
                               result={"kind": "cli_tool" if keep else "library", "reason": "why"}, keep=keep,
                               review_reason=None, error=None, usage=None, cost_usd=0.0005, latency_s=1.0)
        return {"screened": len(repo_ids)}

    # names go to add() in rank order; make that order the same as sorted(gh.data) for the fake above
    out = check.screen(db, n=10, gh=gh, known={}, pipeline_db=pipeline_db, data_dir=tmp_path, now=NOW,
                       add=lambda gh_, pdb, names, **kw: add(gh_, pdb, sorted(names), **kw),
                       prescreen=prescreen, log=lambda s: None)
    assert out["screened"] == {"kept": 1, "dropped": 1, "rules": 1, "known": 1}
    status = dict(db.conn.execute("SELECT key, status_note FROM leads").fetchall())
    assert status["gh:o/lib"] == "prescreen:library" and status["gh:o/ruled"] == "rules:reject"
    assert status["gh:o/rec"] == "record:rec-slug"
    # The candidate harvest stored for screening does not make the kept lead "known".
    assert db.mark_known({"gh:o/tool": "candidate"}) == 0
    db.close()
    database = d1(tmp_path)
    rows = feed(database, n=10, hourly_cap=20, apply=False, db_path=tmp_path / "h.db", now=NOW, log=lambda s: None)
    assert [r["url"] for r in rows] == ["https://github.com/o/tool"]
