import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Env } from '../src/env.ts';
import { INSTRUCTIONS, READONLY_INSTRUCTIONS } from '../src/server.ts';
import { makeWorker } from '../src/worker.ts';
import { answer, fixtureIndex, makeD1, metaResponse } from './helpers.ts';

const MODERN_META = {
  'io.modelcontextprotocol/protocolVersion': '2026-07-28',
  'io.modelcontextprotocol/clientInfo': { name: 'test', version: '0' },
  'io.modelcontextprotocol/clientCapabilities': {},
};
const ARGS = { need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true };

function setup(env: Partial<Env> = {}, fake?: () => Response) {
  const { db, sqlite } = makeD1();
  const pending: Promise<unknown>[] = [];
  const worker = makeWorker(fixtureIndex(), {
    fetch: (async () => (fake ? fake() : Response.json({}, { status: 500 }))) as unknown as typeof fetch,
  });
  const ctx = { waitUntil: (p: Promise<unknown>) => void pending.push(p), passThroughOnException() {} };
  const call = (request: Request) =>
    worker.fetch(request, { DB: db, MATCH_MODE: 'off', ...env } as Env, ctx as unknown as ExecutionContext);
  return { call, sqlite, settle: () => Promise.all(pending) };
}

function rpc(body: object, headers: Record<string, string> = {}, host = '127.0.0.1:8787') {
  return new Request(`http://${host}/mcp`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', ...headers },
    body: JSON.stringify(body),
  });
}

/** Legacy responses may come back as SSE; return the JSON-RPC message either way. */
async function message(response: Response): Promise<any> {
  const text = await response.text();
  if (response.headers.get('content-type')?.includes('text/event-stream')) {
    const data = text.split('\n').find((line) => line.startsWith('data: '));
    return JSON.parse(data!.slice(6));
  }
  return JSON.parse(text);
}

test('legacy clients: initialize, list and call without a session', async () => {
  const { call } = setup();
  const init = await call(
    rpc({
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'test', version: '0' } },
    }),
  );
  assert.equal(init.status, 200);
  assert.equal(init.headers.get('mcp-session-id'), null);
  const initMsg = await message(init);
  assert.match(initMsg.result.instructions, /^pickfit recommends lesser-known software/);
  // Every client loads these each session: keep them short (they grew past 512 with the answer guidance).
  assert.ok(initMsg.result.instructions.length <= 900);

  const list = await message(
    await call(rpc({ jsonrpc: '2.0', id: 2, method: 'tools/list' }, { 'mcp-protocol-version': '2025-11-25' })),
  );
  const tools = Object.fromEntries(list.result.tools.map((t: any) => [t.name, t]));
  assert.deepEqual(Object.keys(tools).sort(), ['find_alternatives', 'find_software', 'get_install_guide', 'report_outcome', 'submit_software']);
  for (const tool of Object.values(tools) as any[]) {
    assert.equal(tool.outputSchema.type, 'object', tool.name);
    assert.ok(tool.description.length <= 1000, tool.name);
  }
  assert.equal(tools.find_software.annotations.readOnlyHint, true);
  assert.equal(tools.find_alternatives.annotations.readOnlyHint, true);
  assert.equal(tools.get_install_guide.annotations.readOnlyHint, true);
  // Writes: never destructive, safe to retry; only submit_software reaches outside (the pipeline reads the repo).
  for (const name of ['report_outcome', 'submit_software']) {
    assert.equal(tools[name].annotations.readOnlyHint, false);
    assert.equal(tools[name].annotations.destructiveHint, false);
    assert.equal(tools[name].annotations.idempotentHint, true);
  }
  assert.equal(tools.report_outcome.annotations.openWorldHint, false);
  assert.equal(tools.submit_software.annotations.openWorldHint, true);

  const res = await message(
    await call(
      rpc(
        { jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'find_software', arguments: ARGS } },
        { 'mcp-protocol-version': '2025-11-25' },
      ),
    ),
  );
  const out = res.result.structuredContent;
  assert.equal(out.matched_by, 'rules');
  assert.equal(out.degraded_reason, 'model_off');
  assert.deepEqual(JSON.parse(res.result.content[0].text), out);
});

