/**
 * The catalog pages (tool, browse, compare, how, agents, not found): served
 * from the bundled index with no model call, under the same CSP, and never
 * stating more than a run record shows. Also: the Fitz files the Worker serves
 * are the ones brand/mascot/build.py wrote.
 */
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import type { Env } from '../src/env.ts';
import { loadCatalog, type Entry } from '../src/catalog.ts';
import { compareTable, slugsFrom } from '../src/pages/compare.ts';
import { visualLine } from '../src/pages/tool.ts';
import { makeWorker } from '../src/worker.ts';
import { commandText, fixtureCatalog, fixtureIndex, makeD1 } from './helpers.ts';

function site(env: Partial<Env> = {}) {
  const d1 = makeD1();
  let metaCalls = 0;
  const worker = makeWorker(fixtureIndex(), {
    fetch: (async () => {
      metaCalls++;
      throw new Error('no model call expected');
    }) as unknown as typeof fetch,
    now: () => new Date('2026-10-30T12:00:00Z'),
  });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const get = (path: string, accept = 'text/html') =>
    worker.fetch(new Request(`http://127.0.0.1:8787${path}`, { headers: { accept } }), { DB: d1.db, MODEL_API_KEY: 'k', ...env } as Env, ctx);
  return { get, metaCalls: () => metaCalls };
}

