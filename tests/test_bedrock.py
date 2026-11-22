"""Claude through Amazon Bedrock: the same requests and answers as the direct API, the bedrock budget, and the
way back to the direct API when Bedrock gives way. The Anthropic SDK's Bedrock client runs for real over a mocked
HTTP transport and signs with a made-up key, so no request leaves the process and AWS is never called."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest

import pickfit.env
from pickfit import anthropic_messages, bedrock_messages, meta, msg_batch
from pickfit.bedrock_messages import to_request, wire_model, with_usage
from pickfit.ledger import BudgetExceeded, Ledger, bedrock_caps, bedrock_ledger
from pickfit.meta import (
    BULK_MODEL,
    DEFAULT_PROVIDER,
    PRICES,
    PROD_MODEL,
    PROVIDERS,
    ModelRefused,
    Usage,
    call_meta,
    cost_usd,
    make_client,
    resolve_model,
    route,
)

ACCESS_KEY = "FAKE-KEY-ID-0001"  # not the shape of a real key id, so no scanner takes it for one
SECRET_KEY = "fake-secret-0123456789abcdef-NEVER-SENT"
DIRECT_KEY = "sk-ant-test-0123456789abcdef-SECRET"
PROFILE_ID = "global.anthropic.claude-opus-5-5"
INVOKE = f"/model/{PROFILE_ID}/invoke"
PNG = "data:image/png;base64,iVBORw0KGgo="
THINKING = {"type": "thinking", "thinking": "", "signature": "sig-1"}
TOOL_USE = {"type": "tool_use", "id": "toolu_1", "name": "run_command", "input": {"cmd": "tinyq --version"}}
USAGE = {"input_tokens": 100, "cache_creation_input_tokens": 400, "cache_read_input_tokens": 1500,
         "output_tokens": 300}
TOOLS = [{"type": "function", "name": "run_command", "description": "Run a command.",
          "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}}]
EPHEMERAL = {"type": "ephemeral"}


def message(*content: dict[str, Any], stop: str = "end_turn", usage: dict | None = None, **more: Any):
    # Bedrock answers with its own model id; pickfit records the id it asked for.
    return {"id": "msg_bdrk_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": list(content), "stop_reason": stop, "stop_sequence": None, "usage": usage or USAGE, **more}


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


class FakeServer:
    """Records every request and answers from a list of handlers, one per request."""

    def __init__(self, *replies: Callable[[httpx2.Request], httpx2.Response]) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self.urls: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append({"path": request.url.path, **json.loads(request.content or b"{}")})
        self.headers.append({name.lower(): value for name, value in request.headers.items()})
        self.urls.append(str(request.url))
        if not self.replies:
            raise AssertionError("unexpected extra request")
        return self.replies.pop(0)(request)

    def bedrock(self) -> bedrock_messages.Client:
        return make_client("bedrock", http_client=httpx2.Client(transport=httpx2.MockTransport(self)))

    def direct(self) -> anthropic_messages.Client:
        sdk = anthropic.Anthropic(api_key=DIRECT_KEY, base_url="https://api.anthropic.com", max_retries=0,
                                  http_client=httpx2.Client(transport=httpx2.MockTransport(self)))
        return anthropic_messages.Client(sdk)


def ok(payload: dict[str, Any]):
    return lambda request: httpx2.Response(200, json=payload)


def status(code: int, kind: str = "ThrottlingException", headers: dict[str, str] | None = None):
    # Bedrock's error body: {"message": ...} with the exception's name in a header.
    return lambda request: httpx2.Response(code, json={"message": f"{kind}: status {code}"},
                                           headers={"x-amzn-errortype": kind, **(headers or {})})


def unreachable(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("no route to bedrock-runtime", request=request)


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """No real .env, AWS credentials, ledger, runs dir or sleeping; returns the recorded backoff sleeps."""
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "PICKFIT_CLAUDE_VIA", "PICKFIT_BEDROCK_REGION",
                 "PICKFIT_BEDROCK_TOTAL_CAP_USD", "PICKFIT_BEDROCK_DAILY_CAP_USD", "PICKFIT_PIPELINE_TOTAL_CAP_USD",
                 "PICKFIT_PIPELINE_DAILY_CAP_USD", "PICKFIT_ANTHROPIC_FALLBACKS", "ANTHROPIC_API_KEY",
                 "AWS_BEARER_TOKEN_BEDROCK", "ANTHROPIC_BEDROCK_BASE_URL", "AWS_ACCESS_KEY_ID",
                 "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_BEDROCK_ACCESS_KEY_ID", ACCESS_KEY)
    monkeypatch.setenv("PICKFIT_BEDROCK_SECRET_ACCESS_KEY", SECRET_KEY)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "ledger.sqlite"))
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(anthropic_messages, "_refused_schemas", set())
    monkeypatch.setattr(meta, "_clients", {})
    monkeypatch.setattr(meta, "_notes", set())
    sleeps: list[float] = []
    monkeypatch.setattr(meta, "sleep", sleeps.append)
    return sleeps


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite")


def rows(tmp_path: Path, columns: str = "budget, provider, model, status") -> list[tuple]:
    with sqlite3.connect(tmp_path / "ledger.sqlite") as conn:
        return conn.execute(f"SELECT {columns} FROM calls ORDER BY id").fetchall()


def traces(tmp_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for path in sorted((tmp_path / "runs" / "traces").glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()]


def via_bedrock(monkeypatch: pytest.MonkeyPatch, bedrock: FakeServer, direct: FakeServer | None = None) -> None:
    """PICKFIT_CLAUDE_VIA=bedrock, with both providers' default clients answered by the fakes."""
    monkeypatch.setenv("PICKFIT_CLAUDE_VIA", "bedrock")
    clients = {"bedrock": bedrock.bedrock()}
    if direct is not None:
        clients["anthropic"] = direct.direct()
    monkeypatch.setattr(meta, "_clients", clients)


