/**
 * Labels only: a rules-only answer (no model) from this tree lists the same
 * picks, in the same order, with the same best_free, question and everything
 * else as another checkout (main). Allowed differences, all added text: each
 * pick's `match` and fit note in tradeoffs, the answer's `match_quality`, the
 * fit sentence in coverage_note (before any note the other tree writes) and in
 * how_we_know. No model call.
 *
 *   node bench/rules_same.ts <index.json> <other worker/ dir> <queries.json> [...]
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const [indexPath, otherDir, ...queryFiles] = process.argv.slice(2);
const FIT_SENTENCE = " Fit is judged by which of the request's specific words the profile mentions.";

async function version(dir: string) {
  const [{ loadCatalog }, find, helpers] = await Promise.all([
    import(join(dir, 'src', 'catalog.ts')),
    import(join(dir, 'src', 'find.ts')),
    import(join(dir, 'test', 'helpers.ts')),
  ]);
  const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));
  return async (args: Record<string, unknown>) => {
    const h = helpers.harness(null, { modelEnabled: false });
    h.deps.catalog = catalog;
    return { ...(await find.findSoftware(args, h.deps)), rec_id: '' };
  };
}

/** This tree's answer less the labels, to compare with the other tree's. */
function unlabeled(out: any, other: any) {
  const { match_quality, ...rest } = out;
  const note = rest.coverage_note as string | null;
  // The fit note comes first; whatever the other tree writes must follow it unchanged.
  const otherNote = other.coverage_note as string | null;
  const coverage_note = otherNote === null ? (note === null || match_quality ? null : note) : note?.endsWith(otherNote) ? otherNote : note;
  return {
    ...rest,
    coverage_note,
    picks: rest.picks.map(({ match, ...pick }: any) => ({
      ...pick,
      tradeoffs: pick.tradeoffs.filter((t: string) => !/^(Covers part of the request|Weak match):/.test(t)),
      how_we_know: pick.how_we_know.replace(FIT_SENTENCE, ''),
    })),
  };
}

const [other, mine] = [await version(otherDir), await version(join(import.meta.dirname, '..'))];
let compared = 0;
let picksDiffer = 0;
let restDiffer = 0;
for (const file of queryFiles) {
  for (const q of JSON.parse(readFileSync(file, 'utf8')).queries) {
    const args = { need: q.query, ...(q.category !== 'any' ? { category: q.category } : {}), ...(q.os ? { os: q.os } : {}) };
    const [a, b] = [await other(args), await mine(args)];
    compared++;
    const slugs = (out: any) => out.picks.map((p: any) => p.slug).join(',');
    if (slugs(a) !== slugs(b)) {
      picksDiffer++;
      console.log(`PICKS ${q.id}: main ${slugs(a)} | here ${slugs(b)}`);
    } else if (JSON.stringify(unlabeled(b, a)) !== JSON.stringify(a)) {
      restDiffer++;
      console.log(`OTHER ${q.id}: ${JSON.stringify(unlabeled(b, a)).slice(0, 300)}`);
    }
  }
}
console.log(`${compared} rules-only answers: picks or order differ in ${picksDiffer}; anything else besides the labels differs in ${restDiffer}`);
