/**
 * The labeling pool for scripts/rules_eval.py: for each query, every tool that
 * passes its hard filters, as a short description (no ranking involved).
 *
 *   node bench/rules_pool.ts <index.json> <queries.json> <pool.json>
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { loadCatalog } from '../src/catalog.ts';
import { passing, type Conditions } from '../src/filter.ts';

const [indexPath, queriesPath, outPath] = process.argv.slice(2);
const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));
const queries = JSON.parse(readFileSync(queriesPath, 'utf8')).queries;

export const conditions = (q: { category: string; os: string | null }): Conditions => ({
  ...(q.category !== 'any' ? { category: q.category as Conditions['category'] } : {}),
  ...(q.os ? { os: q.os as Conditions['os'] } : {}),
});

const pool = queries.map((q: any) => ({
  id: q.id,
  query: q.query,
  tools: passing(catalog.entries, conditions(q)).map((e) => ({
    slug: e.slug,
    name: e.name,
    category: e.category,
    summary: e.summary,
    use_cases: e.use_cases.slice(0, 3),
    tags: e.tags.slice(0, 8),
  })),
}));
writeFileSync(outPath, JSON.stringify({ queries: pool }, null, 1) + '\n');
const sizes = pool.map((p: any) => p.tools.length);
console.log(`${pool.length} queries, ${sizes.reduce((a: number, b: number) => a + b, 0)} tools to label (min ${Math.min(...sizes)}, max ${Math.max(...sizes)})`);
