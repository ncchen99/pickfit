"""Web app records (P2.8): ids, the address to open, and records built from a site and its extraction."""

from __future__ import annotations

import pytest

from pickfit import webrecords as wr


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
