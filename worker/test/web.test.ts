/**
 * The product web page: GET / for browsers, POST /search over the MCP's own
 * findSoftware and installGuide, and the web-only limits (rate limit, web
 * Meta cap, cache). The MCP path and the JSON health check must not change.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Env } from '../src/env.ts';
import type { FindOutput, PickOut } from '../src/find.ts';
import { runDay } from '../src/evidence.ts';
import { catalogStats, EMPTY_FORM, esc, guiSentence, levelLabel, ranSentence, renderResults, safeUrl, yourSystem, type FormValues } from '../src/page.ts';
import { BODY_MAX_BYTES, MAX_IN_FLIGHT, SEARCHES_PER_MINUTE, visitorKey } from '../src/web.ts';
import { makeWorker } from '../src/worker.ts';
import { answer, fixtureCatalog, fixtureIndex, makeD1, metaResponse } from './helpers.ts';

const MAC_LLM = { need: 'run a language model offline on my laptop', os: 'macos', offline: '1' };
const NOW = new Date('2026-10-30T12:00:00Z');

type Fake = (body: any) => Response | Promise<Response>;

function site(env: Partial<Env> = {}, fake: Fake = () => metaResponse(answer())) {
  env = { MODEL_API_KEY: 'test-key', ...env };
  const d1 = makeD1();
  const pending: Promise<unknown>[] = [];
  const metaCalls: any[] = [];
  const worker = makeWorker(fixtureIndex(), {
    fetch: (async (_url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      metaCalls.push(body);
      return fake(body);
    }) as unknown as typeof fetch,
    now: () => NOW,
  });
  const ctx = { waitUntil: (p: Promise<unknown>) => void pending.push(p), passThroughOnException() {} };
  const send = (request: Request) => worker.fetch(request, { DB: d1.db, ...env } as Env, ctx as unknown as ExecutionContext);
  const search = (form: Record<string, string>, headers: Record<string, string> = {}) =>
    send(
      new Request('http://127.0.0.1:8787/search', {
        method: 'POST',
        headers: {
          'content-type': 'application/x-www-form-urlencoded',
          origin: 'http://127.0.0.1:8787',
          'x-pickfit-fragment': '1',
          'cf-connecting-ip': '203.0.113.7',
          ...headers,
        },
        body: new URLSearchParams(form).toString(),
      }),
    );
  let id = 0;
  const mcpFind = async (args: object) => {
    const response = await send(
      new Request('http://127.0.0.1:8787/mcp', {
        method: 'POST',
        headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25' },
        body: JSON.stringify({ jsonrpc: '2.0', id: ++id, method: 'tools/call', params: { name: 'find_software', arguments: args } }),
      }),
    );
    const text = await response.text();
    const data = text.startsWith('{') ? text : text.split('\n').find((l) => l.startsWith('data: '))!.slice(6);
    return JSON.parse(data).result.structuredContent as FindOutput;
  };
  return { send, search, mcpFind, metaCalls, sqlite: d1.sqlite, settle: () => Promise.all(pending) };
}

const events = (s: ReturnType<typeof site>, type: string) =>
  s.sqlite.prepare('SELECT * FROM events WHERE type = ?').all(type) as any[];

test('GET / is the page for a browser; anything else still gets the JSON health check', async () => {
  const s = site();
  const page = await s.send(new Request('http://127.0.0.1:8787/', { headers: { accept: 'text/html,application/xhtml+xml,*/*;q=0.8' } }));
  assert.equal(page.status, 200);
  assert.match(page.headers.get('content-type')!, /^text\/html/);
  assert.equal(page.headers.get('vary'), 'Accept');
  const html = await page.text();
  assert.match(html, /<form id="search"[^>]*method="post" action="\/search#results"/);
  assert.match(html, /claude mcp add --transport http pickfit http:\/\/127\.0\.0\.1:8787\/mcp/);
  // Inline script and style run only under this response's nonce.
  const nonce = /script-src 'nonce-([0-9a-f]+)'/.exec(page.headers.get('content-security-policy')!)![1];
  assert.ok(html.includes(`<script nonce="${nonce}">`) && html.includes(`<style nonce="${nonce}">`));
  assert.match(page.headers.get('content-security-policy')!, /default-src 'none'.*form-action 'self'.*frame-ancestors 'none'/);

  for (const accept of [undefined, '*/*', 'application/json']) {
    const res = await s.send(new Request('http://127.0.0.1:8787/', accept ? { headers: { accept } } : {}));
    assert.match(res.headers.get('content-type')!, /application\/json/);
    assert.deepEqual(Object.keys(await res.json()).sort(), ['data_sha256', 'entries', 'index_built_at', 'match_mode', 'mcp', 'name', 'tools']);
  }
  assert.equal(s.metaCalls.length, 0);
});

