"""call_meta with a mocked HTTP transport: no request ever leaves the process."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import openai
import pytest
from pydantic import BaseModel

import pickfit.env
from pickfit import meta
from pickfit.env import read_env
from pickfit.ledger import BudgetExceeded, Caps, Ledger
from pickfit.meta import (
    OPEN_MODEL,
    PRICES,
    ModelRefused,
    PrivateDataRefused,
    Usage,
    call_meta,
    cost_usd,
    estimate_input_tokens,
    is_open_model,
    ping,
    provider_for,
    resolve_model,
)

FAKE_KEY = "sk-test-0123456789abcdef-SECRET"
CHAT_BODY = {"messages": [{"role": "user", "content": "Summarise this public README."}]}

CHAT_OK = {
    "id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": "muse-spark-1.3-contributor",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "pong"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500,
              "prompt_tokens_details": {"cached_tokens": 200},
              "completion_tokens_details": {"reasoning_tokens": 300}},
}

RESPONSES_OK = {
    "id": "resp_1", "object": "response", "created_at": 0, "model": "muse-spark-1.3", "status": "completed",
    "output": [
        {"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": "Read the README."}]},
        {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
         "content": [{"type": "output_text", "text": '{"name": "tinyq"}', "annotations": []}]},
        {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "run_command",
         "arguments": '{"cmd": "tinyq --version"}', "status": "completed"},
    ],
    "usage": {"input_tokens": 2000, "input_tokens_details": {"cached_tokens": 1000},
              "output_tokens": 400, "output_tokens_details": {"reasoning_tokens": 100}, "total_tokens": 2400},
}

SERVER_503 = {"error": {"message": "persistence service error", "type": "server_error"}}


class FakeServer:
    """Records every request and answers from a list of handlers, one per request."""

    def __init__(self, *replies: Callable[[dict[str, Any]], httpx2.Response]) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.auth_headers: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content or b"{}")
        self.requests.append({"path": request.url.path, **body})
        self.auth_headers.append(request.headers.get("authorization", ""))
        if not self.replies:
            raise AssertionError("unexpected extra request")
        return self.replies.pop(0)(body)

    def client(self) -> openai.OpenAI:
        transport = httpx2.MockTransport(self)
        return openai.OpenAI(api_key=FAKE_KEY, base_url="https://api.meta.ai/v1", max_retries=0,
                             http_client=httpx2.Client(transport=transport))


def ok(payload: dict[str, Any]) -> Callable[[dict[str, Any]], httpx2.Response]:
    return lambda body: httpx2.Response(200, json=payload)


def status(code: int, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
    error = payload or {"error": {"message": f"status {code}", "type": "server_error"}}
    return lambda body: httpx2.Response(code, json=error, headers=headers)


def raises(exc: BaseException):
    """A transport failure instead of a response."""
    def reply(body: dict[str, Any]) -> httpx2.Response:
        raise exc
    return reply


def sse(*events: dict[str, Any], done: bool = False):
    lines = []
    for event in events:
        if "type" in event:
            lines.append(f"event: {event['type']}")
        lines.append(f"data: {json.dumps(event)}\n")
    if done:
        lines.append("data: [DONE]\n")
    content = ("\n".join(lines) + "\n").encode()
    return lambda body: httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=content)


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """No real .env, ledger, runs dir or sleeping; returns the recorded backoff sleeps."""
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "MODEL_API_KEY", "BASETEN_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_LEDGER", str(tmp_path / "default-ledger.sqlite"))
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path / "runs"))
    sleeps: list[float] = []
    monkeypatch.setattr(meta, "sleep", sleeps.append)
    return sleeps


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 25.0))


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    return tmp_path / "runs"


def traces(runs: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for path in sorted((runs / "traces").glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()]


def call(server: FakeServer, ledger: Ledger, endpoint: str = "chat", body: dict | None = None, **kwargs):
    kwargs.setdefault("public_data_only", True)
    kwargs.setdefault("max_output_tokens", 1000)
    return call_meta(endpoint, body or CHAT_BODY, stage="test", client=server.client(), ledger=ledger,
                     **kwargs)


# ---------------------------------------------------------------- cost math


def test_cost_for_chat_usage_shape():
    usage = Usage.from_raw(CHAT_OK)
    assert usage == Usage(input_tokens=1000, cached_tokens=200, output_tokens=500, reasoning_tokens=300)
    # muse-spark-1.3: 800 fresh x 1.25 + 200 cached x 0.15 + 500 out x 4.25, per 1M tokens
    assert cost_usd(PRICES[("meta", "muse-spark-1.3")], usage) == pytest.approx(0.003155)
    # contributor: cached price unknown, so cached input is charged at the input price
    assert cost_usd(PRICES[("meta", "muse-spark-1.3-contributor")], usage) == pytest.approx(0.0002)


def test_cost_for_responses_usage_shape_with_web_search():
    usage = Usage.from_raw(RESPONSES_OK)
    assert usage == Usage(input_tokens=2000, cached_tokens=1000, output_tokens=400, reasoning_tokens=100)
    assert cost_usd(PRICES[("meta", "muse-spark-1.3")], usage) == pytest.approx(0.0031)

    with_search = {**RESPONSES_OK, "output": [*RESPONSES_OK["output"], {"type": "web_search_call", "id": "ws"}]}
    searched = Usage.from_raw(with_search)
    assert searched.web_searches == 1
    assert cost_usd(PRICES[("meta", "muse-spark-1.3")], searched) == pytest.approx(0.0031 + 0.0025)


def test_wonder_and_baseten_prices():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost_usd(PRICES[("meta", "muse-wonder-1.0")], usage) == pytest.approx(24.0)
    assert cost_usd(PRICES[("baseten", "meta-models/muse-spark-open")], usage) == pytest.approx(5.5)


def test_missing_usage_is_none():
    assert Usage.from_raw({"id": "x"}) is None


def test_image_estimate_does_not_count_base64_bytes():
    image = "data:image/png;base64," + "A" * 3_000_000
    body = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": image}}]}]}
    assert meta.IMAGE_TOKENS <= estimate_input_tokens(body) < meta.IMAGE_TOKENS + 200


def test_image_estimate_counts_url_and_file_id_images():
    chat = {"messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/shot.png"}}]}]}
    responses = {"input": [{"role": "user", "content": [
        {"type": "input_image", "file_id": "file_1"},
        {"type": "input_image", "image_url": "data:image/png;base64,AAAA"}]}]}
    assert estimate_input_tokens(chat) >= meta.IMAGE_TOKENS
    assert estimate_input_tokens(responses) >= 2 * meta.IMAGE_TOKENS


# ---------------------------------------------------------------- calls


def test_chat_call_settles_ledger_and_writes_trace(ledger: Ledger, runs: Path):
    server = FakeServer(ok(CHAT_OK))
    result = call(server, ledger, run_id="run-1", scope="extract:tinyq")

    sent = server.requests[0]
    assert sent["path"] == "/v1/chat/completions"
    assert sent["model"] == "muse-spark-1.3-contributor"  # PICKFIT_MODE unset -> dev
    assert sent["max_completion_tokens"] == 1000
    assert sent["reasoning_effort"] == "minimal"
    assert "stream" not in sent

    assert result.text == "pong" and result.status == "stop"
    assert result.cost_usd == pytest.approx(0.0002)
    assert result.response_id == "chatcmpl-1" and not result.cache_hit and result.attempts == 1

    summary = ledger.spend_summary()
    assert summary["total_usd"] == pytest.approx(0.0002)
    assert summary["open_reservations_usd"] == 0
    assert summary["by_stage"] == {"test": pytest.approx(0.0002)}

    [line] = traces(runs)
    assert line["status"] == "ok" and line["attempt"] == 1 and line["cache_hit"] is False
    assert line["model"] == "muse-spark-1.3-contributor" and line["endpoint"] == "chat"
    assert line["run_id"] == "run-1" and line["scope"] == "extract:tinyq" and line["stage"] == "test"
    assert line["usage"]["reasoning_tokens"] == 300
    assert line["cost_usd"] == pytest.approx(0.0002)
    assert line["request_hash"] == result.request_hash and line["response_id"] == "chatcmpl-1"
    assert line["reserved_usd"] > line["cost_usd"]
    assert "latency_s" in line


def test_responses_call_parses_output_tools_and_reasoning(ledger: Ledger, runs: Path):
    class Profile(BaseModel):
        name: str

    server = FakeServer(ok(RESPONSES_OK))
    result = call(server, ledger, "responses", {"input": "README text", "reasoning": {"summary": "auto"}},
                  model="prod", reasoning_effort="low", output_model=Profile)

    sent = server.requests[0]
    assert sent["path"] == "/v1/responses"
    assert sent["model"] == "muse-spark-1.3"
    assert sent["reasoning"] == {"summary": "auto", "effort": "low"}
    assert sent["max_output_tokens"] == 1000

    assert result.parsed == Profile(name="tinyq") and result.parse_error is None
    assert result.tool_calls[0].name == "run_command"
    assert result.tool_calls[0].json_arguments() == {"cmd": "tinyq --version"}
    assert result.reasoning_summary == "Read the README."
    assert result.cost_usd == pytest.approx(0.0031)
    assert traces(runs)[0]["reasoning_summary"] == "Read the README."


def test_chained_response_reserves_for_previous_context(ledger: Ledger, runs: Path):
    server = FakeServer(ok(RESPONSES_OK), ok({**RESPONSES_OK, "id": "resp_2"}))
    call(server, ledger, "responses", {"input": "turn 1"}, model="prod")
    call(server, ledger, "responses", {"input": "turn 2", "previous_response_id": "resp_1"}, model="prod")
    first, second = traces(runs)
    context_usd = 2400 * 1.25 / 1_000_000  # resp_1 used 2,000 in + 400 out
    # the longer body adds a few estimated tokens too
    assert second["reserved_usd"] == pytest.approx(first["reserved_usd"] + context_usd, abs=5e-5)


def test_chain_from_another_process_uses_the_ledger(ledger: Ledger, runs: Path):
    # An earlier process settled resp_big with a 200K-token context.
    row = ledger.reserve(1.0, model="muse-spark-1.3")
    ledger.settle(row, 0.3, tokens={"input_tokens": 190_000, "output_tokens": 10_000}, response_id="resp_big")
    server = FakeServer(ok(RESPONSES_OK), ok(RESPONSES_OK))
    call(server, ledger, "responses", {"input": "next", "previous_response_id": "resp_big"}, model="prod")
    call(server, ledger, "responses", {"input": "next", "previous_response_id": "resp_unseen"}, model="prod")
    known, unseen = traces(runs)
    assert known["reserved_usd"] - unseen["reserved_usd"] == pytest.approx(
        (200_000 - meta.UNKNOWN_CONTEXT_TOKENS) * 1.25 / 1_000_000, abs=1e-5)  # ids differ in length


def test_cache_hit_is_free_and_logged(ledger: Ledger, runs: Path):
    server = FakeServer(ok(CHAT_OK))
    first = call(server, ledger)
    second = call(server, ledger)

    assert len(server.requests) == 1
    assert second.cache_hit and second.cost_usd == 0 and second.attempts == 0
    assert second.text == first.text and second.response_id == first.response_id
    assert (runs / "cache" / f"{first.request_hash}.json").exists()

    lines = traces(runs)
    assert [line["cache_hit"] for line in lines] == [False, True]
    assert lines[1]["cost_usd"] == 0 and lines[1]["request_hash"] == first.request_hash

    summary = ledger.spend_summary()
    assert summary["cache_hits"] == 1 and summary["calls"] == 2
    assert summary["total_usd"] == pytest.approx(first.cost_usd)


def test_cache_off_with_env(ledger: Ledger, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PICKFIT_CACHE", "0")
    server = FakeServer(ok(CHAT_OK), ok(CHAT_OK))
    call(server, ledger)
    assert not call(server, ledger).cache_hit
    assert len(server.requests) == 2


def test_cache_is_off_for_prod_unless_asked(ledger: Ledger, runs: Path, monkeypatch: pytest.MonkeyPatch):
    server = FakeServer(ok(CHAT_OK), ok(CHAT_OK))
    call(server, ledger, model="prod")
    assert not call(server, ledger, model="prod").cache_hit
    assert len(server.requests) == 2 and not (runs / "cache").exists()

    monkeypatch.setenv("PICKFIT_CACHE", "1")
    server = FakeServer(ok(CHAT_OK))
    call(server, ledger, model="prod")
    assert call(server, ledger, model="prod").cache_hit


def test_incomplete_or_invalid_answers_are_not_cached(ledger: Ledger, runs: Path):
    class Profile(BaseModel):
        name: str

    truncated = {**CHAT_OK, "choices": [{"index": 0, "message": {"role": "assistant", "content": ""},
                                         "finish_reason": "length"}]}
    server = FakeServer(ok(truncated), ok(truncated))
    call(server, ledger)
    assert not call(server, ledger).cache_hit  # a retry reaches the model

    incomplete = {**RESPONSES_OK, "status": "incomplete"}
    server = FakeServer(ok(incomplete), ok(incomplete))
    call(server, ledger, "responses", {"input": "x"})
    assert not call(server, ledger, "responses", {"input": "x"}).cache_hit

    not_json = {**CHAT_OK, "choices": [{"index": 0, "message": {"role": "assistant", "content": "nope"},
                                        "finish_reason": "stop"}]}
    body = {"messages": [{"role": "user", "content": "profile please"}]}
    server = FakeServer(ok(not_json), ok(not_json))
    assert call(server, ledger, body=body, output_model=Profile).parse_error
    assert not call(server, ledger, body=body, output_model=Profile).cache_hit
    assert not (runs / "cache").exists()


def test_cached_answer_that_fails_validation_is_not_served(ledger: Ledger):
    class Profile(BaseModel):
        name: str

    server = FakeServer(ok(CHAT_OK), ok(CHAT_OK))
    call(server, ledger)  # cached: "pong" is fine without an output model
    result = call(server, ledger, output_model=Profile)
    assert not result.cache_hit and len(server.requests) == 2


def test_daily_cap_blocks_before_sending(tmp_path: Path, runs: Path):
    tight = Ledger(tmp_path / "tight.sqlite", caps=Caps(total_usd=100.0, daily_usd=lambda d: 0.0001))
    server = FakeServer(ok(CHAT_OK))
    with pytest.raises(BudgetExceeded):
        call(server, tight, model="prod")
    assert server.requests == []
    [line] = traces(runs)
    assert line["status"] == "budget_exceeded"
    assert tight.spend_summary()["calls"] == 0


def test_scope_cap_blocks_before_sending(ledger: Ledger):
    server = FakeServer(ok(CHAT_OK))
    with pytest.raises(BudgetExceeded) as info:
        call(server, ledger, model="prod", scope="verify:tinyq", scope_cap_usd=0.001)
    assert info.value.cap == "scope verify:tinyq"
    assert server.requests == []


def test_contributor_refused_for_non_public_data(ledger: Ledger):
    server = FakeServer()
    with pytest.raises(PrivateDataRefused):
        call(server, ledger, public_data_only=False)  # default mode dev -> contributor
    with pytest.raises(PrivateDataRefused):
        call(server, ledger, model="muse-spark-1.3-contributor", public_data_only=False)
    assert server.requests == []


def test_prod_allowed_for_non_public_data(ledger: Ledger, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PICKFIT_MODE", "prod")
    server = FakeServer(ok(CHAT_OK))
    call(server, ledger, public_data_only=False)
    assert server.requests[0]["model"] == "muse-spark-1.3"


def test_open_alias_names_muse_spark_open_on_baseten():
    assert resolve_model("open") == resolve_model("open", "baseten") == OPEN_MODEL
    assert provider_for(OPEN_MODEL) == "baseten" and provider_for("muse-spark-1.3") == "meta"
    assert is_open_model("open") and is_open_model(OPEN_MODEL)
    assert not is_open_model("prod") and not is_open_model("muse-spark-1.3") and not is_open_model(None)


def test_open_model_is_sent_to_baseten_and_billed_to_its_budget(tmp_path: Path, runs: Path):
    server = FakeServer(ok({**RESPONSES_OK, "model": OPEN_MODEL}))
    result = call_meta("responses", {"input": "README text", "store": False}, stage="test", public_data_only=True,
                       max_output_tokens=1000, model="open", client=server.client())
    assert server.requests[0]["model"] == OPEN_MODEL
    assert (result.provider, result.model) == ("baseten", OPEN_MODEL)
    assert result.cost_usd == pytest.approx(0.0031)  # Baseten's list price, same as muse-spark-1.3
    with sqlite3.connect(tmp_path / "default-ledger.sqlite") as conn:  # PICKFIT_LEDGER (the isolated fixture)
        assert conn.execute("SELECT budget, provider, model FROM calls").fetchall() == [
            ("baseten", "baseten", OPEN_MODEL)]
    assert (traces(runs)[0]["provider"], traces(runs)[0]["model"]) == ("baseten", OPEN_MODEL)


def test_open_model_cannot_be_sent_to_meta(ledger: Ledger):
    server = FakeServer()
    with pytest.raises(ModelRefused):
        call(server, ledger, "responses", {"input": "x"}, model="open", provider="meta")
    with pytest.raises(ValueError, match="stateless"):
        call(server, ledger, "responses", {"input": "x", "previous_response_id": "resp_1"}, model="open")
    assert server.requests == []


def test_unknown_model_refused(ledger: Ledger):
    server = FakeServer()
    with pytest.raises(ModelRefused):
        call(server, ledger, model="muse-spark-9")
    with pytest.raises(ModelRefused):
        call(server, ledger, model="meta-models/unknown", provider="baseten")
    with pytest.raises(ModelRefused):
        call(server, ledger, provider="baseten")  # no alias on Baseten: be explicit
    assert server.requests == []


def test_request_body_cannot_override_managed_keys(ledger: Ledger):
    with pytest.raises(ValueError):
        call(FakeServer(), ledger, body={**CHAT_BODY, "model": "muse-wonder-1.0"})
    with pytest.raises(ValueError):
        call(FakeServer(), ledger, "responses", {"input": "x", "reasoning": {"effort": "high"}})
    with pytest.raises(ValueError):
        call(FakeServer(), ledger, max_output_tokens=0)


@pytest.mark.parametrize("extra", [
    {"extra_body": {"model": "muse-spark-1.3-contributor", "max_completion_tokens": 131072}},
    {"extra_body": {"model": "muse-wonder-1.0"}},
    {"extra_headers": {"x-model": "muse-wonder-1.0"}},
    {"extra_query": {"model": "muse-wonder-1.0"}},
    {"timeout": 1},
    {"n": 2},
    {"web_search_options": {}},
])
def test_body_cannot_bypass_policy_or_cost_bound(ledger: Ledger, extra: dict[str, Any]):
    server = FakeServer()
    with pytest.raises(ValueError):
        call(server, ledger, body={**CHAT_BODY, **extra}, model="prod", public_data_only=False)
    assert server.requests == [] and ledger.spend_summary()["calls"] == 0


@pytest.mark.parametrize("extra", [{"conversation": "conv_1"}, {"prompt": {"id": "pmpt_1"}}])
def test_responses_server_side_context_is_refused(ledger: Ledger, extra: dict[str, Any]):
    server = FakeServer()
    with pytest.raises(ValueError):
        call(server, ledger, "responses", {"input": "x", **extra}, model="prod")
    assert server.requests == []


def test_unknown_body_keys_go_in_extra_body_without_overriding(ledger: Ledger):
    server = FakeServer(ok(CHAT_OK))
    call(server, ledger, body={**CHAT_BODY, "n": 1, "vendor_flag": True}, model="prod")
    sent = server.requests[0]
    assert sent["vendor_flag"] is True and sent["n"] == 1
    assert sent["model"] == "muse-spark-1.3" and sent["max_completion_tokens"] == 1000


def test_web_search_is_capped_and_reserved_per_search(ledger: Ledger, runs: Path):
    search = {"tools": [{"type": "web_search"}]}
    server = FakeServer(ok(RESPONSES_OK), ok(RESPONSES_OK))
    call(server, ledger, "responses", {"input": "x", **search}, model="prod")
    call(server, ledger, "responses", {"input": "x", **search, "max_tool_calls": 1}, model="prod")
    assert server.requests[0]["max_tool_calls"] == meta.WEB_SEARCHES_PER_CALL
    assert server.requests[1]["max_tool_calls"] == 1

    default, one = (line["reserved_usd"] for line in traces(runs))
    per_search = meta.WEB_SEARCH_USD + meta.TOKENS_PER_WEB_SEARCH * 1.25 / 1_000_000
    assert default - one == pytest.approx((meta.WEB_SEARCHES_PER_CALL - 1) * per_search, abs=1e-5)

    with pytest.raises(ValueError):
        call(FakeServer(), ledger, "responses", {"input": "x", **search, "max_tool_calls": 0})
    with pytest.raises(ValueError):  # Chat has no max_tool_calls, so no bound on searches
        call(FakeServer(), ledger, body={**CHAT_BODY, **search})


def test_503_then_success_is_retried_and_logged_twice(ledger: Ledger, runs: Path, isolated: list[float]):
    server = FakeServer(status(503, SERVER_503), ok(RESPONSES_OK))
    result = call(server, ledger, "responses", {"input": "turn 2", "previous_response_id": "resp_0"},
                  model="prod")

    assert len(server.requests) == 2 and result.attempts == 2
    first, second = traces(runs)
    assert (first["attempt"], first["status"], first["http_status"]) == (1, "error", 503)
    assert "persistence service error" in first["error"]["message"]
    assert first["cost_usd"] == first["reserved_usd"] > 0  # a 5xx may have been billed
    assert (second["attempt"], second["status"]) == (2, "ok")
    assert len(isolated) == 1  # one backoff sleep
    summary = ledger.spend_summary()
    assert summary["total_usd"] == pytest.approx(result.cost_usd + first["reserved_usd"], abs=1e-6)
    assert summary["open_reservations_usd"] == 0


def test_server_errors_give_up_after_three_tries(ledger: Ledger, runs: Path):
    server = FakeServer(status(500), status(502), status(503))
    with pytest.raises(openai.InternalServerError):
        call(server, ledger)
    assert len(server.requests) == 3
    lines = traces(runs)
    assert [line["http_status"] for line in lines] == [500, 502, 503]
    held = sum(line["reserved_usd"] for line in lines)
    assert [line["cost_usd"] for line in lines] == [line["reserved_usd"] for line in lines]
    assert ledger.spend_summary()["total_usd"] == pytest.approx(held, abs=1e-6)


def test_4xx_is_released(ledger: Ledger):
    server = FakeServer(status(429), status(400))
    with pytest.raises(openai.BadRequestError):
        call(server, ledger)
    assert len(server.requests) == 2 and ledger.spend_summary()["total_usd"] == 0


def test_connection_refused_is_released_but_a_drop_after_sending_is_held(ledger: Ledger, runs: Path):
    server = FakeServer(raises(httpx2.ConnectError("refused")),
                        raises(httpx2.RemoteProtocolError("Server disconnected")), ok(CHAT_OK))
    result = call(server, ledger)
    assert len(server.requests) == 3 and result.attempts == 3
    refused, dropped, _ = traces(runs)
    assert refused["cost_usd"] == 0
    assert dropped["cost_usd"] == dropped["reserved_usd"] > 0
    total = ledger.spend_summary()["total_usd"]
    assert total == pytest.approx(result.cost_usd + dropped["reserved_usd"], abs=1e-6)


def test_504_holds_its_estimate(ledger: Ledger, runs: Path):
    server = FakeServer(status(504), ok(CHAT_OK))
    result = call(server, ledger, model="prod")
    first = traces(runs)[0]
    assert first["cost_usd"] == first["reserved_usd"] > 0
    total = ledger.spend_summary()["total_usd"]
    assert total == pytest.approx(result.cost_usd + first["reserved_usd"], abs=1e-6)


def test_429_honors_retry_after(ledger: Ledger, isolated: list[float]):
    server = FakeServer(status(429, headers={"retry-after": "7"}), ok(CHAT_OK))
    assert call(server, ledger).attempts == 2
    assert isolated == [7.0]


def test_retry_after_is_clamped(ledger: Ledger, isolated: list[float]):
    server = FakeServer(status(429, headers={"retry-after": "86400"}),
                        status(429, headers={"retry-after-ms": "-5"}), ok(CHAT_OK))
    assert call(server, ledger).attempts == 3
    assert isolated == [meta.BACKOFF_MAX_S, 0.0]


def test_400_is_not_retried(ledger: Ledger, runs: Path):
    server = FakeServer(status(400, {"error": {"message": "stop is not supported", "type": "invalid_request"}}))
    with pytest.raises(openai.BadRequestError):
        call(server, ledger)
    assert len(server.requests) == 1 and len(traces(runs)) == 1


def test_chat_504_falls_back_to_streaming(ledger: Ledger, runs: Path):
    chunk = {"id": "chatcmpl-9", "object": "chat.completion.chunk", "created": 0, "model": "muse-spark-1.3"}
    server = FakeServer(
        status(504, {"error": {"message": "gateway timeout", "type": "gateway_timeout"}}),
        sse({**chunk, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "po"}}]},
            {**chunk, "choices": [{"index": 0, "delta": {"content": "ng"}, "finish_reason": "stop"}]},
            {**chunk, "choices": [], "usage": CHAT_OK["usage"]}, done=True),
    )
    result = call(server, ledger, model="prod")

    assert "stream" not in server.requests[0]
    assert server.requests[1]["stream"] is True
    assert server.requests[1]["stream_options"] == {"include_usage": True}
    assert result.text == "pong" and result.status == "stop" and result.response_id == "chatcmpl-9"
    assert result.cost_usd == pytest.approx(0.003155)
    first, second = traces(runs)
    assert (first["http_status"], first["stream"]) == (504, False)
    assert (second["status"], second["stream"]) == ("ok", True)


def test_chat_stream_aggregates_tool_calls():
    chunk = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m"}
    parts = [
        {"index": 0, "id": "call_1", "type": "function", "function": {"name": "finish", "arguments": '{"ok"'}},
        {"index": 0, "function": {"arguments": ": true}"}},
    ]
    raw = meta._collect_chat_stream([
        {**chunk, "choices": [{"index": 0, "delta": {"tool_calls": [parts[0]]}}]},
        {**chunk, "choices": [{"index": 0, "delta": {"tool_calls": [parts[1]]}, "finish_reason": "tool_calls"}]},
    ])
    [tool_call] = raw["choices"][0]["message"]["tool_calls"]
    assert tool_call == {"id": "call_1", "type": "function", "function": {"name": "finish", "arguments": '{"ok": true}'}}


def test_responses_504_falls_back_to_streaming(ledger: Ledger, runs: Path):
    server = FakeServer(
        status(504, {"error": {"message": "gateway timeout", "type": "gateway_timeout"}}),
        sse({"type": "response.created", "sequence_number": 0,
             "response": {**RESPONSES_OK, "status": "in_progress", "output": [], "usage": None}},
            {"type": "response.output_text.delta", "sequence_number": 1, "item_id": "msg_1",
             "output_index": 1, "content_index": 0, "delta": "{}", "logprobs": []},
            {"type": "response.completed", "sequence_number": 2, "response": RESPONSES_OK}),
    )
    result = call(server, ledger, "responses", {"input": "x"}, model="prod")
    assert server.requests[1]["stream"] is True
    assert result.text == '{"name": "tinyq"}' and result.cost_usd == pytest.approx(0.0031)
    assert [line["stream"] for line in traces(runs)] == [False, True]


def test_second_504_while_streaming_gives_up(ledger: Ledger):
    server = FakeServer(status(504), status(504))
    with pytest.raises(openai.APIStatusError):
        call(server, ledger)
    assert len(server.requests) == 2


def test_api_key_never_in_trace_or_cache(ledger: Ledger, runs: Path):
    echo = {"error": {"message": f"invalid key {FAKE_KEY} or LLM_123_abcDEF", "type": "authentication_error"}}
    server = FakeServer(ok(CHAT_OK), status(401, echo))
    call(server, ledger)
    with pytest.raises(openai.AuthenticationError) as info:
        call(server, ledger, body={"messages": [{"role": "user", "content": "other"}]})
    for shown in (str(info.value), info.value.message, json.dumps(info.value.body)):
        assert FAKE_KEY not in shown and "LLM_123_abcDEF" not in shown

    assert server.auth_headers[0] == f"Bearer {FAKE_KEY}"  # the key did go to the (fake) server
    files = list((runs / "traces").glob("*.jsonl")) + list((runs / "cache").glob("*.json"))
    assert len(files) == 2
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert FAKE_KEY not in text and "LLM_123_abcDEF" not in text
    assert "[redacted]" in next((runs / "traces").glob("*.jsonl")).read_text(encoding="utf-8")


def test_ping_is_tiny_public_and_uncached(ledger: Ledger, runs: Path):
    server = FakeServer(ok(CHAT_OK), ok(CHAT_OK))
    ping(client=server.client(), ledger=ledger)
    ping(client=server.client(), ledger=ledger)
    assert len(server.requests) == 2
    assert server.requests[0]["max_completion_tokens"] == meta.PING_MAX_OUTPUT_TOKENS
    assert server.requests[0]["model"] == "muse-spark-1.3-contributor"
    assert not (runs / "cache").exists()


# ---------------------------------------------------------------- env


def test_env_reads_only_requested_names_and_process_env_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# comment\n"
        "export MODEL_API_KEY='from-file'\n"
        'BASETEN_API_KEY="baseten-file"\n'
        "ANTHROPIC_API_KEY=never-read\n"
        "PICKFIT_MODE=prod # inline comment\n"
        "EMPTY=\n"
    )
    monkeypatch.setenv("BASETEN_API_KEY", "from-process")
    values = read_env(["MODEL_API_KEY", "BASETEN_API_KEY", "PICKFIT_MODE", "EMPTY", "MISSING"], dotenv)
    assert values == {"MODEL_API_KEY": "from-file", "BASETEN_API_KEY": "from-process", "PICKFIT_MODE": "prod"}
    assert "MODEL_API_KEY" not in os.environ  # never exported
