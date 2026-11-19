"""pickfit.msg_batch with a fake Message Batches client: nothing leaves the process."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

import pickfit.env
from pickfit import msg_batch
from pickfit.ledger import Ledger
from pickfit.meta import PRICES, PROD_MODEL, Usage, cost_usd
from pickfit.msg_batch import BatchRequest
from batch_fakes import FakeBatches, PlainClient, fake_client, succeeded, user_text


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    for name in ("PICKFIT_MODE", "PICKFIT_CACHE", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path / "runs"))


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite")


def rows(ledger: Ledger) -> list[dict[str, Any]]:
    conn = sqlite3.connect(ledger.path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM calls ORDER BY id")]
    finally:
        conn.close()


def traces(tmp_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for path in sorted((tmp_path / "runs" / "traces").glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()]


class Answer(BaseModel):
    zh: str


def req(key: str, text: str = "Translate this.", **kw: Any) -> BatchRequest:
    body = {"messages": [{"role": "system", "content": "You translate."}, {"role": "user", "content": text}]}
    return BatchRequest(key=key, endpoint="chat", body=body, stage="translate", max_output_tokens=2000, **kw)


def run(requests: list[BatchRequest], batches: FakeBatches, ledger: Ledger, **kw: Any):
    return msg_batch.run(requests, client=fake_client(batches), ledger=ledger, run_id="run-1", sleep=lambda s: None,
                         log=lambda line: None, **kw)


def test_a_batch_is_sent_polled_and_read_back_by_key_at_half_price(ledger: Ledger, tmp_path: Path):
    batches = FakeBatches(lambda params: succeeded(json.dumps({"zh": user_text(params)})),
                          statuses=["in_progress", "in_progress", "ended"])
    out = run([req("a", "one"), req("b", "two", output_model=Answer)], batches, ledger)

    assert batches.polls == 3 and len(batches.created) == 1
    sent = batches.created[0]
    assert [r["custom_id"] for r in sent] == ["r1", "r2"]  # pickfit's ids; the caller's keys come back below
    params = sent[0]["params"]
    assert params["model"] == PROD_MODEL  # no model named: prod
    assert "fallbacks" not in params and "betas" not in params  # a batch request cannot carry them
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert (out["a"].via, out["a"].result.text) == ("batch", '{"zh": "one"}')
    assert out["b"].result.parsed == Answer(zh="two")

    full = cost_usd(PRICES[("anthropic", PROD_MODEL)], Usage(input_tokens=200, output_tokens=50))
    recorded = rows(ledger)
    assert [(r["batch"], r["status"]) for r in recorded] == [(1, "settled"), (1, "settled")]
    assert all(r["cost_usd"] == pytest.approx(full / 2) and r["input_tokens"] == 200 for r in recorded)
    assert all(r["reserved_usd"] > r["cost_usd"] for r in recorded)
    lines = traces(tmp_path)
    assert [(t["stage"], t["batch"], t["status"]) for t in lines] == [("translate", "msgbatch_1", "ok")] * 2


def test_errored_and_expired_requests_are_released_and_sent_again_through_the_plain_api(ledger: Ledger):
    def answer(params: dict[str, Any]) -> dict[str, Any]:
        said = user_text(params)
        if said == "bad":
            return {"type": "errored", "error": {"type": "error", "error": {"type": "api_error", "message": "x"}}}
        if said == "late":
            return {"type": "expired"}
        return succeeded("fine")

    plain = PlainClient()
    out = run([req("ok", "good"), req("e", "bad"), req("x", "late")], FakeBatches(answer), ledger,
              resend_client=plain)
    assert (out["ok"].via, out["e"].via, out["x"].via) == ("batch", "resent", "resent")
    assert out["e"].result.text == out["x"].result.text == "again" and len(plain.calls) == 2
    recorded = rows(ledger)
    batch_rows = [r for r in recorded if r["batch"]]
    assert sorted(r["status"] for r in batch_rows) == ["batch_errored", "batch_expired", "settled"]
    assert all(r["cost_usd"] == 0 for r in batch_rows if r["status"] != "settled")  # not billed
    plain_rows = [r for r in recorded if not r["batch"]]
    assert len(plain_rows) == 2 and all(r["status"] == "settled" for r in plain_rows)
    settled = next(r for r in batch_rows if r["status"] == "settled")
    assert plain_rows[0]["cost_usd"] == pytest.approx(2 * settled["cost_usd"])  # the plain API: full price


def test_without_resend_an_unanswered_request_is_reported_not_sent(ledger: Ledger):
    out = run([req("x")], FakeBatches(lambda params: {"type": "canceled"}), ledger, resend=False)
    assert out["x"].result is None and out["x"].via == "none" and "did not answer" in out["x"].error


def test_a_declined_answer_is_billed_and_asked_again_where_a_fallback_model_can_take_it(ledger: Ledger):
    plain = PlainClient("answered by the fallback")
    out = run([req("r")], FakeBatches(lambda params: succeeded("", stop="refusal")), ledger, resend_client=plain)
    assert out["r"].via == "resent" and out["r"].result.text == "answered by the fallback"
    batch_row = next(r for r in rows(ledger) if r["batch"])
    assert batch_row["status"] == "settled" and batch_row["cost_usd"] > 0


def test_a_batch_past_its_wait_is_canceled_and_what_finished_still_counts(ledger: Ledger):
    clock = iter(range(0, 10_000, 100))
    batches = FakeBatches(lambda params: succeeded("done") if "first" in json.dumps(params) else {"type": "canceled"},
                          statuses=["in_progress"])
    plain = PlainClient()
    out = run([req("a", "first"), req("b", "second")], batches, ledger, max_wait_s=250,
              clock=lambda: float(next(clock)), resend_client=plain)
    assert batches.canceled == ["msgbatch_1"]
    assert (out["a"].via, out["b"].via) == ("batch", "resent")


def test_the_cap_holds_back_what_it_cannot_reserve_until_the_first_wave_settles(ledger: Ledger):
    one = msg_batch._prepare(req("probe"), "r0", run_id="probe", ledger=ledger).estimate
    batches = FakeBatches(lambda params: succeeded("ok"))
    out = run([req("a", scope="translate:run-1", scope_cap_usd=one * 1.5),
               req("b", scope="translate:run-1", scope_cap_usd=one * 1.5)], batches, ledger)
    assert [len(c) for c in batches.created] == [1, 1]  # two waves: the second once the first cost little
    assert out["a"].result is not None and out["b"].result is not None


def test_a_cap_too_small_for_any_request_sends_nothing(ledger: Ledger):
    batches = FakeBatches(lambda params: succeeded("ok"))
    out = run([req("a", scope="s", scope_cap_usd=1e-6)], batches, ledger)
    assert batches.created == [] and out["a"].via == "none" and out["a"].error.startswith("budget")


def test_a_model_without_a_batch_api_is_refused_and_the_rest_are_sent(ledger: Ledger):
    batches = FakeBatches(lambda params: succeeded("ok"))
    out = run([req("meta", model="muse-spark-1.3"), req("claude")], batches, ledger)
    assert "not a Claude model" in out["meta"].error and out["claude"].result is not None
    assert len(batches.created[0]) == 1


def test_a_batch_the_api_refuses_releases_every_reservation(ledger: Ledger):
    with pytest.raises(RuntimeError):
        run([req("a"), req("b")], FakeBatches(lambda params: succeeded("ok"), fail_create=True), ledger)
    assert [(r["status"], r["cost_usd"]) for r in rows(ledger)] == [("error", 0.0), ("error", 0.0)]


def test_keys_must_be_unique(ledger: Ledger):
    with pytest.raises(ValueError, match="own key"):
        run([req("a"), req("a")], FakeBatches(lambda params: succeeded("ok")), ledger)


def test_an_old_ledger_file_gets_the_batch_column_and_its_rows_read_as_plain_calls(tmp_path: Path):
    path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE calls (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, day TEXT NOT NULL,"
                 " budget TEXT NOT NULL, run_id TEXT, stage TEXT, scope TEXT, provider TEXT, model TEXT,"
                 " attempt INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL, reserved_usd REAL NOT NULL DEFAULT 0,"
                 " cost_usd REAL NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0,"
                 " cached_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,"
                 " reasoning_tokens INTEGER NOT NULL DEFAULT 0, web_searches INTEGER NOT NULL DEFAULT 0,"
                 " cache_hit INTEGER NOT NULL DEFAULT 0, response_id TEXT)")
    conn.execute("INSERT INTO calls (ts, day, budget, status, cost_usd) VALUES ('t', 'd', 'pipeline', 'settled', 1.5)")
    conn.commit()
    conn.close()
    ledger = Ledger(path)
    Ledger(path)  # a second open finds the column there
    ledger.reserve(0.1, batch=True)
    assert [(r["batch"], r["cost_usd"]) for r in rows(ledger)] == [(0, 1.5), (1, 0.0)]
