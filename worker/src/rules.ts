/**
 * The fallback when the model is off, over budget or fails: rank by rules
 * and explain with template reasons built only from card fields.
 * Order: keyword hits of the request on the profile, then verification on
 * the user's OS, then treasure value (quality high, popularity low).
 */
import type { Entry, OS } from './catalog.ts';
import type { Card } from './cards.ts';
import type { ModelReason } from './prompt.ts';
import { runsLocally } from './filter.ts';

const STOPWORDS = new Set(
  'a an and any app are best but can for from get have help how its like need not offline free mac macos linux windows on one only or run runs that the this tool tools use want which with without work works'.split(
    ' ',
  ),
);

function words(text: string): string[] {
  return (text.toLowerCase().match(/[a-z0-9][a-z0-9+.-]{2,}/g) ?? []).filter((w) => !STOPWORDS.has(w));
}

/** How many distinct request words appear in the profile's name, tags, use cases and summary. */
export function keywordHits(entry: Entry, need: string): number {
  const profile = new Set(
    words([entry.name, entry.summary, entry.why_worth_it ?? '', ...entry.tags, ...entry.use_cases, ...entry.alternatives_to].join(' ')),
  );
  return new Set(words(need).filter((w) => profile.has(w))).size;
}

export function rankByRules(entries: Entry[], need: string, os?: OS): Entry[] {
  return entries
    .map((entry) => ({
      entry,
      hits: keywordHits(entry, need),
      onOs: os !== undefined && entry.install[os] !== undefined,
      treasure: entry.scores?.treasure_value ?? -1,
    }))
    .sort(
      (a, b) =>
        b.hits - a.hits ||
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