test('the page never echoes a query string: request URLs reach Workers logs', async () => {
  const s = site();
  const html = await (await s.send(new Request('http://127.0.0.1:8787/?need=secret-words&os=linux', { headers: { accept: 'text/html' } }))).text();
  assert.ok(!html.includes('secret-words'));
  assert.ok(html.includes('<input type="radio" name="os" value="" checked>Any OS'));
  assert.equal(s.metaCalls.length, 0);
});

test('WEB_SEARCH=off: / stays JSON and /search does not exist', async () => {
  const s = site({ WEB_SEARCH: 'off' });
  const res = await s.send(new Request('http://127.0.0.1:8787/', { headers: { accept: 'text/html' } }));
  assert.match(res.headers.get('content-type')!, /application\/json/);
  assert.equal((await s.search(MAC_LLM)).status, 404);
  assert.equal(s.metaCalls.length, 0);
});

test('a search is find_software plus get_install_guide: reasons, verification, steps', async () => {
  const s = site();
  const res = await s.search(MAC_LLM);
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('cache-control'), 'no-store');
  const html = await res.text();
  await s.settle();

  // One muse-spark-1.3 call, with the same request find_software sends.
  assert.equal(s.metaCalls.length, 1);
  assert.equal(s.metaCalls[0].model, 'muse-spark-1.3');
  assert.match(JSON.stringify(s.metaCalls[0].input), /run a language model offline on my laptop/);
  assert.match(html, /\d+ verified tools meet your conditions; Meta’s muse-spark-1\.3 picked 2\. Code checked every reason/);

  // Ranked picks with the fit, cited reasons, tradeoffs, best_free and the comparison.
  const [first, second] = html.split('<article class="pick"').slice(1);
  assert.match(first, /Fixture LLM Runner/);
  assert.match(first, /Serves a local model offline through an OpenAI-compatible API\./);
  assert.match(first, /<summary>Runs offline on your machine<svg[^>]*>.*?<\/svg><\/summary><p class="cite">From its profile: <code>processing<\/code> is “local”/);
  assert.match(first, /Needs 8 GB of RAM/);
  assert.match(first, /Best free option<\/span>/);
  assert.match(first, /Hidden gem/);
  assert.match(first, /Lighter than Ollama/);
  // Verified by hand on macOS arm64: the user's OS, so the steps are the macOS ones.
  assert.match(first, /<li class="rf rf-yes" data-tip="Verified on your OS"><svg class="os os-macos"[^>]*>.*?<\/svg>macOS arm64<\/li><li class="rf">.*?Installed by hand<\/li>/);
  assert.match(first, /<span class="sr">Checked on <\/span>28 Oct 2026/);
  assert.ok(!first.includes('mine-yes'), 'a run on your OS is said by its mark, not again in words');
  assert.match(first, /<details class="install" open><summary><span>Install steps that worked on <span class="sys"><svg class="os os-macos"[^>]*>.*?<\/svg>macOS arm64/);
  assert.match(first, /brew install fixture\/tap\/fixture-llm-runner/);
  assert.match(first, /You do these yourself<\/h4><ul><li>Allow incoming connections/);
  assert.match(first, /The output should contain “fixture-llm-runner 0\.4\.1”/);
  assert.match(first, /fixture-llm-runner serve --model tiny-test/);
  // Only run on Linux: said plainly, with the Linux steps labelled as such.
  assert.match(second, /Fixture Chat TUI/);
  assert.match(second, /mine-no">.*Not verified on your system: it ran on Linux x86_64, and pickfit hasn’t run it on macOS yet\./);
  assert.match(second, /These steps ran on Linux x86_64\. pickfit hasn’t run them on macOS, so expect differences\./);
  assert.match(second, /<details class="install"><summary><span>Install steps that worked on <span class="sys"><svg class="os os-linux"[^>]*>.*?<\/svg>Linux x86_64/);
  assert.ok(!second.includes('Best free option'));
  // find.ts's agent-facing tradeoff is not repeated next to the record that says it.
  assert.ok(!second.includes('Verified on linux only'));
  assert.match(second, /Alpha maturity/);

  // The log: one find event labelled web; showing the guides is not logged as a pick.
  const finds = events(s, 'find');
  assert.equal(finds.length, 1);
  assert.equal(finds[0].client, 'web');
  assert.equal(finds[0].matched_by, 'muse-spark-1.3');
  assert.ok(!JSON.stringify(finds[0]).includes('on my laptop'));
  assert.equal(events(s, 'install_guide').length, 0);
});

test('without an OS the steps shown are the ones pickfit ran, and the badge asks for the OS', async () => {
  const s = site();
  const html = await (await s.search({ need: 'run a language model offline on my laptop' })).text();
  const second = html.split('<article class="pick"')[2];
  assert.match(second, /<p class="small quiet">Choose your OS above to see whether it ran on your system\./);
  assert.match(second, /Install steps that worked on <span class="sys"><svg class="os os-linux"[^>]*>.*?<\/svg>Linux x86_64/);
  assert.ok(!second.includes('expect differences'));
});

