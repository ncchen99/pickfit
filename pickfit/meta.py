"""call_meta: the only way pickfit calls a model.

Since 2026-11-15 the models are Claude models on the Anthropic API (ANTHROPIC_API_KEY). The name and the
request shapes are from the hackathon, when the product ran on Meta's models: callers still build Chat
Completions or Responses requests, and pickfit.anthropic_messages turns them into Messages API calls and
the answers back. The hackathon's providers (Meta, Baseten, Modal's endpoint, OpenRouter) stay reachable
by naming one of their model ids or `provider=`; nothing routes to them by default. Modal's endpoint is
still the only one that takes video ("open-modal").

The same Claude models can be reached through Amazon Bedrock (pickfit.bedrock_messages): PICKFIT_CLAUDE_VIA=bedrock
sends there every Claude call that names no provider, and `provider="bedrock"` one call. The model is the same
one or the call is refused; the ledger row says provider and budget "bedrock". When Bedrock throttles, is down,
is over its own cap or its Claude declines the request, the call goes to the direct API instead, and both
attempts are in the ledger and the trace.

Every call goes through the same steps:

1. Route the model ("dev" and "open" -> Claude Haiku, "prod" or nothing -> Claude Opus) and refuse models
   without a known price, a contributor model for non-public data, and body
   keys that would get around these checks or the cost bound.
2. Serve from the response cache when possible (free, still traced). The cache
   is on by default for the dev model only, and keeps only complete,
   valid answers.
3. Reserve a worst-case cost in the shared ledger. The ledger records every call; it stops one
   (BudgetExceeded, before anything is sent) only at a per-scope cap or a cap the user set.
4. Send with the SDK's own retries off, so every attempt is visible: 429 backs
   off (honoring Retry-After), 500/502/503/529 get up to 3 tries, 504 is retried
   once with streaming.
5. Settle the ledger to the actual cost. A 4xx or a request that never left is
   released; a 5xx, timeout or dropped connection may still be billed, so it
   keeps its worst-case estimate. One trace line per attempt goes to
   runs/traces/<Taipei date>.jsonl. API keys never reach a trace or a raised error.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import random
import re
import sys
import threading
import time
from dataclasses import asdict, dataclass, replace
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal

import anthropic
import openai
from pydantic import BaseModel, ValidationError

from pickfit import anthropic_messages, bedrock_messages
from pickfit.env import REPO_ROOT, get_env, require_env
from pickfit.ledger import (
    BudgetExceeded,
    OPENROUTER_CAPS,
    Ledger,
    baseten_ledger,
    bedrock_caps,
    bedrock_ledger,
    default_ledger,
    modal_llm_ledger,
    openrouter_ledger,
    pipeline_caps,
    taipei_date,
    taipei_now,
)

Endpoint = Literal["chat", "responses"]


@dataclass(frozen=True)
class Provider:
    base_url: str
    key_env: str
    secret_env: str | None = None  # Modal's proxy auth is "<token id>.<token secret>"


DEFAULT_PROVIDER = "anthropic"
PROVIDERS: dict[str, Provider] = {
    "anthropic": Provider("https://api.anthropic.com", "ANTHROPIC_API_KEY"),
    # The same Claude models on Amazon Bedrock, signed with an IAM key that may only invoke them
    # (deploy/watch/aws-bedrock-policy.json). Reached by provider= or PICKFIT_CLAUDE_VIA, never by default.
    "bedrock": Provider("https://bedrock-runtime.{region}.amazonaws.com", "PICKFIT_BEDROCK_ACCESS_KEY_ID",
                        "PICKFIT_BEDROCK_SECRET_ACCESS_KEY"),
    # The hackathon's providers (to 2026-11-04): reached only by one of their model ids or provider=.
    "meta": Provider("https://api.meta.ai/v1", "MODEL_API_KEY"),
    "baseten": Provider("https://inference.baseten.co/v1", "BASETEN_API_KEY"),
    # Muse Spark Open on the hackathon's Modal Shared Endpoint (Modal credits), set up by the coordinating session.
    "modal": Provider("https://ncchen99--ep-pickfit-spark-open-server.us-west.modal.direct/v1",
                      "MODAL_PROXY_TOKEN_ID", "MODAL_PROXY_TOKEN_SECRET"),
    # Meta's own models resold by OpenRouter, pinned to Meta as the provider (OPENROUTER_PIN).
    "openrouter": Provider("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}

# PICKFIT_META_VIA=openrouter sends every Meta-model call to OpenRouter instead of Meta's API (11/3: Meta answered
# the team's key with 402 "billing_not_configured"). The model is the same and Meta serves it: OpenRouter may not
# fall back to another provider, nor to one that collects data. Records and the ledger keep Meta's model id, and the
# row's provider and budget say "openrouter". The contributor tier is not on OpenRouter, so muse-spark-1.3 serves it
# and is what the records name.
META_VIA = ("meta", "openrouter")
OPENROUTER_MODELS = {"muse-spark-1.3": "meta/muse-spark-1.3", "muse-spark-1.3-contributor": "meta/muse-spark-1.3",
                     "muse-wonder-1.0": "meta/muse-wonder"}
OPENROUTER_PIN = {"order": ["meta"], "allow_fallbacks": False, "data_collection": "deny"}

# PICKFIT_CLAUDE_VIA=bedrock sends a Claude call that names no provider through Amazon Bedrock instead of
# Anthropic's API, when Bedrock serves that same model (bedrock_messages.MODELS); any other Claude model stays on
# the direct API. A call site that needs what Bedrock lacks says provider="anthropic" (pickfit.msg_batch does).
CLAUDE_VIA = ("anthropic", "bedrock")
CLAUDE_PROVIDERS = ("anthropic", "bedrock")

# The tiers the pipeline asks for by name. PICKFIT_MODE picks one when a caller passes none, and prod when it is
# unset (since 11/19; it was dev, so a `verify --batch` without --model ran its agent on Haiku on 11/16-11/17).
# - prod: the model behind every product decision (extraction, verification agent, judges, scoring).
# - dev: the cheap model for trying a prompt; its answers are cached by default. Asked for by name only
#   (`--model dev`, PICKFIT_MODE=dev), and said on stderr when it is.
# - open: the bulk model for screens over thousands of candidates. The name is from the hackathon, when this
#   tier was Muse Spark Open (open weights) on Baseten.
PROD_MODEL = "claude-opus-5-5"
BULK_MODEL = "claude-haiku-5-5"
# What "prod" has been. A candidate muse-spark-1.3 read during the hackathon counts as read by the prod
# model, so asking for prod extractions does not pay to read a thousand of them again.
PROD_MODELS = (PROD_MODEL, "muse-spark-1.3")
MODE_ALIASES = {"dev": BULK_MODEL, "prod": PROD_MODEL}
# With provider="meta" the same two names mean what they did during the hackathon.
META_MODE_ALIASES = {"dev": "muse-spark-1.3-contributor", "prod": "muse-spark-1.3"}
OPEN_MODEL = "meta-models/muse-spark-open-1026"  # Muse Spark Open on Baseten; existing records name it
MODAL_OPEN_MODEL = "meta-models/Muse-Spark-Open-816B-A42B"  # the same open-weight model, on Modal
# "open-modal" is still Modal's endpoint: the only model here that takes video.
OPEN_ALIASES = {"open": BULK_MODEL, "open-modal": MODAL_OPEN_MODEL}
BASETEN_PREFIX = "meta-models/"
META_PREFIX = "muse-"
OPEN_PROVIDERS = ("baseten", "modal")
# Providers that keep no conversations: previous_response_id means nothing to them.
STATELESS_PROVIDERS = (*OPEN_PROVIDERS, "openrouter", *CLAUDE_PROVIDERS)


@dataclass(frozen=True)
class Price:
    """USD per 1M tokens. `cached=None` means unknown, so cached input is charged at `input`.

    `cache_write` is input written to the provider's prompt cache (only Anthropic reports such tokens;
    None charges them at `input`). `long_context` is (input tokens, factor): a request with more input
    than that is billed at `factor` times every rate.
    """

    input: float
    output: float
    cached: float | None = None
    cache_write: float | None = None
    long_context: tuple[int, float] | None = None


def _claude(input: float, output: float, cached: float | None = None,  # noqa: A002 - the price's own word
            long_context: tuple[int, float] | None = None) -> Price:
    """A Claude price: input written to the 5-minute prompt cache is billed at 1.25x input."""
    return Price(input=input, output=output, cached=cached, cache_write=input * 1.25, long_context=long_context)


# A model missing here is refused, never billed as $0.
PRICES: dict[tuple[str, str], Price] = {
    # Anthropic's list prices, 2026-11-03. Cache reads are 0.05x input on Opus 5.5 and Sonnet 5.5, 0.1x on
    # Haiku. Haiku's rates are for prompts up to 100K tokens; a longer one is billed at 5x.
    ("anthropic", "claude-opus-5-5"): _claude(4.00, 20.00, cached=0.20),
    ("anthropic", "claude-sonnet-5-5"): _claude(2.00, 10.00, cached=0.10),
    ("anthropic", "claude-haiku-5-5"): _claude(0.10, 0.50, cached=0.01, long_context=(100_000, 5.0)),
    ("anthropic", "claude-fable-5-2"): _claude(8.00, 40.00, cached=0.20),
    # Models a declined request may fall back to (anthropic_messages.FALLBACK_BETA): priced when one answers.
    ("anthropic", "claude-opus-5"): _claude(5.00, 25.00),
    ("anthropic", "claude-opus-4-8"): _claude(5.00, 25.00),
    ("anthropic", "claude-sonnet-5"): _claude(2.00, 10.00),
    # Amazon Bedrock, global cross-Region inference: aws.amazon.com/bedrock/pricing ("Global Cross-region
    # Inference", Anthropic models; its price data was published 2026-11-20), read 2026-11-21. The same as
    # Anthropic's list: Opus 5.5 $4 in, $20 out, $5 a 5-minute and $8 an hour's cache write, $0.20 a cache
    # read; Haiku 5.5 has its own "Long Context" row at 5x (the 100K threshold is Anthropic's, AWS names none).
    # A geographic or single-Region profile is 10% more and is not what bedrock_messages.PROFILE sends.
    ("bedrock", "claude-opus-5-5"): _claude(4.00, 20.00, cached=0.20),
    ("bedrock", "claude-haiku-5-5"): _claude(0.10, 0.50, cached=0.01, long_context=(100_000, 5.0)),
    # The hackathon's providers, measured or confirmed 2026-10-28.
    ("meta", "muse-spark-1.3"): Price(input=1.25, output=4.25, cached=0.15),
    ("meta", "muse-spark-1.3-contributor"): Price(input=0.10, output=0.20),
    ("meta", "muse-wonder-1.0"): Price(input=4.00, output=20.00),
    ("baseten", "meta-models/muse-spark-open"): Price(input=1.25, output=4.25, cached=0.15),
    ("baseten", "meta-models/muse-spark-open-1026"): Price(input=1.25, output=4.25, cached=0.15),
    ("modal", MODAL_OPEN_MODEL): Price(input=1.25, output=4.25, cached=0.15),  # the coordinator's quote, 11/1
    # OpenRouter's list prices for Meta's models (11/3); its cached-input price is not listed, so cached is input.
    ("openrouter", "muse-spark-1.3"): Price(input=1.25, output=4.25),
    ("openrouter", "muse-wonder-1.0"): Price(input=4.00, output=20.00),
}
WEB_SEARCH_USD = 2.50 / 1000

# Claude has no "minimal": it runs as "low" (anthropic_messages.EFFORT), and its thinking cannot be switched off.
EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")
MAX_EFFORT_MODELS = {"muse-spark-1.3", "muse-wonder-1.0"}  # of Meta's models; every Claude model takes "max"

# Worst-case estimate knobs (used only to reserve budget before sending).
BYTES_PER_TOKEN = 3  # UTF-8 JSON bytes per token; low on purpose so estimates run high
IMAGE_TOKENS = 3_000  # a ~1280px image is about 1,300-1,500 tokens
# A video: Muse Spark Open on Modal samples 2 frames a second at ~124 tokens each (probe 11/2); pickfit's screen
# recordings stop at 15 minutes (record.MAX_SECONDS), so VIDEO_TOKENS is their worst case. A caller that knows the
# videos' length passes video_seconds, and they are reserved at VIDEO_TOKENS_PER_S with a margin.
VIDEO_TOKENS = 230_000
VIDEO_TOKENS_PER_S = 250
UNKNOWN_CONTEXT_TOKENS = 32_000  # previous_response_id with no tokens in the ledger
WEB_SEARCHES_PER_CALL = 3  # default max_tool_calls when web_search is on (meta-usage-design)
TOKENS_PER_WEB_SEARCH = 5_000

# Retry policy (the SDK's own retries are disabled).
RATE_LIMIT_TRIES = 6
SERVER_ERROR_TRIES = 3
RETRY_STATUSES = {500, 502, 503, 529}  # 529: Anthropic is overloaded
# Meta's API has answered 404 "model not found" for a model it serves, on and off for minutes (10/29,
# 11/1 01:46-01:49). A 404 is refused before generation, so it is released and tried again, backing off
# for about two minutes in all; a model that is really gone fails after that.
NOT_FOUND_TRIES = 8
BACKOFF_BASE_S = 2.0
BACKOFF_MAX_S = 60.0
CLIENT_TIMEOUT_S = 600.0
# Bedrock is tried this many times when it throttles or fails before the call goes to the direct API: the
# long waits above are for a provider with nowhere else to go.
BEDROCK_TRIES = 2

PING_MAX_OUTPUT_TOKENS = 1_024  # thinking shares this limit, and Claude always thinks
TRACE_TEXT_LIMIT = 4_000

# Request keys that call_meta sets itself; callers pass them as arguments instead.
_RESERVED_KEYS = {"model", "max_tokens", "max_completion_tokens", "max_output_tokens",
                  "stream", "stream_options", "reasoning_effort"}
# SDK control arguments: the SDK applies them after our checks, so they could swap the model,
# lift the output limit or change the client timeout.
_SDK_CONTROLS = {"extra_body", "extra_headers", "extra_query", "timeout"}
# Body keys that would make the reservation too small: server-side context that is never
# estimated (Responses `conversation`, `prompt`) and Chat search with no call limit.
_FORBIDDEN_KEYS = _SDK_CONTROLS | {"conversation", "prompt", "web_search_options"}
# Chat finish_reason or Responses status of a complete answer; anything else is never cached.
_COMPLETE_STATUSES = {"stop", "tool_calls", "completed"}
# Transport errors raised before the request was written, so nothing can have been billed.
# Matched by name because the SDK's HTTP library differs across openai versions (httpx/httpx2).
_UNSENT_ERRORS = {"ConnectError", "ConnectTimeout"}
_KEY_PATTERN = re.compile(r"LLM_\d+_[A-Za-z0-9_\-]+|sk-ant-[A-Za-z0-9_\-]+")
# The two SDKs raise their own classes with the same shape (status_code, response, message, body).
_STATUS_ERRORS = (openai.APIStatusError, anthropic.APIStatusError)
_TIMEOUT_ERRORS = (openai.APITimeoutError, anthropic.APITimeoutError)
_CONNECTION_ERRORS = (openai.APIConnectionError, anthropic.APIConnectionError)
_API_ERRORS = (openai.APIError, anthropic.APIError)

sleep = time.sleep  # tests replace this to skip backoff waits


class ModelRefused(ValueError):
    """The model has no known price, or does not fit the data policy."""


class PrivateDataRefused(ModelRefused):
    """A contributor model (may train on inputs) was asked to handle non-public data."""


class StreamIncomplete(RuntimeError):
    """A streamed response ended without its final event."""


@dataclass
class Usage:
    """Token counts in one shape for both APIs. Input includes cached; output includes reasoning."""

    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    web_searches: int = 0
    cache_write_tokens: int = 0  # of input_tokens, written to the provider's prompt cache (Anthropic)
    cache_write_1h_tokens: int = 0  # of cache_write_tokens, written for an hour (2x input instead of cache_write)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Usage | None:
        """Read Chat (`prompt_tokens`) or Responses (`input_tokens`) usage; None if absent.

        Claude's usage arrives in the same fields (anthropic_messages._usage). Its thinking is part of the
        output tokens and is not counted apart, so reasoning_tokens stays 0 for it.
        """
        u = raw.get("usage")
        if not isinstance(u, dict):
            return None
        searches = sum(1 for item in raw.get("output") or [] if item.get("type") == "web_search_call")
        if "prompt_tokens" in u:
            details = u.get("prompt_tokens_details") or {}
            return cls(
                input_tokens=u.get("prompt_tokens") or 0,
                cached_tokens=details.get("cached_tokens") or 0,
                output_tokens=u.get("completion_tokens") or 0,
                reasoning_tokens=(u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0,
                web_searches=searches,
                cache_write_tokens=details.get("cache_write_tokens") or 0,
                cache_write_1h_tokens=details.get("cache_write_1h_tokens") or 0,
            )
        details = u.get("input_tokens_details") or {}
        return cls(
            input_tokens=u.get("input_tokens") or 0,
            cached_tokens=details.get("cached_tokens") or 0,
            output_tokens=u.get("output_tokens") or 0,
            reasoning_tokens=(u.get("output_tokens_details") or {}).get("reasoning_tokens") or 0,
            web_searches=searches,
            cache_write_tokens=details.get("cache_write_tokens") or 0,
            cache_write_1h_tokens=details.get("cache_write_1h_tokens") or 0,
        )


@dataclass
class ToolCall:
    call_id: str | None
    name: str
    arguments: str

    def json_arguments(self) -> Any:
        """Arguments as JSON. Meta does not guarantee they match the tool schema: validate them."""
        return json.loads(self.arguments or "{}")


@dataclass
class MetaResult:
    provider: str
    model: str
    endpoint: Endpoint
    text: str | None
    tool_calls: list[ToolCall]
    output_items: list[dict[str, Any]]
    usage: Usage | None
    cost_usd: float
    response_id: str | None
    status: str | None  # Chat finish_reason or Responses status
    reasoning_summary: str | None
    cache_hit: bool
    attempts: int
    request_hash: str
    raw: dict[str, Any]
    parsed: Any = None
    parse_error: str | None = None


# ---------------------------------------------------------------- routing and pricing


DEFAULT_MODE = "prod"
_dev_noted: set[str] = set()  # where the dev tier came from, once said on stderr in this process


def _note_dev(source: str, model: str) -> None:
    """One stderr line per process when the dev tier is in use: it is never the default any more."""
    if source in _dev_noted:
        return
    _dev_noted.add(source)
    print(f"pickfit: model tier dev ({model}) from {source}; product runs use prod (Claude Opus)", file=sys.stderr)


def resolve_model(model: str | None, provider: str = DEFAULT_PROVIDER) -> str:
    """Map "dev"/"prod" (or PICKFIT_MODE when None, else prod), "open" and "open-modal" to a model id."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; expected one of {sorted(PROVIDERS)}")
    if model in OPEN_ALIASES:
        return OPEN_ALIASES[model]
    if provider in OPEN_PROVIDERS:
        if model is None or model in MODE_ALIASES:
            raise ModelRefused(f"{provider} calls need an explicit model id, e.g. meta-models/muse-spark-open")
        return model
    source = "the caller"
    if model is None:
        mode = get_env("PICKFIT_MODE")
        model, source = (mode, "PICKFIT_MODE") if mode else (DEFAULT_MODE, "the default")
        if model not in MODE_ALIASES:
            raise ValueError(f"PICKFIT_MODE must be one of {sorted(MODE_ALIASES)}, got {model!r}")
    aliases = META_MODE_ALIASES if provider == "meta" else MODE_ALIASES
    resolved = aliases.get(model, model)
    if model == "dev":
        _note_dev(source, resolved)
    return resolved


