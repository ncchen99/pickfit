"""The web app verifier's own checks (P3.12): one visit per site, robots and terms, the result check."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image, ImageDraw

from pickfit.ledger import BudgetExceeded
from pickfit.verify import web_verify as wv
from pickfit.verify.web_guard import Policy, Request, decide

TARGET = wv.WebTarget(slug="tiny-tool", name="Tiny Tool", url="https://tiny.example.com/app",
                      use_case="Convert text to upper case", features=["Upper-case converter"])


# ---------------------------------------------------------------- one visit per site


def test_a_site_is_visited_once(tmp_path: Path):
    visits = tmp_path / "visits.jsonl"
    wv.claim_visit("example.com", "tiny-tool", "web-a", path=visits)
    with pytest.raises(wv.AlreadyVisited):
        wv.claim_visit("example.com", "other-slug", "web-b", path=visits)
    wv.claim_visit("example.com", "tiny-tool", "web-c", revisit="harness bug fixed", path=visits)
    lines = visits.read_text().splitlines()
    assert len(lines) == 2 and '"revisit": "harness bug fixed"' in lines[1]


def test_verify_site_skips_a_visited_site_before_any_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path))
    wv.record_visit("example.com", "tiny-tool", "web-old")
    fetched: list[str] = []

    def fetcher(url: str) -> tuple[int | None, str, str]:
        fetched.append(url)
        return 404, "", url

    result = wv.verify_site(TARGET, fetcher=fetcher, log=lambda m: None,
                            box_factory=lambda **kw: pytest.fail("no box for a visited site"))
    assert result["level"] == "skipped" and "already visited" in result["reason"] and fetched == []


# ---------------------------------------------------------------- robots and terms before the browser


def fake_site(pages: dict[str, tuple[int | None, str]]):
    def fetcher(url: str) -> tuple[int | None, str, str]:
        status, body = pages.get(url, (404, ""))
        return status, body, url
    return fetcher


def test_preflight_stops_when_robots_disallows(tmp_path: Path):
    fetcher = fake_site({"https://tiny.example.com/robots.txt": (200, "User-agent: *\nDisallow: /app\n")})
    pre = wv.preflight(TARGET, run_id="web-x", fetcher=fetcher)
    assert not pre.allowed and "robots.txt" in pre.reason


def test_preflight_stops_when_robots_is_rate_limited():
    pre = wv.preflight(TARGET, run_id="web-x", fetcher=fake_site({"https://tiny.example.com/robots.txt": (429, "")}))
    assert not pre.allowed


def test_preflight_reads_terms_sentences_and_asks_the_judge(monkeypatch: pytest.MonkeyPatch):
    home = '<a href="/legal/terms">Terms of Service</a><a href="/about">About</a>'
    terms = "<p>Welcome.</p><p>You may not access the Service using bots, scripts or other automated means.</p>"
    fetcher = fake_site({"https://tiny.example.com/app": (200, home), "https://tiny.example.com/legal/terms": (200, terms)})
    asked: list[list[str]] = []

    def judge(sentences, site, **kw):
        asked.append(sentences)
        return wv.TermsVerdict(forbids_automated_use=True, quote=sentences[0]), 0.001

    monkeypatch.setattr(wv, "judge_terms", judge)
    pre = wv.preflight(TARGET, run_id="web-x", fetcher=fetcher)
    assert not pre.allowed and pre.reason == "the terms forbid automated access"
    assert asked == [["You may not access the Service using bots, scripts or other automated means."]]


def test_terms_without_automation_sentences_cost_nothing(monkeypatch: pytest.MonkeyPatch):
    home = '<a href="https://tiny.example.com/terms">Terms</a>'
    fetcher = fake_site({"https://tiny.example.com/app": (200, home),
                         "https://tiny.example.com/terms": (200, "<p>Be nice. No warranty.</p>")})
    monkeypatch.setattr(wv, "judge_terms", lambda *a, **k: pytest.fail("no sentences, no judge"))
    pre = wv.preflight(TARGET, run_id="web-x", fetcher=fetcher)
    assert pre.allowed and pre.terms_checked == ["https://tiny.example.com/terms"]


def test_terms_links_stay_on_the_site():
    links = [("Terms", "https://other.org/terms"), ("Legal", "/legal"), ("Docs", "/docs"), ("x", "/tos#top")]
    assert wv.terms_links(links, "https://tiny.example.com/", "example.com") == [
        "https://tiny.example.com/legal", "https://tiny.example.com/tos"]


# ---------------------------------------------------------------- pickfit's check of the result


def outcome(kind: str, text: str) -> dict[str, Any]:
    return {"feature": "x", "result_kind": kind, "result_text": text, "blocked_by": "nothing", "notes": ""}


def test_text_result_must_be_new_on_the_page_and_not_just_typed():
    after = {"text": "Input: pickfitab12 hello\nOutput: PICKFITAB12 HELLO"}
    typed = ["pickfitab12 hello"]
    ok = wv.check_result(outcome("text_on_page", "PICKFITAB12 HELLO"), "Input:\nOutput:", after, [], typed)
    assert ok["passed"]
    assert wv.check_result(outcome("text_on_page", "Output:"), "Input:\nOutput:", after, [], typed)["why"] == \
        "the claimed text was on the page before the agent acted"
    assert "only what the agent typed" in wv.check_result(outcome("text_on_page", "pickfitab12 hello"), "", after, [],
                                                          typed)["why"]
    assert "not on the page" in wv.check_result(outcome("text_on_page", "Done!"), "", after, [], typed)["why"]


def test_text_match_ignores_spacing_and_case():
    after = {"text": "Untitled Diagram• Modified(Session)"}
    assert wv.check_result(outcome("text_on_page", "untitled diagram • modified"), "", after, [], [])["passed"]


def test_a_file_result_needs_a_real_file():
    files = [{"name": "diagram.png", "size": 2048, "sha256": "ab", "head_hex": "89504e47"}]
    assert wv.check_result(outcome("downloaded_file", "diagram.png"), "", {}, files, [])["passed"]
    assert not wv.check_result(outcome("downloaded_file", "diagram.png"), "", {}, [], [])["passed"]


def test_page_state_without_text_needs_a_visible_change():
    claim = outcome("page_state", "a node appeared")
    assert wv.check_result(claim, "", {"text": ""}, [], [], pixels_changed=0.05)["passed"]
    assert not wv.check_result(claim, "", {"text": ""}, [], [], pixels_changed=0.001)["passed"]
    assert not wv.check_result(outcome("text_on_page", "a node appeared"), "", {"text": ""}, [], [],
                               pixels_changed=0.5)["passed"], "a text claim is never rescued by pixels"


def test_no_outcome_is_no_result():
    assert not wv.check_result(None, "", {}, [], [])["passed"]
    assert not wv.check_result(outcome("none", ""), "", {}, [], [])["passed"]


def test_visual_change_measures_pickfits_own_screenshots(tmp_path: Path):
    a, b = Image.new("RGB", (200, 100), "white"), Image.new("RGB", (200, 100), "white")
    ImageDraw.Draw(b).rectangle((0, 0, 99, 99), fill="blue")
    a.save(tmp_path / "a.png"), b.save(tmp_path / "b.png")
    assert wv.visual_change(tmp_path / "a.png", tmp_path / "b.png") == pytest.approx(0.5)
    assert wv.visual_change(tmp_path / "a.png", tmp_path / "missing.png") is None


@pytest.mark.parametrize("state,problem", [
    ({"url": "chrome-error://chromewebdata/", "text": ""}, "browser error page"),
    ({"url": "https://x.io/", "text": "This domain is for sale! Buy this domain today."}, "parked domain"),
    ({"url": "https://x.io/", "text": "Blocked by pickfit's test guard: navigation off the site to y.io"}, "guard"),
    ({"url": "https://x.io/", "text": "A big working tool " * 50}, None),
])
def test_page_problems_are_found_without_a_model(state: dict[str, Any], problem: str | None):
    found = wv.page_problem(state)
    assert (found is None) if problem is None else (problem in found)


def test_pwa_needs_a_manifest_and_an_active_worker():
    assert wv.is_pwa({"manifest": "https://x.io/manifest.json", "service_workers": [{"active": True}]})
    assert not wv.is_pwa({"manifest": "https://x.io/manifest.json", "service_workers": [{"active": False}]})
    assert not wv.is_pwa({"manifest": None, "service_workers": [{"active": True}]})


# ---------------------------------------------------------------- the operator's model calls


def test_operator_answer_falls_back_to_baseten_and_strips_extra_fields():
    calls: list[str] = []
    raw = {"id": "c1", "object": "chat.completion", "created": 1, "model": "m", "choices": [],
           "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
           "metadata": {"weight_versions": [{"version": "default"}]}}

    def caller(endpoint, body, **kw):
        calls.append(kw["model"])
        if kw["model"] == wv.OPERATOR_MODEL:
            raise RuntimeError("endpoint down")
        assert kw["scope_cap_usd"] == wv.OPERATE_CAP_USD and kw["max_output_tokens"] >= 1500
        assert set(body) == {"messages", "response_format"}
        return SimpleNamespace(raw=raw, cost_usd=0.01, model="meta-models/muse-spark-open-1026")

    spent = wv.OperatorLedger()
    answer = wv.operator_answer({"id": 7, "request": {"messages": [], "response_format": {}, "model": "x",
                                                      "max_completion_tokens": 99}},
                                run_id="r", scope="web:t", spent=spent, caller=caller)
    assert calls == [wv.OPERATOR_MODEL, wv.FALLBACK_MODEL]
    assert answer["type"] == "llm_result" and answer["id"] == 7 and "metadata" not in answer["response"]
    assert spent.fallbacks == 1 and spent.calls == 1


def test_a_declined_operator_call_tries_the_other_model_and_says_why_when_both_decline():
    """11/16: the API declined every operator call (browser-use asked Claude to write its reasoning out), the
    answer came back with no content, and the harness only saw "failed to parse" four times a site."""
    declined = {"id": "c1", "object": "chat.completion", "created": 1, "model": "m",
                "choices": [{"index": 0, "finish_reason": "content_filter",
                             "message": {"role": "assistant", "content": None}}],
                "stop_details": {"type": "refusal", "category": "reasoning_extraction"}}
    answered = {"id": "c2", "object": "chat.completion", "created": 1, "model": "m",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}]}
    replies = {wv.OPERATOR_MODEL: SimpleNamespace(raw=declined, cost_usd=0.02, model="claude-opus-5-5",
                                                  status="content_filter"),
               wv.FALLBACK_MODEL: SimpleNamespace(raw=answered, cost_usd=0.01, model="claude-sonnet-5-5",
                                                  status="stop")}
    spent = wv.OperatorLedger()
    answer = wv.operator_answer({"id": 3, "request": {"messages": []}}, run_id="r", scope="s", spent=spent,
                                caller=lambda endpoint, body, **kw: replies[kw["model"]])
    assert answer["type"] == "llm_result" and answer["response"]["choices"][0]["message"]["content"] == "{}"
    assert spent.cost_usd == pytest.approx(0.03) and spent.calls == 2, "the declined call is paid for and counted"
    assert spent.errors == ["claude-opus-5-5 declined the request (reasoning_extraction)"]

    both = wv.operator_answer({"id": 4, "request": {"messages": []}}, run_id="r", scope="s",
                              spent=wv.OperatorLedger(),
                              caller=lambda endpoint, body, **kw: replies[wv.OPERATOR_MODEL])
    assert both["type"] == "llm_error" and "declined the request (reasoning_extraction)" in both["error"]


def test_claude_is_not_asked_to_write_its_reasoning_into_the_answer():
    assert wv.operator_writes_thinking(wv.OPERATOR_MODEL) is False
    assert wv.operator_writes_thinking(wv.FALLBACK_MODEL) is False and wv.operator_writes_thinking("open") is False
    assert wv.operator_writes_thinking("open-modal") is True  # the hackathon's operator keeps its prompt
    harness = (Path(wv.__file__).parent / "web_harness.py").read_text(encoding="utf-8")
    assert 'use_thinking=bool(start.get("operator_thinking", True))' in harness


def test_the_operators_element_list_is_todays_unless_a_comparison_sets_it(monkeypatch: pytest.MonkeyPatch):
    from pickfit.verify import web_harness

    for name in ("PICKFIT_WEB_ELEMENTS_CHARS", "PICKFIT_WEB_ELEMENT_ATTRIBUTES"):
        monkeypatch.delenv(name, raising=False)
    assert wv.element_settings() == {}
    assert web_harness.element_options({}) == {"max_clickable_elements_length": 12_000}  # browser-use's attributes
    monkeypatch.setenv("PICKFIT_WEB_ELEMENTS_CHARS", "7000")
    monkeypatch.setenv("PICKFIT_WEB_ELEMENT_ATTRIBUTES", "compact")
    start = wv.element_settings()
    assert start == {"elements_chars": 7000, "element_attributes": "compact"}
    options = web_harness.element_options(start)
    assert options["max_clickable_elements_length"] == 7000 and "ax_name" in options["include_attributes"]
    assert "pattern" not in options["include_attributes"]
    harness = (Path(wv.__file__).parent / "web_harness.py").read_text(encoding="utf-8")
    assert "**element_options(start)" in harness
    for name, bad in (("PICKFIT_WEB_ELEMENTS_CHARS", "500"), ("PICKFIT_WEB_ELEMENT_ATTRIBUTES", "tiny")):
        monkeypatch.setenv(name, bad)
        with pytest.raises(ValueError, match=name):
            wv.element_settings()
        monkeypatch.delenv(name)


def test_a_visits_judges_are_capped_with_the_operator_not_below_it():
    # DuckDB's shell, 11/16: the operator spent $0.69 in the visit's scope, and the judge, capped at $0.50 in
    # that same scope, was refused; the visit was lost. A judge's cap is the visit's.
    caps: list[float] = []

    def caller(endpoint, body, **kw):
        caps.append(kw["scope_cap_usd"])
        assert kw["scope"] == "web:duckdb-web-shell"
        return SimpleNamespace(parsed=None, cost_usd=0.03)

    state = {"screenshot_jpeg_b64": "AAAA", "url": "https://shell.duckdb.org", "title": "DuckDB", "text": "D"}
    wv.judge_page("DuckDB Web Shell", state, run_id="web-x", scope="web:duckdb-web-shell", caller=caller)
    assert caps == [wv.SITE_CAP_USD] and wv.SITE_CAP_USD == wv.OPERATE_CAP_USD + wv.JUDGE_CAP_USD
    assert wv.WORST_SITE_USD >= wv.SITE_CAP_USD


def test_operator_answer_reports_a_budget_stop():
    def caller(endpoint, body, **kw):
        raise BudgetExceeded("scope", 0.6, 0.6, 0.01)

    answer = wv.operator_answer({"id": 1, "request": {"messages": []}}, run_id="r", scope="s",
                                spent=wv.OperatorLedger(), caller=caller)
    assert answer["type"] == "llm_error" and "budget" in answer["error"]


# ---------------------------------------------------------------- the task and the guard agree


def test_the_task_states_the_rules_the_guard_enforces():
    task = wv.task_text(TARGET, "pickfitab12", ["sample.txt"], 10)
    for rule in ("Do not sign up", "Never type an email address", "pickfitab12", "sample.txt", "at most 10 steps"):
        assert rule in task
    assert not decide(Request("POST", "https://tiny.example.com/signup", {"sec-fetch-mode": "cors"}, b"{}"),
                      Policy(site="example.com")).allow


def test_sample_files_carry_the_marker():
    files = wv.sample_files("pickfitab12")
    assert set(files) >= {"sample.txt", "sample.csv", "sample.png", "sample.jpg", "sample.pdf"}
    assert all(b"pickfitab12" in data for data in files.values())


def test_the_user_agent_is_honest():
    ua = wv.user_agent("156.0.1")
    assert "HeadlessChrome/156.0.1" in ua and "pickfit-verifier" in ua


def test_a_batch_stops_only_at_its_own_max_usd():
    spend = {"anthropic": 3.0, "meta": 80.0, "modal": 19.9, "baseten": 4.9, "pipeline_total": 400.0}
    assert wv.batch_spend(spend) == pytest.approx(107.8), "the pipeline's total is not the web verifier's"
    # No cap: the hackathon's totals (Meta $8, Modal $20, the pipeline under $158) stop nothing any more.
    assert wv.budget_stop(60, 107.8, None) is None
    assert wv.budget_stop(1, 0.0, 20.0) is None
    stop = wv.budget_stop(1, 20.0 - wv.WORST_SITE_USD + 0.01, 20.0)
    assert "--max-usd 20.00" in stop, "each site is checked against a worst case before it starts"


def test_typed_text_counts_only_when_the_app_rendered_it_outside_inputs():
    claim = outcome("page_state", "pickfitab12 hello world")
    typed = ["pickfitab12 hello world"]
    card = {"text": "Backlog\npickfitab12 hello world", "static_text": "Backlog\npickfitab12 hello world"}
    ok = wv.check_result(claim, "Backlog", card, [], typed, before_static="Backlog")
    assert ok["passed"] and ok["rendered_from_input"]
    still_in_the_box = {"text": "Backlog", "static_text": "Backlog"}
    assert not wv.check_result(claim, "Backlog", still_in_the_box, [], typed, before_static="Backlog")["passed"]
    as_text_claim = wv.check_result(outcome("text_on_page", "pickfitab12 hello world"), "Backlog", card, [], typed,
                                    before_static="Backlog")
    assert not as_text_claim["passed"], "a text result must be more than the typed text"


def test_a_result_shown_in_a_read_only_field_counts():
    after = {"text": "Amount\nResult", "output_values": "92.54 EUR"}
    assert wv.check_result(outcome("text_on_page", "92.54 EUR"), "Amount\nResult", after, [], ["100"])["passed"]


def test_the_task_forbids_acting_in_public():
    task = wv.task_text(TARGET, "pickfitab12", ["/home/web/samples/sample.txt"], 10)
    assert "Never do anything other people could see" in task and "multiplayer" in task


def _shot(path: Path) -> Path:
    Image.new("RGB", (10, 10), "white").save(path)
    return path


def test_text_drawn_outside_the_dom_counts_when_only_the_after_screenshot_shows_it(tmp_path: Path):
    before, after = _shot(tmp_path / "before.png"), _shot(tmp_path / "after.png")
    missing = {"passed": False, "kind": "text_on_page", "why": "the claimed text is not on the page"}
    claim = outcome("text_on_page", "Score: 120")

    def reader(png, sought, **kw):
        return wv.ScreenRead(shown=png.name == "after.png", read="Score: 120" if png.name == "after.png" else ""), 0.004

    check, cost = wv.screenshot_check(missing, claim, before, after, [], run_id="r", scope="s", reader=reader)
    assert check["passed"] and check["read_from_screenshot"] and cost == pytest.approx(0.008)

    def credulous(png, sought, **kw):  # sees whatever it is told: the before screenshot catches it
        return wv.ScreenRead(shown=True, read=sought), 0.004

    assert not wv.screenshot_check(missing, claim, before, after, [], run_id="r", scope="s", reader=credulous)[0]["passed"]
    typed = wv.screenshot_check(missing, outcome("text_on_page", "pickfitab12"), before, after, ["pickfitab12"],
                                run_id="r", scope="s", reader=reader)
    assert not typed[0]["passed"] and typed[1] == 0.0, "typed text is never read back as a result"
    other = {"passed": False, "kind": "text_on_page", "why": "the claimed text was on the page before the agent acted"}
    assert wv.screenshot_check(other, claim, before, after, [], run_id="r", scope="s", reader=reader)[1] == 0.0


def test_the_task_asks_for_a_visible_result_and_explains_canvas_apps():
    task = wv.task_text(TARGET, "pickfitab12", ["/home/web/samples/sample.txt"], 10)
    assert "Never report a result you cannot see" in task and "send_keys" in task
