/**
 * What the matcher reads of a card (promptCard): the card's own values, less what says nothing. The guard still
 * holds reasons to the whole card, so a reason copied from the prompt's card holds.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CARD_FIELDS, promptCard, STANDING_FIELDS, toCard } from '../src/cards.ts';
import type { Entry } from '../src/catalog.ts';
import { reasonHolds } from '../src/guard.ts';
import { matchInput } from '../src/prompt.ts';
import { fixtureCatalog } from './helpers.ts';

const catalog = fixtureCatalog();

test('the prompt leaves out empty, unknown and default values and popularity, and keeps a meaningful false', () => {
  for (const entry of catalog.entries) {
    const card = toCard(entry, 'linux');
    const sent = promptCard(card);
    for (const [key, value] of Object.entries(sent)) {
      assert.notEqual(value, null, `${entry.slug}.${key}`);
      assert.ok(!(Array.isArray(value) && value.length === 0), `${entry.slug}.${key}`);
      assert.deepEqual(value, card[key as keyof typeof card], `${entry.slug}.${key} is the card's own value`);
    }
    assert.equal('popularity' in sent, false);
    if (card.apple_silicon_only === false) assert.equal('apple_silicon_only' in sent, false);
    if (card.open_source === false) assert.equal(sent.open_source, false);
    if (card.verified_on_user_os === false) assert.equal(sent.verified_on_user_os, false);
    assert.ok(JSON.stringify(sent).length < JSON.stringify(card).length);
  }
});

test('the request carries the prompt cards, and a reason copied from one holds against the whole card', () => {
  const entry = catalog.bySlug.get('fixture-transcribe')!;
  const card = toCard(entry, 'linux');
  const text = matchInput({ need: 'transcribe audio' }, [card]);
  const line = text.split('\n').find((l) => l.startsWith('{"slug"'))!;
  assert.deepEqual(JSON.parse(line), promptCard(card));
  const verified = (card.verified_on as string[])[0];
  assert.match(verified, /^linux x86_64: \w+ check passed \d{4}-\d{2}-\d{2}, (sandbox, replayed|by hand)$/);
  assert.equal(reasonHolds(card, { claim: 'Checked on Linux', field: 'verified_on', value: verified }), true);
});

test('a feature not checked says why only when the reason is about the tool', () => {
  const card = toCard(catalog.bySlug.get('fixture-transcribe')!, 'linux');
  for (const item of card.features_not_checked as string[]) {
    assert.doesNotMatch(item, /\((not_attempted|beyond_budget|not_recorded|other)\)$/);
  }
});

test('brief 15 fields: on the card only when the record has them, with days counted in code', () => {
  const base = catalog.bySlug.get('fixture-json-query')!;
  const now = new Date('2026-11-22T12:00:00Z');
  // A record not yet assessed, read without a clock: the card is what it was.
  const plain = toCard(base, 'linux');
  for (const field of STANDING_FIELDS) assert.equal(field in plain, false, field);
  // With the request's clock: whole days since checked_at, and nothing else added.
  const days = Math.floor((now.getTime() - Date.parse(base.verification.checked_at!)) / 86_400_000);
  const timed = toCard(base, 'linux', undefined, [], now);
  assert.equal(timed.verified_days_ago, days);
  for (const field of ['track', 'used_by', 'standing']) assert.equal(field in timed, false, field);
  // last_passed_at wins over checked_at.
  const assessed: Entry = {
    ...base,
    track: 'A',
    used_by: 'agent',
    standing: 'new',
    verification: { ...base.verification, last_passed_at: '2026-11-19T00:00:00Z' },
  };
  const card = toCard(assessed, 'linux', undefined, [], now);
  assert.deepEqual([card.track, card.used_by, card.standing, card.verified_days_ago], ['A', 'agent', 'new', 3]);
  const sent = promptCard(card);
  assert.deepEqual([sent.track, sent.used_by, sent.standing, sent.verified_days_ago], ['A', 'agent', 'new', 3]);
  for (const field of STANDING_FIELDS) assert.ok((CARD_FIELDS as readonly string[]).includes(field), field);
  assert.equal(reasonHolds(card, { claim: 'Made for agents', field: 'used_by', value: 'agent' }), true);
  // Verified today is 0, and a 0 still reaches the prompt.
  const today = toCard(
    { ...assessed, verification: { ...assessed.verification, last_passed_at: now.toISOString() } },
    'linux', undefined, [], now,
  );
  assert.equal(promptCard(today).verified_days_ago, 0);
});
