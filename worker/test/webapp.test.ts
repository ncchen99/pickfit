/**
 * Hosted web apps (kind web_app, brief 2.2): the hard filters (offline only as a PWA checked offline, local data
 * only when nothing typed left the device), "no install, just open it" first among equal fits unless the job leans
 * to installed tools, the cards and the guard, the guide that is a URL, the check-in that only asks, the submission
 * of a website, and the page.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadCatalog, webCheck, type Catalog, type Entry, type WebCheck } from '../src/catalog.ts';
import { CARD_FIELDS, toCard, WEB_FIELDS } from '../src/cards.ts';
import { hardFilter, type Conditions } from '../src/filter.ts';
import { findSoftware } from '../src/find.ts';
import { contradiction } from '../src/guard.ts';
import { installGuide } from '../src/install.ts';
import { esc, renderResults, EMPTY_FORM } from '../src/page.ts';
import { webRunWords } from '../src/ui/facts.ts';
import { MATCH_INSTRUCTIONS } from '../src/prompt.ts';
import { leansInstall, rankByRules, WEB_BAND } from '../src/rules.ts';
import { normalizeWebUrl, submitSoftware } from '../src/submit.ts';
import { makeWorker } from '../src/worker.ts';
import { logEvent } from '../src/events.ts';
import type { Env } from '../src/env.ts';
import { fixtureIndex, harness, makeD1 } from './helpers.ts';

const SLUG = 'fixture-web-sketch';

/** The fixture catalog with the web app's check changed (null: no browser run passed). */
function withCheck(change: Partial<WebCheck> | null): Catalog {
  const data = structuredClone(fixtureIndex()) as any;
  const entry = data.entries.find((e: any) => e.slug === SLUG);
  entry.web.check = change === null ? null : { ...entry.web.check, ...change };
  return loadCatalog(data);
}

const passes = (catalog: Catalog, cond: Conditions) => hardFilter(catalog.entries, cond).candidates.some((e) => e.slug === SLUG);

test('offline needs a PWA pickfit reloaded offline; local data needs nothing typed to have left; unknown does not qualify', () => {
  const ok = withCheck({});
  for (const cond of [{}, { offline: true }, { data_stays_local: true }, { must_run_locally: true }] as Conditions[]) {
    assert.ok(passes(ok, cond), JSON.stringify(cond));
  }
  for (const offline of ['not_offline', 'not_tested'] as const) {
    const c = withCheck({ offline });
    assert.ok(!passes(c, { offline: true }) && !passes(c, { must_run_locally: true }), offline);
    assert.ok(passes(c, { data_stays_local: true }) && passes(c, {}), `${offline}: other conditions still pass`);
  }
  for (const data_sent of ['observed', 'unknown'] as const) {
    const c = withCheck({ data_sent });
    assert.ok(!passes(c, { data_stays_local: true }) && !passes(c, { must_run_locally: true }), data_sent);
    assert.ok(passes(c, { offline: true }), `${data_sent}: offline alone still passes`);
  }
});

test('a web app opens in any browser: the OS never filters it out, but a site no browser run passed on never qualifies', () => {
  for (const os of ['macos', 'linux', 'windows'] as const) assert.ok(passes(withCheck({}), { os, arch: 'arm64' }), os);
  assert.ok(!passes(withCheck(null), {}));
  assert.ok(!passes(withCheck({}), { category: 'dev_cli' }), 'its category still filters');
  assert.ok(!passes(withCheck({}), { exclude: [SLUG] }));
});

/** Two entries the rules see: a web app and a tool to install, with the given relevance each. */
function pair(web: number, install: number) {
  const catalog = withCheck({});
  const sketch = catalog.bySlug.get(SLUG)!;
  const tool = catalog.bySlug.get('fixture-json-query')!;
  const relevance = new Map([[sketch.slug, web], [tool.slug, install]]);
  return (lean = false, os?: 'macos') => rankByRules([tool, sketch], relevance, os, undefined, lean).map((e: Entry) => e.slug);
}

test('rules: fit first; within WEB_BAND a web app goes ahead of a tool to install, even one verified on the user OS', () => {
  assert.deepEqual(pair(1, 1)(), [SLUG, 'fixture-json-query']);
  assert.deepEqual(pair(0.95, 1)(false, 'macos'), [SLUG, 'fixture-json-query'], 'about equal: no install first');
  assert.deepEqual(pair(1 - WEB_BAND * 2, 1)(), ['fixture-json-query', SLUG], 'clearly less fit: fit decides');
  assert.deepEqual(pair(1, 0.5)(), [SLUG, 'fixture-json-query']);
  assert.deepEqual(pair(0.5, 1)(), ['fixture-json-query', SLUG]);
});

