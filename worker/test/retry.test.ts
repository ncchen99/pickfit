/**
 * One retry of the model call after a transient Meta error (429, 5xx, 404
 * "model not found"), inside META_TIMEOUT_MS, charged once, and recorded in
 * the response and the events row.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { findSoftware, type FindInput } from '../src/find.ts';
import { costUsd, isTransient, MATCH_MODEL, retryAfterMs } from '../src/meta.ts';
import { answer, harness, metaResponse, USAGE, type FakeFetch } from './helpers.ts';

const MAC_OFFLINE: FindInput = { need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true };
/** What one fake Meta answer (helpers USAGE) costs. */
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

const status = (code: number, body: unknown = { error: { code: 'x' } }, headers: HeadersInit = {}) => () =>
  Response.json(body, { status: code, headers });
const ok = () => metaResponse(answer());

/** A harness whose fake Meta answers with `replies` in turn, at the real 25 s timeout, recording each wait. */
function retrying(...replies: FakeFetch[]) {
  let n = 0;
  const h = harness((body) => replies[Math.min(n++, replies.length - 1)](body), { timeoutMs: 25_000 });
  const waits: number[] = [];
  h.deps.sleep = async (ms) => void waits.push(ms);
  const row = async () => {
    await h.settle();
    return {
      ...(h.sqlite
        .prepare("SELECT degraded, degraded_reason, model_attempts, model_statuses, meta_cost_usd FROM events WHERE type = 'find'")
        .get() as any),
    };
  };
  const budget = () => ({ ...(h.sqlite.prepare('SELECT calls, cost_usd FROM meta_budget').get() as any) });
  return { h, waits, row, budget };
}

test('a 503 is retried once; the answer that follows is used and charged once', async () => {
  const { h, waits, row, budget } = retrying(status(503), ok);
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 2);
  assert.equal(out.matched_by, MATCH_MODEL);
  assert.equal(out.degraded, false);
  assert.equal(out.model_attempts, 2);
  assert.equal(out.model_http_status, null);
  assert.equal(waits.length, 1);
  assert.ok(waits[0] >= 200 && waits[0] <= 800, `jittered wait ${waits[0]}`);
  assert.deepEqual(h.requests[0].body, h.requests[1].body); // the same request again

  const logged = await row();
  assert.deepEqual([logged.degraded, logged.degraded_reason, logged.model_attempts], [0, null, 2]);
  assert.deepEqual(JSON.parse(logged.model_statuses), [503, 200]);
  assert.equal(logged.meta_cost_usd, ONE_CALL_USD);
  assert.deepEqual(budget(), { calls: 1, cost_usd: ONE_CALL_USD });
});

test('429, other 5xx and a 404 "model not found" are retried', async () => {
  for (const first of [
    status(429),
    status(500),
    status(502),
    status(504),
    status(404, MODEL_NOT_FOUND),
    status(404, { error: { message: 'Model not found' } }),
  ]) {
    const { h } = retrying(first, ok);
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    assert.equal(h.requests.length, 2);
    assert.equal(out.matched_by, MATCH_MODEL);
  }
});

test('a retry that fails too degrades to rules with the last status', async () => {
  const { h, row, budget } = retrying(status(404, MODEL_NOT_FOUND), status(503));
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 2); // never a third
  assert.equal(out.matched_by, 'rules');
  assert.equal(out.degraded, true);
  assert.equal(out.degraded_reason, 'model_http');
  assert.equal(out.model_http_status, 503);
  assert.equal(out.model_attempts, 2);
  assert.ok(out.picks.length > 0);

  const logged = await row();
  assert.deepEqual([logged.degraded, logged.degraded_reason, logged.model_attempts], [1, 'model_http', 2]);
  assert.deepEqual(JSON.parse(logged.model_statuses), [404, 503]);
  assert.deepEqual(budget(), { calls: 1, cost_usd: 0 }); // no usage came back, nothing charged
});

test('no retry for 400, 401, 403, a plain 404 or a network error', async () => {
  for (const [label, first, code] of [
    ['400', status(400), 400],
    ['401', status(401, { error: { message: 'Invalid API key' } }), 401],
    ['403', status(403), 403],
    ['404 route', status(404, { error: { message: 'Not Found' } }), 404],
    ['network', () => Promise.reject(new TypeError('fetch failed')), null],
  ] as const) {
    const { h, waits, row } = retrying(first, ok);
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    assert.equal(h.requests.length, 1, label);
    assert.equal(waits.length, 0, label);
    assert.equal(out.degraded_reason, code === null ? 'model_network' : 'model_http', label);
    assert.equal(out.model_http_status, code, label);
    assert.equal(out.model_attempts, 1, label);
    assert.deepEqual(JSON.parse((await row()).model_statuses), [code], label);
  }
});

test('no retry when too little of META_TIMEOUT_MS is left', async () => {
  let t = Date.parse('2026-10-30T12:00:00Z');
  const { h, waits } = retrying(() => {
    t += 16_000; // a slow 503: 9 s of 25 s left
    return status(503)();
  }, ok);
  h.deps.now = () => new Date(t);
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 1);
  assert.equal(waits.length, 0);
  assert.equal(out.degraded_reason, 'model_http');
  assert.equal(out.model_http_status, 503);
  assert.equal(out.model_attempts, 1);

  // The same slow 503 with time to spare (a longer timeout) is retried.
  t = Date.parse('2026-10-30T12:00:00Z');
  const roomy = retrying(() => {
    t += 16_000;
    return status(503)();
  }, ok);
  roomy.h.deps.now = () => new Date(t);
  roomy.h.deps.settings = { ...roomy.h.deps.settings, timeoutMs: 30_000 };
  assert.equal((await findSoftware(MAC_OFFLINE, roomy.h.deps)).model_attempts, 2);
});

