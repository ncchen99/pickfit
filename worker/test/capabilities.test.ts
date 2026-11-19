/**
 * Documented capabilities (docs/proposals/capabilities.md steps 5 and 7), on synthetic data: no record has
 * them yet, so each test adds them to a copy of the fixture index. They help a tool be found and be cited
 * for a job its docs name, they are marked as not tested, and the page folds them away from the features.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CAPABILITIES_SHOWN, matchedCapabilities } from '../src/capabilities.ts';
import { CARD_FIELDS, toCard } from '../src/cards.ts';
import { capabilityTexts, loadCatalog, type Capability, type Catalog, type Entry } from '../src/catalog.ts';
import { findSoftware } from '../src/find.ts';
import { fitOf, jobOf } from '../src/fit.ts';
import { translateWith, withLang } from '../src/i18n.ts';
import { renderTool } from '../src/pages/tool.ts';
import { reasonHolds } from '../src/guard.ts';
import { MATCH_INSTRUCTIONS } from '../src/prompt.ts';
import { queryTerms, relevance } from '../src/relevance.ts';
import { answer, fixtureIndex, harness, isKeywordsCall, modelResponse, schemaOf } from './helpers.ts';

const FORMATS: Capability = { label: 'convert JSON to other formats', items: ['csv', 'yaml', 'toml'] };
const COLOR: Capability = { label: 'color output in the terminal' };

/** The fixture catalog with capabilities on some entries. */
function withCapabilities(caps: Record<string, Capability[]>, edit: (entries: any[]) => void = () => {}): Catalog {
  const data = structuredClone(fixtureIndex()) as any;
  for (const entry of data.entries) if (caps[entry.slug]) entry.capabilities = caps[entry.slug];
  edit(data.entries);
  return loadCatalog(data);
}

const entryOf = (catalog: Catalog, slug: string): Entry => catalog.bySlug.get(slug)!;

test('a capability is matched by a specific word of its label or by a listed item, and shown with the items asked', () => {
  const entry = entryOf(withCapabilities({ 'fixture-json-query': [COLOR, FORMATS] }), 'fixture-json-query');
  assert.deepEqual(matchedCapabilities(entry, queryTerms('convert a TOML config to YAML')), [
    'convert JSON to other formats (yaml, toml)',
  ]);
  assert.deepEqual(matchedCapabilities(entry, queryTerms('colorful JSON')), ['convert JSON to other formats']); // json, in the label
  assert.deepEqual(matchedCapabilities(entry, queryTerms('a terminal tool')), []); // generic words name nothing
  assert.deepEqual(matchedCapabilities(entry, []), []);
  assert.deepEqual(capabilityTexts(entry), ['color output in the terminal', 'convert JSON to other formats', 'csv', 'yaml', 'toml']);
});

test('a card shows at most five matched capabilities, the ones naming more of the request first', () => {
  const many = Array.from({ length: 8 }, (_, i) => ({ label: `export reports as format${i}` }));
  const entry = entryOf(withCapabilities({ 'fixture-json-query': [...many, FORMATS] }), 'fixture-json-query');
  const shown = matchedCapabilities(entry, queryTerms('export as yaml'));
  assert.equal(shown.length, CAPABILITIES_SHOWN);
  assert.equal(shown[0], 'convert JSON to other formats (yaml)'); // an item counts twice a label word
});

test('the card field appears only when the request names a capability, and a reason may cite it', () => {
  const catalog = withCapabilities({ 'fixture-json-query': [FORMATS] });
  const entry = entryOf(catalog, 'fixture-json-query');
  assert.equal('capabilities_matched' in toCard(entry), false);
  assert.equal('capabilities_matched' in toCard(entry, undefined, undefined, queryTerms('summarize a git diff')), false);
  const card = toCard(entry, undefined, undefined, queryTerms('turn a csv file into JSON'));
  assert.deepEqual(card.capabilities_matched, ['convert JSON to other formats (csv)']);
  assert.ok((CARD_FIELDS as readonly string[]).includes('capabilities_matched'));
  assert.equal(reasonHolds(card, { claim: 'Converts CSV', field: 'capabilities_matched', value: 'convert JSON to other formats (csv)' }), true);
  assert.equal(reasonHolds(card, { claim: 'Converts XML', field: 'capabilities_matched', value: 'convert XML' }), false);
});

test('capabilities and features count in relevance, a capability half as much as a feature', () => {
  const plain = withCapabilities({});
  const query = queryTerms('epub');
  const score = (catalog: Catalog) => relevance(catalog.entries, catalog.entries, query).get('fixture-json-query')!;
  assert.equal(score(plain), 0);
  const asCapability = withCapabilities({ 'fixture-json-query': [{ label: 'write epub books' }] });
  const asFeature = withCapabilities({}, (entries) => {
    entries.find((e) => e.slug === 'fixture-json-query').features = ['write epub books'];
  });
  assert.ok(score(asCapability) > 0);
  assert.ok(score(asFeature) > score(asCapability));
});

