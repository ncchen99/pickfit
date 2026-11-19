"""call_meta on Claude: Chat and Responses requests go out as Messages API calls and come back in their own
shape. The Anthropic SDK runs for real over a mocked HTTP transport, so no request ever leaves the process."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

import pickfit.env
from pickfit import anthropic_messages, meta
from pickfit.anthropic_messages import UNION_LIMIT, Plan, claude_schema, from_message, to_request, union_count
from pickfit.ledger import BudgetExceeded, Caps, Ledger
from pickfit.meta import (
    BULK_MODEL,
    PRICES,
    PROD_MODEL,
    Usage,
    call_meta,
    cost_usd,
    make_client,
    ping,
    provider_for,
    resolve_model,
)

FAKE_KEY = "sk-ant-test-0123456789abcdef-SECRET"
PNG = "data:image/png;base64,iVBORw0KGgo="
THINKING = {"type": "thinking", "thinking": "Read the README.", "signature": "sig-1"}
TOOL_USE = {"type": "tool_use", "id": "toolu_1", "name": "run_command", "input": {"cmd": "tinyq --version"}}
USAGE = {"input_tokens": 100, "cache_creation_input_tokens": 400, "cache_read_input_tokens": 1500,
         "output_tokens": 300}


def message(*content: dict[str, Any], stop: str = "end_turn", model: str = PROD_MODEL, usage: dict | None = None,
            **more: Any) -> dict[str, Any]:
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": list(content),
            "stop_reason": stop, "stop_sequence": None, "usage": usage or USAGE, **more}


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


class FakeAnthropic:
    """Records every request and answers from a list of handlers, one per request."""

    def __init__(self, *replies: Callable[[dict[str, Any]], httpx2.Response]) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content or b"{}")
        self.requests.append({"path": request.url.path, **body})
        self.headers.append({name.lower(): value for name, value in request.headers.items()})
        if not self.replies:
            raise AssertionError("unexpected extra request")
        return self.replies.pop(0)(body)

    def client(self, **options: Any) -> anthropic_messages.Client:
        sdk = anthropic.Anthropic(api_key=FAKE_KEY, base_url="https://api.anthropic.com", max_retries=0,
                                  http_client=httpx2.Client(transport=httpx2.MockTransport(self)))
        return anthropic_messages.Client(sdk, **options)


def ok(payload: dict[str, Any]) -> Callable[[dict[str, Any]], httpx2.Response]:
    return lambda body: httpx2.Response(200, json=payload)


def status(code: int, kind: str = "api_error", headers: dict[str, str] | None = None):
    error = {"type": "error", "error": {"type": kind, "message": f"status {code} for key {FAKE_KEY}"}}
    return lambda body: httpx2.Response(code, json=error, headers=headers)


def sse(*events: dict[str, Any]):
    lines = [f"event: {e['type']}\ndata: {json.dumps(e)}\n" for e in events]
    return lambda body: httpx2.Response(200, headers={"content-type": "text/event-stream"},
                                        content=("\n".join(lines) + "\n").encode())


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """No real .env, ledger, runs dir or sleeping; returns the recorded backoff sleeps."""
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "PICKFIT_META_VIA",
                 "PICKFIT_ANTHROPIC_FALLBACKS", "PICKFIT_PIPELINE_TOTAL_CAP_USD", "PICKFIT_PIPELINE_DAILY_CAP_USD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "default-ledger.sqlite"))
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(anthropic_messages, "_refused_schemas", set())
    sleeps: list[float] = []
    monkeypatch.setattr(meta, "sleep", sleeps.append)
    return sleeps


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite")


def traces(tmp_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for path in sorted((tmp_path / "runs" / "traces").glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()]


def call(server: FakeAnthropic, ledger: Ledger, endpoint: str = "responses", body: dict | None = None, **kwargs):
    kwargs.setdefault("public_data_only", True)
    kwargs.setdefault("max_output_tokens", 1000)
    kwargs.setdefault("model", "prod")
    return call_meta(endpoint, body or {"instructions": "Be brief.", "input": "ping"}, stage="test",
                     client=server.client(), ledger=ledger, **kwargs)


# ---------------------------------------------------------------- routing and prices


def test_the_tiers_are_claude_models_and_the_hackathon_ids_keep_their_providers(monkeypatch: pytest.MonkeyPatch):
    assert (resolve_model("prod"), resolve_model("dev"), resolve_model("open")) == (PROD_MODEL, BULK_MODEL, BULK_MODEL)
    assert (PROD_MODEL, BULK_MODEL) == ("claude-opus-5-5", "claude-haiku-5-5")
    assert resolve_model(None) == PROD_MODEL  # PICKFIT_MODE unset: prod
    monkeypatch.setenv("PICKFIT_MODE", "dev")
    assert resolve_model(None) == BULK_MODEL
    assert provider_for(PROD_MODEL) == provider_for("claude-sonnet-5-5") == "anthropic"
    assert provider_for("muse-spark-1.3") == "meta" and resolve_model("prod", "meta") == "muse-spark-1.3"
    assert provider_for(resolve_model("open-modal")) == "modal"  # the endpoint that takes video


def test_no_model_named_means_opus_and_haiku_only_by_name(monkeypatch: pytest.MonkeyPatch,
                                                          capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(meta, "_dev_noted", set())
    assert resolve_model(None) == PROD_MODEL  # no environment variable: Opus
    assert capsys.readouterr().err == ""
    monkeypatch.setenv("PICKFIT_MODE", "dev")
    assert resolve_model(None) == BULK_MODEL  # PICKFIT_MODE=dev: Haiku, and stderr says so once
    assert resolve_model(None) == BULK_MODEL
    err = capsys.readouterr().err
    assert err.count("model tier dev") == 1 and "PICKFIT_MODE" in err
    assert resolve_model("prod") == PROD_MODEL  # a model the caller names wins over PICKFIT_MODE
    monkeypatch.setenv("PICKFIT_MODE", "prod")
    assert resolve_model("dev") == BULK_MODEL and "the caller" in capsys.readouterr().err
    assert resolve_model("claude-sonnet-5-5") == "claude-sonnet-5-5"
    monkeypatch.setenv("PICKFIT_MODE", "cheap")
    with pytest.raises(ValueError, match="PICKFIT_MODE"):
        resolve_model(None)


def test_a_call_with_no_model_is_sent_to_opus_and_recorded_so(ledger: Ledger, tmp_path: Path):
    server = FakeAnthropic(ok(message(text("pong"))))
    result = call(server, ledger, model=None)
    assert server.requests[0]["model"] == PROD_MODEL and result.model == PROD_MODEL
    assert {r["model"] for r in traces(tmp_path)} == {PROD_MODEL}


def test_claude_prices_count_cache_reads_cache_writes_and_long_prompts():
    opus = PRICES[("anthropic", PROD_MODEL)]
    assert (opus.input, opus.output, opus.cached, opus.cache_write) == (4.00, 20.00, 0.20, 5.00)
    usage = Usage(input_tokens=2000, cached_tokens=1500, cache_write_tokens=400, output_tokens=300)
    assert cost_usd(opus, usage) == pytest.approx((100 * 4.00 + 1500 * 0.20 + 400 * 5.00 + 300 * 20.00) / 1e6)
    haiku = PRICES[("anthropic", BULK_MODEL)]
    short = Usage(input_tokens=100_000, output_tokens=1000)
    assert cost_usd(haiku, short) == pytest.approx((100_000 * 0.10 + 1000 * 0.50) / 1e6)
    long = Usage(input_tokens=100_001, output_tokens=1000)  # past 100K tokens the whole request is 5x
    assert cost_usd(haiku, long) == pytest.approx(5 * (100_001 * 0.10 + 1000 * 0.50) / 1e6)
    # The worst case reserved before a call: every input token written to the cache, every output token used.
    request = {"model": PROD_MODEL, "input": "x" * 2997, "max_output_tokens": 1000}
    tokens_in = meta.estimate_input_tokens(request)
    assert meta.estimate_cost(opus, request, 1000) == pytest.approx((tokens_in * 5.00 + 1000 * 20.00) / 1e6)


def test_make_client_reads_the_key_and_never_a_base_url_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.invalid")
    client = make_client()
    assert isinstance(client, anthropic_messages.Client) and client.api_key == FAKE_KEY
    assert str(client.anthropic.base_url).rstrip("/") == "https://api.anthropic.com"
    assert client.anthropic.max_retries == 0 and client.fallbacks is True
    monkeypatch.setenv("PICKFIT_ANTHROPIC_FALLBACKS", "0")
    assert make_client().fallbacks is False


# ---------------------------------------------------------------- the request


def test_a_chat_request_becomes_a_messages_request():
    request = {
        "model": PROD_MODEL, "max_completion_tokens": 4000, "reasoning_effort": "minimal",
        "messages": [
            {"role": "system", "content": "You screen repositories."},
            {"role": "user", "content": [{"type": "text", "text": "What is on this screen?"},
                                         {"type": "image_url", "image_url": {"url": PNG}},
                                         {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}}]},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "click", "arguments": '{"x": 3}'}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": "clicked"},
            {"role": "user", "content": "Go on."},
        ],
        "tools": [{"type": "function", "function": {"name": "click", "description": "Click a point.", "strict": True,
                                                    "parameters": {"type": "object", "properties": {}}}}],
        "prompt_cache_key": "k", "store": False,
    }
    kwargs, plan = to_request("chat", request)
    assert plan == Plan(endpoint="chat", forced_tool=None)
    assert kwargs["model"] == PROD_MODEL and kwargs["max_tokens"] == 4000
    assert kwargs["output_config"] == {"effort": "low"}  # Claude has no "minimal"
    assert "thinking" not in kwargs and "temperature" not in kwargs and "tool_choice" not in kwargs
    assert kwargs["system"] == [{"type": "text", "text": "You screen repositories.",
                                 "cache_control": {"type": "ephemeral"}}]
    assert kwargs["tools"] == [{"name": "click", "description": "Click a point.", "strict": True,
                                "input_schema": {"type": "object", "properties": {}}}]
    user, assistant, results = kwargs["messages"]
    assert user == {"role": "user", "content": [
        {"type": "text", "text": "What is on this screen?"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="}},
        {"type": "image", "source": {"type": "url", "url": "https://example.com/a.png"}}]}
    assert assistant == {"role": "assistant", "content": [
        {"type": "tool_use", "id": "call_1", "name": "click", "input": {"x": 3}}]}
    # The tool's output and the user's next words are one user turn, the tool result first.
    assert results == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "call_1", "content": [{"type": "text", "text": "clicked"}]},
        {"type": "text", "text": "Go on."}]}
    assert kwargs["cache_control"] == {"type": "ephemeral"}  # a conversation: its history is cached
    assert kwargs["betas"] == ["server-side-fallback-2026-07-01"] and kwargs["fallbacks"] == "default"


def test_a_single_call_caches_only_its_instructions_and_haiku_gets_no_fallback():
    request = {"model": BULK_MODEL, "instructions": "Grade the README.", "input": "<source>README</source>",
               "reasoning": {"effort": "medium"}, "max_output_tokens": 8000, "store": False}
    kwargs, _ = to_request("responses", request)
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in kwargs  # the sources differ on every call: writing them to a cache is a surcharge
    assert kwargs["messages"] == [{"role": "user", "content": [{"type": "text", "text": "<source>README</source>"}]}]
    assert kwargs["output_config"] == {"effort": "medium"}
    assert "betas" not in kwargs and "fallbacks" not in kwargs
    assert "betas" not in to_request("responses", {**request, "model": PROD_MODEL}, fallbacks=False)[0]


AGENT_TOOL = {"type": "function", "name": "run_command", "description": "Run a command.",
              "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}}}


def test_a_conversation_caches_its_first_turn_and_a_single_call_does_not(ledger: Ledger):
    first_turn = {"model": PROD_MODEL, "instructions": "You verify tools.", "tools": [AGENT_TOOL],
                  "input": [{"type": "message", "role": "user", "content": "Task: tinyq. <source>README</source>"}],
                  "reasoning": {"effort": "medium"}, "max_output_tokens": 8000, "store": False}
    kwargs, _ = to_request("responses", first_turn, conversation=True)
    assert kwargs["cache_control"] == {"type": "ephemeral"}  # the task is read from the cache on turn 2
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}  # the instructions keep their own
    assert "cache_control" not in to_request("responses", first_turn)[0]  # a judge, a translation: one call

    server = FakeAnthropic(ok(message(TOOL_USE)), ok(message(text("Graded."))))
    call(server, ledger, body={k: first_turn[k] for k in ("instructions", "tools", "input")}, conversation=True)
    call(server, ledger, body={"instructions": "Grade the README.", "input": "<source>README</source>"})
    assert server.requests[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in server.requests[1]


def test_a_json_schema_and_a_reasoning_summary_are_asked_for_the_claude_way():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"],
              "additionalProperties": False}
    responses = {"model": PROD_MODEL, "input": "x", "max_output_tokens": 1000,
                 "reasoning": {"effort": "low", "summary": "auto"},
                 "text": {"format": {"type": "json_schema", "name": "n", "schema": schema, "strict": True}}}
    kwargs, _ = to_request("responses", responses)
    assert kwargs["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": schema}}
    assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
    chat = {"model": PROD_MODEL, "messages": [{"role": "user", "content": "x"}], "max_completion_tokens": 1000,
            "reasoning_effort": "high",
            "response_format": {"type": "json_schema", "json_schema": {"name": "n", "schema": schema, "strict": True}}}
    kwargs, _ = to_request("chat", chat)
    assert kwargs["output_config"] == {"effort": "high", "format": {"type": "json_schema", "schema": schema}}
    assert "thinking" not in kwargs


def test_a_forced_tool_call_is_sent_as_its_schema_and_comes_back_as_the_call():
    schema = {"type": "object", "properties": {"keep": {"type": "boolean"}}, "required": ["keep"],
              "additionalProperties": False}
    request = {"model": BULK_MODEL, "max_completion_tokens": 4000, "reasoning_effort": "low",
               "messages": [{"role": "system", "content": "Answer only by calling record_prescreen."},
                            {"role": "user", "content": "<source>README</source>"}],
               "tools": [{"type": "function", "function": {"name": "record_prescreen", "parameters": schema}}],
               "tool_choice": {"type": "function", "function": {"name": "record_prescreen"}}}
    kwargs, plan = to_request("chat", request)
    assert plan.forced_tool == "record_prescreen"
    assert "tools" not in kwargs and "tool_choice" not in kwargs  # current Claude models refuse a forced choice
    assert kwargs["output_config"]["format"] == {"type": "json_schema", "schema": schema}
    assert "reply with the JSON object of its arguments" in kwargs["system"][0]["text"]

    raw = from_message(message(THINKING, text('{"keep": true}')), plan)
    choice = raw["choices"][0]
    assert choice["finish_reason"] == "tool_calls" and choice["message"]["content"] is None
    assert choice["message"]["tool_calls"] == [{"id": "forced_msg_1", "type": "function", "function": {
        "name": "record_prescreen", "arguments": '{"keep": true}'}}]
    # Cut off before the JSON was whole: no call is made up from half an answer.
    cut = from_message(message(text('{"keep": tr'), stop="max_tokens"), plan)["choices"][0]
    assert cut["finish_reason"] == "length" and "tool_calls" not in cut["message"]
    with pytest.raises(ValueError, match="not among the tools"):
        to_request("chat", {**request, "tool_choice": {"type": "function", "function": {"name": "other"}}})


def wide_schema(nullable: int) -> dict[str, Any]:
    names = [f"p{i}" for i in range(nullable)]
    return {"type": "object", "properties": {n: {"type": ["string", "null"]} for n in names}, "required": names,
            "additionalProperties": False}


def test_a_nullable_type_list_becomes_anyof_and_a_schema_too_wide_for_claude_goes_in_the_prompt():
    schema = {"type": "object", "additionalProperties": False, "required": ["kind", "tags"], "properties": {
        "kind": {"type": ["string", "null"], "enum": ["cli_tool", None], "description": "What it is."},
        "tags": {"type": "array", "items": {"type": ["integer", "null"]}}}}
    compiled = claude_schema(schema)
    # Claude refuses an enum next to a type list ("Enum value 'cli_tool' does not match declared type").
    assert compiled["properties"]["kind"] == {"description": "What it is.", "anyOf": [
        {"type": "string", "enum": ["cli_tool"]}, {"type": "null"}]}
    assert compiled["properties"]["tags"]["items"] == {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    assert union_count(compiled) == 2 and schema["properties"]["kind"]["type"] == ["string", "null"]  # not mutated

    request = {"model": PROD_MODEL, "instructions": "Read the README.", "input": "x", "max_output_tokens": 8000}
    fits = {**request, "text": {"format": {"type": "json_schema", "name": "n", "schema": wide_schema(UNION_LIMIT)}}}
    kwargs, plan = to_request("responses", fits)
    assert not plan.prompted_schema and len(kwargs["output_config"]["format"]["schema"]["properties"]) == UNION_LIMIT
    wide = {**request, "text": {"format": {"type": "json_schema", "name": "n", "schema": wide_schema(UNION_LIMIT + 1)}}}
    kwargs, plan = to_request("responses", wide)
    assert plan.prompted_schema and "format" not in kwargs["output_config"]
    system = kwargs["system"][0]["text"]
    assert system.startswith("Read the README.") and "<json_schema>" in system and '"p16"' in system
    # The answer is cut down to its JSON object; the caller still validates it.
    raw = from_message(message(text('Here it is:\n```json\n{"p0": null}\n```')), plan)
    assert raw["output"][0]["content"][0]["text"] == '{"p0": null}' and raw["schema_in_prompt"] is True
    assert raw["output"][0]["anthropic_block"]["text"].startswith("Here it is")  # a replay sends what was said


def test_the_extraction_schema_is_the_one_that_goes_in_the_prompt():
    from pickfit.prescreen import PrescreenResult
    from pickfit.schema import ExtractionResult, meta_strict_schema

    assert union_count(claude_schema(meta_strict_schema(ExtractionResult))) > UNION_LIMIT
    assert union_count(claude_schema(meta_strict_schema(PrescreenResult))) <= UNION_LIMIT


def test_a_schema_the_api_refuses_is_sent_again_in_the_prompt_and_remembered(ledger: Ledger):
    refused = lambda body: httpx2.Response(400, json={"type": "error", "error": {  # noqa: E731
        "type": "invalid_request_error", "message": "output_config.format.schema: Invalid schema: too complex"}})
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"],
              "additionalProperties": False}
    body = {"instructions": "Name it.", "input": "tinyq",
            "text": {"format": {"type": "json_schema", "name": "named", "schema": schema, "strict": True}}}
    server = FakeAnthropic(refused, ok(message(text('{"name": "tinyq"}'))), ok(message(text('{"name": "tinyq"}'))))
    first = call(server, ledger, body=body, output_model=Named)
    assert first.parsed == Named(name="tinyq") and first.attempts == 1 and first.raw["schema_in_prompt"] is True
    sent_format, sent_prompt = server.requests
    assert "format" in sent_format["output_config"] and "format" not in sent_prompt["output_config"]
    assert "<json_schema>" in sent_prompt["system"][0]["text"]
    assert call(server, ledger, body=body, output_model=Named).parsed == Named(name="tinyq")
    assert len(server.requests) == 3 and "format" not in server.requests[2]["output_config"]  # not tried again
    # Any other 400 is the caller's to see.
    other = FakeAnthropic(status(400, "invalid_request_error"))
    with pytest.raises(anthropic.BadRequestError):
        call(other, ledger, body={"instructions": "x", "input": "y"})


def test_what_has_no_counterpart_is_refused_not_dropped():
    base = {"model": PROD_MODEL, "max_completion_tokens": 100, "reasoning_effort": "low"}
    video = {"role": "user", "content": [{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,AA=="}}]}
    with pytest.raises(ValueError, match="no video input"):
        to_request("chat", {**base, "messages": [video]})
    with pytest.raises(ValueError, match="temperature"):
        to_request("chat", {**base, "messages": [{"role": "user", "content": "x"}], "temperature": 0})
    with pytest.raises(ValueError, match="not wired"):
        to_request("responses", {"model": PROD_MODEL, "input": "x", "max_output_tokens": 100,
                                 "tools": [{"type": "web_search"}]})
    # An empty text part is left out (the API refuses one), and a conversation always opens with the user.
    kwargs, _ = to_request("chat", {**base, "messages": [{"role": "user", "content": [
        {"type": "text", "text": "  "}, {"type": "text", "text": "hello"}]}]})
    assert kwargs["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]


# ---------------------------------------------------------------- the response


def test_a_message_reads_as_a_responses_object():
    raw = from_message(message(THINKING, text("Checking the version."), TOOL_USE, stop="tool_use"),
                       Plan(endpoint="responses"))
    assert raw["status"] == "completed" and raw["incomplete_details"] is None and raw["id"] == "msg_1"
    reasoning, said, call_item = raw["output"]
    assert reasoning == {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Read the README."}],
                         "anthropic_block": THINKING}
    assert said["content"] == [{"type": "output_text", "text": "Checking the version."}]
    assert (call_item["type"], call_item["call_id"], call_item["name"]) == ("function_call", "toolu_1", "run_command")
    assert json.loads(call_item["arguments"]) == {"cmd": "tinyq --version"}
    # Input counts what was read from and written to the cache too, as pickfit's Usage does.
    assert raw["usage"] == {"input_tokens": 2000, "output_tokens": 300, "total_tokens": 2300,
                            "input_tokens_details": {"cached_tokens": 1500, "cache_write_tokens": 400}}
    assert Usage.from_raw(raw) == Usage(input_tokens=2000, cached_tokens=1500, output_tokens=300,
                                        cache_write_tokens=400)


@pytest.mark.parametrize(("stop", "responses", "chat"), [
    ("max_tokens", ("incomplete", "max_output_tokens"), "length"),
    ("refusal", ("incomplete", "content_filter"), "content_filter"),
    ("end_turn", ("completed", None), "stop"),
    ("tool_use", ("completed", None), "tool_calls"),
])
def test_stop_reasons_map_to_each_endpoints_words(stop: str, responses: tuple[str, str | None], chat: str):
    details = {"stop_details": {"type": "refusal", "category": "cyber"}} if stop == "refusal" else {}
    as_responses = from_message(message(text("x"), stop=stop, **details), Plan(endpoint="responses"))
    assert (as_responses["status"], (as_responses["incomplete_details"] or {}).get("reason")) == responses
    as_chat = from_message(message(text("x"), stop=stop, **details), Plan(endpoint="chat"))
    assert as_chat["choices"][0]["finish_reason"] == chat
    if stop == "refusal":
        assert as_responses["stop_details"]["category"] == as_chat["stop_details"]["category"] == "cyber"


def test_a_replayed_history_sends_every_block_back_as_it_came():
    """The agent resends its history each turn. A thinking block is valid only unchanged and in place, so
    the answer's items carry their blocks and go back verbatim."""
    first = from_message(message(THINKING, text("Checking."), TOOL_USE, stop="tool_use"), Plan(endpoint="responses"))
    history = [{"role": "user", "content": [{"type": "input_text", "text": "Verify tinyq."}]}, *first["output"],
               {"type": "function_call_output", "call_id": "toolu_1", "output": "tinyq 0.3.1"},
               {"role": "user", "content": [{"type": "input_text", "text": "Call finish now."},
                                            {"type": "input_image", "image_url": PNG}]}]
    kwargs, _ = to_request("responses", {"model": PROD_MODEL, "instructions": "Verify the tool.", "input": history,
                                         "max_output_tokens": 8000, "reasoning": {"effort": "medium"},
                                         "store": False, "include": ["reasoning.encrypted_content"]})
    task, answer, results = kwargs["messages"]
    assert task == {"role": "user", "content": [{"type": "text", "text": "Verify tinyq."}]}
    assert answer == {"role": "assistant", "content": [THINKING, text("Checking."), TOOL_USE]}
    assert results["content"][0] == {"type": "tool_result", "tool_use_id": "toolu_1",
                                     "content": [{"type": "text", "text": "tinyq 0.3.1"}]}
    assert [b["type"] for b in results["content"]] == ["tool_result", "text", "image"]
    assert kwargs["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------- call_meta, end to end


class Named(BaseModel):
    name: str


def test_a_call_goes_to_the_messages_api_and_is_priced_and_recorded(tmp_path: Path, ledger: Ledger):
    server = FakeAnthropic(ok(message(THINKING, text('{"name": "tinyq"}'))))
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"],
              "additionalProperties": False}
    body = {"instructions": "Name the tool.", "input": [{"role": "user", "content": [
                {"type": "input_text", "text": "<source>tinyq</source>"}]}],
            "text": {"format": {"type": "json_schema", "name": "named", "schema": schema, "strict": True}},
            "store": False}
    result = call(server, ledger, body=body, output_model=Named, run_id="r1", scope="extract:tinyq",
                  scope_cap_usd=1.0)

    (sent,) = server.requests
    assert sent["path"] == "/v1/messages" and sent["model"] == PROD_MODEL and sent["max_tokens"] == 1000
    assert sent["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": schema}}
    assert server.headers[0]["authorization"] == f"Bearer {FAKE_KEY}"  # how the SDK sends an API key
    assert "stream" not in sent and sent["fallbacks"] == "default"

    assert (result.provider, result.model, result.endpoint) == ("anthropic", PROD_MODEL, "responses")
    assert result.parsed == Named(name="tinyq") and result.status == "completed"
    assert result.reasoning_summary == "Read the README." and result.response_id == "msg_1"
    assert result.usage == Usage(input_tokens=2000, cached_tokens=1500, output_tokens=300, cache_write_tokens=400)
    assert result.cost_usd == pytest.approx((100 * 4.00 + 1500 * 0.20 + 400 * 5.00 + 300 * 20.00) / 1e6)

    with sqlite3.connect(tmp_path / "ledger.sqlite") as conn:  # Claude calls are the pipeline budget's
        assert conn.execute("SELECT budget, provider, model, status, input_tokens, cached_tokens, output_tokens "
                            "FROM calls").fetchall() == [("pipeline", "anthropic", PROD_MODEL, "settled", 2000,
                                                          1500, 300)]
    assert ledger.spend_summary()["total_usd"] == pytest.approx(result.cost_usd)
    (trace,) = traces(tmp_path)
    assert (trace["provider"], trace["model"], trace["status"], trace["finish"]) == (
        "anthropic", PROD_MODEL, "ok", "completed")
    assert trace["usage"]["cache_write_tokens"] == 400 and FAKE_KEY not in json.dumps(trace)


