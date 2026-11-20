/** U4: web searches shared in D1 across instances (Cloud Run scales to zero), keyed by the search and the data. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Env } from '../src/env.ts';
import { makeWorker } from '../src/worker.ts';
import { answer, fixtureIndex, makeD1, modelResponse } from './helpers.ts';

const FORM = { need: 'run a language model offline on my laptop', os: 'macos', offline: '1' };

function instance(d1: ReturnType<typeof makeD1>, index: unknown = fixtureIndex(), status = 200) {
  const pending: Promise<unknown>[] = [];
  let calls = 0;
  const worker = makeWorker(index, {
    fetch: (async () => {
      calls++;
      return status === 200 ? modelResponse(answer()) : Response.json({}, { status });
    }) as unknown as typeof fetch,
    now: () => new Date('2026-10-30T12:00:00Z'),
  });
  const ctx = { waitUntil: (p: Promise<unknown>) => void pending.push(p), passThroughOnException() {} } as unknown as ExecutionContext;
  const search = async () => {
    const res = await worker.fetch(
      new Request('http://127.0.0.1:8787/search', {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded', origin: 'http://127.0.0.1:8787', 'x-pickfit-fragment': '1', 'cf-connecting-ip': '203.0.113.9' },
        body: new URLSearchParams(FORM).toString(),
      }),
      { DB: d1.db, ANTHROPIC_API_KEY: 'k' } as Env,
      ctx,
    );
    await Promise.all(pending);
    return res.text();
  };
  return { search, calls: () => calls };
}

test('another instance answers the same search from D1, with no model call', async () => {
  const d1 = makeD1();
  const a = instance(d1);
  await a.search();
  assert.equal(a.calls(), 1);
  const b = instance(d1);
  const html = await b.search();
  assert.equal(b.calls(), 0);
  assert.match(html, /Shown from the same search made on 30 Oct 2026, on the same data\./);
  assert.equal((d1.sqlite.prepare('SELECT count(*) AS n FROM search_cache').get() as any).n, 1);
});

test('new data is a new key: the old answer is not shown', async () => {
  const d1 = makeD1();
  await instance(d1).search();
  const changed = { ...(fixtureIndex() as object), data_sha256: 'f'.repeat(64) };
  const b = instance(d1, changed);
  await b.search();
  assert.equal(b.calls(), 1);
});

test('a degraded answer is not shared, and a D1 without the table is a miss, not an error', async () => {
  const d1 = makeD1();
  await instance(d1, fixtureIndex(), 503).search();
  assert.equal((d1.sqlite.prepare('SELECT count(*) AS n FROM search_cache').get() as any).n, 0);

  const bare = makeD1();
  bare.sqlite.exec('DROP TABLE search_cache');
  const c = instance(bare);
  const html = await c.search();
  assert.equal(c.calls(), 1);
  assert.doesNotMatch(html, /Something went wrong/);
});

test('rows older than 7 days are not read, and are deleted on the next write', async () => {
  const d1 = makeD1();
  d1.sqlite.prepare("INSERT INTO search_cache (key, result, created_at) VALUES ('old', '{}', '2026-10-01T00:00:00.000Z')").run();
  await instance(d1).search();
  const keys = (d1.sqlite.prepare('SELECT key FROM search_cache').all() as any[]).map((r) => r.key);
  assert.ok(!keys.includes('old'));
  assert.equal(keys.length, 1);
});
