"""`pickfit harvest probe`: fails a source that errors or names nothing, skips unkeyed social sources, runs the chain.

The live test at the end calls the real APIs (no screen, no D1); run it with PICKFIT_LIVE_HARVEST=1.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pickfit.harvest import probe as probe_mod
from pickfit.harvest import sources
from pickfit.harvest.leads import Hit
from pickfit.harvest.sources import SourceError
from tests.queue_fakes import d1

NOW = datetime(2026, 11, 19, 4, 0, tzinfo=UTC)


class FakeGitHub:
    def __init__(self) -> None:
        self.requests: Counter[str] = Counter()

    def repos(self, names: list[str]) -> dict:
        return {n: {"full_name": n, "html_url": f"https://github.com/{n}", "stargazers_count": 5,
                    "pushed_at": "2026-11-01T00:00:00Z"} for n in names}


def _fake_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    def good(ctx):
        yield from (Hit("good", str(i), [f"https://github.com/o/r{i}"], kind_hint="cli_tool") for i in range(40))

    def broken(ctx):
        raise SourceError("broken: GET https://api.example: HTTP 410")
        yield  # pragma: no cover

    def changed(ctx):  # answers, but nothing in it names software any more
        yield from (Hit("changed", str(i), ["https://example.com/not-a-repo"]) for i in range(5))

    monkeypatch.setattr(sources, "SOURCES", {"good": good, "broken": broken, "changed": changed,
                                             "bluesky": good, "x": good})
    monkeypatch.setattr(probe_mod, "SOURCES", sources.SOURCES)


def test_probe_reports_each_source(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_sources(monkeypatch)
    report = probe_mod.probe(env={}, gh=None, chain=False, now=NOW, log=lambda s: None)
    s = report["sources"]
    assert s["good"]["status"] == "ok" and s["good"]["named"] == probe_mod.PROBE_LIMIT  # stops at the limit
    assert s["broken"]["status"] == "failed" and "HTTP 410" in s["broken"]["error"]
    assert s["changed"]["status"] == "failed" and "format" in s["changed"]["error"]
    assert s["bluesky"]["status"] == s["x"]["status"] == "skipped"
    assert report["ok"] is False


def test_probe_ok_and_chain_runs_on_a_throwaway_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _fake_sources(monkeypatch)
    screened = []

    def screen(db, *, n, **kw):
        lead = db.ranked(limit=1)[0]
        db.save_screen(lead["key"], keep=True, kind="cli_tool", reason="fake")
        screened.append(lead["key"])
        return {"checked": {}, "screened": {"kept": 1}, "prescreen": None}

    database = d1(tmp_path)
    report = probe_mod.probe(["good", "x"], env={"X_BEARER_TOKEN": "t"}, gh=FakeGitHub(), d1=database,
                             now=NOW, screen_fn=screen, log=lambda s: None)
    assert report["ok"] is True, report
    assert report["chain"]["check"]["result"] == {"ok": 5}
    assert report["chain"]["feed"]["result"][0]["url"] == f"https://github.com/{screened[0][3:]}"
    assert database.query("SELECT count(*) AS n FROM submissions")[0]["n"] == 0  # the feed was a dry run


def test_chain_failure_fails_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_sources(monkeypatch)

    def screen(db, **kw):
        return {"checked": {}, "screened": {"unscreened": 1}, "prescreen": None}

    report = probe_mod.probe(["good"], env={}, gh=FakeGitHub(), now=NOW, screen_fn=screen, log=lambda s: None)
    assert report["chain"]["screen"]["status"] == "failed" and report["ok"] is False


@pytest.mark.skipif(os.environ.get("PICKFIT_LIVE_HARVEST") != "1", reason="calls the real APIs")
def test_live_sources_still_work() -> None:
    from pickfit.discover.github import GitHub
    from pickfit.env import read_env
    from pickfit.harvest.run import ENV_NAMES

    env = read_env(ENV_NAMES)
    token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    gh = GitHub(token) if token else None
    try:
        report = probe_mod.probe(env=env, gh=gh, screen=False, log=print)
    finally:
        if gh is not None:
            gh.close()
    failed = {k: v["error"] for k, v in {**report["sources"], **report["chain"]}.items() if v["status"] == "failed"}
    assert not failed, failed
