import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Catalog, Entry } from '../src/catalog.ts';
import { findAlternatives, findSoftware } from '../src/find.ts';
import { hardFilter, MAX_CARDS, TREASURE_SLOTS } from '../src/filter.ts';
import { MATCH_MODEL } from '../src/meta.ts';
import { queryTerms, relevance, terms } from '../src/relevance.ts';
import { rankByRules } from '../src/rules.ts';
import { answer, fixtureCatalog, harness, metaResponse } from './helpers.ts';

const fixtures = fixtureCatalog();
const fixture = (slug: string) => fixtures.bySlug.get(slug)!;

function like(base: string, slug: string, treasure: number, fields: Partial<Entry> = {}): Entry {
  const entry = fixture(base);
  return { ...entry, slug, name: slug, scores: { ...entry.scores!, treasure_value: treasure }, ...fields };
}

/** 70 spreadsheet tools with high treasure values, and two low-treasure tools that fit particular requests. */
function bulk(): Entry[] {
  const filler = Array.from({ length: 70 }, (_, i) =>
    like('fixture-json-query', `sheet-${String(i).padStart(2, '0')}`, 20 + i, {
      summary: 'Formats spreadsheet cells in the terminal.',
      why_worth_it: null,
      tags: ['spreadsheet', 'csv'],
      use_cases: ['tidy a spreadsheet'],
      alternatives_to: [],
    }),
  );
  return [
    ...filler,
    like('fixture-transcribe', 'quiet-transcriber', 1, { summary: 'Transcribes audio recordings to text offline.' }),
    like('fixture-json-query', 'quiet-yaml', 0, {
      summary: 'Edits configuration files from scripts.',
      tags: ['yaml'],
      use_cases: [],
      alternatives_to: ['jq'],
    }),
  ];
}

const asCatalog = (entries: Entry[]): Catalog => ({ ...fixtures, count: entries.length, entries, bySlug: new Map(entries.map((e) => [e.slug, e])) });
const slugsOf = (entries: Entry[]) => entries.map((e) => e.slug);

test('terms: camelCase and snake_case split, stopwords dropped, plural and -ing forms agree; other scripts give none', () => {
  assert.deepEqual(terms('convertingFiles to_JSON'), ['convert', 'fil', 'json']);
  assert.deepEqual(terms('I want a tool that converts files'), terms('convert file'));
  assert.deepEqual(terms('queries'), terms('query'));
  assert.deepEqual(terms('runs locally, privately'), terms('run local private'));
  assert.deepEqual(terms('assemblies'), terms('assembly'));
  assert.deepEqual(terms('我想要把錄音轉成文字'), []);
  assert.deepEqual(queryTerms('audio audio', 'Audio files'), ['audio', 'fil']);
});

test('relevance: a profile that shares the request words scores above 0, one that shares none scores 0', () => {
  const entries = bulk();
  const scores = relevance(entries, entries, queryTerms('transcribe my audio recordings'));
  assert.ok(scores.get('quiet-transcriber')! > 0);
  assert.equal(scores.get('sheet-00'), 0);
  // A word in the name or tags weighs more than the same word only in a use case.
  const named = like('fixture-json-query', 'yaml-name', 0, { name: 'yaml tool', tags: [], use_cases: ['edit files'] });
  const used = like('fixture-json-query', 'yaml-used', 0, { name: 'other', tags: [], use_cases: ['edit yaml files'] });
  const pair = relevance([named, used], [named, used], ['yaml']);
  assert.ok(pair.get('yaml-name')! > pair.get('yaml-used')!);
});

test('shortlist above MAX_CARDS: a fitting low-treasure tool gets in; cards stay in slug order', () => {
  const entries = bulk();
  const before = hardFilter(entries, {});
  assert.ok(!slugsOf(before.candidates).includes('quiet-transcriber')); // treasure order alone cuts it
  const after = hardFilter(entries, {}, { terms: queryTerms('transcribe my audio recordings') });
  assert.equal(after.passed, 72);
  assert.equal(after.candidates.length, MAX_CARDS);
  assert.ok(slugsOf(after.candidates).includes('quiet-transcriber'));
  assert.equal(after.byRelevance, 1);
  assert.deepEqual(slugsOf(after.candidates), [...slugsOf(after.candidates)].sort());
});

