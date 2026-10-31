/**
 * Feature coverage in find_software picks and get_install_guide: a feature is shown as checked
 * only when a passing smoke test of the run behind the guide covers it; the rest come with why.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { toCard } from '../src/cards.ts';
import { bestGuide, loadCatalog, type Catalog } from '../src/catalog.ts';
import { featuresOut } from '../src/features.ts';
import { findSoftware } from '../src/find.ts';
import { installGuide } from '../src/install.ts';
import { fixtureCatalog, fixtureIndex, harness } from './helpers.ts';

const catalog = fixtureCatalog();

test('get_install_guide lists checked features with their check, and the rest with reasons', () => {
  const out = installGuide(catalog, { slug: 'fixture-transcribe', os: 'linux' });
  assert.equal(out.features.recorded, true);
  assert.deepEqual(out.features.checked, [
    { feature: 'transcribe audio files offline', check: 'fixture-transcribe sample.wav' },
  ]);
  assert.deepEqual(
    out.features.not_checked.map((f) => [f.feature, f.reason]),
    [
      ['write SRT subtitles', 'test_failed'],
      ['dictate from a microphone', 'needs_hardware'],
    ],
  );
  assert.match(out.features.not_checked[0].detail, /tool's own error.*: error: unknown format 'srt'$/);
  assert.match(out.features.not_checked[1].detail, /microphone.*: the sandbox has no microphone$/);
  assert.match(out.how_we_know, /The run exercised 1 of the 3 main features its README advertises; see features/);
});

test('a failure the sandbox explains is said to be the sandbox', () => {
  const out = installGuide(catalog, { slug: 'fixture-llm-runner', os: 'linux' });
  const pull = out.features.not_checked.find((f) => f.feature === 'pull models from a registry')!;
  assert.equal(pull.reason, 'test_failed_in_sandbox');
  assert.match(pull.detail, /sandbox's limits explain .*\(needs an outside service.*\): the registry was unreachable offline/);
});

test('a run from before feature checks says so instead of claiming anything', () => {
  const out = installGuide(catalog, { slug: 'fixture-llm-runner', os: 'macos', arch: 'arm64' });
  assert.equal(out.features.recorded, false);
  assert.deepEqual(out.features.checked, []);
  assert.deepEqual(
    out.features.not_checked.map((f) => [f.feature, f.reason]),
    [
      ['serve an OpenAI-compatible API', 'not_recorded'],
      ['pull models from a registry', 'not_recorded'],
    ],
  );
  assert.doesNotMatch(out.how_we_know, /main features/);
});

test('the index status alone never makes a feature checked: a passing check must back it', () => {
  const data = structuredClone(fixtureIndex()) as any;
  const guide = data.entries.find((e: any) => e.slug === 'fixture-transcribe').install.linux;
  guide.features[0].checks[0].passed = false; // says checked, but its test did not pass
  guide.features[2] = { ...guide.features[2], status: 'checked', reason: null, checks: [] };
  const tampered: Catalog = loadCatalog(data);
  const entry = tampered.bySlug.get('fixture-transcribe')!;
  const out = featuresOut(entry, bestGuide(entry, 'linux'));
  assert.deepEqual(out.checked, []);
  assert.deepEqual(
    out.not_checked.map((f) => [f.feature, f.reason]),
    [
      ['transcribe audio files offline', 'other'],
      ['write SRT subtitles', 'test_failed'],
      ['dictate from a microphone', 'other'],
    ],
  );
});

test('an older index without features still answers', () => {
  const data = structuredClone(fixtureIndex()) as any;
  for (const entry of data.entries) {
    delete entry.features;
    for (const guide of Object.values(entry.install) as any[]) delete guide.features;
  }
  const out = installGuide(loadCatalog(data), { slug: 'fixture-transcribe', os: 'linux' });
  assert.deepEqual(out.features, { recorded: false, checked: [], not_checked: [] });
});

test('find_software picks carry the features of the guide they show, and cards let the model cite them', async () => {
  const h = harness(null, { modelEnabled: false });
  const out = await findSoftware({ need: 'transcribe a recording to text offline', os: 'linux' }, h.deps);
  await h.settle();
  const transcribe = out.picks.find((p) => p.slug === 'fixture-transcribe')!;
  assert.deepEqual(transcribe.features.checked.map((f) => f.feature), ['transcribe audio files offline']);
  assert.equal(transcribe.features.not_checked.length, 2);
  assert.match(transcribe.how_we_know, /exercised 1 of the 3 main features/);
  const card = toCard(catalog.bySlug.get('fixture-transcribe')!, 'linux');
  assert.deepEqual(card.features_checked, ['transcribe audio files offline']);
  assert.deepEqual(card.features_not_checked, ['write SRT subtitles (test_failed)', 'dictate from a microphone (needs_hardware)']);
});
