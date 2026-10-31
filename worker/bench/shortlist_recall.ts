/**
 * Shortlist recall by labeled class (scripts/rules_eval.py labels): of the
 * tools graded suitable for a query (grade 2; for queries with none, grade 1),
 * how many reach the MAX_CARDS cards the model reads, this tree against another
 * checkout (main). Only queries where more than MAX_CARDS tools pass the hard
 * filters, since otherwise every tool is sent. Two shortlists:
 *   model path: request words (less negated ones) plus Meta's keywords, as find.ts
 *     sends when the keyword call works (keywords from bench/keywords.ts, by query id);
 *   fallback: the rules' own words and scorer, when the keyword call fails.
 * No model call; never reads eval/.
 *
 *   node bench/shortlist_recall.ts <index.json> <other worker/ dir> <queries.json>:<labels.json>[:<keywords.json>] [...]
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const [indexPath, otherDir, ...sets] = process.argv.slice(2);

async function version(dir: string) {
  const src = (f: string) => import(join(dir, 'src', f));
  const [{ loadCatalog }, filter, relevance] = await Promise.all([src('catalog.ts'), src('filter.ts'), src('relevance.ts')]);
  const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));
  const own = (text: string) => (relevance.dropNegated ? relevance.dropNegated(text) : text);
  return {
    max: filter.MAX_CARDS as number,
    cards(cond: any, text: string, keywords: string[] | null) {
      const f = keywords
        ? filter.hardFilter(catalog.entries, cond, { terms: relevance.queryTerms(own(text), ...keywords) })
        : filter.hardFilter(catalog.entries, cond, { terms: relevance.rulesTerms(text), scorer: 'rules' });
      return { passed: f.passed as number, cards: new Set<string>(f.candidates.map((e: any) => e.slug)) };
    },
  };
}

const versions = { main: await version(otherDir), jobs: await version(join(import.meta.dirname, '..')) };
type Row = { recall: number[]; missed: number; queries: number };
const rows = new Map<string, Row>();
const row = (key: string) => rows.get(key) ?? (rows.set(key, { recall: [], missed: 0, queries: 0 }), rows.get(key)!);

for (const set of sets) {
  const [qPath, lPath, kPath] = set.split(':');
  const labels: Record<string, Record<string, number>> = JSON.parse(readFileSync(lPath, 'utf8')).labels;
  const keywords: Record<string, string[]> = kPath ? JSON.parse(readFileSync(kPath, 'utf8')).keywords : {};
  for (const q of JSON.parse(readFileSync(qPath, 'utf8')).queries) {
    const grades = labels[q.id] ?? {};
    const cls = Object.values(grades).some((g) => g === 2) ? 'good' : Object.keys(grades).length ? 'partial' : 'none';
    if (cls === 'none') continue;
    const suitable = Object.keys(grades).filter((s) => grades[s] === (cls === 'good' ? 2 : 1));
    const cond = { ...(q.category !== 'any' ? { category: q.category } : {}), ...(q.os ? { os: q.os } : {}) };
    for (const path of kPath ? ['model', 'fallback'] : ['fallback']) {
      for (const [name, v] of Object.entries(versions)) {
        const kw = path === 'model' ? (keywords[q.id] ?? null) : null;
        if (path === 'model' && !kw) continue;
        const { passed, cards } = v.cards(cond, q.query, kw);
        if (passed <= v.max) continue;
        const hit = suitable.filter((s) => cards.has(s)).length;
        for (const group of [`${path} ${cls} all`, `${path} ${cls} ${q.lang}`]) {
          const r = row(`${group} ${name}`);
          r.queries++;
          r.recall.push(hit / suitable.length);
          if (hit < suitable.length) r.missed++;
        }
      }
    }
  }
}

const pct = (a: number[]) => (a.length ? `${((100 * a.reduce((x, y) => x + y, 0)) / a.length).toFixed(1)}%` : '-');
console.log('path      class    lang  version  queries  recall of suitable tools  queries with one left out');
for (const [key, r] of [...rows].sort(([a], [b]) => a.localeCompare(b))) {
  const [path, cls, lang, name] = key.split(' ');
  console.log(`${path.padEnd(9)} ${cls.padEnd(8)} ${lang.padEnd(5)} ${name.padEnd(8)} ${String(r.queries).padStart(7)}  ${pct(r.recall).padStart(24)}  ${String(r.missed).padStart(26)}`);
}
