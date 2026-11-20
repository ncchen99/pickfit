/** U9: the zh-TW page gets the model's sentences in Chinese, the guard reads Chinese claims, and the rules path has
 * English words for the home page's Chinese examples. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { findSoftware } from '../src/find.ts';
import { contradiction, guardNoInstall, saysFree } from '../src/guard.ts';
import { toCard } from '../src/cards.ts';
import { zhWords } from '../src/relevance.ts';
import { answer, fixtureCatalog, harness, modelResponse } from './helpers.ts';

test('answer_language reaches the model inside <request> only when the page asks; the instructions stay the same', async () => {
  const h = harness(() => modelResponse(answer()));
  await findSoftware({ need: 'run a language model offline on my laptop', os: 'macos' }, h.deps);
  await findSoftware({ need: 'run a language model offline on my laptop', os: 'macos', answer_language: 'zh-TW' }, h.deps);
  const [en, zh] = h.requests.map((r) => r.body);
  assert.doesNotMatch(en.messages[0].content, /answer_language/);
  assert.match(zh.messages[0].content, /"answer_language":"zh-TW"/);
  assert.deepEqual(en.system, zh.system, 'one cached prefix for both languages');
});

test('the guard reads the same claims in Chinese', () => {
  // A web app pickfit did not see work offline, or keep typed data on the device.
  const card = { ...toCard(fixtureCatalog().bySlug.get('fixture-web-sketch')!), works_offline: 'not_checked', data_sent: 'some', account_needed: true };
  assert.equal(contradiction(card, '可以離線使用'), 'claims a web app works offline');
  assert.equal(contradiction(card, '資料都留在你的裝置上'), 'claims a web app keeps data local');
  assert.equal(contradiction(card, '免註冊就能用'), 'claims it needs no account');
  const runner = toCard(fixtureCatalog().bySlug.get('fixture-llm-runner')!, 'macos');
  assert.equal(contradiction(runner, '在本機執行，不需要雲端'), null);
  assert.equal(contradiction(runner, '在 Windows 上驗證過'), 'claims it was verified on windows');
  assert.equal(saysFree('它是免費的開源工具，可以離線轉錄。'), true);
  assert.equal(saysFree('它不是免費的，只有試用版。'), false);
  assert.equal(guardNoInstall('macOS 內建的預覽程式就能合併 PDF。'), 'macOS 內建的預覽程式就能合併 PDF。');
  assert.equal(guardNoInstall('用預覽程式就好，pickfit 驗證過。'), null);
});

test('the zh home examples have English words for the rules path', () => {
  const words = (text: string) => zhWords(text).join(' ');
  assert.match(words('一個 MCP 伺服器，讓我的程式設計 agent 看懂整個程式碼庫的結構'), /codebase/);
  assert.match(words('安裝 MCP 伺服器前，先檢查我的 MCP 設定有沒有危險權限'), /check|audit/);
  assert.match(words('找出佔用連接埠 3000 的程序並關掉它'), /port/);
  assert.match(words('找出佔用連接埠 3000 的程序並關掉它'), /kill|stop/);
  assert.match(words('幫我剪輯影片並加上浮水印'), /edit.*watermark|watermark.*edit/);
});