def provider_for(model: str) -> str:
    """The provider that serves a model id: Anthropic, unless the id is one of the hackathon's (Modal's
    endpoint model, Baseten's meta-models/ slugs, Meta's muse- models)."""
    if model == MODAL_OPEN_MODEL:
        return "modal"
    if model.startswith(BASETEN_PREFIX):
        return "baseten"
    return "meta" if model.startswith(META_PREFIX) else DEFAULT_PROVIDER


def meta_via() -> str:
    """Where Meta-model calls go: "meta" (Meta's API, the default) or "openrouter" (PICKFIT_META_VIA)."""
    via = get_env("PICKFIT_META_VIA") or "meta"
    if via not in META_VIA:
        raise ValueError(f"PICKFIT_META_VIA must be one of {META_VIA}, got {via!r}")
    return via


def claude_via() -> str:
    """Where Claude calls that name no provider go: "anthropic" (the direct API, the default) or "bedrock"
    (PICKFIT_CLAUDE_VIA)."""
    via = get_env("PICKFIT_CLAUDE_VIA") or DEFAULT_PROVIDER
    if via not in CLAUDE_VIA:
        raise ValueError(f"PICKFIT_CLAUDE_VIA must be one of {CLAUDE_VIA}, got {via!r}")
    return via


_notes: set[str] = set()  # what has been said once on stderr in this process


