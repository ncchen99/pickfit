"""The web sandbox's own guards (P3.12): the browser's network path, its flags, typing, browser-use's settings."""

from __future__ import annotations

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
