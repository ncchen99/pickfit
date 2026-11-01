"""Web app discovery (P2.8): neutral rules, robots.txt and terms checks, the band and the pick order."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pickfit.discover import webapps as w


@pytest.mark.parametrize("url,key", [
    ("https://www.Example.com/", "web:example.com"),
    ("http://example.com/index.html?ref=hn#top", "web:example.com"),
    ("https://user.github.io/tool/", "web:user.github.io/tool"),
    ("ftp://example.com", None),
    ("not a url", None),
    (None, None),
])
def test_site_key(url, key):
    assert w.site_key(url) == key


@pytest.mark.parametrize("url,outcome", [
    ("https://tool.example.com/app", None),
    ("https://someone.github.io/app", None),  # a hosting provider: the site is its owner's
    ("https://my-app.vercel.app", None),
    ("https://github.com/a/b", "code_host"),
    ("https://gist.github.com/a/1", "code_host"),
    ("https://apps.apple.com/app/id1", "platform"),
    ("https://www.youtube.com/watch?v=x", "platform"),
    ("https://blog.medium.com/post", "platform"),
    ("https://example.com/files/App.dmg", "download"),
    ("", "no_link"),
    (None, "no_link"),
])
def test_site_outcome(url, outcome):
    assert w.site_outcome(url) == outcome


def test_on_matches_subdomains_not_suffixes():
    assert w.on("docs.google.com", w.PLATFORMS)
    assert w.on("foo.notion.site", w.PLATFORMS)
    assert not w.on("notx.com", w.PLATFORMS)
    assert not w.on("mygithub.com", w.PLATFORMS)


def test_robots_star_disallow():
    v = w.robots_verdict("User-agent: *\nDisallow: /\n", "https://a.com/")
    assert v["allowed"] is False and v["star"] is False


def test_robots_training_block_is_recorded_not_excluding():
    text = "User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\nContent-Signal: search=yes, ai-train=no\n"
    v = w.robots_verdict(text, "https://a.com/app")
    assert v["allowed"] is True
    assert v["training_agents_blocked"] == ["gptbot"]
    assert v["content_signal"] == {"search": "yes", "ai-train": "no"}


def test_robots_live_agent_block_excludes():
    v = w.robots_verdict("User-agent: ChatGPT-User\nDisallow: /\n", "https://a.com/")
    assert v["allowed"] is False and v["live_agents_blocked"] == ["chatgpt-user"]


def test_robots_ai_input_no_excludes():
    v = w.robots_verdict("User-agent: *\nContent-Signal: ai-input=no, search=yes\nAllow: /\n", "https://a.com/")
    assert v["allowed"] is False


def test_robots_pickfit_named():
    v = w.robots_verdict("User-agent: pickfit\nDisallow: /\n", "https://a.com/")
    assert v["allowed"] is False and v["pickfit"] is False


def test_no_robots_file_allows():
    assert w.robots_verdict(None, "https://a.com/") == {"allowed": True, "file": False}


def test_terms_links_same_site_terms_first():
    links = [("/privacy", "Privacy policy"), ("https://other.com/terms", "Terms"), ("/legal", "Legal"),
             ("/tos", "Terms of Service"), ("#", "Home")]
    assert w.terms_links(links, "https://app.example.com/") == [
        "https://app.example.com/tos", "https://app.example.com/legal"]


def test_terms_bans_finds_prohibition_with_automation():
    text = ("You may use the service for personal use. You agree not to use any robot, spider or scraper "
            "to access the service. We use cookies. Bots are cool.")
    bans = w.terms_bans(text)
    assert len(bans) == 1 and "robot, spider or scraper" in bans[0]


def test_terms_bans_contractions_and_list_leads():
    assert w.terms_bans("Don't reverse engineer or scrape the service.")
    text = ("You may not:\nResell the Service\nUse automated means to access the Service beyond the API\n"
            "Contact: hello@example.com")
    assert w.terms_bans(text) == ["You may not: Use automated means to access the Service beyond the API"]
    assert w.terms_bans("Our features:\nAutomated tools for scheduling posts") == []


def test_parse_page_text_title_meta_links_manifest():
    html = ("<html lang='en'><head><title> My Tool </title><meta name='description' content='Does x'>"
            "<link rel='manifest' href='/m.json'><script>var x = 1</script></head><body><h1>Hello</h1>"
            "<p>Use it <a href='/terms'>Terms</a></p><noscript>enable js</noscript></body></html>")
    p = w.parse_page(html)
    assert p.title.strip() == "My Tool" and p.meta["description"] == "Does x" and p.manifest == "/m.json"
    assert p.links == [("/terms", "Terms")]
    text = p.text()
    assert "Hello" in text and "Use it" in text and "var x" not in text and "enable js" not in text


def test_apply_band_one_value_per_site():
    rows = [{"outcome": "site", "site_key": f"web:s{i}", "popularity": i} for i in range(1, 9)]
    rows.append({"outcome": "site", "site_key": "web:s1", "popularity": 5})  # s1's best post has 5 points
    rows.append({"outcome": "platform", "site_key": None, "popularity": 999})
    band = w.apply_band(rows)
    assert band == (4, 6)  # values 2,3,4,5,5,6,7,8: nearest-rank P25 and P75
    by_site = {r["site_key"]: r["outcome"] for r in rows if r["site_key"]}
    assert by_site["web:s1"] == "in_band" and by_site["web:s2"] == "below_band" and by_site["web:s8"] == "above_band"
    assert rows[-1]["outcome"] == "platform"


def test_apply_band_floor_marks_unused_and_bands_the_rest():
    rows = [{"outcome": "site", "site_key": f"web:s{i}", "popularity": p} for i, p in enumerate([1, 1, 1, 2, 3, 4, 9])]
    assert w.apply_band(rows, floor=2) == (3, 4)  # nearest-rank P25 and P75 of 2, 3, 4, 9
    assert [r["outcome"] for r in rows] == ["unused"] * 3 + ["below_band", "in_band", "in_band", "above_band"]


def _repo(**kw):
    base = {"homepage": "https://x.example.com", "fork": False, "is_template": False, "license": "MIT",
            "archived": False, "disabled": False, "pushed_at": "2026-10-01T00:00:00Z"}
    return {**base, **kw}


@pytest.mark.parametrize("kw,outcome", [
    ({}, None),
    ({"homepage": None}, "no_homepage"),
    ({"homepage": "https://www.npmjs.com/package/x"}, "platform"),
    ({"homepage": "x.example.com"}, None),  # a homepage without a scheme
    ({"fork": True}, "fork"),
    ({"license": None}, "not_open_source"),
    ({"license": "BUSL-1.1"}, "not_open_source"),
    ({"archived": True}, "unmaintained"),
    ({"pushed_at": "2025-01-01T00:00:00Z"}, "unmaintained"),
])
def test_github_outcome(kw, outcome):
    assert w.github_outcome(_repo(**kw), datetime(2026, 11, 1, tzinfo=UTC)) == outcome


def test_screen_keep():
    r = w.WebScreenResult(page_kind="web_app", web_app=True, account_for_core_use="unclear", free_to_try="yes",
                          confidence=0.9, reason="r")
    assert w.screen_keep(r) == (True, None)
    assert w.screen_keep(r.model_copy(update={"account_for_core_use": "needed"})) == (False, None)
    assert w.screen_keep(r.model_copy(update={"free_to_try": "no"})) == (False, None)
    assert w.screen_keep(r.model_copy(update={"confidence": 0.5})) == (True, "low_confidence")
    assert w.screen_keep(r.model_copy(update={"web_app": False})) == (False, "inconsistent")
    assert w.screen_keep(r.model_copy(update={"page_kind": "content", "web_app": False})) == (False, None)


def test_pick_order_is_fixed():
    assert w.pick_key("p2.8", "web:a.com") == w.pick_key("p2.8", "web:a.com")
    assert w.pick_key("p2.8", "web:a.com") != w.pick_key("other", "web:a.com")


def test_store_keeps_checks_on_refresh(tmp_path):
    db = w.WebSites(tmp_path / "p.db")
    row = {"source": "show_hn", "item_id": "1", "item_url": "https://news.ycombinator.com/item?id=1",
           "title": "Show HN: X", "site_url": "https://x.com", "site_key": "web:x.com", "popularity": 3,
           "outcome": "in_band"}
    db.save(row, "r1")
    db.save_check("show_hn", "1", outcome="passed", checks={"a": 1}, page="text")
    db.save({**row, "popularity": 4}, "r2")
    [got] = db.rows("show_hn")
    assert got["outcome"] == "passed" and got["popularity"] == 4 and got["checks"] == {"a": 1}
    assert db.purge_pages() == 1 and db.rows()[0]["page"] is None


def test_recheck_terms_marks_passed_sites_with_a_ban(tmp_path, monkeypatch):
    db = w.WebSites(tmp_path / "p.db")
    for i, outcome in enumerate(["selected", "passed", "not_web_app:content"]):
        db.save({"source": "show_hn", "item_id": str(i), "item_url": "u", "title": "t", "site_url": f"https://s{i}.com",
                 "site_key": f"web:s{i}.com", "outcome": outcome}, "r")
        db.save_check("show_hn", str(i), outcome=outcome, checks={"terms": {"url": f"https://s{i}.com/terms"}})
    pages = {"https://s0.com/terms": "You agree not to scrape the service. " + "x " * 300,
             "https://s1.com/terms": "Be nice. " + "y " * 300}
    monkeypatch.setattr(w.Fetcher, "get", lambda self, kind, url: {
        "status": 200, "url": url, "type": "text/plain", "text": pages.get(url, ""), "error": None})
    assert w.recheck_terms(db, log=lambda _: None) == {"terms_disallow": 1, "kept": 1}
    assert [r["outcome"] for r in db.rows()] == ["terms_disallow", "passed", "not_web_app:content"]
