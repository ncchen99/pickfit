import assert from 'node:assert/strict';
import { test } from 'node:test';
import { findSoftware, type FindInput } from '../src/find.ts';
import { costUsd, estimateCostUsd, MATCH_MODEL } from '../src/meta.ts';
import { MATCH_INSTRUCTIONS } from '../src/prompt.ts';
import { answer, harness, modelResponse, sentSlugs, systemText } from './helpers.ts';

const MAC_OFFLINE: FindInput = {
  // "chat": the install-level chat TUI fits best, so it comes in as P2-01's fallback (filter.ts strictPool).
  need: '我想要一個 Mac 上、免費、能離線跑本地 LLM 的 chat 工具 (secret-project-xyz)',
  os: 'macos',
  budget: 'free_only',
  must_run_locally: true,
};

test('model path: picks come from claude-opus-5-5 and are checked against the cards', async () => {
  const h = harness(() => modelResponse(answer()));
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  await h.settle();

  assert.equal(out.matched_by, MATCH_MODEL);
  assert.equal(out.degraded, false);
  assert.equal(out.degraded_reason, null);
  assert.match(out.rec_id, /^rec_[0-9a-f]{32}$/);
  assert.deepEqual(out.picks.map((p) => p.slug), ['fixture-llm-runner', 'fixture-chat-tui']);
  assert.equal(out.considered, 5); // cloud-summarize fails free_only and must_run_locally; the web app is an offline-checked PWA

  const [runner, chat] = out.picks;
  assert.equal(runner.why.length, 2);
  assert.equal(runner.verification.os, 'macos');
  assert.equal(runner.verification.method, 'human');
  assert.equal(runner.verification.verified_on_user_os, true);
  assert.match(runner.how_we_know, /installed it by hand on macos\/arm64/);
  assert.match(runner.how_we_know, /Chosen by claude-opus-5-5 among 5 tools/);
  assert.equal(runner.evidence_url, 'https://example.invalid/runs/run-20261028-macos-1');
  assert.deepEqual(runner.scores, { quality: 84, popularity: 12, treasure: true });
  // Install-level (P2-01) and verified only on Linux: the response says both even though the model did not, the
  // install-only note first.
  assert.equal(chat.verification.verified_on_user_os, false);
  assert.equal(chat.tradeoffs[0], 'pickfit only confirmed it installs; its core features have not been verified yet.');
  assert.match(chat.tradeoffs[1], /Verified on linux only/);
  assert.deepEqual(runner.tradeoffs, ['Needs 8 GB of RAM']); // function level: no such note
  assert.match(out.coverage_note ?? '', /tools it only installed are included/);
  assert.deepEqual(out.best_free, { slug: 'fixture-llm-runner', reason: 'Free, open source and runs offline.' });
});

