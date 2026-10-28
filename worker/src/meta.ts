/**
 * The Worker's only model call: Meta Responses API, muse-spark-1.3.
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
  costUsd: number;
  latencyMs: number;
}

export type MetaFailure = 'http' | 'timeout' | 'network' | 'incomplete' | 'no_output';

export class MetaCallError extends Error {
  readonly kind: MetaFailure;
  /** What the failed call may have cost; charged to the budget. */
  readonly costUsd: number;
  constructor(kind: MetaFailure, message: string, costUsd = 0) {
    super(message);
    this.kind = kind;
    this.costUsd = costUsd;
  }
}

export function costUsd(usage: Usage): number {
  const cached = Math.min(usage.cached_tokens, usage.input_tokens);
  return (
    ((usage.input_tokens - cached) * PRICE.input + cached * PRICE.cached + usage.output_tokens * PRICE.output) /
    1_000_000
  );
}

/** Upper bound for one call: ~3 characters per input token, every output token used. */
export function estimateCostUsd(requestChars: number): number {
  return ((requestChars / 3) * PRICE.input + MAX_OUTPUT_TOKENS * PRICE.output) / 1_000_000;
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
}

export function requestBody(req: StructuredRequest): Record<string, unknown> {
  return {
    model: MATCH_MODEL,
    store: false,
    reasoning: { effort: 'low' },
    max_output_tokens: MAX_OUTPUT_TOKENS,
    input: [
      { role: 'developer', content: req.instructions },
      { role: 'user', content: req.input },
    ],
    text: { format: { type: 'json_schema', name: req.schemaName, schema: req.schema, strict: true } },
  };
}

/** One structured call. Throws MetaCallError on anything short of a complete answer. */
export async function callMeta(
  apiKey: string,
  body: Record<string, unknown>,
  opts: { timeoutMs: number; fetch?: typeof fetch },
): Promise<MetaResult> {
  const doFetch = opts.fetch ?? fetch;
  const started = Date.now();
  let response: Response;
  try {
    response = await doFetch(`${META_BASE_URL}/responses`, {
      method: 'POST',
      headers: { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(opts.timeoutMs),
    });
  } catch (err) {
    const timedOut = err instanceof Error && (err.name === 'TimeoutError' || err.name === 'AbortError');
    // A timed-out request may still be billed; charge the upper bound.
    const charge = timedOut ? estimateCostUsd(JSON.stringify(body).length) : 0;
    throw new MetaCallError(timedOut ? 'timeout' : 'network', String(err), charge);
  }
  const latencyMs = Date.now() - started;
  const raw: any = await response.json().catch(() => null);
  if (!response.ok) {
    const code = raw?.error?.code ?? raw?.error?.type ?? 'unknown';
    throw new MetaCallError('http', `Meta API ${response.status} ${code}`);
  }
  const usage = readUsage(raw);
  const cost = usage ? costUsd(usage) : estimateCostUsd(JSON.stringify(body).length);
  if (raw?.status !== 'completed') {
    throw new MetaCallError('incomplete', `response status ${raw?.status ?? 'missing'}`, cost);
  }
  const text = outputText(raw);
  if (!text || !usage) throw new MetaCallError('no_output', 'no output text or usage', cost);
  return { text, usage, costUsd: cost, latencyMs };
}
