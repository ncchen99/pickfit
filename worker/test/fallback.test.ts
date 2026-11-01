/**
 * When Meta still answers 404 after the retry, the same match request goes
 * once to Muse Spark Open on Baseten; the response and the events row say so.
 * Any other failure, or no Baseten key, degrades to rules as before.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { findSoftware, type FindInput } from '../src/find.ts';
import { BASETEN_BASE_URL, costUsd, MATCH_MODEL, META_BASE_URL, OPEN_MODEL } from '../src/meta.ts';
import { answer, harness, metaResponse, USAGE, type FakeFetch } from './helpers.ts';

const MAC_OFFLINE: FindInput = { need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true };
const ONE_CALL_USD = costUsd({
  input_tokens: USAGE.input_tokens,
  cached_tokens: USAGE.input_tokens_details.cached_tokens,
  output_tokens: USAGE.output_tokens,
  reasoning_tokens: USAGE.output_tokens_details.reasoning_tokens,
});
const MODEL_NOT_FOUND = {
  error: {
    message: 'The model `muse-spark-1.3` does not exist or you do not have access to it.',
    type: 'invalid_request_error',
    code: 'model_not_found',
  },
};

const status = (code: number, body: unknown = { error: { code: 'x' } }) => () => Response.json(body, { status: code });
const notFound = status(404, MODEL_NOT_FOUND);
const ok = () => metaResponse(answer());

/** Fake model APIs answering `replies` in turn, at the real 25 s timeout, with a Baseten key unless `key` is null. */
function fallingBack(replies: FakeFetch[], key: string | null = 'baseten-key') {
  let n = 0;
  const h = harness((body) => replies[Math.min(n++, replies.length - 1)](body), { timeoutMs: 25_000, fallbackApiKey: key });
  h.deps.sleep = async () => {};
  const row = async () => {
    await h.settle();
    const r = h.sqlite
      .prepare("SELECT matched_by, degraded, degraded_reason, model_attempts, model_statuses, meta_cost_usd, need FROM events WHERE type = 'find'")
      .get() as any;
    return { ...r, need: JSON.parse(r.need) };
  };
  const budget = () => ({ ...(h.sqlite.prepare('SELECT calls, cost_usd FROM meta_budget').get() as any) });
  return { h, row, budget };
}

test('404 after the retry: Muse Spark Open on Baseten answers the same request, and everything says so', async () => {
  const { h, row, budget } = fallingBack([notFound, notFound, ok]);
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 3);
  const [meta1, meta2, open] = h.requests;
  assert.equal(meta1.url, `${META_BASE_URL}/responses`);
  assert.equal(meta2.url, `${META_BASE_URL}/responses`);
  assert.equal(open.url, `${BASETEN_BASE_URL}/responses`);
  assert.equal((open.init.headers as Record<string, string>).authorization, 'Bearer baseten-key');
  // Only the model changes: the prompt, cards and schema are Meta's request as sent.
  assert.equal(meta1.body.model, MATCH_MODEL);
  assert.equal(open.body.model, OPEN_MODEL);
  assert.deepEqual({ ...open.body, model: MATCH_MODEL }, meta1.body);

  assert.equal(out.matched_by, OPEN_MODEL);
  assert.equal(out.fallback_model, OPEN_MODEL);
  assert.equal(out.degraded, false);
  assert.equal(out.degraded_reason, null);
  assert.equal(out.model_attempts, 3);
  assert.deepEqual(
    out.picks.map((p) => p.slug),
    ['fixture-llm-runner', 'fixture-chat-tui'],
  );
  for (const pick of out.picks) {
    assert.match(pick.how_we_know, /Chosen by Muse Spark Open \(meta-models\/muse-spark-open-1026, Meta's open-weight model served by Baseten/);
    assert.doesNotMatch(pick.how_we_know, /1\.3/);
  }

  const r = await row();
  assert.equal(r.matched_by, OPEN_MODEL);
  assert.equal(r.degraded, 0);
  assert.equal(r.model_attempts, 3);
  assert.equal(r.model_statuses, '[404,404,200]');
  assert.deepEqual(r.need.model_fallback, { model: OPEN_MODEL, status: 200 });
  // Meta's 404s cost nothing; Baseten's answer counts against the same daily cap, once.
  assert.ok(Math.abs(r.meta_cost_usd - ONE_CALL_USD) < 1e-9);
  const b = budget();
  assert.equal(b.calls, 1);
  assert.ok(Math.abs(b.cost_usd - ONE_CALL_USD) < 1e-9);
});

test('404 after the retry and Baseten fails too: rules, with the fallback still on record and no second Baseten try', async () => {
  const { h, row, budget } = fallingBack([notFound, notFound, status(503)]);
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 3);
  assert.equal(h.requests[2].url, `${BASETEN_BASE_URL}/responses`);
  assert.equal(out.matched_by, 'rules');
  assert.equal(out.degraded, true);
  assert.equal(out.degraded_reason, 'model_http');
  assert.equal(out.model_http_status, 503);
  assert.equal(out.model_attempts, 3);
  assert.equal(out.fallback_model, OPEN_MODEL);
  assert.ok(out.picks.length > 0);
  for (const pick of out.picks) assert.match(pick.how_we_know, /no model was used/);

  const r = await row();
  assert.equal(r.matched_by, 'rules');
  assert.equal(r.degraded_reason, 'model_http');
  assert.equal(r.model_statuses, '[404,404,503]');
  assert.deepEqual(r.need.model_fallback, { model: OPEN_MODEL, status: 503 });
  assert.equal(r.meta_cost_usd, 0);
  assert.equal(budget().cost_usd, 0);
});

