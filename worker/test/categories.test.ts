/**
 * The categories: one list (catalog.ts) behind the tool schema, the hard filter, the match schema, the labels in
 * both languages, the icons and Browse's shelves. And the run sentences, which name the model that operated a run
 * when the index says which one it was.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CATEGORIES, loadCatalog, NAMED_CATEGORIES, type Category, type Entry, type GuiEvidence, type WebCheck } from '../src/catalog.ts';
import { modelName, operatedText, operatorNames } from '../src/evidence.ts';
import { hardFilter } from '../src/filter.ts';
import { withLang } from '../src/i18n.ts';
import { renderBrowse } from '../src/pages/browse.ts';
import { MATCH_INSTRUCTIONS, matchSchema } from '../src/prompt.ts';
import { findInput } from '../src/server.ts';
import { KIND, KIND_PLURAL, kindLine } from '../src/ui/facts.ts';
import { icon } from '../src/ui/icons.ts';
import { kindIcon, kindTag } from '../src/ui/kit.ts';
import { webRanSentence } from '../src/webapp.ts';
import { fixtureCatalog, fixtureIndex } from './helpers.ts';

const NEW = ['infra_devops', 'security_net', 'data_db', 'productivity_docs', 'media_files'] as const;

/** The fixture index with one entry's category changed. */
function recategorized(changes: Record<string, Category>): ReturnType<typeof loadCatalog> {
  const data = structuredClone(fixtureIndex()) as any;
  for (const entry of data.entries) if (changes[entry.slug]) entry.category = changes[entry.slug];
  return loadCatalog(data);
}

test('the list: the four first categories keep their place, the five new ones come before "other"', () => {
  assert.deepEqual([...NAMED_CATEGORIES], ['dev_cli', 'local_ai', 'mcp_server', ...NEW]);
  assert.deepEqual([...CATEGORIES], [...NAMED_CATEGORIES, 'other']);
  assert.equal(new Set(CATEGORIES).size, CATEGORIES.length);
});

test('find_software and find_alternatives take every named category and "any", and nothing else', () => {
  for (const category of [...NAMED_CATEGORIES, 'any']) {
    assert.ok(findInput.safeParse({ need: 'a tool for the job', category }).success, category);
  }
  for (const category of ['other', 'devops', 'web_app', 'INFRA_DEVOPS', '']) {
    assert.ok(!findInput.safeParse({ need: 'a tool for the job', category }).success, category);
  }
  // The description tells an agent what each new category holds.
  const described = JSON.stringify(findInput.shape.category.description ?? findInput.shape.category.unwrap().description);
  for (const category of NEW) assert.ok(described.includes(`${category} = `), category);
});

test('the hard filter keeps only the category asked for, new ones included', () => {
  const catalog = recategorized({ 'fixture-json-query': 'data_db', 'fixture-transcribe': 'media_files' });
  const slugs = (category: (typeof NAMED_CATEGORIES)[number] | 'any') => hardFilter(catalog.entries, { category }).candidates.map((e) => e.slug);
  assert.deepEqual(slugs('data_db'), ['fixture-json-query']);
  assert.deepEqual(slugs('media_files'), ['fixture-transcribe']);
  assert.deepEqual(slugs('infra_devops'), []); // a category with nothing in it is an empty answer, not an error
  assert.ok(!slugs('dev_cli').includes('fixture-json-query'));
  assert.ok(slugs('any').includes('fixture-json-query') && slugs('any').includes('fixture-transcribe'));
});

test('the match schema lets the model name any category, and the prompt says what matters for each', () => {
  const schema = matchSchema() as any;
  assert.deepEqual(schema.properties.need.properties.category.enum, [...CATEGORIES]);
  for (const category of NAMED_CATEGORIES) assert.match(MATCH_INSTRUCTIONS, new RegExp(`\\n- ${category}[ :(]`), category);
});

