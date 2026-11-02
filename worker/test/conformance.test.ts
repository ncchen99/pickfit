/**
 * Every tool's structuredContent matches the outputSchema it advertises in
 * tools/list (additionalProperties: false), checked with the MCP SDK's own
 * validator, for every response shape. A client that validates strictly
 * rejects anything else, so this catches the next drift between a tool's code
 * and its zod schema.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CfWorkerJsonSchemaValidator } from '@modelcontextprotocol/server/validators/cf-worker';
import type { Env } from '../src/env.ts';
import { makeWorker } from '../src/worker.ts';
import { answer, fixtureIndex, makeD1, metaResponse } from './helpers.ts';

/**
 * The fixture index plus shapes the fixtures lack: tagged pitfalls (one with a
 * kind pickfit does not know, and a field the response must not pass on), a
 * profile with no install run, and a profile on GitHub for submit_software.
 */
function index(): unknown {
  const data = structuredClone(fixtureIndex()) as any;
  const entry = (slug: string) => data.entries.find((e: any) => e.slug === slug);
  entry('fixture-transcribe').install.linux.pitfalls[0].kind = 'readme_wrong';
  Object.assign(entry('fixture-llm-runner').install.linux.pitfalls[0], { kind: 'surprise', seen_in: 'step 2' });
  entry('fixture-cloud-summarize').install = {};
  entry('fixture-json-query').repo_url = 'https://github.com/example/json-query';
  // An index from before feature coverage: no features on the entry or its guide.
  delete entry('fixture-chat-tui').features;
  for (const guide of Object.values(entry('fixture-chat-tui').install) as any[]) delete guide.features;
  // A GUI app's launch on its Linux run.
  const chat = entry('fixture-chat-tui');
  const gui = { tier: 'ui_rendered', screen: 'main_ui', display: 'Xvfb 1280x800x24, no window manager, no GPU', launch_offline: true };
  chat.kind = 'desktop_app';
  chat.install.linux.run.gui = gui;
  for (const run of chat.verification.passed_runs) if (run.os === 'linux') run.gui = gui;
  return data;
}

const LLM = { need: 'run a language model offline on my laptop', os: 'macos', must_run_locally: true };

function server(env: Partial<Env> = {}) {
  const { db } = makeD1();
  let meta: () => Response = () => Response.json({ error: { code: 'unexpected' } }, { status: 500 });
  const worker = makeWorker(index(), {
    fetch: (async () => meta()) as unknown as typeof fetch,
    now: () => new Date('2026-10-30T12:00:00Z'),
  });
  const pending: Promise<unknown>[] = [];
  const ctx = { waitUntil: (p: Promise<unknown>) => void pending.push(p), passThroughOnException() {} };
  let id = 0;
  const rpc = async (method: string, params: object = {}) => {
    const response = await worker.fetch(
      new Request('http://127.0.0.1:8787/mcp', {
        method: 'POST',
        headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25' },
        body: JSON.stringify({ jsonrpc: '2.0', id: ++id, method, params }),
      }),
      { DB: db, ...env } as Env,
      ctx as unknown as ExecutionContext,
    );
    const text = await response.text();
    return JSON.parse(text.startsWith('{') ? text : text.split('\n').find((l) => l.startsWith('data: '))!.slice(6));
  };
  return {
    rpc,
    answers: (fake: () => Response) => void (meta = fake),
    settle: () => Promise.all(pending),
  };
}

