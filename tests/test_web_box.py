"""The web sandbox's own guards (P3.12): the browser's network path, its flags, typing, browser-use's settings."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pickfit.verify import web_box, web_harness


def test_the_browser_uid_reaches_loopback_only_and_the_guard_no_new_loopback():
    rules = web_box.RULES
    assert f"meta skuid {web_box.WEB_UID} oifname lo accept" in rules
    assert f"meta skuid {web_box.WEB_UID} counter drop" in rules
    assert rules.index("oifname lo accept") < rules.index("counter drop")
    assert f"meta skuid {web_box.GUARD_UID} ip daddr 127.0.0.0/8 drop" in rules
    assert "ct state established,related accept" in rules


def test_offline_cuts_the_guard_and_raises_its_flag():
    assert f"meta skuid {web_box.GUARD_UID} oifname != lo drop" in web_box.OFFLINE_ON
    assert web_box.OFFLINE_FLAG in web_box.OFFLINE_ON


def test_the_vm_allows_public_addresses_only():
    kwargs = web_box.WebBox(site="example.com").create_kwargs()
    assert kwargs["runtime"] == "vm" and kwargs["outbound_domain_allowlist"] == []
    nets = kwargs["outbound_cidr_allowlist"]
    assert nets and not any(n.startswith(("10.", "169.254.", "192.168.", "127.")) for n in nets)


def test_browser_use_runs_without_telemetry_or_cloud_and_pinned():
    env = dict(e.split("=", 1) for e in web_box.AGENT_ENV)
    assert env["ANONYMIZED_TELEMETRY"] == "false" and env["BROWSER_USE_CLOUD_SYNC"] == "false"
    assert env["BROWSER_USE_VERSION_CHECK"] == "false" and env["BROWSER_USE_DISABLE_EXTENSIONS"] == "1"
    assert web_box.BROWSER_USE == "browser-use==0.13.14"
    assert all("==" in p for p in web_box.GUARD_PACKAGES)
    assert {"search", "evaluate"} <= set(web_harness.EXCLUDED_ACTIONS)


def test_chromium_goes_through_the_guard_with_an_honest_user_agent():
    args = web_harness.chrome_args("UA pickfit-verifier/0.1")
    assert "--proxy-server=http://127.0.0.1:8080" in args and "--proxy-bypass-list=<-loopback>" in args
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args and "--disable-quic" in args
    assert "--user-agent=UA pickfit-verifier/0.1" in args
    assert not any(a.startswith("--no-sandbox") for a in args), "Chromium keeps its own sandbox"


@pytest.mark.parametrize("attrs,text", [
    ({"type": "password"}, "x"), ({"type": "email"}, "x"), ({"type": "tel"}, "x"),
    ({"name": "username"}, "bob"), ({"autocomplete": "current-password"}, "x"),
    ({"placeholder": "Enter your email"}, "x"), ({"aria-label": "Card number"}, "x"),
    ({"id": "otp-code"}, "1234"), ({"type": "text"}, "write to jo@example.org"),
    ({"type": "text"}, "4242 4242 4242 4242"),
])
def test_typing_into_credential_fields_or_typing_personal_data_is_refused(attrs, text):
    assert web_harness.typing_refused(attrs, text)


@pytest.mark.parametrize("attrs,text", [({"type": "text", "name": "q"}, "pickfitab12 hello"),
                                        ({"type": "number", "aria-label": "Value to convert"}, "100"),
                                        ({}, "Naruto")])
def test_ordinary_inputs_are_typed(attrs, text):
    assert web_harness.typing_refused(attrs, text) is None


@pytest.mark.parametrize("label,attrs", [
    ("Get in line", {}), ("Post", {}), ("Share", {}), ("Send", {}), ("Join game", {}), ("Invite friends", {}),
    ("", {"aria-label": "Like"}), ("Vote", {}), ("Sign up free", {}), ("Log in", {}), ("Claim your page", {}),
    ("Add to cart", {}), ("Follow", {}), ("Emote", {}), ("Go live", {}),
])
def test_controls_that_act_in_public_or_sign_up_are_not_clicked(label, attrs):
    assert web_harness.click_refused(label, attrs)


@pytest.mark.parametrize("label,attrs", [
    ("Convert", {}), ("Generate", {}), ("Easy (36 clues)", {}), ("Download PNG", {}), ("Add card", {}),
    ("Sort order", {}), ("Compress", {}), ("Postprocess", {}), ("Unlikely", {}), ("Next", {"type": "submit"}),
])
def test_ordinary_controls_are_clicked(label, attrs):
    assert web_harness.click_refused(label, attrs) is None


@pytest.mark.parametrize("attrs", [{"placeholder": "Your nickname"}, {"aria-label": "Chat message"},
                                   {"name": "display_name", "placeholder": "Display name"},
                                   {"placeholder": "Write a comment"}])
def test_fields_other_people_would_see_are_not_typed_into(attrs):
    assert web_harness.typing_refused(attrs, "pickfitab12")


# ---------------------------------------------------------------- the phone-size look (P2-07)


class _FakePage:
    @property
    async def session_id(self) -> str:
        return "sid"


class _FakeSession:
    """Just enough of browser-use's session for mobile_check: CDP calls are logged, the DOM answer is canned."""

    def __init__(self, dom: dict[str, Any] | Exception, screenshot: bytes | Exception = b"\x89PNG phone") -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.dom, self.screenshot = dom, screenshot
        outer = self

        class _Emulation:
            async def setDeviceMetricsOverride(self, params: dict[str, Any], session_id: str) -> None:
                outer.calls.append(("viewport", params))

        class _Runtime:
            async def evaluate(self, params: dict[str, Any], session_id: str) -> dict[str, Any]:
                outer.calls.append(("evaluate", {"expression": params["expression"]}))
                if isinstance(outer.dom, Exception):
                    raise outer.dom
                return {"result": {"value": json.dumps(outer.dom)}}

        self.cdp_client = SimpleNamespace(send=SimpleNamespace(Emulation=_Emulation(), Runtime=_Runtime()))

    async def must_get_current_page(self) -> _FakePage:
        return _FakePage()

    async def take_screenshot(self, full_page: bool, format: str) -> bytes:
        self.calls.append(("screenshot", {"full_page": full_page}))
        if isinstance(self.screenshot, Exception):
            raise self.screenshot
        return self.screenshot


