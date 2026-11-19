/**
 * What the matcher reads of a card (promptCard): the card's own values, less what says nothing. The guard still
 * holds reasons to the whole card, so a reason copied from the prompt's card holds.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { promptCard, toCard } from '../src/cards.ts';
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
