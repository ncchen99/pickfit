import assert from 'node:assert/strict';
import { test } from 'node:test';
import { findAlternatives, findSoftware, type FindInput } from '../src/find.ts';
import { hardFilter, MAX_CARDS } from '../src/filter.ts';
import { guardWellKnown } from '../src/guard.ts';
import { MATCH_INSTRUCTIONS } from '../src/prompt.ts';
import { answer, fixtureCatalog, harness, metaResponse } from './helpers.ts';

const MAC_OFFLINE: FindInput = {
  need: 'run a small language model offline on my Mac (secret-project-xyz)',
  os: 'macos',
  budget: 'free_only',
  must_run_locally: true,
};

const OLLAMA = {
  well_known_name: 'Ollama',
  well_known_why: 'Ollama is free, runs models offline on macOS and needs no API setup. It is also widely used.',
};

test('a well-known free tool is named outside the picks, labelled unverified by code', async () => {
  const h = harness(() => metaResponse(answer(OLLAMA)));
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  await h.settle();

  // The picks are unchanged: still pickfit's verified candidates.
  assert.deepEqual(out.picks.map((p) => p.slug), ['fixture-llm-runner', 'fixture-chat-tui']);
  assert.deepEqual(out.well_known_option, {
    name: 'Ollama',
    why: 'Ollama is free, runs models offline on macOS and needs no API setup.', // first sentence only
    verified: false,
    how_we_know:
      "Named by muse-spark-1.3 from general knowledge, not from pickfit's data. " +
      'pickfit has not installed it, has no install guide for it and has not checked its price, that it runs on macos or that it works offline.',
  });

  const row = h.sqlite.prepare('SELECT * FROM events WHERE type = ?').get('find') as any;
  assert.deepEqual(JSON.parse(row.need).well_known, { name: 'Ollama', dropped: null });
  assert.deepEqual(JSON.parse(row.results), ['fixture-llm-runner', 'fixture-chat-tui']);
  assert.ok(!JSON.stringify(row).includes('secret-project-xyz'));
});

test('how_we_know lists only the conditions the person gave', async () => {
  const h = harness(() => metaResponse(answer({ well_known_name: 'jq', well_known_why: 'jq is free and does exactly this.' })));
  const out = await findSoftware({ need: 'query json in the terminal' }, h.deps);
  assert.match(out.well_known_option!.how_we_know, /has not checked its price\.$/);
});

test('the prompt asks for it rarely, and the schema allows only a name and a sentence', async () => {
  const h = harness(() => metaResponse(answer()));
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  await h.settle();
  assert.equal(out.well_known_option, null);
  const row = h.sqlite.prepare('SELECT need FROM events').get() as any;
  assert.equal(JSON.parse(row.need).well_known, null);

  assert.match(MATCH_INSTRUCTIONS, /10\. well_known_name and well_known_why: usually both null/);
  assert.match(MATCH_INSTRUCTIONS, /never say it was verified or tested/);
  const schema = h.requests[0].body.text.format.schema;
  assert.deepEqual(schema.properties.well_known_name, { type: ['string', 'null'] });
  assert.deepEqual(schema.properties.well_known_why, { type: ['string', 'null'] });
  assert.ok(schema.required.includes('well_known_name') && schema.required.includes('well_known_why'));
});

test('guard: what code can check about a tool it does not list', () => {
  const entries = fixtureCatalog().entries;
  const check = (name: string | null, why: string | null, current?: string) =>
    guardWellKnown(answer({ well_known_name: name, well_known_why: why }), entries, current);

  assert.deepEqual(check(null, null), { option: null, name: null, dropped: null });
  assert.deepEqual(check('  ', 'Free.'), { option: null, name: null, dropped: null });
  // A pickfit entry is a pick or was filtered out for a reason; it is never "outside".
  assert.equal(check('Fixture LLM Runner', 'It is free.').dropped, 'listed_in_pickfit');
  assert.equal(check('fixture-json-query', 'It is free.').dropped, 'listed_in_pickfit');
  assert.equal(check('ollama', 'It is free.', 'Ollama').dropped, 'current_tool');
  assert.equal(check('https://ollama.com', 'It is free.').dropped, 'not_a_name');
  assert.equal(check('A very long sentence that is not the name of any tool at all, really', 'Free.').dropped, 'not_a_name');
  assert.equal(check('Ollama', null).dropped, 'no_reason');
  assert.equal(check('Ollama', 'Runs models offline on macOS.').dropped, 'not_said_free');
  // It is the second sentence that says free: only the first one is kept.
  assert.equal(check('Ollama', 'Runs models offline. It is free.').dropped, 'not_said_free');
  assert.equal(check('Ollama', 'Free and verified to run offline on macOS.').dropped, 'claims_checked');
  assert.equal(check('Ollama', 'Free, and pickfit users like it.').dropped, 'claims_checked');

  const kept = check('llama.cpp', 'llama.cpp is free and runs on old laptops without a GPU. More text.');
  assert.deepEqual(kept.option, { name: 'llama.cpp', why: 'llama.cpp is free and runs on old laptops without a GPU.' });
});

