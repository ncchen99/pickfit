/**
 * The Worker's model calls: Claude through the Anthropic Messages API (the
 * match call, and English keywords when the shortlist must cut, expand.ts).
 *
 * The model is fixed here, one constant with its price beside it (a bench run may name another, MODEL_PRICES). The file
 * keeps its first name, and so do the D1 table (meta_budget), the events
 * column (meta_cost_usd) and the log events (meta_call, meta_retry): until
 * 2026-11-15 these calls went to Meta's muse-spark-1.3.
 */

export const ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages';
export const ANTHROPIC_VERSION = '2026-10-21';
export const MATCH_MODEL = 'claude-opus-5-5';
/**
 * USD per 1M tokens (same table as pickfit/meta.py). cacheWrite is the 5-minute prompt cache, 1.25 times input.
 * The product always calls MATCH_MODEL; Settings.matchModel picks another model from this table only for a bench run
 * (worker/bench/capability.ts --model-id), so a cost is never counted at the wrong price.
 */
export const MODEL_PRICES: Record<string, { input: number; cacheRead: number; cacheWrite: number; output: number }> = {
  'claude-opus-5-5': { input: 4.0, cacheRead: 0.2, cacheWrite: 5.0, output: 20.0 },
  'claude-sonnet-5-5': { input: 2.0, cacheRead: 0.2, cacheWrite: 2.5, output: 10.0 },
};
const priceOf = (model: string) => {
  const price = MODEL_PRICES[model];
  if (!price) throw new Error(`No price for model ${model}; add it to MODEL_PRICES`);
  return price;
};
/** Thinking is always on for this model and shares the limit with the answer (a match answer is about 1,000 tokens). */
export const MAX_OUTPUT_TOKENS = 8000;

export interface Usage {
  /** Every input token: uncached, written to the prompt cache and read from it. */
  input_tokens: number;
  /** Of input_tokens, those read from the prompt cache. */
  cached_tokens: number;
  /** Of input_tokens, those written to the prompt cache. */
  cache_write_tokens: number;
  /** Thinking included; the API does not count it apart. */
  output_tokens: number;
}

export interface ModelResult {
  text: string;
  usage: Usage;
  /** All requests this call sent; an HTTP error costs nothing. */
  costUsd: number;
  latencyMs: number;
  /** HTTP status of each request sent, in order: [200], or [503, 200] after a retry. */
  statuses: (number | null)[];
}

/** refused: the API's safety classifiers, or the model, declined (stop_reason "refusal"). */
export type ModelFailure = 'http' | 'timeout' | 'network' | 'incomplete' | 'refused' | 'no_output';

interface FailureDetail {
  costUsd?: number;
  /** The HTTP status the API returned; null for a timeout or a request that never got a response. */
  status?: number | null;
  /** Worth one retry: see isTransient. */
  transient?: boolean;
  /** How long the API asked us to wait (Retry-After), when it said. */
  retryAfterMs?: number | null;
  statuses?: (number | null)[];
}

export class ModelCallError extends Error {
  readonly kind: ModelFailure;
  /** What the failed call may have cost; recorded as spend. */
  readonly costUsd: number;
  readonly status: number | null;
  readonly transient: boolean;
  readonly retryAfterMs: number | null;
  /** HTTP status of each request sent (null where none came back), in order. */
  readonly statuses: (number | null)[];
  constructor(kind: ModelFailure, message: string, detail: FailureDetail = {}) {
    super(message);
    this.kind = kind;
    this.costUsd = detail.costUsd ?? 0;
    this.status = detail.status ?? null;
    this.transient = detail.transient ?? false;
    this.retryAfterMs = detail.retryAfterMs ?? null;
    this.statuses = detail.statuses ?? [this.status];
  }
}

/** No retry with less than this left of the timeout: a retry that times out is still charged. */
const RETRY_MIN_LEFT_MS = 10_000;
/** Honor Retry-After up to this; asked to wait longer, degrade now. */
const RETRY_AFTER_MAX_MS = 5_000;
/** Jittered wait before the retry when the API gives no Retry-After. */
const BACKOFF_MS = [200, 800] as const;

