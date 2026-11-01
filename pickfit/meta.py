"""call_meta: the only way pickfit calls a model.

Every call goes through the same steps:

1. Route the model ("dev" -> contributor, "prod" -> standard) and refuse models
   without a known price, a contributor model for non-public data, and body
   keys that would get around these checks or the cost bound.
2. Serve from the response cache when possible (free, still traced). The cache
   is on by default for dev (contributor) models only, and keeps only complete,
   valid answers.
3. Reserve a worst-case cost in the shared ledger; BudgetExceeded stops the
   call before anything is sent.
4. Send with the SDK's own retries off, so every attempt is visible: 429 backs
   off (honoring Retry-After), 500/502/503 get up to 3 tries, 504 is retried
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
import threading
import time
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal

import openai
from pydantic import BaseModel, ValidationError

from pickfit.env import REPO_ROOT, get_env, require_env
from pickfit.ledger import BudgetExceeded, Ledger, baseten_ledger, default_ledger, taipei_date, taipei_now

Endpoint = Literal["chat", "responses"]


@dataclass(frozen=True)
class Provider:
    base_url: str
    key_env: str


PROVIDERS: dict[str, Provider] = {
    "meta": Provider("https://api.meta.ai/v1", "MODEL_API_KEY"),
    "baseten": Provider("https://inference.baseten.co/v1", "BASETEN_API_KEY"),
}

# PICKFIT_MODE (default dev) picks the model when a Meta caller passes none.
MODE_ALIASES = {"dev": "muse-spark-1.3-contributor", "prod": "muse-spark-1.3"}
# "open" is Muse Spark Open on Baseten (the hackathon's open-weight model). The model id says which
# provider serves it, so call_meta routes and bills it to Baseten without the caller passing provider.
OPEN_MODEL = "meta-models/muse-spark-open-1026"
OPEN_ALIASES = {"open": OPEN_MODEL}
BASETEN_PREFIX = "meta-models/"


@dataclass(frozen=True)
class Price:
    """USD per 1M tokens. `cached=None` means unknown, so cached input is charged at `input`."""

    input: float
    output: float
    cached: float | None = None


# Measured or confirmed 2026-10-28. A model missing here is refused, never billed as $0.
PRICES: dict[tuple[str, str], Price] = {
    ("meta", "muse-spark-1.3"): Price(input=1.25, output=4.25, cached=0.15),
    ("meta", "muse-spark-1.3-contributor"): Price(input=0.10, output=0.20),
    ("meta", "muse-wonder-1.0"): Price(input=4.00, output=20.00),
    ("baseten", "meta-models/muse-spark-open"): Price(input=1.25, output=4.25, cached=0.15),
    ("baseten", "meta-models/muse-spark-open-1026"): Price(input=1.25, output=4.25, cached=0.15),
}
WEB_SEARCH_USD = 2.50 / 1000

EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")
MAX_EFFORT_MODELS = {"muse-spark-1.3", "muse-wonder-1.0"}

# Worst-case estimate knobs (used only to reserve budget before sending).
BYTES_PER_TOKEN = 3  # UTF-8 JSON bytes per token; low on purpose so estimates run high
IMAGE_TOKENS = 3_000  # a ~1280px image is about 1,300-1,500 tokens
UNKNOWN_CONTEXT_TOKENS = 32_000  # previous_response_id with no tokens in the ledger
WEB_SEARCHES_PER_CALL = 3  # default max_tool_calls when web_search is on (meta-usage-design)
TOKENS_PER_WEB_SEARCH = 5_000

# Retry policy (the SDK's own retries are disabled).
RATE_LIMIT_TRIES = 6
SERVER_ERROR_TRIES = 3
RETRY_STATUSES = {500, 502, 503}
# Meta's API has answered 404 "model not found" for a model it serves, on and off for minutes (10/29,
# 11/1 01:46-01:49). A 404 is refused before generation, so it is released and tried again, backing off
# for about two minutes in all; a model that is really gone fails after that.
NOT_FOUND_TRIES = 8
BACKOFF_BASE_S = 2.0
BACKOFF_MAX_S = 60.0
CLIENT_TIMEOUT_S = 600.0

PING_MAX_OUTPUT_TOKENS = 256  # reasoning shares this limit; 64 was cut off at minimal effort
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
_KEY_PATTERN = re.compile(r"LLM_\d+_[A-Za-z0-9_\-]+")

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

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Usage | None:
        """Read Chat (`prompt_tokens`) or Responses (`input_tokens`) usage; None if absent."""
        u = raw.get("usage")
        if not isinstance(u, dict):
            return None
        searches = sum(1 for item in raw.get("output") or [] if item.get("type") == "web_search_call")
        if "prompt_tokens" in u:
            return cls(
                input_tokens=u.get("prompt_tokens") or 0,
                cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0,
                output_tokens=u.get("completion_tokens") or 0,
                reasoning_tokens=(u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0,
                web_searches=searches,
            )
        return cls(
            input_tokens=u.get("input_tokens") or 0,
            cached_tokens=(u.get("input_tokens_details") or {}).get("cached_tokens") or 0,
            output_tokens=u.get("output_tokens") or 0,
            reasoning_tokens=(u.get("output_tokens_details") or {}).get("reasoning_tokens") or 0,
            web_searches=searches,
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


def resolve_model(model: str | None, provider: str = "meta") -> str:
    """Map "dev"/"prod" (or PICKFIT_MODE when None) and "open" to a model id."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; expected one of {sorted(PROVIDERS)}")
    if model in OPEN_ALIASES:
        return OPEN_ALIASES[model]
    if provider == "baseten":
        if model is None or model in MODE_ALIASES:
            raise ModelRefused("baseten calls need an explicit model id, e.g. meta-models/muse-spark-open")
        return model
    if model is None:
        model = get_env("PICKFIT_MODE") or "dev"
        if model not in MODE_ALIASES:
            raise ValueError(f"PICKFIT_MODE must be one of {sorted(MODE_ALIASES)}, got {model!r}")
    return MODE_ALIASES.get(model, model)


