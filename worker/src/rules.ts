/**
 * The fallback when the model is off, over budget or fails: rank by rules
 * and explain with template reasons built only from card fields.
 * Order: (find_alternatives only) the profile names the current tool in
 * alternatives_to, then relevance to the request (rulesRelevance,
 * relevance.ts), then, for equal relevance, verification on the user's OS,
 * then treasure value (quality high, popularity low). A web app goes ahead of
 * tools to install whose relevance is within WEB_BAND of its own (no install,
 * just open it), unless the request leans to installed tools (leansInstall),
 * when those go ahead of web apps within the same band.
 */
import { isWebApp, webCheck, type Entry, type OS } from './catalog.ts';
import type { Card } from './cards.ts';
import type { ModelReason } from './prompt.ts';
import { replacesCurrent, runsLocally } from './filter.ts';

/** Scores this close count as equal, so OS verification and treasure decide. */
const SAME_SCORE = 1e-6;

/** A web app and a tool to install this close in relevance (share of the larger score) fit about equally. */
export const WEB_BAND = 0.1;

/** Long-running or background work, system integration, many local files, or a terminal tool: installed tools fit better. */
const INSTALL_LEAN =
  /\b(background|daemon|always[- ]on|long[- ]running|overnight|at (startup|login|boot)|cron|scheduled?|system[- ]wide|hot ?keys?|global shortcuts?|menu ?bar|system tray|clipboard|file ?system|folders?|director(y|ies)|batch|bulk|many files|thousands of|terminal|shell|cli|command[- ]line|scripts?|pipelines?)\b/i;

export const leansInstall = (text: string) => INSTALL_LEAN.test(text);

interface Ranked {
  entry: Entry;
  replaces: boolean;
  score: number;
}

const aboutEqual = (a: number, b: number) => Math.abs(a - b) <= Math.max(SAME_SCORE, WEB_BAND * Math.max(a, b));

/** Moves each preferred entry up past the others above it that fit about equally (and name the current tool alike). */
function aheadWhenEqual<T extends Ranked>(ranked: T[], preferred: (entry: Entry) => boolean): T[] {
  const out: T[] = [];
  for (const item of ranked) {
    let at = out.length;
    if (preferred(item.entry)) {
      while (at > 0) {
        const above = out[at - 1];
        if (preferred(above.entry) || above.replaces !== item.replaces || !aboutEqual(above.score, item.score)) break;
        at--;
      }
    }
    out.splice(at, 0, item);
  }
  return out;
}

/** relevance: rulesRelevance of each entry against the request, 0 or absent for no match. */
export function rankByRules(entries: Entry[], relevance: Map<string, number>, os?: OS, current?: string, leanInstall = false): Entry[] {
  const ranked = entries
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
    );
  return aheadWhenEqual(ranked, (entry) => isWebApp(entry) !== leanInstall).map((item) => item.entry);
}

/** True statements read straight off the card; at least one per tool. */
export function templateReasons(entry: Entry, card: Card, os?: OS): ModelReason[] {
  const reasons: ModelReason[] = [];
  const verified = card.verified_on as string[];
  const web = webCheck(entry);
  if (isWebApp(entry) && web) {
    reasons.push({ claim: 'No install: it opens in a browser', field: 'no_install', value: 'true' });
    if (verified.length) reasons.push({ claim: 'pickfit opened it in a browser and checked it', field: 'verified_on', value: verified[0] });
    if (entry.use_cases.length) reasons.push({ claim: `Use case: ${entry.use_cases[0]}`, field: 'use_cases', value: entry.use_cases[0] });
    if (web.offline === 'verified') reasons.push({ claim: 'Works offline once loaded (checked)', field: 'works_offline', value: 'verified' });
    if (web.data_sent === 'none') reasons.push({ claim: 'What you type stayed on your device in pickfit’s check', field: 'data_sent', value: 'none' });
    if (entry.pricing === 'free') reasons.push({ claim: 'Free to use', field: 'pricing', value: 'free' });
    return reasons.slice(0, 4);
  }
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
