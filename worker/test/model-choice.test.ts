/** A bench run may name the model (bench/capability.ts --model-id); the product never does and stays on MATCH_MODEL. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { modelArg } from '../bench/model-arg.ts';
import { settings, type Env } from '../src/env.ts';
import { findSoftware } from '../src/find.ts';
import { costUsd, estimateCostUsd, MATCH_MODEL, MODEL_PRICES } from '../src/meta.ts';
import { answer, harness, isKeywordsCall, modelResponse, USAGE_READ } from './helpers.ts';

test('--model-id: default MATCH_MODEL, a priced model taken as given, anything else refused', () => {
  assert.equal(MATCH_MODEL, 'claude-opus-5-5');
  assert.equal(modelArg(['idx', 'q', '--model']), MATCH_MODEL);
  assert.equal(modelArg(['idx', 'q', '--model-id', 'claude-sonnet-5-5', '--cap', '6']), 'claude-sonnet-5-5');
  assert.throws(() => modelArg(['--model-id', 'claude-haiku-5-5']), /no price for it/);
  assert.throws(() => modelArg(['--model-id', '--cap']), /needs a model id/);
});

test('Sonnet 5.5 is counted at its own price: half of Opus 5.5 for input and output, the same cache read', () => {
  const usage = { input_tokens: 10_000, cached_tokens: 0, cache_write_tokens: 0, output_tokens: 1_000 };
  assert.equal(costUsd(usage, 'claude-sonnet-5-5') * 2, costUsd(usage));
  assert.equal(MODEL_PRICES['claude-sonnet-5-5'].cacheRead, MODEL_PRICES['claude-opus-5-5'].cacheRead);
  assert.equal(estimateCostUsd(30_000, 8_000, 'claude-sonnet-5-5') * 2, estimateCostUsd(30_000, 8_000));
});

test('the named model goes to both calls, matched_by and the recorded spend; no Env setting can change it', async () => {
  const h = harness((body) => modelResponse(isKeywordsCall(body) ? { keywords: ['x'] } : answer()), { matchModel: 'claude-sonnet-5-5' });
  const out = await findSoftware({ need: 'run a language model offline on my laptop', os: 'macos' }, h.deps);
  await h.settle();
  assert.ok(h.requests.length >= 1);
  assert.ok(h.requests.every((r) => r.body.model === 'claude-sonnet-5-5'));
  assert.equal(out.matched_by, 'claude-sonnet-5-5');
  const spent = (h.sqlite.prepare('SELECT sum(cost_usd) AS usd FROM meta_budget').get() as any).usd;
  assert.ok(Math.abs(spent - costUsd(USAGE_READ, 'claude-sonnet-5-5') * h.requests.length) < 1e-9, String(spent));

  const product = settings({ ANTHROPIC_API_KEY: 'k', MATCH_MODEL: 'claude-sonnet-5-5' } as unknown as Env);
  assert.equal(product.matchModel, undefined);
  const plain = harness(() => modelResponse(answer()));
  await findSoftware({ need: 'run a language model offline on my laptop', os: 'macos' }, plain.deps);
  assert.equal(plain.requests[0].body.model, MATCH_MODEL);
});
