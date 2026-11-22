/**
 * What a feature's check ran against (fidelity: real, compatible, stand_in; docs/proposals/privileges.md P1). A feature
 * checked against a stand-in (a mail sink, a storage emulator, a tiny model) shows the tool connects, not that it works
 * with the real service: no page ticks it, no count takes it as working without saying so, the matcher's card does not
 * list it as checked, and an MCP answer names it in both the structured output and the text. A compatible endpoint
 * keeps its tick with a note. A run that recorded no fidelity reads exactly as before.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CfWorkerJsonSchemaValidator } from '@modelcontextprotocol/server/validators/cf-worker';
import { toCard } from '../src/cards.ts';
import { bestGuide, loadCatalog, type Entry } from '../src/catalog.ts';
import type { Env } from '../src/env.ts';
import { featureSentence, featuresOut, shownWorking, standInOnly } from '../src/features.ts';
import { findSoftware } from '../src/find.ts';
import { reasonHolds } from '../src/guard.ts';
import { translateWith, withLang } from '../src/i18n.ts';
import { installGuide } from '../src/install.ts';
import { compareTable } from '../src/pages/compare.ts';
import { findSummary, installSummary } from '../src/summary.ts';
import { coverageSection } from '../src/ui/coverage.ts';
import { workedFeatures } from '../src/ui/facts.ts';
import { coverage } from '../src/ui/kit.ts';
import { makeWorker } from '../src/worker.ts';
import { fixtureCatalog, fixtureIndex, harness, makeD1 } from './helpers.ts';

const SLUG = 'fixture-llm-runner';
const SERVE = 'serve an OpenAI-compatible API';
const MAIL = 'send a report by email';
const HOSTED = 'summarize with a hosted model';
const PULL = 'pull models from a registry';
const STAND_IN_EN = 'Checked against a stand-in: this shows it connects, not that it works with the real service.';
const STAND_IN_ZH = '用替身驗的：只確認接得上，沒有對真的服務驗過。';

/** The fixture index with two more checked features on fixture-llm-runner's Linux run, as index.py would write them:
 * one checked against a stand-in (a mail sink), one through a compatible endpoint. The first feature has no fidelity. */
function index(): any {
  const data = structuredClone(fixtureIndex()) as any;
  const runner = data.entries.find((e: any) => e.slug === SLUG);
  runner.features = [SERVE, MAIL, HOSTED, PULL];
  const checked = (feature: string, fidelity: string, command: string) => ({
    feature,
    status: 'checked',
    reason: null,
    failure: null,
    note: null,
    checks: [{ command, passed: true }],
    fidelity,
  });
  runner.install.linux.features.splice(
    1,
    0,
    checked(MAIL, 'stand_in', 'fixture-llm-runner report --smtp 127.0.0.1:1025'),
    checked(HOSTED, 'compatible', 'fixture-llm-runner summarize --base-url http://127.0.0.1:8080/v1 notes.txt'),
  );
  runner.coverage.dimensions.function = { status: 'partial', done: 3, of: 4, unit: 'feature', gaps: ['sandbox_missing'], stand_in: 1 };
  return data;
}

const catalog = loadCatalog(index());
const entry = catalog.bySlug.get(SLUG)!;
const linux = entry.install.linux!;
const features = featuresOut(entry, linux);

function site(data: unknown) {
  const { db } = makeD1();
  const worker = makeWorker(data, {
    fetch: (async () => {
      throw new Error('no model call expected');
    }) as unknown as typeof fetch,
    now: () => new Date('2026-10-30T12:00:00Z'),
  });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const env = { DB: db } as Env;
  const get = async (path: string) => (await worker.fetch(new Request(`http://127.0.0.1:8787${path}`, { headers: { accept: 'text/html' } }), env, ctx)).text();
  let id = 0;
  const rpc = async (method: string, params: object = {}) => {
    const response = await worker.fetch(
      new Request('http://127.0.0.1:8787/mcp', {
        method: 'POST',
        headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25' },
        body: JSON.stringify({ jsonrpc: '2.0', id: ++id, method, params }),
      }),
      env,
      ctx,
    );
    const text = await response.text();
    return JSON.parse(text.startsWith('{') ? text : text.split('\n').find((l) => l.startsWith('data: '))!.slice(6));
  };
  return { get, rpc };
}

