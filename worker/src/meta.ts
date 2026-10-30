/**
 * The Worker's model calls: Meta Responses API, muse-spark-1.3 (the match
 * call, and English keywords when the shortlist must cut, expand.ts).
 *
 * User requests are private, so the model is fixed here: never the
 * -contributor models (their inputs may be used for training), and
 * store: false so Meta keeps no copy of the request.
 */

export const META_BASE_URL = 'https://api.meta.ai/v1';
export const MATCH_MODEL = 'muse-spark-1.3';
/** USD per 1M tokens for MATCH_MODEL (same table as pickfit/meta.py). */
const PRICE = { input: 1.25, cached: 0.15, output: 4.25 };
export const MAX_OUTPUT_TOKENS = 4000;

export interface Usage {
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
}

export interface MetaResult {
  text: string;
  usage: Usage;
  /** All requests this call sent; an HTTP error costs nothing. */
  costUsd: number;
  latencyMs: number;
  /** HTTP status of each request sent, in order: [200], or [503, 200] after a retry. */
  statuses: (number | null)[];
}

export type MetaFailure = 'http' | 'timeout' | 'network' | 'incomplete' | 'no_output';

interface FailureDetail {
  costUsd?: number;
  /** The HTTP status Meta returned; null for a timeout or a request that never got a response. */
  status?: number | null;
  /** Worth one retry: see isTransient. */
  transient?: boolean;
  /** How long Meta asked us to wait (Retry-After), when it said. */
  retryAfterMs?: number | null;
  statuses?: (number | null)[];
}

export class MetaCallError extends Error {
  readonly kind: MetaFailure;
  /** What the failed call may have cost; charged to the budget. */
  readonly costUsd: number;
  readonly status: number | null;
  readonly transient: boolean;
  readonly retryAfterMs: number | null;
  /** HTTP status of each request sent (null where none came back), in order. */
  readonly statuses: (number | null)[];
  constructor(kind: MetaFailure, message: string, detail: FailureDetail = {}) {
    super(message);
    this.kind = kind;
    this.costUsd = detail.costUsd ?? 0;
    this.status = detail.status ?? null;
    this.transient = detail.transient ?? false;
    this.retryAfterMs = detail.retryAfterMs ?? null;
    this.statuses = detail.statuses ?? [this.status];
  }
}

/** No retry with less than this left of the timeout: a match call takes 6-8 s, and a retry that times out is still charged. */
const RETRY_MIN_LEFT_MS = 10_000;
/** Honor Retry-After up to this; asked to wait longer, degrade now. */
const RETRY_AFTER_MAX_MS = 5_000;
/** Jittered wait before the retry when Meta gives no Retry-After. */
const BACKOFF_MS = [200, 800] as const;

/** A 404 that says the model is missing: Meta returned this for muse-spark-1.3, on and off, on 2026-10-29. */
const MODEL_NOT_FOUND = /model_not_found|\bmodel\b[^\n]{0,80}\b(?:not found|does not exist)/i;

/** Rate limits, server errors, and a 404 that says the model is missing (it came back minutes later). */
export function isTransient(status: number, body: string): boolean {
  return status === 429 || (status >= 500 && status <= 599) || (status === 404 && MODEL_NOT_FOUND.test(body));
}

/** Milliseconds from `retry-after-ms`, else `retry-after` (seconds or an HTTP date); null when absent. */
export function retryAfterMs(headers: Headers, nowMs: number): number | null {
  const ms = headers.get('retry-after-ms');
  if (ms !== null && ms.trim() !== '' && Number.isFinite(Number(ms))) return Math.max(0, Number(ms));
  const value = headers.get('retry-after')?.trim();
  if (!value) return null;
  if (Number.isFinite(Number(value))) return Math.max(0, Number(value) * 1000);
  const at = Date.parse(value);
  return Number.isNaN(at) ? null : Math.max(0, at - nowMs);
}

export function costUsd(usage: Usage): number {
  const cached = Math.min(usage.cached_tokens, usage.input_tokens);
  return (
    ((usage.input_tokens - cached) * PRICE.input + cached * PRICE.cached + usage.output_tokens * PRICE.output) /
    1_000_000
  );
}

/** Upper bound for one call: ~3 characters per input token, every output token used. */
export function estimateCostUsd(requestChars: number, maxOutputTokens = MAX_OUTPUT_TOKENS): number {
  return ((requestChars / 3) * PRICE.input + maxOutputTokens * PRICE.output) / 1_000_000;
}

function readUsage(raw: any): Usage | null {
  const u = raw?.usage;
  if (!u || typeof u.input_tokens !== 'number') return null;
  return {
    input_tokens: u.input_tokens,
    cached_tokens: u.input_tokens_details?.cached_tokens ?? 0,
    output_tokens: u.output_tokens ?? 0,
    reasoning_tokens: u.output_tokens_details?.reasoning_tokens ?? 0,
  };
}

function outputText(raw: any): string | null {
  const parts: string[] = [];
  for (const item of raw?.output ?? []) {
    if (item?.type !== 'message') continue;
    for (const part of item.content ?? []) {
      if (part?.type === 'output_text' && typeof part.text === 'string') parts.push(part.text);
    }
  }
  return parts.length ? parts.join('') : null;
}

