/** P2-01 (recommend strictly) and P2-02 (agent-first MCP: reuse and build_it_yourself), brief 15.1, 15.5, 15.6. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Entry, InstallGuide } from '../src/catalog.ts';
import { toCard } from '../src/cards.ts';
import { beyondInstall, hardFilter, MIN_BEYOND_INSTALL, verifiedLevel } from '../src/filter.ts';
import { findSoftware } from '../src/find.ts';
import { guardAdvice, guardBuildItYourself, guardNoInstall, guardReuse } from '../src/guard.ts';
import { MATCH_MODEL } from '../src/meta.ts';
import { MATCH_INSTRUCTIONS, matchSchema } from '../src/prompt.ts';
import { rulesTerms } from '../src/relevance.ts';
import { INSTALL_ONLY_NOTE, rankByRules, saysInstallOnly } from '../src/rules.ts';
import { BEFORE_BUILDING, INSTRUCTIONS, READONLY_INSTRUCTIONS } from '../src/server.ts';
import { findSummary } from '../src/summary.ts';
import { answer, fixtureCatalog, harness, modelResponse } from './helpers.ts';

const catalog = fixtureCatalog();
const fixture = (slug: string) => catalog.bySlug.get(slug)!;

/** A copy of a fixture under another slug; installOnly: every guide's run at level install. */
function like(base: string, slug: string, installOnly = false): Entry {
  const entry = fixture(base);
  if (!installOnly) return { ...entry, slug, name: slug };
  const install = Object.fromEntries(
    Object.entries(entry.install).map(([os, guide]) => [os, { ...guide!, run: { ...guide!.run, level: 'install' } } as InstallGuide]),
  );
  return { ...entry, slug, name: slug, install, verification: { ...entry.verification, level: 'install' } };
}

const JSON_TERMS = { terms: rulesTerms('query json files from the terminal'), scorer: 'rules' as const };

// --- P2-01: the shortlist ------------------------------------------------------------------------------------------

test('the level a tool reached is its strongest passed check; install and a launch are not beyond install', () => {
  assert.equal(verifiedLevel(fixture('fixture-llm-runner')), 'service');
  assert.equal(verifiedLevel(fixture('fixture-json-query')), 'function');
  assert.equal(verifiedLevel(fixture('fixture-chat-tui')), 'install'); // a GUI launch stays install
  assert.equal(beyondInstall(fixture('fixture-web-sketch')), true); // an operation pickfit checked in the browser
  assert.equal(beyondInstall(fixture('fixture-chat-tui')), false);
  assert.equal(beyondInstall(like('fixture-json-query', 'x', true)), false);
});

test('install-level tools are held back while enough tools pickfit saw work fit the request', () => {
  const entries = [like('fixture-json-query', 'deep-a'), like('fixture-json-query', 'deep-b'), like('fixture-json-query', 'shallow', true)];
  assert.equal(MIN_BEYOND_INSTALL, 2);
  const out = hardFilter(entries, {}, JSON_TERMS);
  assert.deepEqual(out.candidates.map((e) => e.slug), ['deep-a', 'deep-b']);
  assert.equal(out.installFallback, false);
  assert.equal(out.heldBack, 1);
  assert.equal(out.passed, 2);
});

test('with too few tools pickfit saw work, the install-level ones that fit come in as a fallback', () => {
  const entries = [like('fixture-json-query', 'deep-a'), like('fixture-json-query', 'shallow', true), like('fixture-transcribe', 'off-topic', true)];
  const out = hardFilter(entries, {}, JSON_TERMS);
  // The install-level tool that fits the request comes in; one that does not is still held back.
  assert.deepEqual(out.candidates.map((e) => e.slug), ['deep-a', 'shallow']);
  assert.equal(out.installFallback, true);
  assert.equal(out.heldBack, 1);
});

test('a weak match pickfit saw work does not hold back a much closer install-level one', () => {
  // The transcriber barely mentions the request; the install-level JSON tool is the real fit.
  const entries = [like('fixture-transcribe', 'deep-a'), like('fixture-llm-runner', 'deep-b'), like('fixture-json-query', 'shallow', true)];
  const out = hardFilter(entries, {}, JSON_TERMS);
  assert.ok(out.candidates.some((e) => e.slug === 'shallow'), out.candidates.map((e) => e.slug).join());
  assert.equal(out.installFallback, true);
});

test('with no word to judge fit by, nothing is held back and the model and labels do the rest', () => {
  const entries = [like('fixture-json-query', 'deep-a'), like('fixture-json-query', 'deep-b'), like('fixture-json-query', 'shallow', true)];
  const out = hardFilter(entries, {});
  assert.equal(out.candidates.length, 3);
  assert.equal(out.installFallback, true);
  assert.equal(out.heldBack, 0);
});