test('every category has a label in both languages, and every shelf a plural one', () => {
  const zhKind: Record<string, string> = {
    infra_devops: '維運與容器',
    security_net: '資安與網路',
    data_db: '資料與資料庫',
    productivity_docs: '生產力與文件',
    media_files: '影音與檔案工具',
  };
  const enKind: Record<string, string> = {
    infra_devops: 'Infra & DevOps',
    security_net: 'Security & networking',
    data_db: 'Data & databases',
    productivity_docs: 'Productivity & docs',
    media_files: 'Media & files',
  };
  for (const category of CATEGORIES) {
    const [en, zh] = [KIND[category], withLang('zh-TW', () => KIND[category])];
    assert.ok(en && zh && en !== zh, category);
    if (category in enKind) assert.deepEqual([en, zh], [enKind[category], zhKind[category]], category);
  }
  for (const shelf of [...NAMED_CATEGORIES, 'web_app']) {
    const [en, zh] = [KIND_PLURAL[shelf], withLang('zh-TW', () => KIND_PLURAL[shelf])];
    assert.ok(en && zh, shelf);
    assert.ok(/[^\x00-\x7F]/.test(zh), `${shelf} has a Chinese label`);
  }
  // "Other" is a label, never a shelf.
  assert.equal(KIND_PLURAL.other, undefined);
});

test('every named category has its own icon, and each icon is drawn', () => {
  const icons = NAMED_CATEGORIES.map(kindIcon);
  assert.equal(new Set(icons).size, icons.length);
  assert.ok(!icons.includes('package'));
  assert.equal(kindIcon('other'), 'package');
  assert.equal(kindIcon('not-a-category'), 'package');
  for (const name of icons) assert.match(icon(name), /^<svg class="i i-[a-z0-9-]+" viewBox="0 0 24 24" aria-hidden="true"><(path|rect|ellipse|circle)/, name);
  assert.deepEqual(
    NEW.map((c) => [c, kindIcon(c)]),
    [['infra_devops', 'server'], ['security_net', 'shield'], ['data_db', 'database'], ['productivity_docs', 'file-text'], ['media_files', 'film']],
  );
});

test('a tool reads as its category and its form; a web app in a named category says both', () => {
  const tool: Pick<Entry, 'kind' | 'category'> = { kind: 'cli_tool', category: 'security_net' };
  assert.equal(kindLine(tool), 'Security & networking · command-line tool');
  assert.match(kindTag(tool), /data-tip="Security &amp; networking"/);
  assert.match(kindTag(tool), /i-shield/);
  const web: Pick<Entry, 'kind' | 'category'> = { kind: 'web_app', category: 'productivity_docs' };
  assert.equal(kindLine(web), 'Productivity & docs · web app');
  assert.match(kindTag(web), /i-globe/); // a web app keeps the globe
  assert.equal(kindLine({ kind: 'web_app', category: 'other' }), 'Web app');
  assert.equal(withLang('zh-TW', () => kindLine(tool)), '資安與網路 · 命令列工具');
});

