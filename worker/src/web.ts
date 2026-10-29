/**
 * The product web page (P5.7): GET / for browsers and POST /search. A search
 * runs the MCP's own findSoftware, then installGuide for each pick, so the
 * page and the agents cannot drift apart. GET / without Accept: text/html is
 * still the JSON health check, and WEB_SEARCH=off leaves the Worker as it was.
 *
 * What the page adds is only what a public search box needs:
 * - a per-visitor rate limit, keyed by a hash of the day and the IP, held only
 *   in the rate limiter's counters (never in D1 or logs);
 * - a lower daily Meta cap than the MCP's (WEB_DAILY_CAP_USD): web searches
 *   stop calling the model once today's spend reaches it, leaving the rest of
 *   META_DAILY_CAP_USD for agents, and are then ranked by rules and say so;
 * - a 10-minute in-memory cache of identical searches (this isolate only;
 *   the MCP path never reads it).
 * Shown install guides are not logged as install_guide events: the person has
 * not picked a tool yet, and that event means a pick in the MCP flow.
 */
import { validateHostHeader, validateOriginHeader } from '@modelcontextprotocol/server';
import { utcDay } from './budget.ts';
import type { Catalog } from './catalog.ts';
import { settings, webSettings, type Env } from './env.ts';
import { findSoftware, type Deps } from './find.ts';
import { installGuide, type InstallOutput } from './install.ts';
import { catalogStats, EMPTY_FORM, renderNotice, renderPage, renderResults, type FormValues, type SearchResult } from './page.ts';
import { findInput } from './server.ts';

/** Searches per visitor per minute; wrangler.jsonc's WEB_RATE_LIMITER uses the same number. */
export const SEARCHES_PER_MINUTE = 6;
export const CACHE_TTL_MS = 10 * 60_000;
const CACHE_MAX = 64;
const BODY_MAX = 4096;

export interface WebOptions {
  /** Test hook: replaces global fetch for the Meta call. */
  fetch?: typeof fetch;
  now?: () => Date;
}

const OS_VALUES = new Set(['macos', 'linux', 'windows']);
const ARCH_VALUES = new Set(['arm64', 'x86_64']);
const yes = (value: string | null) => value === '1' || value === 'on' || value === 'true';

/** Form fields (or the same names in a ?query, to prefill the page). Unknown values are dropped. */
export function formFrom(params: URLSearchParams): FormValues {
  const os = params.get('os') ?? '';
  const arch = params.get('arch') ?? '';
  return {
    need: (params.get('need') ?? '').trim().slice(0, 500),
    os: OS_VALUES.has(os) ? (os as FormValues['os']) : '',
    arch: ARCH_VALUES.has(arch) ? (arch as FormValues['arch']) : '',
    free_only: yes(params.get('free_only')),
    offline: yes(params.get('offline')),
  };
}

/** find_software's arguments for a form, before the same zod check the MCP tool uses. */
export function toFindArgs(form: FormValues): Record<string, unknown> {
  return {
    need: form.need,
    ...(form.os ? { os: form.os } : {}),
    ...(form.arch ? { arch: form.arch } : {}),
    ...(form.free_only ? { budget: 'free_only' } : {}),
    ...(form.offline ? { must_run_locally: true } : {}),
  };
}

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function csp(nonce: string | null): string {
  const inline = nonce ? `'nonce-${nonce}'` : `'none'`;
  return `default-src 'none'; script-src ${inline}; style-src ${inline}; img-src data:; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`;
}

function html(body: string, status: number, nonce: string | null, extra: Record<string, string> = {}): Response {
  return new Response(body, {
    status,
    headers: {
      'content-type': 'text/html; charset=utf-8',
      'cache-control': 'no-store',
      'content-security-policy': csp(nonce),
      'x-content-type-options': 'nosniff',
      'referrer-policy': 'no-referrer',
      ...extra,
    },
  });
}

const newNonce = () => crypto.randomUUID().replace(/-/g, '');
const wantsHtml = (request: Request) => (request.headers.get('accept') ?? '').includes('text/html');

