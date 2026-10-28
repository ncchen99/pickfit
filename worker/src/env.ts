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
  /** "all" (default) or "readonly": find_software, find_alternatives and get_install_guide only. */
  TOOLS?: string;
}

export type ToolSet = 'all' | 'readonly';

export interface Settings {
  modelEnabled: boolean;
  apiKey: string | null;
  dailyCapUsd: number;
  totalCapUsd: number;
  timeoutMs: number;
  submitHourlyCap: number;
  tools: ToolSet;
}

function number(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return value !== undefined && value.trim() !== '' && Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

/** Unset or "all" exposes every tool; any other value is read-only, so a typo never exposes the write tools. */
function toolSet(value: string | undefined): ToolSet {
  const v = (value ?? '').trim().toLowerCase();
  return v === '' || v === 'all' ? 'all' : 'readonly';
}

export function settings(env: Env): Settings {
  return {
    modelEnabled: (env.MATCH_MODE ?? 'model').trim().toLowerCase() !== 'off',
    apiKey: env.MODEL_API_KEY?.trim() || null,
    dailyCapUsd: number(env.META_DAILY_CAP_USD, 3),
    totalCapUsd: number(env.META_TOTAL_CAP_USD, 40),
    timeoutMs: number(env.META_TIMEOUT_MS, 25_000),
    submitHourlyCap: number(env.SUBMIT_HOURLY_CAP, 20),
    tools: toolSet(env.TOOLS),
  };
}
