import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Catalog, Entry } from '../src/catalog.ts';
import { fitOf, jobOf } from '../src/fit.ts';
import { findAlternatives, findSoftware } from '../src/find.ts';
import { answer, fixtureCatalog, harness, metaResponse } from './helpers.ts';

const fixtures = fixtureCatalog();

function tool(slug: string, summary: string, fields: Partial<Entry> = {}): Entry {
  const base = fixtures.bySlug.get('fixture-json-query')!;
  return { ...base, slug, name: slug, summary, why_worth_it: null, tags: [], use_cases: [], alternatives_to: [], ...fields };
}

const corpus = [
  tool('renamer', 'Renames files in bulk with a regex and a preview.'),
  tool('grepper', 'Searches files with a regex.'),
  tool('notes-sync', 'Syncs Notion pages to Markdown notes.', { tags: ['notion'] }),
  tool('vault', 'Searches and edits Markdown notes in a vault.'),
  tool('speaker', 'Offline text-to-speech with natural voices.'),
  tool('tts-alt', 'Reads text aloud.', { alternatives_to: ['Balabolka'] }),
];
const catalog = (entries: Entry[]): Catalog => ({ ...fixtures, count: entries.length, entries, bySlug: new Map(entries.map((e) => [e.slug, e])) });
const job = (text: string) => jobOf(corpus, text);
const fit = (slug: string, text: string) => fitOf(corpus.find((e) => e.slug === slug)!, job(text));

test('jobOf: the specific words of the job, without the kind of tool, filler, constraints or labels', () => {
  assert.deepEqual(job('I need an MCP server so the AI assistant can search my Notion pages').terms, ['search', 'notion', 'pag']);
  assert.deepEqual([...job('search my Notion pages').named], ['notion']);
  assert.deepEqual([...job('search PDF and JSON files').named], []); // formats are words of the job, not names
  assert.deepEqual(job('text-to-speech without internet, no cloud account').terms, ['text-to-speech'].flatMap(() => ['speech']));
  assert.deepEqual(job('keep an eye on my notes (secret-project-xyz)').terms, job('monitor my notes').terms);
  assert.deepEqual(job('類似 ChatGPT 的工具，用正規表示式找檔案').terms, ['regex']);
  assert.deepEqual(job('defragment my disk').unknown, ['defragment', 'disk']);
});

test('fitOf: good covers half the job and every named product; partial a third and two words; else none', () => {
  assert.equal(fit('renamer', 'bulk rename files with a regex').quality, 'good');
  const grep = fit('grepper', 'bulk rename files with a regex and preview the changes');
  assert.equal(grep.quality, 'none'); // one shared word ("regex") is not enough
  assert.deepEqual(grep.covers, ['regex']);
  const notes = fit('vault', 'search and edit my Notion notes');
  assert.equal(notes.quality, 'none'); // it covers most words, but not the product named
  const sync = fit('notes-sync', 'search and edit my Notion notes');
  assert.deepEqual([sync.quality, sync.covers, sync.missing], ['good', ['notion', 'notes'], ['search', 'edit']]);
  const part = fit('notes-sync', 'search, edit and sync my Notion notes in a vault with a regex');
  assert.deepEqual([part.quality, part.covers], ['partial', ['sync', 'notion', 'notes']]);
  assert.equal(fit('speaker', 'a text-to-speech tool that sounds natural').quality, 'good');
});

test('fitOf: nothing specific asked is a good fit; only words the catalog never uses is none', () => {
  assert.equal(fit('vault', 'a free tool for my Mac').quality, 'good');
  assert.deepEqual(fit('vault', 'defragment the hard drive').quality, 'none');
});

test('no good match: no picks, no best_free, no question, and a note that says so', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = catalog(corpus);
  const out = await findSoftware({ need: 'manage my Jira tickets' }, h.deps);
  await h.settle();
  assert.deepEqual([out.match_quality, out.picks, out.best_free, out.clarifying_question], ['none', [], null, null]);
  assert.match(out.coverage_note ?? '', /pickfit has no verified tool for this yet: .*none of the 6 that meet the conditions does this job \(the closest profile does not mention: jira\)/);
  assert.equal(out.well_known_option, null);
  const row = h.sqlite.prepare('SELECT need, results FROM events').get() as any;
  assert.equal(JSON.parse(row.need).match_quality, 'none');
  assert.deepEqual(JSON.parse(row.results), []);
});

test('good picks come first, then partial ones, in rank order; tools that do not fit are not shown', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = catalog(corpus);
  const out = await findSoftware({ need: 'bulk rename files with a regex and preview them' }, h.deps);
  assert.equal(out.match_quality, 'good');
  assert.deepEqual(out.picks.map((p) => [p.slug, p.match?.quality]), [['renamer', 'good']]);
});

test('find_alternatives: a tool that names the current one is a good fit, whatever the pain points say', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = catalog(corpus);
  const out = await findAlternatives({ current_software: 'Balabolka', pain_points: 'the voices sound robotic' }, h.deps);
  assert.equal(out.picks[0].slug, 'tts-alt');
  assert.deepEqual(out.picks[0].match, { quality: 'good', covers: ['an alternative to Balabolka'], missing: [] });
});

test('the model path is untouched: no fit fields, picks as the model chose them', async () => {
  const h = harness(() => metaResponse(answer()));
  const out = await findSoftware({ need: 'search my Notion pages', os: 'macos' }, h.deps);
  assert.equal(out.matched_by, 'muse-spark-1.3');
  assert.ok(!('match_quality' in out));
  assert.ok(out.picks.length > 0 && out.picks.every((p) => !('match' in p)));
});