@pytest.fixture
def evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    async def no_wait(seconds: float) -> None:
        return None

    monkeypatch.setattr(web_harness, "EVIDENCE", tmp_path)
    monkeypatch.setattr(web_harness, "settle", no_wait)
    return tmp_path


def test_the_phone_look_uses_390x844_and_44px_targets():
    assert web_harness.MOBILE_VIEWPORT == (390, 844) and web_harness.MIN_TAP_TARGET_PX == 44
    js = web_harness.MOBILE_JS
    assert "const min = 44;" in js and "scrollWidth > innerWidth" in js
    for selector in ("a", "button", "input", "select", "textarea", '[role="button"]', "[onclick]"):
        assert selector in web_harness.TAP_TARGETS.split(",")
    assert web_harness.TAP_TARGETS in js


def test_the_phone_look_measures_shoots_and_sets_the_desktop_viewport_back(evidence: Path):
    dom = {"scroll_width": 520, "inner_width": 390, "horizontal_overflow": True, "tap_targets": 12,
           "small_tap_targets": 4}
    session = _FakeSession(dom)
    state = asyncio.run(web_harness.mobile_check(session))
    assert state == {"viewport": "390x844", **dom, "screenshot": "mobile.png"}
    assert (evidence / "mobile.png").read_bytes() == b"\x89PNG phone"
    assert json.loads((evidence / "mobile.json").read_text()) == state
    kinds = [c[0] for c in session.calls]
    assert kinds == ["viewport", "evaluate", "screenshot", "viewport"], "measure and shoot at phone size, then restore"
    assert session.calls[0][1] == {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True}
    assert session.calls[-1][1] == {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False}


def test_a_failed_phone_look_still_sets_the_desktop_viewport_back(evidence: Path):
    session = _FakeSession(RuntimeError("page crashed"))
    state = asyncio.run(web_harness.mobile_check(session))
    assert state["error"].startswith("RuntimeError") and "screenshot" not in state
    assert not (evidence / "mobile.png").exists()
    assert session.calls[-1] == ("viewport", {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False})
