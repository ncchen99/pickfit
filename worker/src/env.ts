/** Bindings and settings (wrangler.jsonc vars; MODEL_API_KEY is a secret). */
export interface Env {
  DB: D1Database;
  /** Meta Model API key. Missing means find_software ranks by rules. */
  MODEL_API_KEY?: string;
  /** "model" (default) or "off" to rank by rules without calling Meta. */
  MATCH_MODE?: string;
  META_DAILY_CAP_USD?: string;
  META_TOTAL_CAP_USD?: string;
  META_TIMEOUT_MS?: string;
  /** Comma-separated extra Host names to accept, e.g. the workers.dev host. */
  ALLOWED_HOSTS?: string;
  /** New submit_software submissions accepted per hour, across everyone. */
  SUBMIT_HOURLY_CAP?: string;
}

export interface Settings {
  modelEnabled: boolean;
  apiKey: string | null;
  dailyCapUsd: number;
  totalCapUsd: number;
  timeoutMs: number;
  submitHourlyCap: number;
}

function number(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return value !== undefined && value.trim() !== '' && Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

export function settings(env: Env): Settings {
  return {
    modelEnabled: (env.MATCH_MODE ?? 'model').trim().toLowerCase() !== 'off',
    apiKey: env.MODEL_API_KEY?.trim() || null,
    dailyCapUsd: number(env.META_DAILY_CAP_USD, 3),
    totalCapUsd: number(env.META_TOTAL_CAP_USD, 40),
    timeoutMs: number(env.META_TIMEOUT_MS, 25_000),
    submitHourlyCap: number(env.SUBMIT_HOURLY_CAP, 20),
  };
}