test('a short Retry-After is honored; a long one means degrade now', async () => {
  for (const [headers, wait] of [
    [{ 'retry-after': '2' }, 2000],
    [{ 'retry-after-ms': '1500' }, 1500],
    [{ 'retry-after': '0' }, null], // falls back to the jittered wait
  ] as const) {
    const { h, waits } = retrying(status(429, {}, headers), ok);
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    assert.equal(out.model_attempts, 2);
    if (wait === null) assert.ok(waits[0] >= 200 && waits[0] <= 800);
    else assert.deepEqual(waits, [wait]);
  }
  const { h, waits } = retrying(status(429, {}, { 'retry-after': '30' }), ok);
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 1);
  assert.equal(waits.length, 0);
  assert.equal(out.model_http_status, 429);
});

test('an answer is never retried: bad output, an incomplete answer, or every pick rejected', async () => {
  const rejected = answer({
    picks: [{ slug: 'fixture-llm-runner', fit: 'x', reasons: [{ claim: 'Paid', field: 'pricing', value: 'paid' }], tradeoffs: [], vs_well_known: null }],
  });
  for (const [first, reason] of [
    [() => metaResponse('this is not json'), 'model_bad_output'],
    [() => metaResponse(answer(), { status: 'incomplete' }), 'model_incomplete'],
    [() => metaResponse(rejected), 'guard_rejected_all'],
  ] as const) {
    const { h, budget } = retrying(first, ok);
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    await h.settle();
    assert.equal(h.requests.length, 1, reason);
    assert.equal(out.degraded_reason, reason);
    assert.equal(out.model_attempts, 1);
    assert.equal(out.model_http_status, null);
    assert.deepEqual(budget(), { calls: 1, cost_usd: ONE_CALL_USD }, reason); // Meta answered, so it was billed
  }
});

test('the model unused: zero attempts in the response and the log', async () => {
  const h = harness(null, { modelEnabled: false });
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  await h.settle();
  assert.equal(out.model_attempts, 0);
  assert.equal(out.model_http_status, null);
  const logged = h.sqlite.prepare("SELECT degraded_reason, model_attempts, model_statuses FROM events WHERE type = 'find'").get() as any;
  assert.deepEqual({ ...logged }, { degraded_reason: 'model_off', model_attempts: 0, model_statuses: '[]' });
});

test('isTransient and retryAfterMs', () => {
  const body = JSON.stringify(MODEL_NOT_FOUND);
  assert.ok(isTransient(404, body));
  assert.ok(isTransient(404, '{"detail":"Model muse-spark-1.3 not found"}'));
  assert.ok(!isTransient(404, '{"error":{"message":"Not Found"}}'));
  assert.ok(isTransient(429, '') && isTransient(500, '') && isTransient(599, ''));
  for (const code of [400, 401, 403, 409, 422]) assert.ok(!isTransient(code, body), String(code));

  const now = Date.parse('2026-10-30T12:00:00Z');
  const h = (init: Record<string, string>) => new Headers(init);
  assert.equal(retryAfterMs(h({}), now), null);
  assert.equal(retryAfterMs(h({ 'retry-after': '3' }), now), 3000);
  assert.equal(retryAfterMs(h({ 'retry-after-ms': '250', 'retry-after': '3' }), now), 250);
  assert.equal(retryAfterMs(h({ 'retry-after': 'Fri, 30 Oct 2026 12:00:04 GMT' }), now), 4000);
  assert.equal(retryAfterMs(h({ 'retry-after': 'soon' }), now), null);
});

test('META_VIA=openrouter sends the same request to OpenRouter, pinned to Meta, with the OpenRouter key', async () => {
  const h = harness(() => ok(), { via: 'openrouter', apiKey: 'or-key' });
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(out.matched_by, MATCH_MODEL);
  const sent = h.requests.at(-1)!;
  assert.equal(sent.url, 'https://openrouter.ai/api/v1/responses');
  assert.equal(sent.body.model, 'meta/muse-spark-1.3');
  assert.deepEqual(sent.body.provider, { order: ['meta'], allow_fallbacks: false, data_collection: 'deny' });
  assert.equal(sent.body.store, false);
  assert.equal(new Headers(sent.init.headers).get('authorization'), 'Bearer or-key');
});

test('on OpenRouter the cost is the one it reports, not the cached-token estimate', async () => {
  const h = harness(() => metaResponse(answer(), { usage: { ...USAGE, cost: 0.0123 } }), { via: 'openrouter', apiKey: 'or-key' });
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(out.matched_by, MATCH_MODEL);
  await h.settle();
  const spent = h.sqlite.prepare('SELECT SUM(cost_usd) AS usd FROM meta_budget').get() as { usd: number };
  assert.ok(Math.abs(spent.usd - 0.0123) < 1e-9, String(spent.usd));
});
