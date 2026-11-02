/**
 * The web page in English or zh-TW (i18n.ts): how a request picks its language, that the tools'
 * sentences come from data/i18n only where the English still matches, and that searches, the
 * model call and the MCP answers stay English.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import type { Env } from '../src/env.ts';
import { L, lang, pickLang, translateWith, withLang, type Translations } from '../src/i18n.ts';
import { makeWorker } from '../src/worker.ts';
import { answer, fixtureIndex, makeD1, metaResponse } from './helpers.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const translations = JSON.parse(readFileSync(join(HERE, 'generated', 'zh-TW.json'), 'utf8')) as Translations;
const SUMMARY_ZH = '（測試用假資料）離線執行小型語言模型';
const SUMMARY_EN = '(Fake test fixture) Runs small language models offline';

function site() {
  const d1 = makeD1();
  const metaCalls: string[] = [];
  const worker = makeWorker(fixtureIndex(), {
    fetch: (async (_url: string, init: RequestInit) => {
      metaCalls.push(String(init.body));
      return metaResponse(answer());
    }) as unknown as typeof fetch,
    now: () => new Date('2026-10-30T12:00:00Z'),
    translations,
  });
  const ctx = { waitUntil() {}, passThroughOnException() {} };
  const send = (path: string, headers: Record<string, string> = {}, init: RequestInit = {}) =>
    worker.fetch(
      new Request(`http://127.0.0.1:8787${path}`, { ...init, headers: { accept: 'text/html', ...headers } }),
      { DB: d1.db, MODEL_API_KEY: 'test-key' } as unknown as Env,
      ctx as unknown as ExecutionContext,
    );
  return { send, metaCalls };
}

test('the build writes only translations whose English is still in the index', () => {
  assert.deepEqual(Object.keys(translations), ['fixture-llm-runner']);
  // The command is not prose, so build_index never carries it, even though the file has it.
  assert.equal(translations['fixture-llm-runner']['brew install fixture/tap/fixture-llm-runner'], undefined);
});

test('language: ?lang= wins and is remembered, then the cookie, then Accept-Language', () => {
  const req = (url: string, headers: Record<string, string> = {}) => new Request(url, { headers });
  assert.deepEqual(pickLang(req('https://x/?lang=zh-TW')), { lang: 'zh-TW', remember: true });
  assert.deepEqual(pickLang(req('https://x/?lang=en', { cookie: 'pickfit_lang=zh-TW' })), { lang: 'en', remember: true });
  assert.deepEqual(pickLang(req('https://x/', { cookie: 'a=1; pickfit_lang=zh-TW' })), { lang: 'zh-TW', remember: false });
  assert.deepEqual(pickLang(req('https://x/', { 'accept-language': 'zh-TW,zh;q=0.9,en;q=0.8' })), { lang: 'zh-TW', remember: false });
  assert.deepEqual(pickLang(req('https://x/', { 'accept-language': 'en-US,en;q=0.9,zh-TW;q=0.8' })), { lang: 'en', remember: false });
  assert.deepEqual(pickLang(req('https://x/?lang=fr')), { lang: 'en', remember: false });
});

test('withLang switches L() for one synchronous render only', () => {
  assert.equal(L('Find', '搜尋'), 'Find');
  assert.equal(withLang('zh-TW', () => `${L('Find', '搜尋')} ${withLang('en', () => L('Find', '搜尋'))} ${lang()}`), '搜尋 Find zh-TW');
  assert.equal(lang(), 'en');
  assert.throws(() => withLang('zh-TW', () => { throw new Error('x'); }));
  assert.equal(lang(), 'en');
});

test('translateWith swaps exact sentences and never commands, names or codes', () => {
  const map = { 'Install it': '安裝', 'npm i x': '不能翻', x: '不能翻', needs_gpu: '不能翻' };
  const out = translateWith(map, {
    name: 'x',
    summary: 'Install it',
    steps: [{ command: 'npm i x', purpose: 'Install it' }],
    features: [{ feature: 'Install it', reason: 'needs_gpu' }],
    other: 'Install it now',
  });
  assert.deepEqual(out, {
    name: 'x',
    summary: '安裝',
    steps: [{ command: 'npm i x', purpose: '安裝' }],
    features: [{ feature: '安裝', reason: 'needs_gpu' }],
    other: 'Install it now',
  });
});

test('a tool page in zh-TW shows the translated sentences, the same command and Chinese chrome', async () => {
  const { send } = site();
  const zh = await send('/tool/fixture-llm-runner?lang=zh-TW');
  assert.equal(zh.status, 200);
  assert.match(zh.headers.get('set-cookie') ?? '', /^pickfit_lang=zh-TW; Path=\/;/);
  const page = await zh.text();
  assert.match(page, /<html lang="zh-Hant-TW">/);
  assert.ok(page.includes(SUMMARY_ZH));
  assert.ok(page.includes('從專案的 tap 安裝'));
  assert.ok(page.includes('brew install fixture/tap/fixture-llm-runner'));
  assert.ok(!page.includes(SUMMARY_EN));

  const en = await (await send('/tool/fixture-llm-runner')).text();
  assert.match(en, /<html lang="en">/);
  assert.ok(en.includes(SUMMARY_EN));
  assert.ok(!en.includes(SUMMARY_ZH));
});

test('every catalog page renders in both languages', async () => {
  const { send } = site();
  for (const path of ['/', '/browse', '/compare?tools=fixture-llm-runner,fixture-chat-tui', '/how', '/agents', '/tool/fixture-web-sketch', '/nope']) {
    for (const cookie of ['pickfit_lang=en', 'pickfit_lang=zh-TW']) {
      const res = await send(path, { cookie });
      assert.ok(res.status === 200 || (path === '/nope' && res.status === 404), `${path} ${cookie}: ${res.status}`);
      const body = await res.text();
      assert.match(body, cookie.endsWith('zh-TW') ? /<html lang="zh-Hant-TW">/ : /<html lang="en">/);
      assert.ok(!body.includes('[object Object]'), `${path} ${cookie} leaked an object`);
    }
  }
});

test('a zh-TW search sends the model exactly what an English search sends, and shows Chinese data', async () => {
  const en = site();
  const zh = site();
  const body = new URLSearchParams({ need: 'run a language model offline on my laptop', os: 'macos', offline: '1' }).toString();
  const headers = (cookie: string) => ({ cookie, 'content-type': 'application/x-www-form-urlencoded', origin: 'http://127.0.0.1:8787' });
  const enPage = await (await en.send('/search', headers('pickfit_lang=en'), { method: 'POST', body })).text();
  const zhPage = await (await zh.send('/search', headers('pickfit_lang=zh-TW'), { method: 'POST', body })).text();
  assert.equal(en.metaCalls.length, 1);
  assert.deepEqual(zh.metaCalls, en.metaCalls);
  assert.ok(enPage.includes(SUMMARY_EN) && !enPage.includes(SUMMARY_ZH));
  assert.ok(zhPage.includes(SUMMARY_ZH));
  assert.match(zhPage, /<html lang="zh-Hant-TW">/);
});