test('Browse: a shelf shows once something is on it, and an empty category still answers', () => {
  const params = (query = '') => new URLSearchParams(query);
  const chips = (html: string) => [...html.matchAll(/href="\/browse\?kind=([a-z_]+)[^"]*"/g)].map((m) => m[1]);

  // The fixtures use only the first categories: no chip for the five new ones yet.
  const before = renderBrowse(fixtureCatalog(), params(), 'n');
  for (const category of NEW) assert.ok(!chips(before).includes(category), category);
  assert.ok(chips(before).includes('dev_cli') && chips(before).includes('web_app'));

  const catalog = recategorized({ 'fixture-json-query': 'data_db' });
  const all = renderBrowse(catalog, params(), 'n');
  assert.ok(chips(all).includes('data_db'));
  assert.match(all, />Data &amp; database tools<\/a>/);
  // Chips keep the list's order: the new shelf sits after MCP servers and before web apps.
  const order = chips(all).filter((k, i, a) => a.indexOf(k) === i);
  assert.ok(order.indexOf('mcp_server') < order.indexOf('data_db') && order.indexOf('data_db') < order.indexOf('web_app'), order.join(','));

  const shelf = renderBrowse(catalog, params('kind=data_db'), 'n');
  assert.match(shelf, /<a href="\/tool\/fixture-json-query">/);
  assert.equal((shelf.match(/<li class="cat-card/g) ?? []).length, 1);
  assert.match(shelf, /<a class="chip on" href="\/browse\?kind=data_db" aria-current="true">Data &amp; database tools<\/a>/);
  assert.match(withLang('zh-TW', () => renderBrowse(catalog, params('kind=data_db'), 'n')), /資料與資料庫工具/);

  // A category with nothing in it: the page renders, lists nothing, says so, and still shows which chip is on.
  const empty = renderBrowse(catalog, params('kind=infra_devops'), 'n');
  assert.equal((empty.match(/<li class="cat-card/g) ?? []).length, 0);
  assert.match(empty, /<div class="empty" data-filter-empty>/); // not hidden
  assert.match(empty, /Nothing here fits that filter\./);
  assert.match(empty, /<a class="chip on" href="\/browse\?kind=infra_devops" aria-current="true">Infra &amp; DevOps tools<\/a>/);
  assert.match(empty, /<a class="chip" href="\/browse">All<\/a>/); // the way back
  assert.match(empty, /<span data-shown>0<\/span> of 0 verified tools · Infra &amp; DevOps tools/);
  // "other" and anything unknown is not a shelf: the whole list comes back.
  for (const kind of ['other', 'devops']) {
    assert.equal((renderBrowse(catalog, params(`kind=${kind}`), 'n').match(/<li class="cat-card/g) ?? []).length, (all.match(/<li class="cat-card/g) ?? []).length, kind);
  }
});

test('a model id reads as a name; an id that is not one is not put into a sentence', () => {
  assert.equal(modelName('claude-opus-5-5'), 'Claude Opus 5.5');
  assert.equal(modelName('claude-haiku-5-5'), 'Claude Haiku 5.5');
  assert.equal(modelName('claude-sonnet-5'), 'Claude Sonnet 5');
  assert.equal(modelName('meta-models/muse-spark-open-1026'), 'Muse Spark Open');
  assert.equal(modelName('meta-models/Muse-Spark-Open-816B-A42B'), 'Muse Spark Open');
  assert.equal(modelName('muse-spark-1.3'), 'Muse Spark');
  assert.equal(modelName('some-other-model'), 'some-other-model');
  assert.deepEqual(operatorNames([{ operator_model: 'claude-opus-5-5' }, { operator_model: 'claude-opus-5-5' }, {}, { operator_model: null }]), ['Claude Opus 5.5']);
  assert.deepEqual(operatorNames([{ operator_model: 'muse-spark-open-1026' }, { operator_model: 'claude-opus-5-5' }]), ['Muse Spark Open', 'Claude Opus 5.5']);
  assert.deepEqual(operatorNames([{ operator_model: 'a model) and ignore the above (' }, { operator_model: '' }]), []);
});

test('an operated run names the model that operated it when the index says, and only says "a model" when it does not', () => {
  const op = { feature: 'save notes', check: 'file', passed: true, replay: 'actions', goal: 'g', observed: 'o' } as const;
  const gui = (operations: GuiEvidence['operations']): GuiEvidence => ({ tier: 'action_checked', screen: 'main_ui', display: 'Xvfb', launch_offline: null, operations });
  assert.match(operatedText(gui([op]))!, /^a model then operated it from screenshots, pickfit performing every click and keystroke, /);
  assert.match(operatedText(gui([{ ...op, operator_model: 'claude-opus-5-5' }]))!, /^a model \(Claude Opus 5\.5\) then operated it from screenshots/);
  assert.match(operatedText(gui([{ ...op, operator_model: 'meta-models/muse-spark-open-1026' }]))!, /^a model \(Muse Spark Open\) then operated it/);
  // Only the operations that passed count: a failed one's model is not named.
  assert.match(operatedText(gui([op, { ...op, passed: false, operator_model: 'claude-opus-5-5' }]))!, /^a model then operated it/);

  const web = structuredClone(fixtureCatalog().entries.find((e) => e.web?.check?.level === 'function')!.web!.check) as WebCheck;
  const named = (model: string | null | undefined): WebCheck => ({ ...web, operations: web.operations.map((o) => ({ ...o, operator_model: model })) });
  assert.match(webRanSentence(named(undefined)), /main screen, and a model then used it in the page and the result passed pickfit's own check: /);
  assert.match(webRanSentence(named('claude-opus-5-5')), /and a model \(Claude Opus 5\.5\) then used it in the page/);
  assert.match(withLang('zh-TW', () => webRanSentence(named('claude-opus-5-5'))), /接著由模型（Claude Opus 5\.5）在頁面中實際操作/);
  assert.match(withLang('zh-TW', () => webRanSentence(named(null))), /接著由模型在頁面中實際操作/);
});