test('well_known_option is set apart, labelled not verified, and never looks like a pick', async () => {
  const why = 'Ollama is free, runs models offline on macOS and needs no API setup.';
  const s = site({}, () => metaResponse(answer({ well_known_name: 'Ollama', well_known_why: why })));
  const html = await (await s.search({ ...MAC_LLM, free_only: '1' })).text();
  const [picks, outside] = html.split('<aside class="outside"');
  assert.ok(outside, 'the well-known option is rendered');
  assert.match(outside, /^ aria-label="Not verified by pickfit"><h3>Also consider Ollama, not verified by pickfit<\/h3>/);
  assert.ok(outside.includes(esc(why)));
  assert.match(outside, /pickfit has not installed it, has no install guide for it/);
  // No rank, badges, test record, install steps or links: nothing a verified pick has.
  for (const mark of ['class="pick"', 'data-ui', 'badge', 'class="record"', 'class="install"', '<a ']) {
    assert.ok(!outside.includes(mark), `well-known option has ${mark}`);
  }
  assert.ok(!picks.includes('Also consider'));
});

test('nothing fits: the coverage note, no picks', async () => {
  const s = site({}, () => metaResponse(answer({ picks: [], best_free_slug: null })));
  const html = await (await s.search(MAC_LLM)).text();
  assert.match(html, /<h2 class="results-title">Nothing fits yet<\/h2>/);
  assert.match(html, /None of the \d+ verified tools that meet the conditions fits this request\./);
  assert.ok(!html.includes('<article class="pick"'));
});

test('a model failure says the results are ranked by rules', async () => {
  const s = site({}, () => Response.json({ error: 'bad request' }, { status: 400 }));
  const html = await (await s.search(MAC_LLM)).text();
  // Said once, in the status list under Fitz, before any pick.
  assert.match(html, /<li class="st st-busy" role="status"><svg[^>]*>.*?<\/svg><span><strong>Ranked without the model this time\.<\/strong>/);
  assert.ok(html.indexOf('st-busy') < html.indexOf('<article class="pick"'));
  assert.match(html, /\d+ verified tools meet your conditions; these are ranked by rules, without a model\./);
  assert.ok(html.includes('<article class="pick"'));
});

test('web searches stop calling Meta at WEB_DAILY_CAP_USD; agents keep the rest of the daily cap', async () => {
  const s = site({ WEB_DAILY_CAP_USD: '2' });
  s.sqlite.prepare('INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?, 1, 2.0)').run('2026-10-30');
  const html = await (await s.search(MAC_LLM)).text();
  assert.equal(s.metaCalls.length, 0);
  assert.match(html, /<strong>Model matching paused until 00:00 UTC\.<\/strong>/);
  assert.ok(html.includes('<article class="pick"'), 'still shows rules results');
  await s.settle();
  assert.equal(events(s, 'find')[0].degraded_reason, 'over_budget');

  // The MCP's own cap is untouched: $2 spent of $3, so an agent still gets the model.
  const out = await s.mcpFind({ need: 'run a language model offline on my laptop', os: 'macos' });
  assert.equal(out.matched_by, 'muse-spark-1.3');
  assert.equal(s.metaCalls.length, 1);
});

test('the rate limit answers busy before any Meta call', async () => {
  const keys: string[] = [];
  const limiter = { limit: async ({ key }: { key: string }) => (keys.push(key), { success: false }) };
  const s = site({ WEB_RATE_LIMITER: limiter as unknown as RateLimit });
  const res = await s.search(MAC_LLM);
  assert.equal(res.status, 429);
  assert.equal(res.headers.get('retry-after'), '60');
  assert.match(await res.text(), /Busy: too many searches from here/);
  assert.equal(s.metaCalls.length, 0);
  await s.settle();
  assert.equal(events(s, 'find').length, 0);
  // The limiter sees a hash, never the address.
  assert.match(keys[0], /^[0-9a-f]{32}$/);
  assert.ok(!keys[0].includes('203.0.113.7'));
});

test('without the binding, an in-memory count limits each visitor', async () => {
  const s = site();
  for (let i = 0; i < SEARCHES_PER_MINUTE; i++) {
    assert.equal((await s.search({ ...MAC_LLM, need: `run a language model offline, try ${i}` })).status, 200);
  }
  assert.equal((await s.search({ ...MAC_LLM, need: 'one more search' })).status, 429);
  // Another visitor is counted apart.
  assert.equal((await s.search({ ...MAC_LLM, need: 'one more search' }, { 'cf-connecting-ip': '198.51.100.2' })).status, 200);
  assert.equal(s.metaCalls.length, SEARCHES_PER_MINUTE + 1);
});

test('identical web searches share one model call; MCP calls are never cached', async () => {
  const s = site();
  await s.search(MAC_LLM);
  const again = await (await s.search({ ...MAC_LLM, need: '  Run a language model   OFFLINE on my laptop ' })).text();
  assert.equal(s.metaCalls.length, 1);
  assert.match(again, /Shown from the same search made in the last few minutes/);
  // Different conditions are a different search.
  await s.search({ ...MAC_LLM, os: 'linux' });
  assert.equal(s.metaCalls.length, 2);

  await s.mcpFind({ need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true });
  await s.mcpFind({ need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true });
  assert.equal(s.metaCalls.length, 4);
});

