/**
 * Rules only (MATCH_MODE off, or the model failed): does a ranked tool do
 * the job, judging only by its profile? The request's specific words (not
 * generic words, filler, constraints, OS names or the kind of tool; words the
 * catalog knows, or names of products) are checked against the tool's
 * capability fields: name, summary, use cases, tags and MCP tool names. A
 * Chinese word counts once, whichever of its dictionary synonyms the profile uses.
 *
 * - good: the profile names every product the request names, and mentions
 *   most of the specific words (more than GOOD_SHARE) and at least MIN_WORDS
 *   of them. A request with one specific word is good only when that word is a
 *   product the profile names directly; one shared ordinary word is weak evidence;
 * - partial: it mentions at least one named product (when the request names
 *   any) and at least PARTIAL_SHARE of the specific words: MIN_WORDS of them,
 *   or one when that is half the request or more;
 * - weak: otherwise.
 *
 * Labels only: rules answers list the same tools in the same order either way;
 * the labels say how well each listed profile covers the request.
 *
 * A profile names a product directly unless it mentions it only as what it
 * replaces ("jira-alternative", "an alternative to Notion"); such a mention
 * counts only for a request that asks for an alternative to that product.
 * Every word counts the same: weighting by rarity let quality words such as
 * "natural" outweigh the job. Each pick can say which of the request's words
 * its profile covers and which it does not. No model call.
 */
import { OSES, type Entry } from './catalog.ts';
import { EN_PHRASES, GENERIC_WORDS, NOT_THE_JOB_WORDS, ZH_PHRASES } from './lexicon.ts';
import { dropNegated, relevanceIndex, terms, zhWords } from './relevance.ts';

export type FitQuality = 'good' | 'partial' | 'weak';
/** A whole rules answer: its best pick's label, or none when no pick reaches partial. */
export type MatchQuality = 'good' | 'partial' | 'none';

export interface Fit {
  quality: FitQuality;
  /** The request's words the profile mentions, as the request put them. */
  covers: string[];
  /** The request's words it does not mention. */
  missing: string[];
}

export const GOOD_SHARE = 1 / 2;
export const PARTIAL_SHARE = 1 / 3;
export const MIN_WORDS = 2;

const OS_WORDS = ['mac', 'macos', 'osx', 'linux', 'ubuntu', 'windows'];
const SKIP = new Set([...GENERIC_WORDS, ...OS_WORDS, ...NOT_THE_JOB_WORDS].flatMap(terms));
/** "an MCP server" is the kind of tool, which the category settles. */
const KIND = /\bmcp\s+servers?\b/gi;
/** OS names are conditions, removed as whole words ("macOS" is not a product called "OS"). */
const OS_NAMES = /\b(?:mac\s?os(?:\s?x)?|macbook(?:\s(?:pro|air))?|mac|osx|linux|ubuntu|windows|wsl)\b/gi;
const PHRASES = [
  ...Object.entries(EN_PHRASES).map(([phrase, word]) => [new RegExp(`\\b${phrase}\\b`, 'gi'), word] as const),
  ...Object.entries(ZH_PHRASES).map(([phrase, word]) => [new RegExp(phrase, 'g'), word] as const),
];
/** Whole words that are never the job, removed before splitting ("ChatGPT" would split into chat + gpt). */
const NOT_THE_JOB = new RegExp(`\\b(?:${NOT_THE_JOB_WORDS.join('|')})\\b`, 'gi');
/** "an alternative to Jira", "instead of Postman", "類似 Notion": a product to replace, not to work with. */
const REFERENCE = /\b(?:[Aa]lternatives?\s+(?:to|for)|[Ii]nstead\s+of|[Ss]imilar\s+to|[Rr]eplacements?\s+for)\s+(?:(?:my|the|a|an)\s+)?([A-Z][\w.+-]*)|(?:類似|取代|替代|像是|像)\s*([A-Za-z][\w.+-]*)/g;
/** How a profile mentions a product it replaces: "jira-alternative", "an alternative to Notion". */
const ALTERNATIVE = /\b([\w.+]+)[- ]alternatives?\b|\b(?:alternatives?\s+(?:to|for)|instead\s+of|similar\s+to|replacements?\s+for)\s+([\w.+-]+)/gi;
const CJK = /[⺀-鿿豈-﫿]/;
/** "secret-project-xyz": a label for the person's own thing, not the job ("text-to-speech" is kept). */
const LABEL = /\b(?![a-z0-9]+(?:-[a-z0-9]+)*-to-)[a-z0-9]+(?:-[a-z0-9]+){2,}\b/g;