def provider_for(model: str) -> str:
    """The provider that serves a model id: Baseten for its meta-models/ slugs, else Meta."""
    return "baseten" if model.startswith(BASETEN_PREFIX) else "meta"


def is_open_model(model: str | None) -> bool:
    """True when `model` (an alias or an id) is served on Baseten rather than by Meta's API."""
    return model is not None and provider_for(OPEN_ALIASES.get(model, model)) == "baseten"


def price_for(provider: str, model: str) -> Price:
    try:
        return PRICES[(provider, model)]
    except KeyError:
        raise ModelRefused(f"no price for {provider}/{model}; add it to PRICES before calling it") from None


def cost_usd(price: Price, usage: Usage) -> float:
    cached = min(usage.cached_tokens, usage.input_tokens)
    cached_rate = price.input if price.cached is None else price.cached
    token_usd = ((usage.input_tokens - cached) * price.input + cached * cached_rate
                 + usage.output_tokens * price.output) / 1_000_000
    return token_usd + usage.web_searches * WEB_SEARCH_USD


def _has_web_search(body: dict[str, Any]) -> bool:
    return any(isinstance(t, dict) and str(t.get("type", "")).startswith("web_search")
               for t in body.get("tools") or [])


def estimate_input_tokens(body: dict[str, Any]) -> int:
    """Rough upper estimate from request size; each image counts as IMAGE_TOKENS.

    An image is an `image_url` / `input_image` part (inline data, https URL or file_id)
    or any other inline `data:image/` string.
    """
    images = 0

    def strip_images(value: Any) -> Any:
        nonlocal images
        if isinstance(value, str) and value.startswith("data:image/"):
            images += 1
            return ""
        if isinstance(value, dict):
            if value.get("type") in ("image_url", "input_image"):
                images += 1
                return {}
            return {k: strip_images(v) for k, v in value.items()}
        if isinstance(value, list):
            return [strip_images(v) for v in value]
        return value

    size = len(json.dumps(strip_images(body), ensure_ascii=False).encode("utf-8"))
    return size // BYTES_PER_TOKEN + 1 + images * IMAGE_TOKENS


