"""The web guard: what pickfit's browser may send while it tests someone else's site (P3.12)."""

from __future__ import annotations

import json

import pytest

from pickfit.verify.web_guard import (
    UA_SUFFIX,
    Policy,
    Request,
    crawl_delay,
    decide,
    find_leaks,
    registrable,
    robots_allows,
    robots_parser,
    summarize,
    words,
)

SITE = Policy(site="example.com")
NAV = {"sec-fetch-mode": "navigate", "sec-fetch-dest": "document", "accept": "text/html"}
FETCH = {"sec-fetch-mode": "cors", "sec-fetch-dest": "empty", "content-type": "application/json"}


def req(method: str, url: str, headers: dict[str, str] | None = None, body: bytes | str = b"") -> Request:
    return Request(method=method, url=url, headers=headers or {},
                   body=body.encode() if isinstance(body, str) else body)


def allowed(r: Request, policy: Policy = SITE) -> bool:
    return decide(r, policy).allow


# ---------------------------------------------------------------- navigation stays on the site


def test_navigation_on_the_site_and_its_subdomains_is_allowed():
    assert allowed(req("GET", "https://example.com/app", NAV))
    assert allowed(req("GET", "https://docs.example.com/guide", NAV))


def test_navigation_off_the_site_is_refused():
    d = decide(req("GET", "https://other.org/", NAV), SITE)
    assert not d.allow and "off the site" in d.reason


def test_private_suffixes_are_separate_sites():
    policy = Policy(site=registrable("alice.github.io"))
    assert allowed(req("GET", "https://alice.github.io/tool/", NAV), policy)
    assert not allowed(req("GET", "https://mallory.github.io/", NAV), policy)


def test_plain_http_navigation_is_told_by_its_headers():
    headers = {"upgrade-insecure-requests": "1", "accept": "text/html,application/xhtml+xml"}
    assert allowed(req("GET", "http://example.com/", headers))
    assert not allowed(req("GET", "http://elsewhere.net/", headers))


def test_assets_and_api_reads_from_other_hosts_load():
    assert allowed(req("GET", "https://cdn.jsdelivr.net/npm/x.js", {"sec-fetch-mode": "no-cors",
                                                                    "sec-fetch-dest": "script"}))
    assert allowed(req("GET", "https://api.other.io/v1/data", FETCH))
    assert allowed(req("GET", "https://www.youtube.com/embed/x", {"sec-fetch-mode": "navigate",
                                                                  "sec-fetch-dest": "iframe"}))


# ---------------------------------------------------------------- no submissions with side effects


def test_form_submission_navigation_is_refused():
    d = decide(req("POST", "https://example.com/search", NAV, "q=cats"), SITE)
    assert not d.allow and "form submission" in d.reason


def test_post_inside_a_frame_is_refused():
    frame = {"sec-fetch-mode": "navigate", "sec-fetch-dest": "iframe"}
    assert not allowed(req("POST", "https://example.com/widget", frame, "a=1"))


@pytest.mark.parametrize("path", [
    "/api/auth/login", "/signup", "/users/sign_up", "/api/v1/register", "/oauth/token", "/session",
    "/api/posts", "/api/comments", "/threads/1/reply", "/api/messages", "/contact", "/api/sendEmail",
    "/newsletter/subscribe", "/checkout", "/api/cart/items", "/orders", "/api/payments/intent",
    "/booking/create", "/reservations", "/api/appointments", "/api/votes", "/api/users", "/logIn",
])
def test_side_effect_paths_are_refused_for_writes(path: str):
    d = decide(req("POST", f"https://example.com{path}", FETCH, "{}"), SITE)
    assert not d.allow and "side-effect path" in d.reason
    assert allowed(req("GET", f"https://example.com{path}", NAV)), "viewing such a page is fine"


@pytest.mark.parametrize("path", ["/api/convert", "/api/postprocess", "/api/compute", "/v1/chat/completions",
                                  "/api/render", "/api/search"])
def test_in_page_tool_calls_are_allowed(path: str):
    assert allowed(req("POST", f"https://example.com{path}", FETCH, json.dumps({"text": "hello"})))


@pytest.mark.parametrize("host", ["accounts.google.com", "api.stripe.com", "formspree.io", "api.emailjs.com",
                                  "us21.list-manage.com", "hooks.slack.com", "discord.com", "api.telegram.org"])
def test_writes_to_auth_payment_form_and_messaging_services_are_refused(host: str):
    d = decide(req("POST", f"https://{host}/v1/x", FETCH, "{}"), SITE)
    assert not d.allow and "service" in d.reason


@pytest.mark.parametrize("body,ctype", [
    ('{"user": {"password": "x"}}', "application/json"),
    ('{"email": "a@b.co"}', "application/json"),
    ("username=a&pwd=b", "application/x-www-form-urlencoded"),
    ('{"cardNumber": "4242"}', "application/json"),
    ('{"g-recaptcha-response": "t"}', "application/json"),
    ('--b\r\nContent-Disposition: form-data; name="phone"\r\n\r\n123\r\n--b--', "multipart/form-data; boundary=b"),
])
def test_credential_or_personal_fields_are_refused(body: str, ctype: str):
    d = decide(req("POST", "https://example.com/api/convert", {**FETCH, "content-type": ctype}, body), SITE)
    assert not d.allow


def test_an_email_address_anywhere_in_a_write_or_address_is_refused():
    assert not allowed(req("POST", "https://example.com/api/convert", FETCH, '{"text": "mail me: jo@example.org"}'))
    assert not allowed(req("GET", "https://example.com/find?q=jo%40example.org", NAV))