def _note_once(key: str, text: str) -> None:
    if key not in _notes:
        _notes.add(key)
        print(f"pickfit: {text}", file=sys.stderr)


def _provider_by_setting(model: str) -> str:
    """The provider of a call that named none: the one serving the model id, or Bedrock for a Claude model
    when PICKFIT_CLAUDE_VIA says so and Bedrock serves that model. One it does not serve stays on the direct
    API, the same model, and that is said once."""
    provider = provider_for(model)
    if provider != DEFAULT_PROVIDER or claude_via() != "bedrock":
        return provider
    if bedrock_messages.offers(model):
        return "bedrock"
    _note_once(f"not-on-bedrock:{model}", f"{model} is not offered through Amazon Bedrock here; its calls "
                                          "stay on Anthropic's API")
    return provider


def route(provider: str, model: str) -> tuple[str, str]:
    """The provider a call goes to and the model id it sends: a Meta-model call goes to OpenRouter (under
    OpenRouter's id) when PICKFIT_META_VIA says so, a Bedrock call names the model's inference profile (and
    is refused when Bedrock does not serve that model); every other call as it is."""
    if provider == "bedrock":
        try:
            return provider, bedrock_messages.wire_model(model)
        except bedrock_messages.NotOnBedrock as err:
            raise ModelRefused(str(err)) from None
    if provider == "meta" and meta_via() == "openrouter":
        provider = "openrouter"
    if provider != "openrouter":
        return provider, model
    if model not in OPENROUTER_MODELS:
        raise ModelRefused(f"{model} is not on OpenRouter; unset PICKFIT_META_VIA to call Meta's API")
    return provider, OPENROUTER_MODELS[model]


