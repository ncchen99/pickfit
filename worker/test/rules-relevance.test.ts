import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Catalog, Entry } from '../src/catalog.ts';
import { findSoftware } from '../src/find.ts';
import { hardFilter, MAX_CARDS } from '../src/filter.ts';
import { queryTerms, relevance, rulesRelevance, rulesTerms, terms, zhToEnglish } from '../src/relevance.ts';
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
