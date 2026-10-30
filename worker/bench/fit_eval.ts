/**
 * The rules-only fit decision (src/fit.ts) against labeled queries: per query
 * class (from the labels: good = some tool does the main job, grade 2;
 * partial = only grade 1; none = nothing helps), how often the answer's
 * decision is right, false positives (good or partial claimed when nothing
 * helps), false negatives (no good match said when a tool does the job), and
 * Precision@5 of the picks shown. No model call.
 *
 *   node bench/fit_eval.ts <index.json> <queries.json>:<labels.json>:<dev|heldout> [...] [--show]
 */
import { readFileSync } from 'node:fs';
import { loadCatalog } from '../src/catalog.ts';
import { hardFilter, type Conditions } from '../src/filter.ts';
import { fitOf, jobOf, type FitQuality } from '../src/fit.ts';
import { rulesTerms } from '../src/relevance.ts';
import { rankByRules } from '../src/rules.ts';
import { findSoftware } from '../src/find.ts';
import { harness } from '../test/helpers.ts';

const args = process.argv.slice(2);
const show = args.includes('--show');
const [indexPath, ...sets] = args.filter((a) => a !== '--show');
const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));

type Cls = 'good' | 'partial' | 'none';
const decisions: Record<Cls, Record<FitQuality, number>> = {
  good: { good: 0, partial: 0, none: 0 },
  partial: { good: 0, partial: 0, none: 0 },
  none: { good: 0, partial: 0, none: 0 },
};
const p5Before: number[] = [];
const p5Shown: number[] = [];
const precisionShown: number[] = [];
const p5ShownLenient: number[] = [];
const picksClaimed: Record<'good' | 'partial', number[]> = { good: [], partial: [] };
const ms: number[] = [];
let mismatches = 0;

for (const set of sets) {
  const [qPath, lPath, split] = set.split(':');
  const queries = JSON.parse(readFileSync(qPath, 'utf8')).queries.filter((q: any) => q.split === split);
  const labels: Record<string, Record<string, number>> = JSON.parse(readFileSync(lPath, 'utf8')).labels;
  for (const q of queries) {
    const cond: Conditions = { ...(q.category !== 'any' ? { category: q.category } : {}), ...(q.os ? { os: q.os } : {}) };
    const grades = labels[q.id] ?? {};
    const cls: Cls = Object.values(grades).some((g) => g === 2) ? 'good' : Object.keys(grades).length ? 'partial' : 'none';
    const f = hardFilter(catalog.entries, cond, { terms: rulesTerms(q.query), scorer: 'rules' });
    const ranked = rankByRules(f.candidates, f.relevance, cond.os);
    const t0 = performance.now();
    const job = jobOf(catalog.entries, q.query);
    const fits = ranked.map((entry) => ({ entry, fit: fitOf(entry, job) }));
    const shown = [...fits.filter((x) => x.fit.quality === 'good'), ...fits.filter((x) => x.fit.quality === 'partial')];
    ms.push(performance.now() - t0);
    const quality: FitQuality = shown[0]?.fit.quality ?? 'none';
    decisions[cls][quality]++;
    const rel = (slug: string) => grades[slug] === 2;
    if (cls === 'good') p5Before.push(ranked.slice(0, 5).filter((e) => rel(e.slug)).length / 5);
    if (shown.length && cls === 'good') {
      p5Shown.push(shown.slice(0, 5).filter((x) => rel(x.entry.slug)).length / 5);
      precisionShown.push(shown.slice(0, 5).filter((x) => rel(x.entry.slug)).length / Math.min(5, shown.length));
    }
    if (shown.length) p5ShownLenient.push(shown.slice(0, 5).filter((x) => grades[x.entry.slug]).length / Math.min(5, shown.length));
    for (const x of shown.slice(0, 3)) {
      const g = grades[x.entry.slug] ?? 0;
      picksClaimed[x.fit.quality as 'good' | 'partial'].push(x.fit.quality === 'good' ? Number(g === 2) : Number(g >= 1));
    }
    if (show) {
      console.log(`${q.id} class ${cls} -> ${quality} | ${q.query}`);
      console.log(`   job: ${job.terms.join(' ')} | named: ${[...job.named].join(' ')}`);
      for (const x of fits.slice(0, 4)) console.log(`   rank: ${x.entry.slug} g${grades[x.entry.slug] ?? 0} ${x.fit.quality} covers ${x.fit.covers.join(',')}`);
      for (const x of shown.slice(0, 3)) console.log(`   shown: ${x.entry.slug} g${grades[x.entry.slug] ?? 0} ${x.fit.quality}`);
    }
    // The product's own answer must agree with what is measured here.
    const h = harness(null, { modelEnabled: false });
    h.deps.catalog = catalog;
    const out: any = await findSoftware({ need: q.query, ...cond }, h.deps);
    const expect = shown.slice(0, 3).map((x) => x.entry.slug);
    if (out.picks.map((p: any) => p.slug).join() !== expect.join() || (out.match_quality ?? 'none') !== quality) {
      mismatches++;
      console.log(`MISMATCH ${q.id}: find ${out.match_quality} ${out.picks.map((p: any) => p.slug).join(',')} vs bench ${quality} ${expect.join(',')}`);
    }
  }
}

const mean = (a: number[]) => (a.length ? (100 * a.reduce((x, y) => x + y, 0)) / a.length : NaN);
const total = (c: Cls) => decisions[c].good + decisions[c].partial + decisions[c].none;
console.log('\nclass     n   -> good partial none   right   false positive / false negative');
for (const c of ['good', 'partial', 'none'] as Cls[]) {
  const d = decisions[c];
  const n = total(c);
  const right = c === 'good' ? d.good : c === 'partial' ? d.partial : d.none;
  const fp = c === 'none' ? `FP ${d.good + d.partial}/${n}` : '';
  const fn = c !== 'none' ? `FN ${d.none}/${n}` : '';
  console.log(`${c.padEnd(8)}${String(n).padStart(3)}   ${String(d.good).padStart(6)} ${String(d.partial).padStart(7)} ${String(d.none).padStart(4)}   ${String(right).padStart(3)}/${n}   ${fp}${fn}`);
}
console.log(`good-class P@5: ranking alone ${mean(p5Before).toFixed(1)}% (n=${p5Before.length}); with the decision ${mean(p5Shown).toFixed(1)}% (n=${p5Shown.length}), precision of what is shown ${mean(precisionShown).toFixed(1)}%`);
console.log(`shown picks with grade >= 1 (any class): ${mean(p5ShownLenient).toFixed(1)}% (n=${p5ShownLenient.length})`);
console.log(`claimed good -> grade 2: ${mean(picksClaimed.good).toFixed(1)}% (n=${picksClaimed.good.length}); claimed partial -> grade >= 1: ${mean(picksClaimed.partial).toFixed(1)}% (n=${picksClaimed.partial.length})`);
console.log(`decision latency: mean ${(ms.reduce((a, b) => a + b, 0) / ms.length).toFixed(2)} ms; findSoftware vs bench mismatches: ${mismatches}`);
