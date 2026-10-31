/**
 * How well a request's words match each profile: BM25 over the card text the
 * matcher reads (name, tags, summary, use cases, alternatives, MCP tool names),
 * with field weights. Used to choose which cards reach the model when more
 * than MAX_CARDS pass the hard filters, and by the rules fallback. Words are
 * English; Meta adds English keywords for the request first (expand.ts).
 * Without those keywords (rules only, or the keyword call failed) the rules'
 * own scorer, rulesRelevance, ranks instead: it reads Chinese words through a
 * small dictionary, counts generic words for little and favors profiles that
 * match more of what the request asks for.
 */
import { OSES, type Entry } from './catalog.ts';
import { GENERIC_WORDS, ZH_EN } from './lexicon.ts';

const STOPWORDS = new Set(
  (
    'a about after all also am an and any app apps are as at be best but by can could do does doesn either ' +
    'every for from get good has have help how i if in into is it its just let like ll lot make me more ' +
    'most much my need needs no not now of on one only or other our out over really run runs should ' +
    'so some something such than that the their them then there these they thing things this those to ' +
    'too tool tools up us use used uses using ve very want wants way we what when where which while who ' +
    'why will with without work works would you your'
  ).split(' '),
);

/** A light stemmer: plurals, -ing/-ed/-ly and a final e, so "converting", "converts" and "convert" agree. */
function stem(word: string): string {
  let w = word;
  if (w.length > 4 && w.endsWith('ies')) w = `${w.slice(0, -3)}y`;
  else if (w.length > 3 && w.endsWith('s') && !/(ss|us|is)$/.test(w)) w = w.slice(0, -1);
  if (w.length > 6 && w.endsWith('ly')) w = w.slice(0, -2);
  else if (w.length > 5 && w.endsWith('ing')) w = w.slice(0, -3);
  else if (w.length > 4 && w.endsWith('ed')) w = w.slice(0, -2);
  if (w.length > 3 && /([b-df-hj-np-tv-z])\1$/.test(w) && !/(ll|ss|zz)$/.test(w)) w = w.slice(0, -1);
  if (w.length > 3 && w.endsWith('e')) w = w.slice(0, -1);
  return w;
}

/** English search terms in a text: camelCase and snake_case split, lowercased, stopwords dropped, stemmed. */
export function terms(text: string): string[] {
  const split = text.replace(/([a-z0-9])([A-Z])/g, '$1 $2').toLowerCase();
  return (split.match(/[a-z0-9]+/g) ?? []).filter((w) => w.length > 1 && !STOPWORDS.has(w)).map(stem);
}

/** Each request term once. */
export const queryTerms = (...texts: string[]) => [...new Set(texts.flatMap(terms))];

/** Handshake tool names from any OS's run (what cards may show). */
function mcpToolNames(entry: Entry): string[] {
  return OSES.flatMap((os) => entry.install[os]?.mcp?.tools ?? []);
}

/** BM25F-style field weights: a word in the name counts three times one in a use case. */
const FIELDS: [number, (entry: Entry) => string[]][] = [
  [3, (e) => [e.name, e.slug]],
  [2, (e) => e.tags],
  [1.5, (e) => [e.summary]],
  [1.5, (e) => e.alternatives_to],
  [1, (e) => e.use_cases],
  [1, (e) => [e.why_worth_it ?? '']],
  [1, (e) => [...new Set(mcpToolNames(e))]],
];
const K1 = 1.2;
const B = 0.75;

interface Doc {
  tf: Map<string, number>;
  length: number;
}

export interface RelevanceIndex {
  docs: Map<string, Doc>;
  df: Map<string, number>;
  avgLength: number;
}

function toDoc(entry: Entry): Doc {
  const tf = new Map<string, number>();
  let length = 0;
  for (const [weight, field] of FIELDS) {
    for (const term of field(entry).flatMap(terms)) {
      tf.set(term, (tf.get(term) ?? 0) + weight);
      length += weight;
    }
  }
  return { tf, length };
}

const indexes = new WeakMap<readonly Entry[], RelevanceIndex>();

/** Built once per catalog (the Worker's entries array lives as long as the isolate). */
export function relevanceIndex(corpus: readonly Entry[]): RelevanceIndex {
  let index = indexes.get(corpus);
  if (!index) {
    const docs = new Map(corpus.map((entry) => [entry.slug, toDoc(entry)]));
    const df = new Map<string, number>();
    let total = 0;
    for (const doc of docs.values()) {
      total += doc.length;
      for (const term of doc.tf.keys()) df.set(term, (df.get(term) ?? 0) + 1);
    }
    index = { docs, df, avgLength: docs.size ? total / docs.size : 0 };
    indexes.set(corpus, index);
  }
  return index;
}