def test_secrets_in_the_address_are_refused():
    assert not allowed(req("GET", "https://example.com/x?user=a&password=b", FETCH))


def test_message_forms_are_refused():
    body = '{"subject": "hi", "body": "hello"}'
    assert not allowed(req("POST", "https://example.com/api/convert", FETCH, body))


def test_graphql_mutations_with_side_effects_are_refused():
    body = json.dumps({"query": "mutation CreateComment($t: String!) { createComment(text: $t) { id } }"})
    d = decide(req("POST", "https://example.com/graphql", FETCH, body), SITE)
    assert not d.allow and "GraphQL" in d.reason
    query = json.dumps({"query": "query Search { items { id } }"})
    assert allowed(req("POST", "https://example.com/graphql", FETCH, query))


# ---------------------------------------------------------------- addresses, background services, offline


@pytest.mark.parametrize("url", ["http://127.0.0.1:9222/json", "http://localhost:3000/", "http://10.1.2.3/",
                                 "http://169.254.169.254/latest/meta-data", "http://192.168.1.1/",
                                 "http://[::1]/", "http://printer.local/"])
def test_private_loopback_and_metadata_addresses_are_refused(url: str):
    assert not allowed(req("GET", url, FETCH))


def test_the_browser_tool_vendor_and_chrome_background_services_are_refused():
    assert not allowed(req("GET", "https://cf.browser-use.com/logo.svg", {"sec-fetch-dest": "image"}))
    assert not allowed(req("GET", "https://update.googleapis.com/service/update2", {}))


def test_offline_phase_refuses_everything():
    offline = Policy(site="example.com", offline=True)
    assert not allowed(req("GET", "https://example.com/", NAV), offline)


def test_other_schemes_are_refused():
    assert not allowed(req("GET", "ftp://example.com/x", NAV))


# ---------------------------------------------------------------- robots.txt


ROBOTS = """User-agent: *
Disallow: /private/

User-agent: pickfit-verifier
Disallow: /app/admin
Crawl-delay: 4
"""


def test_robots_rules_for_pickfit_are_obeyed():
    parser = robots_parser(ROBOTS, 200)
    assert robots_allows(parser, "https://example.com/")
    assert not robots_allows(parser, "https://example.com/app/admin/x")
    assert crawl_delay(parser) == 4.0
    policy = Policy(site="example.com", robots_txt=ROBOTS, robots_status=200)
    d = decide(req("GET", "https://example.com/app/admin", NAV), policy)
    assert not d.allow and "robots" in d.reason


def test_robots_disallow_all_blocks_the_site():
    parser = robots_parser("User-agent: *\nDisallow: /\n", 200)
    assert not robots_allows(parser, "https://example.com/")


@pytest.mark.parametrize("status,ok", [(404, True), (410, True), (401, False), (403, False), (500, False),
                                       (None, False)])
def test_robots_status_codes(status: int | None, ok: bool):
    assert robots_allows(robots_parser(None, status), "https://example.com/") is ok


def test_the_user_agent_names_pickfit_and_says_what_it_does():
    assert UA_SUFFIX.startswith("pickfit-verifier/") and "github.com/ncchen99/pickfit" in UA_SUFFIX
    assert "no sign-ups" in UA_SUFFIX


# ---------------------------------------------------------------- what left the device


def test_typed_text_found_in_any_encoding_counts_as_sent():
    flows = [
        {"host": "example.com", "site": "example.com", "method": "GET", "kind": "fetch", "allowed": True,
         "url": "https://example.com/api/search?q=pickfit+kiwi+7f3a", "body": ""},
        {"host": "t.tracker.io", "site": "tracker.io", "method": "POST", "kind": "fetch", "allowed": False,
         "url": "https://t.tracker.io/c", "body": '{"v":"pickfit kiwi 7f3a"}'},
        {"host": "example.com", "site": "example.com", "method": "GET", "kind": "script", "allowed": True,
         "url": "https://example.com/app.js", "body": ""},
    ]
    hits = find_leaks(flows, ["pickfit kiwi 7f3a", "ab"])
    assert [(h["host"], h["sent"]) for h in hits] == [("example.com", True), ("t.tracker.io", False)]


def test_nothing_typed_nothing_found():
    flows = [{"host": "example.com", "url": "https://example.com/", "body": "", "allowed": True}]
    assert find_leaks(flows, ["pickfit kiwi 7f3a"]) == []


def test_summary_counts_third_party_sites_and_ad_networks():
    flows = [
        {"host": "example.com", "site": "example.com", "allowed": True},
        {"host": "cdn.example.com", "site": "example.com", "allowed": True},
        {"host": "fonts.gstatic.com", "site": "gstatic.com", "allowed": True},
        {"host": "securepubads.g.doubleclick.net", "site": "doubleclick.net", "allowed": True},
        {"host": "cf.browser-use.com", "site": "browser-use.com", "allowed": False, "reason": "tool"},
        {"host": "evil.org", "site": "evil.org", "allowed": False, "method": "GET", "kind": "navigation",
         "reason": "off the site"},
    ]
    s = summarize(flows, "example.com")
    assert s["third_party_sites"] == ["doubleclick.net", "gstatic.com"]
    assert s["ad_networks"] == ["doubleclick.net"]
    assert s["refused_count"] == 1, "background services are not counted"


def test_words_split_camel_case_and_join_neighbours():
    assert {"sign", "up", "signup"} <= words("/api/signUp")
    assert "post" not in words("/api/postprocess")