def test_a_tool_call_comes_back_for_the_agent_loop(ledger: Ledger):
    server = FakeAnthropic(ok(message(THINKING, TOOL_USE, stop="tool_use")))
    tools = [{"type": "function", "name": "run_command", "description": "Run a command.",
              "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}}]
    result = call(server, ledger, body={"instructions": "Verify.", "input": "tinyq", "tools": tools,
                                        "reasoning": {"summary": "auto"}, "prompt_cache_key": "run-1"},
                  reasoning_effort="medium")
    assert server.requests[0]["tools"][0]["input_schema"]["required"] == ["cmd"]
    assert server.requests[0]["thinking"] == {"type": "adaptive", "display": "summarized"}
    (tool_call,) = result.tool_calls
    assert (tool_call.call_id, tool_call.name, tool_call.json_arguments()) == (
        "toolu_1", "run_command", {"cmd": "tinyq --version"})
    assert result.text is None and result.status == "completed"
    assert [item["type"] for item in result.output_items] == ["reasoning", "function_call"]


def test_nothing_stops_a_claude_call_by_default_but_a_scope_cap_does(tmp_path: Path, monkeypatch):
    """No total or daily cap: a ledger far past the hackathon's $225 still records and sends."""
    book = meta.default_ledger()
    book.settle(book.reserve(500.0, stage="old"), 500.0)
    server = FakeAnthropic(ok(message(text("pong"))), ok(message(text("pong"))))
    result = call_meta("chat", {"messages": [{"role": "user", "content": "ping"}]}, stage="test",
                       public_data_only=True, max_output_tokens=1000, model="prod", client=server.client())
    assert result.text == "pong" and len(server.requests) == 1
    assert book.spend_summary()["total_usd"] == pytest.approx(500.0 + result.cost_usd)
    with pytest.raises(BudgetExceeded) as info:  # one run's own cap still holds
        call_meta("chat", {"messages": [{"role": "user", "content": "ping"}]}, stage="test", public_data_only=True,
                  max_output_tokens=1000, model="prod", client=server.client(), scope="verify:x",
                  scope_cap_usd=0.001, run_id="r")
    assert info.value.cap == "scope verify:x" and len(server.requests) == 1
    monkeypatch.setenv("PICKFIT_PIPELINE_TOTAL_CAP_USD", "100")  # and a cap the user sets is enforced
    with pytest.raises(BudgetExceeded) as info:
        call_meta("chat", {"messages": [{"role": "user", "content": "ping"}]}, stage="test", public_data_only=True,
                  max_output_tokens=1000, model="prod", client=server.client())
    assert info.value.cap == "total"


def test_overload_and_rate_limits_are_retried_and_a_wrong_model_is_not(ledger: Ledger, isolated: list[float],
                                                                      tmp_path: Path):
    server = FakeAnthropic(status(529, "overloaded_error"), status(429, "rate_limit_error", {"retry-after": "7"}),
                           ok(message(text("pong"))))
    result = call(server, ledger)
    assert result.attempts == 3 and result.text == "pong" and 7.0 in isolated
    statuses = [(t["status"], t["http_status"]) for t in traces(tmp_path)]
    assert statuses == [("error", 529), ("error", 429), ("ok", 200)]
    # The 529 may have been generated and billed: its worst case stays in the ledger. The 429 is released.
    with sqlite3.connect(tmp_path / "ledger.sqlite") as conn:
        assert [r[0] for r in conn.execute("SELECT status FROM calls ORDER BY id")] == ["unknown", "error", "settled"]

    wrong = FakeAnthropic(status(404, "not_found_error"))
    with pytest.raises(anthropic.NotFoundError) as info:  # Meta's on-and-off 404 is not Anthropic's: no retry
        call(wrong, ledger)
    assert len(wrong.requests) == 1
    assert FAKE_KEY not in str(info.value) and "[redacted]" in str(info.value)
    assert FAKE_KEY not in json.dumps(traces(tmp_path))


def test_a_refusal_is_an_incomplete_answer_and_a_fallback_model_is_named_and_priced(ledger: Ledger):
    declined = message(stop="refusal", stop_details={"type": "refusal", "category": "cyber", "explanation": None})
    result = call(FakeAnthropic(ok(declined)), ledger, output_model=Named)
    assert result.status == "incomplete" and result.raw["incomplete_details"] == {"reason": "content_filter"}
    assert result.parsed is None and result.raw["stop_details"]["category"] == "cyber" and result.model == PROD_MODEL

    usage = {"input_tokens": 1000, "output_tokens": 200,
             "iterations": [{"type": "message", "input_tokens": 1000, "output_tokens": 0},
                            {"type": "fallback_message", "input_tokens": 1000, "output_tokens": 200}]}
    rescued = message({"type": "fallback", "from": {"model": PROD_MODEL}, "to": {"model": "claude-opus-4-8"}},
                      text('{"name": "tinyq"}'), model="claude-opus-4-8-20260201", usage=usage)
    result = call(FakeAnthropic(ok(rescued)), ledger, output_model=Named)
    assert result.parsed == Named(name="tinyq")
    assert result.model == "claude-opus-4-8"  # the model that wrote the answer, by its priced id
    assert result.cost_usd == pytest.approx((1000 * 5.00 + 200 * 25.00) / 1e6)
    assert [i["type"] for i in result.output_items] == ["anthropic_block", "message"]


def test_a_long_generation_is_streamed_inside_the_client(ledger: Ledger):
    start = {**message(), "content": [], "stop_reason": None, "usage": {"input_tokens": 100, "output_tokens": 1}}
    stream = sse({"type": "message_start", "message": start},
                 {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                 {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "po"}},
                 {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "ng"}},
                 {"type": "content_block_stop", "index": 0},
                 {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                  "usage": {"output_tokens": 50}},
                 {"type": "message_stop"})
    server = FakeAnthropic(stream)
    result = call(server, ledger, "chat", {"messages": [{"role": "user", "content": "ping"}]},
                  max_output_tokens=32_000)
    assert server.requests[0]["stream"] is True and server.requests[0]["max_tokens"] == 32_000
    assert result.text == "pong" and result.status == "stop" and result.usage.output_tokens == 50


def test_the_dev_model_is_cached_by_default_and_prod_is_not(ledger: Ledger, tmp_path: Path):
    server = FakeAnthropic(ok(message(text("pong"), model=BULK_MODEL)))
    first = call(server, ledger, model="dev")
    again = call(server, ledger, model="dev")  # no second request: served from runs/cache
    assert (first.cache_hit, again.cache_hit, again.cost_usd, again.text) == (False, True, 0.0, "pong")
    assert first.cost_usd == pytest.approx((100 * 0.10 + 1500 * 0.01 + 400 * 0.125 + 300 * 0.50) / 1e6)
    prod = FakeAnthropic(ok(message(text("pong"))), ok(message(text("pong"))))
    assert not call(prod, ledger).cache_hit and not call(prod, ledger).cache_hit and len(prod.requests) == 2


def test_claude_refuses_what_only_metas_api_does(ledger: Ledger):
    server = FakeAnthropic()
    with pytest.raises(ValueError, match="keeps no conversations"):
        call(server, ledger, body={"input": "x", "previous_response_id": "resp_1"})
    with pytest.raises(ValueError, match="web_search is not wired"):
        call(server, ledger, body={"input": "x", "tools": [{"type": "web_search"}]})
    call(FakeAnthropic(ok(message(text("ok")))), ledger, reasoning_effort="max")  # every Claude model takes max
    assert server.requests == []


def test_ping_is_a_small_claude_call(ledger: Ledger):
    server = FakeAnthropic(ok(message(text("pong"))), ok(message(text("pong"), model=BULK_MODEL)))
    result = ping(client=server.client(), ledger=ledger)  # no model named: the prod model, as every call
    assert (result.provider, result.model, result.text) == ("anthropic", PROD_MODEL, "pong")
    assert server.requests[0]["max_tokens"] == meta.PING_MAX_OUTPUT_TOKENS and not result.cache_hit
    assert ping(model="dev", client=server.client(), ledger=ledger).model == BULK_MODEL


def test_a_user_cap_blocks_through_caps_given_to_the_ledger(tmp_path: Path):
    tight = Ledger(tmp_path / "tight.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 0.0001))
    server = FakeAnthropic()
    with pytest.raises(BudgetExceeded) as info:
        call(server, tight)
    assert info.value.cap == "daily" and server.requests == []
