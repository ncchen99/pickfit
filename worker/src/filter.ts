/** Step B of find_software: hard conditions, applied by code before any model sees a card. */
import { isWebApp, nameKey, verifiedOn, webCheck, type Arch, type Entry, type OS } from './catalog.ts';
import { relevance, rulesRelevance } from './relevance.ts';

export interface Conditions {
  category?: 'dev_cli' | 'local_ai' | 'mcp_server' | 'any';
  os?: OS;
  arch?: Arch;
  budget?: 'free_only' | 'free_or_paid';
  /** Both of the two below. */
  must_run_locally?: boolean;
  /** Must work without internet. */
  offline?: boolean;
  /** What the user enters must not leave the machine. */
  data_stays_local?: boolean;
  exclude?: string[];
}

export const needsOffline = (cond: Conditions) => cond.must_run_locally === true || cond.offline === true;
export const needsLocalData = (cond: Conditions) => cond.must_run_locally === true || cond.data_stays_local === true;

/** Hard filters never relax; MAX_CARDS bounds what one model call reads (architecture F.2 C). */
export const MAX_CARDS = 60;

export function runsLocally(entry: Entry): boolean {
  const { network, api_keys } = entry.prerequisites;
  return entry.processing === 'local' && network !== 'required' && api_keys.length === 0;
}

/**
 * A web app opens in any browser, so the OS does not filter it. It qualifies for offline use only as a PWA that
 * pickfit reloaded with the network off, and for data that must stay local only when pickfit saw nothing it typed
 * in leave the device (unknown does not qualify).
 */
function webFits(entry: Entry, cond: Conditions): boolean {
  const check = webCheck(entry);
  if (!check) return false; // only sites a browser run passed on
  if (needsOffline(cond) && check.offline !== 'verified') return false;
  if (needsLocalData(cond) && check.data_sent !== 'none') return false;
  return true;
}

function fits(entry: Entry, cond: Conditions): boolean {
  if (cond.exclude?.includes(entry.slug)) return false;
  if (cond.category && cond.category !== 'any' && entry.category !== cond.category) return false;
  if (cond.budget === 'free_only' && entry.pricing !== 'free') return false;
  if (isWebApp(entry)) return webFits(entry, cond);
  const verified = verifiedOn(entry);
  if (verified.length === 0) return false; // only tools whose install steps were actually run
  if ((needsOffline(cond) || needsLocalData(cond)) && !runsLocally(entry)) return false;
  if (cond.os && !entry.platforms.includes(cond.os) && !verified.includes(cond.os)) return false;
  if (entry.prerequisites.apple_silicon_only) {
    if (cond.os && cond.os !== 'macos') return false;
    if (cond.arch === 'x86_64') return false;
  }
  return true;
}

/** Shortlist slots kept for the highest treasure values, so good general picks are not lost to keyword matches. */
export const TREASURE_SLOTS = 10;

/** What the shortlist ranks by: request terms (relevance.ts) and, for find_alternatives, the current tool. */
export interface Query {
  terms: string[];
  current?: string;
  /** "bm25" (default): with Meta's keywords, for the model. "rules": no keywords (rules only, or the call failed). */
  scorer?: 'bm25' | 'rules';
}

export interface Filtered {
  candidates: Entry[];
  /** How many passed the hard filters before MAX_CARDS. */
  passed: number;
  /** Shortlist slots filled by fit to the request rather than treasure value; 0 when all passed or nothing matched. */
  byRelevance: number;
  /** The scorer's relevance of every entry that passed. */
  relevance: Map<string, number>;
}

const treasure = (entry: Entry) => entry.scores?.treasure_value ?? -1;

/** Profiles whose alternatives_to names the user's current tool. */
export function replacesCurrent(entry: Entry, current: string | undefined): boolean {
  const key = current ? nameKey(current) : '';
  return key !== '' && entry.alternatives_to.some((alt) => nameKey(alt) === key);
}

/**
 * Entries that meet every hard condition, in slug order (no popularity order
 * for the model to lean on). A tool that claims the user's OS but was verified
 * only elsewhere stays in; its card and the response say so.
 * Above MAX_CARDS the shortlist is relevance first: tools that name the current
 * tool (find_alternatives), then the best BM25 matches, up to
 * MAX_CARDS - TREASURE_SLOTS; the rest are the highest treasure values. A
 * request with no matching words gets the treasure order alone.
 */
/** Every entry that meets the hard conditions, in catalog order. */
export const passing = (entries: Entry[], cond: Conditions) => entries.filter((entry) => fits(entry, cond));

export function hardFilter(entries: Entry[], cond: Conditions, query: Query = { terms: [] }): Filtered {
  const passed = passing(entries, cond);
  const scores = (query.scorer === 'rules' ? rulesRelevance : relevance)(entries, passed, query.terms);
  if (passed.length <= MAX_CARDS) return { candidates: passed, passed: passed.length, byRelevance: 0, relevance: scores };
  const fit = passed
    .map((entry) => ({ entry, replaces: replacesCurrent(entry, query.current), score: scores.get(entry.slug)! }))
    .filter((item) => item.replaces || item.score > 0)
    .sort(
      (a, b) =>
        Number(b.replaces) - Number(a.replaces) ||
        b.score - a.score ||
        treasure(b.entry) - treasure(a.entry) ||
        a.entry.slug.localeCompare(b.entry.slug),
    )
    .slice(0, MAX_CARDS - TREASURE_SLOTS)
    .map((item) => item.entry);
  const chosen = new Set(fit);
  const rest = passed
    .filter((entry) => !chosen.has(entry))
    .sort((a, b) => treasure(b) - treasure(a) || a.slug.localeCompare(b.slug))
    .slice(0, MAX_CARDS - fit.length);
  const candidates = [...fit, ...rest].sort((a, b) => a.slug.localeCompare(b.slug));
  return { candidates, passed: passed.length, byRelevance: fit.length, relevance: scores };
}