def is_open_model(model: str | None) -> bool:
    """True when `model` (an alias or an id) is the bulk tier ("open", the dev model) or Muse Spark Open,
    rather than the model product decisions are made with. A run on such a model keeps its judges on prod."""
    if model is None:
        return False
    resolved = OPEN_ALIASES.get(model, MODE_ALIASES.get(model, model))
    return resolved == BULK_MODEL or provider_for(resolved) in OPEN_PROVIDERS


def price_for(provider: str, model: str) -> Price:
    try:
        return PRICES[(provider, model)]
    except KeyError:
        raise ModelRefused(f"no price for {provider}/{model}; add it to PRICES before calling it") from None


def _long_factor(price: Price, input_tokens: int) -> float:
    return price.long_context[1] if price.long_context and input_tokens > price.long_context[0] else 1.0


def cost_usd(price: Price, usage: Usage) -> float:
    cached = min(usage.cached_tokens, usage.input_tokens)
    written = min(usage.cache_write_tokens, usage.input_tokens - cached)
    cached_rate = price.input if price.cached is None else price.cached
    write_rate = price.input if price.cache_write is None else price.cache_write
    hour = min(usage.cache_write_1h_tokens, written)  # an hour's write: 2x input (Anthropic)
    token_usd = ((usage.input_tokens - cached - written) * price.input + cached * cached_rate
                 + (written - hour) * write_rate + hour * price.input * 2 + usage.output_tokens * price.output
                 ) / 1_000_000
    return token_usd * _long_factor(price, usage.input_tokens) + usage.web_searches * WEB_SEARCH_USD


def _has_web_search(body: dict[str, Any]) -> bool:
    return any(isinstance(t, dict) and str(t.get("type", "")).startswith("web_search")
               for t in body.get("tools") or [])


def estimate_input_tokens(body: dict[str, Any], video_seconds: float | None = None) -> int:
    """Rough upper estimate from request size; each image counts as IMAGE_TOKENS, each video as VIDEO_TOKENS.

    An image is an `image_url` / `input_image` part (inline data, https URL or file_id)
    or any other inline `data:image/` string; a video a `video_url` / `input_video` part or a `data:video/` string.
    """
    images = videos = 0

    def strip_images(value: Any) -> Any:
        nonlocal images, videos
        if isinstance(value, str) and value.startswith("data:image/"):
            images += 1
            return ""
        if isinstance(value, str) and value.startswith("data:video/"):
            videos += 1
            return ""
        if isinstance(value, dict):
            if value.get("type") in ("image_url", "input_image"):
                images += 1
                return {}
            if value.get("type") in ("video_url", "input_video"):
                videos += 1
                return {}
            return {k: strip_images(v) for k, v in value.items()}
        if isinstance(value, list):
            return [strip_images(v) for v in value]
        return value

    size = len(json.dumps(strip_images(body), ensure_ascii=False).encode("utf-8"))
    video_tokens = videos * VIDEO_TOKENS if video_seconds is None or not videos else \
        int(video_seconds * VIDEO_TOKENS_PER_S * 1.25) + 500 * videos
    return size // BYTES_PER_TOKEN + 1 + images * IMAGE_TOKENS + video_tokens


def estimate_cost(price: Price, request: dict[str, Any], max_output_tokens: int,
                  context_tokens: int = 0, video_seconds: float | None = None) -> float:
    """Worst case for one attempt: estimated input + context + every allowed output token.

    With web_search on, every allowed built-in tool call (`max_tool_calls`) is a search.
    """
    searches = request.get("max_tool_calls", WEB_SEARCHES_PER_CALL) if _has_web_search(request) else 0
    tokens_in = estimate_input_tokens(request, video_seconds) + context_tokens + searches * TOKENS_PER_WEB_SEARCH
    # The worst case for input: none of it read from a cache, all of it written to one.
    input_rate = max(price.input, price.cache_write or 0.0)
    token_usd = (tokens_in * input_rate + max_output_tokens * price.output) / 1_000_000
    return token_usd * _long_factor(price, tokens_in) + searches * WEB_SEARCH_USD


def _previous_context(request: dict[str, Any], ledger: Ledger) -> int:
    """Tokens the server adds back for previous_response_id, looked up in the shared ledger
    so a chain resumed in another process is still estimated from its real size."""
    previous = request.get("previous_response_id")
    if not previous:
        return 0
    tokens = ledger.context_tokens(previous)
    return UNKNOWN_CONTEXT_TOKENS if tokens is None else tokens


# ---------------------------------------------------------------- requests


def build_request(endpoint: Endpoint, model: str, body: dict[str, Any],
                  max_output_tokens: int, reasoning_effort: str) -> dict[str, Any]:
    """Full request body: the caller's body plus model, output limit and reasoning effort.

    Refuses body keys that would get around the model policy, the price or the cost bound.
    """
    clashes = _RESERVED_KEYS & body.keys()
    if clashes:
        raise ValueError(f"pass {sorted(clashes)} as call_meta arguments, not in body")
    forbidden = _FORBIDDEN_KEYS & body.keys()
    if forbidden:
        raise ValueError(f"body may not set {sorted(forbidden)}: it would bypass call_meta's checks")
    if body.get("n", 1) != 1:
        raise ValueError("n must be 1: call_meta reserves and records a single completion")
    request = {"model": model, **body}
    if endpoint == "chat":
        if _has_web_search(body):
            raise ValueError("web_search needs endpoint='responses', where max_tool_calls bounds it")
        request["max_completion_tokens"] = max_output_tokens
        request["reasoning_effort"] = reasoning_effort
    elif endpoint == "responses":
        reasoning = dict(body.get("reasoning") or {})
        if "effort" in reasoning:
            raise ValueError("pass reasoning effort as call_meta(reasoning_effort=...)")
        request["reasoning"] = {**reasoning, "effort": reasoning_effort}
        request["max_output_tokens"] = max_output_tokens
        if _has_web_search(body):
            searches = body.get("max_tool_calls", WEB_SEARCHES_PER_CALL)
            if isinstance(searches, bool) or not isinstance(searches, int) or searches <= 0:
                raise ValueError("max_tool_calls must be a positive int")
            request["max_tool_calls"] = searches
    else:
        raise ValueError(f"unknown endpoint {endpoint!r}")
    return request