test('shortlist keeps TREASURE_SLOTS for the highest treasure values when many tools match', () => {
  const matching = Array.from({ length: 65 }, (_, i) =>
    like('fixture-transcribe', `match-${String(i).padStart(2, '0')}`, i, { summary: 'Transcribes audio.' }),
  );
  const general = Array.from({ length: 15 }, (_, i) =>
    like('fixture-json-query', `general-${String(i).padStart(2, '0')}`, 100 + i, { summary: 'Queries JSON.', tags: ['json'], use_cases: [] }),
  );
  const { candidates, byRelevance } = hardFilter([...matching, ...general], {}, { terms: queryTerms('transcribe audio') });
  assert.equal(byRelevance, MAX_CARDS - TREASURE_SLOTS);
  const kept = slugsOf(candidates).filter((s) => s.startsWith('general-'));
  assert.deepEqual(kept, Array.from({ length: TREASURE_SLOTS }, (_, i) => `general-${String(5 + i).padStart(2, '0')}`));
  // Among equal matches the higher treasure values win the relevance slots.
  assert.ok(slugsOf(candidates).includes('match-64'));
  assert.ok(!slugsOf(candidates).includes('match-00'));
});

test('hard filters never relax for a strong match', () => {
  const paid = like('fixture-transcribe', 'paid-transcriber', 99, { pricing: 'paid', summary: 'Transcribes audio recordings to text.' });
  const entries = [...bulk(), paid];
  const { candidates, relevance: scores } = hardFilter(entries, { budget: 'free_only' }, { terms: queryTerms('transcribe audio recordings') });
  assert.ok(!slugsOf(candidates).includes('paid-transcriber'));
  assert.ok(!scores.has('paid-transcriber'));
});

test('find_alternatives: a tool that names the current one in alternatives_to is always shortlisted', () => {
  const { candidates } = hardFilter(bulk(), {}, { terms: queryTerms('too slow on big files'), current: 'jq' });
  assert.ok(slugsOf(candidates).includes('quiet-yaml'));
});

test('rules: relevance tier first, then verification on the OS, then treasure', () => {
  const entries = bulk();
  const scores = relevance(entries, entries, queryTerms('transcribe audio recordings'));
  assert.equal(rankByRules(entries, scores)[0].slug, 'quiet-transcriber');
  const same = { summary: 'Transcribes audio recordings to text offline.', why_worth_it: null, tags: ['audio'], use_cases: [], alternatives_to: [] };
  const mac = like('fixture-llm-runner', 'mac-transcriber', 0, same);
  const linux = like('fixture-transcribe', 'linux-transcriber', 90, same);
  const pair = relevance([mac, linux], [mac, linux], queryTerms('transcribe audio recordings'));
  assert.deepEqual(slugsOf(rankByRules([mac, linux], pair, 'macos')), ['mac-transcriber', 'linux-transcriber']);
  assert.deepEqual(slugsOf(rankByRules([mac, linux], pair)), ['linux-transcriber', 'mac-transcriber']);
  // No word matches: treasure order, as before.
  assert.deepEqual(slugsOf(rankByRules(entries, new Map())).slice(0, 2), ['sheet-69', 'sheet-68']);
});

const ZH_NEED = '我想把會議錄音轉成逐字稿 (secret-xyz)';

function twoCalls(keywords: Response | (() => Response), pick = 'quiet-transcriber') {
  return (body: any) =>
    body.text.format.name === 'pickfit_keywords'
      ? typeof keywords === 'function'
        ? keywords()
        : keywords
      : metaResponse(
          answer({
            picks: [{ slug: pick, fit: 'Transcribes recordings offline.', reasons: [{ claim: 'Free', field: 'pricing', value: 'free' }], tradeoffs: [], vs_well_known: null }],
            best_free_slug: null,
          }),
        );
}

test('a request over MAX_CARDS gets English keywords from muse-spark-1.3 first (here a Chinese one)', async () => {
  const h = harness(twoCalls(() => metaResponse({ keywords: ['transcribe audio', 'speech to text', 'recordings'] })));
  h.deps.catalog = asCatalog(bulk());
  const out = await findSoftware({ need: ZH_NEED }, h.deps);
  await h.settle();

  assert.equal(h.requests.length, 2);
  const [kw, match] = h.requests.map((r) => r.body);
  assert.equal(kw.model, MATCH_MODEL);
  assert.equal(kw.store, false);
  assert.deepEqual(kw.reasoning, { effort: 'minimal' });
  assert.equal(kw.text.format.strict, true);
  assert.match(kw.input[1].content, /<request>\n.*secret-xyz.*\n<\/request>/);
  assert.ok(match.text.format.schema.properties.picks.items.properties.slug.enum.includes('quiet-transcriber'));
  assert.equal(out.matched_by, MATCH_MODEL);
  assert.deepEqual(out.picks.map((p) => p.slug), ['quiet-transcriber']);
  assert.match(out.coverage_note ?? '', /72 tools met the conditions; the 60 compared were the 1 whose profiles best match/);

  const row = h.sqlite.prepare('SELECT * FROM events WHERE type = ?').get('find') as any;
  assert.deepEqual(JSON.parse(row.need).shortlist, { by_relevance: 1, keywords: 'ok' });
  const budget = h.sqlite.prepare('SELECT * FROM meta_budget').get() as any;
  assert.equal(budget.calls, 2);
  assert.ok(Math.abs(row.meta_cost_usd - budget.cost_usd) < 1e-12);
  const stored = JSON.stringify(h.sqlite.prepare('SELECT * FROM events').all());
  assert.ok(!stored.includes('secret-xyz') && !stored.includes('transcribe audio'));
});

