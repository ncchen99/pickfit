import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Catalog, Entry } from '../src/catalog.ts';
import { findSoftware } from '../src/find.ts';
import { hardFilter, MAX_CARDS } from '../src/filter.ts';
import { dropNegated, queryTerms, relevance, rulesRelevance, rulesTerms, terms, zhToEnglish } from '../src/relevance.ts';
import { rankByRules } from '../src/rules.ts';
import { answer, fixtureCatalog, harness, metaResponse } from './helpers.ts';

const fixtures = fixtureCatalog();

function tool(slug: string, summary: string, treasure = 50, fields: Partial<Entry> = {}): Entry {
  const base = fixtures.bySlug.get('fixture-json-query')!;
  return {
    ...base,
    slug,
    name: slug,
    summary,
    why_worth_it: null,
    tags: [],
    use_cases: [],
    alternatives_to: [],
    scores: { ...base.scores!, treasure_value: treasure },
    ...fields,
  };
}

const slugs = (entries: Entry[]) => entries.map((e) => e.slug);

test('zhToEnglish: the longest dictionary word wins, negated words are skipped, punctuation ends a negation', () => {
  assert.equal(zhToEnglish('記憶體'), 'memory ram'); // not 記憶 "remember"
  assert.equal(zhToEnglish('批次重新命名檔案'), 'batch bulk rename file');
  assert.equal(zhToEnglish('不用上傳'), '');
  assert.equal(zhToEnglish('不用上傳，要能離線'), 'offline');
  assert.equal(zhToEnglish('plain English'), '');
});

test('rulesTerms: English and dictionary words; the word after "without" or "no" is a constraint, not the job', () => {
  assert.deepEqual(rulesTerms('監控伺服器的 CPU 使用率'), queryTerms('cpu monitor server usage'));
  assert.deepEqual(rulesTerms('text to speech without internet, no cloud'), queryTerms('text speech'));
  assert.deepEqual(rulesTerms('no-code builder'), queryTerms('no-code builder')); // a compound, not a negation
});

test('negation across languages: a Chinese negation also covers the English words after it, up to its clause', () => {
  const has = (text: string, word: string) => rulesTerms(text).includes(terms(word)[0]);
  // The reported request: the negation ends the sentence.
  const photo = '找一個可以在自己電腦上跑、把模糊的照片放大變清楚的 AI 工具，不需要 GPU';
  assert.ok(!has(photo, 'gpu') && has(photo, 'photo'));
  // A clause boundary and a new positive verb end the scope.
  assert.deepEqual(rulesTerms('不需要 GPU，但需要 CUDA'), queryTerms('cuda'));
  assert.deepEqual(rulesTerms('要能管理 Docker 容器，不要 Kubernetes'), queryTerms('docker container'));
  // A list continues it (和, 、, 或); 的 closes the modifier, so the job after it stays.
  assert.deepEqual(rulesTerms('不需要 GPU 和 Docker 的語音轉文字工具'), queryTerms('speech text transcribe'));
  assert.deepEqual(rulesTerms('不需要 GPU、Docker 或 CUDA，但要能跑 Whisper'), queryTerms('whisper'));
  // A negated product name; a Chinese verb after the English object is the job, not part of the negation.
  assert.deepEqual(rulesTerms('不用 Docker 部署本地模型'), queryTerms('deploy deployment local model'));
  assert.ok(!has('不需要 GPU 轉錄會議錄音', 'gpu') && has('不需要 GPU 轉錄會議錄音', 'transcribe'));
  // A short verb before the object belongs to the negation.
  assert.deepEqual(rulesTerms('不想裝 Python，有沒有單一執行檔的 JSON 查詢工具'), queryTerms('json query'));
  assert.ok(!has('不需要用到 GPU 的語音轉文字', 'gpu'));
  assert.deepEqual(rulesTerms('無須註冊、不必 Node.js 的 CLI'), queryTerms('cli'));
  // Not negations: free, "is there".
  assert.deepEqual(rulesTerms('免費的翻譯工具'), queryTerms('translate translation'));
  assert.ok(has('有沒有 Docker 的管理工具', 'docker'));
});

test('negation in English: without, no, no need for, do not need, does not require; it stops at its clause', () => {
  assert.deepEqual(rulesTerms("I don't need Docker, just a single binary to monitor CPU"), queryTerms('single binary monitor cpu'));
  assert.deepEqual(rulesTerms('no need for an account or API key to sync my notes'), queryTerms('sync notes'));
  assert.deepEqual(rulesTerms('a tool that does not require Node.js to convert Markdown to PDF'), queryTerms('convert markdown pdf'));
  assert.deepEqual(rulesTerms('without Docker or Kubernetes, deploy apps to a VPS'), queryTerms('deploy vps'));
  // "and" and "to" (not after a gerund) start what the tool should do.
  assert.deepEqual(rulesTerms('text to speech that works without internet and transcribes audio'), queryTerms('text speech transcribes audio'));
  assert.deepEqual(rulesTerms('search my notes without uploading them to the cloud'), queryTerms('search notes'));
  assert.deepEqual(rulesTerms('a speech-to-text CLI without a GPU, but with CUDA support'), queryTerms('speech text cli cuda support'));
  // The shortlist's own words (keywords path) drop them too.
  assert.equal(dropNegated('不需要 GPU，但需要 CUDA').trim(), '，但需要 CUDA');
});