def call(endpoint: str = "responses", body: dict | None = None, **kwargs: Any):
    kwargs.setdefault("public_data_only", True)
    kwargs.setdefault("max_output_tokens", 1000)
    kwargs.setdefault("model", "prod")
    return call_meta(endpoint, body or {"instructions": "Be brief.", "input": "ping"}, stage="test", **kwargs)


def wire(endpoint: str, body: dict[str, Any], **options: Any) -> dict[str, Any]:
    """The Bedrock request for one call_meta body on the prod model."""
    request = meta.build_request(endpoint, wire_model(PROD_MODEL), body, 1000, "medium")
    return to_request(endpoint, request, **options)[0]


# ---------------------------------------------------------------- the default and the setting


def test_the_default_provider_is_still_anthropics_api(ledger: Ledger, tmp_path: Path):
    assert DEFAULT_PROVIDER == "anthropic" and meta.claude_via() == "anthropic"
    assert "bedrock" in PROVIDERS and meta.provider_for(PROD_MODEL) == "anthropic"
    server = FakeServer(ok(message(text("pong"))))
    result = call(client=server.direct(), ledger=ledger)
    assert server.requests[0]["path"] == "/v1/messages" and result.provider == "anthropic"
    assert rows(tmp_path) == [("pipeline", "anthropic", PROD_MODEL, "settled")]


def test_the_setting_must_be_one_of_the_two(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PICKFIT_CLAUDE_VIA", "vertex")
    with pytest.raises(ValueError, match="PICKFIT_CLAUDE_VIA"):
        meta.claude_via()


def test_the_setting_sends_a_claude_call_to_bedrock_signed_for_its_region(monkeypatch, tmp_path: Path):
    bedrock = FakeServer(ok(message(THINKING, text("pong"))))
    via_bedrock(monkeypatch, bedrock)
    result = call(run_id="r1", scope="extract:tinyq")

    (sent,) = bedrock.requests
    assert bedrock.urls == [f"https://bedrock-runtime.us-east-1.amazonaws.com{INVOKE}"]
    assert "model" not in sent and sent["anthropic_version"]  # the profile is in the path, as InvokeModel has it
    assert sent["max_tokens"] == 1000 and sent["output_config"] == {"effort": "low"}
    assert "fallbacks" not in sent and "anthropic_beta" not in sent and "cache_control" not in sent
    auth = bedrock.headers[0]["authorization"]
    assert auth.startswith(f"AWS4-HMAC-SHA256 Credential={ACCESS_KEY}/") and "/us-east-1/bedrock/aws4_request" in auth
    assert SECRET_KEY not in json.dumps(bedrock.headers)

    assert (result.provider, result.model, result.text) == ("bedrock", PROD_MODEL, "pong")
    assert rows(tmp_path) == [("bedrock", "bedrock", PROD_MODEL, "settled")]
    (trace,) = traces(tmp_path)
    assert (trace["provider"], trace["model"], trace["status"]) == ("bedrock", PROD_MODEL, "ok")
    assert SECRET_KEY not in json.dumps(trace) and ACCESS_KEY not in json.dumps(trace)


def test_the_region_is_a_setting_and_the_base_url_never_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("PICKFIT_BEDROCK_REGION", "us-west-2")
    monkeypatch.setenv("ANTHROPIC_BEDROCK_BASE_URL", "https://elsewhere.example")
    bedrock = FakeServer(ok(message(text("pong"))))
    call(provider="bedrock", client=bedrock.bedrock())
    assert bedrock.urls == [f"https://bedrock-runtime.us-west-2.amazonaws.com{INVOKE}"]
    assert "/us-west-2/bedrock/aws4_request" in bedrock.headers[0]["authorization"]


def test_bedrock_needs_its_own_key_and_takes_none_from_the_aws_environment(monkeypatch):
    monkeypatch.delenv("PICKFIT_BEDROCK_SECRET_ACCESS_KEY")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "the-ec2-lanes-key-id")  # the EC2 lane's key is not Bedrock's
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "another-secret")
    with pytest.raises(RuntimeError, match="PICKFIT_BEDROCK_SECRET_ACCESS_KEY is not set"):
        make_client("bedrock")


def test_a_callers_own_client_or_provider_keeps_the_setting_off(monkeypatch, ledger: Ledger, tmp_path: Path):
    via_bedrock(monkeypatch, FakeServer())  # would fail the test if it were asked
    direct = FakeServer(ok(message(text("pong"))), ok(message(text("pong"))))
    assert call(client=direct.direct(), ledger=ledger).provider == "anthropic"
    monkeypatch.setitem(meta._clients, "anthropic", direct.direct())
    assert call(provider="anthropic", ledger=ledger).provider == "anthropic"
    assert [r["path"] for r in direct.requests] == ["/v1/messages"] * 2
    assert {row[0] for row in rows(tmp_path)} == {"pipeline"}


