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
import { answer, fixtureIndex, harness, makeD1, modelResponse } from './helpers.ts';

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
    worker.fetch(new Request(`http://127.0.0.1:8787${path}`, { headers: { accept: 'text/html' } }), { DB: d1.db, ANTHROPIC_API_KEY: 'k', MATCH_MODE: 'off' } as Env, ctx);
}

test('tool page, vulnerable: a red shield with the count and its source, jumping to the warning that lists each advisory', () => {
  const mark = markFor(VULNERABLE);
  const say = '7 known high or critical vulnerabilities in packages it installs \\(OSV\\.dev, 3 Nov 2026\\)\\. See the list';
  assert.match(mark, new RegExp(`^<a class="check-mark mark-fail" href="#security" data-tip="${say}"><svg class="i i-shield-alert"`));
  assert.match(mark, new RegExp(`<span class="check-label" aria-hidden="true">Security check</span><span class="check-count" aria-hidden="true">7</span><span class="sr">${say}</span></a>$`));
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
  assert.match(fold, /4 more findings not listed here\./);
  assert.doesNotMatch(fold, /Another one/); // the fold leaves out each advisory's own summary
  assert.doesNotMatch(notice, /capped|hidden gem|79/);

  const zh = noticeFor(THREE, 'zh-TW');
  assert.match(zh, /<summary>再看 1 個<\/summary>/);
  assert.match(zh, /GHSA-abcd-1234-wxyz<\/a>，高風險，8\.12\.2 已修正）<\/li>/);
  assert.match(zh, /RUSTSEC-2020-0071<\/a>，嚴重，尚無修正版本）<\/li>/);
  assert.match(zh, /GHSA-efgh-5678-wxyz<\/a>（高風險），8\.12\.2 已修正<\/li>/);
  assert.match(zh, /另有 4 筆未列出。/);
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
  assert.match(how, /A known high or critical vulnerability among them caps quality at 79/);
  // sec.v2: a finding shown not shipped or never reached changes nothing; not checked is no verdict (11/19).
  assert.match(how, /is not in what you get \(development and build tools, parts for another platform\)/);
  assert.match(how, /not checked is neither a known hole nor safe/);
  assert.doesNotMatch(how, /in what it installs caps quality at 79/);
  const howZh = await (await get('/how?lang=zh-TW')).text();
  assert.match(howZh, /比對公開的已知漏洞資料庫 OSV\.dev/);
  assert.match(howZh, /品質最高只算 79 分，因此不會列為寶藏/);
  assert.match(howZh, /沒有檢查不代表有漏洞，也不代表安全/);
});

test('get_install_guide: the security field, and a warning to tell the user before installing', () => {
  const out = installGuide(loadCatalog(indexWith(VULNERABLE)), { slug: SLUG, os: 'macos', arch: 'arm64' });
  assert.deepEqual(out.security, {
    status: 'vulnerable',
    level: null,
    coverage: null,
    reason: null,
    checked_at: '2026-11-03',
    count: 7,
    advisories: 7,
    findings: [
      { package: 'npm:undici', version: '8.9.0', advisory: 'GHSA-abcd-1234-wxyz', severity: 'HIGH', fixed_in: '8.12.2', malicious: false, level: null, preconditions: [] },
      { package: 'crates.io:time', version: '0.1.0', advisory: 'RUSTSEC-2020-0071', severity: 'CRITICAL', fixed_in: null, malicious: false, level: null, preconditions: [] },
    ],
  });
  assert.deepEqual(out.warnings, [
    'Known vulnerabilities (7 high or critical): npm:undici 8.9.0 GHSA-abcd-1234-wxyz (HIGH), fixed in 8.12.2; ' +
      'crates.io:time 0.1.0 RUSTSEC-2020-0071 (CRITICAL), no fix yet; 5 more findings. Tell the user before installing.',
  ]);
  // One advisory on several packages counts once in the headline; the rest are still findings.
  const shared = installGuide(loadCatalog(indexWith({ ...VULNERABLE, advisories: 4 })), { slug: SLUG, os: 'macos', arch: 'arm64' });
  assert.equal(shared.security.advisories, 4);
  assert.match(shared.warnings[0], /^Known vulnerabilities \(4 high or critical\): .*; 5 more findings\. /);

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
  assert.deepEqual(clean.security, { status: 'clean', level: null, coverage: null, reason: null, checked_at: '2026-11-03', count: 0, advisories: 0, findings: [] });
  assert.deepEqual(clean.warnings, []);

  const unchecked = installGuide(loadCatalog(indexWith(undefined)), { slug: SLUG, os: 'macos', arch: 'arm64' });
  assert.deepEqual(unchecked.security, { status: 'unchecked', level: null, coverage: null, reason: 'not_run', checked_at: null, count: 0, advisories: 0, findings: [] });
  assert.deepEqual(unchecked.warnings, []);

  // A web app's guide carries it too.
  const web = installGuide(loadCatalog(indexWith({ status: 'unchecked', reason: 'no_source', checked_at: '2026-11-03' }, 'fixture-web-sketch')), {
    slug: 'fixture-web-sketch',
    os: 'macos',
  });
  assert.deepEqual([web.security.status, web.security.reason], ['unchecked', 'no_source']);
});

