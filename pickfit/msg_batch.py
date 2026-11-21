"""Message Batches: model calls that can wait, at half price.

Anthropic's Message Batches API answers a set of Messages requests within 24 hours (most within an hour) and
bills every token at half the list price. pickfit sends the calls whose answers nobody is waiting for through
it: backfills of the page's zh-TW sentences (pickfit.translate) and of usage guides (pickfit.usage_guide).
Extraction and the README rubric are to follow once their own changes land (docs/proposals/tokens.md, T3).

run() takes the same requests call_meta takes (Chat or Responses shapes, pickfit.anthropic_messages turns
them into Messages requests) and returns what call_meta returns, a MetaResult per request, keyed as the
caller keyed them:

1. Each request is checked as call_meta checks it, and its worst case reserved in the shared ledger at the
   batch price, as its own row marked `batch`. A request the run's cap cannot hold is not sent in this wave.
2. One batch is sent; its custom_ids are pickfit's own ("r<n>"), mapped back to the caller's keys, since
   results come back in any order.
3. The batch is polled until it has ended. Past `max_wait_s` it is canceled: what finished is still used.
4. A request that succeeded is settled at half its tokens' price and traced like a call_meta call. One that
   errored, expired or was canceled was not billed: its reservation is released and it is sent again
   through call_meta, the plain API. So is one a safety classifier declined, since a batch request cannot
   carry `fallbacks` (it was billed, and is settled).
5. Requests the cap held back go in a next wave once the first has settled (worst cases are far above what
   calls cost), until all are sent or a wave sends none.

Only Claude models, and only on Anthropic's own API: the hackathon's providers have no batch API, and Amazon
Bedrock has neither Message Batches nor a batch tier for these models (PICKFIT_CLAUDE_VIA does not move a batch,
nor the requests sent again after one, which need the direct API's fallback model).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pickfit import anthropic_messages
from pickfit.env import require_env
from pickfit.ledger import BudgetExceeded, Ledger, default_ledger, taipei_now
from pickfit.meta import (
    CLIENT_TIMEOUT_S,
    DEFAULT_PROVIDER,
    PROVIDERS,
    Endpoint,
    MetaResult,
    Price,
    Usage,
    _append_trace,
    _check_policy,
    _parse_output,
    _read_result,
    _runs_dir,
    build_request,
    call_meta,
    cost_usd,
    estimate_cost,
    price_for,
    provider_for,
    request_hash,
    resolve_model,
)

DISCOUNT = 0.5  # every token of a batch request: input, output, cache reads and writes
POLL_S = 60.0
MAX_WAIT_S = 24 * 3600.0  # the API's own limit; past it a batch's open requests expire anyway
CANCEL_WAIT_S = 600.0  # after a cancel, how long to wait for the batch to end


@dataclass
class BatchRequest:
    """One call_meta call, to be sent in a batch. `key` is the caller's own name for it."""

    key: str
    endpoint: Endpoint
    body: dict[str, Any]
    stage: str
    max_output_tokens: int
    model: str | None = None
    reasoning_effort: str = "minimal"
    output_model: type[BaseModel] | None = None
    scope: str | None = None
    scope_cap_usd: float | None = None
    public_data_only: bool = True


@dataclass
class BatchOutcome:
    """What became of one request: its result (as call_meta's), or why there is none."""

    key: str
    result: MetaResult | None = None
    error: str | None = None
    via: str = "batch"  # "batch", "resent" (the plain API answered it) or "none"


@dataclass
class _Prepared:
    request: BatchRequest
    custom_id: str
    model: str
    price: Price
    wire: dict[str, Any]  # call_meta's request body (Chat or Responses)
    params: dict[str, Any]  # the Messages request
    plan: anthropic_messages.Plan
    estimate: float
    row: int
    hash: str


@dataclass
class BatchReport:
    """Per wave: the batch's id, how many requests it held and how each ended."""

    waves: list[dict[str, Any]] = field(default_factory=list)


def batch_client() -> Any:
    """Anthropic's SDK with the key from the environment and pickfit's own base URL. Its retries stay on: polling
    and reading results are safe to repeat; creating a batch is sent with retries off (create())."""
    import anthropic

    info = PROVIDERS[DEFAULT_PROVIDER]
    return anthropic.Anthropic(api_key=require_env(info.key_env), base_url=info.base_url, timeout=CLIENT_TIMEOUT_S)


def _to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    return obj.to_dict(mode="json") if hasattr(obj, "to_dict") else obj.model_dump(mode="json")


