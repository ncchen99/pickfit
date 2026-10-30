/**
 * How well a request's words match each profile: BM25 over the card text the
 * matcher reads (name, tags, summary, use cases, alternatives, MCP tool names),
 * with field weights. Used to choose which cards reach the model when more
 * than MAX_CARDS pass the hard filters, and by the rules fallback. Words are
 * English; Meta adds English keywords for the request first (expand.ts).
 */
import { OSES, type Entry } from './catalog.ts';

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
