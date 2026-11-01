"""Web app records (P2.8): ids, the address to open, and records built from a site and its extraction."""

from __future__ import annotations

from datetime import datetime

import pytest

from pickfit import webrecords as wr
from pickfit.discover import webapps as w
from pickfit.schema import SoftwareRecord


@pytest.mark.parametrize("key,expected", [
    ("web:example.com", "web:example.com"),
    ("web:user.github.io/my%20tool/v2", "web:user.github.io/my-20tool/v2"),
    ("web:a.com/@me/+x", "web:a.com/me/x"),
    ("web:bücher.de/app", "web:xn--bcher-kva.de/app"),
])
def test_site_id_fits_the_record_alphabet(key, expected):
    assert wr.site_id({"site_key": key}) == expected


def test_web_url_prefers_https_final_url():
    site = {"site_url": "http://a.com", "checks": {"home": {"final_url": "https://a.com/app"}}}
    assert wr.web_url(site) == "https://a.com/app"
    assert wr.web_url({"site_url": "http://a.com", "checks": {}}) is None
    assert wr.web_url({"site_url": "https://a.com", "checks": {"home": {"final_url": "http://a.com"}}}) == "https://a.com"


PAGE = ("title: Word Pad\ndescription: Count words in your browser.\n\nWord Pad\n"
        "Count words and characters as you type. Everything stays in your browser.\nFree, no sign-up.")
NOW = datetime.fromisoformat("2026-11-02T10:00:00+08:00")


def _c(value=None, quote=None):
    return {"value": value, "quote": quote}


def _extraction(**over):
    result = {
        "name": _c("Word Pad", "Word Pad"), "summary": _c("Counts words and characters in the browser.",
                                                          "Count words and characters as you type."),
        "kind": _c("web_app", "Count words in your browser."), "category": _c("other", "Count words in your browser."),
        "audience": _c("end_user", "Count words and characters as you type."), "maturity": _c(),
        "processing": _c("local", "Everything stays in your browser."), "pricing": _c("free", "Free, no sign-up."),
        "platforms": _c(), "install_methods": [], "smoke_test_candidates": [], "manual_steps": [],
        "use_cases": [_c("count the words in an essay", "Count words and characters as you type.")],
        "alternatives_to": [],
        "features": [_c("count words and characters as you type", "Count words and characters as you type.")],
        "prerequisites": {"runtimes": [], "system_packages": [], "api_keys": [], "gpu": _c(),
                          "apple_silicon_only": _c(), "min_ram_gb": _c(), "network": _c()},
        "mcp": {"transports": _c(), "launch_command": _c(), "client_configs": [], "env_vars": [], "tools": []},
    }
    result.update(over)
    return {"model": "muse-spark-1.3", "created_at": "2026-11-02T09:00:00+08:00", "result": result}


def _site(**over):
    site = {"source": "show_hn", "item_id": "45000001", "item_url": "https://news.ycombinator.com/item?id=45000001",
            "title": "Show HN: Word Pad", "link": "https://wordpad.example.com/", "site_url": "https://wordpad.example.com/",
            "site_key": "web:wordpad.example.com", "repo_id": None, "repo": None, "page": PAGE, "readme": None,
            "checks": {"checked_at": "2026-11-02T00:05:00+08:00",
                       "home": {"final_url": "https://wordpad.example.com/"}},
            "first_seen_at": "2026-11-01T23:44:00+08:00", "checked_at": "2026-11-02T00:05:00+08:00"}
    site.update(over)
    return site


def test_record_for_a_site_without_a_repo():
    record = wr.build_web_record(_site(), _extraction(), slug="word-pad", now=NOW)
    assert isinstance(record, SoftwareRecord)
    assert record.repo_id == "web:wordpad.example.com" and record.repo is None
    assert record.kind == "web_app" and record.web.url == "https://wordpad.example.com/"
    assert record.install.guides() == [] and record.platforms == ["macos", "linux", "windows"]
    assert record.prerequisites.network == "required" and record.processing == "local"
    assert record.features == ["count words and characters as you type"]
    assert [s.kind for s in record.sources] == ["website", "hn"]
    cited = {e.field: e for e in record.evidence}
    assert cited["/summary"].source_id == "site" and cited["/summary"].method == "model"
    assert cited["/web"].source_id == "hn:45000001" and cited["/web"].method == "api"
    assert not any(e.source_id.startswith("hn:") and e.method == "model" for e in record.evidence)
    assert record.verification.level == "unverified"


def test_record_for_a_github_site_cites_the_repo():
    repo = {"id": 123, "full_name": "me/wordpad", "name": "wordpad", "html_url": "https://github.com/me/wordpad",
            "description": "Word counter", "homepage": "https://wordpad.example.com/", "topics": ["pwa", "Not A Tag!"],
            "license": "MIT", "created_at": "2025-01-01T00:00:00Z", "archived": False, "default_branch": "main"}
    site = _site(source="github", item_id="gh:123", item_url=repo["html_url"], repo_id="gh:123", repo=repo,
                 readme="# Word Pad\nA tiny word counter.")
    record = wr.build_web_record(site, _extraction(), slug="word-pad", now=NOW)
    assert record.repo_id == "gh:123" and record.repo.full_name == "me/wordpad"
    assert record.license == "MIT" and record.open_source is True and record.tags == ["pwa"]
    assert [s.id for s in record.sources] == ["site", "github_api", "readme"]
    assert {e.field: e.source_id for e in record.evidence}["/web"] == "github_api"


@pytest.mark.parametrize("over,reason", [
    ({"kind": _c("desktop_app", "Word Pad")}, "not_web_app"),
    ({"summary": _c(), "name": _c("Word Pad", "Word Pad")}, "no_summary"),
])
def test_record_skips(over, reason):
    with pytest.raises(ValueError, match=reason):
        wr.build_web_record(_site(), _extraction(**over), slug="word-pad", now=NOW)


def test_mcp_category_becomes_other_and_no_https_is_skipped():
    record = wr.build_web_record(_site(), _extraction(category=_c("mcp_server", "Word Pad")), slug="w", now=NOW)
    assert record.category == "other"
    http = _site(site_url="http://wordpad.example.com/", checks={"checked_at": "2026-11-02T00:05:00+08:00",
                                                                 "home": {"final_url": "http://wordpad.example.com/"}})
    with pytest.raises(ValueError, match="no_https"):
        wr.build_web_record(http, _extraction(), slug="w", now=NOW)


def test_write_web_records_writes_new_files_only(tmp_path, monkeypatch):
    db = w.WebSites(tmp_path / "p.db")
    site = _site()
    db.save({**site, "outcome": "selected"}, "r")
    db.save_check("show_hn", site["item_id"], outcome="selected", checks=site["checks"], page=PAGE)
    monkeypatch.setattr(wr, "latest_web_extractions", lambda path, model: {"web:wordpad.example.com": _extraction()})
    out = tmp_path / "software"
    out.mkdir()
    (out / "word-pad.json").write_text('{"slug": "word-pad", "repo_id": "gh:9"}')
    summary = wr.write_web_records(db, model="muse-spark-1.3", out_dir=out, now=NOW)
    assert summary.written == ["wordpad-example-com"]  # the name's slug was taken
    assert (out / "word-pad.json").read_text() == '{"slug": "word-pad", "repo_id": "gh:9"}'
    again = wr.write_web_records(db, model="muse-spark-1.3", out_dir=out, now=NOW)
    assert again.written == [] and again.skipped == {"web:wordpad.example.com": "has_record"}