test("Baseten's answer goes through the same guard: a bad answer falls back to rules", async () => {
  const { h, row } = fallingBack([notFound, notFound, () => metaResponse('not json')]);
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(out.matched_by, 'rules');
  assert.equal(out.degraded_reason, 'model_bad_output');
  assert.equal(out.fallback_model, OPEN_MODEL);
  const r = await row();
  assert.ok(Math.abs(r.meta_cost_usd - ONE_CALL_USD) < 1e-9); // Baseten answered, so it is charged
});

test('without a Baseten key a 404 degrades to rules as before', async () => {
  const { h, row } = fallingBack([notFound, notFound, ok], null);
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 2);
  assert.equal(out.matched_by, 'rules');
  assert.equal(out.degraded_reason, 'model_http');
  assert.equal(out.model_http_status, 404);
  assert.equal(out.fallback_model, null);
  const r = await row();
  assert.equal(r.model_statuses, '[404,404]');
  assert.equal(r.need.model_fallback, undefined);
});

test('only a 404 goes to Baseten: 503s, 400s and timeouts degrade as before', async () => {
  // The last case: a 404 whose retry answered 503 is not "still 404".
  for (const replies of [[status(503), status(503)], [status(400)], [notFound, status(503)]]) {
    const { h } = fallingBack(replies);
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    assert.ok(h.requests.every((r) => r.url.startsWith(META_BASE_URL)), `no Baseten request after ${out.model_http_status}`);
    assert.equal(out.fallback_model, null);
    assert.equal(out.matched_by, 'rules');
  }
  const timedOut = fallingBack([
    () => {
      throw new DOMException('timed out', 'TimeoutError');
    },
  ]);
  const out = await findSoftware(MAC_OFFLINE, timedOut.h.deps);
  assert.equal(out.degraded_reason, 'model_timeout');
  assert.equal(out.fallback_model, null);
  assert.equal(timedOut.h.requests.length, 1);
});

test('a 404 is the last answer even after a 429 retry: that goes to Baseten too', async () => {
  const { h } = fallingBack([status(429), notFound, ok]);
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 3);
  assert.equal(out.matched_by, OPEN_MODEL);
});

test('no fallback with less than 10 s of the timeout left', async () => {
  const { h } = fallingBack([notFound, notFound, ok]);
  // Each Meta 404 takes 8 s: after two, 9 s of the 25 s are left.
  let ms = Date.parse('2026-10-30T12:00:00Z');
  h.deps.now = () => new Date(ms);
  const fetch = h.deps.fetch!;
  h.deps.fetch = (async (url: string, init: RequestInit) => {
    ms += 8_000;
    return fetch(url, init);
  }) as typeof globalThis.fetch;
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 2);
  assert.equal(out.matched_by, 'rules');
  assert.equal(out.fallback_model, null);
});