/** One feature's row on the tool page. */
const row = (html: string, title: string) => html.match(new RegExp(`<li class="feat-[a-z]+"><div><span class="feat-title">${title}</span>.*?</li>`))?.[0] ?? '';

test('a checked feature carries its fidelity only when the run recorded one', () => {
  assert.deepEqual(features.checked, [
    { feature: SERVE, check: 'fixture-llm-runner serve --model tiny-test --once' },
    { feature: MAIL, check: 'fixture-llm-runner report --smtp 127.0.0.1:1025', fidelity: 'stand_in' },
    { feature: HOSTED, check: 'fixture-llm-runner summarize --base-url http://127.0.0.1:8080/v1 notes.txt', fidelity: 'compatible' },
  ]);
  assert.deepEqual(standInOnly(features).map((f) => f.feature), [MAIL]);
  assert.deepEqual(shownWorking(features).map((f) => f.feature), [SERVE, HOSTED]);
  // The index as it is today has none: nothing gains a key.
  for (const e of fixtureCatalog().entries) {
    for (const guide of [...Object.values(e.install), null]) {
      assert.ok(featuresOut(e, guide ?? null).checked.every((f) => !('fidelity' in f)), e.slug);
    }
  }
});

test('a fidelity the Worker does not know is left out, and a failed test never becomes a stand-in pass', () => {
  const data = index();
  const feats = data.entries.find((e: any) => e.slug === SLUG).install.linux.features;
  feats[1].fidelity = 'pretend';
  feats[2].checks[0].passed = false;
  const tampered = loadCatalog(data).bySlug.get(SLUG)!;
  const out = featuresOut(tampered, tampered.install.linux!);
  assert.deepEqual(out.checked.map((f) => [f.feature, f.fidelity]), [[SERVE, undefined], [MAIL, undefined]]);
  assert.deepEqual(out.not_checked.map((f) => f.feature), [HOSTED, PULL]);
});

test('how_we_know says how many of the features exercised ran only against a stand-in, and names them', () => {
  const sentence = featureSentence(features)!;
  assert.match(sentence, /^The run exercised 3 of the 4 main features its README advertises; see features for the ones it did not check and why\./);
  assert.match(sentence, / 1 of those 3 ran only against a stand-in, not the real service \(send a report by email\): that shows the tool connects, not that the feature works\./);
  assert.match(sentence, / 1 ran through a compatible endpoint with a real model behind it \(summarize with a hosted model\)\.$/);
  const out = installGuide(catalog, { slug: SLUG, os: 'linux' });
  assert.ok(out.how_we_know.includes(sentence));
  // No fidelity recorded: the sentence is the one it always was.
  const plain = installGuide(fixtureCatalog(), { slug: 'fixture-transcribe', os: 'linux' });
  assert.match(plain.how_we_know, /The run exercised 1 of the 3 main features its README advertises; see features for the ones it did not check and why\.(?! \d)/);
  assert.doesNotMatch(plain.how_we_know, /stand-in|compatible endpoint/);
});

test("the text of an install guide names the stand-in features, so an agent that reads only the text can't call them verified", () => {
  const text = installSummary(installGuide(catalog, { slug: SLUG, os: 'linux' }));
  assert.match(
    text,
    /^Features: Checked only against a stand-in, not the real service: send a report by email\. That shows the tool connects; do not say these were verified to work\.$/m,
  );
  assert.match(text, /^Features: Checked through a compatible endpoint with a real model behind it, not the service the tool names: summarize with a hosted model\.$/m);
  assert.doesNotMatch(installSummary(installGuide(fixtureCatalog(), { slug: SLUG, os: 'linux' })), /^Features:/m);
});

test('a find_software pick carries the fidelity, and its text names the stand-in features', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = catalog;
  const out = await findSoftware({ need: 'run a language model with an OpenAI-compatible API', os: 'linux' }, h.deps);
  await h.settle();
  const pick = out.picks.find((p) => p.slug === SLUG)!;
  assert.equal(pick.features.checked.find((f) => f.feature === MAIL)!.fidelity, 'stand_in');
  assert.match(pick.how_we_know, /1 of those 3 ran only against a stand-in/);
  assert.match(findSummary(out), /^ {3}Features: Checked only against a stand-in, not the real service: send a report by email\./m);
});

