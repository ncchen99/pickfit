/**
 * The known-vulnerability check (OSV.dev, pickfit/index.py _security): the tool
 * page's line in both languages, the How page, and the security field that
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
import { securityLine } from '../src/pages/tool.ts';
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

const lineFor = (security: SecurityCheck | null | undefined, language: 'en' | 'zh-TW' = 'en') =>
  withLang(language, () => securityLine(loadCatalog(indexWith(security)).bySlug.get(SLUG)!));

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

test('tool page, vulnerable: a warning with the count, the 79 cap and each advisory linked to OSV.dev', () => {
  const html = lineFor(VULNERABLE);
  assert.match(html, /class="badge badge-fail"><svg[^>]*>.*?<\/svg>Known vulnerabilities<\/span>/);
  assert.match(html, /7 known high or critical vulnerabilities in packages it installs\. That keeps it out of hidden gems: quality is capped at 79\./);
  assert.match(
    html,
    /<li><code>npm:undici 8\.9\.0<\/code> — <a href="https:\/\/osv\.dev\/vulnerability\/GHSA-abcd-1234-wxyz" target="_blank" rel="noopener noreferrer">GHSA-abcd-1234-wxyz<\/a> \(high\), fixed in 8\.12\.2<\/li>/,
  );
  assert.match(html, /RUSTSEC-2020-0071<\/a> \(critical\), no fix yet<\/li>/);
  assert.match(html, /5 more not listed here\./);
  assert.doesNotMatch(html, /parser/); // the advisory's own summary is not shown

  const zh = lineFor(VULNERABLE, 'zh-TW');
  assert.match(zh, />已知漏洞<\/span>/);
  assert.match(zh, /它安裝的套件有 7 個已知的高風險或嚴重漏洞，所以不列為寶藏：品質最高 79 分。/);
  assert.match(zh, /GHSA-abcd-1234-wxyz<\/a>（高風險），8\.12\.2 已修正<\/li>/);
  assert.match(zh, /RUSTSEC-2020-0071<\/a>（嚴重），尚無修正版本<\/li>/);
  assert.match(zh, /另有 5 個未列出。/);

  // One finding: singular, nothing more to list; a malicious package is named as such.
  const one = lineFor({ ...VULNERABLE, count: 1, findings: [{ ...VULNERABLE.findings![0], advisory: 'MAL-2026-1', malicious: true }] });
  assert.match(one, /1 known high or critical vulnerability in packages it installs/);
  assert.match(one, /MAL-2026-1<\/a> \(malicious package\)<\/li>/);
  assert.doesNotMatch(one, /more not listed/);
});

test('tool page, clean: none known, with the date and how many packages', () => {
  assert.equal(
    lineFor(CLEAN),
    '<p class="small security-check">No known high or critical vulnerabilities (OSV.dev, checked 3 Nov 2026, 115 packages).</p>',
  );
  assert.match(lineFor(CLEAN, 'zh-TW'), /沒有已知的高風險或嚴重漏洞（OSV\.dev，2026年11月3日 檢查，共 115 個套件）。/);
});

test('tool page, unchecked: why, and that its score is unchanged; an older index reads as not checked yet', () => {
  const lockfile = lineFor({ status: 'unchecked', reason: 'no_lockfile', checked_at: '2026-11-03' });
  assert.equal(lockfile, '<p class="small quiet security-check">Not checked for known vulnerabilities: there is no lockfile to read. Its score is unchanged.</p>');
  assert.match(lineFor({ status: 'unchecked', reason: 'no_lockfile' }, 'zh-TW'), /沒有檢查已知漏洞：沒有可讀取的 lockfile，分數不變。/);
  assert.match(lineFor({ status: 'unchecked', reason: 'no_source' }), /there is no repository or package to read\./);
  assert.match(lineFor({ status: 'unchecked', reason: 'lockfile_not_supported' }), /it uses a lockfile pickfit cannot read yet\./);
  assert.match(lineFor({ status: 'unchecked', reason: 'resolve_failed' }), /its dependencies could not be resolved\./);
  for (const security of [{ status: 'unchecked', reason: 'not_run' } as SecurityCheck, null, undefined]) {
    const line = lineFor(security);
    assert.match(line, /Not checked for known vulnerabilities yet\. Its score is unchanged\./);
    assert.doesNotMatch(line, /badge-fail|capped/);
  }
  assert.match(lineFor(undefined, 'zh-TW'), /尚未檢查已知漏洞，分數不變。/);
});

test('the tool page shows the line from the index, and the How page explains the check and the 79 cap', async () => {
  const get = site(indexWith(VULNERABLE));
  const html = await (await get(`/tool/${SLUG}`)).text();
  assert.match(html, /<div class="small security-check" id="security"><p><span class="badge badge-fail">/);
  assert.match(html, /href="https:\/\/osv\.dev\/vulnerability\/GHSA-abcd-1234-wxyz"/);
  const zh = await (await get(`/tool/${SLUG}?lang=zh-TW`)).text();
  assert.match(zh, /所以不列為寶藏：品質最高 79 分/);
  // Another fixture with no check run yet.
  assert.match(await (await get('/tool/fixture-chat-tui')).text(), /class="small quiet security-check">Not checked for known vulnerabilities yet\./);

  const how = await (await get('/how')).text();
  assert.match(how, /against OSV\.dev, the public database of known vulnerabilities/);
  assert.match(how, /caps quality at 79, so the tool can’t be a hidden gem/);
  assert.match(how, /keeps its score, and its page says it was not checked/);
  assert.match(how, /A known high or critical vulnerability in what it installs caps quality at 79\./); // the quality popover
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
  assert.match(html, /<a href="#security">See all 7<\/a>/);
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