test('every page answers with HTML under a nonce CSP that allows only this Worker’s images and font', async () => {
  const s = site();
  for (const path of ['/browse', '/compare', '/compare?tools=fixture-llm-runner,fixture-chat-tui', '/how', '/agents', '/tool/fixture-llm-runner']) {
    const res = await s.get(path);
    assert.equal(res.status, 200, path);
    assert.match(res.headers.get('content-type')!, /^text\/html/);
    const csp = res.headers.get('content-security-policy')!;
    assert.match(csp, /img-src 'self' data:; media-src 'self'; font-src 'self'/);
    const nonce = /script-src 'nonce-([0-9a-f]+)'/.exec(csp)![1];
    const html = await res.text();
    assert.ok(html.includes(`<script nonce="${nonce}">`) && html.includes(`<style nonce="${nonce}">`), path);
    assert.ok(!/ style="/.test(html), `${path} has an inline style attribute`);
  }
  assert.equal(s.metaCalls(), 0);
});

test('unknown tools and paths get the not-found page for a browser and the plain 404 otherwise; JSON health is unchanged', async () => {
  const s = site();
  const tool = await s.get('/tool/no-such-tool');
  assert.equal(tool.status, 404);
  assert.match(await tool.text(), /Page not found/);
  assert.equal((await s.get('/tool/%3Cscript%3E')).status, 404);
  assert.equal((await s.get('/nowhere')).status, 404);
  const plain = await s.get('/nowhere', 'application/json');
  assert.equal(plain.status, 404);
  assert.equal(await plain.text(), 'Not found');
  const health = await s.get('/', 'application/json');
  assert.match(health.headers.get('content-type')!, /application\/json/);
});

test('WEB_SEARCH=off serves none of the pages', async () => {
  const s = site({ WEB_SEARCH: 'off' });
  for (const path of ['/browse', '/tool/fixture-llm-runner', '/how']) assert.equal((await s.get(path)).status, 404, path);
});

test('a tool page shows how far each verified run got, its install steps, and the test evidence folded', async () => {
  const s = site();
  const html = await (await s.get('/tool/fixture-llm-runner')).text();
  assert.match(html, /<h1>Fixture LLM Runner<\/h1>/);
  assert.ok(html.includes('id="install-macos"') && html.includes('id="install-linux"'), 'one install card per verified OS');
  assert.equal(html.split('<div class="progress-row" data-os=').length - 1, 2, 'one progress row per verified OS');
  assert.match(html, /<details class="progress-more" data-progress-more hidden><summary>Other systems/, 'the script folds the other systems');
  assert.match(html, /<li class="prog-stage prog-done"[^>]*><span class="prog-bar"><\/span><span class="prog-label">.*Installs<\/span><\/li>/);
  assert.match(html, /data-tip="Tested on macOS and Linux"><svg class="i[^"]*"[^>]*>.*?<\/svg><span aria-hidden="true">Tested<\/span><svg class="os os-macos"/, 'the systems as marks, their names in the tooltip');
  // Use it is one section on the page ground (no card), the systems as tabs across its top, no fold inside it.
  assert.match(html, /<div class="use-it"><div class="os-tabs"/);
  assert.ok(!html.includes('<details class="install"'), 'no install fold inside Use it');
  assert.match(html, /<details class="block tested"><summary><h2>How pickfit tested it<\/h2>/);
  // Each run card names its system once, in the heading, with the OS mark.
  assert.match(html, /<h3><svg class="os os-macos"[^>]*><use href="#os-macos"\/><\/svg>macOS <span class="arch">arm64<\/span><\/h3>/);
  assert.match(html, /<h3><svg class="os os-linux"[^>]*><use href="#os-linux"\/><\/svg>Linux <span class="arch">x86_64<\/span><\/h3>/);
  assert.match(html, /<symbol id="os-linux"/, 'the page carries the OS marks it points at');
  assert.match(commandText(html), /brew install fixture\/tap\/fixture-llm-runner/);
  // The gem badge comes from the score.
  assert.match(html, /Hidden gem/);
  assert.match(html, /aria-label="Quality: \d+ out of 100/);
});

test('Compare is in the nav only on /compare (the script adds it while the tray holds tools); the footer always links to it', async () => {
  const s = site();
  const navOf = (html: string) => /<nav class="nav"[^>]*>(.*?)<\/nav>/s.exec(html)![1];
  for (const path of ['/', '/browse', '/how', '/tool/fixture-llm-runner']) {
    const html = await (await s.get(path)).text();
    assert.match(navOf(html), /<a href="\/compare" data-tray-link data-tray-nav hidden>/, path);
    assert.match(html, /<footer class="foot">.*<a href="\/compare">Compare tools<\/a>/s, path);
  }
  assert.match(navOf(await (await s.get('/compare')).text()), /<a href="\/compare" aria-current="page" data-tray-link data-tray-nav>/);
});

test('At a glance is a measurement sheet that never drops a fact: unverified and unstated stay visible, in words', async () => {
  const sheet = (html: string) => /<dl class="measure glance-sheet">(.*?)<\/dl>/s.exec(html)?.[1] ?? '';
  const row = (html: string, label: string) => new RegExp(`<div class="m[^"]*"><dt>${label}</dt><dd>(.*?)</dd></div>`, 's').exec(sheet(html));
  const verified = await (await site().get('/tool/fixture-llm-runner')).text();
  assert.ok(sheet(verified), 'the facts are one measure() sheet');
  // What a run proved: the OS marks, each system named on hover and for screen readers (three names would not fit a row).
  assert.match(sheet(verified), /<div class="m m-pass[^"]*"><dt>Verified on<\/dt><dd><span class="oses oses-pass" data-tip="macOS and Linux">.*?<span class="sr">macOS and Linux<\/span><\/span><\/dd>/s, 'what a run proved: marks, named');
  // The same tool with no run and no price: both rows stay, said in words.
  const index = fixtureIndex() as { entries: { slug: string; install: Record<string, unknown>; pricing: string | null }[] };
  const entry = index.entries.find((e) => e.slug === 'fixture-llm-runner')!;
  entry.install = {};
  entry.pricing = null;
  const worker = makeWorker(index, { fetch: (async () => { throw new Error('no model call expected'); }) as unknown as typeof fetch, now: () => new Date('2026-10-30T12:00:00Z') });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const raw = await (await worker.fetch(new Request('http://127.0.0.1:8787/tool/fixture-llm-runner', { headers: { accept: 'text/html' } }), { DB: makeD1().db, MODEL_API_KEY: 'k' } as Env, ctx)).text();
  assert.match(sheet(raw), /<div class="m m-caution[^"]*"><dt>Verified on<\/dt><dd>Not verified yet<\/dd>/);
  assert.match(row(raw, 'Price')?.[0] ?? '', /m-quiet/);
  assert.equal(row(raw, 'Price')?.[1], '<span class="unknown">not stated</span>');
});

test('a verified tool page leads with how to use it (how far each run got below it); an unverified one leads with that fact', async () => {
  const s = site();
  const at = (html: string, id: string) => html.indexOf(`id="${id}"`);
  const html = await (await s.get('/tool/fixture-llm-runner')).text();
  assert.ok(at(html, 'install-title') > 0 && at(html, 'install-title') < at(html, 'progress-title'), 'install before progress');
  // Without a clip, how to use it comes before what it does.
  if (at(html, 'about-title') > 0) assert.ok(at(html, 'install-title') < at(html, 'about-title'), 'install before what it does');
  assert.ok(html.split('>Good for</h').length <= 2, 'Good for once');
  // The same tool with no run: the page says so first.
  const index = fixtureIndex() as { entries: { slug: string; install: Record<string, unknown> }[] };
  index.entries.find((e) => e.slug === 'fixture-llm-runner')!.install = {};
  const worker = makeWorker(index, { fetch: (async () => { throw new Error('no model call expected'); }) as unknown as typeof fetch, now: () => new Date('2026-10-30T12:00:00Z') });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const res = await worker.fetch(new Request('http://127.0.0.1:8787/tool/fixture-llm-runner', { headers: { accept: 'text/html' } }), { DB: makeD1().db, MODEL_API_KEY: 'k' } as Env, ctx);
  const raw = await res.text();
  assert.match(raw, /pickfit hasn’t verified Fixture LLM Runner yet/);
  const install = at(raw, 'install-title');
  assert.ok(at(raw, 'progress-title') > 0 && (install < 0 || at(raw, 'progress-title') < install), 'progress first');
});

test('install steps come one stage at a time: install, then check, each with Back and Next naming the other', async () => {
  const html = await (await site().get('/tool/fixture-llm-runner')).text();
  assert.match(html, /<div class="install-body" data-stepper><ol class="stage-tabs js-only">.*?<span class="lbl">Install<\/span>.*?<span class="lbl">Check it works<\/span>/);
  // What you need first opens the install stage of each system, not a block above the systems.
  assert.match(html, /<section class="inst-stage" data-stage aria-label="Install"><div class="prereq"><h4>You need first<\/h4>.*?<ol class="steps">/);
  assert.doesNotMatch(html, /<h2 id="install-title">Use it<\/h2><div class="prereq">/);
  assert.match(html, /data-goto="1">Next: Check it works/);
  assert.match(html, /data-goto="0">.*?Back: Install<\/button>/);
});

test('what it does: plain titles from the usage guide, steps only for a feature the run checked, why not only in a tooltip', async () => {
  const html = await (await site().get('/tool/fixture-llm-runner')).text();
  assert.match(html, /<li class="feat-ok"><div><span class="feat-title">Serve models over an OpenAI-style API<\/span><details class="how-to"><summary>How to use it<\/summary><ol><li>Run <code translate="no">fixture-llm-runner serve<\/code>\.<\/li>.*?<span class="feat-state">.*?Tested<\/span><\/li>/);
  // An untested feature is greyed, with why only in its mark's tooltip: no line under the title, no note on who wrote the list.
  assert.match(html, /<li class="feat-open"><div><span class="feat-title">Download models from a registry<\/span><\/div><span class="feat-state" tabindex="0" data-tip="[^"]+">.*?Not tested<\/span><\/li>/);
  assert.ok(!html.includes('written by'));
  // A tool without a guide still lists its features, under the README's own words.
  const plain = await (await site().get('/tool/fixture-transcribe')).text();
  assert.match(plain, /<span class="feat-title">Transcribe audio files offline<\/span>/);
  assert.ok(!plain.includes('written by'));
});

test('a run card says when the sandbox had a GPU or a simulated microphone, and only then', async () => {
  const s = site();
  const html = await (await s.get('/tool/fixture-transcribe')).text();
  assert.match(html, /data-tip="The sandbox had this GPU">.*GPU: Tesla T4<\/li>/);
  assert.match(html, /data-tip="A simulated microphone played words pickfit spoke for each check">.*Simulated microphone<\/li>/);
  const plain = await (await s.get('/tool/fixture-llm-runner')).text();
  assert.ok(!plain.includes('GPU:') && !plain.includes('Simulated microphone'));
});

test('browse lists verified tools only unless asked, filters by plain links, and keeps typed text out of URLs', async () => {
  const s = site();
  const all = await (await s.get('/browse')).text();
  assert.equal(all.split('<li class="cat-card"').length - 1, 7);
  const mac = await (await s.get('/browse?os=macos')).text();
  // The web app was checked in a browser, so it runs on any OS.
  assert.equal(mac.split('<li class="cat-card"').length - 1, 2);
  assert.match(mac, /href="\/tool\/fixture-llm-runner"/);
  assert.match(mac, /href="\/tool\/fixture-web-sketch"/);
  const web = await (await s.get('/browse?kind=web_app')).text();
  assert.equal(web.split('<li class="cat-card"').length - 1, 1);
  assert.match(web, /Checked in a browser, any OS/);
  const mcp = await (await s.get('/browse?kind=mcp_server')).text();
  assert.equal(mcp.split('<li class="cat-card"').length - 1, 1);
  // The text filter is an input with no name: it never becomes a query parameter.
  assert.match(all, /<input type="search" data-filter placeholder="Filter by name or task" autocomplete="off">/);
  assert.ok(!/<input[^>]*name="q"/.test(all));
  // Junk parameters are ignored, never echoed.
  const junk = await (await s.get('/browse?kind=%3Cx%3E&os=beos')).text();
  assert.ok(!junk.includes('<x>') && !junk.includes('beos'));
});

test('compare takes two to four known tools, marks "best" only on recorded numbers, and says where each ran', async () => {
  const catalog = fixtureCatalog();
  assert.deepEqual(slugsFrom(new URLSearchParams('tools=fixture-llm-runner,FIXTURE-CHAT-TUI,nope,fixture-llm-runner'), catalog), ['fixture-llm-runner', 'fixture-chat-tui']);
  assert.equal(slugsFrom(new URLSearchParams('tools=a,b&add=fixture-json-query'), catalog).join(), 'fixture-json-query');
  // The add field suggests names; a name typed in full works as well as the slug.
  assert.deepEqual(slugsFrom(new URLSearchParams('tools=fixture-llm-runner&add=Fixture JSON Query'), catalog), ['fixture-llm-runner', 'fixture-json-query']);
  const slugs = ['fixture-llm-runner', 'fixture-chat-tui', 'fixture-json-query', 'fixture-transcribe', 'fixture-notes-mcp'].join(',');
  assert.equal(slugsFrom(new URLSearchParams(`tools=${slugs}`), catalog).length, 4);

  const table = compareTable([catalog.bySlug.get('fixture-llm-runner')!, catalog.bySlug.get('fixture-chat-tui')!], { os: 'macos', now: new Date(catalog.built_at) });
  assert.match(table, /<span class="oses oses-pass" data-tip="macOS and Linux, including yours">/);
  assert.match(table, /<span class="oses oses-caution" data-tip="Linux only, not macOS">/);
  for (const best of table.split('best here').slice(0, -1)) {
    const row = best.slice(best.lastIndexOf('<th scope="row">'));
    assert.match(row, /^<th scope="row">(Install|Quality|Features|Last release)<\/th>/, 'best is marked only on plain recorded comparisons');
  }

  const s = site();
  const one = await (await s.get('/compare?tools=fixture-llm-runner')).text();
  assert.match(one, /Add one more to compare with Fixture LLM Runner/);
  assert.ok(!one.includes('<table class="dt cmp-table">'));
});

test('the how page states the scoring as score.py computes it', async () => {
  const html = await (await site().get('/how')).text();
  assert.match(html, /40%/);
  assert.match(html, /25%/);
  assert.match(html, /quality score drops by 5%; finding none adds nothing/);
  assert.match(html, /not visually checked and keeps its score/);
  assert.doesNotMatch(html, /15%/);
  assert.match(html, /quality 80 or more and popularity 45 or less/);
});

test('the Fitz files the Worker serves are the ones brand/mascot/build.py wrote', () => {
  const brand = new URL('../../brand/mascot/', import.meta.url).pathname;
  const served = new URL('../public/assets/fitz/', import.meta.url).pathname;
  const walk = (dir: string, base = ''): string[] =>
    readdirSync(join(dir, base)).flatMap((name) => {
      const rel = join(base, name);
      return statSync(join(dir, rel)).isDirectory() ? walk(dir, rel) : [rel];
    });
  const files = walk(served);
  assert.ok(files.length >= 25);
  for (const rel of files) {
    assert.equal(readFileSync(join(served, rel), 'utf8'), readFileSync(join(brand, rel), 'utf8'), `${rel} differs: run npm run sync:assets`);
  }
});

test('a web app opens from an address bar that ends in the button, its facts two to a row below', async () => {
  const html = await (await site().get('/tool/fixture-web-sketch')).text();
  assert.match(html, /<div class="web-bar"><span class="web-addr"><svg[^>]*>.*?<\/svg><span translate="no">fixture-sketch\.example\.invalid<\/span><\/span><a [^>]*class="btn btn-primary btn-sm"/);
  assert.match(html, /<ul class="web-facts web-facts-grid">/);
});


test('a desktop or web app says what the visual check found: a defect and its -5%, none, or not checked', async () => {
  const base = fixtureIndex() as { entries: Entry[] };
  const render = (visual: Entry['visual']) => {
    const index = structuredClone(base);
    index.entries.find((e) => e.slug === 'fixture-web-sketch')!.visual = visual;
    return visualLine(loadCatalog(index).bySlug.get('fixture-web-sketch')!);
  };
  const defect = render({ status: 'defect', factor: 0.95, defects: [{ kind: 'overlap', problem: 'A <b>button</b> covers the title.', quote: 'Sketch' }] });
  assert.match(defect, /Visual check found a defect: −5%/);
  assert.match(defect, /<li>A &lt;b&gt;button&lt;\/b&gt; covers the title\.<\/li>/);
  assert.match(render({ status: 'clean', factor: 1, defects: [] }), /Visual check: no defect found\./);
  const none = render({ status: 'not_checked' });
  assert.match(none, /Not visually checked/);
  assert.doesNotMatch(none, /−5%|defect found/);
  assert.equal(render(null), '');
  // The tool page shows the line from the index: the fixture web app has no check.
  const html = await (await site().get('/tool/fixture-web-sketch')).text();
  assert.match(html, /class="small quiet visual-check">Not visually checked yet, so nothing is taken off\./);
  assert.doesNotMatch(html, /no screenshots/);
});