test('a dropped option is not shown, but the log keeps the name and why', async () => {
  const h = harness(() => metaResponse(answer({ well_known_name: 'Fixture Chat TUI', well_known_why: 'Free.' })));
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  await h.settle();
  assert.equal(out.well_known_option, null);
  assert.equal(out.degraded, false);
  const row = h.sqlite.prepare('SELECT need FROM events').get() as any;
  assert.deepEqual(JSON.parse(row.need).well_known, { name: 'Fixture Chat TUI', dropped: 'listed_in_pickfit' });
});

test('find_alternatives never offers the current tool as the well-known option', async () => {
  const h = harness(() =>
    metaResponse(answer({ well_known_name: 'Ollama', well_known_why: 'Ollama is free.', keep_current: { recommended: true, reason: 'x' } })),
  );
  const out = await findAlternatives({ current_software: 'Ollama', pain_points: 'too heavy', os: 'linux' }, h.deps);
  assert.equal(out.well_known_option, null);

  const h2 = harness(() =>
    metaResponse(answer({ well_known_name: 'llama.cpp', well_known_why: 'llama.cpp is free and much lighter.', keep_current: { recommended: false, reason: 'x' } })),
  );
  const out2 = await findAlternatives({ current_software: 'Ollama', pain_points: 'too heavy', os: 'linux' }, h2.deps);
  assert.equal(out2.well_known_option?.name, 'llama.cpp');
  assert.match(out2.well_known_option!.how_we_know, /runs on linux\.$/);
});

test('without the model there is no well-known option; with no candidates the note says one may fit', async () => {
  const rules = await findSoftware(MAC_OFFLINE, harness(null, { modelEnabled: false }).deps);
  assert.equal(rules.matched_by, 'rules');
  assert.equal(rules.well_known_option, null);

  const h = harness(null);
  const none = await findSoftware(
    { need: 'local transcription', os: 'windows', category: 'local_ai', exclude: ['fixture-chat-tui'] },
    h.deps,
  );
  assert.equal(h.requests.length, 0);
  assert.equal(none.well_known_option, null);
  assert.match(none.coverage_note ?? '', /No verified tool.*lists mostly lesser-known tools, so a well-known one may still fit\./);
});

// Reference records of well-known tools (phase 2): real picks with verified steps, flagged, never treasures.
const OLLAMA_REF = { package: 'homebrew:ollama', rank: 23, count: 655153, period_end: '2026-10-29' };

function withReferences(h: ReturnType<typeof harness>, slugs: string[]) {
  for (const slug of slugs) {
    const entry = h.deps.catalog.bySlug.get(slug)!;
    entry.well_known = { ...OLLAMA_REF, package: `homebrew:${slug}` };
  }
}

test('a well-known reference record is a real pick, flagged, and at most one is kept', async () => {
  const h = harness(() => metaResponse(answer()));
  withReferences(h, ['fixture-llm-runner', 'fixture-chat-tui']);
  const out = await findSoftware(MAC_OFFLINE, h.deps);

  // The model chose both; the guard keeps the first reference record only.
  assert.deepEqual(out.picks.map((p) => p.slug), ['fixture-llm-runner']);
  const [pick] = out.picks;
  assert.deepEqual(pick.well_known, { ...OLLAMA_REF, package: 'homebrew:fixture-llm-runner' });
  assert.match(pick.how_we_know, /A well-known tool listed as a reference: homebrew:fixture-llm-runner is #23 in Homebrew installs/);
  assert.equal(pick.verification.verified_on_user_os, true); // verified like the rest
  // The model sees the flag on the card, and the prompt says what it means.
  const input = h.requests[0].body.input[1].content as string;
  assert.match(input, /"slug":"fixture-llm-runner"[^\n]*"well_known":true/);
  assert.match(input, /"slug":"fixture-transcribe"[^\n]*"well_known":false/);
  assert.match(MATCH_INSTRUCTIONS, /well_known true is a reference record of a well-known tool/);
});

test('long-tail picks carry well_known null; rules keep at most one reference record too', async () => {
  const plain = await findSoftware(MAC_OFFLINE, harness(() => metaResponse(answer())).deps);
  assert.ok(plain.picks.every((p) => p.well_known === null));

  const h = harness(null, { modelEnabled: false });
  withReferences(h, ['fixture-llm-runner', 'fixture-chat-tui', 'fixture-transcribe']);
  const out = await findSoftware({ need: 'local language model chat offline', os: 'linux' }, h.deps);
  assert.equal(out.matched_by, 'rules');
  assert.equal(out.picks.filter((p) => p.well_known).length, 1);
  assert.ok(out.picks.length >= 2);
});

test('above MAX_CARDS the reference records stay among the cards', () => {
  const base = fixtureCatalog().bySlug.get('fixture-json-query')!;
  const entries = Array.from({ length: MAX_CARDS + 5 }, (_, i) => ({
    ...structuredClone(base),
    slug: `tail-${String(i).padStart(2, '0')}`,
    scores: { ...base.scores!, treasure_value: 90 },
  }));
  entries.push({ ...structuredClone(base), slug: 'famous', well_known: OLLAMA_REF, scores: { ...base.scores!, treasure_value: 5 } });
  const { candidates, passed } = hardFilter(entries, { os: 'linux' });
  assert.equal(passed, MAX_CARDS + 6);
  assert.equal(candidates.length, MAX_CARDS);
  assert.ok(candidates.some((e) => e.slug === 'famous'));
});