test('the MCP answers conform to their output schema with a fidelity, and the text block says it', async () => {
  const s = site(index());
  await s.rpc('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 't', version: '0' } });
  const { tools } = (await s.rpc('tools/list')).result;
  const tool = tools.find((t: any) => t.name === 'get_install_guide');
  assert.deepEqual(tool.outputSchema.properties.features.properties.checked.items.properties.fidelity.enum, ['real', 'compatible', 'stand_in']);
  assert.match(tool.outputSchema.properties.features.properties.checked.items.properties.fidelity.description, /never tell the user this feature was verified to work/);
  const res = (await s.rpc('tools/call', { name: 'get_install_guide', arguments: { slug: SLUG, os: 'linux' } })).result;
  assert.ok(!res.isError, JSON.stringify(res.content));
  const check = new CfWorkerJsonSchemaValidator().getValidator(tool.outputSchema)(res.structuredContent);
  assert.ok(check.valid, check.errorMessage ?? JSON.stringify(check));
  assert.deepEqual(
    res.structuredContent.features.checked.map((f: any) => [f.feature, f.fidelity ?? null]),
    [[SERVE, null], [MAIL, 'stand_in'], [HOSTED, 'compatible']],
  );
  assert.match(res.content[0].text, /Checked only against a stand-in, not the real service: send a report by email\./);
});

test("the matcher's card does not list a stand-in feature as checked: it is with the ones pickfit did not see work", () => {
  const card = toCard(entry, 'linux');
  assert.deepEqual(card.features_checked, [SERVE, HOSTED]);
  assert.deepEqual(card.features_not_checked, [`${MAIL} (stand_in_only)`, `${PULL} (test_failed_in_sandbox)`]);
  // A reason that cites it as a checked feature does not hold against the card.
  assert.equal(reasonHolds(card, { claim: 'pickfit checked that it sends reports by email', field: 'features_checked', value: MAIL }), false);
  assert.equal(reasonHolds(card, { claim: 'pickfit checked that it serves an API', field: 'features_checked', value: SERVE }), true);
});

test('the tool page gives a stand-in feature no tick: a plug and one line; a compatible endpoint keeps the tick with a note', async () => {
  const html = await site(index()).get(`/tool/${SLUG}`);
  const mail = row(html, 'Send a report by email');
  assert.match(mail, /^<li class="feat-standin">/);
  assert.ok(mail.includes(`<span class="feat-note">${STAND_IN_EN}</span>`), mail);
  assert.match(mail, /<span class="feat-state"><svg[^>]*>.*?<\/svg>Stand-in only<\/span><\/li>$/);
  assert.doesNotMatch(mail, /Tested|feat-ok/);
  const hosted = row(html, 'Summarize with a hosted model');
  assert.match(hosted, /^<li class="feat-ok">/);
  assert.ok(hosted.includes('<span class="feat-note">Checked through a compatible endpoint, not the service it names.</span>'), hosted);
  assert.match(hosted, /Tested<\/span><\/li>$/);
  const serve = row(html, 'Serve models over an OpenAI-style API'); // its usage guide's title
  assert.match(serve, /^<li class="feat-ok">/);
  assert.doesNotMatch(serve, /feat-note/);
  // Counts: the stage counts only what was seen working, the meter and the coverage say how many were a stand-in.
  assert.match(html, /2 of 4 features work, 1 more checked against a stand-in/);
  assert.doesNotMatch(html, /3 of 4 features work/);
  assert.match(html, /aria-label="Features: 3 of 4 checked, 1 of them against a stand-in"/);
  assert.match(html, /3 of 4 features reached a verdict, 1 of them against a stand-in/);
});

test('the same page in Traditional Chinese', async () => {
  const html = await site(index()).get(`/tool/${SLUG}?lang=zh-TW`);
  const mail = row(html, 'Send a report by email');
  assert.match(mail, /^<li class="feat-standin">/);
  assert.ok(mail.includes(`<span class="feat-note">${STAND_IN_ZH}</span>`), mail);
  assert.match(mail, /只用替身驗<\/span><\/li>$/);
  assert.doesNotMatch(mail, /已測試/);
  assert.ok(row(html, 'Summarize with a hosted model').includes('<span class="feat-note">用相容的端點驗的，不是它指定的那個服務。</span>'));
  assert.match(html, /4 項功能中 2 項可用，另有 1 項是用替身驗的/);
  assert.match(html, /aria-label="功能：已檢查 3\/4 項，其中 1 項是用替身驗的"/);
  assert.match(html, /4 項功能中 3 項有結論，其中 1 項是用替身驗的/);
});

test('a tool page whose runs recorded no fidelity has no stand-in mark, note or count', async () => {
  const page = async (data: unknown) => (await site(data).get('/tool/fixture-transcribe')).replace(/nonce="[^"]*"/g, 'nonce');
  const [before, after] = await Promise.all([page(fixtureIndex()), page(index())]);
  assert.equal(before, after);
  assert.doesNotMatch(before, /class="feat-standin"|class="feat-note"|class="cov-standin"|of them against a stand-in|more checked against a stand-in/);
  assert.match(before, /1 of 3 features work/);
});

test('the features meter draws stand-in features paler than the ones seen working, and says how many in words', () => {
  const meter = coverage(features);
  assert.match(meter, /aria-label="Features: 3 of 4 checked, 1 of them against a stand-in"/);
  assert.equal((meter.match(/class="cov-ok"/g) ?? []).length, 1);
  assert.equal((meter.match(/class="cov-standin"/g) ?? []).length, 1);
  // Two seen working of four: half the bar; the stand-in takes a quarter after it.
  assert.match(meter, /<rect class="cov-ok" x="0\.0" y="0" width="98\.0"/);
  assert.match(meter, /<rect class="cov-standin" x="100\.0" y="0" width="48\.0"/);
  assert.match(withLang('zh-TW', () => coverage(features)), /aria-label="功能：已檢查 3\/4 項，其中 1 項是用替身驗的"/);
  const plain = coverage(featuresOut(fixtureCatalog().bySlug.get(SLUG)!, fixtureCatalog().bySlug.get(SLUG)!.install.linux!));
  assert.match(plain, /aria-label="Features: 1 of 2 checked"/);
  assert.doesNotMatch(plain, /cov-standin/);
});

test('what pickfit could check says how many of the features counted were a stand-in, only when some were', () => {
  assert.match(coverageSection(entry.coverage), /3 of 4 features reached a verdict, 1 of them against a stand-in/);
  assert.doesNotMatch(coverageSection(fixtureCatalog().bySlug.get(SLUG)!.coverage), /stand-in/);
});

test('compare does not count a stand-in feature toward the most features checked', () => {
  // Two entries with three passing features each; one of the first's is a stand-in, so the other has the most.
  const data = index();
  const other = structuredClone(data.entries.find((e: any) => e.slug === SLUG));
  other.slug = 'fixture-llm-runner-two';
  other.name = 'llm-runner-two';
  for (const f of other.install.linux.features) delete f.fidelity;
  const pair = [loadCatalog(data).bySlug.get(SLUG)!, other as Entry];
  const table = compareTable(pair, { os: 'linux', now: new Date('2026-10-30T12:00:00Z') });
  const cells = (table.match(/<tr><th scope="row">Features<\/th>.*?<\/tr>/s)?.[0] ?? '').split('<td>').slice(1);
  assert.equal(cells.length, 2);
  assert.match(cells[0], /aria-label="Features: 3 of 4 checked, 1 of them against a stand-in"/);
  assert.match(cells[1], /aria-label="Features: 3 of 4 checked"/);
  assert.deepEqual(cells.map((c) => c.includes('class="best"')), [false, true]);
});

test('the sentence that says which features worked leaves a stand-in feature out', () => {
  const ops = [SERVE, MAIL].map((feature) => ({ feature, passed: true }));
  assert.deepEqual(workedFeatures(ops, entry, features), { used: true, names: ['Serve models over an OpenAI-style API'] });
});

test('fidelity is a value the code compares: the zh-TW page never translates it', () => {
  const guide = translateWith({ stand_in: '替身', [MAIL]: '用電子郵件寄出報告' }, linux);
  const mail = guide.features!.find((f) => f.fidelity === 'stand_in')!;
  assert.equal(mail.feature, '用電子郵件寄出報告');
  assert.deepEqual(standInOnly(featuresOut(entry, guide)).length, 1);
  assert.equal(bestGuide(entry, 'linux'), linux);
});
