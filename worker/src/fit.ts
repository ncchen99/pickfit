/**
 * Rules only (MATCH_MODE off, or the model failed): does a ranked tool do
 * the job, judging only by its profile? The request's specific words (not
 * generic words, filler, constraints or the kind of tool; words the catalog
 * knows, or names of products) are checked against the tool's capability
 * fields: name, summary, use cases, tags and MCP tool names.
 *
 * - good: the profile mentions every product the request names and at least
 *   GOOD_SHARE of its specific words;
 * - partial: it mentions at least one named product (when the request names
 *   any), at least PARTIAL_SHARE of the specific words, and at least
 *   PARTIAL_MIN_WORDS of them (one shared word is weak evidence);
 * - none: otherwise. A request answered only by "none" tools gets no picks.
 *
 * Every word counts the same: weighting by rarity let quality words such as
 * "natural" outweigh the job. Each pick can say which of the request's words
 * its profile covers and which it does not. No model call.
 */
import { OSES, type Entry } from './catalog.ts';
import { EN_PHRASES, GENERIC_WORDS, NOT_THE_JOB_WORDS } from './lexicon.ts';
import { relevanceIndex, rulesTerms, terms, zhToEnglish } from './relevance.ts';

export type FitQuality = 'good' | 'partial' | 'none';

export interface Fit {
  quality: FitQuality;
  /** The request's words the profile mentions, as the request put them. */
  covers: string[];
  /** The request's words it does not mention. */
  missing: string[];
}

export const GOOD_SHARE = 1 / 2;
export const PARTIAL_SHARE = 1 / 3;
export const PARTIAL_MIN_WORDS = 2;

const OS_WORDS = ['mac', 'macos', 'osx', 'linux', 'ubuntu', 'windows'];
const SKIP = new Set([...GENERIC_WORDS, ...OS_WORDS, ...NOT_THE_JOB_WORDS].flatMap(terms));
/** "an MCP server" is the kind of tool, which the category settles. */
const KIND = /\bmcp\s+servers?\b/gi;
const PHRASES = Object.entries(EN_PHRASES).map(([phrase, word]) => [new RegExp(`\\b${phrase}\\b`, 'gi'), word] as const);
/** Whole words that are never the job, removed before splitting ("ChatGPT" would split into chat + gpt). */
const NOT_THE_JOB = new RegExp(`\\b(?:${NOT_THE_JOB_WORDS.join('|')})\\b`, 'gi');
/** "without API keys", "no cloud upload": up to two words after a negation name a constraint. */
const NEGATED = /\b(without|no)\s+(?:(?:a|an|the|any|my|to|being|having)\s+)*[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*)?/gi;
const CJK = /[\u2e80-\u9fff\uf900-\ufaff]/;
/** "secret-project-xyz": a label for the person's own thing, not the job ("text-to-speech" is kept). */
const LABEL = /\b(?![a-z0-9]+(?:-[a-z0-9]+)*-to-)[a-z0-9]+(?:-[a-z0-9]+){2,}\b/g;

export interface Job {
  /** Specific terms of the request, each once. */
  terms: string[];
  /** Terms of the products it names (Notion, PostgreSQL, GitHub). */
  named: Set<string>;
  /** term -> the word the request used for it. */
  words: Map<string, string>;
  /** Specific words no profile in the catalog uses; ignored, unless they are all the request asks. */
  unknown: string[];
}

/**
 * Names of products and services: mixed case anywhere (GitHub, PostgreSQL,
 * LoRA), capitalized words inside an English sentence (Notion), capitalized
 * Latin words in Chinese text. Plain acronyms (PDF, JSON, CPU) are formats and
 * parts of the job, not names, so they count like any other word.
 */
function namedWords(text: string): string[] {
  const out: string[] = [];
  for (const sentence of text.split(/[.!?。！？\n]+/)) {
    const chinese = CJK.test(sentence);
    const words = sentence.match(/[A-Za-z][A-Za-z0-9+#.-]*/g) ?? [];
    words.forEach((word, i) => {
      if (/^[A-Z0-9+#.-]+s?$/.test(word)) return; // an acronym
      const mixed = /[a-z][A-Z]/.test(word) || /[A-Z]{2,}[a-z]/.test(word);
      const capital = /^[A-Z]/.test(word) && (i > 0 || chinese);
      if (mixed || capital) out.push(word);
    });
  }
  return out;
}

export function jobOf(corpus: readonly Entry[], text: string): Job {
  let plain = text.replace(KIND, ' ').replace(LABEL, ' ').replace(NEGATED, '$1 ').replace(NOT_THE_JOB, ' ');
  for (const [pattern, word] of PHRASES) plain = plain.replace(pattern, ` ${word} `);
  const index = relevanceIndex(corpus);
  const names = new Set(namedWords(plain).flatMap(terms).filter((t) => !SKIP.has(t)));
  // A word counts when the catalog knows it or it names a product; other words (asides, labels) do not.
  const candidate = rulesTerms(plain).filter((t) => !SKIP.has(t) && !/^\d+$/.test(t));
  const all = candidate.filter((t) => index.df.has(t) || names.has(t));
  const unknown = candidate.filter((t) => !all.includes(t));
  const named = new Set(all.filter((t) => names.has(t)));
  const words = new Map<string, string>();
  for (const word of [...(plain.match(/[A-Za-z][\w+#.-]*/g) ?? []), ...zhToEnglish(plain).split(' ')]) {
    for (const term of terms(word)) if (!words.has(term)) words.set(term, word.toLowerCase());
  }
  return { terms: all, named, words, unknown: unknown.map((t) => words.get(t) ?? t) };
}

const capabilities = new WeakMap<Entry, Set<string>>();

/** Terms of what the profile says the tool does (not why_worth_it or alternatives_to). */
function capabilityTerms(entry: Entry): Set<string> {
  let set = capabilities.get(entry);
  if (!set) {
    const mcpTools = OSES.flatMap((os) => entry.install[os]?.mcp?.tools ?? []);
    set = new Set([entry.name, entry.slug, entry.summary, ...entry.use_cases, ...entry.tags, ...mcpTools].flatMap(terms));
    capabilities.set(entry, set);
  }
  return set;
}

export function fitOf(entry: Entry, job: Job): Fit {
  const has = capabilityTerms(entry);
  const said = (ts: string[]) => [...new Set(ts.map((t) => job.words.get(t) ?? t))];
  const covered = job.terms.filter((t) => has.has(t));
  const missing = job.terms.filter((t) => !has.has(t));
  const fit = (quality: FitQuality): Fit => ({ quality, covers: said(covered), missing: said(missing) });
  if (job.terms.length === 0) {
    // Only words no profile uses: nothing in the catalog speaks of this job.
    if (job.unknown.length) return { quality: 'none', covers: [], missing: job.unknown };
    // Nothing specific asked beyond the kind of tool, which the hard filters already settled.
    return fit('good');
  }
  const share = covered.length / job.terms.length;
  const namedCovered = [...job.named].filter((t) => has.has(t)).length;
  const enough = covered.length >= Math.min(PARTIAL_MIN_WORDS, job.terms.length);
  if (namedCovered === job.named.size && share >= GOOD_SHARE) return fit('good');
  if (enough && (job.named.size === 0 || namedCovered > 0) && share >= PARTIAL_SHARE) return fit('partial');
  return fit('none');
}

/** One sentence on what a partial match does and does not cover, from its profile. */
export function partialNote(fit: Fit): string {
  const list = (words: string[]) => words.slice(0, 5).join(', ');
  return `Covers part of the request: its profile mentions ${list(fit.covers)} but not ${list(fit.missing)}.`;
}