export interface Job {
  /** Specific words of the request, each as its terms (a Chinese word's synonyms are one word). */
  words: string[][];
  /** Each term once, in the request's order. */
  terms: string[];
  /** Terms of the products it names (Notion, PostgreSQL, GitHub). */
  named: Set<string>;
  /** Terms of the products it asks to replace ("an alternative to Jira"); also in named. */
  reference: Set<string>;
  /** term -> the word the request used for it. */
  said: Map<string, string>;
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
  let plain = text.replace(KIND, ' ').replace(OS_NAMES, ' ').replace(LABEL, ' ');
  const reference = new Set(
    [...plain.matchAll(REFERENCE)].map((m) => m[1] ?? m[2]).filter((w) => !NOT_THE_JOB_WORDS.includes(w.toLowerCase())).flatMap(terms).filter((t) => !SKIP.has(t)),
  );
  plain = dropNegated(plain);
  for (const [pattern, word] of PHRASES) plain = plain.replace(pattern, ` ${word} `);
  plain = plain.replace(NOT_THE_JOB, ' ');
  const index = relevanceIndex(corpus);
  // "my Node project", "Python code": where the job happens, an ordinary word rather than a product to work with.
  const context = new Set([...plain.matchAll(/\b([A-Z][\w.+-]*)\s+(?:projects?|codebases?|apps?|code|scripts?)\b/g)].flatMap((m) => terms(m[1])));
  const names = new Set([...namedWords(plain).flatMap(terms).filter((t) => !SKIP.has(t) && !context.has(t)), ...reference]);
  // An English term is one word; a Chinese word's synonyms are one word, and words sharing a term are merged.
  const candidate: string[][] = [];
  for (const group of [...terms(plain).map((t) => [t]), ...zhWords(plain).map(terms)]) {
    const g = [...new Set(group.filter((t) => !SKIP.has(t) && !/^\d+$/.test(t)))];
    const same = candidate.find((c) => c.some((t) => g.includes(t)));
    if (same) same.push(...g.filter((t) => !same.includes(t)));
    else if (g.length) candidate.push(g);
  }
  const said = new Map<string, string>();
  for (const word of [...(plain.match(/[A-Za-z][\w+#.-]*/g) ?? []), ...zhWords(plain).join(' ').split(' ')]) {
    for (const term of terms(word)) if (!said.has(term)) said.set(term, word.toLowerCase().replace(/\.+$/, ''));
  }
  // A word counts when the catalog knows it or it names a product; other words (asides, labels) do not.
  const known = (t: string) => index.df.has(t) || names.has(t);
  const words = candidate.map((g) => g.filter(known)).filter((g) => g.length);
  const unknown = candidate.filter((g) => !g.some(known)).map((g) => said.get(g[0]) ?? g[0]);
  const all = words.flat();
  return { words, terms: all, named: new Set(all.filter((t) => names.has(t))), reference, said, unknown };
}

interface Profile {
  /** Terms of what the profile says the tool does (not why_worth_it or alternatives_to). */
  does: Set<string>;
  /** The same, less products it mentions only as what it replaces. */
  direct: Set<string>;
  /** Terms of the products it replaces. */
  replaces: Set<string>;
}

const profiles = new WeakMap<Entry, Profile>();

function profileOf(entry: Entry): Profile {
  let profile = profiles.get(entry);
  if (!profile) {
    const mcpTools = OSES.flatMap((os) => entry.install[os]?.mcp?.tools ?? []);
    const texts = [entry.name, entry.slug, entry.summary, ...entry.use_cases, ...entry.tags, ...mcpTools];
    const replaced = texts.flatMap((t) => [...t.matchAll(ALTERNATIVE)].map((m) => m[1] ?? m[2]));
    profile = {
      does: new Set(texts.flatMap(terms)),
      direct: new Set(texts.map((t) => t.replace(ALTERNATIVE, ' ')).flatMap(terms)),
      replaces: new Set([...entry.alternatives_to, ...replaced].flatMap(terms)),
    };
    profiles.set(entry, profile);
  }
  return profile;
}

export function fitOf(entry: Entry, job: Job): Fit {
  const profile = profileOf(entry);
  const has = (t: string) =>
    job.reference.has(t) ? profile.replaces.has(t) : job.named.has(t) ? profile.direct.has(t) : profile.does.has(t);
  const said = (words: string[][]) => [...new Set(words.map((w) => job.said.get(w[0]) ?? w[0]))];
  const covered = job.words.filter((w) => w.some(has));
  const missing = job.words.filter((w) => !w.some(has));
  // A word split in two ("real-time") that is half covered is listed as covered.
  const fit = (quality: FitQuality): Fit => ({ quality, covers: said(covered), missing: said(missing).filter((w) => !said(covered).includes(w)) });
  if (job.words.length === 0) {
    // Only words no profile uses: nothing in the catalog speaks of this job.
    if (job.unknown.length) return { quality: 'weak', covers: [], missing: job.unknown };
    // Nothing specific asked beyond the kind of tool, which the hard filters already settled.
    return fit('good');
  }
  const share = covered.length / job.words.length;
  const named = [...job.named];
  const namedCovered = named.filter(has).length;
  // One specific word: good only when it names a product (to work with, or to replace) and the profile does too.
  const enough = job.words.length === 1 ? named.length > 0 : covered.length >= MIN_WORDS;
  // Most of the words, not half: on the dev queries, picks covering exactly half held up far less often.
  if (namedCovered === named.length && share > GOOD_SHARE && enough) return fit('good');
  const some = covered.length >= MIN_WORDS || share >= GOOD_SHARE;
  if (some && (named.length === 0 || namedCovered > 0) && share >= PARTIAL_SHARE) return fit('partial');
  return fit('weak');
}

/** One sentence on what a partial or weak pick does and does not cover, from its profile; none for a good one. */
export function fitNote(fit: Fit): string | null {
  const list = (words: string[]) => words.slice(0, 5).join(', ');
  if (fit.quality === 'partial') return `Covers part of the request: its profile mentions ${list(fit.covers)} but not ${list(fit.missing)}.`;
  if (fit.quality === 'weak') {
    return fit.covers.length
      ? `Weak match: its profile mentions ${list(fit.covers)} but not ${list(fit.missing)}.`
      : `Weak match: its profile mentions none of ${list(fit.missing)}.`;
  }
  return null;
}
