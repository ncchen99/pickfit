/**
 * The known-vulnerability check (OSV.dev, pickfit/index.py _security): the tool
 * page's mark and its warning before the install steps in both languages, the How page, and the security field that
 * find_software, find_alternatives and get_install_guide carry, with the
 * install guide's warning. A vulnerable tool is capped at 79 quality upstream;
 * an unchecked one keeps its score and says so.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadCatalog, type Entry, type SecurityCheck } from '../src/catalog.ts';
import type { Env } from '../src/env.ts';
import { findSoftware } from '../src/find.ts';
import { withLang } from '../src/i18n.ts';
import { installGuide } from '../src/install.ts';
import { EMPTY_FORM, renderResults } from '../src/page.ts';
import { securityMark, securityNotice } from '../src/pages/tool.ts';
import { makeWorker } from '../src/worker.ts';
import { answer, fixtureIndex, harness, makeD1, metaResponse } from './helpers.ts';

const SLUG = 'fixture-llm-runner';

const VULNERABLE: SecurityCheck = {
  status: 'vulnerable',
  checked_at: '2026-11-03',
  packages_checked: 115,
  count: 7,
  findings: [
    { package: 'npm:undici', version: '8.9.0', advisory: 'GHSA-abcd-1234-wxyz', severity: 'HIGH', fixed_in: '8.12.2', summary: 'A <b>bad</b> parser.', malicious: false },
    { package: 'crates.io:time', version: '0.1.0', advisory: 'RUSTSEC-2020-0071', severity: 'CRITICAL', fixed_in: null, summary: 'Segfault.', malicious: false },
  ],
};
const CLEAN: SecurityCheck = { status: 'clean', checked_at: '2026-11-03', packages_checked: 115 };

/** The fixture index with one entry's security replaced (undefined: an index from before the check). */
function indexWith(security: SecurityCheck | null | undefined, slug = SLUG) {
  const index = structuredClone(fixtureIndex()) as { entries: Entry[] };
  const entry = index.entries.find((e) => e.slug === slug)!;
  if (security === undefined) delete entry.security;
  else entry.security = security;
  return index;
}

const markFor = (security: SecurityCheck | null | undefined, language: 'en' | 'zh-TW' = 'en') =>
  withLang(language, () => securityMark(loadCatalog(indexWith(security)).bySlug.get(SLUG)!));
const noticeFor = (security: SecurityCheck | null | undefined, language: 'en' | 'zh-TW' = 'en') =>
  withLang(language, () => securityNotice(loadCatalog(indexWith(security)).bySlug.get(SLUG)!));

/** Three findings on two packages: the warning names the worst two packages and folds all three. */
const THREE: SecurityCheck = {
  ...VULNERABLE,
  findings: [
    ...VULNERABLE.findings!,
    { package: 'npm:undici', version: '8.9.0', advisory: 'GHSA-efgh-5678-wxyz', severity: 'HIGH', fixed_in: '8.12.2', summary: 'Another one.', malicious: false },
  ],
};

function site(index: unknown) {
  const d1 = makeD1();
  const worker = makeWorker(index, {
    fetch: (async () => {
      throw new Error('no model call expected');
    }) as unknown as typeof fetch,
    now: () => new Date('2026-11-03T12:00:00Z'),
  });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  return (path: string) =>
    worker.fetch(new Request(`http://127.0.0.1:8787${path}`, { headers: { accept: 'text/html' } }), { DB: d1.db, MODEL_API_KEY: 'k', MATCH_MODE: 'off' } as Env, ctx);
}