export function makeWeb(catalog: Catalog, options: WebOptions = {}) {
  const stats = catalogStats(catalog);
  const now = options.now ?? (() => new Date());
  const cache = new Map<string, { at: number; result: SearchResult }>();
  /** Without the rate limiting binding: request times per hashed visitor key, this isolate only. */
  const recent = new Map<string, number[]>();

  function page(origin: string, form: FormValues, results: string, status = 200, extra: Record<string, string> = {}): Response {
    const nonce = newNonce();
    return html(renderPage({ nonce, origin, stats, form, results }), status, nonce, extra);
  }

  async function allow(request: Request, env: Env): Promise<boolean> {
    const ip = request.headers.get('cf-connecting-ip') ?? 'unknown';
    const key = (await sha256(`${utcDay(now())} ${ip}`)).slice(0, 32);
    if (env.WEB_RATE_LIMITER) {
      try {
        return (await env.WEB_RATE_LIMITER.limit({ key })).success;
      } catch (err) {
        // The web's daily Meta cap still bounds spend, so a broken limiter does not take the page down.
        console.error(JSON.stringify({ event: 'web_rate_limit_failed', error: String(err) }));
        return true;
      }
    }
    const t = now().getTime();
    const times = (recent.get(key) ?? []).filter((at) => t - at < 60_000);
    const ok = times.length < SEARCHES_PER_MINUTE;
    if (ok) times.push(t);
    recent.set(key, times);
    if (recent.size > 1000) {
      for (const [k, v] of recent) if (!v.some((at) => t - at < 60_000)) recent.delete(k);
    }
    return ok;
  }

  function guidesFor(result: SearchResult['out'], form: FormValues): Record<string, InstallOutput> {
    const guides: Record<string, InstallOutput> = {};
    for (const pick of result.picks) {
      // No OS given: show the steps of the run pickfit has, labelled with where they ran.
      const os = form.os || pick.verification.os;
      if (!os) continue;
      guides[pick.slug] = installGuide(catalog, { slug: pick.slug, os, arch: form.arch || undefined, rec_id: result.rec_id });
    }
    return guides;
  }

  async function search(request: Request, env: Env, ctx: ExecutionContext, hosts: string[]): Promise<Response> {
    const url = new URL(request.url);
    // Same DNS-rebinding and cross-site checks as /mcp: another site's form cannot spend the budget.
    const host = validateHostHeader(request.headers.get('host') ?? url.host, hosts);
    const origin = validateOriginHeader(request.headers.get('origin'), hosts);
    if (!host.ok || !origin.ok) return new Response('Forbidden', { status: 403 });

    const fragment = request.headers.get('x-pickfit-fragment') === '1';
    const respond = (form: FormValues, body: string, status = 200, extra: Record<string, string> = {}) =>
      fragment ? html(body, status, null, extra) : page(url.origin, form, body, status, extra);

    const text = await request.text();
    if (text.length > BODY_MAX) return respond(EMPTY_FORM, renderNotice('error', 'That request is too long', 'Describe what you need in up to 500 characters.'), 413);
    const form = formFrom(new URLSearchParams(text));
    const parsed = findInput.safeParse(toFindArgs(form));
    if (!parsed.success) {
      return respond(form, renderNotice('error', 'Describe what you need', 'Write 3 to 500 characters about the job you want done, then search again.'), 400);
    }

    const t = now().getTime();
    const key = await sha256(JSON.stringify([form.need.toLowerCase().replace(/\s+/g, ' '), form.os, form.arch, form.free_only, form.offline]));
    const hit = cache.get(key);
    if (hit && t - hit.at < CACHE_TTL_MS) {
      console.log(JSON.stringify({ event: 'web_search', cached: true, picks: hit.result.out.picks.length }));
      return respond(form, renderResults(hit.result, form, catalog, { cached: true }));
    }

    if (!(await allow(request, env))) {
      console.log(JSON.stringify({ event: 'web_rate_limited' }));
      return respond(
        form,
        renderNotice('busy', 'Busy: too many searches from here', 'Each search asks a Meta model, so pickfit limits how often one connection can search. Try again in a minute.'),
        429,
        { 'retry-after': '60' },
      );
    }

    const config = settings(env);
    const deps: Deps = {
      catalog,
      db: env.DB,
      settings: { ...config, dailyCapUsd: Math.min(config.dailyCapUsd, webSettings(env).dailyCapUsd) },
      now,
      waitUntil: (promise) => ctx.waitUntil(promise),
      fetch: options.fetch,
      client: 'web',
    };
    const out = await findSoftware(parsed.data, deps);
    const result: SearchResult = { out, guides: guidesFor(out, form) };
    // A degraded answer is not kept: the next identical search should get to try the model again.
    if (!out.degraded) {
      cache.set(key, { at: t, result });
      for (const [k, v] of cache) if (cache.size > CACHE_MAX || t - v.at >= CACHE_TTL_MS) cache.delete(k);
    }
    console.log(JSON.stringify({ event: 'web_search', cached: false, picks: out.picks.length, degraded_reason: out.degraded_reason }));
    return respond(form, renderResults(result, form, catalog));
  }

  return {
    /** The page's response, or null when the request is not the page's (the Worker then answers as before). */
    async fetch(request: Request, env: Env, ctx: ExecutionContext, hosts: string[]): Promise<Response | null> {
      if (!webSettings(env).enabled) return null;
      const url = new URL(request.url);
      if (url.pathname === '/') {
        if (request.method !== 'GET' || !wantsHtml(request)) return null;
        return page(url.origin, formFrom(url.searchParams), '', 200, { vary: 'Accept' });
      }
      if (url.pathname !== '/search') return null;
      if (request.method === 'GET') return new Response(null, { status: 303, headers: { location: '/' } });
      if (request.method !== 'POST') return new Response('Method not allowed', { status: 405, headers: { allow: 'POST' } });
      return search(request, env, ctx, hosts);
    },
  };
}