export interface StructuredRequest {
  instructions: string;
  input: string;
  schemaName: string;
  schema: Record<string, unknown>;
  /** Defaults: the match call's low effort and MAX_OUTPUT_TOKENS. */
  effort?: 'minimal' | 'low';
  maxOutputTokens?: number;
}

export function requestBody(req: StructuredRequest): Record<string, unknown> {
  return {
    model: MATCH_MODEL,
    store: false,
    reasoning: { effort: req.effort ?? 'low' },
    max_output_tokens: req.maxOutputTokens ?? MAX_OUTPUT_TOKENS,
    input: [
      { role: 'developer', content: req.instructions },
      { role: 'user', content: req.input },
    ],
    text: { format: { type: 'json_schema', name: req.schemaName, schema: req.schema, strict: true } },
  };
}

export interface CallOptions {
  /** META_TIMEOUT_MS: both tries and the wait between them fit in it. */
  timeoutMs: number;
  fetch?: typeof fetch;
  /** Milliseconds now, the wait before a retry, and jitter in [0, 1); seams for tests. */
  clock?: () => number;
  sleep?: (ms: number) => Promise<void>;
  random?: () => number;
}

const pause = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * One structured call, retried once after a transient HTTP error (429, 5xx,
 * 404 model not found) when enough of timeoutMs is left. Never retried: an
 * answer (even one that turns out bad), a timeout, a network error, or any
 * other status. Throws MetaCallError on anything short of a complete answer.
 */
export async function callMeta(apiKey: string, body: Record<string, unknown>, opts: CallOptions): Promise<MetaResult> {
  const clock = opts.clock ?? Date.now;
  const deadline = clock() + opts.timeoutMs;
  const statuses: (number | null)[] = [];
  let spent = 0;
  for (let attempt = 1; ; attempt++) {
    try {
      const result = await callOnce(apiKey, body, deadline - clock(), opts.fetch ?? fetch, clock);
      return { ...result, costUsd: spent + result.costUsd, statuses: [...statuses, ...result.statuses] };
    } catch (err) {
      if (!(err instanceof MetaCallError)) throw err;
      statuses.push(err.status);
      spent += err.costUsd;
      const wait = attempt === 1 ? retryWait(err, opts.random ?? Math.random) : null;
      const leftMs = deadline - clock() - (wait ?? 0);
      if (wait === null || leftMs < RETRY_MIN_LEFT_MS) {
        throw new MetaCallError(err.kind, err.message, {
          costUsd: spent,
          status: err.status,
          transient: err.transient,
          retryAfterMs: err.retryAfterMs,
          statuses,
        });
      }
      console.log(JSON.stringify({ event: 'meta_retry', status: err.status, wait_ms: Math.round(wait), left_ms: Math.round(leftMs) }));
      await (opts.sleep ?? pause)(wait);
    }
  }
}

/** How long to wait before the one retry, or null for no retry. */
function retryWait(err: MetaCallError, random: () => number): number | null {
  if (!err.transient) return null;
  const jitter = BACKOFF_MS[0] + random() * (BACKOFF_MS[1] - BACKOFF_MS[0]);
  if (err.retryAfterMs === null) return jitter;
  return err.retryAfterMs <= RETRY_AFTER_MAX_MS ? Math.max(err.retryAfterMs, jitter) : null;
}

const outputLimit = (body: Record<string, unknown>) =>
  typeof body.max_output_tokens === 'number' ? body.max_output_tokens : MAX_OUTPUT_TOKENS;

async function callOnce(
  apiKey: string,
  body: Record<string, unknown>,
  timeoutMs: number,
  doFetch: typeof fetch,
  clock: () => number,
): Promise<MetaResult> {
  const started = clock();
  let response: Response;
  try {
    response = await doFetch(`${META_BASE_URL}/responses`, {
      method: 'POST',
      headers: { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(Math.max(1, timeoutMs)),
    });
  } catch (err) {
    const timedOut = err instanceof Error && (err.name === 'TimeoutError' || err.name === 'AbortError');
    // A timed-out request may still be billed; charge the upper bound.
    const charge = timedOut ? estimateCostUsd(JSON.stringify(body).length, outputLimit(body)) : 0;
    throw new MetaCallError(timedOut ? 'timeout' : 'network', String(err), { costUsd: charge });
  }
  const latencyMs = clock() - started;
  const bodyText = await response.text().catch(() => '');
  let raw: any = null;
  try {
    raw = JSON.parse(bodyText);
  } catch {
    // not JSON; handled below
  }
  const status = response.status;
  if (!response.ok) {
    const code = raw?.error?.code ?? raw?.error?.type ?? 'unknown';
    throw new MetaCallError('http', `Meta API ${status} ${code}`, {
      status,
      transient: isTransient(status, bodyText),
      retryAfterMs: retryAfterMs(response.headers, clock()),
    });
  }
  const usage = readUsage(raw);
  const cost = usage ? costUsd(usage) : estimateCostUsd(JSON.stringify(body).length, outputLimit(body));
  if (raw?.status !== 'completed') {
    throw new MetaCallError('incomplete', `response status ${raw?.status ?? 'missing'}`, { costUsd: cost, status });
  }
  const text = outputText(raw);
  if (!text || !usage) throw new MetaCallError('no_output', 'no output text or usage', { costUsd: cost, status });
  return { text, usage, costUsd: cost, latencyMs, statuses: [status] };
}