test('rules: background work, system integration, many local files or a terminal tool lean to installed tools', () => {
  assert.deepEqual(pair(1, 0.95)(true), ['fixture-json-query', SLUG]);
  assert.deepEqual(pair(1, 0.5)(true), [SLUG, 'fixture-json-query'], 'the lean only breaks near ties');
  for (const need of ['run a sync in the background', 'a global hotkey to paste snippets', 'rename thousands of photos in a folder', 'a CLI to convert CSV']) {
    assert.ok(leansInstall(need), need);
  }
  for (const need of ['draw a flowchart and export a PNG', 'convert a color between hex and rgb', 'make a quick invoice']) {
    assert.ok(!leansInstall(need), need);
  }
});

test('find_software by rules: the web app comes first among equal fits, labelled, with no install steps behind it', async () => {
  const h = harness(null, { modelEnabled: false });
  const out = await findSoftware({ need: 'draw a flowchart diagram and export it as PNG' }, h.deps);
  const pick = out.picks[0];
  assert.equal(pick.slug, SLUG);
  assert.equal(pick.web_app?.label, 'No install, just open it');
  assert.deepEqual([pick.web_app?.url, pick.web_app?.checked_at, pick.web_app?.works_offline], ['https://fixture-sketch.example.invalid/', '2026-11-02T09:00:00Z', 'verified']);
  assert.deepEqual([pick.verification.level, pick.verification.os, pick.verification.verified_on_user_os, pick.repo], ['function', null, null, null]);
  assert.match(pick.how_we_know, /opened it in a sandboxed browser .* on 2026-11-02; the page loaded to its main screen, and a model \(Muse Spark\) then used it/);
  assert.ok(pick.why.some((r) => r.field === 'no_install'), 'the template reasons say there is nothing to install');
  assert.deepEqual([pick.features.recorded, pick.features.checked.length], [true, 2]);
});

test('cards: only a web app carries the browser facts, and the model may cite them', () => {
  const catalog = withCheck({});
  const card = toCard(catalog.bySlug.get(SLUG)!, 'macos');
  assert.deepEqual(
    WEB_FIELDS.map((f) => card[f]),
    [true, false, false, 1, 'none', 'verified'],
  );
  assert.equal(card.verified_on_user_os, null);
  assert.match((card.verified_on as string[])[0], /^any OS, in a browser: .* function check passed, 2026-11-02$/);
  const other = toCard(catalog.bySlug.get('fixture-json-query')!, 'macos');
  assert.ok(WEB_FIELDS.every((f) => !(f in other)), 'other cards stay as small as before');
  assert.ok(WEB_FIELDS.every((f) => (CARD_FIELDS as readonly string[]).includes(f)));
  assert.match(MATCH_INSTRUCTIONS, /Among tools that fit about equally, put a web app \(no_install true\) first, unless the job runs long or in the background/);
  assert.equal(card.network, 'optional', 'a PWA checked offline needs the network only to load');
  assert.equal(toCard(withCheck({ offline: 'not_tested' }).bySlug.get(SLUG)!).network, 'required');
  assert.match(MATCH_INSTRUCTIONS, /works offline only if works_offline is "verified", and keeps typed data on the device only if data_sent is "none"/);
});

test('guard: a web app is offline, private, account-free or ad-free only as far as its browser run showed', () => {
  const card = (change: Partial<WebCheck>) => toCard(withCheck(change).bySlug.get(SLUG)!);
  assert.equal(contradiction(card({}), 'Works offline once loaded'), null);
  assert.equal(contradiction(card({ offline: 'not_tested' }), 'Works offline once loaded'), 'claims a web app works offline');
  assert.equal(contradiction(card({}), 'Your drawings stay on your device, fully local'), null);
  assert.equal(contradiction(card({ data_sent: 'unknown' }), 'Private: nothing leaves your machine'), 'claims a web app keeps data local');
  assert.equal(contradiction(card({ account_needed: null }), 'No account needed'), 'claims it needs no account');
  assert.equal(contradiction(card({ ads_seen: true }), 'Ad-free'), 'claims it has no ads');
});