# ---------------------------------------------------------------- the same model, or no call


def test_a_model_bedrock_does_not_offer_is_refused_never_swapped(monkeypatch, capsys, ledger: Ledger):
    assert route("bedrock", PROD_MODEL) == ("bedrock", PROFILE_ID)
    assert route("bedrock", BULK_MODEL) == ("bedrock", "global.anthropic.claude-haiku-5-5")
    assert resolve_model("prod", "bedrock") == PROD_MODEL  # the tiers mean what they mean on the direct API
    for model in ("claude-sonnet-5-5", "claude-fable-5-2", "claude-opus-5"):
        with pytest.raises(ModelRefused, match="not sent as another model"):
            route("bedrock", model)
    bedrock = FakeServer()
    with pytest.raises(ModelRefused):
        call(model="claude-sonnet-5-5", provider="bedrock", client=bedrock.bedrock(), ledger=ledger)
    assert bedrock.requests == [] and ledger.spend_summary()["calls"] == 0

    # With the setting, such a model stays where it is served, as itself, and that is said once.
    direct = FakeServer(ok(message(text("pong"))), ok(message(text("pong"))))
    via_bedrock(monkeypatch, bedrock, direct)
    for _ in range(2):
        result = call(model="claude-sonnet-5-5", ledger=ledger)
        assert (result.provider, result.model) == ("anthropic", "claude-sonnet-5-5")
    assert [r["model"] for r in direct.requests] == ["claude-sonnet-5-5"] * 2 and bedrock.requests == []
    assert capsys.readouterr().err.count("claude-sonnet-5-5 is not offered through Amazon Bedrock") == 1


def test_every_bedrock_model_is_priced_as_the_same_model_on_the_direct_api():
    for model, bedrock_id in bedrock_messages.MODELS.items():
        assert bedrock_id == f"anthropic.{model}"  # the same model's id, not a neighbour's
        assert PRICES[("bedrock", model)] == PRICES[("anthropic", model)]
    assert {m for p, m in PRICES if p == "bedrock"} == set(bedrock_messages.MODELS)
    with pytest.raises(ModelRefused, match="no price"):
        meta.price_for("bedrock", "claude-opus-5")


# ---------------------------------------------------------------- request shapes the pipeline sends