test('find_software: each pick carries its security check', async () => {
  const h = harness(() => modelResponse(answer()));
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
    level: null,
    preconditions: [],
  });
  assert.ok(!('summary' in runner.security.findings[0]));
  const other = out.picks.find((p) => p.slug !== SLUG)!;
  assert.deepEqual(other.security, { status: 'unchecked', level: null, coverage: null, reason: 'not_run', checked_at: null, count: 0, advisories: 0, findings: [] });
});

test('results: a vulnerable pick is flagged before its commands, with the count, the source and the list; others are not', async () => {
  const h = harness(() => modelResponse(answer()));
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
  assert.match(html, /<p class="small quiet">5 more findings not listed here\.<\/p>/);
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

test('tool page: one advisory on several packages counts once, and the notice says how many findings there are', () => {
  // 11/3, MangoDisk: 9 distinct advisories in 15 findings (zip 4.6.1 and 8.6.0 share four; one vue-i18n advisory sits on three packages).
  const shared = { ...VULNERABLE, count: 7, advisories: 5 };
  assert.match(markFor(shared), /5 known high or critical vulnerabilities in packages it installs/);
  assert.match(noticeFor(shared), /pickfit found 5 known high or critical vulnerabilities \(7 findings, one per affected package version\) in the packages a fresh install brings/);
  assert.match(noticeFor(shared, 'zh-TW'), /找到 5 個已知的高風險或嚴重漏洞（共 7 筆，每個受影響的套件版本一筆）/);
  // A check from before the count of distinct advisories reads as its findings.
  assert.match(noticeFor(VULNERABLE), /pickfit found 7 known high or critical vulnerabilities in the packages/);
});

// ---------------------------------------------------------------- sec.v2: a level per check (pickfit/security.py)

/** An OpenPets-like check: two findings that matter only in some uses, the MCP SDK's HTTP deps present but unused,
 * build and peer packages counted only. */
const CONDITIONAL: SecurityCheck = {
  status: 'vulnerable',
  level: 'conditional',
  policy_version: 'sec.v2',
  checked_at: '2026-11-19',
  packages_checked: 755,
  count: 2,
  advisories: 2,
  counts: { conditional: 2, present_unreachable: 3, not_shipped: 9 },
  target: 'repo_lockfile',
  coverage: { state: 'complete', packages_checked: 755, packages_found: 755, gaps: [] },
  findings: [
    { package: 'npm:sharp', version: '0.34.5', advisory: 'GHSA-f88m-g3jw-g9cj', severity: 'HIGH', fixed_in: '0.35.0', summary: 'libvips holes.', malicious: false, level: 'conditional', scope: 'runtime', kev: false, preconditions: ['user_interaction'] },
    { package: 'npm:undici', version: '7.29.0', advisory: 'GHSA-2m5v-pch6-74hx', severity: 'HIGH', fixed_in: '7.30.1', summary: 'TLS bypass.', malicious: false, level: 'conditional', scope: 'runtime', kev: false, preconditions: [] },
  ],
  unreachable: [
    { package: 'npm:proxy-addr', version: '2.0.7', advisory: 'GHSA-jqcg-44mw-7w3h', severity: 'CRITICAL', method: 'entry_point_grep', evidence: ["no source file imports the MCP SDK's HTTP transports"] },
  ],
};
const UNREACHABLE: SecurityCheck = {
  status: 'clean',
  level: 'present_unreachable',
  policy_version: 'sec.v2',
  checked_at: '2026-11-19',
  packages_checked: 40,
  counts: { present_unreachable: 1, not_shipped: 2 },
  target: 'repo_lockfile',
  coverage: { state: 'complete', packages_checked: 40, packages_found: 40, gaps: [] },
  unreachable: [
    { package: 'crates:pulldown-cmark', version: '0.13.0', advisory: 'RUSTSEC-2026-0433', severity: 'HIGH', method: 'option_grep', evidence: ['no source file uses ENABLE_WIKILINKS'] },
  ],
};

test('sec.v2 tool page, conditional: an amber shield and notice that say, for each, when it applies', () => {
  const mark = markFor(CONDITIONAL);
  assert.match(mark, /^<a class="check-mark mark-caution" href="#security" data-tip="2 known high or critical vulnerabilities in packages it installs that matter only in some uses \(OSV\.dev, 19 Nov 2026\)\. See when"/);
  assert.match(markFor(CONDITIONAL, 'zh-TW'), /data-tip="它安裝的套件有 2 個已知的高風險或嚴重漏洞，只在某些用法下才會碰到（OSV\.dev，2026年11月19日）。看是哪些情況"/);
  const notice = noticeFor(CONDITIONAL);
  assert.match(notice, /^<div class="notice busy security-notice" role="note" id="security">/);
  assert.match(notice, /<h3>Before you install: known vulnerabilities in some uses<\/h3>/);
  assert.match(notice, /Each matters only in some uses, which pickfit could not rule out\./);
  assert.match(notice, /GHSA-f88m-g3jw-g9cj<\/a>, high, fixed in 0\.35\.0\) <span class="quiet">Only when you open a crafted file or link\.<\/span><\/li>/);
  assert.match(notice, /GHSA-2m5v-pch6-74hx<\/a>, high, fixed in 7\.30\.1\) <span class="quiet">pickfit could not tell when it applies\.<\/span>/);
  const zh = noticeFor(CONDITIONAL, 'zh-TW');
  assert.match(zh, /<h3>安裝前先知道：某些用法下有已知漏洞<\/h3>/);
  assert.match(zh, /這些漏洞只在某些用法下才會碰到，pickfit 無法排除。安裝前先看看下面列的情況。/);
  assert.match(zh, /<span class="quiet">只在你打開特製的檔案或連結時才會碰到。<\/span>/);
});

