/**
 * One build, several deployments configured only by env: the read-only
 * evaluation server (TOOLS=readonly), its own Meta caps, and a rules-only
 * twin (MATCH_MODE=off). Also: no response is ever cached, and every response's
 * rec_id is in the D1 events log.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { settings, type Env } from '../src/env.ts';
import { makeWorker } from '../src/worker.ts';
import { answer, fixtureIndex, makeD1, metaResponse } from './helpers.ts';

const WRITE_TOOLS = ['report_outcome', 'submit_software'];
const READ_TOOLS = ['find_alternatives', 'find_software', 'get_install_guide'];
const MAC_LLM = { need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true };

/** Two workers built from the same index never share anything but what env gives them. */
function deployment(env: Partial<Env>, opts: { db?: ReturnType<typeof makeD1> } = {}) {
  const d1 = opts.db ?? makeD1();
  const pending: Promise<unknown>[] = [];
  const metaCalls: unknown[] = [];
  const worker = makeWorker(fixtureIndex(), {
    fetch: (async (_url: string, init: RequestInit) => {
      metaCalls.push(JSON.parse(String(init.body)));
      return metaResponse(answer());
    }) as unknown as typeof fetch,
    now: () => new Date('2026-10-30T12:00:00Z'),
  });
  const ctx = { waitUntil: (p: Promise<unknown>) => void pending.push(p), passThroughOnException() {} };
  const send = (request: Request) => worker.fetch(request, { DB: d1.db, ...env } as Env, ctx as unknown as ExecutionContext);
  let id = 0;
  const rpc = async (method: string, params: object = {}) => {
    const response = await send(
      new Request('http://127.0.0.1:8787/mcp', {
        method: 'POST',
        headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25' },
        body: JSON.stringify({ jsonrpc: '2.0', id: ++id, method, params }),
      }),
    );
    const text = await response.text();
    const data = text.startsWith('{') ? text : text.split('\n').find((l) => l.startsWith('data: '))!.slice(6);
    return { response, message: JSON.parse(data) };
  };
  const call = async (name: string, args: object) => (await rpc('tools/call', { name, arguments: args })).message;
  const health = async () => (await send(new Request('http://127.0.0.1:8787/'))).json() as Promise<any>;
  return { rpc, call, health, sqlite: d1.sqlite, metaCalls, settle: () => Promise.all(pending) };
}