def estimate_cost(price: Price, request: dict[str, Any], max_output_tokens: int,
                  context_tokens: int = 0) -> float:
    """Worst case for one attempt: estimated input + context + every allowed output token.

    With web_search on, every allowed built-in tool call (`max_tool_calls`) is a search.
    """
    searches = request.get("max_tool_calls", WEB_SEARCHES_PER_CALL) if _has_web_search(request) else 0
    tokens_in = estimate_input_tokens(request) + context_tokens + searches * TOKENS_PER_WEB_SEARCH
    token_usd = (tokens_in * price.input + max_output_tokens * price.output) / 1_000_000
    return token_usd + searches * WEB_SEARCH_USD


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
    if effort == "max" and model not in MAX_EFFORT_MODELS:
        raise ValueError(f"{model} does not support reasoning_effort='max'")
    if not isinstance(max_output_tokens, int) or max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be a positive int")
    if provider == "baseten" and body.get("previous_response_id"):
        raise ValueError("Baseten /responses is stateless; previous_response_id is not supported")


_clients: dict[str, openai.OpenAI] = {}
_clients_lock = threading.Lock()


def make_client(provider: str = "meta", *, http_client: Any = None) -> openai.OpenAI:
    """OpenAI SDK client for a provider, with SDK retries off (call_meta retries itself)."""
    info = PROVIDERS[provider]
    return openai.OpenAI(api_key=require_env(info.key_env), base_url=info.base_url,
                         max_retries=0, timeout=CLIENT_TIMEOUT_S, http_client=http_client)


def _default_client(provider: str) -> openai.OpenAI:
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


def _send(client: Any, endpoint: Endpoint, request: dict[str, Any], stream: bool) -> dict[str, Any]:
    create = client.chat.completions.create if endpoint == "chat" else client.responses.create
    kwargs = _sdk_kwargs(create, request)
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
    """The `cache` argument, else PICKFIT_CACHE, else on only for dev (contributor) models.

    Prod runs and re-verification must ask the model again, not replay an old answer.
    """
    if cache is not None:
        return cache
    setting = get_env("PICKFIT_CACHE")
    if setting is not None:
        return setting.strip().lower() not in {"0", "false", "no", "off"}
    return model.endswith("-contributor")


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


def _retry_after_s(err: openai.APIStatusError) -> float | None:
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

    def after_http_error(self, err: openai.APIStatusError) -> bool:
        """Whether to try again after an HTTP error; sleeps first when backing off."""
        if err.status_code == 429:
            self.rate_limited += 1
            if self.rate_limited >= RATE_LIMIT_TRIES:
                return False
            wait = _retry_after_s(err)
            sleep(wait if wait is not None else _backoff_s(self.rate_limited))
            return True
        if err.status_code in RETRY_STATUSES:
            return self.after_server_error()
        if err.status_code == 404:
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
        if self.server_errors >= SERVER_ERROR_TRIES:
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
    if isinstance(err, openai.APIError):
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
) -> MetaResult:
    """Call a Meta model through Chat Completions (`chat`) or the Responses API (`responses`).

    `body` is the request without model, output limit or reasoning effort, e.g.
    {"messages": [...]} or {"input": ..., "tools": [...], "previous_response_id": ...}.
    With a web_search tool, `max_tool_calls` (default WEB_SEARCHES_PER_CALL) caps searches.
    `public_data_only` must be True for contributor models. `scope_cap_usd` caps what
    `scope` may spend within `run_id` (e.g. "verify:<slug>" at 0.50 per verification run).
    `output_model` validates the text output as JSON into that pydantic model.
    `cache` defaults to PICKFIT_CACHE, else on for dev (contributor) models only.
    `provider` defaults to the one serving the model (Baseten for "open" and meta-models/ ids), and
    `ledger` to that provider's budget in the shared ledger.
    """
    model = resolve_model(model, provider or "meta")
    provider = provider or provider_for(model)
    _check_policy(provider, model, public_data_only, reasoning_effort, body, max_output_tokens)
    price = price_for(provider, model)
    request = build_request(endpoint, model, body, max_output_tokens, reasoning_effort)
    key = request_hash(provider, endpoint, request)
    runs = _runs_dir(runs_dir)
    base = {"run_id": run_id, "stage": stage, "scope": scope, "provider": provider, "model": model,
            "endpoint": endpoint, "request_hash": key, "reasoning_effort": reasoning_effort,
            "max_output_tokens": max_output_tokens}

    def make_result(raw: dict[str, Any], usage: Usage | None, cost: float, cache_hit: bool,
                    attempts: int) -> MetaResult:
        read = _read_result(endpoint, raw)
        parsed, parse_error = _parse_output(read["text"], output_model)
        return MetaResult(provider=provider, model=model, endpoint=endpoint, usage=usage, cost_usd=cost,
                          response_id=raw.get("id"), cache_hit=cache_hit, attempts=attempts,
                          request_hash=key, raw=raw, parsed=parsed, parse_error=parse_error, **read)

    ledger = ledger or (baseten_ledger() if provider == "baseten" else default_ledger())
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


    client = client or _default_client(provider)
    secrets = [client.api_key] if isinstance(getattr(client, "api_key", None), str) else []
    raw, usage, cost, attempts = _send_with_retries(
        client, endpoint, request, price, max_output_tokens, ledger, runs, base, secrets,
        scope_cap_usd=scope_cap_usd)
    result = make_result(raw, usage, cost, cache_hit=False, attempts=attempts)
    if use_cache and _cacheable(result):
        _cache_write(runs, key, provider, endpoint, raw)
    return result


