/**
 * Secondary-capability recall: requests for a job a tool's README documents but
 * its record does not list (scripts/capability_queries.py). Is the tool found?
 * Never reads eval/.
 *
 * Per query and language, without a model:
 *   card     the target's card for this request (what the matcher may cite, capabilities_matched included)
 *            has one of the key terms
 *   short    the target is among the MAX_CARDS cards the rules scorer sends (no keywords)
 *   short+q  the same with the BM25 scorer on the request's own English words, standing
 *            in for the model's keywords (English only)
 *   rules    the target is among the rules-only picks
 * With --model (paid, ANTHROPIC_API_KEY): the product's real path (keyword call when
 * more than MAX_CARDS pass, then the match call) and whether the target is a pick.
 * --model-id names the model for both calls (default claude-opus-5-5, the product's;
 * one with a price in src/meta.ts MODEL_PRICES) and implies --model.
 *
 *   node bench/capability.ts <index.json> <queries.json> [--lang en|zh|both] [--category] [--model] [--model-id ID] [--limit N] [--cap USD] [--out picks.json] [--show]
 *
 * --category passes the target's category, as a client that knows it would;
 * without it the request runs over the whole catalog.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { loadCatalog, type Entry } from '../src/catalog.ts';
import { toCard } from '../src/cards.ts';
import { hardFilter, type Conditions } from '../src/filter.ts';
import { queryTerms, rulesTerms, terms } from '../src/relevance.ts';
import { findSoftware } from '../src/find.ts';
import { harness, makeD1, SETTINGS } from '../test/helpers.ts';
import { modelArg } from './model-arg.ts';

interface Query {
  id: string;
  /** The tool the request is about; null for a request no catalog tool answers (a dev query of class none). */
  slug: string | null;
  category: string;
  capability: string;
  key_terms: string[];
  en: string;
  zh: string;
  /** Only this language (a dev query is asked in the one it was written in); default: those --lang asks for. */
  lang?: 'en' | 'zh';
  /** The request's own conditions (a dev query's category and OS), used instead of --category. */
  conditions?: Conditions;
}

const args = process.argv.slice(2);
const flag = (name: string) => args.includes(name);
const opt = (name: string) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined);
const [indexPath, queriesPath] = args.filter((a, i) => !a.startsWith('--') && !['--lang', '--limit', '--cap', '--out', '--model-id'].includes(args[i - 1]));
const langs = (opt('--lang') ?? 'both') === 'both' ? ['en', 'zh'] : [opt('--lang')!];
const modelId = modelArg(args);
const useModel = flag('--model') || flag('--model-id');
const show = flag('--show');
const capUsd = Number(opt('--cap') ?? 15);

const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));
const all: Query[] = JSON.parse(readFileSync(queriesPath, 'utf8')).queries;
const queries = all.filter((q) => q.slug === null || catalog.bySlug.has(q.slug)).slice(0, opt('--limit') ? Number(opt('--limit')) : undefined);
if (queries.length < all.length) console.error(`${all.length - queries.length} queries name tools not in this index; skipped`);

/** The card text the matcher reads about what the tool does. */
function cardTerms(entry: Entry, query: string[]): Set<string> {
  // The card as the matcher gets it for this request: capabilities_matched holds the documented capabilities its words name.
  const card = toCard(entry, undefined, undefined, query);
  const texts = [card.summary, card.why_worth_it, card.tags, card.use_cases, card.features_checked, card.features_not_checked, card.alternatives_to, card.mcp_tools, card.capabilities_matched]
    .flat()
    .filter((v): v is string => typeof v === 'string');
  return new Set(texts.flatMap(terms));
}

const conditionsFor = (q: Query): Conditions =>
  q.conditions ?? (flag('--category') && q.category !== 'other' ? { category: q.category as Conditions['category'] } : {});

const apiKey = process.env.ANTHROPIC_API_KEY;
if (useModel && !apiKey) throw new Error('ANTHROPIC_API_KEY is not set');
const paid = useModel ? makeD1() : null;
const modelDeps = paid && {
  catalog,
  db: paid.db,
  settings: { ...SETTINGS, apiKey: apiKey!, dailyCapUsd: capUsd, totalCapUsd: capUsd, timeoutMs: 60_000, matchModel: modelId }, // this run's own stop
  now: () => new Date(),
  waitUntil: () => {},
};

