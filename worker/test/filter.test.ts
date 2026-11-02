import assert from 'node:assert/strict';
import { test } from 'node:test';
import { toCard } from '../src/cards.ts';
import { hardFilter, MAX_CARDS, type Conditions } from '../src/filter.ts';
import { contradiction, reasonHolds, valueMatches } from '../src/guard.ts';
import { templateReasons } from '../src/rules.ts';
import { fixtureCatalog } from './helpers.ts';

const catalog = fixtureCatalog();
const slugs = (cond: Conditions) => hardFilter(catalog.entries, cond).candidates.map((e) => e.slug);

test('hard filters: Mac, free, offline', () => {
  assert.deepEqual(slugs({ os: 'macos', budget: 'free_only', must_run_locally: true }), [
    'fixture-chat-tui',
    'fixture-json-query',
    'fixture-llm-runner',
    'fixture-transcribe',
    'fixture-web-sketch', // a PWA checked offline, nothing typed left the device
  ]);
});

test('hard filters: category, OS claims and exclusions', () => {
  assert.deepEqual(slugs({ category: 'local_ai', os: 'macos' }), [
    'fixture-chat-tui',
    'fixture-llm-runner',
    'fixture-transcribe',
  ]);
  assert.deepEqual(slugs({ os: 'windows' }), ['fixture-chat-tui', 'fixture-cloud-summarize', 'fixture-json-query', 'fixture-web-sketch']);
  assert.deepEqual(slugs({ os: 'linux', exclude: ['fixture-json-query'] }).length, 6);
  assert.deepEqual(slugs({ budget: 'free_or_paid' }).length, 7);
  assert.deepEqual(slugs({ category: 'mcp_server' }), ['fixture-notes-mcp']);
  assert.deepEqual(slugs({ category: 'mcp_server', os: 'macos' }), []); // claims and runs are Linux only
});

test('must_run_locally rejects cloud processing, required network and API keys', () => {
  assert.ok(!slugs({ must_run_locally: true }).includes('fixture-cloud-summarize'));
});

test('above MAX_CARDS the highest treasure values are kept, still in slug order', () => {
  const base = catalog.entries.find((e) => e.slug === 'fixture-json-query')!;
  const many = Array.from({ length: MAX_CARDS + 10 }, (_, i) => ({
    ...base,
    slug: `bulk-${String(i).padStart(3, '0')}`,
    scores: { ...base.scores!, treasure_value: i },
  }));
  const { candidates, passed } = hardFilter(many, {});
  assert.equal(passed, MAX_CARDS + 10);
  assert.equal(candidates.length, MAX_CARDS);
  assert.equal(candidates[0].slug, 'bulk-010');
  assert.deepEqual(
    candidates.map((e) => e.slug),
    [...candidates.map((e) => e.slug)].sort(),
  );
});

test('cards carry what the guard checks, with verification on the user OS spelled out', () => {
  const runner = toCard(catalog.bySlug.get('fixture-llm-runner')!, 'macos');
  assert.equal(runner.verified_on_user_os, true);
  assert.equal(runner.install_method_user_os, 'brew');
  assert.deepEqual(runner.verified_on, [
    'macos arm64: installed by hand, function check passed, 2026-10-28',
    'linux x86_64: sandbox install, replayed from scratch, service check passed, 2026-10-28',
  ]);
  const transcribe = toCard(catalog.bySlug.get('fixture-transcribe')!, 'macos');
  assert.equal(transcribe.verified_on_user_os, false);
  assert.equal(transcribe.install_method_user_os, null);
});

test('valueMatches: exact values, list items and quoted parts of text', () => {
  assert.ok(valueMatches('local', 'Local'));
  assert.ok(valueMatches(['json', 'cli'], 'cli'));
  assert.ok(valueMatches('Runs small language models offline', 'language models'));
  assert.ok(valueMatches(84, '84'));
  assert.ok(valueMatches(true, 'true'));
  assert.ok(!valueMatches('local', 'cloud'));
  assert.ok(!valueMatches(['json'], 'js')); // too short to count as a quote
  assert.ok(!valueMatches(null, 'anything'));
});

test('contradiction: claims the card does not support', () => {
  const cloud = toCard(catalog.bySlug.get('fixture-cloud-summarize')!, 'linux');
  assert.match(contradiction(cloud, 'Works fully offline') ?? '', /locally/);
  assert.match(contradiction(cloud, 'Completely free') ?? '', /free/);
  assert.equal(contradiction(cloud, 'Has a free tier'), null);
  assert.match(contradiction(cloud, 'Open-source CLI') ?? '', /open source/);
  assert.match(contradiction(cloud, 'Needs no API key') ?? '', /key/);
  const transcribe = toCard(catalog.bySlug.get('fixture-transcribe')!, 'macos');
  assert.match(contradiction(transcribe, 'Tested on macOS') ?? '', /verified on macos/);
  assert.equal(contradiction(transcribe, 'Supports macOS and Linux'), null);
  assert.match(contradiction(transcribe, 'Runs on Windows') ?? '', /windows support/);
});

test('template reasons from rules always pass the guard', () => {
  for (const entry of catalog.entries) {
    for (const os of ['macos', 'linux', 'windows', undefined] as const) {
      const card = toCard(entry, os);
      const reasons = templateReasons(entry, card, os);
      assert.ok(reasons.length > 0, entry.slug);
      for (const reason of reasons) assert.ok(reasonHolds(card, reason), `${entry.slug} ${os}: ${reason.claim}`);
    }
  }
});
