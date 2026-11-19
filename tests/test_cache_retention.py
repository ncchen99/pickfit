"""The one-hour prompt cache for extraction's shared instructions (11/20): request shape, usage and cost."""

from __future__ import annotations

import pytest

from pickfit import extract
from pickfit.anthropic_messages import _usage, to_request
from pickfit.meta import PRICES, Usage, cost_usd


def body(**extra):
    return {"model": "claude-opus-5-5", "instructions": "Extract.", "input": "<source>README</source>",
            "max_output_tokens": 4000, "store": False, **extra}


def test_one_hour_retention_marks_only_the_system_prompt() -> None:
    kwargs, _ = to_request("responses", body(prompt_cache_retention="1h"))
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "cache_control" not in kwargs  # the per-record sources are still not written to the cache
    kwargs, _ = to_request("responses", body())
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}  # default: five minutes
    with pytest.raises(ValueError, match="prompt_cache_retention"):
        to_request("responses", body(prompt_cache_retention="24h"))


def test_every_extraction_request_asks_for_the_hour() -> None:
    src = [extract.Source(id="readme", kind="readme", url=None, text="# tool\n\nInstall with pip.")]
    for kw in ({}, {"features_only": True}):
        b = extract.build_body(src, **kw)
        assert b["prompt_cache_retention"] == "1h"
        kwargs, _ = to_request("responses", {**b, "model": "claude-opus-5-5", "max_output_tokens": 4000})
        assert kwargs["system"][0]["cache_control"]["ttl"] == "1h"
        assert kwargs["messages"][0]["role"] == "user" and "cache_control" not in kwargs


def test_an_hours_write_is_read_from_the_usage_and_charged_twice_the_input() -> None:
    raw = {"input_tokens": 100, "cache_creation_input_tokens": 6000, "cache_read_input_tokens": 0,
           "output_tokens": 0, "cache_creation": {"ephemeral_1h_input_tokens": 6000, "ephemeral_5m_input_tokens": 0}}
    details = _usage(raw, "responses")["input_tokens_details"]
    assert details == {"cached_tokens": 0, "cache_write_tokens": 6000, "cache_write_1h_tokens": 6000}
    price = PRICES[("anthropic", "claude-opus-5-5")]
    hour = Usage(input_tokens=6100, cache_write_tokens=6000, cache_write_1h_tokens=6000)
    five = Usage(input_tokens=6100, cache_write_tokens=6000)
    assert cost_usd(price, hour) == pytest.approx((100 * price.input + 6000 * price.input * 2) / 1e6)
    assert cost_usd(price, five) == pytest.approx((100 * price.input + 6000 * price.cache_write) / 1e6)