def request_hash(provider: str, endpoint: Endpoint, request: dict[str, Any]) -> str:
    """sha256 of the canonical JSON of provider + endpoint + full request body."""
    canonical = json.dumps({"provider": provider, "endpoint": endpoint, "request": request},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_policy(provider: str, model: str, public_data_only: bool, effort: str,
                  body: dict[str, Any], max_output_tokens: int) -> None:
    if not isinstance(public_data_only, bool):
        raise TypeError("public_data_only must be True or False")
    if model.endswith("-contributor") and not public_data_only:
        raise PrivateDataRefused(
            f"{model} may train on its inputs; use model='prod' for data that is not public")
    if effort not in EFFORTS:
        raise ValueError(f"reasoning_effort must be one of {EFFORTS}")
    if effort == "max" and provider not in CLAUDE_PROVIDERS and model not in MAX_EFFORT_MODELS:
        raise ValueError(f"{model} does not support reasoning_effort='max'")
    if not isinstance(max_output_tokens, int) or max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be a positive int")
    if provider in STATELESS_PROVIDERS and body.get("previous_response_id"):
        raise ValueError(f"{provider} keeps no conversations; previous_response_id is not supported")
    if provider in CLAUDE_PROVIDERS and _has_web_search(body):
        raise ValueError("web_search is not wired for Claude models")


_clients: dict[str, Any] = {}
_clients_lock = threading.Lock()


def make_client(provider: str = DEFAULT_PROVIDER, *, http_client: Any = None) -> Any:
    """A client with `chat.completions.create` and `responses.create`, with SDK retries off (call_meta
    retries itself): Anthropic's SDK behind pickfit.anthropic_messages.Client (its Bedrock client behind
    pickfit.bedrock_messages.Client), or OpenAI's SDK for the hackathon's providers. The base URL is always
    pickfit's own, never one from the environment."""
    info = PROVIDERS[provider]
    if provider == "bedrock":
        region = get_env("PICKFIT_BEDROCK_REGION") or bedrock_messages.DEFAULT_REGION
        return bedrock_messages.make_client(
            access_key=require_env(info.key_env), secret_key=require_env(info.secret_env), region=region,
            base_url=info.base_url.format(region=region), timeout=CLIENT_TIMEOUT_S, http_client=http_client)
    key = require_env(info.key_env) + (f".{require_env(info.secret_env)}" if info.secret_env else "")
    options = dict(api_key=key, base_url=info.base_url, max_retries=0, timeout=CLIENT_TIMEOUT_S,
                   http_client=http_client)
    if provider == "anthropic":
        return anthropic_messages.Client(anthropic.Anthropic(**options), fallbacks=_anthropic_fallbacks())
    return openai.OpenAI(**options)


def _default_client(provider: str) -> Any:
    with _clients_lock:
        if provider not in _clients:
            _clients[provider] = make_client(provider)
        return _clients[provider]


def _to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict(mode="json")
    return obj.model_dump(mode="json", exclude_unset=True)


def _sdk_kwargs(create: Any, request: dict[str, Any]) -> dict[str, Any]:
    """Split the request into SDK keyword arguments and `extra_body` for the rest.

    `extra_body` holds only keys the SDK does not know, so it cannot override model or
    limits; SDK controls (extra_*, timeout) never come from the request.
    """
    params = inspect.signature(create).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(request)
    known = params.keys() - _SDK_CONTROLS
    kwargs = {k: v for k, v in request.items() if k in known}
    extra = {k: v for k, v in request.items() if k not in known}
    if extra:
        kwargs["extra_body"] = extra
    return kwargs


def _anthropic_fallbacks() -> bool:
    """Whether a request a safety classifier declines is retried on Anthropic's recommended fallback model
    (on unless PICKFIT_ANTHROPIC_FALLBACKS is 0/false/no/off)."""
    return (get_env("PICKFIT_ANTHROPIC_FALLBACKS") or "1").strip().lower() not in {"0", "false", "no", "off"}


def _send(client: Any, endpoint: Endpoint, request: dict[str, Any], stream: bool,
          conversation: bool = False) -> dict[str, Any]:
    create = client.chat.completions.create if endpoint == "chat" else client.responses.create
    kwargs = _sdk_kwargs(create, request)
    if getattr(client, "returns_whole_response", False):  # pickfit's Anthropic client streams inside
        hint = {"conversation": True} if conversation else {}  # where the prompt cache's breakpoint goes
        return _to_dict(create(**kwargs, stream=stream, **hint))
    if not stream:
        return _to_dict(create(**kwargs))
    kwargs["stream"] = True
    if endpoint == "chat":
        kwargs["stream_options"] = {"include_usage": True}
        return _collect_chat_stream(create(**kwargs))
    return _collect_responses_stream(create(**kwargs))


def _collect_chat_stream(stream: Any) -> dict[str, Any]:
    """Aggregate Chat chunks into the shape of a non-streamed chat.completion."""
    raw: dict[str, Any] = {"id": None, "object": "chat.completion", "model": None}
    content: list[str] = []
    reasoning: list[str] = []
    calls: dict[int, dict[str, Any]] = {}
    finish = None
    for chunk in stream:
        c = _to_dict(chunk)
        raw["id"] = raw["id"] or c.get("id")
        raw["model"] = raw["model"] or c.get("model")
        if c.get("usage"):
            raw["usage"] = c["usage"]
        for choice in c.get("choices") or []:
            delta = choice.get("delta") or {}
            content.append(delta.get("content") or "")
            for key in ("reasoning_content", "reasoning"):
                if isinstance(delta.get(key), str):
                    reasoning.append(delta[key])
            for tc in delta.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", 0), {
                    "id": None, "type": "function", "function": {"name": "", "arguments": ""}})
                fn = tc.get("function") or {}
                slot["id"] = slot["id"] or tc.get("id")
                slot["function"]["name"] = slot["function"]["name"] or fn.get("name") or ""
                slot["function"]["arguments"] += fn.get("arguments") or ""
            finish = choice.get("finish_reason") or finish
    message: dict[str, Any] = {"role": "assistant", "content": "".join(content) or None}
    if reasoning:
        message["reasoning_content"] = "".join(reasoning)
    if calls:
        message["tool_calls"] = [calls[i] for i in sorted(calls)]
    raw["choices"] = [{"index": 0, "message": message, "finish_reason": finish}]
    return raw


def _collect_responses_stream(stream: Any) -> dict[str, Any]:
    """Keep the final response object from a Responses event stream."""
    final = None
    for event in stream:
        e = _to_dict(event)
        if e.get("type") in ("response.completed", "response.incomplete", "response.failed"):
            final = e.get("response")
    if not isinstance(final, dict):
        raise StreamIncomplete("Responses stream ended without response.completed")
    return final