/** Rate limits and server errors (529 "overloaded" included). A 404 here is a wrong model id, which a retry cannot fix. */
export function isTransient(status: number): boolean {
  return status === 429 || (status >= 500 && status <= 599);
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

export function costUsd(usage: Usage, model = MATCH_MODEL): number {
  const PRICE = priceOf(model);
  const cached = Math.min(usage.cached_tokens, usage.input_tokens);
  const written = Math.min(usage.cache_write_tokens, usage.input_tokens - cached);
  return (
    ((usage.input_tokens - cached - written) * PRICE.input +
      cached * PRICE.cacheRead +
      written * PRICE.cacheWrite +
      usage.output_tokens * PRICE.output) /
    1_000_000
  );
}

/** Upper bound for one call: ~3 characters per input token, every output token used. */
export function estimateCostUsd(requestChars: number, maxOutputTokens = MAX_OUTPUT_TOKENS, model = MATCH_MODEL): number {
  const PRICE = priceOf(model);
  return ((requestChars / 3) * PRICE.input + maxOutputTokens * PRICE.output) / 1_000_000;
}

/** The API reports uncached, cache-written and cache-read input apart; Usage.input_tokens is their sum. */
function readUsage(raw: any): Usage | null {
  const u = raw?.usage;
  if (!u || typeof u.input_tokens !== 'number') return null;
  const cached = u.cache_read_input_tokens ?? 0;
  const written = u.cache_creation_input_tokens ?? 0;
  return {
    input_tokens: u.input_tokens + cached + written,
    cached_tokens: cached,
    cache_write_tokens: written,
    output_tokens: u.output_tokens ?? 0,
  };
}

/** The answer is in the text blocks; thinking blocks may come first and are skipped. */
function outputText(raw: any): string | null {
  const parts: string[] = [];
  for (const block of raw?.content ?? []) {
    if (block?.type === 'text' && typeof block.text === 'string') parts.push(block.text);
  }
  return parts.length ? parts.join('') : null;
}

export interface StructuredRequest {
  instructions: string;
  input: string;
  /** JSON schema of the answer: every object closed (additionalProperties false), a nullable field as anyOf with null. */
  schema: Record<string, unknown>;
  /** Defaults: low effort (this model cannot turn thinking off; effort is the control) and MAX_OUTPUT_TOKENS. */
  effort?: 'low' | 'medium' | 'high';
  maxOutputTokens?: number;
  /**
   * Mark the instructions for the prompt cache (5 minutes). Only worth it for a prefix that is the same from request
   * to request and at least the model's minimum cacheable length (512 tokens on Opus 5.5): the match's instructions;
   * the keyword call's are too short to cache.
   */
  cache?: boolean;
  /** A model from MODEL_PRICES; MATCH_MODEL when absent (the product never sets it). */
  model?: string;
}

export function requestBody(req: StructuredRequest): Record<string, unknown> {
  return {
    model: req.model ?? MATCH_MODEL,
    max_tokens: req.maxOutputTokens ?? MAX_OUTPUT_TOKENS,
    system: req.cache ? [{ type: 'text', text: req.instructions, cache_control: { type: 'ephemeral' } }] : req.instructions,
    messages: [{ role: 'user', content: req.input }],
    output_config: { effort: req.effort ?? 'low', format: { type: 'json_schema', schema: req.schema } },
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
 * One structured call, retried once after a transient HTTP error (429, 5xx)
 * when enough of timeoutMs is left. Never retried: an answer (even one that
 * turns out bad, cut off or refused), a timeout, a network error, or any
 * other status. Throws ModelCallError on anything short of a complete answer.
 */
export async function callModel(apiKey: string, body: Record<string, unknown>, opts: CallOptions): Promise<ModelResult> {
  const clock = opts.clock ?? Date.now;
  const deadline = clock() + opts.timeoutMs;
  const statuses: (number | null)[] = [];
  let spent = 0;
  for (let attempt = 1; ; attempt++) {
    try {
      const result = await callOnce(apiKey, body, deadline - clock(), opts.fetch ?? fetch, clock);
      return { ...result, costUsd: spent + result.costUsd, statuses: [...statuses, ...result.statuses] };
    } catch (err) {
      if (!(err instanceof ModelCallError)) throw err;
      statuses.push(err.status);
      spent += err.costUsd;
      const wait = attempt === 1 ? retryWait(err, opts.random ?? Math.random) : null;
      const leftMs = deadline - clock() - (wait ?? 0);
      if (wait === null || leftMs < RETRY_MIN_LEFT_MS) {
        throw new ModelCallError(err.kind, err.message, {
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
function retryWait(err: ModelCallError, random: () => number): number | null {
  if (!err.transient) return null;
  const jitter = BACKOFF_MS[0] + random() * (BACKOFF_MS[1] - BACKOFF_MS[0]);
  if (err.retryAfterMs === null) return jitter;
  return err.retryAfterMs <= RETRY_AFTER_MAX_MS ? Math.max(err.retryAfterMs, jitter) : null;
}

const outputLimit = (body: Record<string, unknown>) => (typeof body.max_tokens === 'number' ? body.max_tokens : MAX_OUTPUT_TOKENS);

async function callOnce(
  apiKey: string,
  body: Record<string, unknown>,
  timeoutMs: number,
  doFetch: typeof fetch,
  clock: () => number,
): Promise<ModelResult> {
  const started = clock();
  const upperBound = () => estimateCostUsd(JSON.stringify(body).length, outputLimit(body), String(body.model ?? MATCH_MODEL));
  let response: Response;
  try {
    response = await doFetch(ANTHROPIC_URL, {
      method: 'POST',
      headers: { 'x-api-key': apiKey, 'anthropic-version': ANTHROPIC_VERSION, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(Math.max(1, timeoutMs)),
    });
  } catch (err) {
    const timedOut = err instanceof Error && (err.name === 'TimeoutError' || err.name === 'AbortError');
    // A timed-out request may still be billed; charge the upper bound.
    throw new ModelCallError(timedOut ? 'timeout' : 'network', String(err), { costUsd: timedOut ? upperBound() : 0 });
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
    const code = raw?.error?.type ?? 'unknown';
    throw new ModelCallError('http', `Anthropic API ${status} ${code}`, {
      status,
      transient: isTransient(status),
      retryAfterMs: retryAfterMs(response.headers, clock()),
    });
  }
  const usage = readUsage(raw);
  const cost = usage ? costUsd(usage, String(body.model ?? MATCH_MODEL)) : upperBound();
  // stop_reason comes before content: a refusal or a cut-off answer is a 200 whose text is not an answer.
  const stop = raw?.stop_reason;
  if (stop === 'refusal') {
    const category = typeof raw?.stop_details?.category === 'string' ? ` (${raw.stop_details.category})` : '';
    throw new ModelCallError('refused', `stop_reason refusal${category}`, { costUsd: cost, status });
  }
  if (stop !== 'end_turn') {
    throw new ModelCallError('incomplete', `stop_reason ${stop ?? 'missing'}`, { costUsd: cost, status });
  }
  const text = outputText(raw);
  if (!text || !usage) throw new ModelCallError('no_output', 'no output text or usage', { costUsd: cost, status });
  return { text, usage, costUsd: cost, latencyMs, statuses: [status] };
}
