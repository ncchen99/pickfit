/** Test doubles: D1 on node:sqlite (with the real migrations), fake Meta responses, the fixture catalog. */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { loadCatalog, type Catalog } from '../src/catalog.ts';
import type { Settings } from '../src/env.ts';
import type { Deps } from '../src/find.ts';
import type { ModelAnswer } from '../src/prompt.ts';

const HERE = import.meta.dirname;

/** Built from test/fixtures/software by `npm run build:fixtures` (part of `npm test`). */
export function fixtureIndex(): unknown {
  return JSON.parse(readFileSync(join(HERE, 'generated', 'index.json'), 'utf8'));
}

export function fixtureCatalog(): Catalog {
  return loadCatalog(fixtureIndex());
}

type Value = string | number | null;

class Statement {
  readonly sqlite: DatabaseSync;
  readonly sql: string;
  readonly params: Value[];
  constructor(sqlite: DatabaseSync, sql: string, params: Value[] = []) {
    this.sqlite = sqlite;
    this.sql = sql;
    this.params = params;
  }
  bind(...params: Value[]) {
    return new Statement(this.sqlite, this.sql, params);
  }
  async first<T>() {
    return (this.sqlite.prepare(this.sql).get(...this.params) as T | undefined) ?? null;
  }
  async all<T>() {
    return { results: this.sqlite.prepare(this.sql).all(...this.params) as T[], success: true, meta: {} };
  }
  async run() {
    const info = this.sqlite.prepare(this.sql).run(...this.params);
    return { results: [], success: true, meta: { changes: Number(info.changes) } };
  }
}

/** The subset of D1Database the Worker uses, over an in-memory SQLite with migrations applied. */
export function makeD1(): { db: D1Database; sqlite: DatabaseSync } {
  const sqlite = new DatabaseSync(':memory:');
  const dir = join(HERE, '..', 'migrations');
  for (const name of readdirSync(dir).filter((f) => f.endsWith('.sql')).sort()) {
    sqlite.exec(readFileSync(join(dir, name), 'utf8'));
  }
  const db = { prepare: (sql: string) => new Statement(sqlite, sql) };
  return { db: db as unknown as D1Database, sqlite };
}

export const SETTINGS: Settings = {
  modelEnabled: true,
  apiKey: 'test-key',
  dailyCapUsd: 3,
  totalCapUsd: 40,
  timeoutMs: 2000,
  submitHourlyCap: 20,
};

export interface Harness {
  deps: Deps;
  sqlite: DatabaseSync;
  requests: { url: string; init: RequestInit; body: any }[];
  /** Await everything handed to waitUntil (D1 writes). */
  settle: () => Promise<void>;
}

export type FakeFetch = (body: any) => Response | Promise<Response>;

export function harness(fake: FakeFetch | null, settings: Partial<Settings> = {}): Harness {
  const { db, sqlite } = makeD1();
  const pending: Promise<unknown>[] = [];
  const requests: Harness['requests'] = [];
  const fetchImpl = (async (url: string | URL | Request, init: RequestInit = {}) => {
    const body = JSON.parse(String(init.body));
    requests.push({ url: String(url), init, body });
    if (!fake) throw new Error('fetch must not be called');
    return fake(body);
  }) as typeof fetch;
  return {
    deps: {
      catalog: fixtureCatalog(),
      db,
      settings: { ...SETTINGS, ...settings },
      now: () => new Date('2026-10-30T12:00:00Z'),
      waitUntil: (promise) => void pending.push(promise),
      fetch: fetchImpl,
    },
    sqlite,
    requests,
    settle: async () => {
      await Promise.all(pending);
    },
  };
}

export const USAGE = {
  input_tokens: 3000,
  input_tokens_details: { cached_tokens: 1000 },
  output_tokens: 800,
  output_tokens_details: { reasoning_tokens: 300 },
};

/** A Responses API body as Meta returns it, carrying `answer` as the output text. */
export function metaResponse(answer: unknown, opts: { status?: string; usage?: unknown } = {}): Response {
  return Response.json({
    id: 'resp_test',
    object: 'response',
    status: opts.status ?? 'completed',
    model: 'muse-spark-1.3',
    output: [
      { type: 'reasoning', summary: [] },
      {
        type: 'message',
        role: 'assistant',
        content: [{ type: 'output_text', text: typeof answer === 'string' ? answer : JSON.stringify(answer) }],
      },
    ],
    usage: opts.usage ?? USAGE,
  });
}

export function answer(overrides: Partial<ModelAnswer> = {}): ModelAnswer {
  return {
    need: {
      task: 'run a small language model offline',
      category: 'local_ai',
      os: 'macos',
      budget: 'free_only',
      must_run_locally: true,
      must_have: [],
      search_terms: ['local llm', 'offline inference'],
    },
    picks: [
      {
        slug: 'fixture-llm-runner',
        fit: 'Serves a local model offline through an OpenAI-compatible API.',
        reasons: [
          { claim: 'Runs offline on your machine', field: 'processing', value: 'local' },
          { claim: 'Checked by hand on macOS', field: 'verified_on', value: 'macos arm64' },
        ],
        tradeoffs: ['Needs 8 GB of RAM'],
        vs_well_known: 'Lighter than Ollama when you only need an API endpoint.',
      },
      {
        slug: 'fixture-chat-tui',
        fit: 'A terminal chat front end for that local model.',
        reasons: [{ claim: 'Free to use', field: 'pricing', value: 'free' }],
        tradeoffs: ['Alpha maturity'],
        vs_well_known: null,
      },
    ],
    best_free_slug: 'fixture-llm-runner',
    best_free_reason: 'Free, open source and runs offline.',
    no_install_option: null,
    clarifying_question: null,
    ...overrides,
  };
}