test('a degraded answer is not cached, so the next identical search tries the model again', async () => {
  let status = 503;
  const s = site({}, () => (status === 200 ? metaResponse(answer()) : Response.json({}, { status })));
  await s.search(MAC_LLM);
  status = 200;
  const html = await (await s.search(MAC_LLM)).text();
  assert.ok(!html.includes('Ranked without the model'));
  assert.equal(s.metaCalls.length, 3); // 503, retried 503, then 200
});

test('another site cannot post to /search, and a bad need is refused before Meta', async () => {
  const s = site();
  assert.equal((await s.search(MAC_LLM, { origin: 'https://evil.example' })).status, 403);
  assert.equal((await s.search(MAC_LLM, { host: 'evil.example' })).status, 403);
  const short = await s.search({ need: 'ab' });
  assert.equal(short.status, 400);
  assert.match(await short.text(), /Describe what you need/);
  const long = await s.search({ need: 'x'.repeat(5000) });
  assert.equal(long.status, 400, 'over 500 characters is a 400 that says so, never a silent cut');
  assert.match(await long.text(), /That is 5,000 characters\./);
  const huge = await s.search({ need: 'x'.repeat(BODY_MAX_BYTES + 10) });
  assert.equal(huge.status, 413);
  const declared = await s.send(
    new Request('http://127.0.0.1:8787/search', {
      method: 'POST',
      headers: { origin: 'http://127.0.0.1:8787', 'content-length': String(10 * 1024 * 1024), 'x-pickfit-fragment': '1' },
      body: 'need=short',
    }),
  );
  assert.equal(declared.status, 413, 'a declared length over the limit is refused before reading');
  assert.equal(s.metaCalls.length, 0);
  // GET /search goes back to the page; other methods are refused.
  assert.equal((await s.send(new Request('http://127.0.0.1:8787/search'))).status, 303);
  assert.equal((await s.send(new Request('http://127.0.0.1:8787/search', { method: 'PUT' }))).status, 405);
});

test('without the script, the form posts and gets the whole page back', async () => {
  const s = site();
  const res = await s.search({ ...MAC_LLM, need: 'run a language model offline <for "me">' }, { 'x-pickfit-fragment': '' });
  const html = await res.text();
  assert.match(html, /^<!doctype html>/);
  assert.ok(html.includes('offline &lt;for &quot;me&quot;&gt;</textarea>'));
  assert.ok(html.includes('<input type="radio" name="os" value="macos" checked>'));
  assert.match(html, /<body class="is-results" data-served="1">/);
  assert.match(html, /<section id="results"[^>]*><div class="res-head"><div class="says"><img [^>]*><div class="bubble"><h2 class="results-title">2 tools fit your need<\/h2><p class="match-line">/);
  const nonce = /script-src 'nonce-([0-9a-f]+)'/.exec(res.headers.get('content-security-policy')!)![1];
  assert.ok(html.includes(`<script nonce="${nonce}">`));
});

test('before any search the page shows real catalog runs, never invented ones', async () => {
  const s = site();
  const html = await (await s.send(new Request('http://127.0.0.1:8787/', { headers: { accept: 'text/html' } }))).text();
  // How Fitz picks: four short steps, each with Fitz's own state.
  const how = html.slice(html.indexOf('<section id="how"'), html.indexOf('<section id="recent"'));
  assert.equal(how.split('<li class="stage">').length - 1, 4);
  // A README the run corrected: a real pitfall from the index, the newest hidden gem that has one.
  const fix = html.slice(html.indexOf('<figure class="fix-card">'), html.indexOf('</figure>'));
  assert.match(fix, /<a href="\/tool\/fixture-llm-runner">Fixture LLM Runner<\/a>/);
  assert.match(fix, /<b>README said<\/b><span>make install<\/span>/);
  assert.match(fix, /<b>What worked<\/b><span>the install script/);
  // The newest runs: three rows, each a verified tool with where and when, linking to its profile.
  const runs = html.slice(html.indexOf('<ul class="runs-list">'), html.indexOf('</ul></div></section>'));
  assert.equal(runs.split('<li class="run-row">').length - 1, 3);
  assert.match(runs, /<a class="name" href="\/tool\/[a-z0-9-]+">/);
  assert.match(html, /6 of 7 tools installed and replayed, and 1 web app used in a browser\. Only those are ever suggested\./);
  // The counts in the hero are the catalog's.
  assert.match(html, /<strong>7<\/strong> READMEs read/);
  assert.equal(s.metaCalls.length, 0);
});

