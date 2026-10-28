import assert from 'node:assert/strict';
import { test } from 'node:test';
import { findSoftware, type FindInput } from '../src/find.ts';
import { MATCH_MODEL } from '../src/meta.ts';
import { answer, harness, metaResponse } from './helpers.ts';

const MAC_OFFLINE: FindInput = {
  need: '我想要一個 Mac 上、免費、能離線跑本地 LLM 的工具 (secret-project-xyz)',
  os: 'macos',
  budget: 'free_only',
  must_run_locally: true,
};

test('model path: picks come from muse-spark-1.3 and are checked against the cards', async () => {
  const h = harness(() => metaResponse(answer()));
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  await h.settle();

  assert.equal(out.matched_by, MATCH_MODEL);
  assert.equal(out.degraded, false);
  assert.equal(out.degraded_reason, null);
  assert.match(out.rec_id, /^rec_[0-9a-f]{32}$/);
  assert.deepEqual(out.picks.map((p) => p.slug), ['fixture-llm-runner', 'fixture-chat-tui']);
  assert.equal(out.considered, 4); // cloud-summarize fails free_only and must_run_locally

  const [runner, chat] = out.picks;
  assert.equal(runner.why.length, 2);
  assert.equal(runner.verification.os, 'macos');
  assert.equal(runner.verification.method, 'human');
  assert.equal(runner.verification.verified_on_user_os, true);
  assert.match(runner.how_we_know, /installed it by hand on macos\/arm64/);
  assert.match(runner.how_we_know, /Chosen by muse-spark-1\.3 among 4 tools/);
  assert.equal(runner.evidence_url, 'https://example.invalid/runs/run-20261028-macos-1');
  assert.deepEqual(runner.scores, { quality: 84, popularity: 12, treasure: true });
  // Verified only on Linux: the response says so even though the model did not.
  assert.equal(chat.verification.verified_on_user_os, false);
  assert.match(chat.tradeoffs[0], /Verified on linux only/);
  assert.deepEqual(out.best_free, { slug: 'fixture-llm-runner', reason: 'Free, open source and runs offline.' });
});

test('the request uses muse-spark-1.3, store false, low effort and a strict schema limited to the candidates', async () => {
  const h = harness(() => metaResponse(answer()));
  await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 1);
  const { url, init, body } = h.requests[0];
  assert.equal(url, 'https://api.meta.ai/v1/responses');
  assert.equal((init.headers as Record<string, string>).authorization, 'Bearer test-key');
  assert.equal(body.model, 'muse-spark-1.3');
  assert.equal(body.store, false);
  assert.deepEqual(body.reasoning, { effort: 'low' });
  assert.equal(body.text.format.type, 'json_schema');
  assert.equal(body.text.format.strict, true);
  const slugEnum = body.text.format.schema.properties.picks.items.properties.slug.enum;
  assert.deepEqual(slugEnum, ['fixture-chat-tui', 'fixture-json-query', 'fixture-llm-runner', 'fixture-transcribe']);
  // The user's words go to the model inside <request>, as data.
  assert.match(body.input[1].content, /<request>\n.*secret-project-xyz.*\n<\/request>/);
});

test('D1 keeps parsed conditions and spend, never the request text', async () => {
  const h = harness(() => metaResponse(answer()));
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  await h.settle();
  const row = h.sqlite.prepare('SELECT * FROM events WHERE type = ?').get('find') as any;
  assert.equal(row.rec_id, out.rec_id);
  assert.equal(row.matched_by, 'muse-spark-1.3');
  assert.equal(row.degraded, 0);
  assert.deepEqual(JSON.parse(row.results), ['fixture-llm-runner', 'fixture-chat-tui']);
  const need = JSON.parse(row.need);
  assert.equal(need.parsed.task, 'run a small language model offline');
  assert.equal(need.given.os, 'macos');
  const everything = JSON.stringify(h.sqlite.prepare('SELECT * FROM events').all());
  assert.ok(!everything.includes('secret-project-xyz'));
  assert.ok(!everything.includes('本地'));
  // 2000 uncached input, 1000 cached, 800 output tokens at muse-spark-1.3 prices.
  const expected = (2000 * 1.25 + 1000 * 0.15 + 800 * 4.25) / 1e6;
  const budget = h.sqlite.prepare('SELECT * FROM meta_budget').get() as any;
  assert.equal(budget.day, '2026-10-30');
  assert.equal(budget.calls, 1);
  assert.ok(Math.abs(budget.cost_usd - expected) < 1e-12);
  assert.ok(Math.abs(row.meta_cost_usd - expected) < 1e-12);
});