def _clip(text: str | None) -> str | None:
    return text[:TRACE_TEXT_LIMIT] if text else None


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
) -> tuple[dict[str, Any], Usage | None, float, int]:
    """Send one request with visible retries; every attempt is reserved, settled and traced.

    An attempt that may have been billed (5xx, timeout, connection lost after sending)
    keeps its worst-case estimate as status `unknown`; only a 4xx or a request that
    never left is released.
    """
    retry = _Retry()
    attempt = 0
    while True:
        attempt += 1
        estimate = estimate_cost(price, request, max_output_tokens, _previous_context(request, ledger))
        trace = {**base, "attempt": attempt, "stream": retry.stream, "reserved_usd": round(estimate, 6)}
        try:
            row = ledger.reserve(estimate, run_id=base["run_id"], stage=base["stage"], scope=base["scope"],
                                 provider=base["provider"], model=base["model"], attempt=attempt,
                                 scope_cap_usd=scope_cap_usd)
        except BudgetExceeded as err:
            _append_trace(runs, {**trace, "status": "budget_exceeded", "error": _error_info(err)}, secrets)
            raise
        started = time.monotonic()
        try:
            raw = _send(client, endpoint, request, retry.stream)
        except openai.APIStatusError as err:
            # A 4xx (429 included) is refused before generation. A 5xx may come after the
            # upstream generated (504 gateway timeout, 503 persistence error): keep the estimate.
            held = estimate if err.status_code >= 500 else 0.0
            _hold_or_release(ledger, row, held)
            _trace_error(runs, trace, secrets, err, err.status_code, held, started)
            if retry.after_http_error(err):
                continue
            raise
        except openai.APITimeoutError as err:
            held = 0.0 if _never_sent(err) else estimate  # the server may still finish and bill it
            _hold_or_release(ledger, row, held)
            _trace_error(runs, trace, secrets, err, None, held, started)
            if retry.switch_to_stream():
                continue
            raise
        except openai.APIConnectionError as err:
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


def ping(provider: str = "meta", model: str | None = None, **kwargs: Any) -> MetaResult:
    """Smallest possible paid call (a few dozen tokens, never cached), for `pickfit ping`."""
    return call_meta("chat", {"messages": [{"role": "user", "content": "ping"}]}, stage="ping",
                     provider=provider, model=model, public_data_only=True,
                     max_output_tokens=PING_MAX_OUTPUT_TOKENS, reasoning_effort="minimal",
                     cache=False, **kwargs)
