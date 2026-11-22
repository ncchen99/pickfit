/**
 * An MCP server's safety facts (pickfit/index.py _mcp_safety, brief 15.7): the card fields the matcher may cite, and
 * the mcp_risk summary find_software's picks carry so an agent can warn before connecting the server. Entries
 * without the facts keep their cards and picks exactly as before.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadCatalog, type Entry, type McpSafety } from '../src/catalog.ts';
import { CARD_FIELDS, MCP_SAFETY_FIELDS, promptCard, toCard } from '../src/cards.ts';
import type { Env } from '../src/env.ts';
import { findSoftware } from '../src/find.ts';
import { mcpRisk } from '../src/mcprisk.ts';
import { makeWorker } from '../src/worker.ts';
import { fixtureIndex, harness, makeD1 } from './helpers.ts';

const SLUG = 'fixture-notes-mcp';
const NEED = { need: 'search Markdown notes from an AI client over MCP', os: 'linux' as const, category: 'mcp_server' as const };

const RISKY: McpSafety = {
  description_flags: ['override', 'sensitive_files'],
  tool_annotations: { read_only: 1, destructive: 1, open_world: 2 },
  egress_hosts: ['sync.notes.example', 'telemetry.notes.example', 'a.example', 'b.example', 'c.example', 'd.example'],
  tool_count: 2,
};

function indexWith(safety: McpSafety | undefined) {
  const index = structuredClone(fixtureIndex()) as { entries: Entry[] };
  const entry = index.entries.find((e) => e.slug === SLUG)!;
  if (safety) entry.mcp_safety = safety;
  else delete entry.mcp_safety;
  return index;
}

const entryWith = (safety: McpSafety | undefined) => loadCatalog(indexWith(safety)).bySlug.get(SLUG)!;

test('the fixture index has no safety facts, so cards and picks stay as they were', () => {
  const entry = entryWith(undefined);
  assert.equal(mcpRisk(entry), null);
  const card = toCard(entry, 'linux');
  for (const field of MCP_SAFETY_FIELDS) assert.ok(!(field in card), field);
});

test('cards carry the recorded facts, citable by the matcher', () => {
  const card = toCard(entryWith(RISKY), 'linux');
  assert.deepEqual(card.mcp_injection_flags, ['override', 'sensitive_files']);
  assert.equal(card.mcp_destructive_tools, 1);
  assert.equal(card.mcp_open_world_tools, 2);
  assert.deepEqual(card.mcp_egress_hosts, RISKY.egress_hosts);
  for (const field of MCP_SAFETY_FIELDS) assert.ok((CARD_FIELDS as readonly string[]).includes(field));
  // Only what was recorded: a run with egress logged and nothing else adds that one field; [] leaves the prompt.
  const egressOnly = toCard(entryWith({ egress_hosts: [], tool_count: 2 }), 'linux');
  assert.deepEqual(egressOnly.mcp_egress_hosts, []);
  assert.ok(!('mcp_injection_flags' in egressOnly) && !('mcp_destructive_tools' in egressOnly));
  assert.ok(!('mcp_egress_hosts' in promptCard(egressOnly)));
});

test('mcp_risk sums the facts up and says what to tell the user', () => {
  const risk = mcpRisk(entryWith(RISKY))!;
  assert.equal(risk.prompt_injection, true);
  assert.deepEqual(risk.injection_patterns, ['override', 'sensitive_files']);
  assert.deepEqual([risk.tool_count, risk.destructive_tools, risk.open_world_tools, risk.read_only_tools], [2, 1, 2, 1]);
  assert.equal(risk.egress_hosts, 6);
  assert.deepEqual(risk.egress_examples, RISKY.egress_hosts!.slice(0, 5));
  assert.match(risk.warning!, /^Before adding it to a client: /);
  assert.match(risk.warning!, /ignore its instructions/);
  assert.match(risk.warning!, /1 of 2 tools say they can delete or overwrite things/);
  assert.match(risk.warning!, /connected to 6 outside hosts \(sync\.notes\.example, .*, …\)/);

  const clean = mcpRisk(entryWith({ description_flags: [], tool_annotations: { read_only: 2, destructive: 0, open_world: 0 }, egress_hosts: [], tool_count: 2 }))!;
  assert.deepEqual(
    [clean.prompt_injection, clean.destructive_tools, clean.egress_hosts, clean.warning],
    [false, 0, 0, null],
  );
  // Not recorded stays null, never a reassuring zero.
  const partial = mcpRisk(entryWith({ egress_hosts: ['api.notes.example'], tool_count: 2 }))!;
  assert.deepEqual([partial.prompt_injection, partial.destructive_tools, partial.open_world_tools], [null, null, null]);
  assert.equal(partial.warning, "Before adding it to a client: in pickfit's sandbox it connected to 1 outside host (api.notes.example).");
});

test('find_software picks carry mcp_risk for an MCP server with facts, and leave it out otherwise', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = loadCatalog(indexWith(RISKY));
  const out = await findSoftware(NEED, h.deps);
  await h.settle();
  const pick = out.picks.find((p) => p.slug === SLUG);
  assert.ok(pick, JSON.stringify(out.picks.map((p) => p.slug)));
  assert.equal(pick.mcp_risk?.prompt_injection, true);
  assert.equal(pick.mcp_risk?.egress_hosts, 6);

  const plain = harness(null, { modelEnabled: false });
  const before = await findSoftware(NEED, plain.deps);
  await plain.settle();
  assert.ok(before.picks.every((p) => !('mcp_risk' in p)));
});

test('the MCP find_software output schema accepts mcp_risk', async () => {
  const { db } = makeD1();
  const worker = makeWorker(indexWith(RISKY), { fetch: (async () => Response.json({}, { status: 500 })) as unknown as typeof fetch });
  const ctx = { waitUntil() {}, passThroughOnException() {} };
  const response = await worker.fetch(
    new Request('http://127.0.0.1:8787/mcp', {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'find_software', arguments: NEED } }),
    }),
    { DB: db, MATCH_MODE: 'off' } as Env,
    ctx as unknown as ExecutionContext,
  );
  const text = await response.text();
  const body = JSON.parse(text.startsWith('{') ? text : text.split('\n').find((l) => l.startsWith('data: '))!.slice(6));
  assert.ok(!body.result.isError, JSON.stringify(body.result).slice(0, 300));
  const pick = body.result.structuredContent.picks.find((p: any) => p.slug === SLUG);
  assert.ok(pick);
  assert.equal(pick.mcp_risk.egress_hosts, 6);
  assert.match(pick.mcp_risk.warning, /outside hosts/);
});
