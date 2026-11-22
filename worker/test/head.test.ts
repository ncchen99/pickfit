/** HEAD is GET without the body, on every page and the JSON check (link checkers and uptime monitors send it). */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Env } from '../src/env.ts';
import { makeWorker } from '../src/worker.ts';
import { fixtureIndex, makeD1 } from './helpers.ts';

function site(index: unknown = fixtureIndex()) {
  const d1 = makeD1();
  let modelCalls = 0;
  const worker = makeWorker(index, {
    fetch: (async () => {
      modelCalls++;
      throw new Error('no model call expected');
    }) as unknown as typeof fetch,
    now: () => new Date('2026-10-30T12:00:00Z'),
  });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const send = (method: string, path: string, accept: string) =>
    worker.fetch(new Request(`http://127.0.0.1:8787${path}`, { method, headers: { accept } }), { DB: d1.db, ANTHROPIC_API_KEY: 'k' } as Env, ctx);
  return { send, modelCalls: () => modelCalls };
}

const PAGES = ['/', '/?lang=zh-TW', '/agents', '/how', '/browse', '/about', '/compare', '/compare?tools=fixture-llm-runner,fixture-chat-tui', '/submit', '/tool/fixture-llm-runner', '/tool/fixture-llm-runner?lang=zh-TW', '/no-such-page', '/tool/no-such-tool'];
// Headers that differ between two responses on their own (a fresh nonce in the CSP).
const SAME = (headers: Headers) => [...headers].filter(([k]) => k !== 'content-security-policy');

test('HEAD answers every page with the status and headers of GET, and no body', async () => {
  const s = site();
  for (const path of PAGES) {
    for (const accept of ['text/html,application/xhtml+xml,*/*;q=0.8', '*/*']) {
      const got = await s.send('GET', path, accept);
      const head = await s.send('HEAD', path, accept);
      assert.equal(head.status, got.status, `${path} (${accept})`);
      assert.deepEqual(SAME(head.headers), SAME(got.headers), `${path} (${accept})`);
      assert.equal(head.body, null, `${path}: no body`);
      await got.text();
    }
  }
  assert.equal(s.modelCalls(), 0);
});

test('HEAD / is 200 for a browser and for a link checker (the JSON check), as GET is', async () => {
  const s = site();
  const browser = await s.send('HEAD', '/?ref=producthunt&utm_source=producthunt', 'text/html');
  assert.equal(browser.status, 200);
  assert.match(browser.headers.get('content-type')!, /^text\/html/);
  const checker = await s.send('HEAD', '/', '*/*');
  assert.equal(checker.status, 200);
  assert.match(checker.headers.get('content-type')!, /^application\/json/);
});

test('HEAD on the home page and a broken tool page (brief 15 brand) matches GET, whose body carries the new facts', async () => {
  const index = structuredClone(fixtureIndex()) as { built_at: string; entries: { slug: string; standing?: string; standing_note?: string; used_by?: string }[] };
  index.built_at = '2026-11-29T12:00:00Z';
  Object.assign(index.entries.find((e) => e.slug === 'fixture-llm-runner')!, { standing: 'broken', standing_note: 'The install script now 404s.', used_by: 'agent' });
  const s = site(index);
  for (const [path, says] of [
    ['/', /verified in the last 30 days.*class="agent-entry"|class="agent-entry".*verified in the last 30 days/s],
    ['/tool/fixture-llm-runner', /class="broken-banner".*<dt>For<\/dt><dd>Agents<\/dd>/s],
  ] as const) {
    const got = await s.send('GET', path, 'text/html');
    const head = await s.send('HEAD', path, 'text/html');
    assert.equal(head.status, 200, path);
    assert.equal(head.status, got.status, path);
    assert.deepEqual(SAME(head.headers), SAME(got.headers), path);
    assert.equal(head.body, null, `${path}: no body`);
    assert.match(await got.text(), says, path);
  }
  assert.equal(s.modelCalls(), 0);
});

test('HEAD on /search and /mcp keeps their own answers', async () => {
  const s = site();
  assert.equal((await s.send('HEAD', '/search', 'text/html')).status, (await s.send('GET', '/search', 'text/html')).status);
  assert.notEqual((await s.send('HEAD', '/mcp', 'application/json')).status, 200);
});
