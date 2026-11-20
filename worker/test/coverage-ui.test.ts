/** U8: the tool page's "What pickfit could check", from the index's Verification Coverage summary. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Env } from '../src/env.ts';
import { toCard, promptCard } from '../src/cards.ts';
import { withLang } from '../src/i18n.ts';
import { coverageSection } from '../src/ui/coverage.ts';
import { makeWorker } from '../src/worker.ts';
import { fixtureCatalog, fixtureIndex, makeD1 } from './helpers.ts';

const page = async (slug: string, index: unknown = fixtureIndex(), lang = 'en') => {
  const worker = makeWorker(index);
  const res = await worker.fetch(
    new Request(`http://127.0.0.1:8787/tool/${slug}?lang=${lang}`, { headers: { accept: 'text/html' } }),
    { DB: makeD1().db } as Env,
    { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext,
  );
  return res.text();
};
const section = (html: string) => html.slice(html.indexOf('<section class="block coverage"'), html.indexOf('</section>', html.indexOf('<section class="block coverage"')));

test('the tool page says per dimension what pickfit checked, how much, and why not', async () => {
  const html = section(await page('fixture-llm-runner'));
  assert.match(html, /<h2 id="coverage-title">What pickfit could check<\/h2><p>About 58% of what applies to this tool\. Not checked doesn’t mean it fails/);
  assert.match(html, /<span class="cov-mark mark-pass">.*?<span>Checked<\/span><\/span><span class="cov-what"><b>Install<\/b><span class="cov-detail">2 of 2 systems it claims installed and checked<\/span>/);
  assert.match(html, /<span class="cov-mark mark-caution">.*?<span>Partly<\/span><\/span><span class="cov-what"><b>Features<\/b><span class="cov-detail">1 of 2 features reached a verdict\. Not covered: the test machine lacks something it needs/);
  assert.match(html, /<span>Not yet<\/span><\/span><span class="cov-what"><b>Known vulnerabilities<\/b><span class="cov-detail">Not covered: not tried yet/);
  // An MCP server has a service row; usability and video do not apply to it.
  assert.match(html, /<b>Service starts and answers<\/b>/);
  assert.match(html, /Doesn’t apply to this kind of tool: ease of use, video of it in use\./);
});

test('zh-TW: the same section in Chinese', async () => {
  const html = section(await page('fixture-transcribe', fixtureIndex(), 'zh-TW'));
  assert.match(html, /pickfit 檢查到哪些部分/);
  assert.match(html, /3 項功能中 2 項有結論。沒涵蓋到：需要 pickfit 沒有的硬體/);
  assert.match(html, /這類工具不適用：服務啟動與回應、好不好上手、操作影片。/);
});

test('an index from before coverage leaves the section out; a check-only function reads in words', () => {
  assert.equal(coverageSection(undefined), '');
  const out = withLang('en', () =>
    coverageSection({ version: 'cov.v1', share: 1, dimensions: { function: { status: 'verified', done: 1, of: 1, unit: 'check' }, install: { status: 'unverified', done: 0, of: 1, gaps: ['no_host', '<b>x</b>'] } } }),
  );
  assert.match(out, /A check beyond --version passed/);
  assert.match(out, /Not covered: pickfit has no test machine for that system yet; &lt;b&gt;x&lt;\/b&gt;/);
});

test('the matcher never reads coverage: it is not on the cards', () => {
  const entry = fixtureCatalog().bySlug.get('fixture-llm-runner')!;
  assert.ok(entry.coverage);
  assert.ok(!JSON.stringify(promptCard(toCard(entry, 'macos'))).includes('cov.v1'));
  assert.ok(!('coverage' in toCard(entry, 'macos')));
});
