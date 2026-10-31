/**
 * Runs the product's keyword call (expand.ts, muse-spark-1.3) on the check
 * set's needs in one language and writes the keywords for bench/shortlist.ts,
 * with latency and cost. Paid (about $0.001 a need): record the printed total
 * in the shared ledger afterwards.
 *
 *   MODEL_API_KEY=… node bench/keywords.ts <index.json> <needs.json> <out.json> [zh|en] [limit]
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { loadCatalog } from '../src/catalog.ts';
import { englishKeywords, EXPAND_TIMEOUT_MS } from '../src/expand.ts';
import { makeD1, SETTINGS } from '../test/helpers.ts';

const [indexPath, needsPath, outPath, lang = 'zh', limitArg] = process.argv.slice(2);
const apiKey = process.env.MODEL_API_KEY;
if (!apiKey) throw new Error('MODEL_API_KEY is not set');
const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));
const needs: { slug: string; zh: string; en: string }[] = JSON.parse(readFileSync(needsPath, 'utf8')).needs;
const todo = needs.slice(0, limitArg ? Number(limitArg) : needs.length);

const { db } = makeD1();
const deps = {
  catalog,
  db,
  settings: { ...SETTINGS, apiKey, dailyCapUsd: 5, totalCapUsd: 5, timeoutMs: 25_000 },
  now: () => new Date(),
  waitUntil: () => {},
};

const keywords: Record<string, string[]> = {};
const outcomes: Record<string, number> = {};
const latencies: number[] = [];
let cost = 0;
const CONCURRENCY = 6;
let next = 0;
async function worker() {
  while (next < todo.length) {
    const need = todo[next++];
    const result = await englishKeywords(lang === 'en' ? need.en : need.zh, deps, new Date(), EXPAND_TIMEOUT_MS);
    cost += result.costUsd;
    outcomes[result.outcome] = (outcomes[result.outcome] ?? 0) + 1;
    if (result.keywords) {
      keywords[need.slug] = result.keywords;
      latencies.push(result.latencyMs);
    }
  }
}
await Promise.all(Array.from({ length: CONCURRENCY }, worker));

latencies.sort((a, b) => a - b);
const q = (p: number) => latencies[Math.min(latencies.length - 1, Math.floor(p * latencies.length))];
writeFileSync(outPath, JSON.stringify({ keywords }, null, 1) + '\n');
console.log(JSON.stringify({ needs: todo.length, outcomes, cost_usd: Number(cost.toFixed(5)), latency_ms: { p50: q(0.5), p90: q(0.9), max: q(1) } }));