# ---------------------------------------------------------------- results


def _read_result(endpoint: Endpoint, raw: dict[str, Any]) -> dict[str, Any]:
    """Text, tool calls, output items, status and reasoning summary from a raw response."""
    if endpoint == "chat":
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        return {
            "text": message.get("content") if isinstance(message.get("content"), str) else None,
            "tool_calls": [ToolCall(tc.get("id"), (tc.get("function") or {}).get("name", ""),
                                    (tc.get("function") or {}).get("arguments") or "")
                           for tc in message.get("tool_calls") or []],
            "output_items": [message] if message else [],
            "status": choice.get("finish_reason"),
            "reasoning_summary": reasoning if isinstance(reasoning, str) and reasoning else None,
        }
    items = raw.get("output") or []
    texts = [part.get("text", "") for item in items if item.get("type") == "message"
             for part in item.get("content") or [] if part.get("type") == "output_text"]
    summaries = [s.get("text", "") for item in items if item.get("type") == "reasoning"
                 for s in item.get("summary") or []]
    return {
        "text": "".join(texts) if texts else None,
        "tool_calls": [ToolCall(item.get("call_id"), item.get("name", ""), item.get("arguments") or "")
                       for item in items if item.get("type") == "function_call"],
        "output_items": items,
        "status": raw.get("status"),
        "reasoning_summary": "\n".join(summaries) or None,
    }


def _parse_output(text: str | None, output_model: type[BaseModel] | None) -> tuple[Any, str | None]:
    if output_model is None:
        return None, None
    if not text:
        return None, "no text output to parse"
    try:
        return output_model.model_validate_json(text), None
    except ValidationError as err:
        return None, str(err)[:TRACE_TEXT_LIMIT]


# ---------------------------------------------------------------- cache and trace


def _runs_dir(runs_dir: Path | str | None) -> Path:
    return Path(runs_dir or get_env("PICKFIT_RUNS_DIR") or REPO_ROOT / "runs")


def _cache_enabled(cache: bool | None, model: str) -> bool:
    """The `cache` argument, else PICKFIT_CACHE, else on only for the dev model (and Meta's contributor one).

    Prod runs and re-verification must ask the model again, not replay an old answer. The bulk screens run
    on the same model as dev, so they pass cache=False themselves.
    """
    if cache is not None:
        return cache
    setting = get_env("PICKFIT_CACHE")
    if setting is not None:
        return setting.strip().lower() not in {"0", "false", "no", "off"}
    return model == MODE_ALIASES["dev"] or model.endswith("-contributor")


def _cacheable(result: MetaResult) -> bool:
    """Only a complete, billed, valid answer may be cached or served from the cache.

    A truncated (`length`), filtered, incomplete or unparsable answer is never replayed,
    so retrying it reaches the model.
    """
    return (result.usage is not None and result.status in _COMPLETE_STATUSES
            and result.parse_error is None)


def _cache_read(runs: Path, key: str) -> dict[str, Any] | None:
    try:
        entry = json.loads((runs / "cache" / f"{key}.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return entry.get("raw") if isinstance(entry, dict) else None


def _cache_write(runs: Path, key: str, provider: str, endpoint: Endpoint, raw: dict[str, Any]) -> None:
    path = runs / "cache" / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"provider": provider, "endpoint": endpoint, "created_at": taipei_now().isoformat(), "raw": raw}
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


_trace_lock = threading.Lock()


def _redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[redacted]")
    return _KEY_PATTERN.sub("[redacted]", text)


# Every trace line has the same keys; each attempt fills in what it knows.
_TRACE_DEFAULTS: dict[str, Any] = {
    "attempt": None, "stream": False, "cache_hit": False, "status": None, "http_status": None,
    "error": None, "response_id": None, "usage": None, "reserved_usd": 0.0, "cost_usd": 0.0,
    "latency_s": None, "finish": None, "reasoning_summary": None,
}


def _append_trace(runs: Path, record: dict[str, Any], secrets: list[str]) -> None:
    """Append one JSON line; a single O_APPEND write keeps lines whole across processes."""
    record = {"ts": taipei_now().isoformat(timespec="milliseconds"), **_TRACE_DEFAULTS, **record}
    line = _redact(json.dumps(record, ensure_ascii=False, default=str), secrets) + "\n"
    path = runs / "traces" / f"{taipei_date()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _trace_lock:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)


def _header_wait_s(headers: Any) -> float | None:
    """Seconds from `retry-after-ms`, else `retry-after` (seconds or an HTTP date)."""
    try:
        return float(headers["retry-after-ms"]) / 1000
    except (KeyError, TypeError, ValueError):
        pass
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).timestamp() - time.time()
    except (TypeError, ValueError):
        return None


def _retry_after_s(err: Any) -> float | None:
    """The wait the server asked for, clamped to [0, BACKOFF_MAX_S]; None if it gave none."""
    headers = err.response.headers if err.response is not None else {}
    wait = _header_wait_s(headers)
    return None if wait is None else min(max(0.0, wait), BACKOFF_MAX_S)


def _backoff_s(tries: int) -> float:
    return min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2 ** (tries - 1)) * (0.5 + random.random() / 2)


@dataclass
class _Retry:
    """Retry bookkeeping for one call_meta call."""

    rate_limited: int = 0
    server_errors: int = 0
    not_found: int = 0
    stream: bool = False
    retry_not_found: bool = True  # Meta's on-and-off 404; any other provider's 404 is a wrong model id
    tries: int = 0  # tries on a 429 and on a server error; 0 for RATE_LIMIT_TRIES and SERVER_ERROR_TRIES

    def after_http_error(self, err: Any) -> bool:
        """Whether to try again after an HTTP error; sleeps first when backing off."""
        if err.status_code == 429:
            self.rate_limited += 1
            if self.rate_limited >= (self.tries or RATE_LIMIT_TRIES):
                return False
            wait = _retry_after_s(err)
            sleep(wait if wait is not None else _backoff_s(self.rate_limited))
            return True
        if err.status_code in RETRY_STATUSES:
            return self.after_server_error()
        if err.status_code == 404 and self.retry_not_found:
            self.not_found += 1
            if self.not_found >= NOT_FOUND_TRIES:
                return False
            sleep(_backoff_s(self.not_found))
            return True
        if err.status_code == 504:
            return self.switch_to_stream()
        return False

    def after_server_error(self) -> bool:
        self.server_errors += 1
        if self.server_errors >= (self.tries or SERVER_ERROR_TRIES):
            return False
        sleep(_backoff_s(self.server_errors))
        return True

    def switch_to_stream(self) -> bool:
        """A gateway or client timeout: retry once with streaming, which has no time limit."""
        if self.stream:
            return False
        self.stream = True
        return True


def _error_info(err: BaseException) -> dict[str, Any]:
    return {"type": type(err).__name__, "message": str(err)[:1000]}


def _scrub_error(err: BaseException, secrets: list[str]) -> None:
    """Redact keys in the exception itself, so the caller's traceback is as clean as the trace."""
    err.args = tuple(_redact(a, secrets) if isinstance(a, str) else a for a in err.args)
    if isinstance(err, _API_ERRORS):
        err.message = _redact(err.message, secrets)
        if err.body is not None:
            err.body = json.loads(_redact(json.dumps(err.body, default=str), secrets))