test('guard drops reasons that do not match their field and picks left without reasons', async () => {
  const h = harness(() =>
    metaResponse(
      answer({
        picks: [
          {
            slug: 'fixture-transcribe',
            fit: 'Transcribes audio offline.',
            reasons: [
              { claim: 'Verified on macOS', field: 'verified_on', value: 'linux x86_64' }, // claim contradicts the card
              { claim: 'GPL licensed', field: 'license', value: 'GPL-3.0' }, // value is not on the card
              { claim: 'Transcribes recordings', field: 'use_cases', value: 'transcribe a wav or mp3 file offline' },
            ],
            tradeoffs: [],
            vs_well_known: null,
          },
          {
            slug: 'fixture-json-query',
            fit: 'Queries JSON.',
            reasons: [{ claim: 'Has a GUI', field: 'kind', value: 'desktop_app' }],
            tradeoffs: [],
            vs_well_known: null,
          },
          {
            slug: 'not-a-candidate',
            fit: 'x',
            reasons: [{ claim: 'Free to use', field: 'pricing', value: 'free' }],
            tradeoffs: [],
            vs_well_known: null,
          },
        ],
        best_free_slug: 'fixture-transcribe',
      }),
    ),
  );
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(out.matched_by, MATCH_MODEL);
  assert.deepEqual(out.picks.map((p) => p.slug), ['fixture-transcribe']);
  assert.deepEqual(out.picks[0].why.map((r) => r.field), ['use_cases']);
});

test('a fit sentence that contradicts the card is replaced by the summary', async () => {
  const h = harness(() =>
    metaResponse(
      answer({
        picks: [
          {
            slug: 'fixture-chat-tui',
            fit: 'Closed-source but tested on macOS by pickfit.',
            reasons: [{ claim: 'Free to use', field: 'pricing', value: 'free' }],
            tradeoffs: [],
            vs_well_known: null,
          },
        ],
      }),
    ),
  );
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.match(out.picks[0].fit, /^\(Fake test fixture\) Terminal chat client/);
});

test('every pick rejected by the guard falls back to rules', async () => {
  const bad = answer({
    picks: [
      {
        slug: 'fixture-llm-runner',
        fit: 'x',
        reasons: [{ claim: 'Paid enterprise tool', field: 'pricing', value: 'paid' }],
        tradeoffs: [],
        vs_well_known: null,
      },
    ],
  });
  const h = harness(() => metaResponse(bad));
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  await h.settle();
  assert.equal(out.matched_by, 'rules');
  assert.equal(out.degraded, true);
  assert.equal(out.degraded_reason, 'guard_rejected_all');
  assert.ok(out.picks.length > 0);
  // The failed call was still paid for and counted.
  assert.equal((h.sqlite.prepare('SELECT calls FROM meta_budget').get() as any).calls, 1);
});

const failures: [string, () => Response | Promise<Response>, string][] = [
  ['HTTP 500', () => Response.json({ error: { code: 'internal' } }, { status: 500 }), 'model_http'],
  ['incomplete answer', () => metaResponse(answer(), { status: 'incomplete' }), 'model_incomplete'],
  ['not JSON', () => metaResponse('this is not json'), 'model_bad_output'],
  ['wrong shape', () => metaResponse({ picks: 'none' }), 'model_bad_output'],
];
for (const [label, fake, reason] of failures) {
  test(`model failure (${label}) degrades to rules`, async () => {
    const h = harness(fake);
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    assert.equal(out.matched_by, 'rules');
    assert.equal(out.degraded, true);
    assert.equal(out.degraded_reason, reason);
    assert.ok(out.picks.length >= 2);
    assert.match(out.picks[0].how_we_know, /Ranked by rules/);
  });
}