test('instructions say how to write the answer: pick first, alternative before the steps, no narration', () => {
  for (const text of [INSTRUCTIONS, READONLY_INSTRUCTIONS]) {
    assert.match(text, /open with one pick for the likely setup and confirm hard limits/);
    assert.match(text, /say "free" whenever it is/);
    assert.match(text, /Next line, before any steps: "If your setup is X instead, use Y\."/);
    assert.match(text, /say why the obvious choice isn't recommended/);
    assert.match(text, /Tag well_known_option "\(not verified by pickfit\)" beside its name/);
    assert.match(text, /Don't narrate the search or say pickfit found nothing; just answer/);
    assert.match(text, /No disclaimers about what you didn't run/);
  }
});

test('find tools: the unverified tag and no search narration', async () => {
  const { call } = setup();
  const list = await message(
    await call(rpc({ jsonrpc: '2.0', id: 1, method: 'tools/list' }, { 'mcp-protocol-version': '2025-11-25' })),
  );
  const tools = Object.fromEntries(list.result.tools.map((t: any) => [t.name, t.description as string]));
  for (const name of ['find_software', 'find_alternatives']) {
    assert.match(tools[name], /well_known_option[^.]*: tag it "\(not verified by pickfit\)" beside its name/, name);
    assert.match(tools[name], /If no pick fits, answer without mentioning the search\./, name);
  }
  assert.match(tools.find_alternatives, /lead with "keep X" and why/);
});

test('modern clients: the model path end to end, then the install guide', async () => {
  const { call, sqlite, settle } = setup({ MATCH_MODE: 'model', MODEL_API_KEY: 'k' }, () => metaResponse(answer()));
  const headers = { 'mcp-protocol-version': '2026-07-28', 'mcp-method': 'tools/call' };
  const found = await message(
    await call(
      rpc(
        {
          jsonrpc: '2.0',
          id: 10,
          method: 'tools/call',
          params: { name: 'find_software', arguments: ARGS, _meta: MODERN_META },
        },
        { ...headers, 'mcp-name': 'find_software' },
      ),
    ),
  );
  const out = found.result.structuredContent;
  assert.equal(out.matched_by, 'muse-spark-1.3');
  assert.deepEqual(out.picks.map((p: any) => p.slug), ['fixture-llm-runner', 'fixture-chat-tui']);

  const guide = await message(
    await call(
      rpc(
        {
          jsonrpc: '2.0',
          id: 11,
          method: 'tools/call',
          params: {
            name: 'get_install_guide',
            arguments: { slug: 'fixture-llm-runner', os: 'macos', rec_id: out.rec_id },
            _meta: MODERN_META,
          },
        },
        { ...headers, 'mcp-name': 'get_install_guide' },
      ),
    ),
  );
  assert.equal(guide.result.structuredContent.applies_to_user_system.match, 'exact');
  assert.equal(guide.result.structuredContent.rec_id, out.rec_id);
  await settle();

  const reported = await message(
    await call(
      rpc(
        {
          jsonrpc: '2.0',
          id: 12,
          method: 'tools/call',
          params: {
            name: 'report_outcome',
            arguments: { slug: 'fixture-llm-runner', stage: 'installed', rec_id: out.rec_id, satisfaction: 'satisfied' },
            _meta: MODERN_META,
          },
        },
        { ...headers, 'mcp-name': 'report_outcome', 'x-pickfit-reporter': 'dev' },
      ),
    ),
  );
  assert.equal(reported.result.structuredContent.counted_in_score, true);
  await settle();
  const rows = sqlite.prepare('SELECT type, rec_id, reporter FROM events ORDER BY type').all() as any[];
  assert.deepEqual(rows.map((r) => r.type), ['find', 'install_guide', 'outcome']);
  assert.ok(rows.every((r) => r.rec_id === out.rec_id));
  assert.equal(rows[2].reporter, 'dev');
});

test('a record with a usage guide still passes find_software and get_install_guide output schemas', async () => {
  const { call } = setup();
  const headers = { 'mcp-protocol-version': '2025-11-25' };
  const guide = await message(
    await call(
      rpc(
        { jsonrpc: '2.0', id: 30, method: 'tools/call', params: { name: 'get_install_guide', arguments: { slug: 'fixture-llm-runner', os: 'linux' } } },
        headers,
      ),
    ),
  );
  assert.ok(!guide.result.isError, JSON.stringify(guide.result).slice(0, 300));
  assert.equal(guide.result.structuredContent.slug, 'fixture-llm-runner');
  const found = await message(
    await call(rpc({ jsonrpc: '2.0', id: 31, method: 'tools/call', params: { name: 'find_software', arguments: ARGS } }, headers)),
  );
  assert.ok(!found.result.isError, JSON.stringify(found.result).slice(0, 300));
  assert.ok(found.result.structuredContent.picks.some((p: any) => p.slug === 'fixture-llm-runner'));
});

test('bad input and unknown slugs come back as tool errors', async () => {
  const { call } = setup();
  const headers = { 'mcp-protocol-version': '2025-11-25' };
  const short = await message(
    await call(
      rpc({ jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 'find_software', arguments: { need: 'x' } } }, headers),
    ),
  );
  assert.equal(short.result.isError, true);
  const unknown = await message(
    await call(
      rpc(
        {
          jsonrpc: '2.0',
          id: 5,
          method: 'tools/call',
          params: { name: 'get_install_guide', arguments: { slug: 'not-there', os: 'linux' } },
        },
        headers,
      ),
    ),
  );
  assert.equal(unknown.result.isError, true);
  assert.match(unknown.result.content[0].text, /Call find_software first/);
});

test('Host and Origin allowlists block DNS rebinding', async () => {
  const { call } = setup({ ALLOWED_HOSTS: 'pickfit-mcp.example.workers.dev' });
  const list = { jsonrpc: '2.0', id: 1, method: 'tools/list' };
  const h = { 'mcp-protocol-version': '2025-11-25' };
  assert.equal((await call(rpc(list, h, 'evil.example'))).status, 403);
  assert.equal((await call(rpc(list, { ...h, origin: 'https://evil.example' }))).status, 403);
  assert.equal((await call(rpc(list, { ...h, origin: 'http://localhost:6274' }))).status, 200);
  assert.equal((await call(rpc(list, h, 'pickfit-mcp.example.workers.dev'))).status, 200);
});

test('other paths: health at /, 404 elsewhere', async () => {
  const { call } = setup();
  const health = await call(new Request('http://127.0.0.1:8787/'));
  assert.deepEqual(Object.keys(await health.json()).sort(), ['data_sha256', 'entries', 'index_built_at', 'match_mode', 'mcp', 'name', 'tools']);
  assert.equal((await call(new Request('http://127.0.0.1:8787/other'))).status, 404);
});