test('tool page, vulnerable: a red shield with the count and its source, jumping to the warning that lists each advisory', () => {
  const mark = markFor(VULNERABLE);
  const say = '7 known high or critical vulnerabilities in packages it installs \\(OSV\\.dev, 3 Nov 2026\\)\\. See the list';
  assert.match(mark, new RegExp(`^<a class="check-mark mark-fail" href="#security" data-tip="${say}"><svg class="i i-shield-alert"`));
  assert.match(mark, new RegExp(`<span class="check-count" aria-hidden="true">7</span><span class="sr">${say}</span></a>$`));
  // The score's rules are the How page's: the mark says what is vulnerable, not what it does to the score.
  assert.doesNotMatch(mark, /capped|79|hidden gem/);
  const zhMark = markFor(VULNERABLE, 'zh-TW');
  assert.match(zhMark, /data-tip="它安裝的套件有 7 個已知的高風險或嚴重漏洞（OSV\.dev，2026年11月3日）。看清單"/);
  assert.doesNotMatch(zhMark, /寶藏|79/);

  // The warning names the worst two packages, folds the rest the check kept (each once, linked to OSV.dev), and says how
  // many more it counted.
  const notice = noticeFor(THREE);
  const at = notice.indexOf('<details class="vuln-list small">');
  const top = notice.slice(0, at);
  const fold = notice.slice(at);
  assert.match(top, /<code>npm:undici 8\.9\.0<\/code> A &lt;b&gt;bad&lt;\/b&gt; parser\. \(<a [^>]*>GHSA-abcd-1234-wxyz<\/a>, high, fixed in 8\.12\.2\)<\/li>/);
  assert.match(top, /RUSTSEC-2020-0071<\/a>, critical, no fix yet\)<\/li>/);
  assert.match(fold, /^<details class="vuln-list small"><summary>See 1 more<\/summary><ul>/);
  assert.match(
    fold,
    /<li><code>npm:undici 8\.9\.0<\/code> — <a href="https:\/\/osv\.dev\/vulnerability\/GHSA-efgh-5678-wxyz" target="_blank" rel="noopener noreferrer">GHSA-efgh-5678-wxyz<\/a> \(high\), fixed in 8\.12\.2<\/li>/,
  );
  // No advisory is listed twice: the two named above are not in the fold.
  assert.doesNotMatch(fold, /GHSA-abcd-1234-wxyz|RUSTSEC-2020-0071/);
  for (const advisory of ['GHSA-abcd-1234-wxyz', 'RUSTSEC-2020-0071', 'GHSA-efgh-5678-wxyz']) {
    assert.equal(notice.split(`>${advisory}</a>`).length - 1, 1, `${advisory} is listed once`);
  }
  assert.match(fold, /4 more not listed here\./);
  assert.doesNotMatch(fold, /Another one/); // the fold leaves out each advisory's own summary
  assert.doesNotMatch(notice, /capped|hidden gem|79/);

  const zh = noticeFor(THREE, 'zh-TW');
  assert.match(zh, /<summary>再看 1 個<\/summary>/);
  assert.match(zh, /GHSA-abcd-1234-wxyz<\/a>，高風險，8\.12\.2 已修正）<\/li>/);
  assert.match(zh, /RUSTSEC-2020-0071<\/a>，嚴重，尚無修正版本）<\/li>/);
  assert.match(zh, /GHSA-efgh-5678-wxyz<\/a>（高風險），8\.12\.2 已修正<\/li>/);
  assert.match(zh, /另有 4 個未列出。/);
  assert.doesNotMatch(zh, /寶藏|品質最高/);

  // One finding: singular, nothing more to list or fold; a malicious package is named as such.
  const single = { ...VULNERABLE, count: 1, findings: [{ ...VULNERABLE.findings![0], advisory: 'MAL-2026-1', malicious: true }] };
  assert.match(markFor(single), /data-tip="1 known high or critical vulnerability in packages it installs/);
  const one = noticeFor(single);
  assert.match(one, /MAL-2026-1<\/a>, malicious package\)<\/li>/);
  assert.doesNotMatch(one, /more not listed|vuln-list/);
});