async function listTools(d: ReturnType<typeof deployment>) {
  const init = await d.rpc('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 't', version: '0' } });
  const list = await d.rpc('tools/list');
  return { instructions: init.message.result.instructions as string, tools: list.message.result.tools as any[] };
}

test('TOOLS=readonly exposes only the read tools and never mentions the others', async () => {
  const d = deployment({ TOOLS: 'readonly', MATCH_MODE: 'off' });
  const { instructions, tools } = await listTools(d);
  assert.deepEqual(tools.map((t) => t.name).sort(), READ_TOOLS);
  for (const name of WRITE_TOOLS) {
    assert.ok(!instructions.includes(name), `instructions mention ${name}`);
    assert.ok(!JSON.stringify(tools).includes(name), `a tool description mentions ${name}`);
  }
  assert.ok(tools.every((t) => t.annotations.readOnlyHint === true));

  for (const name of WRITE_TOOLS) {
    const res = await d.call(name, { slug: 'fixture-llm-runner', stage: 'installed', url: 'https://github.com/a/b' });
    assert.ok(res.error || res.result?.isError, `${name} must not be callable`);
  }
  // No report_outcome to check in with, so the guide carries no check_in.
  const guide = await d.call('get_install_guide', { slug: 'fixture-llm-runner', os: 'macos' });
  assert.equal(guide.result.structuredContent.check_in, null);
  assert.ok(!JSON.stringify(guide.result).includes('report_outcome'));
  await d.settle();
  assert.equal(d.sqlite.prepare("SELECT count(*) AS n FROM events WHERE type IN ('outcome', 'submit')").get()!.n, 0);
  assert.equal(d.sqlite.prepare('SELECT count(*) AS n FROM submissions').get()!.n, 0);
});

test('TOOLS unset or "all" exposes all five; an unknown value falls back to read-only', async () => {
  for (const [value, expected] of [
    [undefined, [...READ_TOOLS, ...WRITE_TOOLS].sort()],
    ['all', [...READ_TOOLS, ...WRITE_TOOLS].sort()],
    ['ALL ', [...READ_TOOLS, ...WRITE_TOOLS].sort()],
    ['readnoly', READ_TOOLS],
  ] as const) {
    const { tools } = await listTools(deployment(value === undefined ? {} : { TOOLS: value }));
    assert.deepEqual(tools.map((t) => t.name).sort(), expected, String(value));
  }
});

test('find_software is never cached: the same request is matched again, with a new rec_id', async () => {
  const d = deployment({ TOOLS: 'readonly', MATCH_MODE: 'model', MODEL_API_KEY: 'k' });
  const first = await d.rpc('tools/call', { name: 'find_software', arguments: MAC_LLM });
  const second = await d.rpc('tools/call', { name: 'find_software', arguments: MAC_LLM });
  assert.equal(d.metaCalls.length, 2);
  const [a, b] = [first, second].map((r) => r.message.result.structuredContent);
  assert.equal(a.matched_by, 'muse-spark-1.3');
  assert.notEqual(a.rec_id, b.rec_id);
  for (const { response } of [first, second]) assert.equal(response.headers.get('cache-control'), 'no-store');
  // The Meta request asks Meta to keep nothing either.
  assert.ok(d.metaCalls.every((body: any) => body.store === false));
  await d.settle();
  const rows = d.sqlite.prepare("SELECT rec_id FROM events WHERE type = 'find' ORDER BY rowid").all() as any[];
  assert.deepEqual(rows.map((r) => r.rec_id), [a.rec_id, b.rec_id]);
});

test('every read-only response carries a rec_id that is in the events log', async () => {
  const d = deployment({ TOOLS: 'readonly', MATCH_MODE: 'off' });
  const found = (await d.call('find_software', MAC_LLM)).result.structuredContent;
  const alt = (await d.call('find_alternatives', { current_software: 'jq', pain_points: 'hard filter syntax', os: 'linux' })).result
    .structuredContent;
  const guided = (await d.call('get_install_guide', { slug: 'fixture-llm-runner', os: 'macos' })).result.structuredContent;
  const followed = (await d.call('get_install_guide', { slug: 'fixture-llm-runner', os: 'macos', rec_id: found.rec_id })).result
    .structuredContent;
  await d.settle();
  const logged = (type: string, rec: string, slug: string | null = null) =>
    d.sqlite
      .prepare('SELECT count(*) AS n FROM events WHERE type = ? AND rec_id = ? AND (? IS NULL OR slug = ?)')
      .get(type, rec, slug, slug)!.n;
  assert.equal(logged('find', found.rec_id), 1);
  assert.equal(logged('alternatives', alt.rec_id), 1);
  assert.equal(logged('install_guide', guided.rec_id, 'fixture-llm-runner'), 1);
  assert.equal(followed.rec_id, found.rec_id); // a guide keeps the rec_id of the recommendation it follows
  assert.equal(logged('install_guide', found.rec_id, 'fixture-llm-runner'), 1);
});

test('the daily cap is per deployment and drives degraded', async () => {
  const shared = makeD1();
  shared.sqlite.prepare("INSERT INTO meta_budget (day, calls, cost_usd) VALUES ('2026-10-30', 10, 0.49)").run();
  const tight = deployment({ TOOLS: 'readonly', MODEL_API_KEY: 'k', META_DAILY_CAP_USD: '0.5' }, { db: shared });
  const out = (await tight.call('find_software', MAC_LLM)).result.structuredContent;
  assert.equal(tight.metaCalls.length, 0);
  assert.equal(out.degraded, true);
  assert.equal(out.degraded_reason, 'over_budget');
  assert.equal(out.matched_by, 'rules');

  // Same code, same data, same spend, a larger cap: the model is used.
  const roomy = deployment({ TOOLS: 'readonly', MODEL_API_KEY: 'k', META_DAILY_CAP_USD: '5' }, { db: shared });
  const ok = (await roomy.call('find_software', MAC_LLM)).result.structuredContent;
  assert.equal(roomy.metaCalls.length, 1);
  assert.equal(ok.degraded, false);
});

test('MATCH_MODE=off is a rules-only twin of the same build and data', async () => {
  const model = deployment({ TOOLS: 'readonly', MODEL_API_KEY: 'k' });
  const rules = deployment({ TOOLS: 'readonly', MODEL_API_KEY: 'k', MATCH_MODE: 'off' });
  const [hm, hr] = [await model.health(), await rules.health()];
  assert.equal(hm.data_sha256, hr.data_sha256);
  assert.match(hm.data_sha256, /^[0-9a-f]{64}$/);
  assert.equal(hm.index_built_at, hr.index_built_at);
  assert.deepEqual([hm.match_mode, hr.match_mode], ['model', 'off']);
  assert.deepEqual([hm.tools, hr.tools], ['readonly', 'readonly']);

  const out = (await rules.call('find_software', MAC_LLM)).result.structuredContent;
  assert.equal(rules.metaCalls.length, 0);
  assert.equal(out.matched_by, 'rules');
  assert.equal(out.degraded_reason, 'model_off');
  assert.ok(out.picks.length > 0);
  assert.equal((await model.call('find_software', MAC_LLM)).result.structuredContent.matched_by, 'muse-spark-1.3');
});

test('a failed events write does not fail the response, and is logged with the rec_id', async () => {
  const d1 = makeD1();
  d1.sqlite.exec('DROP TABLE events');
  const d = deployment({ TOOLS: 'readonly', MATCH_MODE: 'off' }, { db: d1 });
  const errors: string[] = [];
  const original = console.error;
  console.error = (line: string) => void errors.push(line);
  try {
    const out = (await d.call('find_software', MAC_LLM)).result.structuredContent;
    await d.settle();
    assert.ok(out.picks.length > 0);
    const logged = errors.map((line) => JSON.parse(line));
    assert.deepEqual(logged.map((e) => [e.event, e.what, e.rec_id]), [['d1_write_failed', 'find', out.rec_id]]);
  } finally {
    console.error = original;
  }
});

test('the full deployment: the guide has a check_in, and report_outcome takes only coarse last_used values', async () => {
  const d = deployment({ MATCH_MODE: 'off' });
  const guide = (await d.call('get_install_guide', { slug: 'fixture-llm-runner', os: 'macos' })).result.structuredContent;
  assert.ok(guide.check_in.commands.length > 0);
  const args = { slug: 'fixture-llm-runner', stage: 'still_using', rec_id: guide.rec_id };
  const bad = await d.call('report_outcome', { ...args, last_used: '2026-10-31' });
  assert.ok(bad.error || bad.result?.isError, 'an exact date is refused');
  await d.settle();
  const ok = (await d.call('report_outcome', { ...args, last_used: 'this_week' })).result.structuredContent;
  assert.equal(ok.counted_in_score, true);
  assert.equal(d.sqlite.prepare("SELECT last_used FROM events WHERE type = 'outcome'").get()!.last_used, 'this_week');
});

test('META_VIA picks the route and its key; anything but "openrouter" stays on Meta', () => {
  const base = { DB: {} as D1Database, MODEL_API_KEY: 'meta-key', OPENROUTER_API_KEY: 'or-key' };
  assert.deepEqual(
    [settings({ ...base }).via, settings({ ...base }).apiKey],
    ['meta', 'meta-key'],
  );
  assert.deepEqual(
    [settings({ ...base, META_VIA: ' OpenRouter ' }).via, settings({ ...base, META_VIA: 'openrouter' }).apiKey],
    ['openrouter', 'or-key'],
  );
  assert.equal(settings({ ...base, META_VIA: 'open-router' }).via, 'meta');
});
