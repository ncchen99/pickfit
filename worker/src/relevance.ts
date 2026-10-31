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
import { GENERIC_WORDS, NEGATION_LISTS, NEGATION_STOPS, NEGATIONS, NOT_NEGATIONS, ZH_EN } from './lexicon.ts';

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

/** A negation's scope takes at most this many words ("without sending my code to the cloud": sending, code, cloud). */
const NEGATED_WORDS = 4;
const EN_NEGATIONS = NEGATIONS.en.map((phrase) => phrase.split(' ')).sort((a, b) => b.length - a.length);
const ZH_NEGATION_SET = new Set(NEGATIONS.zh);
const STOPS = { zh: new Set(NEGATION_STOPS.zh), en: new Set(NEGATION_STOPS.en) };
const LISTS = new Set(NEGATION_LISTS);
/** Chinese tokens, longest first: dictionary words and the words negation scopes are made of. */
const ZH_TOKENS = [...new Set([...ZH_KEYS, ...NEGATIONS.zh, ...NOT_NEGATIONS, ...NEGATION_STOPS.zh, ...NEGATION_LISTS])]
  .filter((k) => k.charCodeAt(0) >= 0x2e80)
  .sort((a, b) => b.length - a.length);
const CLAUSE_END = /[,.;:!?()[\]{}"“”‘’，。；：！？（）「」『』【】\n—–-]/;
const EN_WORD = /[A-Za-z0-9](?:[\w+#'’-]|\.(?=[A-Za-z0-9]))*/y;

interface Token {
  start: number;
  end: number;
  /** Lowercase English word, a Chinese token, or one punctuation character. */
  text: string;
  kind: 'en' | 'zh' | 'punct';
}

function tokenize(text: string): Token[] {
  const out: Token[] = [];
  for (let i = 0; i < text.length; ) {
    const ch = text[i];
    if (/\s/.test(ch)) {
      i++;
    } else if (/[A-Za-z0-9]/.test(ch)) {
      EN_WORD.lastIndex = i;
      const word = EN_WORD.exec(text)![0];
      out.push({ start: i, end: i + word.length, text: word.toLowerCase().replace(/’/g, "'"), kind: 'en' });
      i += word.length;
    } else if (ch.charCodeAt(0) >= 0x2e80 && !CLAUSE_END.test(ch)) {
      const key = ZH_TOKENS.find((k) => text.startsWith(k, i)) ?? ch;
      out.push({ start: i, end: i + key.length, text: key, kind: 'zh' });
      i += key.length;
    } else {
      out.push({ start: i, end: i + 1, text: ch, kind: 'punct' });
      i++;
    }
  }
  return out;
}

/** How many tokens a negation spans at tokens[i] ("不需要", "do not need"), or 0. */
function negationAt(tokens: Token[], i: number): number {
  if (tokens[i].kind === 'zh') return ZH_NEGATION_SET.has(tokens[i].text) ? 1 : 0;
  const phrase = EN_NEGATIONS.find((words) => words.every((w, k) => tokens[i + k]?.kind === 'en' && tokens[i + k].text === w));
  return phrase?.length ?? 0;
}

/** One or two Chinese characters outside the dictionary (or 用, 使用) right before the negated object, an English or dictionary word: how many, or 0. */
function verbBefore(tokens: Token[], i: number): number {
  let j = i;
  while (j < i + 2 && tokens[j]?.kind === 'zh' && (tokens[j].text === '用' || tokens[j].text === '使用' || (!(tokens[j].text in ZH_EN) && tokens[j].text.length === 1 && !STOPS.zh.has(tokens[j].text) && !LISTS.has(tokens[j].text)))) j++;
  const next = tokens[j];
  const object = next?.kind === 'en' ? !STOPS.en.has(next.text) : next?.kind === 'zh' && next.text in ZH_EN && !STOPS.zh.has(next.text);
  return j > i && object ? j - i : 0;
}

/**
 * The text with what a negation rules out blanked, in Chinese and English
 * alike ("不需要 GPU", "without a cloud account"): what follows is a
 * constraint, not the job. The scope is one item, extended by a list ("GPU 和
 * Docker", "an account or API key", "GPU/CUDA"): English words, or one Chinese
 * dictionary word, optionally followed by English words (its object: "免安裝
 * Docker"). It ends at punctuation, a stop (a contrast, a new positive verb,
 * 的; see NEGATION_STOPS), a Chinese word after English ones ("不需要 GPU 轉錄"
 * transcribes), any other character, or NEGATED_WORDS words.
 */
export function dropNegated(text: string): string {
  const tokens = tokenize(text);
  const blanked: Token[] = [];
  let scope: { item: 'none' | 'zh' | 'en'; words: number; gerund: boolean } | null = null;
  for (let i = 0; i < tokens.length; i++) {
    const cue = negationAt(tokens, i);
    if (cue) {
      blanked.push(...tokens.slice(i, i + cue));
      scope = { item: 'none', words: 0, gerund: false };
      i += cue - 1;
      continue;
    }
    if (!scope) continue;
    const t = tokens[i];
    if (LISTS.has(t.text)) {
      blanked.push(t);
      scope.item = 'none';
      continue;
    }
    // A short verb before the object belongs to the negation ("不想裝 Python", "不需要用到 GPU", "不用把檔案上傳").
    const verb = verbBefore(tokens, i);
    if (scope.words === 0 && scope.item === 'none' && verb) {
      blanked.push(...tokens.slice(i, i + verb));
      i += verb - 1;
      continue;
    }
    const english = t.kind === 'en' && !(STOPS.en.has(t.text) && !(t.text === 'to' && scope.gerund));
    const chinese = t.kind === 'zh' && t.text in ZH_EN && !STOPS.zh.has(t.text) && scope.item === 'none';
    if (!(english || chinese) || scope.words >= NEGATED_WORDS) {
      scope = null;
      continue;
    }
    blanked.push(t);
    if (chinese || !STOPWORDS.has(t.text)) {
      if (english && scope.words === 0) scope.gerund = t.text.endsWith('ing');
      scope.words++;
    }
    scope.item = english ? 'en' : 'zh';
  }
  let out = '';
  let last = 0;
  for (const t of blanked) {
    out += text.slice(last, t.start) + ' '.repeat(t.end - t.start);
    last = t.end;
  }
  return out + text.slice(last);
}

/** English words for the Chinese words in a text: at each position the longest dictionary word wins; negated words are left out. */
export const zhToEnglish = (text: string): string => zhWords(text).join(' ');

/** The dictionary's English for each Chinese word in a text, one string per word (its synonyms together), less negated words unless `negate` is false. */
export function zhWords(text: string, negate = true): string[] {
  const plain = negate ? dropNegated(text) : text;
  const out: string[] = [];
  for (let i = 0; i < plain.length; ) {
    const key = plain.charCodeAt(i) >= 0x2e80 ? ZH_KEYS.find((k) => plain.startsWith(k, i)) : undefined;
    if (key) out.push(ZH_EN[key]);
    i += key?.length ?? 1;
  }
  return out;
}

/** The request's terms for rulesRelevance: its own English words and the dictionary's English for its Chinese ones, less negated words. */
export const rulesTerms = (...texts: string[]) => queryTerms(...texts.map(dropNegated), ...texts.map(zhToEnglish));

/** The same, with negated words kept as said: find_alternatives' pain points, where "no dark mode" names what is wanted. */
export const termsAsSaid = (...texts: string[]) => queryTerms(...texts, ...texts.map((t) => zhWords(t, false).join(' ')));

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