test('rulesRelevance: a generic word counts for little; matching more of the request beats repeating one word', () => {
  const generic = tool('generic', 'Terminal tool for terminal files in the terminal.');
  const specific = tool('specific', 'Renames with a regex.');
  const both = tool('both', 'Bulk renames with a regex and a preview.');
  const one = tool('one', 'Preview preview preview everything.');
  const corpus = [generic, specific, both, one, ...Array.from({ length: 20 }, (_, i) => tool(`t${i}`, 'A terminal tool for files.'))];
  const scores = rulesRelevance(corpus, corpus, rulesTerms('terminal tool to bulk rename files with a regex and preview'));
  assert.ok(scores.get('specific')! > scores.get('generic')!);
  assert.ok(scores.get('both')! > scores.get('specific')!);
  assert.ok(scores.get('both')! > scores.get('one')!);
  // Plain BM25 (the AI path's shortlist) is unchanged: it does not discount the generic word.
  const plain = relevance(corpus, corpus, queryTerms('terminal'));
  assert.ok(plain.get('generic')! > plain.get('t0')!);
});

test('rankByRules: the relevance score first; equal scores fall to verification on the OS, then treasure', () => {
  const mac = fixtures.bySlug.get('fixture-llm-runner')!; // verified on macOS
  const a = { ...mac, slug: 'a', scores: { ...mac.scores!, treasure_value: 1 } };
  const b = tool('b', 'x', 99);
  const c = tool('c', 'x', 50);
  const order = (scores: Record<string, number>, os?: 'macos') => slugs(rankByRules([a, b, c], new Map(Object.entries(scores)), os));
  assert.deepEqual(order({ a: 1, b: 2, c: 3 }, 'macos'), ['c', 'b', 'a']); // score beats OS and treasure
  assert.deepEqual(order({ a: 2, b: 2, c: 2 }, 'macos'), ['a', 'b', 'c']); // tie: OS, then treasure
  assert.deepEqual(order({ a: 2, b: 2, c: 2 }), ['b', 'c', 'a']); // tie without OS: treasure
});

function many(): Entry[] {
  return [
    ...Array.from({ length: 70 }, (_, i) => tool(`term-${String(i).padStart(2, '0')}`, 'A terminal tool for your files.', 20 + i)),
    tool('regex-renamer', 'Renames files in bulk with a regex, with a preview.', 0),
  ];
}
const asCatalog = (entries: Entry[]): Catalog => ({ ...fixtures, count: entries.length, entries, bySlug: new Map(entries.map((e) => [e.slug, e])) });

test('hardFilter: the rules scorer only when asked; the default scorer is plain BM25', () => {
  const entries = many();
  const text = 'a terminal tool to bulk-rename files with a regex and preview the changes';
  const plain = hardFilter(entries, {}, { terms: queryTerms(text) });
  assert.deepEqual([...plain.relevance], [...relevance(entries, entries, queryTerms(text))]);
  const rules = hardFilter(entries, {}, { terms: rulesTerms(text), scorer: 'rules' });
  assert.deepEqual([...rules.relevance], [...rulesRelevance(entries, entries, rulesTerms(text))]);
  assert.equal(rankByRules(rules.candidates, rules.relevance)[0].slug, 'regex-renamer');
});

test('rules only: a Chinese request ranks through the dictionary, a specific match first', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = asCatalog(many());
  const out = await findSoftware({ need: '想找終端機工具，用正規表示式批次重新命名檔案' }, h.deps);
  assert.equal(out.picks[0].slug, 'regex-renamer');
});

test('with keywords from Meta the cards sent to the model are the plain-BM25 shortlist, as before', async () => {
  const keywords = ['bulk rename', 'regex', 'files'];
  const need = '想找終端機工具，用正規表示式批次重新命名檔案';
  const h = harness((body) =>
    body.text.format.name === 'pickfit_keywords'
      ? metaResponse({ keywords })
      : metaResponse(answer({ picks: [], best_free_slug: null })),
  );
  const entries = many();
  h.deps.catalog = asCatalog(entries);
  await findSoftware({ need }, h.deps);
  const sent = h.requests[1].body.text.format.schema.properties.picks.items.properties.slug.enum;
  const expected = hardFilter(entries, {}, { terms: queryTerms(need, ...keywords) }).candidates;
  assert.equal(expected.length, MAX_CARDS);
  assert.deepEqual(sent, slugs(expected));
});
