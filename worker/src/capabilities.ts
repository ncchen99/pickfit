/**
 * Documented capabilities (docs/proposals/capabilities.md step 5): what a tool's own docs say it can do
 * beyond its main features. They are for matching only, never checked one by one, so a card shows just
 * the few that the request's words name (capabilities_matched), and a pick that rests on one says the
 * docs claim it, not that pickfit saw it work.
 */
import type { Entry } from './catalog.ts';
import { GENERIC_WORDS } from './lexicon.ts';
import { terms } from './relevance.ts';

/** At most this many on a card: 60 cards each listing 40 would cost more than the rest of the card. */
export const CAPABILITIES_SHOWN = 5;

const GENERIC = new Set(GENERIC_WORDS.flatMap(terms));

/** A capability's words that say something specific (not "file", "tool", "support"). */
const specific = (text: string) => terms(text).filter((t) => !GENERIC.has(t));

/**
 * The capabilities the request's terms name, best first, each as the card shows it: the label, and the
 * listed items the request named ("convert documents between formats (epub)"). A label counts when one
 * of its specific words is a request term; an item counts when all of its words are.
 */
export function matchedCapabilities(entry: Entry, query: readonly string[]): string[] {
  const asked = new Set(query);
  const scored = (entry.capabilities ?? []).flatMap((c, order) => {
    const labelHits = new Set(specific(c.label).filter((t) => asked.has(t))).size;
    const items = (c.items ?? []).filter((item) => {
      const words = terms(item);
      return words.length > 0 && words.every((t) => asked.has(t));
    });
    if (labelHits === 0 && items.length === 0) return [];
    const shown = items.length ? `${c.label} (${items.join(', ')})` : c.label;
    return [{ shown, score: labelHits + 2 * items.length, order }];
  });
  return scored
    .sort((a, b) => b.score - a.score || a.order - b.order)
    .slice(0, CAPABILITIES_SHOWN)
    .map((c) => c.shown);
}
