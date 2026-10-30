/** MCP servers: the client config get_install_guide writes from the sandbox run, and what the cards show. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { toCard } from '../src/cards.ts';
import { installGuide } from '../src/install.ts';
import { clientConfig, shellQuote } from '../src/mcpconfig.ts';
import { fixtureCatalog } from './helpers.ts';

const catalog = fixtureCatalog();

test('the client config comes from the launch argv the sandbox started', () => {
  const out = installGuide(catalog, { slug: 'fixture-notes-mcp', os: 'linux' });
  const config = out.mcp_client_config!;
  assert.deepEqual([config.command, config.args], ['notes-mcp', ['--root', '~/work']]);
  assert.equal(config.claude_code, "claude mcp add fixture-notes-mcp -e NOTES_SYNC_TOKEN='<NOTES_SYNC_TOKEN>' -- notes-mcp --root ~/work");
  assert.deepEqual(JSON.parse(config.json), {
    mcpServers: { 'fixture-notes-mcp': { command: 'notes-mcp', args: ['--root', '~/work'], env: { NOTES_SYNC_TOKEN: '<NOTES_SYNC_TOKEN>' } } },
  });
  // Only variables the README marks required become placeholders; pickfit never had a value.
  assert.deepEqual(config.env.map((v) => v.name), ['NOTES_SYNC_TOKEN']);
  assert.match(config.note ?? '', /paths inside pickfit's sandbox/);
  assert.match(config.note ?? '', /Ask the user for NOTES_SYNC_TOKEN/);
  assert.deepEqual([config.tools, config.tool_count, config.called_tool, config.works_offline], [['search_notes', 'read_note'], 2, 'search_notes', true]);
  // The probe exists only in pickfit's sandbox: never a check or first task for the user.
  assert.deepEqual([out.verify, out.first_task], [null, null]);
  assert.match(out.how_we_know, /an MCP client handshake over stdio listed its 2 tools with the network off, and a call to search_notes returned a result/);
});

test('other software has no client config, and an MCP server without a run gives none', () => {
  assert.equal(installGuide(catalog, { slug: 'fixture-json-query', os: 'linux' }).mcp_client_config, null);
  const entry = catalog.bySlug.get('fixture-notes-mcp')!;
  assert.equal(clientConfig(entry, null), null);
  assert.equal(clientConfig(entry, { ...entry.install.linux!, mcp: null }), null);
});

test('cards show the tool names a handshake listed, and the env vars the README names', () => {
  const card = toCard(catalog.bySlug.get('fixture-notes-mcp')!, 'linux');
  assert.deepEqual(card.mcp_tools, ['search_notes', 'read_note']);
  assert.deepEqual(card.mcp_env_vars, ['NOTES_ROOT', 'NOTES_SYNC_TOKEN']);
  assert.deepEqual(toCard(catalog.bySlug.get('fixture-json-query')!).mcp_tools, []);
});

test('shell quoting keeps plain words and ~/ paths, and quotes the rest', () => {
  assert.equal(shellQuote('notes-mcp'), 'notes-mcp');
  assert.equal(shellQuote('~/work'), '~/work');
  assert.equal(shellQuote('a b'), "'a b'");
  assert.equal(shellQuote("it's"), `'it'"'"'s'`);
  assert.equal(shellQuote('$(rm -rf /)'), "'$(rm -rf /)'");
});

test('an HTTP-only server gets the URL to add and the command to start first', () => {
  const entry = catalog.bySlug.get('fixture-notes-mcp')!;
  const guide = {
    ...entry.install.linux!,
    mcp: { ...entry.install.linux!.mcp!, transport: 'streamable_http' as const, launch: ['notes-mcp', '--http', '--port', '8765'], url: 'http://127.0.0.1:8765/mcp' },
  };
  const config = clientConfig(entry, guide)!;
  assert.equal(config.claude_code, 'claude mcp add --transport http fixture-notes-mcp http://127.0.0.1:8765/mcp');
  assert.deepEqual(JSON.parse(config.json), { mcpServers: { 'fixture-notes-mcp': { type: 'http', url: 'http://127.0.0.1:8765/mcp' } } });
  assert.deepEqual([config.transport, config.url, config.command], ['streamable_http', 'http://127.0.0.1:8765/mcp', 'notes-mcp']);
  assert.match(config.note ?? '', /start it first and keep it running \(notes-mcp --http --port 8765, with NOTES_SYNC_TOKEN set\)/);
  assert.equal(clientConfig(entry, { ...guide, mcp: { ...guide.mcp, url: null } }), null);
});

test('variables an HTTP server was started with stay in the start command, not in command', () => {
  const entry = catalog.bySlug.get('fixture-notes-mcp')!;
  const guide = {
    ...entry.install.linux!,
    mcp: { ...entry.install.linux!.mcp!, transport: 'streamable_http' as const, launch: ['VAULT_PATH=/tmp/v', 'PORT=3001', 'notes-mcp'], url: 'http://127.0.0.1:3001/sse' },
  };
  const config = clientConfig(entry, guide)!;
  assert.deepEqual([config.command, config.args], ['notes-mcp', []]);
  assert.match(config.note ?? '', /keep it running \(VAULT_PATH=\/tmp\/v PORT=3001 notes-mcp/);
  assert.match(config.note ?? '', /paths inside pickfit's sandbox/);
});