test('the request is an Anthropic Messages call: claude-opus-5-5, low effort, cached instructions and one fixed JSON schema', async () => {
  const h = harness(() => modelResponse(answer()));
  await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(h.requests.length, 1);
  const { url, init, body } = h.requests[0];
  assert.equal(url, 'https://api.anthropic.com/v1/messages');
  const headers = new Headers(init.headers);
  assert.equal(headers.get('x-api-key'), 'test-key');
  assert.equal(headers.get('anthropic-version'), '2026-10-21');
  assert.equal(headers.get('content-type'), 'application/json');
  assert.equal(headers.get('authorization'), null);
  assert.equal(body.model, 'claude-opus-5-5');
  // Exactly these fields: no sampling parameters, no thinking setting (this model rejects both), no forced tool.
  assert.deepEqual(Object.keys(body).sort(), ['max_tokens', 'messages', 'model', 'output_config', 'system']);
  assert.equal(body.max_tokens, 8000);
  assert.equal(systemText(body), MATCH_INSTRUCTIONS.replace('{limit}', '3'));
  assert.deepEqual(Object.keys(body.output_config).sort(), ['effort', 'format']);
  assert.equal(body.output_config.effort, 'low');
  assert.deepEqual(Object.keys(body.output_config.format).sort(), ['schema', 'type']);
  assert.equal(body.output_config.format.type, 'json_schema');
  const schema = body.output_config.format.schema;
  assert.deepEqual(sentSlugs(body), ['fixture-chat-tui', 'fixture-json-query', 'fixture-llm-runner', 'fixture-transcribe', 'fixture-web-sketch']);
  // C1: the instructions are one cached block, and the schema names no slugs, so both stay the same from request to
  // request (the guard keeps only this request's candidates).
  assert.deepEqual(body.system.map((b: any) => b.cache_control), [{ type: 'ephemeral' }]);
  assert.equal(schema.properties.picks.items.properties.slug.enum, undefined);
  // A nullable field is anyOf with null, and every object is closed: what the API's JSON outputs accept.
  assert.deepEqual(schema.properties.best_free_slug.anyOf[1], { type: 'null' });
  assert.deepEqual(schema.properties.need.properties.os, { anyOf: [{ type: 'string', enum: ['macos', 'linux', 'windows'] }, { type: 'null' }] });
  const open: string[] = [];
  const walk = (node: any, path: string) => {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node.type)) open.push(`${path}: type list`);
    if (node.type === 'object' && node.additionalProperties !== false) open.push(`${path}: open object`);
    for (const [key, value] of Object.entries(node)) walk(value, `${path}/${key}`);
  };
  walk(schema, '');
  assert.deepEqual(open, []);
  // One user message; the user's words go to the model inside <request>, as data.
  assert.equal(body.messages.length, 1);
  assert.equal(body.messages[0].role, 'user');
  assert.match(body.messages[0].content, /<request>\n.*secret-project-xyz.*\n<\/request>/);
});

test('the answer is read by block type: thinking first, several text blocks, or text alone', async () => {
  const text = JSON.stringify(answer());
  for (const content of [
    [{ type: 'thinking', thinking: '', signature: 's' }, { type: 'thinking', thinking: 'summary', signature: 's' }, { type: 'text', text }],
    [{ type: 'text', text: text.slice(0, 40) }, { type: 'text', text: text.slice(40) }],
    [{ type: 'text', text }],
  ]) {
    const h = harness(() => modelResponse(null, { content }));
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    assert.equal(out.matched_by, MATCH_MODEL);
    assert.deepEqual(out.picks.map((p) => p.slug), ['fixture-llm-runner', 'fixture-chat-tui']);
  }
});

test('stop_reason is read before the content: a refusal or a cut-off answer is not an answer', async () => {
  for (const [opts, reason] of [
    [{ stop_reason: 'refusal', stop_details: { type: 'refusal', category: 'cyber', explanation: 'x' } }, 'model_refused'],
    [{ stop_reason: 'refusal', stop_details: null, content: [] }, 'model_refused'], // declined before any output
    [{ stop_reason: 'max_tokens' }, 'model_incomplete'], // the text is there but cut off
    [{ stop_reason: 'max_tokens', content: [{ type: 'thinking', thinking: '', signature: 's' }] }, 'model_incomplete'], // thinking used the limit
    [{ stop_reason: 'tool_use' }, 'model_incomplete'],
    [{ stop_reason: null }, 'model_incomplete'],
    [{ content: [{ type: 'thinking', thinking: '', signature: 's' }] }, 'model_no_output'], // ended with no text block
    [{ usage: null }, 'model_no_output'],
  ] as const) {
    const h = harness(() => modelResponse(answer(), opts as any));
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    await h.settle();
    assert.equal(out.matched_by, 'rules', reason);
    assert.equal(out.degraded_reason, reason, JSON.stringify(opts));
    assert.equal(out.model_attempts, 1, reason); // an answer, even a refused one, is never retried
    assert.ok(out.picks.length > 0, reason);
    const spent = (h.sqlite.prepare('SELECT cost_usd FROM meta_budget').get() as any).cost_usd;
    assert.ok(spent > 0, `${reason}: what came back is still recorded as spend`);
  }
});