test('get_install_guide for a web app: open this URL, the checked facts and the date, and a check-in that only asks', () => {
  const now = new Date('2026-11-02T12:00:00Z');
  const out = installGuide(withCheck({ data_sent: 'unknown', ads_seen: true }), { slug: SLUG, os: 'macos' }, now);
  assert.deepEqual([out.steps, out.verify, out.first_task, out.mcp_client_config], [[], null, null, null]);
  assert.deepEqual(out.manual_steps, [{ title: 'Open https://fixture-sketch.example.invalid/ in a browser. Nothing to install.', run_by: 'user' }]);
  assert.deepEqual([out.verification.status, out.verification.level, out.verification.checked_at, out.verification.works_offline], ['verified', 'function', '2026-11-02T09:00:00Z', true]);
  assert.deepEqual([out.web_app?.label, out.web_app?.data_sent, out.web_app?.ads_seen, out.web_app?.third_party_domains], ['No install, just open it', 'unknown', true, 1]);
  assert.equal(out.applies_to_user_system.match, 'exact');
  assert.match(out.how_we_know, /Nothing to install: open https:\/\/fixture-sketch\.example\.invalid\/ in a browser\./);
  assert.ok(out.warnings.some((w) => /did not check whether what the user types leaves/.test(w)));
  assert.ok(out.warnings.some((w) => /shows ads/.test(w)));
  assert.deepEqual(out.check_in?.commands, []);
  assert.match(out.check_in?.how ?? '', /Only ask: never read their browser history, bookmarks, cookies, open tabs/);
  // Software to install keeps its steps and has no web_app.
  assert.equal(installGuide(withCheck({}), { slug: 'fixture-json-query', os: 'linux' }, now).web_app, null);
  // Not checked yet: no facts, no check-in, said as such.
  const never = installGuide(withCheck(null), { slug: SLUG, os: 'linux' }, now);
  assert.deepEqual([never.verification.status, never.applies_to_user_system.match, never.check_in], ['unverified', 'none', null]);
});

test('submit_software takes the https URL of a web app into the same queue, and knows a listed one', async () => {
  assert.equal(normalizeWebUrl('https://Tools.Example.com/app/?ref=hn#top'), 'https://tools.example.com/app');
  assert.equal(normalizeWebUrl('https://example.com'), 'https://example.com/');
  for (const url of ['http://example.com/', 'https://user:pw@example.com/', 'https://example.com:8443/', 'https://192.168.1.2/', 'https://intranet/', 'https://foo.local/', 'https://github.com/', 'https://gitlab.com/a/b']) {
    assert.equal(normalizeWebUrl(url), null, url);
  }
  const h = harness(null);
  // A listed web app on a public host (the fixture's .invalid host is never accepted).
  const data = structuredClone(fixtureIndex()) as any;
  data.entries.find((e: any) => e.slug === SLUG).web.url = 'https://sketch.example.com/';
  const deps = { catalog: loadCatalog(data), db: h.deps.db, now: h.deps.now, hourlyCap: 20 };
  const first = await submitSoftware({ url: 'https://Tools.Example.com/app/', submitter_role: 'author' }, deps);
  assert.deepEqual([first.status, first.url, first.already_submitted], ['queued', 'https://tools.example.com/app', false]);
  assert.match(first.next, /sandboxed browser/);
  const again = await submitSoftware({ url: 'https://tools.example.com/app?utm=x' }, deps);
  assert.deepEqual([again.already_submitted, again.submission_id], [true, first.submission_id]);
  const listed = await submitSoftware({ url: 'https://Sketch.example.com' }, deps);
  assert.deepEqual([listed.status, listed.slug, listed.submission_id], ['listed', SLUG, null]);
});

test('page: a web app ticket opens the URL, says no install, and shows what the browser saw', async () => {
  const h = harness(null, { modelEnabled: false });
  const catalog = h.deps.catalog;
  const out = await findSoftware({ need: 'draw a flowchart diagram and export it as PNG' }, h.deps);
  const guides = Object.fromEntries(out.picks.map((p) => [p.slug, installGuide(catalog, { slug: p.slug, os: 'linux' })]));
  const html = renderResults({ out, guides }, EMPTY_FORM, catalog);
  const ticket = html.slice(html.indexOf(`id="pick-${SLUG}"`), html.indexOf('</article>', html.indexOf(`id="pick-${SLUG}"`)));
  assert.match(ticket, /No install, just open it/);
  assert.match(ticket, /href="https:\/\/fixture-sketch\.example\.invalid\/"[^>]*>.*Open the site/);
  assert.match(ticket, /Any browser/);
  assert.match(ticket, /Nothing to install/);
  assert.match(ticket, /What pickfit typed in stayed on the device/);
  assert.match(ticket, /Works offline once loaded \(checked\)/);
  assert.ok(!ticket.includes('Source code'), 'no repository, no source link');
  assert.ok(!ticket.includes('Install steps that worked'));
  // The run in the reader's words, as the tool page says it (same day, same features): not the agents' sentence with
  // the browser build, the model and the replay rule.
  const entry = catalog.bySlug.get(SLUG)!;
  assert.ok(ticket.includes(esc(webRunWords(entry, webCheck(entry)!))));
  assert.match(ticket, /When pickfit opened it in a browser on \d{1,2} \w{3} \d{4}, the page loaded to its main screen\./);
  assert.doesNotMatch(ticket, /Chromium|headless|Muse Spark|visited once|no replay/);
});