def test_a_judges_single_call_keeps_its_schema_and_image_and_caches_only_the_instructions():
    schema = {"type": "object", "properties": {"verdict": {"type": ["string", "null"], "enum": ["pass", "fail", None]}},
              "required": ["verdict"], "additionalProperties": False}
    kwargs = wire("responses", {
        "instructions": "Judge the screen.", "store": False,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Is the window open?"},
                                               {"type": "input_image", "image_url": PNG}]}],
        "text": {"format": {"type": "json_schema", "name": "verdict", "schema": schema, "strict": True}}})
    direct = anthropic_messages.to_request("responses", meta.build_request(
        "responses", PROD_MODEL, {"instructions": "Judge the screen.", "input": "x"}, 1000, "medium"))[0]
    assert "fallbacks" in direct and "betas" in direct  # what the direct API gets and Bedrock must not
    assert kwargs["model"] == PROFILE_ID and "fallbacks" not in kwargs and "betas" not in kwargs
    assert kwargs["system"] == [{"type": "text", "text": "Judge the screen.", "cache_control": EPHEMERAL}]
    assert kwargs["messages"] == [{"role": "user", "content": [
        {"type": "text", "text": "Is the window open?"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="}}]}]
    assert "cache_control" not in kwargs  # a single call: nothing would read a second breakpoint back
    assert kwargs["output_config"]["format"]["schema"]["properties"]["verdict"] == {
        "anyOf": [{"type": "string", "enum": ["pass", "fail"]}, {"type": "null"}]}


def test_an_agent_loop_gets_an_explicit_breakpoint_where_automatic_caching_puts_one():
    first = wire("responses", {"instructions": "Verify.", "input": "README of tinyq", "tools": TOOLS,
                               "reasoning": {"summary": "auto"}, "parallel_tool_calls": False}, conversation=True)
    assert "cache_control" not in first  # InvokeModel takes no top-level cache_control
    assert first["messages"] == [{"role": "user", "content": [
        {"type": "text", "text": "README of tinyq", "cache_control": EPHEMERAL}]}]
    assert first["tools"][0]["input_schema"]["required"] == ["cmd"]
    assert first["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert first["thinking"] == {"type": "adaptive", "display": "summarized"}

    # A later turn: the history replayed as it came, the new tool result last and marked.
    history = [{"role": "user", "content": "README of tinyq"},
               {"type": "reasoning", "summary": [], "anthropic_block": THINKING},
               {"type": "function_call", "call_id": "toolu_1", "name": "run_command", "arguments": "{}",
                "anthropic_block": TOOL_USE},
               {"type": "function_call_output", "call_id": "toolu_1", "output": "tinyq 1.2.0"}]
    later = wire("responses", {"instructions": "Verify.", "input": history, "tools": TOOLS})
    assert "cache_control" not in later and [m["role"] for m in later["messages"]] == ["user", "assistant", "user"]
    assert later["messages"][1]["content"] == [THINKING, TOOL_USE]  # thinking goes back unchanged
    assert later["messages"][2]["content"] == [{"type": "tool_result", "tool_use_id": "toolu_1",
                                                "content": [{"type": "text", "text": "tinyq 1.2.0"}],
                                                "cache_control": EPHEMERAL}]
    assert "cache_control" not in TOOL_USE and "cache_control" not in THINKING  # the caller's history is not touched
    assert "cache_control" not in json.dumps(later["messages"][:2])  # one breakpoint, at the end


def test_a_chat_loop_with_tool_messages_is_marked_the_same_way():
    kwargs = wire("chat", {"messages": [
        {"role": "system", "content": "Operate the page."},
        {"role": "user", "content": [{"type": "text", "text": "Click Start."},
                                     {"type": "image_url", "image_url": {"url": PNG}}]},
        {"role": "assistant", "content": None, "anthropic_content": [THINKING, TOOL_USE]},
        {"role": "tool", "tool_call_id": "toolu_1", "content": "clicked"}],
        "tools": [{"type": "function", "function": TOOLS[0] | {"type": None}}]})
    assert kwargs["messages"][-1]["content"][-1]["cache_control"] == EPHEMERAL
    assert kwargs["messages"][0]["content"][1]["source"]["type"] == "base64"
    assert json.dumps(kwargs).count('"cache_control"') == 2  # the system's and the last block's


def test_the_extraction_asks_for_an_hours_cache_and_carries_its_schema_in_the_prompt():
    wide = {"type": "object", "additionalProperties": False, "required": [f"f{i}" for i in range(20)],
            "properties": {f"f{i}": {"type": ["string", "null"]} for i in range(20)}}
    kwargs = wire("responses", {"instructions": "Extract.", "input": "<source>tinyq</source>",
                                "prompt_cache_retention": "1h",
                                "text": {"format": {"type": "json_schema", "name": "x", "schema": wide}}})
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "format" not in kwargs["output_config"] and "<json_schema>" in kwargs["system"][0]["text"]


def test_a_forced_tool_call_is_sent_as_its_schema_as_on_the_direct_api():
    kwargs, plan = to_request("responses", meta.build_request("responses", PROFILE_ID, {
        "input": "Rate it.", "tools": TOOLS, "tool_choice": {"type": "function", "name": "run_command"}}, 1000, "low"))
    assert "tools" not in kwargs and "tool_choice" not in kwargs and plan.forced_tool == "run_command"
    assert kwargs["output_config"]["format"]["schema"]["required"] == ["cmd"]


def test_what_bedrock_cannot_take_is_refused_before_it_is_sent(ledger: Ledger):
    url_image = {"input": [{"role": "user", "content": [{"type": "input_image",
                                                         "image_url": "https://example.com/shot.png"}]}]}
    with pytest.raises(ValueError, match="takes no image URLs"):
        wire("responses", url_image)
    in_a_tool_result = {"input": [{"type": "function_call", "call_id": "t1", "name": "look", "arguments": "{}"},
                                  {"type": "function_call_output", "call_id": "t1", "output": [
                                      {"type": "input_image", "image_url": "https://example.com/shot.png"}]}]}
    with pytest.raises(ValueError, match="takes no image URLs"):
        wire("responses", in_a_tool_result)
    bedrock = FakeServer()
    with pytest.raises(ValueError, match="web_search is not wired"):  # as for any Claude call
        call(body={"input": "x", "tools": [{"type": "web_search"}]}, provider="bedrock", client=bedrock.bedrock(),
             ledger=ledger)
    with pytest.raises(ValueError, match="previous_response_id"):
        call(body={"input": "x", "previous_response_id": "resp_1"}, provider="bedrock", client=bedrock.bedrock(),
             ledger=ledger)
    assert bedrock.requests == []


def test_a_schema_bedrock_refuses_is_sent_again_in_the_prompt(ledger: Ledger):
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"],
              "additionalProperties": False}
    bedrock = FakeServer(status(400, "ValidationException: output_config.format.schema: too complex"),
                         ok(message(text('Here it is: {"name": "tinyq"}'))))
    body = {"input": "Name it.", "text": {"format": {"type": "json_schema", "name": "n", "schema": schema}}}
    result = call(body=body, provider="bedrock", client=bedrock.bedrock(), ledger=ledger)
    first, second = bedrock.requests
    assert "format" in first["output_config"] and "format" not in second["output_config"]
    assert "<json_schema>" in second["system"][0]["text"] and result.text == '{"name": "tinyq"}'


# ---------------------------------------------------------------- answers, usage and price


def test_an_answer_is_read_and_priced_with_cache_reads_and_writes_as_on_the_direct_api(tmp_path: Path,
                                                                                       ledger: Ledger):
    bedrock = FakeServer(ok(message(THINKING, TOOL_USE, stop="tool_use")))
    result = call(body={"instructions": "Verify.", "input": "tinyq", "tools": TOOLS}, provider="bedrock",
                  client=bedrock.bedrock(), ledger=ledger, run_id="r1", scope="verify:tinyq", conversation=True)
    (tool_call,) = result.tool_calls
    assert (tool_call.call_id, tool_call.name, tool_call.json_arguments()) == (
        "toolu_1", "run_command", {"cmd": "tinyq --version"})
    assert [item["type"] for item in result.output_items] == ["reasoning", "function_call"]
    assert result.output_items[0]["anthropic_block"] == THINKING and result.status == "completed"

    # Anthropic's three input counts are one input figure, with the cached and the written parts named.
    assert result.usage == Usage(input_tokens=2000, cached_tokens=1500, output_tokens=300, cache_write_tokens=400)
    assert result.cost_usd == pytest.approx((100 * 4.00 + 1500 * 0.20 + 400 * 5.00 + 300 * 20.00) / 1e6)
    direct = cost_usd(PRICES[("anthropic", PROD_MODEL)], result.usage)
    assert result.cost_usd == pytest.approx(direct)  # the same tokens cost the same on either side
    assert rows(tmp_path, "budget, provider, model, status, input_tokens, cached_tokens, output_tokens, cost_usd") == [
        ("bedrock", "bedrock", PROD_MODEL, "settled", 2000, 1500, 300, pytest.approx(result.cost_usd))]
    assert bedrock_ledger().spend_summary()["total_usd"] == pytest.approx(result.cost_usd)
    assert ledger.spend_summary()["calls"] == 0  # the caller's pipeline budget holds none of it


def test_an_hours_cache_write_is_priced_as_one_with_or_without_bedrocks_breakdown(ledger: Ledger):
    asked = wire("responses", {"instructions": "Extract.", "input": "x", "prompt_cache_retention": "1h"})
    plain = wire("responses", {"instructions": "Extract.", "input": "x"})
    wrote = {"input_tokens": 50, "cache_creation_input_tokens": 3000, "cache_read_input_tokens": 0, "output_tokens": 10}
    # No breakdown, an hour asked for: all of it is an hour's write, the dearer reading.
    assert with_usage(message(usage=wrote), asked)["usage"]["cache_creation"] == {
        "ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 3000}
    assert "cache_creation" not in with_usage(message(usage=wrote), plain)["usage"]  # five minutes: nothing to add
    split = {**wrote, "cache_creation": {"ephemeral_5m_input_tokens": 1000, "ephemeral_1h_input_tokens": 2000}}
    assert with_usage(message(usage=split), asked)["usage"] == split  # a breakdown Bedrock gives is kept
    read_only = {"input_tokens": 50, "cache_read_input_tokens": 3000, "output_tokens": 10}
    assert with_usage(message(usage=read_only), asked)["usage"] == read_only

    bedrock = FakeServer(ok(message(text("{}"), usage=wrote)), ok(message(text("{}"), usage=split)))
    body = {"instructions": "Extract.", "input": "x", "prompt_cache_retention": "1h"}
    whole = call(body=body, provider="bedrock", client=bedrock.bedrock(), ledger=ledger)
    assert whole.usage.cache_write_tokens == 3000 and whole.usage.cache_write_1h_tokens == 3000
    assert whole.cost_usd == pytest.approx((50 * 4.00 + 3000 * 8.00 + 10 * 20.00) / 1e6)
    parted = call(body=body, provider="bedrock", client=bedrock.bedrock(), ledger=ledger)
    assert parted.cost_usd == pytest.approx((50 * 4.00 + 1000 * 5.00 + 2000 * 8.00 + 10 * 20.00) / 1e6)


def test_haiku_on_bedrock_is_priced_by_prompt_length_as_on_the_direct_api(ledger: Ledger):
    long_prompt = {"input_tokens": 120_000, "output_tokens": 1000}
    bedrock = FakeServer(ok(message(text("ok"), usage=long_prompt)))
    result = call(model="dev", cache=False, provider="bedrock", client=bedrock.bedrock(), ledger=ledger)
    assert bedrock.requests[0]["path"] == "/model/global.anthropic.claude-haiku-5-5/invoke"
    assert result.cost_usd == pytest.approx((120_000 * 0.50 + 1000 * 2.50) / 1e6)


def event_stream(*events: dict[str, Any]):
    """Messages stream events as InvokeModelWithResponseStream sends them: AWS event-stream frames, each a `chunk`
    whose payload carries one event as base64."""
    import base64
    import struct
    import zlib

    def header(name: str, value: str) -> bytes:
        return bytes([len(name)]) + name.encode() + b"\x07" + struct.pack(">H", len(value)) + value.encode()

    def frame(event: dict[str, Any]) -> bytes:
        headers = (header(":event-type", "chunk") + header(":content-type", "application/json")
                   + header(":message-type", "event"))
        payload = json.dumps({"bytes": base64.b64encode(json.dumps(event).encode()).decode()}).encode()
        prelude = struct.pack(">II", 16 + len(headers) + len(payload), len(headers))
        prelude += struct.pack(">I", zlib.crc32(prelude))
        body = prelude + headers + payload
        return body + struct.pack(">I", zlib.crc32(body))

    stream = b"".join(frame(event) for event in events)
    return lambda request: httpx2.Response(200, content=stream,
                                           headers={"content-type": "application/vnd.amazon.eventstream"})


def test_a_long_generation_is_streamed_from_bedrock_and_its_cache_tokens_are_counted(ledger: Ledger):
    start = {**message(), "content": [], "stop_reason": None,
             "usage": {"input_tokens": 100, "cache_creation_input_tokens": 400, "cache_read_input_tokens": 1500,
                       "output_tokens": 1}}
    bedrock = FakeServer(event_stream(
        {"type": "message_start", "message": start},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "po"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "ng"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 50}},
        {"type": "message_stop", "amazon-bedrock-invocationMetrics": {"inputTokenCount": 100, "outputTokenCount": 50}}))
    result = call("chat", {"messages": [{"role": "user", "content": "ping"}]}, max_output_tokens=32_000,
                  provider="bedrock", client=bedrock.bedrock(), ledger=ledger)
    assert bedrock.requests[0]["path"] == f"{INVOKE}-with-response-stream"  # the action the policy also allows
    assert "stream" not in bedrock.requests[0] and bedrock.requests[0]["max_tokens"] == 32_000
    assert result.text == "pong" and result.status == "stop"
    assert result.usage == Usage(input_tokens=2000, cached_tokens=1500, output_tokens=50, cache_write_tokens=400)


# ---------------------------------------------------------------- when Bedrock gives way


@pytest.mark.parametrize(("failure", "kept"), [
    (status(429, "ThrottlingException"), "error"),             # refused before generation: released
    (status(503, "ServiceUnavailableException"), "unknown"),   # may have been billed: the estimate is kept
    (status(500, "InternalServerException"), "unknown"),
    (unreachable, "error"),                                    # never left: released
])
def test_a_throttled_or_failing_bedrock_hands_the_call_to_the_direct_api(
        failure, kept: str, monkeypatch, tmp_path: Path, isolated: list[float], capsys):
    bedrock, direct = FakeServer(failure, failure), FakeServer(ok(message(text("pong"))))
    via_bedrock(monkeypatch, bedrock, direct)
    result = call(run_id="r1", scope="verify:tinyq", scope_cap_usd=5.0)

    assert len(bedrock.requests) == meta.BEDROCK_TRIES == 2 and len(isolated) == 1  # one short wait, not six
    (sent,) = direct.requests
    assert sent["path"] == "/v1/messages" and sent["model"] == PROD_MODEL  # the same model, never a lesser one
    assert sent["fallbacks"] == "default"  # the direct API's own request, with what Bedrock lacks
    assert (result.provider, result.model, result.text) == ("anthropic", PROD_MODEL, "pong")
    assert rows(tmp_path) == [("bedrock", "bedrock", PROD_MODEL, kept)] * 2 + [
        ("pipeline", "anthropic", PROD_MODEL, "settled")]
    statuses = [(t["provider"], t["status"]) for t in traces(tmp_path)]
    assert statuses == [("bedrock", "error"), ("bedrock", "error"), ("bedrock", "fallback"), ("anthropic", "ok")]
    assert traces(tmp_path)[2]["error"]["type"] == "bedrock_fallback"
    assert "Amazon Bedrock" in capsys.readouterr().err


def test_bedrock_recovering_on_its_second_try_keeps_the_call(monkeypatch, tmp_path: Path):
    bedrock = FakeServer(status(429, headers={"retry-after": "1"}), ok(message(text("pong"))))
    via_bedrock(monkeypatch, bedrock, FakeServer())
    assert call().provider == "bedrock"
    assert rows(tmp_path, "budget, status") == [("bedrock", "error"), ("bedrock", "settled")]


@pytest.mark.parametrize(("code", "kind", "error"), [
    (403, "AccessDeniedException", anthropic.PermissionDeniedError),   # the key or the model access is wrong
    (400, "ValidationException", anthropic.BadRequestError),
    (404, "ResourceNotFoundException", anthropic.NotFoundError),
])
def test_a_request_bedrock_refuses_outright_fails_rather_than_hide_a_mistake(code, kind, error, monkeypatch,
                                                                             tmp_path: Path):
    bedrock, direct = FakeServer(status(code, kind)), FakeServer()
    via_bedrock(monkeypatch, bedrock, direct)
    with pytest.raises(error):
        call()
    assert direct.requests == [] and rows(tmp_path) == [("bedrock", "bedrock", PROD_MODEL, "error")]


def test_a_request_claude_declines_on_bedrock_goes_to_the_direct_api_and_its_fallback_model(monkeypatch,
                                                                                            tmp_path: Path):
    declined = message(stop="refusal", stop_details={"type": "refusal", "category": "cyber", "explanation": None},
                       usage={"input_tokens": 900, "output_tokens": 0})
    rescued = message(text("done"), model="claude-opus-5", usage={
        "input_tokens": 900, "output_tokens": 50, "iterations": [{"type": "fallback_message"}]})
    bedrock, direct = FakeServer(ok(declined)), FakeServer(ok(rescued))
    via_bedrock(monkeypatch, bedrock, direct)
    result = call()
    assert (result.provider, result.model, result.text) == ("anthropic", "claude-opus-5", "done")
    billed = rows(tmp_path, "provider, model, status, cost_usd")
    assert [row[:3] for row in billed] == [("bedrock", PROD_MODEL, "settled"), ("anthropic", PROD_MODEL, "settled")]
    assert result.cost_usd == pytest.approx(billed[0][3] + billed[1][3]) and result.attempts == 2
    assert billed[0][3] == pytest.approx(900 * 4.00 / 1e6)  # what Bedrock billed for the decline is not lost


def test_the_bedrock_budgets_own_cap_sends_the_call_to_the_direct_api_but_a_scope_cap_stops_it(monkeypatch,
                                                                                             tmp_path: Path):
    monkeypatch.setenv("PICKFIT_BEDROCK_DAILY_CAP_USD", "0.001")
    assert bedrock_caps().daily_usd(None) == 0.001 and bedrock_ledger().budget == "bedrock"
    bedrock, direct = FakeServer(), FakeServer(ok(message(text("pong"))))
    via_bedrock(monkeypatch, bedrock, direct)
    assert call().provider == "anthropic" and bedrock.requests == []
    assert traces(tmp_path)[0]["status"] == "budget_exceeded" and traces(tmp_path)[1]["status"] == "fallback"

    monkeypatch.delenv("PICKFIT_BEDROCK_DAILY_CAP_USD")
    with pytest.raises(BudgetExceeded) as info:  # the caller's own limit holds on any provider
        call(run_id="r1", scope="verify:tinyq", scope_cap_usd=0.000001)
    assert info.value.cap == "scope verify:tinyq" and len(direct.requests) == 1


def test_a_scope_cap_counts_what_the_scope_spent_in_both_budgets(tmp_path: Path):
    """A run that moved from Bedrock to the direct API mid-way has one cap, not one for each."""
    path = tmp_path / "ledger.sqlite"
    on_bedrock, on_direct = Ledger(path, budget="bedrock"), Ledger(path)
    on_bedrock.settle(on_bedrock.reserve(2.0, run_id="r1", scope="verify:tinyq", scope_cap_usd=3.0), 2.0)
    with pytest.raises(BudgetExceeded) as info:
        on_direct.reserve(1.5, run_id="r1", scope="verify:tinyq", scope_cap_usd=3.0)
    assert info.value.spent_usd == pytest.approx(2.0)
    on_direct.reserve(0.9, run_id="r1", scope="verify:tinyq", scope_cap_usd=3.0)  # still fits
    on_direct.reserve(3.0, run_id="r2", scope="verify:tinyq", scope_cap_usd=3.0)  # another run: its own cap


def test_the_signing_key_is_scrubbed_from_what_a_failed_bedrock_call_leaves_behind(tmp_path: Path, ledger: Ledger):
    def leaky(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(403, json={"message": f"the signature made with {SECRET_KEY} does not match"})

    with pytest.raises(anthropic.PermissionDeniedError) as info:
        call(provider="bedrock", client=FakeServer(leaky).bedrock(), ledger=ledger)
    left = json.dumps(traces(tmp_path)) + str(info.value) + json.dumps(info.value.body)
    assert SECRET_KEY not in left and "[redacted]" in left


def test_the_command_line_can_ping_bedrock_and_show_its_budget(monkeypatch, capsys):
    from pickfit.cli import main

    bedrock = FakeServer(ok(message(text("pong"), usage={"input_tokens": 10, "output_tokens": 5})))
    monkeypatch.setattr(meta, "_clients", {"bedrock": bedrock.bedrock()})
    assert main(["ping", "--provider", "bedrock"]) == 0
    pinged = json.loads(capsys.readouterr().out)
    assert (pinged["provider"], pinged["model"], pinged["text"]) == ("bedrock", PROD_MODEL, "pong")
    assert main(["spend", "--budget", "bedrock"]) == 0
    spent = json.loads(capsys.readouterr().out)
    assert (spent["budget"], spent["calls"]) == ("bedrock", 1)
    assert spent["total_usd"] == pytest.approx(pinged["cost_usd"])
    assert main(["spend"]) == 0 and json.loads(capsys.readouterr().out)["calls"] == 0  # the pipeline budget: none of it


# ---------------------------------------------------------------- the key's policy and the settings' names


def test_the_policy_file_allows_the_models_pickfit_sends_and_nothing_else():
    deploy = Path(__file__).resolve().parent.parent / "deploy" / "watch"
    policy = json.loads((deploy / "aws-bedrock-policy.json").read_text(encoding="utf-8"))
    region, expected = bedrock_messages.DEFAULT_REGION, set()
    for model in bedrock_messages.MODELS:
        profile, bedrock_id = wire_model(model), bedrock_messages.MODELS[model]
        expected |= {f"arn:aws:bedrock:{region}:*:inference-profile/{profile}",  # the profile, where it is called
                     f"arn:aws:bedrock:{region}::foundation-model/{bedrock_id}",  # the model there
                     f"arn:aws:bedrock:::foundation-model/{bedrock_id}"}          # and wherever the profile routes
    assert {arn for statement in policy["Statement"] for arn in statement["Resource"]} == expected
    for statement in policy["Statement"]:
        assert statement["Effect"] == "Allow" and "Condition" in statement
        assert set(statement["Action"]) == {"bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"}
    assert "*" not in json.dumps([s["Action"] for s in policy["Statement"]])
    example = (deploy / "watch.env.example").read_text(encoding="utf-8")
    info = PROVIDERS["bedrock"]
    for name in ("PICKFIT_CLAUDE_VIA", info.key_env, info.secret_env, "PICKFIT_BEDROCK_REGION",
                 "PICKFIT_BEDROCK_DAILY_CAP_USD", "PICKFIT_BEDROCK_TOTAL_CAP_USD"):
        assert f"\n{name}=\n" in example  # named, and empty: the direct API unless someone fills it in


# ---------------------------------------------------------------- what stays on the direct API


def test_a_batch_and_what_it_sends_again_stay_on_the_direct_api(monkeypatch):
    monkeypatch.setenv("PICKFIT_CLAUDE_VIA", "bedrock")
    assert msg_batch.provider_for(resolve_model("prod")) == "anthropic"  # what a batch request is prepared for
    seen: dict[str, Any] = {}
    monkeypatch.setattr(msg_batch, "call_meta", lambda *args, **kwargs: seen.update(kwargs) or "result")
    request = msg_batch.BatchRequest(key="k", endpoint="responses", body={"input": "x"}, stage="translate",
                                     max_output_tokens=100)
    outcome = msg_batch._resend(request, run_id=None, ledger=None, runs_dir=None, client=None)
    assert seen["provider"] == "anthropic" and outcome.via == "resent"


# ---------------------------------------------------------------- the first real comparison, rehearsed


def test_the_comparison_script_asks_both_sides_the_same_and_says_where_they_differ(monkeypatch, tmp_path: Path,
                                                                                  capsys):
    """scripts/bedrock_compare.py against two fakes that behave alike, except that the Bedrock one leaves out
    the cache_creation breakdown (as AWS's pages leave open)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "bedrock_compare", Path(__file__).resolve().parent.parent / "scripts" / "bedrock_compare.py")
    compare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare)

    def platform(breakdown: bool) -> FakeServer:
        written: set[str] = set()
        count = iter(range(1, 100))

        def answer(request: httpx2.Request) -> httpx2.Response:
            body = json.loads(request.content)
            blocks = [b for m in body["messages"] for b in m["content"]]
            system, hour = body["system"][0]["text"], body["system"][0]["cache_control"].get("ttl") == "1h"
            if body.get("tools") and not any(b["type"] == "tool_result" for b in blocks):
                content, stop = [THINKING, TOOL_USE], "tool_use"
            elif "format" in body["output_config"]:
                content, stop = [text('{"verdict": "pass", "reason": "one colour"}')], "end_turn"
            else:
                content, stop = [text("It is /bin/sh.")], "end_turn"
            fresh = system not in written
            usage = {"input_tokens": 60, "output_tokens": 20, "cache_read_input_tokens": 0 if fresh else 6000,
                     "cache_creation_input_tokens": 6000 if fresh else 0}
            if breakdown and fresh:
                usage["cache_creation"] = {"ephemeral_5m_input_tokens": 0 if hour else 6000,
                                           "ephemeral_1h_input_tokens": 6000 if hour else 0}
            written.add(system)
            name = f"msg_{'direct' if breakdown else 'bdrk'}_{next(count)}"
            return httpx2.Response(200, json=message(*content, stop=stop, usage=usage) | {"id": name})

        return FakeServer(*[answer] * (compare.CALLS // 2))

    direct, bedrock = platform(breakdown=True), platform(breakdown=False)
    monkeypatch.setattr(meta, "_clients", {"anthropic": direct.direct(), "bedrock": bedrock.bedrock()})
    out = tmp_path / "compare.json"
    assert compare.main(["--out", str(out)]) == 1  # one difference: the breakdown

    assert len(direct.requests) == len(bedrock.requests) == compare.CALLS // 2 and not direct.replies
    assert {row[0] for row in rows(tmp_path)} == {"pipeline", "bedrock"} and len(rows(tmp_path)) == compare.CALLS
    report = json.loads(out.read_text(encoding="utf-8"))
    assert len(report["differences"]) == 1 and report["differences"][0].startswith("hour: Bedrock's usage has no")
    hour = report["cases"]["hour"]
    assert [c["cache_write_1h"] for c in hour["bedrock"]] == [6000, 0]  # filled in by with_usage
    assert [c["cache_write_1h"] for c in hour["anthropic"]] == [6000, 0]
    assert "cache_creation" in hour["anthropic"][0]["native_usage_keys"]
    assert "cache_creation" not in hour["bedrock"][0]["native_usage_keys"]
    agent = report["cases"]["agent"]["bedrock"]
    assert (agent[0]["cache_write"], agent[1]["cache_read"], agent[0]["tool_calls"]) == (6000, 6000, ["run_command"])
    switched = report["cases"]["switch"]["bedrock->anthropic"]
    assert [c["provider"] for c in switched] == ["bedrock", "anthropic"] and not any(c["fell_back"] for c in switched)
    # The second provider is sent the first one's thinking and tool call, as a fall back mid-run would send them.
    assert direct.requests[-1]["messages"][1]["content"] == [THINKING, TOOL_USE]
    table = capsys.readouterr().out
    assert "differences:" in table and "spent: US$" in table and "no cache_creation breakdown" in table
    hooks = (anthropic_messages.from_message.__name__, bedrock_messages.with_usage.__name__)
    assert hooks == ("from_message", "with_usage")  # the recording hooks are taken off again

    assert compare.main(["--dry-run"]) == 0 and "14 calls" in capsys.readouterr().out
    assert len(direct.requests) == compare.CALLS // 2  # the dry run asked nobody