test('when the keyword call fails the rules scorer chooses the cards (Chinese through the dictionary) and matching goes on', async () => {
  for (const failure of [new Response('{}', { status: 500 }), metaResponse('not json')]) {
    const h = harness(twoCalls(() => failure.clone()));
    h.deps.catalog = asCatalog(bulk());
    const out = await findSoftware({ need: ZH_NEED }, h.deps);
    await h.settle();
    assert.equal(h.requests.length, 2);
    assert.ok(h.requests[1].body.text.format.schema.properties.picks.items.properties.slug.enum.includes('quiet-transcriber'));
    assert.equal(out.matched_by, MATCH_MODEL);
    const row = h.sqlite.prepare('SELECT need FROM events WHERE type = ?').get('find') as any;
    assert.ok(JSON.parse(row.need).shortlist.by_relevance >= 1);
    assert.match(JSON.parse(row.need).shortlist.keywords, /^model_(http|bad_output)$/);
  }
  // No word the profiles or the dictionary know: the treasure order, as before.
  const h = harness(twoCalls(() => new Response('{}', { status: 500 }), 'sheet-69'));
  h.deps.catalog = asCatalog(bulk());
  const out = await findSoftware({ need: '我想要一個好用的東西 (secret-xyz)' }, h.deps);
  assert.ok(!h.requests[1].body.text.format.schema.properties.picks.items.properties.slug.enum.includes('quiet-transcriber'));
  assert.match(out.coverage_note ?? '', /no profile matched the request's words/);
});

test('English requests get keywords too (synonyms); none when at most MAX_CARDS tools meet the conditions', async () => {
  const h = harness(twoCalls(() => metaResponse({ keywords: ['transcribe', 'speech to text'] })));
  h.deps.catalog = asCatalog(bulk());
  const out = await findSoftware({ need: 'dictate my notes' }, h.deps);
  assert.equal(h.requests.length, 2);
  assert.ok(h.requests[1].body.text.format.schema.properties.picks.items.properties.slug.enum.includes('quiet-transcriber'));
  assert.deepEqual(out.picks.map((p) => p.slug), ['quiet-transcriber']);
  const small = harness(twoCalls(() => metaResponse({ keywords: [] }), 'fixture-transcribe'));
  await findSoftware({ need: ZH_NEED }, small.deps);
  assert.equal(small.requests.length, 1);
  await small.settle();
  const row = small.sqlite.prepare('SELECT need FROM events WHERE type = ?').get('find') as any;
  assert.equal(JSON.parse(row.need).shortlist, null);
});

test('rules only (MATCH_MODE off): no Meta call at all, picks ranked by relevance', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = asCatalog(bulk());
  const en = await findSoftware({ need: 'transcribe my audio recordings to text' }, h.deps);
  assert.equal(en.matched_by, 'rules');
  assert.equal(en.picks[0].slug, 'quiet-transcriber');
  const zh = await findSoftware({ need: ZH_NEED }, h.deps);
  assert.equal(zh.degraded_reason, 'model_off');
  assert.equal(zh.picks[0].slug, 'quiet-transcriber'); // 錄音, 逐字稿 through the dictionary
  const none = await findSoftware({ need: '我想要一個好用的東西' }, h.deps);
  await h.settle();
  assert.equal(none.picks[0].slug, 'sheet-69'); // nothing to match: treasure order
  const rows = h.sqlite.prepare('SELECT need FROM events ORDER BY rowid').all() as any[];
  assert.deepEqual(rows.map((r) => JSON.parse(r.need).shortlist.keywords), ['model_off', 'model_off', 'model_off']);
});

test('degraded after the keywords: the rules use them', async () => {
  const h = harness((body) =>
    body.text.format.name === 'pickfit_keywords'
      ? metaResponse({ keywords: ['transcribe audio', 'recordings'] })
      : new Response('{}', { status: 400 }),
  );
  h.deps.catalog = asCatalog(bulk());
  const out = await findSoftware({ need: ZH_NEED }, h.deps);
  assert.equal(out.degraded_reason, 'model_http');
  assert.equal(out.picks[0].slug, 'quiet-transcriber');
});

test('find_alternatives over MAX_CARDS keeps the tools that replace the current one', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = asCatalog(bulk());
  const out = await findAlternatives({ current_software: 'jq', pain_points: 'hard to remember the syntax' }, h.deps);
  assert.equal(out.picks[0].slug, 'quiet-yaml');
});
