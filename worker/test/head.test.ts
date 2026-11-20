/** HEAD is GET without the body, on every page and the JSON check (link checkers and uptime monitors send it). */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Env } from '../src/env.ts';
import { makeWorker } from '../src/worker.ts';
import { fixtureIndex, makeD1 } from './helpers.ts';

function site() {
  const d1 = makeD1();
  let modelCalls = 0;
  const worker = makeWorker(fixtureIndex(), {
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

const PAGES = ['/', '/agents', '/how', '/browse', '/about', '/compare', '/compare?tools=fixture-llm-runner,fixture-chat-tui', '/submit', '/tool/fixture-llm-runner', '/no-such-page', '/tool/no-such-tool'];
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

test('HEAD on /search and /mcp keeps their own answers', async () => {
  const s = site();
  assert.equal((await s.send('HEAD', '/search', 'text/html')).status, (await s.send('GET', '/search', 'text/html')).status);
  assert.notEqual((await s.send('HEAD', '/mcp', 'application/json')).status, 200);
});