test('tool page, clean: a green shield, with the source, the date and how many packages', () => {
  const say = 'No known high or critical vulnerabilities \\(OSV\\.dev, checked 3 Nov 2026, 115 packages\\)';
  const mark = markFor(CLEAN);
  assert.match(mark, new RegExp(`^<span class="check-mark mark-pass" tabindex="0" data-tip="${say}"><svg class="i i-shield-check"`));
  assert.match(mark, new RegExp(`<span class="sr">${say}</span></span>$`));
  assert.match(markFor(CLEAN, 'zh-TW'), /data-tip="沒有已知的高風險或嚴重漏洞（OSV\.dev，2026年11月3日 檢查，共 115 個套件）"/);
  assert.equal(noticeFor(CLEAN), '');
});

test('tool page, unchecked: a grey, dashed shield that says so and why; an older index reads as not checked yet', () => {
  const lockfile = markFor({ status: 'unchecked', reason: 'no_lockfile', checked_at: '2026-11-03' });
  assert.match(lockfile, /^<span class="check-mark mark-open" tabindex="0" data-tip="Not checked for known vulnerabilities: there is no lockfile to read"><svg class="i i-shield"/);
  assert.match(lockfile, /<span class="sr">Not checked for known vulnerabilities: there is no lockfile to read<\/span>/);
  assert.match(markFor({ status: 'unchecked', reason: 'no_lockfile' }, 'zh-TW'), /data-tip="沒有檢查已知漏洞：沒有可讀取的 lockfile"/);
  assert.match(markFor({ status: 'unchecked', reason: 'no_source' }), /: there is no repository or package to read"/);
  assert.match(markFor({ status: 'unchecked', reason: 'lockfile_not_supported' }), /: it uses a lockfile pickfit cannot read yet"/);
  assert.match(markFor({ status: 'unchecked', reason: 'resolve_failed' }), /: its dependencies could not be resolved"/);
  for (const security of [{ status: 'unchecked', reason: 'not_run' } as SecurityCheck, null, undefined]) {
    const mark = markFor(security);
    assert.match(mark, /data-tip="Not checked for known vulnerabilities yet"/);
    // Never clean or vulnerable, and no word about the score.
    assert.doesNotMatch(mark, /mark-fail|mark-pass|shield-check|score|capped/);
    assert.equal(noticeFor(security), '');
  }
  const zh = markFor(undefined, 'zh-TW');
  assert.match(zh, /data-tip="尚未檢查已知漏洞"/);
  assert.doesNotMatch(zh, /分數不變/);
});

test('the tool page shows the mark from the index, and the How page explains the check and the 79 cap', async () => {
  const get = site(indexWith(VULNERABLE));
  const html = await (await get(`/tool/${SLUG}`)).text();
  const aside = (page: string) => page.slice(page.indexOf('<aside class="side"'), page.indexOf('</aside>'));
  assert.match(aside(html), /<ul class="check-marks" aria-label="Checks"><li><a class="check-mark mark-fail" href="#security"/);
  assert.match(html, /<div class="notice error security-notice" role="note" id="security">/);
  assert.match(html, /href="https:\/\/osv\.dev\/vulnerability\/GHSA-abcd-1234-wxyz"/);
  assert.doesNotMatch(aside(html), /Scored apart|capped|hidden gems/);
  const zh = await (await get(`/tool/${SLUG}?lang=zh-TW`)).text();
  assert.match(aside(zh), /<ul class="check-marks" aria-label="檢查">/);
  assert.doesNotMatch(aside(zh), /寶藏|品質最高 79 分|兩項分開計分/);
  // Another fixture with no check run yet.
  assert.match(aside(await (await get('/tool/fixture-chat-tui')).text()), /class="check-mark mark-open" tabindex="0" data-tip="Not checked for known vulnerabilities yet"/);

  const how = await (await get('/how')).text();
  assert.match(how, /against OSV\.dev, the public database of known vulnerabilities/);
  assert.match(how, /caps quality at 79, so the tool can’t be a hidden gem/);
  assert.match(how, /keeps its score, and its page says it was not checked/);
  // The cap is the How page's to explain: the quality popover every page carries no longer states it.
  assert.match(how, /A known high or critical vulnerability in any of them caps quality at 79/);
  assert.doesNotMatch(how, /in what it installs caps quality at 79/);
  const howZh = await (await get('/how?lang=zh-TW')).text();
  assert.match(howZh, /比對公開的已知漏洞資料庫 OSV\.dev/);
  assert.match(howZh, /品質最高只算 79 分，因此不會列為寶藏/);
});

test('get_install_guide: the security field, and a warning to tell the user before installing', () => {
  const out = installGuide(loadCatalog(indexWith(VULNERABLE)), { slug: SLUG, os: 'macos', arch: 'arm64' });
  assert.deepEqual(out.security, {
    status: 'vulnerable',
    reason: null,
    checked_at: '2026-11-03',
    count: 7,
    findings: [
      { package: 'npm:undici', version: '8.9.0', advisory: 'GHSA-abcd-1234-wxyz', severity: 'HIGH', fixed_in: '8.12.2', malicious: false },
      { package: 'crates.io:time', version: '0.1.0', advisory: 'RUSTSEC-2020-0071', severity: 'CRITICAL', fixed_in: null, malicious: false },
    ],
  });
  assert.deepEqual(out.warnings, [
    'Known vulnerabilities (7 high or critical): npm:undici 8.9.0 GHSA-abcd-1234-wxyz (HIGH), fixed in 8.12.2; ' +
      'crates.io:time 0.1.0 RUSTSEC-2020-0071 (CRITICAL), no fix yet; 5 more. Tell the user before installing.',
  ]);

  const single = installGuide(loadCatalog(indexWith({ ...VULNERABLE, count: 1, findings: [VULNERABLE.findings![0]] })), { slug: SLUG, os: 'macos', arch: 'arm64' });
  assert.deepEqual(single.warnings, ['Known vulnerability: npm:undici 8.9.0 GHSA-abcd-1234-wxyz (HIGH), fixed in 8.12.2. Tell the user before installing.']);

  const malicious = installGuide(
    loadCatalog(indexWith({ ...VULNERABLE, count: 1, findings: [{ ...VULNERABLE.findings![0], advisory: 'MAL-2026-1', malicious: true }] })),
    { slug: SLUG, os: 'macos', arch: 'arm64' },
  );
  assert.deepEqual(malicious.warnings, ['Malicious package: npm:undici 8.9.0 (MAL-2026-1). Tell the user; do not install it.']);

  // At most 5 findings in the answer; count keeps the total.
  const many = { ...VULNERABLE, count: 9, findings: Array.from({ length: 8 }, (_, i) => ({ ...VULNERABLE.findings![0], advisory: `GHSA-${i}` })) };
  assert.equal(installGuide(loadCatalog(indexWith(many)), { slug: SLUG, os: 'macos' }).security.findings.length, 5);

  const clean = installGuide(loadCatalog(indexWith(CLEAN)), { slug: SLUG, os: 'macos', arch: 'arm64' });
  assert.deepEqual(clean.security, { status: 'clean', reason: null, checked_at: '2026-11-03', count: 0, findings: [] });
  assert.deepEqual(clean.warnings, []);

  const unchecked = installGuide(loadCatalog(indexWith(undefined)), { slug: SLUG, os: 'macos', arch: 'arm64' });
  assert.deepEqual(unchecked.security, { status: 'unchecked', reason: 'not_run', checked_at: null, count: 0, findings: [] });
  assert.deepEqual(unchecked.warnings, []);

  // A web app's guide carries it too.
  const web = installGuide(loadCatalog(indexWith({ status: 'unchecked', reason: 'no_source', checked_at: '2026-11-03' }, 'fixture-web-sketch')), {
    slug: 'fixture-web-sketch',
    os: 'macos',
  });
  assert.deepEqual([web.security.status, web.security.reason], ['unchecked', 'no_source']);
});

test('find_software: each pick carries its security check', async () => {
  const h = harness(() => metaResponse(answer()));
  h.deps.catalog = loadCatalog(indexWith(VULNERABLE));
  const out = await findSoftware({ need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true }, h.deps);
  await h.settle();
  const runner = out.picks.find((p) => p.slug === SLUG)!;
  assert.equal(runner.security.status, 'vulnerable');
  assert.equal(runner.security.count, 7);
  assert.deepEqual(runner.security.findings[0], {
    package: 'npm:undici',
    version: '8.9.0',
    advisory: 'GHSA-abcd-1234-wxyz',
    severity: 'HIGH',
    fixed_in: '8.12.2',
    malicious: false,
  });
  assert.ok(!('summary' in runner.security.findings[0]));
  const other = out.picks.find((p) => p.slug !== SLUG)!;
  assert.deepEqual(other.security, { status: 'unchecked', reason: 'not_run', checked_at: null, count: 0, findings: [] });
});

test('results: a vulnerable pick is flagged before its commands, with the count, the source and the list; others are not', async () => {
  const h = harness(() => metaResponse(answer()));
  const catalog = loadCatalog(indexWith(VULNERABLE));
  h.deps.catalog = catalog;
  const out = await findSoftware({ need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true }, h.deps);
  await h.settle();
  const guides = Object.fromEntries(out.picks.map((p) => [p.slug, installGuide(catalog, { slug: p.slug, os: 'macos' })]));
  const ticketOf = (html: string, slug: string) => html.slice(html.indexOf(`id="pick-${slug}"`), html.indexOf('</article>', html.indexOf(`id="pick-${slug}"`)));
  for (const language of ['en', 'zh-TW'] as const) {
    const html = withLang(language, () => renderResults({ out, guides }, { ...EMPTY_FORM, os: 'macos' }, catalog));
    const ticket = ticketOf(html, SLUG);
    const flag = ticket.indexOf('<p class="t-vuln" role="note">');
    assert.ok(flag > 0, 'the vulnerable pick is flagged');
    const install = ticket.indexOf('class="t-install');
    assert.ok(install < 0 || flag < install, 'the flag comes before the commands');
    assert.ok(flag < ticket.indexOf('<details class="t-more">'), 'and before the steps in the fold');
    const line = ticket.slice(flag, ticket.indexOf('</p>', flag));
    assert.match(line, /<svg class="i i-shield-alert"/);
    assert.match(line, /href="\/tool\/fixture-llm-runner#security"/);
    assert.match(
      line,
      language === 'en'
        ? /<b>7 known vulnerabilities in packages it installs<\/b> \(high or critical; OSV\.dev, 3 Nov 2026\)\. <a [^>]*>See the list<\/a>/
        : /<b>它安裝的套件有 7 個已知漏洞<\/b>（高風險或嚴重；OSV\.dev，2026年11月3日）。<a [^>]*>看清單<\/a>/,
    );
    assert.doesNotMatch(line, /79|capped|hidden gem|寶藏/);
    // An unchecked pick says nothing here, so it never reads as checked clean.
    for (const other of out.picks.filter((p) => p.slug !== SLUG)) assert.ok(!ticketOf(html, other.slug).includes('t-vuln'));
  }
});

test('over MCP, a vulnerable tool passes the find_software and get_install_guide output schemas', async () => {
  const { db } = makeD1();
  const worker = makeWorker(indexWith(VULNERABLE), {
    fetch: (async () => Response.json({}, { status: 500 })) as unknown as typeof fetch,
  });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const call = async (id: number, name: string, args: object) => {
    const res = await worker.fetch(
      new Request('http://127.0.0.1:8787/mcp', {
        method: 'POST',
        headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25' },
        body: JSON.stringify({ jsonrpc: '2.0', id, method: 'tools/call', params: { name, arguments: args } }),
      }),
      { DB: db, MATCH_MODE: 'off' } as Env,
      ctx,
    );
    const text = await res.text();
    const data = res.headers.get('content-type')?.includes('text/event-stream') ? text.split('\n').find((l) => l.startsWith('data: '))!.slice(6) : text;
    return JSON.parse(data).result;
  };
  const guide = await call(1, 'get_install_guide', { slug: SLUG, os: 'macos' });
  assert.ok(!guide.isError, JSON.stringify(guide).slice(0, 300));
  assert.equal(guide.structuredContent.security.status, 'vulnerable');
  assert.match(guide.structuredContent.warnings[0], /^Known vulnerabilities \(7 high or critical\)/);
  const found = await call(2, 'find_software', { need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true });
  assert.ok(!found.isError, JSON.stringify(found).slice(0, 300));
  assert.equal(found.structuredContent.picks.find((p: any) => p.slug === SLUG).security.count, 7);
});

test('tool page, vulnerable: a badge by the title that jumps to the list, and a notice before the first install step', async () => {
  const get = site(indexWith(VULNERABLE));
  const html = await (await get(`/tool/${SLUG}`)).text();
  const head = html.slice(0, html.indexOf('class="wrap layout"'));
  assert.match(head, /<a class="badge-link" href="#security"><span class="badge badge-fail"><svg[^>]*>.*?<\/svg>Known vulnerabilities<\/span><\/a>/);
  const notice = html.indexOf('class="notice error security-notice"');
  assert.ok(notice > 0 && notice < html.indexOf('class="use-it"'), 'the notice comes before the install steps');
  assert.match(html, /<h3>Before you install: known vulnerabilities<\/h3>/);
  assert.match(html, /found 7 known high or critical vulnerabilities in the packages a fresh install brings \(OSV\.dev, /);
  // The two worst, escaped, each with its advisory, severity and fix; then a link to the whole list.
  assert.match(html, /<code>npm:undici 8\.9\.0<\/code> A &lt;b&gt;bad&lt;\/b&gt; parser\. \(<a [^>]*href="https:\/\/osv\.dev\/vulnerability\/GHSA-abcd-1234-wxyz"[^>]*>GHSA-abcd-1234-wxyz<\/a>, high, fixed in 8\.12\.2\)/);
  assert.match(html, /RUSTSEC-2020-0071<\/a>, critical, no fix yet\)/);
  // The two named above are all the check kept, so nothing folds; the rest of the count is said, not hidden.
  assert.match(html, /<p class="small quiet">5 more not listed here\.<\/p>/);
  assert.doesNotMatch(html, />See all|<details class="vuln-list/);
  const zh = await (await get(`/tool/${SLUG}?lang=zh-TW`)).text();
  assert.match(zh, /有已知漏洞<\/span><\/a>/);
  assert.match(zh, /<h3>安裝前先知道：有已知漏洞<\/h3>/);
  assert.match(zh, /安裝時會一併裝上的套件裡找到 7 個已知的高風險或嚴重漏洞/);
  assert.match(zh, /高風險，8\.12\.2 已修正）/);
});

test('tool page, clean or unchecked: no badge by the title and no notice', async () => {
  for (const security of [CLEAN, undefined]) {
    const html = await (await site(indexWith(security))(`/tool/${SLUG}`)).text();
    assert.doesNotMatch(html, /class="badge-link"|class="notice error security-notice"/);
  }
});

test('web app, vulnerable: the notice sits beside the site, worded for using it', async () => {
  const html = await (await site(indexWith(VULNERABLE, 'fixture-web-sketch'))('/tool/fixture-web-sketch')).text();
  assert.match(html, /<h3>Before you use it: known vulnerabilities<\/h3>/);
  assert.match(html, /in the packages this site is built with/);
  const zh = await (await site(indexWith(VULNERABLE, 'fixture-web-sketch'))('/tool/fixture-web-sketch?lang=zh-TW')).text();
  assert.match(zh, /使用前先知道：有已知漏洞/);
});

test('get_install_guide for a web app: the warning speaks of using the site, not installing it', () => {
  const catalog = loadCatalog(indexWith(VULNERABLE, 'fixture-web-sketch'));
  const out = installGuide(catalog, { slug: 'fixture-web-sketch', os: 'linux' }) as unknown as { warnings: string[] };
  assert.match(out.warnings[0], /^Known vulnerabilities \(7 high or critical\): .*Tell the user before they use it\.$/);
});
