/**
 * How big the matcher's cards are, field by field: the cards findSoftware would send for the capability check set's
 * requests (the same shortlist and toCard as find.ts), measured as characters of the JSON the prompt carries.
 * No model call.
 *
 *   node bench/card_size.ts <index.json> [queries.json] [--max N]
 */
import { readFileSync } from 'node:fs';
import { loadCatalog } from '../src/catalog.ts';
import { promptCard, toCard } from '../src/cards.ts';
import { hardFilter } from '../src/filter.ts';
import { safeJson } from '../src/prompt.ts';
import { queryTerms, rulesTerms } from '../src/relevance.ts';

const args = process.argv.slice(2);
const [indexPath, queriesPath = 'bench/capability/queries.json'] = args.filter((a, i) => !a.startsWith('--') && args[i - 1] !== '--max');
const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));
const queries: any[] = JSON.parse(readFileSync(queriesPath, 'utf8')).queries;

const perField = new Map<string, number>();
let cards = 0;
let chars = 0;
const perRequest: number[] = [];
for (const q of queries) {
  const text = q.en ?? q.query;
  const terms = queryTerms(text);
  const { candidates } = hardFilter(catalog.entries, {}, { terms });
  let request = 0;
  for (const entry of candidates) {
    const card = promptCard(toCard(entry, undefined, undefined, [...new Set([...rulesTerms(text), ...terms])])) as any;
    const whole = safeJson(card).length;
    request += whole + 1;
    cards += 1;
    chars += whole;
    for (const [k, v] of Object.entries(card)) perField.set(k, (perField.get(k) ?? 0) + safeJson({ [k]: v }).length - 2);
  }
  perRequest.push(request);
}
const rows = [...perField.entries()].sort((a, b) => b[1] - a[1]);
console.log(`requests ${queries.length}, cards ${cards}, mean card ${Math.round(chars / cards)} chars, mean candidates block ${Math.round(perRequest.reduce((a, b) => a + b, 0) / perRequest.length)} chars`);
for (const [k, v] of rows) console.log(`${k.padEnd(24)} ${String(Math.round(v / cards)).padStart(5)} chars/card  ${(100 * v / chars).toFixed(1)}%`);