def _prepare(req: BatchRequest, custom_id: str, *, run_id: str | None, ledger: Ledger) -> _Prepared:
    """call_meta's checks and request, as a Messages request, with its worst case reserved at the batch price.
    Raises BudgetExceeded (nothing reserved) when the cap cannot hold it, ValueError for what no batch takes."""
    model = resolve_model(req.model)
    provider = provider_for(model)
    if provider != DEFAULT_PROVIDER:
        raise ValueError(f"{model} is not a Claude model: only Anthropic's API takes message batches")
    _check_policy(provider, model, req.public_data_only, req.reasoning_effort, req.body, req.max_output_tokens)
    price = price_for(provider, model)
    wire = build_request(req.endpoint, model, req.body, req.max_output_tokens, req.reasoning_effort)
    params, plan = anthropic_messages.to_request(req.endpoint, wire, fallbacks=False)  # batches take no fallbacks
    estimate = estimate_cost(price, wire, req.max_output_tokens) * DISCOUNT
    row = ledger.reserve(estimate, run_id=run_id, stage=req.stage, scope=req.scope, provider=provider, model=model,
                         scope_cap_usd=req.scope_cap_usd, batch=True)
    return _Prepared(req, custom_id, model, price, wire, params, plan, estimate, row,
                     request_hash(provider, req.endpoint, wire))


def _result(p: _Prepared, raw: dict[str, Any], usage: Usage | None, cost: float) -> MetaResult:
    read = _read_result(p.request.endpoint, raw)
    parsed, parse_error = _parse_output(read["text"], p.request.output_model)
    return MetaResult(provider=DEFAULT_PROVIDER, model=p.model, endpoint=p.request.endpoint, usage=usage,
                      cost_usd=cost, response_id=raw.get("id"), cache_hit=False, attempts=1, request_hash=p.hash,
                      raw=raw, parsed=parsed, parse_error=parse_error, **read)


def _trace(runs: Path, p: _Prepared, run_id: str | None, batch_id: str, **fields: Any) -> None:
    _append_trace(runs, {"run_id": run_id, "stage": p.request.stage, "scope": p.request.scope,
                         "provider": DEFAULT_PROVIDER, "model": p.model, "endpoint": p.request.endpoint,
                         "request_hash": p.hash, "reasoning_effort": p.request.reasoning_effort,
                         "max_output_tokens": p.request.max_output_tokens, "attempt": 1,
                         "reserved_usd": round(p.estimate, 6), "batch": batch_id, **fields}, [])


def _wait(client: Any, batch_id: str, *, poll_s: float, max_wait_s: float, sleep: Callable[[float], None],
          clock: Callable[[], float], log: Callable[[str], None]) -> dict[str, Any]:
    """The batch once it has ended; canceled first when it runs past max_wait_s."""
    began = clock()
    canceled_at: float | None = None
    while True:
        batch = _to_dict(client.messages.batches.retrieve(batch_id))
        if batch.get("processing_status") == "ended":
            return batch
        waited = clock() - began
        if canceled_at is None and waited >= max_wait_s:
            log(f"msg_batch: {batch_id} still running after {waited / 60:.0f} min: canceling it")
            client.messages.batches.cancel(batch_id)
            canceled_at = clock()
        elif canceled_at is not None and clock() - canceled_at >= CANCEL_WAIT_S:
            raise TimeoutError(f"batch {batch_id} did not end after it was canceled")
        sleep(poll_s)


def _send_wave(prepared: list[_Prepared], *, client: Any, ledger: Ledger, runs: Path, run_id: str | None,
               poll_s: float, max_wait_s: float, sleep: Callable[[float], None], clock: Callable[[], float],
               log: Callable[[str], None]) -> tuple[str, dict[str, BatchOutcome], list[_Prepared]]:
    """One batch: (its id, the outcomes it settled, the requests to send again through the plain API)."""
    requests = [{"custom_id": p.custom_id, "params": p.params} for p in prepared]
    try:
        # Not retried by the SDK: a create that timed out may have made a batch, and a second one bills twice.
        once = client.with_options(max_retries=0) if hasattr(client, "with_options") else client
        batch = _to_dict(once.messages.batches.create(requests=requests))
    except BaseException:
        for p in prepared:  # refused or never sent: nothing was billed
            ledger.release(p.row)
        raise
    batch_id = str(batch.get("id"))
    log(f"msg_batch: {batch_id} · {len(prepared)} request(s) sent")
    by_id = {p.custom_id: p for p in prepared}
    outcomes: dict[str, BatchOutcome] = {}
    again: list[_Prepared] = []
    try:
        _wait(client, batch_id, poll_s=poll_s, max_wait_s=max_wait_s, sleep=sleep, clock=clock, log=log)
    except BaseException:
        for p in prepared:  # it may still finish and bill: keep the worst case, as call_meta does
            ledger.settle(p.row, p.estimate, status="unknown")
        raise
    for item in client.messages.batches.results(batch_id):
        entry = _to_dict(item)
        p = by_id.pop(str(entry.get("custom_id")), None)
        if p is None:
            continue
        result = entry.get("result") or {}
        kind = result.get("type")
        if kind != "succeeded":
            ledger.release(p.row, status=f"batch_{kind or 'missing'}")
            error = (result.get("error") or {}).get("error") or result.get("error") or {}
            _trace(runs, p, run_id, batch_id, status="error", error={"type": f"batch_{kind}",
                                                                      "message": str(error)[:1000]})
            again.append(p)
            continue
        message = _to_dict(result.get("message") or {})
        raw = anthropic_messages.from_message(message, p.plan)
        usage = Usage.from_raw(raw)
        cost = cost_usd(p.price, usage) * DISCOUNT if usage else p.estimate
        ledger.settle(p.row, cost, tokens=asdict(usage) if usage else None, response_id=raw.get("id"),
                      status="settled" if usage else "no_usage")
        out = _result(p, raw, usage, cost)
        _trace(runs, p, run_id, batch_id, status="ok", http_status=200, response_id=raw.get("id"),
               usage=asdict(usage) if usage else None, cost_usd=round(cost, 8), finish=out.status)
        if message.get("stop_reason") == "refusal":  # no fallback model in a batch: the plain API has one
            again.append(p)
            continue
        outcomes[p.request.key] = BatchOutcome(p.request.key, out)
    for p in by_id.values():  # never reported: not billed
        ledger.release(p.row, status="batch_missing")
        again.append(p)
    return batch_id, outcomes, again