/** BM25 of each entry (scored against the whole corpus's statistics); 0 when no term matches. */
export function relevance(corpus: readonly Entry[], entries: readonly Entry[], query: string[]): Map<string, number> {
  const index = relevanceIndex(corpus);
  const n = index.docs.size;
  const idf = new Map(
    query.map((term) => {
      const df = index.df.get(term) ?? 0;
      return [term, Math.log(1 + (n - df + 0.5) / (df + 0.5))];
    }),
  );
  const scores = new Map<string, number>();
  for (const entry of entries) {
    const doc = index.docs.get(entry.slug) ?? toDoc(entry);
    const norm = K1 * (1 - B + (B * doc.length) / (index.avgLength || 1));
    let score = 0;
    for (const term of query) {
      const tf = doc.tf.get(term);
      if (tf) score += (idf.get(term) ?? 0) * ((tf * (K1 + 1)) / (tf + norm));
    }
    scores.set(entry.slug, score);
  }
  return scores;
}

/** Generic words count this share of their IDF in rulesRelevance. */
export const GENERIC_WEIGHT = 0.2;
/** OS names are hard conditions, not the job, so they count as generic too. */
const OS_WORDS = ['mac', 'macos', 'osx', 'linux', 'ubuntu', 'windows'];
const GENERIC = new Set([...GENERIC_WORDS, ...OS_WORDS].flatMap(terms));
const ZH_KEYS = Object.keys(ZH_EN).sort((a, b) => b.length - a.length);
/** "without internet", "no cloud": the word after names a constraint, not what the tool should do. */
const EN_NEGATED = /\b(without|no)\s+(?:(?:a|an|the|any|my|to|being|having)\s+)*[A-Za-z][\w-]*/gi;
const ZH_NEGATIONS = ['不需要', '不用', '不要', '不必', '無需', '无需', '免'];

/** English words for the Chinese words in a text: at each position the longest dictionary word wins; a negated word is skipped. */
export const zhToEnglish = (text: string): string => zhWords(text).join(' ');

/** The dictionary's English for each Chinese word in a text, one string per word (its synonyms together). */
export function zhWords(text: string): string[] {
  const out: string[] = [];
  let negated = false;
  for (let i = 0; i < text.length; ) {
    if (text.charCodeAt(i) < 0x2e80) {
      if (!/[\w]/.test(text[i])) negated = false;
      i++;
      continue;
    }
    const neg = ZH_NEGATIONS.find((k) => text.startsWith(k, i));
    if (neg) {
      negated = true;
      i += neg.length;
      continue;
    }
    const key = ZH_KEYS.find((k) => text.startsWith(k, i));
    if (key) {
      if (!negated) out.push(ZH_EN[key]);
      negated = false;
      i += key.length;
    } else {
      if ('，。、；！？'.includes(text[i])) negated = false;
      i++;
    }
  }
  return out;
}

/** The request's terms for rulesRelevance: its own English words (less negated ones) and the dictionary's English for its Chinese ones. */
export const rulesTerms = (...texts: string[]) =>
  queryTerms(...texts.map((t) => t.replace(EN_NEGATED, '$1 ')), ...texts.map(zhToEnglish));

/**
 * Relevance without the model: BM25 where a generic word ("tool", "terminal",
 * "file") weighs GENERIC_WEIGHT of its IDF, times the share of the request's
 * weight the profile matches, so a profile that matches the specific words of
 * the request outranks one that repeats a generic word.
 */
export function rulesRelevance(corpus: readonly Entry[], entries: readonly Entry[], query: string[]): Map<string, number> {
  const index = relevanceIndex(corpus);
  const n = index.docs.size;
  const weight = new Map(
    query.map((term) => {
      const df = index.df.get(term) ?? 0;
      const idf = Math.log(1 + (n - df + 0.5) / (df + 0.5));
      return [term, GENERIC.has(term) ? GENERIC_WEIGHT * idf : idf];
    }),
  );
  const total = [...weight.values()].reduce((a, b) => a + b, 0);
  const scores = new Map<string, number>();
  for (const entry of entries) {
    const doc = index.docs.get(entry.slug) ?? toDoc(entry);
    const norm = K1 * (1 - B + (B * doc.length) / (index.avgLength || 1));
    let score = 0;
    let matched = 0;
    for (const [term, w] of weight) {
      const tf = doc.tf.get(term);
      if (!tf) continue;
      score += w * ((tf * (K1 + 1)) / (tf + norm));
      matched += w;
    }
    scores.set(entry.slug, total > 0 ? score * (matched / total) : 0);
  }
  return scores;
}