type Row = {
  id: string;
  lang: string;
  slug: string | null;
  card: boolean | null;
  short: boolean | null;
  shortQ: boolean | null;
  rules: boolean | null;
  rulesPicks: string[];
  model: boolean | null;
  modelPicks?: string[];
  matchedBy?: string;
};
const rows: Row[] = [];

async function one(q: Query, lang: string): Promise<Row> {
  const entry = q.slug === null ? null : catalog.bySlug.get(q.slug)!;
  const text = lang === 'en' ? q.en : q.zh;
  const cond = conditionsFor(q);
  const have = entry && cardTerms(entry, rulesTerms(text));
  const card = have && q.key_terms.length ? q.key_terms.some((t) => terms(t).length > 0 && terms(t).every((w) => have.has(w))) : null;
  const short = entry ? hardFilter(catalog.entries, cond, { terms: rulesTerms(text), scorer: 'rules' }).candidates.includes(entry) : null;
  const shortQ = entry && lang === 'en' ? hardFilter(catalog.entries, cond, { terms: queryTerms(text) }).candidates.includes(entry) : null;
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = catalog;
  const rulesOut: any = await findSoftware({ need: text, ...cond }, h.deps);
  const rulesPicks: string[] = rulesOut.picks.map((p: any) => p.slug);
  const row: Row = { id: q.id, lang, slug: q.slug, card, short, shortQ, rules: entry ? rulesPicks.includes(q.slug!) : null, rulesPicks, model: null };
  if (modelDeps) {
    const out: any = await findSoftware({ need: text, ...cond }, modelDeps as any);
    row.modelPicks = out.picks.map((p: any) => p.slug);
    row.model = entry ? row.modelPicks!.includes(q.slug!) : null;
    row.matchedBy = out.matched_by;
  }
  return row;
}

const jobs = queries.flatMap((q) => (q.lang ? [q.lang] : langs).map((lang) => [q, lang] as const));
let next = 0;
async function worker() {
  while (next < jobs.length) {
    const [q, lang] = jobs[next++];
    const row = await one(q, lang);
    rows.push(row);
    const mark = (x: boolean | null) => (x === null ? '-' : +x);
    if (show) console.log(`${row.id} ${lang} ${q.slug ?? '(none)'} card=${mark(row.card)} short=${mark(row.short)} short+q=${mark(row.shortQ)} rules=${mark(row.rules)}${row.model === null ? '' : ` model=${+row.model} [${row.modelPicks!.join(',')}] ${row.matchedBy}`} | ${lang === 'en' ? q.en : q.zh}`);
  }
}
await Promise.all(Array.from({ length: useModel ? 4 : 1 }, worker));

const rate = (xs: (boolean | null)[]) => {
  const ys = xs.filter((x): x is boolean => x !== null);
  return ys.length ? `${ys.filter(Boolean).length}/${ys.length} (${Math.round((100 * ys.filter(Boolean).length) / ys.length)}%)` : '-';
};
const summary: Record<string, unknown> = { queries: queries.length, tools: new Set(queries.map((q) => q.slug)).size, category: flag('--category'), ...(useModel ? { model_id: modelId } : {}) };
for (const lang of langs) {
  const r = rows.filter((x) => x.lang === lang);
  summary[lang] = {
    card: rate(r.map((x) => x.card)),
    short: rate(r.map((x) => x.short)),
    'short+q': rate(r.map((x) => x.shortQ)),
    rules: rate(r.map((x) => x.rules)),
    ...(useModel ? { model: rate(r.map((x) => x.model)), matched_by: Object.fromEntries([...new Set(r.map((x) => x.matchedBy))].map((m) => [m, r.filter((x) => x.matchedBy === m).length])) } : {}),
  };
}
if (paid) {
  const spent = paid.sqlite.prepare('SELECT COALESCE(SUM(cost_usd), 0) AS c FROM meta_budget').get() as { c: number };
  summary.cost_usd = Number(spent.c.toFixed(4));
}
console.log(JSON.stringify(summary, null, 1));
const out = opt('--out');
if (out) writeFileSync(out, JSON.stringify({ summary, rows: rows.sort((a, b) => a.id.localeCompare(b.id) || a.lang.localeCompare(b.lang)) }, null, 1) + '\n');