test('rules: among equal fits a tool pickfit saw work goes first; an install-level pick says so first', async () => {
  const entries = [like('fixture-json-query', 'a-shallow', true), like('fixture-json-query', 'b-deep')];
  const scores = new Map(entries.map((e) => [e.slug, 1]));
  assert.deepEqual(rankByRules(entries, scores).map((e) => e.slug), ['b-deep', 'a-shallow']);

  const h = harness(null, { modelEnabled: false });
  const out = await findSoftware({ need: 'chat with a local language model', os: 'linux' }, h.deps);
  await h.settle();
  const chat = out.picks.find((p) => p.slug === 'fixture-chat-tui');
  assert.ok(chat, out.picks.map((p) => p.slug).join());
  assert.equal(chat.tradeoffs[0], INSTALL_ONLY_NOTE);
  assert.equal(chat.reuse, null); // rules cannot tell how to use it
  for (const p of out.picks.filter((p) => p !== chat)) assert.ok(!p.tradeoffs.includes(INSTALL_ONLY_NOTE), p.slug);
});

test('a model that already said it was only installed is not repeated; the cards show the check levels', async () => {
  assert.ok(saysInstallOnly('pickfit only confirmed it installs; its core features were not verified'));
  assert.ok(saysInstallOnly('pickfit 只確認裝得起來（尚未驗證核心功能）'));
  assert.ok(!saysInstallOnly('Needs 8 GB of RAM'));
  const said = 'pickfit only checked that it installs; its core features are not verified.';
  const h = harness(() =>
    modelResponse(
      answer({
        picks: [
          {
            slug: 'fixture-chat-tui',
            fit: 'A terminal chat front end for a local model.',
            reasons: [{ claim: 'Free to use', field: 'pricing', value: 'free' }],
            tradeoffs: [said],
            vs_well_known: null,
          },
        ],
      }),
    ),
  );
  const out = await findSoftware({ need: 'chat with a local language model', os: 'linux' }, h.deps);
  assert.equal(out.matched_by, MATCH_MODEL);
  assert.deepEqual(out.picks[0].tradeoffs, [said]);
  assert.match(String(toCard(fixture('fixture-chat-tui'), 'linux').verified_on), /install check passed/);
});

test('the prompt asks for tools pickfit saw work first, and for the install-only trade-off', () => {
  assert.match(MATCH_INSTRUCTIONS, /prefer a tool pickfit saw work \(a verified_on entry with a function, service or inference check\) over one with only an install check/);
  assert.match(MATCH_INSTRUCTIONS, /the first trade-off must say that pickfit only confirmed it installs and its core features have not been verified yet/);
});

// --- P2-02: agent-first MCP, reuse and build_it_yourself ----------------------------------------------------------

test('the MCP instructions tell an agent to check before it builds', () => {
  assert.match(BEFORE_BUILDING, /^Before writing a new tool, script or integration for the user, call find_software with the job\./);
  assert.ok(INSTRUCTIONS.includes(BEFORE_BUILDING) && READONLY_INSTRUCTIONS.includes(BEFORE_BUILDING));
});

test('the answer schema has reuse per pick and build_it_yourself, each nullable, and the prompt says when', () => {
  const schema = matchSchema('find') as any;
  const pick = schema.properties.picks.items;
  assert.deepEqual(pick.properties.reuse, { anyOf: [{ type: 'string', enum: ['use_directly', 'extend', 'reference'] }, { type: 'null' }] });
  assert.deepEqual(pick.properties.reuse_note, { anyOf: [{ type: 'string' }, { type: 'null' }] });
  assert.ok(pick.required.includes('reuse') && pick.required.includes('reuse_note'));
  assert.deepEqual(schema.properties.build_it_yourself, { anyOf: [{ type: 'string' }, { type: 'null' }] });
  assert.ok(schema.required.includes('build_it_yourself'));
  assert.match(MATCH_INSTRUCTIONS, /13\. reuse: /);
  assert.match(MATCH_INSTRUCTIONS, /14\. build_it_yourself: when the job is a small one-off tool that stores no data and depends on no outside service/);
  assert.match(MATCH_INSTRUCTIONS, /Leave it null when no_install_option is set/);
});