test('results: claim beside evidence, no rank numerals, and "built-in is enough" before the picks', async () => {
  const s = site({}, () => metaResponse(answer({ no_install_option: 'Your OS already ships a tool that does this.' })));
  const html = await (await s.search(MAC_LLM)).text();
  assert.ok(html.indexOf('You may not need to install anything') < html.indexOf('<article class="pick"'));
  assert.ok(!html.includes('class="rank"') && !html.includes('t-rank'));
  for (const pick of html.split('<article class="pick"').slice(1)) {
    // The claim and the verdict, then the stitches, the command that worked, and the record behind one expander.
    assert.match(pick, /<p class="fit">[\s\S]*<div class="glance t-glance">[\s\S]*<div class="seam" aria-hidden="true"><\/div><div class="t-install">[\s\S]*<details class="t-more">[\s\S]*<section class="record" aria-label="Test record">/);
  }
});

/** A Meta answer that arrives after a tick, so searches overlap. */
const slow = (body: () => Response = () => metaResponse(answer())) => () => new Promise<Response>((r) => setTimeout(() => r(body()), 20));

test('concurrent searches cannot spend past the web cap: each reserves its worst case first', async () => {
  const s = site({ WEB_DAILY_CAP_USD: '2' }, slow());
  s.sqlite.prepare('INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?, 1, 1.85)').run('2026-10-30');
  const pages = await Promise.all([0, 1, 2, 3].map((i) => s.search({ ...MAC_LLM, need: `run a language model offline, try ${i}` })));
  await s.settle();
  // Room for one reservation ($0.08) under $2: one Meta call, the rest ranked by rules and told why.
  assert.equal(s.metaCalls.length, 1);
  const texts = await Promise.all(pages.map((r) => r.text()));
  assert.equal(texts.filter((h) => h.includes('Model matching paused until 00:00 UTC')).length, 3);
  // Holds are released: what is left is the real cost of the one call.
  const today = s.sqlite.prepare('SELECT cost_usd, calls FROM meta_budget WHERE day = ?').get('2026-10-30') as any;
  assert.ok(Math.abs(today.cost_usd - (1.85 + 0.00605)) < 1e-9, String(today.cost_usd));
  assert.equal(today.calls, 2);
});

test('two isolates sharing one D1 still cannot pass the web cap together', async () => {
  const d1 = makeD1();
  d1.sqlite.prepare('INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?, 1, 1.85)').run('2026-10-30');
  const pending: Promise<unknown>[] = [];
  let calls = 0;
  const isolate = () =>
    makeWorker(fixtureIndex(), {
      fetch: (async () => (calls++, slow()())) as unknown as typeof fetch,
      now: () => NOW,
    });
  const ctx = { waitUntil: (p: Promise<unknown>) => void pending.push(p), passThroughOnException() {} } as unknown as ExecutionContext;
  const env = { DB: d1.db, MODEL_API_KEY: 'test-key', WEB_DAILY_CAP_USD: '2' } as Env;
  const post = (w: ReturnType<typeof makeWorker>, i: number) =>
    w.fetch(
      new Request('http://127.0.0.1:8787/search', {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded', origin: 'http://127.0.0.1:8787', 'x-pickfit-fragment': '1', 'cf-connecting-ip': `2001:db8:${i}::1` },
        body: new URLSearchParams({ ...MAC_LLM, need: `offline model, isolate search ${i}` }).toString(),
      }),
      env,
      ctx,
    );
  const [a, b] = [isolate(), isolate()];
  await Promise.all([0, 1, 2, 3, 4, 5].map((i) => post(i % 2 ? a : b, i)));
  await Promise.all(pending);
  assert.equal(calls, 1);
  const today = d1.sqlite.prepare('SELECT cost_usd FROM meta_budget WHERE day = ?').get('2026-10-30') as any;
  assert.ok(today.cost_usd <= 2, String(today.cost_usd));
});

test('the total cap stops the page too, and the notice does not promise a reset', async () => {
  const s = site({ META_TOTAL_CAP_USD: '40' });
  s.sqlite.prepare('INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?, 1, 39.99)').run('2026-10-20');
  const html = await (await s.search(MAC_LLM)).text();
  assert.equal(s.metaCalls.length, 0);
  assert.match(html, /<strong>Model matching is paused\.<\/strong> pickfit’s overall budget for Meta model calls is used up/);
  assert.ok(!html.includes('00:00 UTC'));
});

test('identical searches in flight share one model call', async () => {
  const s = site({}, slow());
  const pages = await Promise.all([1, 2, 3].map(() => s.search(MAC_LLM)));
  assert.deepEqual(pages.map((r) => r.status), [200, 200, 200]);
  assert.equal(s.metaCalls.length, 1);
  for (const r of pages) assert.match(await r.text(), /<article class="pick"/);
});