test('a timeout degrades to rules and charges the worst-case cost', async () => {
  const h = harness(
    () => new Promise<Response>(() => undefined), // never answers
    { timeoutMs: 50 },
  );
  // The fake ignores the abort signal, so race it the way fetch would.
  const original = h.deps.fetch!;
  h.deps.fetch = ((url: string, init: RequestInit) =>
    Promise.race([
      original(url, init),
      new Promise<Response>((_, reject) =>
        init.signal!.addEventListener('abort', () => reject(init.signal!.reason)),
      ),
    ])) as typeof fetch;
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  await h.settle();
  assert.equal(out.degraded_reason, 'model_timeout');
  const budget = h.sqlite.prepare('SELECT * FROM meta_budget').get() as any;
  assert.ok(budget.cost_usd > 0.01);
});

test('MATCH_MODE off and a missing key never call Meta', async () => {
  for (const [settings, reason] of [
    [{ modelEnabled: false }, 'model_off'],
    [{ apiKey: null }, 'no_api_key'],
  ] as const) {
    const h = harness(null, settings);
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    await h.settle();
    assert.equal(h.requests.length, 0);
    assert.equal(out.matched_by, 'rules');
    assert.equal(out.degraded_reason, reason);
    assert.equal(h.sqlite.prepare('SELECT count(*) AS n FROM meta_budget').get()!.n, 0);
  }
});

test('the daily cap and the total cap stop the model call', async () => {
  for (const rows of [
    [['2026-10-30', 2.99]], // today is nearly at $3
    [['2026-10-20', 20], ['2026-10-25', 19.99]], // $40 total reached on earlier days
  ]) {
    const h = harness(null);
    for (const [day, cost] of rows) {
      h.sqlite.prepare('INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?, 1, ?)').run(day, cost);
    }
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    assert.equal(h.requests.length, 0);
    assert.equal(out.degraded_reason, 'over_budget');
    assert.equal(out.matched_by, 'rules');
  }
});

test('rules ranking puts request keywords and verification on the user OS first', async () => {
  const h = harness(null, { modelEnabled: false });
  const out = await findSoftware(
    { need: 'run a small language model offline with an OpenAI API', os: 'macos', limit: 2 },
    h.deps,
  );
  assert.equal(out.picks[0].slug, 'fixture-llm-runner');
  assert.equal(out.picks.length, 2);
  assert.ok(out.picks.every((p) => p.why.length > 0));
  assert.equal(out.best_free?.slug, 'fixture-llm-runner');
  assert.equal(out.clarifying_question, null);
});

test('rules ask for the OS when it is unknown and the picks differ', async () => {
  const h = harness(null, { modelEnabled: false });
  const out = await findSoftware({ need: 'query json in the terminal' }, h.deps);
  assert.equal(out.picks[0].slug, 'fixture-json-query');
  assert.match(out.clarifying_question ?? '', /Which OS/);
});

test('no candidate after the hard filters: no model call, an honest note', async () => {
  const h = harness(null);
  const out = await findSoftware(
    // Only fixture-chat-tui claims Windows among the local AI tools.
    { need: 'local transcription', os: 'windows', category: 'local_ai', exclude: ['fixture-chat-tui'] },
    h.deps,
  );
  assert.equal(h.requests.length, 0);
  assert.deepEqual(out.picks, []);
  assert.equal(out.degraded, false);
  assert.match(out.coverage_note ?? '', /No verified tool/);
});

test('the model may honestly answer that nothing fits', async () => {
  const h = harness(() => metaResponse(answer({ picks: [], best_free_slug: null })));
  const out = await findSoftware({ need: 'edit videos with a timeline', os: 'linux' }, h.deps);
  assert.equal(out.matched_by, MATCH_MODEL);
  assert.deepEqual(out.picks, []);
  assert.match(out.coverage_note ?? '', /None of the 5 verified tools/);
});

test('best_free must be a free candidate', async () => {
  const h = harness(() => metaResponse(answer({ best_free_slug: 'fixture-cloud-summarize' })));
  const out = await findSoftware({ need: 'summarize a git diff', os: 'linux' }, h.deps);
  assert.equal(out.best_free, null);
});

test('exclude and limit are honoured', async () => {
  const h = harness(null, { modelEnabled: false });
  const out = await findSoftware(
    { need: 'local language model', os: 'linux', exclude: ['fixture-llm-runner'], limit: 1 },
    h.deps,
  );
  assert.equal(out.picks.length, 1);
  assert.notEqual(out.picks[0].slug, 'fixture-llm-runner');
});