test('page: the tool page of a web app, browse and compare', async () => {
  const d1 = makeD1();
  const worker = makeWorker(fixtureIndex(), { now: () => new Date('2026-11-02T12:00:00Z') });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const get = async (path: string) =>
    (await worker.fetch(new Request(`http://127.0.0.1:8787${path}`, { headers: { accept: 'text/html' } }), { DB: d1.db, MODEL_API_KEY: 'k' } as Env, ctx)).text();
  const tool = await get(`/tool/${SLUG}`);
  assert.match(tool, /<h1>Fixture Web Sketch<\/h1>/);
  assert.match(tool, /Tested in a browser/);
  assert.match(tool, /It worked when used in a browser/);
  assert.match(tool, /href="\/browse\?kind=web_app">Web apps</);
  assert.match(tool, /id="run-web"/);
  assert.match(tool, /Open the site/);
  assert.match(tool, /Any modern browser, nothing to install/);
  assert.ok(!tool.includes('Before you install') && !tool.includes('Source code'));
  assert.ok(!tool.includes('This run came before'), 'its browser run recorded features');
  const cmp = await get(`/compare?tools=${SLUG},fixture-json-query`);
  assert.match(cmp, /Nothing to install, just open it/);
  assert.match(cmp, /In a browser, any OS/);
  const how = await get('/how');
  assert.match(how, /<h3 id="web">Web apps: no install, just open it<\/h3>/);
  assert.match(how, /1 web app passed so far/);
  assert.match(how, /its quality is the browser run 50% .* what the browser saw 40%/);
  const home = await get('/');
  assert.match(home, /name="private" value="1"/);
  assert.match(home, /<strong>1<\/strong> web app tried in a browser/);
});

test('report_outcome: a failed web app is stored for its next browser check, never queued for an install re-run', async () => {
  const { reportOutcome } = await import('../src/outcome.ts');
  const h = harness(null, { modelEnabled: false });
  const guide = installGuide(h.deps.catalog, { slug: SLUG, os: 'macos' });
  await logEvent(h.deps.db, h.deps.now(), { type: 'install_guide', slug: SLUG, os: 'macos', rec_id: guide.rec_id, results: ['exact'] });
  const out = await reportOutcome(
    { slug: SLUG, stage: 'first_run_failed', rec_id: guide.rec_id, os: 'macos', error_excerpt: 'The page stayed blank' },
    { catalog: h.deps.catalog, db: h.deps.db, now: h.deps.now, reporter: 'dev' },
  );
  assert.deepEqual([out.accepted, out.counted_in_score, out.reverify], [true, true, 'none']);
  assert.equal((h.sqlite.prepare('SELECT count(*) AS n FROM reverify_queue').get() as any).n, 0);
  assert.equal((h.sqlite.prepare("SELECT error_excerpt FROM events WHERE type = 'outcome'").get() as any).error_excerpt, 'The page stayed blank');
});

test('page: a web app no browser run passed on says so, and its features come from its own site', async () => {
  const data = structuredClone(fixtureIndex()) as any;
  data.entries.find((e: any) => e.slug === SLUG).web.check = null;
  const worker = makeWorker(data, { now: () => new Date('2026-11-02T12:00:00Z') });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const res = await worker.fetch(new Request(`http://127.0.0.1:8787/tool/${SLUG}`, { headers: { accept: 'text/html' } }), { DB: makeD1().db, MODEL_API_KEY: 'k' } as Env, ctx);
  const html = await res.text();
  assert.match(html, /pickfit hasn’t checked Fixture Web Sketch in its browser yet<\/b>\./);
  assert.doesNotMatch(html, /never suggests it/); // pickfit's own policy is the How page's, not this page's
  assert.match(html, /Not verified yet/);
  assert.match(html, /pickfit hasn’t run it yet, so these come from its own site only\./);
  assert.ok(!html.includes('Checked in a browser'));
});
