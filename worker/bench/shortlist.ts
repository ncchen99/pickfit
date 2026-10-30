/**
 * Shortlist recall on the data-only check set (scripts/shortlist_needs.py):
 * for each verified tool, its own summary rewritten as a user need. How often
 * does that tool reach the MAX_CARDS cards the matcher reads, and where do the
 * rules put it? No model call; never reads eval/.
 *
 *   node bench/shortlist.ts <index.json> <needs.json> [zh=<keywords.json>] [en=<keywords.json>]
 *
 * keywords.json (from bench/keywords.ts): the English keywords Meta gave for
 * each need in that language; those rows ("+kw") show the shortlist with them.
 */
import { readFileSync } from 'node:fs';
import { loadCatalog, type Entry } from '../src/catalog.ts';
import { hardFilter, MAX_CARDS, type Conditions } from '../src/filter.ts';
import { queryTerms } from '../src/relevance.ts';
import { rankByRules } from '../src/rules.ts';

interface Need {
  slug: string;
  category: 'dev_cli' | 'local_ai' | 'mcp_server';
  en: string;
  zh: string;
}

const [indexPath, needsPath, ...keywordArgs] = process.argv.slice(2);
const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));
const needs: Need[] = JSON.parse(readFileSync(needsPath, 'utf8')).needs.filter((n: Need) => catalog.bySlug.has(n.slug));
const keywords: Record<string, Record<string, string[]>> = Object.fromEntries(
  keywordArgs.map((arg) => {
    const [lang, path] = arg.split('=');
    return [lang, JSON.parse(readFileSync(path, 'utf8')).keywords];
  }),
);

/** The rules order before this change: distinct request words found in the profile, then OS, then treasure. */
const OLD_STOP = new Set(
  'a an and any app are best but can for from get have help how its like need not offline free mac macos linux windows on one only or run runs that the this tool tools use want which with without work works'.split(' '),
);
const oldWords = (text: string) => (text.toLowerCase().match(/[a-z0-9][a-z0-9+.-]{2,}/g) ?? []).filter((w) => !OLD_STOP.has(w));
function oldRules(entries: Entry[], need: string): Entry[] {
  const hits = (e: Entry) => {
    const profile = new Set(oldWords([e.name, e.summary, e.why_worth_it ?? '', ...e.tags, ...e.use_cases, ...e.alternatives_to].join(' ')));
    return new Set(oldWords(need).filter((w) => profile.has(w))).size;
  };
  return entries
    .map((entry) => ({ entry, hits: hits(entry), treasure: entry.scores?.treasure_value ?? -1 }))
    .sort((a, b) => b.hits - a.hits || b.treasure - a.treasure || a.entry.slug.localeCompare(b.entry.slug))
    .map((x) => x.entry);
}

interface Row {
  cases: number;
  over: number;
  before: number;
  after: number;
  rules1Before: number;
  rules3Before: number;
  rules1After: number;
  rules3After: number;
}
const empty = (): Row => ({ cases: 0, over: 0, before: 0, after: 0, rules1Before: 0, rules3Before: 0, rules1After: 0, rules3After: 0 });
const table = new Map<string, Row>();

for (const need of needs) {
  for (const lang of ['en', 'zh'] as const) {
    for (const scope of ['category', 'any'] as const) {
      const cond: Conditions = scope === 'category' ? { category: need.category } : {};
      const raw = need[lang];
      const expanded = keywords[lang]?.[need.slug]?.join(' ') ?? '';
      const terms = queryTerms(raw, expanded);
      const before = hardFilter(catalog.entries, cond);
      const after = hardFilter(catalog.entries, cond, { terms });
      const key = `${lang}${expanded ? '+kw' : ''} ${scope === 'category' ? need.category : 'any'}`;
      const row = table.get(key) ?? empty();
      table.set(key, row);
      row.cases++;
      if (before.passed > MAX_CARDS) row.over++;
      if (before.candidates.some((e) => e.slug === need.slug)) row.before++;
      if (after.candidates.some((e) => e.slug === need.slug)) row.after++;
      const oldTop = oldRules(before.candidates, raw).slice(0, 3).map((e) => e.slug);
      const newTop = rankByRules(after.candidates, after.relevance).slice(0, 3).map((e) => e.slug);
      if (oldTop[0] === need.slug) row.rules1Before++;
      if (oldTop.includes(need.slug)) row.rules3Before++;
      if (newTop[0] === need.slug) row.rules1After++;
      if (newTop.includes(need.slug)) row.rules3After++;
    }
  }
}

const pct = (n: number, d: number) => `${((100 * n) / d).toFixed(1)}%`.padStart(6);
console.log(`${needs.length} needs, ${catalog.entries.length} entries; recall = the need's own tool among the ${MAX_CARDS} cards`);
console.log('set            cases  >60   recall before  after   rules top1 before after   top3 before after');
for (const [key, r] of [...table].sort()) {
  console.log(
    `${key.padEnd(15)}${String(r.cases).padStart(5)}${String(r.over).padStart(5)}   ${pct(r.before, r.cases)}  ${pct(r.after, r.cases)}        ${pct(r.rules1Before, r.cases)} ${pct(r.rules1After, r.cases)}        ${pct(r.rules3Before, r.cases)} ${pct(r.rules3After, r.cases)}`,
  );
}
