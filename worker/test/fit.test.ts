import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Catalog, Entry } from '../src/catalog.ts';
import { fitNote, fitOf, jobOf } from '../src/fit.ts';
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
  assert.deepEqual(job('text-to-speech without sending my notes to the cloud').terms, ['speech']); // to the end of the clause
  const gpu = [tool('gpu-tts', 'Text-to-speech on a GPU.')];
  assert.deepEqual(jobOf(gpu, 'a text-to-speech tool on a GPU').terms, ['speech', 'gpu']);
  assert.deepEqual(jobOf(gpu, 'a text-to-speech tool, 不需要 GPU').terms, ['speech']); // a Chinese negation of an English word
  assert.deepEqual([...job('不用 Notion 也能搜尋筆記').named], []); // a negated product is not required
});

test('jobOf: a Chinese word counts once whatever its synonyms; OS names, context and the kind of tool are not products', () => {
  const top = [tool('top', 'Monitors CPU, memory and RAM usage.'), tool('enc', 'Converts text encoding.'), tool('scan', 'Scans Node and Python dependencies.')];
  assert.deepEqual(jobOf(top, '監控記憶體').words, [['monitor'], ['memory', 'ram']]);
  assert.deepEqual(jobOf(top, 'AI 編碼助手').terms, []); // a coding assistant, not text encoding
  assert.deepEqual([...jobOf(top, 'a macOS tool to monitor memory').named], []);
  assert.deepEqual([...jobOf(top, 'scan my Node project dependencies').named], []); // where the job happens
  assert.deepEqual([...jobOf(top, 'scan dependencies for Node').named], ['nod']);
});

test('fitOf: good covers most of the job, two words and every named product; partial a third and two words, or half; else weak', () => {
  assert.equal(fit('renamer', 'bulk rename files with a regex').quality, 'good');
  const grep = fit('grepper', 'bulk rename files with a regex and preview the changes');
  assert.equal(grep.quality, 'weak'); // one shared word ("regex") of four is not enough
  assert.deepEqual(grep.covers, ['regex']);
  assert.equal(fit('grepper', 'search my notes').quality, 'partial'); // one word, but half the request
  const notes = fit('vault', 'search and edit my Notion notes');
  assert.equal(notes.quality, 'weak'); // it covers most words, but not the product named
  const sync = fit('notes-sync', 'search and edit my Notion notes');
  assert.deepEqual([sync.quality, sync.covers, sync.missing], ['partial', ['notion', 'notes'], ['search', 'edit']]); // half is not most
  const part = fit('notes-sync', 'search, edit and sync my Notion notes in a vault with a regex');
  assert.deepEqual([part.quality, part.covers], ['partial', ['sync', 'notion', 'notes']]);
  assert.equal(fit('speaker', 'a text-to-speech tool with natural voices').quality, 'good');
  assert.equal(fit('speaker', 'a text-to-speech tool that sounds natural').quality, 'partial'); // one specific word
  assert.equal(fit('notes-sync', 'a Notion MCP server').quality, 'good'); // one word, a product it names
});

test('fitOf: a product mentioned only as what the tool replaces counts only for a request to replace it', () => {
  const tools = [tool('plane', 'Plans work items from git history.', { tags: ['jira-alternative'] }), tool('jira-mcp', 'Creates and updates Jira tickets and items.')];
  const fits = (text: string) => tools.map((e) => fitOf(e, jobOf(tools, text)).quality);
  assert.deepEqual(fits('manage my Jira tickets'), ['weak', 'good']);
  assert.deepEqual(fits('an alternative to Jira for work items'), ['good', 'weak']);
});

test('fitOf: nothing specific asked is a good fit; only words the catalog never uses is weak', () => {
  assert.equal(fit('vault', 'a free tool for my Mac').quality, 'good');
  assert.deepEqual(fit('vault', 'defragment the hard drive').quality, 'weak');
});

test('labels only: rules picks keep their rank order; each says what it covers', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = catalog(corpus);
  const out = await findSoftware({ need: 'bulk rename files with a regex and preview them' }, h.deps);
  assert.equal(out.match_quality, 'good');
  assert.deepEqual(out.picks.map((p) => [p.slug, p.match?.quality]), [['renamer', 'good'], ['grepper', 'weak'], ['notes-sync', 'weak']]);
  assert.deepEqual(out.picks[0].tradeoffs, []);
  assert.deepEqual(out.picks[1].tradeoffs, ['Weak match: its profile mentions regex but not bulk, rename, preview.']);
  assert.equal(out.coverage_note, null);
});

test('no pick reaches partial: the picks stay listed, and the note names what they miss without dismissing them', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = catalog(corpus);
  const out = await findSoftware({ need: 'manage my Jira tickets' }, h.deps);
  await h.settle();
  assert.equal(out.match_quality, 'none');
  assert.equal(out.picks.length, 3);
  assert.ok(out.picks.every((p) => p.match?.quality === 'weak'));
  assert.ok(out.best_free);
  assert.match(out.coverage_note ?? '', /^pickfit has no verified tool that clearly does this job\. .*the listed tools are the closest it has, but none of them mentions jira; each pick's match says what it covers\./);
  assert.doesNotMatch(out.coverage_note ?? '', /do not use|don't use|ignore|drop/i);
  assert.equal(out.well_known_option, null);
  const row = h.sqlite.prepare('SELECT need, results FROM events').get() as any;
  assert.equal(JSON.parse(row.need).match_quality, 'none');
  assert.equal(JSON.parse(row.results).length, 3);
});

test('the best pick is partial: the note names its gaps; a closer tool past the picks changes the none wording', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = catalog(corpus);
  const partial = await findSoftware({ need: 'search, edit and sync my Notion notes in a vault with a regex', limit: 3 }, h.deps);
  assert.equal(partial.match_quality, 'partial');
  // The top-ranked pick is weak (it does not name Notion); the second is partial and is named.
  assert.deepEqual(partial.picks.map((p) => p.match?.quality), ['weak', 'partial', 'weak']);
  assert.equal(partial.coverage_note, 'No listed tool covers the whole request: the closest, notes-sync, does not mention search, edit, vault, regex. Each pick\'s match says what it covers.');
  assert.equal(fitNote({ quality: 'weak', covers: [], missing: ['jira'] }), 'Weak match: its profile mentions none of jira.');
  const one = await findSoftware({ need: 'search, edit and sync my Notion notes in a vault with a regex', limit: 1 }, h.deps);
  assert.deepEqual([one.picks.map((p) => p.slug), one.match_quality], [['vault'], 'none']);
  assert.match(one.coverage_note ?? '', /^None of the listed tools clearly does this job: judging by their profiles, none of them mentions sync, notion, regex\./);
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