def run(requests: Iterable[BatchRequest], *, run_id: str | None = None, client: Any = None,
        ledger: Ledger | None = None, runs_dir: Path | str | None = None, resend: bool = True,
        resend_client: Any = None, poll_s: float = POLL_S, max_wait_s: float = MAX_WAIT_S,
        sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] = print, report: BatchReport | None = None) -> dict[str, BatchOutcome]:
    """Send `requests` as message batches and wait for them; {key: outcome} for every request.

    resend: a request the batch did not answer (errored, expired, canceled, declined) goes to call_meta,
    the plain API, with `resend_client` as its client (default: call_meta's own).
    """
    requests = list(requests)
    keys = [r.key for r in requests]
    if len(set(keys)) != len(keys):
        raise ValueError("every batch request needs its own key")
    ledger = ledger or default_ledger()
    runs = _runs_dir(runs_dir)
    client = client if client is not None else batch_client()
    report = report if report is not None else BatchReport()
    outcomes: dict[str, BatchOutcome] = {}
    pending = requests
    counter = 0
    while pending:
        prepared: list[_Prepared] = []
        held: list[BatchRequest] = []
        for req in pending:
            counter += 1
            try:
                prepared.append(_prepare(req, f"r{counter}", run_id=run_id, ledger=ledger))
            except BudgetExceeded as err:
                held.append(req)
                outcomes[req.key] = BatchOutcome(req.key, error=f"budget: {err}", via="none")
            except ValueError as err:  # this request can never be sent: say so, send the rest
                outcomes[req.key] = BatchOutcome(req.key, error=f"{type(err).__name__}: {err}", via="none")
        if not prepared:
            break  # the cap holds none of what is left
        batch_id, settled, again = _send_wave(prepared, client=client, ledger=ledger, runs=runs, run_id=run_id,
                                              poll_s=poll_s, max_wait_s=max_wait_s, sleep=sleep, clock=clock,
                                              log=log)
        outcomes.update(settled)
        for p in again:
            outcomes[p.request.key] = _resend(p.request, run_id=run_id, ledger=ledger, runs_dir=runs_dir,
                                              client=resend_client) if resend else \
                BatchOutcome(p.request.key, error="the batch did not answer it", via="none")
        report.waves.append({"batch_id": batch_id, "sent": len(prepared), "answered": len(settled),
                             "resent": len(again) if resend else 0, "held_back": len(held),
                             "at": taipei_now().isoformat(timespec="seconds")})
        log(f"msg_batch: {batch_id} · {len(settled)} answered, {len(again)} not"
            f"{' (sent again through the plain API)' if again and resend else ''}"
            f"{f', {len(held)} held back by the cap for the next wave' if held else ''}")
        pending = held
    return outcomes


def _resend(req: BatchRequest, *, run_id: str | None, ledger: Ledger, runs_dir: Path | str | None,
            client: Any) -> BatchOutcome:
    """One request the batch did not answer, through call_meta (retries, fallbacks, the full price)."""
    try:
        result = call_meta(req.endpoint, req.body, stage=req.stage, public_data_only=req.public_data_only,
                           max_output_tokens=req.max_output_tokens, model=req.model, provider=DEFAULT_PROVIDER,
                           reasoning_effort=req.reasoning_effort, scope=req.scope, scope_cap_usd=req.scope_cap_usd,
                           run_id=run_id, output_model=req.output_model, cache=False, client=client, ledger=ledger,
                           runs_dir=runs_dir)
    except Exception as err:  # noqa: BLE001 - one request's failure is reported, the rest stand
        return BatchOutcome(req.key, error=f"{type(err).__name__}: {str(err)[:300]}", via="none")
    return BatchOutcome(req.key, result, via="resent")
