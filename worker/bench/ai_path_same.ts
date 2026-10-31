/**
 * The AI path must not change: with saved keyword outputs (bench/keywords.ts),
 * this tree and another checkout send byte-identical match requests to Meta
 * (instructions, request, the cards and their order, schema). No model call:
 * the keyword call is answered from the saved file and the match call is
 * captured, then failed.
 *
 *   node bench/ai_path_same.ts <index.json> <needs.json> <keywords-en.json> <keywords-zh.json> <other worker/ dir> [--control] [--out diff.json] [--alternatives]
 *
 * --control answers every keyword call with no keywords (the call failed), where
 * the rules scorer chooses the cards, so the requests are expected to differ.
 * Each request also runs once with the match call answered (the model picks the
 * first two cards), and the whole response is compared, rec_id aside.
 * --out writes each differing match request (both bodies) with the cards that
 * left or entered the shortlist, for a paid replay (scripts/replay_match.py).
 * --alternatives sends each need as find_alternatives pain points instead
 * (current tool "Ollama"), where the keyword call reads the same text.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const [indexPath, needsPath, kwEnPath, kwZhPath, otherDir, ...flags] = process.argv.slice(2);
const control = flags.includes('--control');
const alternatives = flags.includes('--alternatives');
const outPath = flags.includes('--out') ? flags[flags.indexOf('--out') + 1] : null;
const cardSlugs = (body: string) =>
  String(JSON.parse(body).input[1].content)
    .split('\n')
    .filter((line) => line.startsWith('{"slug"'))
    .map((line) => JSON.parse(line).slug as string);
const diffs: unknown[] = [];
const needs: { slug: string; category: string; en: string; zh: string }[] = JSON.parse(readFileSync(needsPath, 'utf8')).needs;
const keywords: Record<string, Record<string, string[]>> = {
  en: JSON.parse(readFileSync(kwEnPath, 'utf8')).keywords,
  zh: JSON.parse(readFileSync(kwZhPath, 'utf8')).keywords,
};

async function version(dir: string) {
  const [{ loadCatalog }, find, helpers] = await Promise.all([
    import(join(dir, 'src', 'catalog.ts')),
    import(join(dir, 'src', 'find.ts')),
    import(join(dir, 'test', 'helpers.ts')),
  ]);
  const catalog = loadCatalog(JSON.parse(readFileSync(indexPath, 'utf8')));
  const picked = (body: any) => {
    const cards = new Map(
      String(body.input[1].content)
        .split('\n')
        .filter((line) => line.startsWith('{"slug"'))
        .map((line) => JSON.parse(line))
        .map((card: any) => [card.slug, card]),
    );
    return helpers.metaResponse(
      helpers.answer({
        picks: body.text.format.schema.properties.picks.items.properties.slug.enum.slice(0, 2).map((slug: string) => ({
          slug,
          fit: 'Fits.',
          reasons: [{ claim: 'It is this tool', field: 'name', value: (cards.get(slug) as any).name }],
          tradeoffs: [],
          vs_well_known: null,
        })),
        best_free_slug: null,
      }),
    );
  };
  return async (args: Record<string, unknown>, kw: string[]) => {
    const run = async (match: (body: any) => Response) => {
      const h = helpers.harness((body: any) => (body.text.format.name === 'pickfit_keywords' ? helpers.metaResponse({ keywords: kw }) : match(body)));
      h.deps.catalog = catalog;
      const out = alternatives
        ? await find.findAlternatives({ current_software: 'Ollama', pain_points: args.need, ...(args.category ? { category: args.category } : {}) }, h.deps)
        : await find.findSoftware(args, h.deps);
      return { h, out };
    };
    const failed = await run(() => new Response('{}', { status: 400 }));
    const answered = await run(picked);
    const match = failed.h.requests.find((r: any) => ['pickfit_match', 'pickfit_alternatives'].includes(r.body.text.format.name));
    return {
      match: match ? String(match.init.body) : null,
      keywordCall: failed.h.requests.some((r: any) => r.body.text.format.name === 'pickfit_keywords'),
      response: answered.out.matched_by === 'muse-spark-1.3' ? JSON.stringify({ ...answered.out, rec_id: '' }) : null,
    };
  };
}

const [current, proposed] = [await version(otherDir), await version(join(import.meta.dirname, '..'))];
let compared = 0;
let withKeywords = 0;
let different = 0;
let responses = 0;
let responsesDifferent = 0;
for (const need of needs) {
  for (const lang of ['en', 'zh'] as const) {
    const saved = keywords[lang][need.slug];
    if (!saved) continue;
    const kw = control ? [] : saved;
    for (const args of [{ need: need[lang], category: need.category }, { need: need[lang] }]) {
      const [a, b] = [await current(args, kw), await proposed(args, kw)];
      compared++;
      if (a.keywordCall) withKeywords++;
      if (a.match === null || a.match !== b.match || a.keywordCall !== b.keywordCall) {
        different++;
        if (different <= 5) console.log(`DIFFERENT ${need.slug} ${lang} ${JSON.stringify(args).slice(0, 80)}`);
        if (a.match && b.match) {
          const [before, after] = [cardSlugs(a.match), cardSlugs(b.match)];
          const out = before.filter((slug) => !after.includes(slug));
          const added = after.filter((slug) => !before.includes(slug));
          diffs.push({ slug: need.slug, lang, args, out, in: added, cards: after.length, order_only: !out.length && !added.length, old: a.match, new: b.match });
        }
      }
      if (a.response !== null) {
        responses++;
        if (a.response !== b.response) {
          responsesDifferent++;
          if (responsesDifferent <= 3) console.log(`RESPONSE DIFFERS ${need.slug} ${lang}`);
        }
      }
    }
  }
}
console.log(`${compared} requests (${withKeywords} with a keyword call): ${different} match requests differ`);
console.log(`${responses} answered by the model: ${responsesDifferent} responses differ`);
if (outPath) {
  writeFileSync(outPath, JSON.stringify({ diffs }, null, 1) + '\n');
  const moved = diffs.filter((d: any) => !d.order_only) as any[];
  console.log(`${diffs.length} differing match requests -> ${outPath}: ${moved.length} change the cards (out ${moved.reduce((n, d) => n + d.out.length, 0)}, in ${moved.reduce((n, d) => n + d.in.length, 0)}), ${diffs.length - moved.length} only their order`);
}