def _never_sent(err: BaseException) -> bool:
    """Whether a transport error happened before the request left (so it cannot be billed)."""
    cause = err.__cause__
    return cause is not None and any(c.__name__ in _UNSENT_ERRORS for c in type(cause).__mro__)


# ---------------------------------------------------------------- call_meta


def call_meta(
    endpoint: Endpoint,
    body: dict[str, Any],
    *,
    stage: str,
    public_data_only: bool,
    max_output_tokens: int,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str = "minimal",
    scope: str | None = None,
    scope_cap_usd: float | None = None,
    run_id: str | None = None,
    output_model: type[BaseModel] | None = None,
    cache: bool | None = None,
    client: Any = None,
    ledger: Ledger | None = None,
    runs_dir: Path | str | None = None,
    video_seconds: float | None = None,
    conversation: bool = False,
) -> MetaResult:
    """Call a model with a Chat Completions (`chat`) or Responses (`responses`) request.

    The model is a Claude model unless the id or `provider` names one of the hackathon's; a Claude call is
    sent as a Messages API request and answered in the endpoint's own shape (pickfit.anthropic_messages).

    `body` is the request without model, output limit or reasoning effort, e.g.
    {"messages": [...]} or {"input": ..., "tools": [...]} (Meta only: "previous_response_id",
    and a web_search tool, whose searches `max_tool_calls` caps).
    `public_data_only` must be True for contributor models. `scope_cap_usd` caps what
    `scope` may spend within `run_id` (e.g. "verify:<slug>" per verification run).
    `output_model` validates the text output as JSON into that pydantic model.
    `cache` defaults to PICKFIT_CACHE, else on for the dev model only.
    `provider` defaults to the one serving the model, and `ledger` to that provider's budget in the shared
    ledger (Claude calls: "pipeline", or "bedrock" when Amazon Bedrock serves them: PICKFIT_CLAUDE_VIA moves
    there a call that brings neither a provider nor a client, and such a call comes back from the direct API
    when Bedrock gives way, see _bedrock_gave_way). `video_seconds`: the videos' total length, so they are reserved at
    their size rather than at VIDEO_TOKENS each. `conversation`: the caller sends this request's history again
    on its next turn (an agent loop), so a Claude call caches it from the first turn on; a single call leaves
    it out, since a cache write nothing reads back costs more than plain input.
    """
    model = resolve_model(model, provider or DEFAULT_PROVIDER)
    if provider is None:  # a client the caller built is for the provider serving the model: the setting keeps off
        provider = _provider_by_setting(model) if client is None else provider_for(model)
    provider, wire_model = route(provider, model)
    _check_policy(provider, model, public_data_only, reasoning_effort, body, max_output_tokens)
    if provider == "openrouter":
        model = model.removesuffix("-contributor")  # the model that serves it (OPENROUTER_MODELS)
    price = price_for(provider, model)
    request = build_request(endpoint, wire_model, body, max_output_tokens, reasoning_effort)
    if provider == "openrouter":
        request["provider"] = dict(OPENROUTER_PIN)
    key = request_hash(provider, endpoint, request)
    runs = _runs_dir(runs_dir)
    base = {"run_id": run_id, "stage": stage, "scope": scope, "provider": provider, "model": model,
            "endpoint": endpoint, "request_hash": key, "reasoning_effort": reasoning_effort,
            "max_output_tokens": max_output_tokens}

    def make_result(raw: dict[str, Any], usage: Usage | None, cost: float, cache_hit: bool,
                    attempts: int) -> MetaResult:
        read = _read_result(endpoint, raw)
        parsed, parse_error = _parse_output(read["text"], output_model)
        # A declined request another Claude model answered names that model, as records must.
        return MetaResult(provider=provider, model=_fallback_model(provider, raw) or model, endpoint=endpoint,
                          usage=usage, cost_usd=cost,
                          response_id=raw.get("id"), cache_hit=cache_hit, attempts=attempts,
                          request_hash=key, raw=raw, parsed=parsed, parse_error=parse_error, **read)

    if provider == "openrouter" and ledger is not None and ledger.budget != "openrouter":
        # A caller's Meta budget: the call now spends OpenRouter's balance, so its budget in the same file counts it.
        ledger = Ledger(ledger.path, budget="openrouter", caps=OPENROUTER_CAPS)
    callers_ledger = ledger
    if provider == "bedrock" and ledger is not None and ledger.budget != "bedrock":
        # A caller's Claude budget: the call now spends AWS's bill, so its budget in the same file counts it.
        ledger = Ledger(ledger.path, budget="bedrock", caps=bedrock_caps(), clock=ledger.clock)
    ledger = ledger or {"baseten": baseten_ledger, "modal": modal_llm_ledger, "openrouter": openrouter_ledger,
                        "bedrock": bedrock_ledger}.get(provider, default_ledger)()
    use_cache = _cache_enabled(cache, model)
    if use_cache:
        raw = _cache_read(runs, key)
        result = make_result(raw, Usage.from_raw(raw), 0.0, cache_hit=True, attempts=0) if raw else None
        if result is not None and _cacheable(result):
            tokens = asdict(result.usage) if result.usage else None
            ledger.record_cache_hit(run_id=run_id, stage=stage, scope=scope, provider=provider, model=model,
                                    tokens=tokens, response_id=result.response_id)
            _append_trace(runs, {**base, "attempt": 0, "cache_hit": True, "status": "ok",
                                 "response_id": result.response_id, "usage": tokens,
                                 "latency_s": 0.0, "finish": result.status,
                                 "reasoning_summary": _clip(result.reasoning_summary)}, [])
            return result


    def on_the_direct_api(reason: str) -> MetaResult:
        """The same call on Anthropic's API, after Bedrock gave way; said in the trace and once on stderr."""
        _append_trace(runs, {**base, "status": "fallback",
                             "error": {"type": "bedrock_fallback", "message": reason}}, [])
        _note_once(f"bedrock:{reason.split(':')[0]}", f"Amazon Bedrock {reason}; such calls go to Anthropic's API "
                                                      "and are recorded under it")
        direct = callers_ledger
        if direct is not None and direct.budget == "bedrock":
            direct = Ledger(direct.path, caps=pipeline_caps(), clock=direct.clock)
        return call_meta(endpoint, body, stage=stage, public_data_only=public_data_only,
                         max_output_tokens=max_output_tokens, model=model, provider=DEFAULT_PROVIDER,
                         reasoning_effort=reasoning_effort, scope=scope, scope_cap_usd=scope_cap_usd, run_id=run_id,
                         output_model=output_model, cache=cache, ledger=direct, runs_dir=runs_dir,
                         video_seconds=video_seconds, conversation=conversation)

    client = client or _default_client(provider)
    secrets = [client.api_key] if isinstance(getattr(client, "api_key", None), str) else []
    try:
        raw, usage, cost, attempts = _send_with_retries(
            client, endpoint, request, price, max_output_tokens, ledger, runs, base, secrets,
            scope_cap_usd=scope_cap_usd, video_seconds=video_seconds, conversation=conversation)
    except Exception as err:
        gave_way = _bedrock_gave_way(err) if provider == "bedrock" else None
        if gave_way is None:
            raise
        return on_the_direct_api(gave_way)
    result = make_result(raw, usage, cost, cache_hit=False, attempts=attempts)
    if provider == "bedrock" and "stop_details" in raw:
        # Declined by a safety classifier. Bedrock has no fallback model to hand it to (the direct API's
        # `fallbacks`), so the direct API gets the request; what Bedrock billed for the decline is counted.
        again = on_the_direct_api("declined: its Claude declined a request and Bedrock has no fallback model")
        return replace(again, cost_usd=again.cost_usd + cost, attempts=again.attempts + attempts)
    if use_cache and _cacheable(result):
        _cache_write(runs, key, provider, endpoint, raw)
    return result


