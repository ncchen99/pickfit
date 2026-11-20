import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { remoteD1 } from '../cloudrun/bindings.ts';
import { cloudRunAllowedHosts } from '../cloudrun/config.ts';
import { parseHeaders, parseJsonc } from '../cloudrun/server.ts';

test('remoteD1 sends sql and params, and reads rows and meta', async () => {
  const calls: { url: string; body: unknown; auth: string | null }[] = [];
  const fakeFetch = (async (url: string, init: RequestInit) => {
    calls.push({ url, body: JSON.parse(String(init.body)), auth: new Headers(init.headers).get('authorization') });
    return Response.json({ success: true, result: [{ results: [{ total: 3, today: 1 }], meta: { changes: 2 } }] });
  }) as unknown as typeof fetch;
  const db = remoteD1({ accountId: 'acc', databaseId: 'db', token: 'tok', fetch: fakeFetch });

  assert.deepEqual(await db.prepare('SELECT ?1, ?2').bind('a', undefined).first(), { total: 3, today: 1 });
  assert.equal(await db.prepare('SELECT 1').first('total'), 3);
  assert.equal((await db.prepare('UPDATE x').run()).meta.changes, 2);
  assert.equal(calls[0].url, 'https://api.cloudflare.com/client/v4/accounts/acc/d1/database/db/query');
  assert.deepEqual(calls[0].body, { sql: 'SELECT ?1, ?2', params: ['a', null] });
  assert.equal(calls[0].auth, 'Bearer tok');
});

test('remoteD1 turns an API error into a thrown error', async () => {
  const fakeFetch = (async () =>
    Response.json({ success: false, errors: [{ message: 'no such table: nope' }] }, { status: 400 })) as unknown as typeof fetch;
  const db = remoteD1({ accountId: 'a', databaseId: 'd', token: 't', fetch: fakeFetch });
  await assert.rejects(db.prepare('SELECT * FROM nope').all(), /no such table/);
});

test('parseJsonc keeps // inside strings and drops comments and trailing commas', () => {
  const text = '// top\n{ "a": "https://x.y", /* b */ "c": [1, 2,], // end\n }';
  assert.deepEqual(parseJsonc(text), { a: 'https://x.y', c: [1, 2] });
});

test('parseHeaders reads Cloudflare _headers rules', () => {
  const rules = parseHeaders('/assets/*\n  Cache-Control: public, max-age=86400\n  X-Content-Type-Options: nosniff\n');
  assert.equal(rules.length, 1);
  assert.ok(rules[0].pattern.test('/assets/fitz/fitz.svg'));
  assert.ok(!rules[0].pattern.test('/tool/x'));
  assert.deepEqual(rules[0].headers[0], ['Cache-Control', 'public, max-age=86400']);
});

test('deploy.sh takes ALLOWED_HOSTS from wrangler.jsonc, adding only the run.app host', () => {
  const wrangler = readFileSync(join(import.meta.dirname, '..', 'wrangler.jsonc'), 'utf8');
  const deploy = readFileSync(join(import.meta.dirname, '..', 'cloudrun', 'deploy.sh'), 'utf8');
  const top = (parseJsonc(wrangler) as { vars: { ALLOWED_HOSTS: string } }).vars.ALLOWED_HOSTS;
  // No host list of its own: the env var is built by config.ts from wrangler.jsonc.
  assert.match(deploy, /HOSTS="\$\(node cloudrun\/config\.ts allowed-hosts "\$RUN_HOST"\)"/);
  assert.match(deploy, /ALLOWED_HOSTS=\$\{HOSTS\}/);
  const code = deploy.split('\n').filter((line) => !line.trim().startsWith('#')).join('\n');
  for (const host of top.split(',')) assert.ok(!code.includes(host.trim()), `deploy.sh hard-codes ${host}`);
  const runHost = /RUN_HOST="([^"]+)"/.exec(deploy)![1];
  assert.equal(cloudRunAllowedHosts(wrangler, runHost), `${top},${runHost}`);
});

test('cloudRunAllowedHosts trims, drops repeats and refuses an empty list', () => {
  assert.equal(cloudRunAllowedHosts('{ "vars": { "ALLOWED_HOSTS": " A.app , b.dev," } }', 'a.app', 'c.run.app'), 'a.app,b.dev,c.run.app');
  assert.throws(() => cloudRunAllowedHosts('{ "vars": {} } // none'), /no top-level ALLOWED_HOSTS/);
});
