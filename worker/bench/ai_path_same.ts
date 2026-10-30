/**
 * The AI path must not change: with saved keyword outputs (bench/keywords.ts),
 * this tree and another checkout send byte-identical match requests to Meta
 * (instructions, request, the cards and their order, schema). No model call:
 * the keyword call is answered from the saved file and the match call is
 * captured, then failed.
 *
 *   node bench/ai_path_same.ts <index.json> <needs.json> <keywords-en.json> <keywords-zh.json> <other worker/ dir> [--control]
 *
 * --control answers every keyword call with no keywords (the call failed), where
 * the rules scorer chooses the cards, so the requests are expected to differ.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const [indexPath, needsPath, kwEnPath, kwZhPath, otherDir, flag] = process.argv.slice(2);
const control = flag === '--control';
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
  return async (args: Record<string, unknown>, kw: string[]): Promise<{ match: string | null; keywordCall: boolean }> => {
    const h = helpers.harness((body: any) =>
      body.text.format.name === 'pickfit_keywords' ? helpers.metaResponse({ keywords: kw }) : new Response('{}', { status: 400 }),
    );
    h.deps.catalog = catalog;
    await find.findSoftware(args, h.deps);
    const match = h.requests.find((r: any) => r.body.text.format.name === 'pickfit_match');
    return { match: match ? String(match.init.body) : null, keywordCall: h.requests.some((r: any) => r.body.text.format.name === 'pickfit_keywords') };
  };
}

const [current, proposed] = [await version(otherDir), await version(join(import.meta.dirname, '..'))];
let compared = 0;
let withKeywords = 0;
let different = 0;
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
      }
    }
  }
}
console.log(`${compared} requests (${withKeywords} with a keyword call): ${different} match requests differ`);