test('the rules fit label reads the features but not the documented capabilities', () => {
  const job = 'convert a TOML config to YAML';
  const documented = withCapabilities({ 'fixture-json-query': [FORMATS] });
  const asFeature = withCapabilities({}, (entries) => {
    entries.find((e) => e.slug === 'fixture-json-query').features = ['convert JSON to YAML or TOML'];
  });
  // A job only the docs name is not "covered": the label stays as cautious as without them (BM25 still shortlists it).
  const withCaps = fitOf(entryOf(documented, 'fixture-json-query'), jobOf(documented.entries, job));
  assert.ok(!withCaps.covers.includes('yaml') && withCaps.missing.includes('yaml'));
  const withFeature = fitOf(entryOf(asFeature, 'fixture-json-query'), jobOf(asFeature.entries, job));
  assert.ok(withFeature.covers.includes('yaml'));
});

test('rules only: the pick says its docs claim the job and that pickfit did not test it', async () => {
  const h = harness(null, { modelEnabled: false });
  h.deps.catalog = withCapabilities({ 'fixture-json-query': [FORMATS] });
  const out: any = await findSoftware({ need: 'convert a TOML config to YAML', category: 'dev_cli' }, h.deps);
  const pick = out.picks.find((p: any) => p.slug === 'fixture-json-query');
  assert.ok(pick);
  const cited = pick.why.find((r: any) => r.field === 'capabilities_matched');
  assert.deepEqual(cited && [cited.value, /not tested by pickfit/.test(cited.claim)], ['convert JSON to other formats (yaml, toml)', true]);
});

test('the model sees capabilities_matched on the card, may cite it, and is told to say it was not tested', async () => {
  let sent: any = null;
  const reply = answer({
    need: { ...answer().need, task: 'convert a toml file to yaml', category: 'dev_cli', os: null, must_run_locally: false },
    picks: [
      {
        slug: 'fixture-json-query',
        fit: 'Its docs say it converts JSON to YAML and TOML.',
        reasons: [{ claim: 'Its docs list YAML and TOML output', field: 'capabilities_matched', value: 'convert JSON to other formats (yaml, toml)' }],
        tradeoffs: ['pickfit did not test the conversion'],
        vs_well_known: null,
      },
    ],
  } as any);
  const h = harness((body) => {
    if (isKeywordsCall(body)) return modelResponse({ keywords: [] });
    sent = body;
    return modelResponse(reply);
  });
  h.deps.catalog = withCapabilities({ 'fixture-json-query': [FORMATS] });
  const out: any = await findSoftware({ need: 'convert a TOML config to YAML', category: 'dev_cli' }, h.deps);
  const text = JSON.stringify(sent.messages);
  assert.match(text, /capabilities_matched/);
  assert.match(text, /convert JSON to other formats \(yaml, toml\)/);
  assert.ok(schemaOf(sent).properties.picks.items.properties.reasons.items.properties.field.enum.includes('capabilities_matched'));
  assert.match(MATCH_INSTRUCTIONS, /capabilities_matched[^.]*documentation/);
  assert.match(MATCH_INSTRUCTIONS, /only capabilities_matched covers \(its docs say it does this; pickfit did not test it\)/);
  assert.equal(out.picks[0].slug, 'fixture-json-query');
  assert.equal(out.picks[0].why[0].field, 'capabilities_matched'); // the guard kept it
});

test('the tool page folds the documented capabilities away from the tested features', () => {
  const catalog = withCapabilities({ 'fixture-transcribe': [FORMATS, COLOR] });
  const entry = entryOf(catalog, 'fixture-transcribe');
  const html = renderTool(catalog, entry, 'n0nce');
  const at = html.indexOf('<details class="more-caps">');
  assert.ok(at > html.indexOf('class="feat-list"'), 'after the feature list');
  assert.match(html, /More it can do, from its docs \(2\)/);
  assert.match(html, /didn’t test these one by one/);
  assert.match(html, /<span class="cap-label">Convert JSON to other formats<\/span> <span class="cap-items">csv, yaml(,| and) toml<\/span>/);
  assert.doesNotMatch(renderTool(catalog, entryOf(catalog, 'fixture-chat-tui'), 'n0nce'), /<details class="more-caps">/);
  const zh = withLang('zh-TW', () =>
    renderTool(catalog, translateWith({ 'convert JSON to other formats': '把 JSON 轉成其他格式', csv: 'CSV 檔' }, entry), 'n0nce'),
  );
  assert.match(zh, /文件寫的其他功能（2 項）/);
  assert.match(zh, /把 JSON 轉成其他格式/);
  assert.doesNotMatch(zh, /CSV 檔/); // items are formats and names: never translated
});
