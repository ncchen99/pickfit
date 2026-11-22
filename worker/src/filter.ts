/** Step B of find_software: hard conditions, applied by code before any model sees a card. */
import { isWebApp, nameKey, verifiedOn, webCheck, type Arch, type Entry, type NamedCategory, type OS } from './catalog.ts';
import { relevance, rulesRelevance } from './relevance.ts';

export interface Conditions {
  category?: NamedCategory | 'any';
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

/** Hard filters never relax; MAX_CARDS bounds what one model call reads (architecture F.2 C). 50 since 11/20: on
 * worker/bench (128 capability queries, 65 controls, the fit-fresh dev shortlist) it lost one query of 128 and one or
 * two of 89 labeled tools against 60, for a sixth fewer cards; 40 lost three to five queries and three to five tools. */
export const MAX_CARDS = 50;

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
  // A re-verification failed (brief 15.4): kept in the catalog and on its tool page, never recommended.
  if (entry.standing === 'broken') return false;
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

/** Levels at which pickfit saw the tool do its job, not only install (brief 15.6, P2-01): strongest first. */
export const BEYOND_INSTALL = ['inference', 'service', 'function'] as const;
const LEVELS = [...BEYOND_INSTALL, 'install'];

/** The strongest level pickfit's passed checks reached: any OS's install guide, or a web app's browser run. */
export function verifiedLevel(entry: Entry): string {
  const levels = [
    ...verifiedOn(entry).map((os) => entry.install[os]!.run.level),
    ...(webCheck(entry) ? [webCheck(entry)!.level] : []),
  ];
  const best = levels.sort((a, b) => LEVELS.indexOf(a) - LEVELS.indexOf(b))[0];
  return best ?? entry.verification.level;
}

/** pickfit saw it work (function, service or inference), not only install or open. */
export const beyondInstall = (entry: Entry) => (BEYOND_INSTALL as readonly string[]).includes(verifiedLevel(entry));

/**
 * Recommend strictly (brief 15.6, P2-01): only tools pickfit saw work go to the shortlist. Install-level tools come in
 * as a fallback only when fewer than this many tools pickfit saw work fit the request; each one that does is
 * labeled "pickfit only confirmed it installs" (rules.ts INSTALL_ONLY_NOTE, prompt rule 6).
 */
export const MIN_BEYOND_INSTALL = 2;

/** Shortlist slots kept for the highest treasure values, so good general picks are not lost to keyword matches. 3 since
 * 11/20: with fewer cards, ten such slots pushed out more fitting tools than they let in (bench, as for MAX_CARDS). */
export const TREASURE_SLOTS = 3;

/** What the shortlist ranks by: request terms (relevance.ts) and, for find_alternatives, the current tool. */
export interface Query {
  terms: string[];
  current?: string;
  /** "bm25" (default): with the model's keywords, for the match call. "rules": no keywords (rules only, or the call failed). */
  scorer?: 'bm25' | 'rules';
}

export interface Filtered {
  candidates: Entry[];
  /** How many passed the hard filters before MAX_CARDS. */
  passed: number;
  /** Shortlist slots filled by fit to the request rather than treasure value; 0 when all passed or nothing matched. */
  byRelevance: number;
  /** The scorer's relevance of every entry that met the hard conditions. */
  relevance: Map<string, number>;
  /** Install-level tools are among the candidates: too few tools pickfit saw work fit the request (P2-01). */
  installFallback: boolean;
  /** Install-level tools that met the conditions but were held back for tools pickfit saw work. */
  heldBack: number;
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

/** A tool fits the request about as well as the best match when its relevance is at least this share of the best's. */
export const CLOSE_FIT = 0.5;

/**
 * The tools a request may be recommended (P2-01): those pickfit saw work, unless fewer than MIN_BEYOND_INSTALL of them
 * fit the request about as well as the best match does (names the current tool, or relevance within CLOSE_FIT of the
 * best). Then the install-level tools that fit come in as a fallback: there is no better choice among the tools pickfit
 * saw work. With no word matching any tool (no words, or none in the profiles' language) code cannot tell which tools
 * fit, so none is held back: the model prefers the tools pickfit saw work (prompt rule 3) and every install-level pick
 * says what pickfit checked (rule 6, find.ts).
 */
function strictPool(met: Entry[], scores: Map<string, number>, current: string | undefined): { pool: Entry[]; installFallback: boolean } {
  const score = (entry: Entry) => scores.get(entry.slug) ?? 0;
  const best = Math.max(0, ...met.map(score));
  const deep = met.filter(beyondInstall);
  if (best === 0 && !met.some((entry) => replacesCurrent(entry, current))) {
    return { pool: met, installFallback: deep.length < met.length };
  }
  const fitsRequest = (entry: Entry) => replacesCurrent(entry, current) || (score(entry) > 0 && score(entry) >= CLOSE_FIT * best);
  if (deep.filter(fitsRequest).length >= MIN_BEYOND_INSTALL || deep.length === met.length) return { pool: deep, installFallback: false };
  const pool = met.filter((entry) => beyondInstall(entry) || fitsRequest(entry));
  return { pool, installFallback: pool.length > deep.length };
}

export function hardFilter(entries: Entry[], cond: Conditions, query: Query = { terms: [] }): Filtered {
  const met = passing(entries, cond);
  const scores = (query.scorer === 'rules' ? rulesRelevance : relevance)(entries, met, query.terms);
  const { pool: passed, installFallback } = strictPool(met, scores, query.current);
  const strict = { installFallback, heldBack: met.length - passed.length };
  if (passed.length <= MAX_CARDS) return { candidates: passed, passed: passed.length, byRelevance: 0, relevance: scores, ...strict };
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
  return { candidates, passed: passed.length, byRelevance: fit.length, relevance: scores, ...strict };
}