test('at most MAX_IN_FLIGHT model searches run at once in an isolate', async () => {
  const s = site({}, slow());
  const n = MAX_IN_FLIGHT + 2;
  const pages = await Promise.all(
    Array.from({ length: n }, (_, i) => s.search({ ...MAC_LLM, need: `search number ${i} offline` }, { 'cf-connecting-ip': `198.51.100.${i + 1}` })),
  );
  const statuses = pages.map((r) => r.status);
  assert.equal(statuses.filter((x) => x === 200).length, MAX_IN_FLIGHT);
  assert.equal(statuses.filter((x) => x === 503).length, 2);
  assert.equal(s.metaCalls.length, MAX_IN_FLIGHT);
  const busy = pages.find((r) => r.status === 503)!;
  assert.equal(busy.headers.get('retry-after'), '10');
  assert.match(await busy.text(), /Busy: pickfit is answering other searches/);
});

test('an IPv6 visitor is limited by its /64, not by each address', async () => {
  assert.equal(visitorKey('2001:db8::1'), '2001:0db8:0000:0000::/64');
  assert.equal(visitorKey('2001:DB8:0:0:ffff:1:2:3'), '2001:0db8:0000:0000::/64');
  assert.equal(visitorKey('2001:db8:0:1::1'), '2001:0db8:0000:0001::/64');
  assert.equal(visitorKey('::ffff:203.0.113.7'), '203.0.113.7');
  assert.equal(visitorKey('203.0.113.7'), '203.0.113.7');
  const s = site();
  for (let i = 1; i <= SEARCHES_PER_MINUTE; i++) {
    assert.equal((await s.search({ ...MAC_LLM, need: `offline model ${i}` }, { 'cf-connecting-ip': `2001:db8::${i}` })).status, 200);
  }
  assert.equal((await s.search({ ...MAC_LLM, need: 'offline model 99' }, { 'cf-connecting-ip': '2001:db8::99' })).status, 429);
  assert.equal((await s.search({ ...MAC_LLM, need: 'offline model 99' }, { 'cf-connecting-ip': '2001:db8:0:1::1' })).status, 200);
});

test('the need is counted in characters: a long CJK need is accepted, 501 characters get a 400', async () => {
  const s = site();
  const cjk = await s.search({ ...MAC_LLM, need: '我想在筆電上離線執行語言模型'.repeat(32) }); // 448 characters, about 4 KB encoded
  assert.equal(cjk.status, 200);
  assert.equal(s.metaCalls.length, 1);
  const over = await s.search({ need: '離'.repeat(501) });
  assert.equal(over.status, 400);
  assert.match(await over.text(), /That is 501 characters\./);
  assert.equal(s.metaCalls.length, 1);
});