test('reuse: only a known mode, and a note only beside one, in plain words the card does not contradict', () => {
  const card = toCard(fixture('fixture-llm-runner'), 'macos');
  assert.deepEqual(guardReuse(card, { reuse: 'extend', reuse_note: 'Add the missing part as a client of its OpenAI-compatible API.' }), {
    reuse: 'extend',
    reuse_note: 'Add the missing part as a client of its OpenAI-compatible API.',
  });
  assert.deepEqual(guardReuse(card, { reuse: 'fork_it' as any, reuse_note: 'x' }), { reuse: null, reuse_note: null });
  assert.deepEqual(guardReuse(card, { reuse: null, reuse_note: 'A note with no mode.' }), { reuse: null, reuse_note: null });
  for (const bad of ['See https://example.com/plugins.', 'Run npm install fixture-plugin first.', 'Verified by pickfit to be extensible.', 'Runs only on Windows.']) {
    assert.deepEqual(guardReuse(card, { reuse: 'use_directly', reuse_note: bad }), { reuse: 'use_directly', reuse_note: null }, bad);
  }
});

test('build_it_yourself and no_install_option get the same strict checks: no link, command, code or claim of a check', () => {
  const fine = 'A short script that renames the files once is simpler than a new tool; watch for names that already exist.';
  assert.equal(guardAdvice(fine), fine);
  assert.equal(guardNoInstall, guardAdvice);
  for (const bad of [
    'Use rename.example.com instead.',
    'Run brew install rename.',
    'Write python3 rename.py over the folder.',
    'Use python3 -m json.tool, it is enough.',
    'Pipe it through sort && uniq.',
    'Put the script in /usr/local/bin and run it.',
    'Pass --dry-run first.',
    'A tested approach: write it yourself.',
    'pickfit says writing it is simpler.',
    'A script `mv a b` is enough.',
    'none',
    'x'.repeat(301),
  ]) {
    assert.equal(guardAdvice(bad), null, bad);
  }
  // Something the person already has beats writing code: build_it_yourself is left out beside it.
  assert.equal(guardBuildItYourself(fine, 'macOS Finder can rename a batch of files.'), null);
  assert.equal(guardBuildItYourself(fine, null), fine);
});

test('find_software carries reuse and build_it_yourself, with similar tools\' pitfalls and checked features', async () => {
  const h = harness(() =>
    modelResponse(
      answer({
        picks: [
          {
            slug: 'fixture-llm-runner',
            fit: 'Shows how a small local model server is put together.',
            reasons: [{ claim: 'Runs offline on your machine', field: 'processing', value: 'local' }],
            tradeoffs: [],
            vs_well_known: null,
            reuse: 'reference',
            reuse_note: 'Read how it serves its API before writing your own small one.',
          },
        ],
        build_it_yourself: 'A one-off script that calls the model once is simpler than a server; keep the prompt and output format fixed.',
      }),
    ),
  );
  const out = await findSoftware({ need: 'run a small language model offline once from a script', os: 'linux', must_run_locally: true }, h.deps);
  await h.settle();
  assert.equal(out.matched_by, MATCH_MODEL);
  const [runner] = out.picks;
  assert.equal(runner.reuse, 'reference');
  assert.equal(runner.reuse_note, 'Read how it serves its API before writing your own small one.');
  assert.ok(out.build_it_yourself);
  assert.match(out.build_it_yourself.advice, /^A one-off script/);
  const similar = out.build_it_yourself.similar;
  assert.equal(similar[0].slug, 'fixture-llm-runner'); // picks first
  assert.ok(similar.length <= 2);
  assert.match(similar[0].pitfalls[0], /^README says make install; actually needed the install script/);
  assert.ok(similar[0].tested_features.includes('serve an OpenAI-compatible API'));

  const text = findSummary(out);
  assert.match(text, /Reuse: use it as a reference and write your own: Read how it serves its API/);
  assert.match(text, /Build it yourself \(not checked by pickfit\): A one-off script/);
  assert.match(text, /Similar: .*\(fixture-llm-runner\): worth testing: serve an OpenAI-compatible API.*pitfalls: README says make install/);
});

test('a build_it_yourself beside a no_install_option, or one with a command, is left out; older answers still parse', async () => {
  for (const extra of [
    { no_install_option: 'Your OS already ships a tool that does this.', build_it_yourself: 'A short script is simpler.' },
    { build_it_yourself: 'Run pip install llm and call it once.' },
    {},
  ]) {
    const h = harness(() => modelResponse(answer(extra)));
    const out = await findSoftware({ need: 'chat with a language model offline on my laptop', os: 'macos', must_run_locally: true }, h.deps);
    assert.equal(out.matched_by, MATCH_MODEL);
    assert.equal(out.build_it_yourself, null, JSON.stringify(extra));
    assert.ok(out.picks.every((p) => p.reuse === null && p.reuse_note === null));
  }
});
