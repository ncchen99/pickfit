/**
 * The rules-only ranking (MATCH_MODE off, or the keyword call failed) against
 * labeled queries (scripts/rules_eval.py): this tree's code vs another
 * checkout's (e.g. main, extracted with `git archive`). No model call.
 *
 *   node bench/rules_eval.ts <index.json> <queries.json> <labels.json> <other worker/ dir> <dev|heldout> [--show] [--before-rules]
 *
 * relevant = grade 2 ("does the main job"); lenient = grade 1 or 2.
 * P@5: share of the first 5 ranked tools that are relevant, over queries with
 * at least one relevant tool; hit@5: at least one relevant in the first 5;
 * MRR: 1 / rank of the first relevant tool. R@60: share of the relevant tools among the
 * cards when more than MAX_CARDS pass. Each version's own findSoftware (model
 * off) is checked to return the same top 3 as the ranking measured here.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Conditions } from '../src/filter.ts';

const [indexPath, queriesPath, labelsPath, otherDir, split, ...flags] = process.argv.slice(2);
const show = flags.includes('--show');
const beforeRules = flags.includes('--before-rules');

interface Version {
  name: string;
  /** Tools in rules order, and the cards a shortlist would send. */
  rank: (entries: any[], cond: Conditions, text: string) => { ranked: any[]; cards: Set<string>; passed: number };
  find: (catalog: any, cond: Conditions, text: string) => Promise<string[]>;
  catalog: any;
}

async function load(name: string, dir: string, proposed: boolean): Promise<Version> {
  const src = (f: string) => import(join(dir, 'src', f));
  const [{ loadCatalog }, filter, relevance, rules, find, helpers] = await Promise.all([
    src('catalog.ts'),
    src('filter.ts'),
    src('relevance.ts'),
    src('rules.ts'),
    src('find.ts'),
    import(join(dir, 'test', 'helpers.ts')),
  ]);
  const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));
  const rank = (entries: any[], cond: Conditions, text: string) => {
    // Both sides rank as the shipped rules path does; --before-rules compares with the ranking before it (queryTerms, BM25).
    const f = proposed || !beforeRules
      ? filter.hardFilter(entries, cond, { terms: relevance.rulesTerms(text), scorer: 'rules' })
      : filter.hardFilter(entries, cond, { terms: relevance.queryTerms(text) });
    return { ranked: rules.rankByRules(f.candidates, f.relevance, cond.os), cards: new Set(f.candidates.map((e: any) => e.slug)), passed: f.passed };
  };
  const findPicks = async (cat: any, cond: Conditions, text: string) => {
    const h = helpers.harness(null, { modelEnabled: false });
    h.deps.catalog = cat;
    const out = await find.findSoftware({ need: text, ...cond }, h.deps);
    return out.picks.map((p: any) => p.slug);
  };
  return { name, rank, find: findPicks, catalog };
}

const queries = JSON.parse(readFileSync(queriesPath, 'utf8')).queries.filter((q: any) => q.split === split);
const labels: Record<string, Record<string, number>> = JSON.parse(readFileSync(labelsPath, 'utf8')).labels;
const versions = [await load('current', join(otherDir), false), await load('proposed', join(import.meta.dirname, '..'), true)];

const cond = (q: any): Conditions => ({
  ...(q.category !== 'any' ? { category: q.category } : {}),
  ...(q.os ? { os: q.os } : {}),
});

type Stat = { p5: number[]; p5l: number[]; hit5: number[]; mrr: number[]; r60: number[]; r60l: number[]; ms: number[] };
const stats = new Map<string, Map<string, Stat>>();
const stat = (v: string, group: string) => {
  const byGroup = stats.get(v) ?? new Map<string, Stat>();
  stats.set(v, byGroup);
  const s = byGroup.get(group) ?? { p5: [], p5l: [], hit5: [], mrr: [], r60: [], r60l: [], ms: [] };
  byGroup.set(group, s);
  return s;
};
let mismatches = 0;

for (const q of queries) {
  const grades = labels[q.id] ?? {};
  const rel = new Set(Object.keys(grades).filter((s) => grades[s] === 2));
  const lenient = new Set(Object.keys(grades));
  for (const v of versions) {
    const c = cond(q);
    v.rank(v.catalog.entries, c, q.query); // warm the index
    const t0 = performance.now();
    const reps = 20;
    let r!: ReturnType<Version['rank']>;
    for (let i = 0; i < reps; i++) r = v.rank(v.catalog.entries, c, q.query);
    const ms = (performance.now() - t0) / reps;
    const top5 = r.ranked.slice(0, 5).map((e: any) => e.slug);
    const picks = await v.find(v.catalog, c, q.query);
    if (picks.join() !== top5.slice(0, picks.length).join()) {
      mismatches++;
      console.log(`MISMATCH ${v.name} ${q.id}: find ${picks.join(',')} vs bench ${top5.slice(0, 3).join(',')}`);
    }
    for (const group of ['all', q.lang]) {
      const s = stat(v.name, group);
      s.ms.push(ms);
      if (rel.size) {
        s.p5.push(top5.filter((x: string) => rel.has(x)).length / 5);
        s.hit5.push(top5.some((x: string) => rel.has(x)) ? 1 : 0);
        const first = r.ranked.findIndex((e: any) => rel.has(e.slug));
        s.mrr.push(first < 0 ? 0 : 1 / (first + 1));
        if (r.passed > 60) s.r60.push([...rel].filter((x) => r.cards.has(x)).length / rel.size);
      }
      if (lenient.size) {
        s.p5l.push(top5.filter((x: string) => lenient.has(x)).length / 5);
        if (r.passed > 60) s.r60l.push([...lenient].filter((x) => r.cards.has(x)).length / lenient.size);
      }
    }
    if (show) {
      const mark = (x: string) => (rel.has(x) ? '**' : lenient.has(x) ? '*' : '');
      console.log(`${v.name.padEnd(8)} ${q.id} ${q.lang} rel=${rel.size} | ${top5.map((x: string) => x + mark(x)).join(' ')}`);
    }
  }
  if (show) console.log(`         ${q.id}: ${q.query}`);
}

const mean = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN);
const pct = (a: number[]) => `${(100 * mean(a)).toFixed(1)}%`.padStart(6) + ` (n=${a.length})`;
console.log(`\n${split}: ${queries.length} queries; relevant = grade 2, lenient = grade 1 or 2`);
for (const group of ['all', 'en', 'zh']) {
  for (const v of versions) {
    const s = stats.get(v.name)!.get(group);
    if (!s) continue;
    console.log(
      `${group.padEnd(4)} ${v.name.padEnd(9)} P@5 ${pct(s.p5)}  hit@5 ${pct(s.hit5)}  MRR ${mean(s.mrr).toFixed(3)}  R@60 ${pct(s.r60)}  | lenient P@5 ${pct(s.p5l)} R@60 ${pct(s.r60l)}  | ${mean(s.ms).toFixed(2)} ms`,
    );
  }
}
console.log(`findSoftware vs bench top 3 mismatches: ${mismatches}`);