test('a best free option outside the picks shows where it ran and whether that is your system', async () => {
  const s = site({}, () => metaResponse(answer({ picks: [answer().picks[0]], best_free_slug: 'fixture-chat-tui', best_free_reason: 'Free and local.' })));
  const html = await (await s.search(MAC_LLM)).text();
  const aside = html.slice(html.indexOf('<div class="aside best-free">'));
  assert.match(aside, /Best free option:<\/span> <a [^>]*>Fixture Chat TUI<\/a>\. Free and local\./);
  assert.match(aside, /<li class="rf rf-no" data-tip="Not your OS"><svg class="os os-linux"[^>]*>.*?<\/svg>Linux x86_64<\/li><li class="rf">.*?Replayed from scratch<\/li>/);
  assert.match(aside, /<span class="sr">Checked on <\/span>28 Oct 2026/);
  assert.match(aside, /mine-no">Not verified on your system: it ran on Linux x86_64, and pickfit hasn’t run it on macOS yet\./);
});

test('the unverified option says so in a filled line and uses plain text type, and no-JS posts land on the results', async () => {
  const s = site({}, () => metaResponse(answer({ well_known_name: 'Ollama', well_known_why: 'Ollama is free and runs models offline on macOS.' })));
  const html = await (await s.search({ ...MAC_LLM, free_only: '1' }, { 'x-pickfit-fragment': '' })).text();
  assert.match(html, /<p class="unchecked">pickfit has not installed or tested it\. There is no run record and no install guide\.<\/p>/);
  assert.match(html, /\.outside h3\{font:600 1\.1rem\/1\.35 var\(--sans\)/);
  assert.match(html, /<form id="search" class="ask-card" method="post" action="\/search#results">/);
});

// Rendering helpers, on crafted outputs.

function pick(overrides: Partial<PickOut> = {}): PickOut {
  return {
    slug: 'tool',
    name: 'Tool',
    summary: 'Does a thing.',
    fit: 'Fits.',
    why: [],
    tradeoffs: [],
    vs_well_known: null,
    platforms: ['linux'],
    pricing: 'free',
    processing: 'local',
    open_source: true,
    license: 'MIT',
    verification: { level: 'function', os: 'linux', arch: 'x86_64', method: 'sandbox', replayed: true, checked_at: '2026-10-29T08:00:00Z', verified_on_user_os: null, gui: null },
    how_we_know: 'pickfit ran it.',
    evidence_url: null,
    features: { recorded: false, checked: [], not_checked: [] },
    scores: { quality: 80, popularity: 10, treasure: false },
    repo: 'https://github.com/a/tool',
    homepage: null,
    web_app: null,
    ...overrides,
  };
}

function output(picks: PickOut[]): FindOutput {
  return {
    rec_id: 'rec_0',
    matched_by: 'muse-spark-1.3',
    degraded: false,
    degraded_reason: null,
    model_attempts: 1,
    model_http_status: null,
    considered: 4,
    picks,
    best_free: null,
    no_install_option: null,
    well_known_option: null,
    clarifying_question: null,
    coverage_note: null,
  };
}

test('render: data and model text are escaped; only http(s) links are links', () => {
  const evil = pick({
    name: '<img src=x onerror=alert(1)>',
    fit: '"><script>alert(1)</script>',
    repo: 'javascript:alert(1)',
    homepage: 'https://example.com/?q="x"',
    why: [{ claim: '<b>bold</b>', field: 'tags', value: '<i>' }],
  });
  const html = renderResults({ out: output([evil]), guides: {} }, EMPTY_FORM, fixtureCatalog());
  assert.ok(!html.includes('<img src=x') && !html.includes('<script') && !html.includes('<b>') && !html.includes('<i>'));
  assert.ok(html.split('<img ').slice(1).every((tag) => tag.startsWith('class="fitz ')), 'the only images are Fitz');
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(!html.includes('javascript:'));
  assert.ok(html.includes('href="https://example.com/?q=%22x%22"'));
  assert.equal(safeUrl('data:text/html,hi'), null);
  assert.equal(safeUrl('not a url'), null);
  assert.equal(safeUrl('http://example.com'), 'http://example.com/');
});

test('render: the your-system line covers yes, another OS, another CPU and no OS', () => {
  const form = (os: FormValues['os'], arch: FormValues['arch']): FormValues => ({ ...EMPTY_FORM, os, arch });
  const v = pick().verification;
  assert.deepEqual(yourSystem({ ...v, verified_on_user_os: true }, form('linux', 'x86_64')), {
    state: 'yes',
    text: 'Verified on your system: it ran on Linux x86_64.',
  });
  assert.equal(
    yourSystem({ ...v, verified_on_user_os: false }, form('windows', '')).text,
    'Not verified on your system: it ran on Linux x86_64, and pickfit hasn’t run it on Windows yet.',
  );
  assert.equal(
    yourSystem({ ...v, os: 'macos', arch: 'arm64', verified_on_user_os: false }, form('macos', 'x86_64')).text,
    'Not verified on your system: it ran on macOS arm64, not x86_64.',
  );
  assert.equal(yourSystem(v, EMPTY_FORM).state, 'unknown');
  assert.equal(ranSentence(v), 'pickfit installed it in a fresh Linux x86_64 sandbox and replayed the steps from scratch on 29 Oct 2026.');
  assert.equal(ranSentence({ ...v, method: 'human', os: 'macos', arch: 'arm64' }), 'pickfit installed it by hand on macOS arm64 on 29 Oct 2026.');
});

test('render: a best free option outside the picks, a no-install option and a cached note', () => {
  const out = { ...output([pick()]), best_free: { slug: 'fixture-json-query', reason: 'Free and local.' }, no_install_option: 'python3 -m json.tool is enough.' };
  const html = renderResults({ out, guides: {} }, EMPTY_FORM, fixtureCatalog(), { cached: true });
  assert.match(html, /Best free option:<\/span> <a href="\/tool\/fixture-json-query">Fixture JSON Query<\/a>\. Free and local\./);
  assert.match(html, /<div class="aside best-free">[\s\S]*?<ul class="run-facts">/);
  assert.match(html, /You may not need to install anything<\/h3><p>python3 -m json\.tool is enough\.<\/p><p class="quiet small">From Muse Spark’s general knowledge; pickfit hasn’t checked it\./);
  assert.match(html, /Shown from the same search/);
});

test('catalog stats come from the index', () => {
  assert.deepEqual(catalogStats(fixtureCatalog()), { listed: 7, verified: 7, replayed: 6, byHand: 1, gems: 1, web: 1 });
});

test('render: the offline check is shown when it failed, and said when it was never run but asked for', () => {
  const out = output([pick()]);
  const guide = (works_offline: boolean | null) => ({ verification: { works_offline }, steps: [], known_issues: [] }) as any;
  const html = (w: boolean | null, offline: boolean) =>
    renderResults({ out, guides: { tool: guide(w) } }, { ...EMPTY_FORM, offline }, fixtureCatalog());
  assert.match(html(true, false), /<li class="rf" data-tip="Its checks passed again with the network off">.*?Works offline<\/li>/);
  assert.match(html(false, false), /<li class="rf rf-no" data-tip="Its checks failed with the network off">.*?Needed the network<\/li>/);
  assert.match(html(null, true), /<li class="rf">.*?Offline not checked<\/li>/);
  assert.ok(!html(null, false).includes('network off'));
});

test('an MCP server pick shows its handshake and how to add it to an agent', async () => {
  const mcpAnswer = answer({
    need: { ...answer().need, task: 'search notes from an agent', category: 'mcp_server' },
    picks: [
      {
        slug: 'fixture-notes-mcp',
        fit: 'Lets your agent search and read your notes over MCP.',
        reasons: [{ claim: 'An MCP server', field: 'category', value: 'mcp_server' }],
        tradeoffs: [],
        vs_well_known: null,
      },
    ],
    best_free_slug: null,
  });
  const s = site({}, () => metaResponse(mcpAnswer));
  const html = await (await s.search({ need: 'let my coding agent search my notes', os: 'linux' })).text();
  const pick = html.split('<article class="pick"')[1];
  assert.match(pick, /An MCP client called one of its tools<\/p>/);
  assert.match(pick, /An MCP client handshake over stdio listed its 2 tools \(search_notes, read_note\), and a call to search_notes returned a result\./);
  assert.match(pick, /<h4>Add it to your agent<\/h4><div class="cmd"><pre translate="no"><code>claude mcp add/);
  assert.match(pick, /JSON for Claude Desktop, Cursor and other clients/);
  assert.match(pick, /<code translate="no">NOTES_SYNC_TOKEN<\/code>: sync service token \(required\)/);
});

test('the rules path shows each pick\'s fit label and its words once, and the heading follows match_quality', async () => {
  const s = site({ MATCH_MODE: 'off' });
  const html = await (await s.search({ ...MAC_LLM, need: 'run a language model offline with a terminal chat client' })).text();
  const title = /<h2 class="results-title">([^<]*)<\/h2>/.exec(html)![1];
  assert.match(title, /^(\d tools? ranked by rules|Partial fits, ranked by rules|No clear fit, ranked by rules)$/);
  const picks = html.split('<article class="pick"').slice(1);
  assert.ok(picks.length > 0);
  for (const pick of picks) {
    assert.match(pick, /<span class="badge badge-(pass|caution) match-(good|partial|weak)">(Good|Partial|Weak) match<\/span>/);
    assert.match(pick, /<p class="coverage">/);
    // The same words are not repeated as a tradeoff.
    assert.ok(!/<li>(Covers part of the request|Weak match):/.test(pick));
  }
});

test('render: a GUI app\'s launch is described as such, and only a real screen gets a check mark', () => {
  const gui = { tier: 'ui_rendered' as const, screen: 'first_run' as const, display: 'Xvfb 1280x800x24, no window manager, no GPU', launch_offline: true };
  const app = pick({ verification: { ...pick().verification, level: 'install', gui } });
  const html = renderResults({ out: output([app]), guides: {} }, EMPTY_FORM, fixtureCatalog());
  assert.match(html, /<p class="level"><span class="level-i"><svg class="i i-app-window"[^>]*>.*?<\/svg><\/span>It opens to its first-run screen<\/p>/);
  assert.ok(html.includes(esc(guiSentence(gui))));
  assert.match(guiSentence(gui), /pickfit did not use any of its features\. The launch passed again with the network off\.$/);
  const offlineGuide = { tool: { verification: { works_offline: true }, steps: [], known_issues: [], mcp_client_config: null } as any };
  const once = renderResults({ out: output([app]), guides: offlineGuide }, EMPTY_FORM, fixtureCatalog());
  assert.equal(once.split('network off').length - 1, 1, 'the offline result is said once for a GUI app');
  const broken = pick({ verification: { ...pick().verification, level: 'install', gui: { ...gui, screen: 'crash_or_error' } } });
  const bad = renderResults({ out: output([broken]), guides: {} }, EMPTY_FORM, fixtureCatalog());
  assert.match(bad, /<p class="level level-caution"><svg class="i i-triangle-alert"[^>]*>.*?<\/svg>It showed an error on launch<\/p>/);
  assert.ok(!bad.includes('class="level-i"') && !bad.includes('class="check"'));
  assert.equal(levelLabel('service', { mcp: { called_tool: null } }), 'An MCP client connects and lists its tools');
  assert.equal(levelLabel('function'), 'Its main function works');
});

test('render: a model timeout says so', () => {
  const out = { ...output([pick()]), matched_by: 'rules', degraded: true, degraded_reason: 'model_timeout' };
  assert.match(renderResults({ out, guides: {} }, EMPTY_FORM, fixtureCatalog()), /Muse Spark didn’t answer in time, so these results are ranked by rules\./);
});

test('a run is dated by its UTC day everywhere, the day the page shows', () => {
  // 01:45 in Taipei on 31 Oct is still 30 Oct in UTC: the agent text and the card value say 30 Oct, like the ticket.
  assert.equal(runDay('2026-10-31T01:45:18.636290+08:00'), '2026-10-30');
  assert.equal(runDay('2026-10-31T12:00:00Z'), '2026-10-31');
  assert.equal(runDay('not a date'), 'not a date');
});
