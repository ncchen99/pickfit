/**
 * The product web page: GET / for browsers, POST /search over the MCP's own
 * findSoftware and installGuide, and the web-only limits (rate limit, web
 * Meta cap, cache). The MCP path and the JSON health check must not change.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Env } from '../src/env.ts';
import type { FindOutput, PickOut } from '../src/find.ts';
import { catalogStats, EMPTY_FORM, esc, ranSentence, renderResults, safeUrl, yourSystem, type FormValues } from '../src/page.ts';
import { SEARCHES_PER_MINUTE } from '../src/web.ts';
import { makeWorker } from '../src/worker.ts';
import { answer, fixtureCatalog, fixtureIndex, makeD1, metaResponse } from './helpers.ts';

const MAC_LLM = { need: 'run a language model offline on my laptop', os: 'macos', offline: '1' };
const NOW = new Date('2026-10-30T12:00:00Z');

type Fake = (body: any) => Response;

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
  assert.match(html, /<form id="search"[^>]*method="post" action="\/search"/);
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
  assert.ok(html.includes('<option value="" selected>Any OS</option>'));
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
  assert.match(first, /Runs offline on your machine<span class="cite">From its profile: processing is “local”/);
  assert.match(first, /Needs 8 GB of RAM/);
  assert.match(first, /Best free option<\/span>/);
  assert.match(first, /Hidden gem/);
  assert.match(first, /Lighter than Ollama/);
  // Verified by hand on macOS arm64: the user's OS, so the steps are the macOS ones.
  assert.match(first, /pickfit installed it by hand on macOS arm64 on 28 Oct 2026\./);
  assert.match(first, /class="mine mine-yes">Verified on your OS: it ran on macOS arm64\./);
  assert.match(first, /<details class="install" open><summary>Install steps that worked on macOS arm64/);
  assert.match(first, /brew install fixture\/tap\/fixture-llm-runner/);
  assert.match(first, /You do these yourself<\/h5><ul><li>Allow incoming connections/);
  assert.match(first, /The output should contain “fixture-llm-runner 0\.4\.1”/);
  assert.match(first, /fixture-llm-runner serve --model tiny-test/);
  // Only run on Linux: said plainly, with the Linux steps labelled as such.
  assert.match(second, /Fixture Chat TUI/);
  assert.match(second, /mine-no">.*Not verified on your system: it ran on Linux x86_64, and pickfit hasn’t run it on macOS yet\./);
  assert.match(second, /These steps ran on Linux x86_64\. pickfit hasn’t run them on macOS, so expect differences\./);
  assert.match(second, /<details class="install"><summary>Install steps that worked on Linux x86_64/);
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
  assert.match(second, /mine-unknown">Choose your OS above to see whether it ran on your system\./);
  assert.match(second, /Install steps that worked on Linux x86_64/);
  assert.ok(!second.includes('expect differences'));
});

test('well_known_option is set apart, labelled not verified, and never looks like a pick', async () => {
  const why = 'Ollama is free, runs models offline on macOS and needs no API setup.';
  const s = site({}, () => metaResponse(answer({ well_known_name: 'Ollama', well_known_why: why })));
  const html = await (await s.search({ ...MAC_LLM, free_only: '1' })).text();
  const [picks, outside] = html.split('<aside class="outside"');
  assert.ok(outside, 'the well-known option is rendered');
  assert.match(outside, /^ aria-label="Not verified by pickfit"><p class="unverified">Not verified by pickfit<\/p><h3>Also consider Ollama<\/h3>/);
  assert.ok(outside.includes(esc(why)));
  assert.match(outside, /pickfit has not installed it, has no install guide for it/);
  // No rank, badges, test record, install steps or links: nothing a verified pick has.
  for (const mark of ['class="pick"', 'class="rank"', 'badge', 'class="record"', 'class="install"', '<a ']) {
    assert.ok(!outside.includes(mark), `well-known option has ${mark}`);
  }
  assert.ok(!picks.includes('Also consider'));
});

test('nothing fits: the coverage note, no picks', async () => {
  const s = site({}, () => metaResponse(answer({ picks: [], best_free_slug: null })));
  const html = await (await s.search(MAC_LLM)).text();
  assert.match(html, /<h2>No verified tool fits this yet<\/h2><p>None of the \d+ verified tools that meet the conditions fits this request\.<\/p>/);
  assert.ok(!html.includes('<article class="pick"'));
});

test('a model failure says the results are ranked by rules', async () => {
  const s = site({}, () => Response.json({ error: 'bad request' }, { status: 400 }));
  const html = await (await s.search(MAC_LLM)).text();
  assert.match(html, /<div class="notice busy" role="status"><h2>Ranked without the model this time<\/h2>/);
  assert.match(html, /\d+ verified tools meet your conditions; these are ranked by rules, without a model\./);
  assert.ok(html.includes('<article class="pick"'));
});

test('web searches stop calling Meta at WEB_DAILY_CAP_USD; agents keep the rest of the daily cap', async () => {
  const s = site({ WEB_DAILY_CAP_USD: '2' });
  s.sqlite.prepare('INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?, 1, 2.0)').run('2026-10-30');
  const html = await (await s.search(MAC_LLM)).text();
  assert.equal(s.metaCalls.length, 0);
  assert.match(html, /<h2>Model matching is paused for today<\/h2>/);
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
  const huge = await s.search({ need: 'x'.repeat(5000) });
  assert.equal(huge.status, 413);
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
  assert.ok(html.includes('<option value="macos" selected>'));
  assert.match(html, /<section id="results"[^>]*><p class="match-line">/);
  const nonce = /script-src 'nonce-([0-9a-f]+)'/.exec(res.headers.get('content-security-policy')!)![1];
  assert.ok(html.includes(`<script nonce="${nonce}">`));
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
    verification: { level: 'function', os: 'linux', arch: 'x86_64', method: 'sandbox', replayed: true, checked_at: '2026-10-29T08:00:00Z', verified_on_user_os: null },
    how_we_know: 'pickfit ran it.',
    evidence_url: null,
    scores: { quality: 80, popularity: 10, treasure: false },
    repo: 'https://github.com/a/tool',
    homepage: null,
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
  assert.ok(!html.includes('<img') && !html.includes('<script') && !html.includes('<b>') && !html.includes('<i>'));
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
  assert.match(html, /Best free option among the verified tools:<\/span> <a href="https:\/\/example\.invalid\/fixture\/fixture-json-query"[^>]*>Fixture JSON Query<\/a>\. Free and local\./);
  assert.match(html, /You may not need to install anything<\/h3><p>python3 -m json\.tool is enough\.<\/p><p class="quiet">From Muse Spark’s general knowledge; pickfit hasn’t checked it\./);
  assert.match(html, /Shown from the same search/);
});

test('catalog stats come from the index', () => {
  assert.deepEqual(catalogStats(fixtureCatalog()), { listed: 5, replayed: 5, byHand: 1, gems: 1 });
});