test('sec.v2 tool page: exposed is red and says normal use reaches it; blocked says not to install it', () => {
  const exposed = { ...CONDITIONAL, level: 'exposed' as const, findings: CONDITIONAL.findings!.map((f) => ({ ...f, level: 'exposed' as const })) };
  assert.match(markFor(exposed), /mark-fail" href="#security" data-tip="2 known high or critical vulnerabilities in packages it installs, reached in normal use/);
  assert.match(noticeFor(exposed), /^<div class="notice error security-notice"[^]*\. Normal use reaches them\. Weigh this before you install it\./);
  assert.doesNotMatch(noticeFor(exposed), /Only when/);
  const blocked = { ...exposed, level: 'blocked' as const };
  assert.match(noticeFor(blocked), /<h3>Do not install it: a malicious package or an exploited hole<\/h3>/);
  assert.match(noticeFor(blocked, 'zh-TW'), /<h3>不要安裝：有惡意套件或已遭利用的漏洞<\/h3>/);
});

test('sec.v2 tool page: present_unreachable and not_shipped are green, partial is grey, none has a notice', () => {
  const unused = markFor(UNREACHABLE);
  assert.match(unused, /^<button type="button" class="check-mark mark-pass" popovertarget="pop-security" data-tip="No known high or critical vulnerabilities in what it runs \(OSV\.dev, checked 19 Nov 2026, 40 packages\)\. 1 more in code it installs but does not use: open to see"/);
  assert.match(unused, /<code>crates:pulldown-cmark 0\.13\.0<\/code> — <a [^>]*>RUSTSEC-2026-0433<\/a>: it never turns on the option the hole needs<\/li>/);
  assert.match(markFor(UNREACHABLE, 'zh-TW'), /程式沒有開啟漏洞需要的選項/);
  assert.equal(noticeFor(UNREACHABLE), '');
  const notShipped: SecurityCheck = { ...UNREACHABLE, level: 'not_shipped', counts: { not_shipped: 9 }, unreachable: undefined };
  assert.match(markFor(notShipped), /mark-pass" tabindex="0" data-tip="No known high or critical vulnerabilities in what it runs \(OSV\.dev, checked 19 Nov 2026, 40 packages\)\. 9 more only in development or build tools"/);
  assert.match(markFor(notShipped, 'zh-TW'), /另有 9 個只在開發或建置工具裡/);
  // Partly checked: grey, never clean and never a vulnerability, with how much was checked and why not the rest.
  const partial: SecurityCheck = {
    status: 'unchecked',
    level: 'not_shipped',
    reason: 'lockfile_not_supported',
    checked_at: '2026-11-19',
    packages_checked: 12,
    counts: { not_shipped: 1 },
    coverage: { state: 'partial', packages_checked: 12, packages_found: 30, gaps: [{ code: 'lockfile.unsupported_format', category: 'lockfile_unreadable', ecosystem: 'npm' }] },
  };
  const grey = markFor(partial);
  assert.match(
    grey,
    /^<span class="check-mark mark-open" tabindex="0" data-tip="Only partly checked for known vulnerabilities: none known in the part pickfit could read\. pickfit checked 12 of 30 packages; part of it uses a lockfile pickfit cannot read yet\. Also 1 only in development or build tools\."/,
  );
  assert.doesNotMatch(grey, /mark-pass|mark-fail|mark-caution/);
  assert.match(markFor(partial, 'zh-TW'), /已知漏洞只檢查了一部分，讀得到的部分沒有已知漏洞。pickfit 檢查了 12 個套件（已知至少 30 個），有一部分用的 lockfile pickfit 還讀不了。另有1 個只在開發或建置工具裡。/);
  assert.equal(noticeFor(partial), '');
  // Nothing checked: as an unchecked check always read.
  const none: SecurityCheck = { status: 'unchecked', level: 'none', reason: 'no_source', checked_at: '2026-11-19', packages_checked: 0, coverage: { state: 'unchecked', packages_checked: 0, packages_found: 0, gaps: [{ code: 'source.none', category: 'no_source', ecosystem: 'unknown' }] } };
  assert.match(markFor(none), /mark-open" tabindex="0" data-tip="Not checked for known vulnerabilities: there is no repository or package to read"/);
  // A warning keeps its colour when only part was checked, and says how much.
  const amber = { ...CONDITIONAL, status: 'vulnerable' as const, coverage: { ...partial.coverage! } };
  assert.match(markFor(amber), /mark-caution" href="#security" data-tip="[^"]*See when\. pickfit checked 12 of 30 packages; part of it uses a lockfile pickfit cannot read yet\."/);
});

test('sec.v2 head badge: conditional is amber, the rest that warn stay red', async () => {
  const html = await (await site(indexWith(CONDITIONAL))(`/tool/${SLUG}`)).text();
  const head = html.slice(0, html.indexOf('class="wrap layout"'));
  assert.match(head, /<a class="badge-link" href="#security"><span class="badge badge-caution"><svg[^>]*>.*?<\/svg>Known vulnerabilities in some uses<\/span><\/a>/);
  const clean = await (await site(indexWith(UNREACHABLE))(`/tool/${SLUG}`)).text();
  assert.doesNotMatch(clean, /class="badge-link" href="#security"|class="notice \w+ security-notice"/);
});

test('sec.v2 get_install_guide: the level in the security field, and the warning by level', () => {
  const guide = (security: SecurityCheck) => installGuide(loadCatalog(indexWith(security)), { slug: SLUG, os: 'macos', arch: 'arm64' });
  const conditional = guide(CONDITIONAL);
  assert.equal(conditional.security.level, 'conditional');
  assert.deepEqual(conditional.security.findings[0].preconditions, ['user_interaction']);
  assert.deepEqual(conditional.warnings, [
    'Known vulnerabilities (2 high or critical) that pickfit could not rule out in normal use: ' +
      'npm:sharp 0.34.5 GHSA-f88m-g3jw-g9cj (HIGH; only when the user opens crafted input), fixed in 0.35.0; ' +
      'npm:undici 7.29.0 GHSA-2m5v-pch6-74hx (HIGH), fixed in 7.30.1. Mention it to the user in one line before installing.',
  ]);
  const exposed = guide({ ...CONDITIONAL, level: 'exposed' });
  assert.match(exposed.warnings[0], /^Known vulnerabilities \(2 high or critical\) reached in normal use: npm:sharp .*Tell the user before installing\.$/);
  const kev = { ...CONDITIONAL.findings![1], level: 'blocked' as const, kev: true };
  const blocked = guide({ ...CONDITIONAL, level: 'blocked', count: 1, advisories: 1, findings: [kev] });
  assert.deepEqual(blocked.warnings, ['Known exploited vulnerability (CISA KEV): npm:undici 7.29.0 GHSA-2m5v-pch6-74hx, fixed in 7.30.1. Do not recommend it; tell the user.']);
  const partly: SecurityCheck = {
    status: 'unchecked',
    level: 'none',
    reason: 'no_lockfile',
    coverage: { state: 'partial', packages_checked: 3, packages_found: 9, gaps: [{ code: 'lockfile.missing', category: 'lockfile_missing', ecosystem: 'npm' }] },
  };
  const quiet: SecurityCheck[] = [UNREACHABLE, { ...UNREACHABLE, level: 'not_shipped' }, partly];
  for (const security of quiet) {
    const out = guide(security);
    assert.deepEqual(out.warnings, []); // an unknown is never a warning
    assert.equal(out.security.level, security.level);
    assert.deepEqual(out.security.findings, []);
  }
  assert.deepEqual(guide(partly).security.coverage, { state: 'partial', packages_checked: 3, packages_found: 9 });
  assert.equal(guide(partly).security.status, 'unchecked');
});

test('over MCP, a sec.v2 conditional tool passes the output schemas', async () => {
  const { db } = makeD1();
  const worker = makeWorker(indexWith(CONDITIONAL), {
    fetch: (async () => Response.json({}, { status: 500 })) as unknown as typeof fetch,
  });
  const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const res = await worker.fetch(
    new Request('http://127.0.0.1:8787/mcp', {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'get_install_guide', arguments: { slug: SLUG, os: 'macos' } } }),
    }),
    { DB: db, MATCH_MODE: 'off' } as Env,
    ctx,
  );
  const text = await res.text();
  const data = res.headers.get('content-type')?.includes('text/event-stream') ? text.split('\n').find((l) => l.startsWith('data: '))!.slice(6) : text;
  const guide = JSON.parse(data).result;
  assert.ok(!guide.isError, JSON.stringify(guide).slice(0, 300));
  assert.equal(guide.structuredContent.security.level, 'conditional');
  assert.match(guide.structuredContent.warnings[0], /only when the user opens crafted input/);
});
