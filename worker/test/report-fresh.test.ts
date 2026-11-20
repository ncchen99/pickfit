/** F1: "It didn't install for me" on the tool page. D1/D2: how old a check is, and a release after it. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Env } from '../src/env.ts';
import { findSoftware } from '../src/find.ts';
import { freshness, releasedAfter } from '../src/freshness.ts';
import { loadCatalog, type Entry } from '../src/catalog.ts';
import { installGuide } from '../src/install.ts';
import { makeWorker } from '../src/worker.ts';
import { answer, fixtureIndex, harness, makeD1, modelResponse } from './helpers.ts';

function site(index: unknown = fixtureIndex()) {
  const d1 = makeD1();
  const worker = makeWorker(index, { now: () => new Date('2026-10-30T12:00:00Z') });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const send = (path: string, init: RequestInit = {}) =>
    worker.fetch(new Request(`http://127.0.0.1:8787${path}`, { ...init, headers: { accept: 'text/html', ...(init.headers ?? {}) } }), { DB: d1.db } as Env, ctx);
  return { send, sqlite: d1.sqlite };
}

const post = (body: Record<string, string>, origin = 'http://127.0.0.1:8787') => ({
  method: 'POST',
  headers: { 'content-type': 'application/x-www-form-urlencoded', origin, 'cf-connecting-ip': '203.0.113.5', 'x-pickfit-reporter': 'dev' },
  body: new URLSearchParams(body).toString(),
  redirect: 'manual' as const,
});

test('the tool page offers the report form, and a report is stored for people, not counted, then thanked', async () => {
  const s = site();
  const page = await (await s.send('/tool/fixture-llm-runner')).text();
  assert.match(page, /<details class="report" id="report"><summary class="small">It didn’t install for me<\/summary><form method="post" action="\/report"/);
  assert.match(page, /<option value="macos">macOS<\/option><option value="linux">Linux<\/option>|<option value="linux">Linux<\/option><option value="macos">macOS<\/option>/);

  const res = await s.send('/report', post({ slug: 'fixture-llm-runner', os: 'linux', error: 'error: /home/alice/x not found' }));
  assert.equal(res.status, 303);
  assert.equal(res.headers.get('location'), '/tool/fixture-llm-runner?reported=1#report');
  const row = s.sqlite.prepare("SELECT * FROM events WHERE type = 'outcome'").get() as any;
  assert.deepEqual([row.slug, row.os, row.stage, row.success, row.rec_id, row.client], ['fixture-llm-runner', 'linux', 'installed', 0, null, 'web']);
  assert.ok(!String(row.error_excerpt).includes('alice'), 'the excerpt is scrubbed like an MCP report');
  assert.equal((s.sqlite.prepare('SELECT count(*) AS n FROM reverify_queue').get() as any).n, 0);

  const thanked = await (await s.send('/tool/fixture-llm-runner?reported=1')).text();
  assert.match(thanked, /Thanks, it’s recorded/);
  assert.doesNotMatch(thanked, /<details class="report"/);
});

test('a report from another site, for an unknown tool or OS, is refused', async () => {
  const s = site();
  assert.equal((await s.send('/report', post({ slug: 'fixture-llm-runner', os: 'linux' }, 'https://evil.example'))).status, 403);
  assert.equal((await s.send('/report', post({ slug: 'nope', os: 'linux' }))).status, 400);
  assert.equal((await s.send('/report', post({ slug: 'fixture-llm-runner', os: 'beos' }))).status, 400);
  assert.equal((s.sqlite.prepare("SELECT count(*) AS n FROM events WHERE type = 'outcome'").get() as any).n, 0);
});

test('freshness: a release after the check warns; an old check says how old; a fresh one says nothing', () => {
  const now = new Date('2026-11-20T00:00:00Z');
  assert.match(freshness('2026-10-28T08:00:00Z', '2026-11-10', now).warning ?? '', /new release came out on 2026-11-10, after pickfit's check on 2026-10-28/);
  assert.equal(freshness('2026-10-28T08:00:00Z', '2026-10-20', now).warning, null);
  assert.equal(freshness('2026-10-28T08:00:00Z', null, now).age_days, 22);
  assert.match(freshness('2026-07-01T00:00:00Z', null, now).warning ?? '', /142 days ago/);
  assert.equal(releasedAfter(null, '2026-11-10'), null);
});

test('find_software picks and the install guide carry it; the tool page shows the day and the warning', async () => {
  const index = structuredClone(fixtureIndex()) as { entries: Entry[] };
  index.entries.find((e) => e.slug === 'fixture-llm-runner')!.last_release = '2026-10-29';
  const h = harness(() => modelResponse(answer()));
  h.deps.catalog = loadCatalog(index);
  const out = await findSoftware({ need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true }, h.deps);
  const pick = out.picks.find((p) => p.slug === 'fixture-llm-runner')!;
  assert.equal(pick.freshness.age_days, 2);
  assert.match(pick.freshness.warning ?? '', /new release came out on 2026-10-29/);
  assert.match(installGuide(h.deps.catalog, { slug: 'fixture-llm-runner', os: 'macos' }).warnings.join(' '), /new release came out on 2026-10-29.*report_outcome/);

  const page = await (await site(index).send('/tool/fixture-llm-runner')).text();
  assert.match(page, /<p class="run-age small quiet">pickfit ran these steps on 28 Oct 2026 \(/);
  assert.match(page, /<p class="run-stale small" role="note">.*A new release came out on 2026-10-29/);
});