/** Validators for each tool's advertised outputSchema, from tools/list. */
async function validators(s: ReturnType<typeof server>) {
  await s.rpc('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 't', version: '0' } });
  const { tools } = (await s.rpc('tools/list')).result;
  const validator = new CfWorkerJsonSchemaValidator();
  return new Map<string, (value: unknown) => any>(
    tools.map((tool: any) => {
      assert.equal(tool.outputSchema.additionalProperties, false, `${tool.name} schema is not strict`);
      return [tool.name, validator.getValidator(tool.outputSchema)];
    }),
  );
}

/** Calls a tool and asserts its structuredContent conforms; returns it for the shape checks. */
async function conforming(s: ReturnType<typeof server>, schemas: Map<string, (v: unknown) => any>, label: string, name: string, args: object) {
  const res = await s.rpc('tools/call', { name, arguments: args });
  assert.ok(res.result && !res.result.isError, `${label}: ${JSON.stringify(res.error ?? res.result?.content)}`);
  const content = res.result.structuredContent;
  const check = schemas.get(name)!(content);
  assert.ok(check.valid, `${label} breaks the ${name} outputSchema: ${check.errorMessage ?? JSON.stringify(check.errors)}`);
  return content;
}

test('find_software conforms: picks, a clarifying question, empty, no candidates, degraded', async () => {
  const s = server({ MODEL_API_KEY: 'k', META_TIMEOUT_MS: '2000' });
  const schemas = await validators(s);
  const call = (label: string, args: object) => conforming(s, schemas, label, 'find_software', args);

  s.answers(() => metaResponse(answer()));
  const picks = await call('model picks', LLM);
  assert.ok(picks.picks.length > 0 && picks.best_free && !picks.degraded);

  s.answers(() =>
    metaResponse(answer({ well_known_name: 'Ollama', well_known_why: 'Ollama is free, runs offline on macOS and is simpler to set up.' })),
  );
  const outside = await call('well-known option', LLM);
  assert.deepEqual([outside.well_known_option.name, outside.well_known_option.verified], ['Ollama', false]);

  s.answers(() => metaResponse(answer({ clarifying_question: 'Do you need a GUI or is a terminal fine?' })));
  assert.ok((await call('clarifying question', LLM)).clarifying_question);

  s.answers(() => metaResponse(answer({ picks: [], best_free_slug: null })));
  const empty = await call('empty by the model', LLM);
  assert.deepEqual([empty.picks.length, empty.best_free], [0, null]);
  assert.ok(empty.coverage_note);

  const none = await call('no candidates', {
    ...LLM,
    exclude: ['fixture-chat-tui', 'fixture-cloud-summarize', 'fixture-json-query', 'fixture-llm-runner', 'fixture-transcribe', 'fixture-web-sketch'],
  });
  assert.equal(none.considered, 0);

  s.answers(() => Response.json({ error: { code: 'unavailable' } }, { status: 503 }));
  const http = await call('degraded: model_http', LLM);
  assert.deepEqual([http.degraded_reason, http.model_http_status, http.matched_by], ['model_http', 503, 'rules']);

  const off = server({ MATCH_MODE: 'off' });
  const rules = await conforming(off, await validators(off), 'degraded: model_off, rules question', 'find_software', {
    need: 'run a language model offline',
  });
  assert.equal(rules.degraded_reason, 'model_off');
  assert.ok(rules.clarifying_question); // no OS given, and the picks run on different ones
});

test('find_software conforms with the rules fit labels: good, partial, weak and none; the model path has none of it', async () => {
  const off = server({ MATCH_MODE: 'off' });
  const schemas = await validators(off);
  const call = (label: string, need: string) => conforming(off, schemas, label, 'find_software', { need });
  const good = await call('rules: good match', 'run a language model offline on my laptop');
  assert.equal(good.match_quality, 'good');
  assert.equal(good.picks[0].match.quality, 'good');
  const partial = await call('rules: partial match', 'transcribe audio into a json summary for git');
  assert.equal(partial.match_quality, 'partial');
  assert.deepEqual(partial.picks[0].match, { quality: 'partial', covers: ['transcribe', 'audio'], missing: ['json', 'summary', 'git'] });
  assert.match(partial.picks[0].tradeoffs[0], /mentions transcribe, audio but not json, summary, git/);
  const none = await call('rules: no good match', 'search my Notion pages');
  assert.equal(none.match_quality, 'none');
  assert.deepEqual(none.picks.map((p: any) => p.match.quality), ['weak', 'weak', 'weak']); // still listed
  assert.match(none.coverage_note, /pickfit has no verified tool that clearly does this job/);

  const s = server({ MODEL_API_KEY: 'k', META_TIMEOUT_MS: '2000' });
  const modelSchemas = await validators(s);
  s.answers(() => metaResponse(answer()));
  const model = await conforming(s, modelSchemas, 'model picks', 'find_software', LLM);
  assert.ok(!('match_quality' in model));
  assert.ok(model.picks.every((p: any) => !('match' in p)));
  s.answers(() => Response.json({ error: { code: 'unavailable' } }, { status: 503 }));
  const degraded = await conforming(s, modelSchemas, 'degraded: rules decide', 'find_software', LLM);
  assert.equal(degraded.matched_by, 'rules');
  assert.ok(degraded.match_quality);
});

test('find_alternatives conforms: keep_current true, a better pick, and rules', async () => {
  const s = server({ MODEL_API_KEY: 'k', META_TIMEOUT_MS: '2000' });
  const schemas = await validators(s);
  const args = { current_software: 'Ollama', pain_points: 'too heavy for my old laptop', os: 'linux' };
  const alt = (keep: { recommended: boolean; reason: string }, picks = answer().picks.slice(0, 1)) =>
    metaResponse(answer({ picks, keep_current: keep, need: { ...answer().need, current_tool: 'Ollama', pain_points: ['too heavy'] } }));

  s.answers(() => alt({ recommended: true, reason: 'Nothing here is clearly lighter.' }, []));
  const keep = await conforming(s, schemas, 'keep current', 'find_alternatives', args);
  assert.deepEqual([keep.keep_current.recommended, keep.picks.length], [true, 0]);

  s.answers(() => alt({ recommended: false, reason: 'The runner is lighter.' }));
  const better = await conforming(s, schemas, 'a better pick', 'find_alternatives', args);
  assert.deepEqual([better.keep_current.recommended, better.picks.length], [false, 1]);

  const off = server({ MATCH_MODE: 'off' });
  const rules = await conforming(off, await validators(off), 'rules, current tool listed', 'find_alternatives', {
    current_software: 'fixture-json-query',
    pain_points: 'hard filter syntax',
    os: 'linux',
  });
  assert.deepEqual([rules.keep_current, rules.current.matched_slug], [null, 'fixture-json-query']);
});

test('get_install_guide conforms: pitfalls, setup, no pitfalls, another OS or arch, never run', async () => {
  const s = server({ MATCH_MODE: 'off' });
  const schemas = await validators(s);
  const call = (label: string, args: object) => conforming(s, schemas, label, 'get_install_guide', args);

  const tagged = await call('pitfall with a kind', { slug: 'fixture-transcribe', os: 'linux' });
  assert.equal(tagged.known_issues[0].kind, 'readme_wrong');
  assert.deepEqual([tagged.features.checked.length, tagged.features.not_checked.length], [1, 2]);
  const older = await call('an index from before feature coverage', { slug: 'fixture-chat-tui', os: 'linux' });
  assert.equal(older.features.recorded, false);

  const setup = await call('setup, offline check, unknown pitfall kind', { slug: 'fixture-llm-runner', os: 'linux' });
  assert.equal(setup.verification.works_offline, true);
  assert.ok(setup.first_task_setup.length > 0);
  assert.equal(setup.known_issues[0].kind, null);
  assert.deepEqual(Object.keys(setup.known_issues[0]).sort(), ['actually_needed', 'kind', 'readme_said']);

  const plain = await call('no pitfalls, manual steps', { slug: 'fixture-llm-runner', os: 'macos' });
  assert.deepEqual([plain.known_issues, plain.applies_to_user_system.match], [[], 'exact']);
  assert.ok(plain.manual_steps.length > 0);

  assert.equal((await call('another OS', { slug: 'fixture-transcribe', os: 'macos' })).applies_to_user_system.match, 'other_os');
  assert.equal(
    (await call('another arch', { slug: 'fixture-llm-runner', os: 'macos', arch: 'x86_64' })).applies_to_user_system.match,
    'same_os_other_arch',
  );
  const never = await call('never run', { slug: 'fixture-cloud-summarize', os: 'linux' });
  assert.deepEqual([never.verification.status, never.steps, never.verify], ['unverified', [], null]);

  const gui = await call('a GUI app with its launch evidence', { slug: 'fixture-chat-tui', os: 'linux' });
  assert.deepEqual([gui.verification.level, gui.verification.gui.tier, gui.verification.gui.screen], ['install', 'ui_rendered', 'main_ui']);
  assert.match(gui.how_we_know, /judged that its main screen rendered/);
  assert.equal(tagged.verification.gui, null);

  const mcp = await call('an MCP server with a client config', { slug: 'fixture-notes-mcp', os: 'linux' });
  assert.ok(mcp.mcp_client_config.claude_code.startsWith('claude mcp add fixture-notes-mcp'));
  assert.equal(plain.mcp_client_config, null);
  const elsewhere = await call('an MCP server checked on another OS', { slug: 'fixture-notes-mcp', os: 'macos' });
  assert.equal(elsewhere.applies_to_user_system.match, 'other_os');
});

test('a web app conforms: find_software picks it with web_app set, and its guide is the URL with no steps', async () => {
  const off = server({ MATCH_MODE: 'off' });
  const schemas = await validators(off);
  const found = await conforming(off, schemas, 'rules, a web app', 'find_software', { need: 'draw a flowchart diagram and export it as PNG' });
  const sketch = found.picks.find((p: any) => p.slug === 'fixture-web-sketch');
  assert.ok(sketch, 'the web app is a pick');
  assert.deepEqual([sketch.repo, sketch.web_app.label, sketch.web_app.url], [null, 'No install, just open it', 'https://fixture-sketch.example.invalid/']);
  assert.equal(sketch.verification.verified_on_user_os, null);
  const guide = await conforming(off, schemas, 'a web app guide', 'get_install_guide', { slug: 'fixture-web-sketch', os: 'windows' });
  assert.deepEqual([guide.steps, guide.verify, guide.applies_to_user_system.match], [[], null, 'exact']);
  assert.equal(guide.web_app.data_sent, 'none');
  assert.deepEqual(guide.check_in.commands, []);
});

test('find_software conforms for the mcp_server category', async () => {
  const off = server({ MATCH_MODE: 'off' });
  const out = await conforming(off, await validators(off), 'rules, mcp_server', 'find_software', {
    need: 'search my Markdown notes from Claude Code',
    category: 'mcp_server',
    os: 'linux',
  });
  assert.deepEqual(out.picks.map((p: any) => p.slug), ['fixture-notes-mcp']);
});

test('find_software conforms with a GUI app among the picks; its verification carries the launch', async () => {
  const off = server({ MATCH_MODE: 'off' });
  const out = await conforming(off, await validators(off), 'rules, a GUI app', 'find_software', {
    need: 'chat with a local language model',
    os: 'linux',
  });
  const chat = out.picks.find((p: any) => p.slug === 'fixture-chat-tui');
  assert.ok(chat, `picks: ${out.picks.map((p: any) => p.slug)}`);
  assert.deepEqual([chat.verification.level, chat.verification.gui.tier], ['install', 'ui_rendered']);
  assert.match(chat.how_we_know, /opened a window of its own on a virtual display/);
  assert.ok(out.picks.filter((p: any) => p !== chat).every((p: any) => p.verification.gui === null));
});

test('report_outcome conforms: counted with a reverify, deduplicated, not counted, replaced', async () => {
  const s = server({ MATCH_MODE: 'off' });
  const schemas = await validators(s);
  const guide = await conforming(s, schemas, 'guide', 'get_install_guide', { slug: 'fixture-transcribe', os: 'linux' });
  await s.settle();
  const call = (label: string, args: object) => conforming(s, schemas, label, 'report_outcome', args);
  const failed = { slug: 'fixture-transcribe', stage: 'install_failed', rec_id: guide.rec_id, os: 'linux', error_excerpt: 'error: no such file' };

  const counted = await call('counted, reverify queued', failed);
  assert.deepEqual([counted.counted_in_score, counted.reverify], [true, 'queued']);
  await s.settle();
  assert.equal((await call('deduplicated', failed)).deduplicated, true);
  assert.equal((await call('not counted', { slug: 'fixture-transcribe', stage: 'installed' })).not_counted_reason, 'no_rec_id');
  const replaced = await call('replaced', {
    slug: 'fixture-transcribe',
    stage: 'replaced',
    rec_id: guide.rec_id,
    replaced_by: 'fixture-json-query',
    satisfaction: 'dissatisfied',
  });
  assert.equal(replaced.accepted, true);
});

test('submit_software conforms: queued, already submitted, listed', async () => {
  const s = server({ MATCH_MODE: 'off' });
  const schemas = await validators(s);
  const call = (label: string, url: string) => conforming(s, schemas, label, 'submit_software', { url, submitter_role: 'author' });

  const queued = await call('queued', 'https://github.com/someone/new-tool');
  assert.deepEqual([queued.status, queued.already_submitted], ['queued', false]);
  assert.equal((await call('already submitted', 'github.com/Someone/new-tool.git')).already_submitted, true);
  const listed = await call('listed', 'https://github.com/example/json-query');
  assert.deepEqual([listed.status, listed.slug, listed.submission_id], ['listed', 'fixture-json-query', null]);
});