test('token cost: uncached input, cache reads, cache writes and output each at their own rate', () => {
  const near = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-12, `${a} vs ${b}`);
  // $4 input, $0.20 cache read, $5 cache write (1.25 x input), $20 output per million tokens.
  near(costUsd({ input_tokens: 1_000_000, cached_tokens: 0, cache_write_tokens: 0, output_tokens: 0 }), 4);
  near(costUsd({ input_tokens: 1_000_000, cached_tokens: 1_000_000, cache_write_tokens: 0, output_tokens: 0 }), 0.2);
  near(costUsd({ input_tokens: 1_000_000, cached_tokens: 0, cache_write_tokens: 1_000_000, output_tokens: 0 }), 5);
  near(costUsd({ input_tokens: 0, cached_tokens: 0, cache_write_tokens: 0, output_tokens: 1_000_000 }), 20);
  near(costUsd({ input_tokens: 3500, cached_tokens: 1000, cache_write_tokens: 500, output_tokens: 800 }), (2000 * 4 + 1000 * 0.2 + 500 * 5 + 800 * 20) / 1e6);
  // The upper bound for a request that never answers: 3 characters a token, every output token used.
  near(estimateCostUsd(30_000, 1000), (10_000 * 4 + 1000 * 20) / 1e6);
});

test("the API's usage is summed into one input count, and each part is billed and logged", async () => {
  const usage = { input_tokens: 2000, cache_creation_input_tokens: 500, cache_read_input_tokens: 1000, output_tokens: 800 };
  const h = harness(() => modelResponse(answer(), { usage }));
  const lines: string[] = [];
  const original = console.log;
  console.log = (line: string) => void lines.push(line);
  try {
    await findSoftware(MAC_OFFLINE, h.deps);
  } finally {
    console.log = original;
  }
  await h.settle();
  const logged = lines.map((line) => JSON.parse(line)).find((e) => e.event === 'meta_call');
  assert.deepEqual(
    [logged.model, logged.input_tokens, logged.cached_tokens, logged.cache_write_tokens, logged.output_tokens],
    ['claude-opus-5-5', 3500, 1000, 500, 800],
  );
  const expected = (2000 * 4 + 1000 * 0.2 + 500 * 5 + 800 * 20) / 1e6;
  assert.ok(Math.abs(logged.cost_usd - expected) < 1e-12);
  assert.ok(Math.abs((h.sqlite.prepare('SELECT cost_usd FROM meta_budget').get() as any).cost_usd - expected) < 1e-12);
});

test('D1 keeps parsed conditions and spend, never the request text', async () => {
  const h = harness(() => modelResponse(answer()));
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  await h.settle();
  const row = h.sqlite.prepare('SELECT * FROM events WHERE type = ?').get('find') as any;
  assert.equal(row.rec_id, out.rec_id);
  assert.equal(row.matched_by, 'claude-opus-5-5');
  assert.equal(row.degraded, 0);
  assert.deepEqual(JSON.parse(row.results), ['fixture-llm-runner', 'fixture-chat-tui']);
  const need = JSON.parse(row.need);
  assert.equal(need.parsed.task, 'run a small language model offline');
  assert.equal(need.given.os, 'macos');
  const everything = JSON.stringify(h.sqlite.prepare('SELECT * FROM events').all());
  assert.ok(!everything.includes('secret-project-xyz'));
  assert.ok(!everything.includes('本地'));
  // 2000 uncached input, 1000 read from the cache, 800 output tokens at claude-opus-5-5 prices.
  const expected = (2000 * 4 + 1000 * 0.2 + 800 * 20) / 1e6;
  const budget = h.sqlite.prepare('SELECT * FROM meta_budget').get() as any;
  assert.equal(budget.day, '2026-10-30');
  assert.equal(budget.calls, 1);
  assert.ok(Math.abs(budget.cost_usd - expected) < 1e-12);
  assert.ok(Math.abs(row.meta_cost_usd - expected) < 1e-12);
});

