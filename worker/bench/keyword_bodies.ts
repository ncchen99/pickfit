/**
 * The product's keyword call (expand.ts) for labeled queries, in two halves so
 * the paid part goes through the shared ledger (scripts/send_bodies.py):
 *
 *   node bench/keyword_bodies.ts capture <out-bodies.json> <queries.json> [...]
 *       writes each query's request body, exactly as find.ts would send it;
 *   node bench/keyword_bodies.ts parse <responses.json> <out-keywords.json>
 *       reads Meta's raw responses back through englishKeywords, so the
 *       keywords are the product's own parse ({keywords: {query id: [...]}}).
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { englishKeywords, EXPAND_TIMEOUT_MS } from '../src/expand.ts';
import { fixtureCatalog, makeD1, SETTINGS } from '../test/helpers.ts';

const [mode, ...args] = process.argv.slice(2);
const deps = (fetch: typeof globalThis.fetch) => ({
  catalog: fixtureCatalog(),
  db: makeD1().db,
  settings: { ...SETTINGS, apiKey: 'unused', dailyCapUsd: 100, totalCapUsd: 100, timeoutMs: 25_000 },
  now: () => new Date(),
  waitUntil: () => {},
  fetch,
  sleep: async () => {},
});

if (mode === 'capture') {
  const [outPath, ...files] = args;
  const bodies: Record<string, string> = {};
  for (const file of files) {
    for (const q of JSON.parse(readFileSync(file, 'utf8')).queries) {
      await englishKeywords(q.query, deps((async (_url: string, init: RequestInit) => {
        bodies[q.id] = String(init.body);
        return new Response('{}', { status: 400 });
      }) as typeof fetch) as any, new Date(), EXPAND_TIMEOUT_MS);
    }
  }
  writeFileSync(outPath, JSON.stringify({ bodies }, null, 1) + '\n');
  console.log(`${Object.keys(bodies).length} keyword requests -> ${outPath}`);
} else if (mode === 'parse') {
  const [responsesPath, outPath] = args;
  const responses: Record<string, unknown> = JSON.parse(readFileSync(responsesPath, 'utf8')).responses;
  const keywords: Record<string, string[]> = {};
  const outcomes: Record<string, number> = {};
  for (const [id, raw] of Object.entries(responses)) {
    const result = await englishKeywords('(replayed)', deps((async () => Response.json(raw)) as typeof fetch) as any, new Date(), EXPAND_TIMEOUT_MS);
    outcomes[result.outcome] = (outcomes[result.outcome] ?? 0) + 1;
    if (result.keywords) keywords[id] = result.keywords;
  }
  writeFileSync(outPath, JSON.stringify({ keywords }, null, 1) + '\n');
  console.log(`${Object.keys(keywords).length} queries with keywords -> ${outPath}; outcomes ${JSON.stringify(outcomes)}`);
} else {
  throw new Error('mode: capture or parse');
}