def _clip(text: str | None) -> str | None:
    return text[:TRACE_TEXT_LIMIT] if text else None


def _bedrock_gave_way(err: BaseException) -> str | None:
    """Why a failed Bedrock call goes to the direct API, or None when it must fail as it is. Throttling and
    outages do (after BEDROCK_TRIES), and so does the bedrock budget's own daily or total cap. A refused
    request does not: a 400, a 403 (the key or the model access is wrong) or a 404 would hide a mistake, and
    a per-scope cap is the caller's limit on any provider."""
    if isinstance(err, BudgetExceeded):
        return None if err.cap.startswith("scope") else f"cap: its {err.cap} cap is reached"
    if isinstance(err, _STATUS_ERRORS):
        if err.status_code == 429:
            return "throttled: it kept answering 429"
        if err.status_code >= 500 or err.status_code == 408:
            return f"down: it kept answering {err.status_code}"
        return None
    if isinstance(err, _CONNECTION_ERRORS):  # timeouts are connection errors too
        return f"down: {type(err).__name__}"
    return None


def _fallback_model(provider: str, raw: dict[str, Any]) -> str | None:
    """The priced model id of the fallback model that answered a declined request, else None. The API may
    name a dated snapshot, so the longest priced id it starts with is taken."""
    served = raw.get("fallback_model")
    if not isinstance(served, str):
        return None
    known = [m for p, m in PRICES if p == provider and served.startswith(m)]
    return max(known, key=len) if known else None


def _trace_error(runs: Path, trace: dict[str, Any], secrets: list[str], err: BaseException,
                 http_status: int | None, cost: float, started: float) -> None:
    """Trace a failed attempt, and scrub keys from the exception before it reaches the caller."""
    _scrub_error(err, secrets)
    _append_trace(runs, {**trace, "status": "error", "http_status": http_status,
                         "error": _error_info(err), "cost_usd": round(cost, 6),
                         "latency_s": round(time.monotonic() - started, 3)}, secrets)


def _send_with_retries(
    client: Any, endpoint: Endpoint, request: dict[str, Any], price: Price, max_output_tokens: int,
    ledger: Ledger, runs: Path, base: dict[str, Any], secrets: list[str], *, scope_cap_usd: float | None,
    video_seconds: float | None = None, conversation: bool = False,
) -> tuple[dict[str, Any], Usage | None, float, int]:
    """Send one request with visible retries; every attempt is reserved, settled and traced.

    An attempt that may have been billed (5xx, timeout, connection lost after sending)
    keeps its worst-case estimate as status `unknown`; only a 4xx or a request that
    never left is released.
    """
    provider = base["provider"]
    retry = _Retry(retry_not_found=provider == "meta", tries=BEDROCK_TRIES if provider == "bedrock" else 0)
    attempt = 0
    while True:
        attempt += 1
        estimate = estimate_cost(price, request, max_output_tokens, _previous_context(request, ledger), video_seconds)
        trace = {**base, "attempt": attempt, "stream": retry.stream, "reserved_usd": round(estimate, 6)}
        try:
            row = ledger.reserve(estimate, run_id=base["run_id"], stage=base["stage"], scope=base["scope"],
                                 provider=provider, model=base["model"], attempt=attempt,
                                 scope_cap_usd=scope_cap_usd)
        except BudgetExceeded as err:
            _append_trace(runs, {**trace, "status": "budget_exceeded", "error": _error_info(err)}, secrets)
            raise
        started = time.monotonic()
        try:
            raw = _send(client, endpoint, request, retry.stream, conversation)
        except _STATUS_ERRORS as err:
            # A 4xx (429 included) is refused before generation. A 5xx may come after the
            # upstream generated (504 gateway timeout, 503 persistence error): keep the estimate.
            held = estimate if err.status_code >= 500 else 0.0
            _hold_or_release(ledger, row, held)
            _trace_error(runs, trace, secrets, err, err.status_code, held, started)
            if retry.after_http_error(err):
                continue
            raise
        except _TIMEOUT_ERRORS as err:
            held = 0.0 if _never_sent(err) else estimate  # the server may still finish and bill it
            _hold_or_release(ledger, row, held)
            _trace_error(runs, trace, secrets, err, None, held, started)
            if retry.switch_to_stream():
                continue
            raise
        except _CONNECTION_ERRORS as err:
            held = 0.0 if _never_sent(err) else estimate  # e.g. "Server disconnected" after sending
            _hold_or_release(ledger, row, held)
            _trace_error(runs, trace, secrets, err, None, held, started)
            if retry.after_server_error():
                continue
            raise
        except BaseException as err:
            ledger.settle(row, estimate, status="unknown")  # e.g. a broken stream: keep the worst case
            _trace_error(runs, trace, secrets, err, None, estimate, started)
            raise
        latency = round(time.monotonic() - started, 3)
        usage = Usage.from_raw(raw)
        fallback = _fallback_model(provider, raw)  # it answered, so its rates apply (an approximation: the
        if fallback:                               # declined attempt's own tokens are priced with it)
            price = PRICES[(provider, fallback)]
            trace["fallback_model"] = fallback
        cost = cost_usd(price, usage) if usage else estimate
        ledger.settle(row, cost, tokens=asdict(usage) if usage else None, response_id=raw.get("id"),
                      status="settled" if usage else "no_usage")
        read = _read_result(endpoint, raw)
        _append_trace(runs, {**trace, "status": "ok", "http_status": 200,
                             "response_id": raw.get("id"), "usage": asdict(usage) if usage else None,
                             "cost_usd": round(cost, 8), "latency_s": latency, "finish": read["status"],
                             "reasoning_summary": _clip(read["reasoning_summary"])}, secrets)
        return raw, usage, cost, attempt


def _hold_or_release(ledger: Ledger, row: int, held: float) -> None:
    """Keep `held` (a worst case that may have been billed) as `unknown`, or release at 0."""
    if held:
        ledger.settle(row, held, status="unknown")
    else:
        ledger.release(row)


def ping(provider: str = DEFAULT_PROVIDER, model: str | None = None, **kwargs: Any) -> MetaResult:
    """Smallest possible paid call (a few dozen tokens, never cached), for `pickfit ping`."""
    return call_meta("chat", {"messages": [{"role": "user", "content": "ping"}]}, stage="ping",
                     provider=provider, model=model, public_data_only=True,
                     max_output_tokens=PING_MAX_OUTPUT_TOKENS, reasoning_effort="minimal",
                     cache=False, **kwargs)
