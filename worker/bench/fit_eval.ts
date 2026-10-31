/**
 * The rules-only fit labels (src/fit.ts) against labeled queries, read from
 * findSoftware's own answers (no model). Per query class (from the labels:
 * good = some tool does the main job, grade 2; partial = only grade 1; none =
 * nothing helps): the answer's match_quality, the labels of the listed picks,
 * and how often each label holds up (good -> grade 2, partial -> grade >= 1,
 * weak -> grade 0). The picks are the ranking's, so Precision@5 is the ranking's.
 *
 *   node bench/fit_eval.ts <index.json> <queries.json>:<labels.json>:<dev|heldout|all> [...] [--show]
 */
import { readFileSync } from 'node:fs';
import { loadCatalog } from '../src/catalog.ts';
import { hardFilter, type Conditions } from '../src/filter.ts';
import { rulesTerms } from '../src/relevance.ts';
import { rankByRules } from '../src/rules.ts';
import { findSoftware } from '../src/find.ts';
import { harness } from '../test/helpers.ts';

const args = process.argv.slice(2);
const show = args.includes('--show');
const [indexPath, ...sets] = args.filter((a) => a !== '--show');
const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));

type Cls = 'good' | 'partial' | 'none';
const CLASSES: Cls[] = ['good', 'partial', 'none'];
const answers = Object.fromEntries(CLASSES.map((c) => [c, { good: 0, partial: 0, none: 0 }])) as Record<Cls, Record<string, number>>;
const labels = Object.fromEntries(CLASSES.map((c) => [c, { good: 0, partial: 0, weak: 0 }])) as Record<Cls, Record<string, number>>;
const holds: Record<string, number[]> = { good: [], partial: [], weak: [] };
const p5: number[] = [];
const ms: number[] = [];

for (const set of sets) {
  const [qPath, lPath, split] = set.split(':');
  const queries = JSON.parse(readFileSync(qPath, 'utf8')).queries.filter((q: any) => split === 'all' || q.split === split);
  const graded: Record<string, Record<string, number>> = JSON.parse(readFileSync(lPath, 'utf8')).labels;
  for (const q of queries) {
    const cond: Conditions = { ...(q.category !== 'any' ? { category: q.category } : {}), ...(q.os ? { os: q.os } : {}) };
    const grades = graded[q.id] ?? {};
    const cls: Cls = Object.values(grades).some((g) => g === 2) ? 'good' : Object.keys(grades).length ? 'partial' : 'none';
    const h = harness(null, { modelEnabled: false });
    h.deps.catalog = catalog;
    const t0 = performance.now();
    const out: any = await findSoftware({ need: q.query, ...cond }, h.deps);
    ms.push(performance.now() - t0);
    answers[cls][out.match_quality ?? 'none']++;
    for (const pick of out.picks) {
      const g = grades[pick.slug] ?? 0;
      labels[cls][pick.match.quality]++;
      holds[pick.match.quality].push(pick.match.quality === 'good' ? Number(g === 2) : pick.match.quality === 'partial' ? Number(g >= 1) : Number(g === 0));
    }
    if (cls === 'good') {
      const f = hardFilter(catalog.entries, cond, { terms: rulesTerms(q.query), scorer: 'rules' });
      p5.push(rankByRules(f.candidates, f.relevance, cond.os).slice(0, 5).filter((e) => grades[e.slug] === 2).length / 5);
    }
    if (show) {
      console.log(`${q.id} class ${cls} -> ${out.match_quality} | ${q.query}`);
      for (const pick of out.picks) console.log(`   ${pick.slug} g${grades[pick.slug] ?? 0} ${pick.match.quality} covers ${pick.match.covers.join(',')} | missing ${pick.match.missing.join(',')}`);
      if (out.coverage_note) console.log(`   note: ${out.coverage_note}`);
    }
  }
}

const mean = (a: number[]) => (a.length ? (100 * a.reduce((x, y) => x + y, 0)) / a.length : NaN);
const sum = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0);
console.log('\nclass     n   answer good/partial/none   pick labels good/partial/weak');
for (const c of CLASSES) {
  const a = answers[c];
  const l = labels[c];
  console.log(`${c.padEnd(8)}${String(sum(a)).padStart(3)}   ${`${a.good}/${a.partial}/${a.none}`.padStart(22)}   ${`${l.good}/${l.partial}/${l.weak}`.padStart(28)}`);
}
console.log(`queries with a suitable tool whose answer is none: ${answers.good.none}/${sum(answers.good)} (their tools are still listed)`);
console.log(`labels that hold up: good -> grade 2 ${mean(holds.good).toFixed(1)}% (n=${holds.good.length}); partial -> grade >= 1 ${mean(holds.partial).toFixed(1)}% (n=${holds.partial.length}); weak -> grade 0 ${mean(holds.weak).toFixed(1)}% (n=${holds.weak.length})`);
console.log(`good-class P@5 (the ranking's picks): ${mean(p5).toFixed(1)}% (n=${p5.length})`);
console.log(`findSoftware latency in process: mean ${(ms.reduce((a, b) => a + b, 0) / ms.length).toFixed(2)} ms`);
