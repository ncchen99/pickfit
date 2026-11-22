/** Bindings and settings (wrangler.jsonc vars; ANTHROPIC_API_KEY is a secret). */
export interface Env {
  DB: D1Database;
  /** Anthropic API key. Missing means find_software ranks by rules. */
  ANTHROPIC_API_KEY?: string;
  /** "model" (default) or "off" to rank by rules without calling the model. */
  MATCH_MODE?: string;
  /**
   * Optional hard stops on the model spend recorded in D1 meta_budget: USD per UTC day, and in all.
   * Unset (the default) means no stop: spend is still recorded, and nothing blocks a call.
   * These three settings keep the names they had when the model was Meta's (like meta.ts and meta_budget),
   * so a config or a command that sets a stop still stops.
   */
  META_DAILY_CAP_USD?: string;
  META_TOTAL_CAP_USD?: string;
  /** Both tries of a model call and the wait between them fit in this many milliseconds (default 40,000). */
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
  /** Optional: web searches stop calling the model once today's spend reaches this, leaving the rest of a daily cap for agents. Unset = no stop of its own. */
  WEB_DAILY_CAP_USD?: string;
  /** Workers rate limiting binding for web searches (wrangler.jsonc ratelimits); without it, a per-isolate count. */
  WEB_RATE_LIMITER?: RateLimit;
  /**
   * "call" (default) or "skip": whether an English request still gets the model's keyword call before the shortlist
   * cut (expand.ts). Skipping saves one model call in series; on the free shortlist bench (11/20, 316 needs) the
   * need's own tool reached the 50 cards for 94.0% of English needs without keywords against 99.7% with them.
   */
  KEYWORDS_ENGLISH?: string;
  /** R2 bucket pickfit-videos: verification clips at <slug>/<file>. Without it, /video/ answers 404. */
  VIDEOS?: R2Bucket;
  /** Re-runs find_software may queue per UTC day for picks past their re-verification cycle (default 10; 0 = none). */
  REVERIFY_DUE_DAILY_CAP?: string;
}

export type ToolSet = 'all' | 'readonly';

export interface Settings {
  modelEnabled: boolean;
  apiKey: string | null;
  /** USD per UTC day; null = no stop. */
  dailyCapUsd: number | null;
  /** USD in all; null = no stop. */
  totalCapUsd: number | null;
  timeoutMs: number;
  submitHourlyCap: number;
  tools: ToolSet;
  /** KEYWORDS_ENGLISH: skip the keyword call for an English request; absent = call it. */
  skipEnglishKeywords?: boolean;
  /** REVERIFY_DUE_DAILY_CAP: due re-runs queued per UTC day; absent = REVERIFY_DUE_DAILY_CAP's default (10). */
  reverifyDueDailyCap?: number;
  /** A bench run's model (worker/bench/capability.ts --model-id); never read from Env, so the product stays on MATCH_MODEL. */
  matchModel?: string;
}

function number(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return value !== undefined && value.trim() !== '' && Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

/**
 * An opt-in cap: unset or blank is no cap (null). A value that is not a number from 0 up stops at 0,
 * so a typo never lifts a stop someone meant to set.
 */
function cap(value: string | undefined): number | null {
  if (value === undefined || value.trim() === '') return null;
  return number(value, 0);
}

/** Unset or "all" exposes every tool; any other value is read-only, so a typo never exposes the write tools. */
function toolSet(value: string | undefined): ToolSet {
  const v = (value ?? '').trim().toLowerCase();
  return v === '' || v === 'all' ? 'all' : 'readonly';
}

export function settings(env: Env): Settings {
  return {
    modelEnabled: (env.MATCH_MODE ?? 'model').trim().toLowerCase() !== 'off',
    apiKey: env.ANTHROPIC_API_KEY?.trim() || null,
    dailyCapUsd: cap(env.META_DAILY_CAP_USD),
    totalCapUsd: cap(env.META_TOTAL_CAP_USD),
    timeoutMs: number(env.META_TIMEOUT_MS, 40_000),
    submitHourlyCap: number(env.SUBMIT_HOURLY_CAP, 20),
    tools: toolSet(env.TOOLS),
    skipEnglishKeywords: (env.KEYWORDS_ENGLISH ?? '').trim().toLowerCase() === 'skip',
    reverifyDueDailyCap: number(env.REVERIFY_DUE_DAILY_CAP, 10),
  };
}

export interface WebSettings {
  enabled: boolean;
  /** USD per UTC day for web searches; null = no stop of its own. */
  dailyCapUsd: number | null;
}

/** Only "off" turns the page off, so the evaluation deployments say so explicitly. */
export function webSettings(env: Env): WebSettings {
  return {
    enabled: (env.WEB_SEARCH ?? 'on').trim().toLowerCase() !== 'off',
    dailyCapUsd: cap(env.WEB_DAILY_CAP_USD),
  };
}