test('guard drops reasons that do not match their field and picks left without reasons', async () => {
  const h = harness(() =>
    modelResponse(
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
    modelResponse(
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

test('a contradicted fit gives way to a reason about the job; a contradicted comparison is left out', async () => {
  const h = harness(() =>
    modelResponse(
      answer({
        picks: [
          {
            slug: 'fixture-chat-tui',
            fit: 'Closed-source but tested on macOS by pickfit.',
            reasons: [
              { claim: 'Free to use', field: 'pricing', value: 'free' },
              { claim: 'Chats with a local model in the terminal', field: 'use_cases', value: 'chat with a local model from the terminal' },
            ],
            tradeoffs: [],
            vs_well_known: 'Unlike the ChatGPT desktop app it is open source and was tested on Windows.',
          },
        ],
      }),
    ),
  );
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(out.picks[0].fit, 'Chats with a local model in the terminal');
  assert.equal(out.picks[0].vs_well_known, null);
});

test('popularity and quality are never a reason, however true', async () => {
  const h = harness(() =>
    modelResponse(
      answer({
        picks: [
          {
            slug: 'fixture-chat-tui',
            fit: 'A terminal chat client for local models.',
            reasons: [
              { claim: 'Well liked', field: 'popularity', value: '22' },
              { claim: 'Scores well', field: 'quality', value: '76' },
              { claim: 'Free to use', field: 'pricing', value: 'free' },
            ],
            tradeoffs: [],
            vs_well_known: null,
          },
        ],
      }),
    ),
  );
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.deepEqual(out.picks[0]?.why.map((r) => r.field), ['pricing']);
});

test('no_install_option drops links, commands and claims of a check; a best free tool with nothing said is left out', async () => {
  const { guardNoInstall } = await import('../src/guard.ts');
  assert.equal(guardNoInstall('macOS Preview can already merge PDFs.'), 'macOS Preview can already merge PDFs.');
  for (const bad of ['Use smallpdf.com instead.', 'Run brew install qpdf.', 'Preview, verified by pickfit, is enough.', 'none']) {
    assert.equal(guardNoInstall(bad), null, bad);
  }
  const h = harness(() => modelResponse(answer({ best_free_slug: 'fixture-transcribe', best_free_reason: null })));
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  if (!out.picks.some((p) => p.slug === 'fixture-transcribe')) assert.equal(out.best_free, null);
  assert.notEqual(out.best_free?.reason, 'Free and fits the request.');
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
  const h = harness(() => modelResponse(bad));
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
  ['incomplete answer', () => modelResponse(answer(), { stop_reason: 'max_tokens' }), 'model_incomplete'],
  ['not JSON', () => modelResponse('this is not json'), 'model_bad_output'],
  ['wrong shape', () => modelResponse({ picks: 'none' }), 'model_bad_output'],
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

test('MATCH_MODE off and a missing key never call the model', async () => {
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

const SPENT_ROWS = [
  [['2026-10-30', 2.99]], // today is nearly at $3
  [['2026-10-20', 20], ['2026-10-25', 19.99]], // $40 in all, reached on earlier days
] as const;

test('with no cap set, recorded spend never stops the model call: it is only recorded', async () => {
  for (const rows of [...SPENT_ROWS, [['2026-10-30', 5000]]] as const) {
    const h = harness(() => modelResponse(answer())); // the defaults: dailyCapUsd and totalCapUsd null
    for (const [day, cost] of rows) {
      h.sqlite.prepare('INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?, 1, ?)').run(day, cost);
    }
    const before = (h.sqlite.prepare('SELECT SUM(cost_usd) AS usd, SUM(calls) AS calls FROM meta_budget').get() as any);
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    await h.settle();
    assert.equal(h.requests.length, 1);
    assert.equal(out.matched_by, MATCH_MODEL);
    assert.equal(out.degraded, false);
    const after = (h.sqlite.prepare('SELECT SUM(cost_usd) AS usd, SUM(calls) AS calls FROM meta_budget').get() as any);
    assert.equal(after.calls, before.calls + 1);
    assert.ok(after.usd > before.usd);
  }
});

test('with no cap set, a D1 that cannot be read does not turn the model off', async () => {
  const h = harness(() => modelResponse(answer()));
  h.sqlite.exec('DROP TABLE meta_budget');
  const errors: string[] = [];
  const original = console.error;
  console.error = (line: string) => void errors.push(line);
  try {
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    await h.settle();
    assert.equal(out.matched_by, MATCH_MODEL);
    assert.equal(out.degraded, false);
  } finally {
    console.error = original;
  }
  // The spend could not be written, and that is logged rather than hidden.
  assert.ok(errors.some((line) => JSON.parse(line).what === 'meta_budget'));
});

test('an opt-in daily cap or total cap stops the model call', async () => {
  for (const [rows, caps] of [
    [SPENT_ROWS[0], { dailyCapUsd: 3, totalCapUsd: null }],
    [SPENT_ROWS[1], { dailyCapUsd: null, totalCapUsd: 40 }],
    [SPENT_ROWS[0], { dailyCapUsd: 3, totalCapUsd: 40 }],
    [[], { dailyCapUsd: 0, totalCapUsd: null }], // a cap of 0 is a stop, not "no cap"
  ] as const) {
    const h = harness(null, caps);
    for (const [day, cost] of rows) {
      h.sqlite.prepare('INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?, 1, ?)').run(day, cost);
    }
    const out = await findSoftware(MAC_OFFLINE, h.deps);
    assert.equal(h.requests.length, 0);
    assert.equal(out.degraded_reason, 'over_budget');
    assert.equal(out.matched_by, 'rules');
  }
  // Each cap looks only at its own sum: $2.99 today is under a $40 total, and $39.99 on earlier days is under $3 a day.
  for (const [rows, caps] of [
    [SPENT_ROWS[0], { dailyCapUsd: null, totalCapUsd: 40 }],
    [SPENT_ROWS[1], { dailyCapUsd: 3, totalCapUsd: null }],
  ] as const) {
    const h = harness(() => modelResponse(answer()), caps);
    for (const [day, cost] of rows) {
      h.sqlite.prepare('INSERT INTO meta_budget (day, calls, cost_usd) VALUES (?, 1, ?)').run(day, cost);
    }
    assert.equal((await findSoftware(MAC_OFFLINE, h.deps)).matched_by, MATCH_MODEL);
  }
});

test('with a cap set, a D1 that cannot be read stops the model call: spend that cannot be counted is not spent', async () => {
  const h = harness(null, { dailyCapUsd: 3 });
  h.sqlite.exec('DROP TABLE meta_budget');
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.equal(out.degraded_reason, 'budget_unavailable');
  assert.equal(out.matched_by, 'rules');
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
  const h = harness(() => modelResponse(answer({ picks: [], best_free_slug: null })));
  const out = await findSoftware({ need: 'edit videos with a timeline', os: 'linux' }, h.deps);
  assert.equal(out.matched_by, MATCH_MODEL);
  assert.deepEqual(out.picks, []);
  assert.match(out.coverage_note ?? '', /None of the 7 verified tools/);
});

test('best_free must be a free candidate', async () => {
  const h = harness(() => modelResponse(answer({ best_free_slug: 'fixture-cloud-summarize' })));
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

test('the cached prefix is the same for requests with different candidates', async () => {
  const h = harness(() => modelResponse(answer()));
  await findSoftware(MAC_OFFLINE, h.deps);
  await findSoftware({ need: 'query JSON files from the terminal', os: 'linux' }, h.deps);
  const [a, b] = h.requests.map((r) => r.body);
  assert.notDeepEqual(sentSlugs(a), sentSlugs(b));
  assert.deepEqual(a.system, b.system);
  assert.deepEqual(a.output_config, b.output_config);
});

test('a pick or best free slug outside the candidates is dropped now that the schema does not list them', async () => {
  const h = harness(() =>
    modelResponse(
      answer({
        picks: [{ slug: 'not-a-candidate', fit: 'x', reasons: [{ claim: 'Free to use', field: 'pricing', value: 'free' }], tradeoffs: [], vs_well_known: null }],
        best_free_slug: 'not-a-candidate',
        best_free_reason: 'It is free.',
      }),
    ),
  );
  const out = await findSoftware(MAC_OFFLINE, h.deps);
  assert.ok(out.picks.every((p) => p.slug !== 'not-a-candidate'));
  assert.notEqual(out.best_free?.slug, 'not-a-candidate');
});

test('isEnglish: ASCII text with letters, typographic quotes allowed; any other script is not', async () => {
  const { isEnglish } = await import('../src/find.ts');
  assert.equal(isEnglish('convert “markdown” to PDF — fast'), true);
  assert.equal(isEnglish('把 markdown 轉成 PDF'), false);
  assert.equal(isEnglish('convertir en PDF à la volée'), false);
  assert.equal(isEnglish('123 456'), false);
});
