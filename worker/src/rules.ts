/**
 * The fallback when the model is off, over budget or fails: rank by rules
 * and explain with template reasons built only from card fields.
 * Order: (find_alternatives only) the profile names the current tool in
 * alternatives_to, then relevance to the request (rulesRelevance,
 * relevance.ts), then, for equal relevance, verification on the user's OS,
 * then treasure value (quality high, popularity low).
 */
import type { Entry, OS } from './catalog.ts';
import type { Card } from './cards.ts';
import type { ModelReason } from './prompt.ts';
import { replacesCurrent, runsLocally } from './filter.ts';

/** Scores this close count as equal, so OS verification and treasure decide. */
const SAME_SCORE = 1e-6;

/** relevance: rulesRelevance of each entry against the request, 0 or absent for no match. */
export function rankByRules(entries: Entry[], relevance: Map<string, number>, os?: OS, current?: string): Entry[] {
  return entries
    .map((entry) => ({
      entry,
      replaces: replacesCurrent(entry, current),
      score: relevance.get(entry.slug) ?? 0,
      onOs: os !== undefined && entry.install[os] !== undefined,
      treasure: entry.scores?.treasure_value ?? -1,
    }))
    .sort(
      (a, b) =>
        Number(b.replaces) - Number(a.replaces) ||
        (Math.abs(b.score - a.score) > SAME_SCORE ? b.score - a.score : 0) ||
        Number(b.onOs) - Number(a.onOs) ||
        b.treasure - a.treasure ||
        a.entry.slug.localeCompare(b.entry.slug),
    )
    .map((item) => item.entry);
}

/** True statements read straight off the card; at least one per tool. */
export function templateReasons(entry: Entry, card: Card, os?: OS): ModelReason[] {
  const reasons: ModelReason[] = [];
  const verified = card.verified_on as string[];
  const onUserOs = os ? verified.find((label) => label.startsWith(`${os} `)) : undefined;
  if (onUserOs) {
    reasons.push({ claim: `Install steps were run and checked on ${os}`, field: 'verified_on', value: onUserOs });
  } else if (verified.length) {
    reasons.push({ claim: 'Install steps were run and checked by pickfit', field: 'verified_on', value: verified[0] });
  }
  if (entry.use_cases.length) {
    reasons.push({ claim: `Use case: ${entry.use_cases[0]}`, field: 'use_cases', value: entry.use_cases[0] });
  }
  if (runsLocally(entry)) {
    reasons.push({ claim: 'Runs on your machine without a cloud service', field: 'processing', value: 'local' });
  }
  if (entry.pricing === 'free') reasons.push({ claim: 'Free to use', field: 'pricing', value: 'free' });
  return reasons.slice(0, 4);
}
