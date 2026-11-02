/** Bindings and settings (wrangler.jsonc vars; MODEL_API_KEY is a secret). */
export interface Env {
  DB: D1Database;
  /** Meta Model API key. Missing means find_software ranks by rules. */
  MODEL_API_KEY?: string;
  /** "meta" (default) or "openrouter": reach muse-spark-1.3 through OpenRouter, Meta as the only provider. */
  META_VIA?: string;
  /** OpenRouter API key, used when META_VIA is "openrouter". */
  OPENROUTER_API_KEY?: string;
  /** "model" (default) or "off" to rank by rules without calling Meta. */
  MATCH_MODE?: string;
  META_DAILY_CAP_USD?: string;
  META_TOTAL_CAP_USD?: string;
  META_TIMEOUT_MS?: string;
  /** Comma-separated extra Host names to accept, e.g. the workers.dev host. */
  ALLOWED_HOSTS?: string;
  /** Public host name for people, e.g. pickfit.app: browser page requests on any other public host are redirected there. */
  CANONICAL_HOST?: string;
  /** New submit_software submissions accepted per hour, across everyone. */
  SUBMIT_HOURLY_CAP?: string;
  /** "all" (default) or "readonly": find_software, find_alternatives and get_install_guide only. */
  TOOLS?: string;
  /** "on" (default) or "off": the product web page (GET / for browsers, POST /search). */
  WEB_SEARCH?: string;
  /** Web searches stop calling Meta once today's spend reaches this; the rest of the daily cap is left for agents. */
  WEB_DAILY_CAP_USD?: string;
  /** Workers rate limiting binding for web searches (wrangler.jsonc ratelimits); without it, a per-isolate count. */
  WEB_RATE_LIMITER?: RateLimit;
  /** R2 bucket pickfit-videos: verification clips at <slug>/<file>. Without it, /video/ answers 404. */
  VIDEOS?: R2Bucket;
}

export type ToolSet = 'all' | 'readonly';
export type MetaVia = 'meta' | 'openrouter';

export interface Settings {
  modelEnabled: boolean;
  /** Where the model calls go; apiKey is that route's key. */
  via: MetaVia;
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
  // Only "openrouter" leaves Meta's API, so a typo keeps the calls where they were.
  const via: MetaVia = (env.META_VIA ?? '').trim().toLowerCase() === 'openrouter' ? 'openrouter' : 'meta';
  return {
    modelEnabled: (env.MATCH_MODE ?? 'model').trim().toLowerCase() !== 'off',
    via,
    apiKey: (via === 'openrouter' ? env.OPENROUTER_API_KEY : env.MODEL_API_KEY)?.trim() || null,
    dailyCapUsd: number(env.META_DAILY_CAP_USD, 3),
    totalCapUsd: number(env.META_TOTAL_CAP_USD, 40),
    timeoutMs: number(env.META_TIMEOUT_MS, 25_000),
    submitHourlyCap: number(env.SUBMIT_HOURLY_CAP, 20),
    tools: toolSet(env.TOOLS),
  };
}

export interface WebSettings {
  enabled: boolean;
  dailyCapUsd: number;
}

/** Only "off" turns the page off, so the evaluation deployments say so explicitly. */
export function webSettings(env: Env): WebSettings {
  return {
    enabled: (env.WEB_SEARCH ?? 'on').trim().toLowerCase() !== 'off',
    dailyCapUsd: number(env.WEB_DAILY_CAP_USD, 2),
  };
}
