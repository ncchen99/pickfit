/**
 * Do the right tools still reach the matcher? For the fit-fresh dev queries, how many of the tools labeled 2 (does
 * the main job) are among the MAX_CARDS cards, with the rules scorer (no keywords) and with BM25 on the request's own
 * words (standing in for the model's keywords, as bench/capability.ts's short+q does). No model call; never reads eval/.
 *
 *   node bench/dev_shortlist.ts <index.json> [<other index.json>]
 *
 * With two indexes it prints both side by side (e.g. without and with documented capabilities).
 */
import { readFileSync } from 'node:fs';
import { loadCatalog } from '../src/catalog.ts';
import { hardFilter, type Conditions } from '../src/filter.ts';
import { queryTerms, rulesTerms } from '../src/relevance.ts';

const [first, second] = process.argv.slice(2);
const queries: any[] = JSON.parse(readFileSync('bench/fit-fresh/queries.json', 'utf8')).queries;
const labels: Record<string, Record<string, number>> = JSON.parse(readFileSync('bench/fit-fresh/labels.json', 'utf8')).labels;

function measure(indexPath: string) {
  const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));
  let wanted = 0;
  let rules = 0;
  let words = 0;
  const perQuery: Record<string, [number, number, number]> = {};
  for (const q of queries) {
    const good = Object.entries(labels[q.id] ?? {}).filter(([slug, g]) => g === 2 && catalog.bySlug.has(slug)).map(([slug]) => slug);
    if (!good.length) continue;
    const cond: Conditions = { ...(q.category !== 'any' ? { category: q.category } : {}), ...(q.os ? { os: q.os } : {}) };
    const byRules = new Set(hardFilter(catalog.entries, cond, { terms: rulesTerms(q.query), scorer: 'rules' }).candidates.map((e) => e.slug));
    const byWords = new Set(hardFilter(catalog.entries, cond, { terms: queryTerms(q.query) }).candidates.map((e) => e.slug));
    const r = good.filter((s) => byRules.has(s)).length;
    const w = good.filter((s) => byWords.has(s)).length;
    wanted += good.length;
    rules += r;
    words += w;
    perQuery[q.id] = [good.length, r, w];
  }
  return { wanted, rules, words, perQuery };
}

const a = measure(first);
const b = second ? measure(second) : null;
const pct = (n: number, d: number) => `${n}/${d} (${Math.round((100 * n) / d)}%)`;
console.log(`tools labeled 2 on the cards: rules ${pct(a.rules, a.wanted)}, words ${pct(a.words, a.wanted)}` +
  (b ? `  ->  rules ${pct(b.rules, b.wanted)}, words ${pct(b.words, b.wanted)}` : ''));
if (b) {
  for (const id of Object.keys(a.perQuery)) {
    const [n, r0, w0] = a.perQuery[id];
    const [, r1, w1] = b.perQuery[id] ?? [n, 0, 0];
    if (r0 !== r1 || w0 !== w1) console.log(`  ${id}: of ${n}, rules ${r0} -> ${r1}, words ${w0} -> ${w1}`);
  }
}
