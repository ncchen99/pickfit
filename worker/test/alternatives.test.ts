import assert from 'node:assert/strict';
import { test } from 'node:test';
import { findAlternatives, matchCurrent, type AlternativesInput } from '../src/find.ts';
import { MATCH_MODEL } from '../src/meta.ts';
import { ALTERNATIVES_RULES, MATCH_INSTRUCTIONS } from '../src/prompt.ts';
import { answer, harness, metaResponse } from './helpers.ts';

const REPLACE_OLLAMA: AlternativesInput = {
  current_software: 'Ollama',
  pain_points: 'too heavy for my old laptop, I only need an API endpoint (private-codename-qq)',
  must_keep: ['OpenAI-compatible API'],
  os: 'linux',
};

const altAnswer = (keep = { recommended: false, reason: 'The runner is lighter and keeps the OpenAI API.' }) =>
  answer({
    need: {
      task: 'serve a local language model over an API',
      category: 'local_ai',
      os: 'linux',
      budget: 'unknown',
      must_run_locally: null,
      must_have: ['OpenAI-compatible API'],
      search_terms: ['local llm server'],
      current_tool: 'Ollama',
      pain_points: ['too heavy on old hardware'],
    },
    picks: [
      {
        slug: 'fixture-llm-runner',
        fit: 'Lighter than the current tool and still serves an OpenAI-compatible API.',
        reasons: [{ claim: 'Runs offline on your machine', field: 'processing', value: 'local' }],
        tradeoffs: ['Needs 8 GB of RAM'],
        vs_well_known: 'Better than Ollama when you only need the API.',
      },
    ],
    keep_current: keep,
  });

test('model path: the request carries the current tool and pain points; the schema adds keep_current', async () => {
  const h = harness(() => metaResponse(altAnswer()));
  const out = await findAlternatives(REPLACE_OLLAMA, h.deps);
  await h.settle();

  assert.equal(out.matched_by, MATCH_MODEL);
  assert.equal(out.degraded, false);
  assert.deepEqual(out.picks.map((p) => p.slug), ['fixture-llm-runner']);
  assert.deepEqual(out.keep_current, { recommended: false, reason: 'The runner is lighter and keeps the OpenAI API.' });
  // Ollama is not in the catalog, but a profile names it as an alternative.
  assert.deepEqual(out.current, { matched_slug: null, known: true });
  assert.match(out.picks[0].how_we_know, /Chosen by muse-spark-1\.3/);
  assert.equal(out.picks[0].evidence_url, 'https://example.invalid/runs/run-20261028-linux-1');

  const { body } = h.requests[0];
  assert.equal(body.model, 'muse-spark-1.3');
  assert.equal(body.store, false);
  assert.equal(body.input[0].content, MATCH_INSTRUCTIONS.replace('{limit}', '3') + ALTERNATIVES_RULES);
  assert.match(body.input[1].content, /<request>\n\{"current_software":"Ollama","pain_points":"too heavy.*"must_keep":\["OpenAI-compatible API"\]/);
  assert.equal(body.text.format.name, 'pickfit_alternatives');
  const schema = body.text.format.schema;
  assert.deepEqual(schema.properties.keep_current.required, ['recommended', 'reason']);
  assert.ok(schema.required.includes('keep_current'));
  assert.ok(schema.properties.need.required.includes('pain_points'));
});

test('find_software keeps its own prompt and schema', async () => {
  const h = harness(() => metaResponse(answer()));
  const { findSoftware } = await import('../src/find.ts');
  await findSoftware({ need: 'run a model offline', os: 'macos' }, h.deps);
  const { body } = h.requests[0];
  assert.equal(body.input[0].content, MATCH_INSTRUCTIONS.replace('{limit}', '3'));
  assert.equal(body.text.format.name, 'pickfit_match');
  assert.equal(body.text.format.schema.properties.keep_current, undefined);
  assert.equal(body.text.format.schema.properties.need.properties.pain_points, undefined);
});

test('the model may advise keeping the current tool', async () => {
  const keep = { recommended: true, reason: 'None of these is lighter while keeping the API.' };
  const h = harness(() => metaResponse(altAnswer(keep)));
  const out = await findAlternatives(REPLACE_OLLAMA, h.deps);
  assert.deepEqual(out.keep_current, keep);
});

test('a current tool that pickfit lists is never among the candidates', async () => {
  const h = harness(() => metaResponse(altAnswer()));
  const out = await findAlternatives(
    { current_software: 'Fixture LLM Runner', pain_points: 'crashes on large models', os: 'linux' },
    h.deps,
  );
  assert.deepEqual(out.current, { matched_slug: 'fixture-llm-runner', known: true });
  const slugEnum = h.requests[0].body.text.format.schema.properties.picks.items.properties.slug.enum;
  assert.ok(!slugEnum.includes('fixture-llm-runner'));
  // The model named it anyway: the guard drops it, and with no pick left the rules take over.
  assert.equal(out.degraded_reason, 'guard_rejected_all');
  assert.ok(out.picks.every((p) => p.slug !== 'fixture-llm-runner'));
});

test('rules fallback: ranks profiles that name the current tool first and does not judge keep_current', async () => {
  const h = harness(null, { modelEnabled: false });
  const out = await findAlternatives(
    { current_software: 'jq', pain_points: 'the filter syntax is hard to remember', os: 'linux', limit: 1 },
    h.deps,
  );
  assert.equal(out.matched_by, 'rules');
  assert.equal(out.degraded, true);
  assert.deepEqual(out.picks.map((p) => p.slug), ['fixture-json-query']);
  assert.equal(out.keep_current, null);
  assert.deepEqual(out.current, { matched_slug: null, known: true });
});

test('D1 keeps the kind, parsed conditions and the catalog match, never the request text', async () => {
  const h = harness(() => metaResponse(altAnswer()));
  const out = await findAlternatives(REPLACE_OLLAMA, h.deps);
  await h.settle();
  const row = h.sqlite.prepare('SELECT * FROM events').get() as any;
  assert.equal(row.type, 'alternatives');
  assert.equal(row.rec_id, out.rec_id);
  const need = JSON.parse(row.need);
  assert.deepEqual(need.parsed.pain_points, ['too heavy on old hardware']);
  assert.equal(need.parsed.current_tool, 'Ollama');
  assert.deepEqual(need.current, { matched_slug: null, known: true });
  const everything = JSON.stringify(h.sqlite.prepare('SELECT * FROM events').all());
  assert.ok(!everything.includes('private-codename-qq'));
  assert.ok(!everything.includes('old laptop'));
});

test('matchCurrent ignores case, spaces and punctuation', () => {
  const { catalog } = harness(null).deps;
  assert.equal(matchCurrent(catalog, 'fixture-json-query').matched_slug, 'fixture-json-query');
  assert.equal(matchCurrent(catalog, 'Fixture JSON-Query').matched_slug, 'fixture-json-query');
  assert.deepEqual(matchCurrent(catalog, 'LM Studio'), { matched_slug: null, known: true });
  assert.deepEqual(matchCurrent(catalog, 'Something Else'), { matched_slug: null, known: false });
  assert.deepEqual(matchCurrent(catalog, '記事本'), { matched_slug: null, known: false });
});
