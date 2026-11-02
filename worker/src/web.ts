/**
 * The product web page (P5.7): GET / for browsers and POST /search. A search
 * runs the MCP's own findSoftware, then installGuide for each pick, so the
 * page and the agents cannot drift apart. GET / without Accept: text/html is
 * still the JSON health check, and WEB_SEARCH=off leaves the Worker as it was.
 *
 * What the page adds is only what a public search box needs:
 * - a per-visitor rate limit, keyed by a hash of the day and the IP (an IPv6
 *   address by its /64), held only in the rate limiter's counters (never in D1
 *   or logs);
 * - a lower daily Meta cap than the MCP's (WEB_DAILY_CAP_USD): before calling
 *   the model a search reserves its worst-case cost against that cap and the
 *   total cap in one D1 statement, so concurrent searches cannot all pass the
 *   check before any records spend; the rest of META_DAILY_CAP_USD stays for
 *   agents. Without a reservation the search is ranked by rules and says why;
 * - at most MAX_IN_FLIGHT model searches at once in an isolate; identical
 *   searches in flight share one call, and finished ones are kept 10 minutes
 *   (this isolate only; the MCP path never reads any of it).
 * Shown install guides are not logged as install_guide events: the person has
 * not picked a tool yet, and that event means a pick in the MCP flow.
 */
import { validateHostHeader, validateOriginHeader } from '@modelcontextprotocol/server';
import { checkBudget, releaseSpend, reserveSpend, utcDay } from './budget.ts';
import type { Catalog } from './catalog.ts';
import { settings, webSettings, type Env } from './env.ts';
import { findSoftware, type Deps } from './find.ts';
import { estimateCostUsd } from './meta.ts';
import { L, langCookie, localizedCatalog, pickLang, translateWith, withLang, type Lang, type Translations } from './i18n.ts';
import { installGuide, type InstallOutput } from './install.ts';
import { catalogShowcase, EMPTY_FORM, renderNotice, renderPage, renderResults, type BudgetStop, type FormValues, type SearchResult } from './page.ts';
import { renderBrowse } from './pages/browse.ts';
import { renderCompare } from './pages/compare.ts';
import { renderAgents, renderHow, renderNotFound } from './pages/info.ts';
import { renderTool } from './pages/tool.ts';
import { findInput } from './server.ts';
import { osName } from './ui/facts.ts';
import { SLUG } from './ui/html.ts';

/** Searches per visitor per minute; wrangler.jsonc's WEB_RATE_LIMITER uses the same number. */
export const SEARCHES_PER_MINUTE = 6;
export const CACHE_TTL_MS = 10 * 60_000;
const CACHE_MAX = 64;
/** Bytes: a 500-character need is up to 6,000 bytes once percent-encoded (4-byte characters), plus the other fields. */
export const BODY_MAX_BYTES = 8192;
/** The need, counted in characters (code points), as the page says. */
export const NEED_MIN = 3;
export const NEED_MAX = 500;
/** Model searches running at once in one isolate; the reservation bounds spend across isolates. */
export const MAX_IN_FLIGHT = 6;
/**
 * Held per search, covering both of its Meta calls: the match for a 150,000-character request (today's
 * 60 cards are about 84,000) and, when more than 60 tools pass, the keyword call (expand.ts: under
 * 8,000 characters, at most 600 output tokens).
 */
export const WEB_RESERVE_USD = estimateCostUsd(150_000) + estimateCostUsd(8_000, 600);

export interface WebOptions {
  /** Test hook: replaces global fetch for the Meta call. */
  fetch?: typeof fetch;
  now?: () => Date;
  /** The zh-TW sentences of each tool (generated/zh-TW.json); without them the zh-TW page shows the data in English. */
  translations?: Translations;
}

const OS_VALUES = new Set(['macos', 'linux', 'windows']);
const ARCH_VALUES = new Set(['arm64', 'x86_64']);
const yes = (value: string | null) => value === '1' || value === 'on' || value === 'true';

/** The posted form. Unknown values are dropped; the need is checked, not cut. (No ?need= prefill: request URLs reach Workers logs.) */
export function formFrom(params: URLSearchParams): FormValues {
  const os = params.get('os') ?? '';
  const arch = params.get('arch') ?? '';
  return {
    need: (params.get('need') ?? '').trim(),
    os: OS_VALUES.has(os) ? (os as FormValues['os']) : '',
    arch: ARCH_VALUES.has(arch) ? (arch as FormValues['arch']) : '',
    free_only: yes(params.get('free_only')),
    offline: yes(params.get('offline')),
    private: yes(params.get('private')),
  };
}

/** find_software's arguments for a form, before the same zod check the MCP tool uses. */
export function toFindArgs(form: FormValues): Record<string, unknown> {
  return {
    need: form.need,
    ...(form.os ? { os: form.os } : {}),
    ...(form.arch ? { arch: form.arch } : {}),
    ...(form.free_only ? { budget: 'free_only' } : {}),
    ...(form.offline && form.private ? { must_run_locally: true } : form.offline ? { offline: true } : form.private ? { data_stays_local: true } : {}),
  };
}

/** The rate limiter's subject: an IPv4 address, or an IPv6 address's /64 (one household or host can hold all of it). */
export function visitorKey(ip: string): string {
  const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/i.exec(ip);
  if (mapped) return mapped[1];
  if (!ip.includes(':')) return ip;
  const [head, tail] = ip.toLowerCase().split('::');
  const front = head ? head.split(':') : [];
  const back = tail !== undefined && tail ? tail.split(':') : [];
  const groups = tail === undefined ? front : [...front, ...Array(Math.max(0, 8 - front.length - back.length)).fill('0'), ...back];
  return `${groups.slice(0, 4).map((g) => g.padStart(4, '0')).join(':')}::/64`;
}

/** The body as text, or null when it is over `max` bytes; stops reading as soon as it is. */
async function readBody(request: Request, max: number): Promise<string | null> {
  if (Number(request.headers.get('content-length') ?? 0) > max) return null;
  if (!request.body) return '';
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > max) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let at = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, at);
    at += chunk.byteLength;
  }
  return new TextDecoder().decode(bytes);
}

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function csp(nonce: string | null): string {
  const inline = nonce ? `'nonce-${nonce}'` : `'none'`;
  // Fitz, the icons and the font are this Worker's own static assets (worker/public/assets).
  return `default-src 'none'; script-src ${inline}; style-src ${inline}; img-src 'self' data:; media-src 'self'; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`;
}

function html(body: string, status: number, nonce: string | null, extra: Record<string, string> = {}): Response {
  return new Response(body, {
    status,
    headers: {
      'content-type': 'text/html; charset=utf-8',
      'cache-control': 'no-store',
      // The language comes from ?lang=, the cookie or Accept-Language (i18n.ts).
      vary: 'Accept, Cookie, Accept-Language',
      'content-security-policy': csp(nonce),
      'x-content-type-options': 'nosniff',
      'referrer-policy': 'no-referrer',
      ...extra,
    },
  });
}

const newNonce = () => crypto.randomUUID().replace(/-/g, '');
const COUNT = new Intl.NumberFormat('en');

/** A search's result, and why the model was not asked when the web's reservation was refused. */
interface Searched {
  result: SearchResult;
  budget: BudgetStop | null;
}
const wantsHtml = (request: Request) => (request.headers.get('accept') ?? '').includes('text/html');

const ZH_CLAIM: Record<string, string> = {
  'No install: it opens in a browser': '免安裝：用瀏覽器就能開啟',
  'pickfit opened it in a browser and checked it': 'pickfit 已在瀏覽器中開啟並檢查過',
  'Works offline once loaded (checked)': '載入後可離線使用（已檢查）',
  'What you type stayed on your device in pickfit’s check': '在 pickfit 的檢查中，你輸入的內容都留在你的裝置上',
  'Free to use': '免費使用',
  'Install steps were run and checked by pickfit': '安裝步驟已由 pickfit 執行並檢查',
  'Runs on your machine without a cloud service': '在你的電腦上執行，不需要雲端服務',
};

/** The rules path's reasons (rules.ts templateReasons) in zh-TW; a model-written reason returns null and stays as written. */
export function zhRuleClaim(claim: string, map: Record<string, string> | undefined): string | null {
  if (ZH_CLAIM[claim]) return ZH_CLAIM[claim];
  const useCase = /^Use case: (.+)$/s.exec(claim);
  if (useCase) return `用途：${map?.[useCase[1]] ?? useCase[1]}`;
  const ranOn = /^Install steps were run and checked on (macos|linux|windows)$/.exec(claim);
  if (ranOn) return `安裝步驟已在 ${osName(ranOn[1] as 'macos')} 上執行並檢查`;
  return null;
}

export function makeWeb(catalog: Catalog, options: WebOptions = {}) {
  const showcase = catalogShowcase(catalog);
  // The zh-TW pages read a copy of the catalog with each tool's sentences in Chinese; search always runs on `catalog`.
  const translations = options.translations ?? {};
  let zh: { catalog: Catalog; showcase: ReturnType<typeof catalogShowcase> } | null = null;
  const view = (lang: Lang) => {
    if (lang === 'en') return { catalog, showcase };
    if (!zh) {
      const localized = localizedCatalog(catalog, translations);
      zh = { catalog: localized, showcase: catalogShowcase(localized) };
    }
    return zh;
  };
  /** One search's picks and guides with their tools' sentences in the page's language. */
  const localizeResult = (result: SearchResult, lang: Lang): SearchResult =>
    lang === 'en'
      ? result
      : {
          out: {
            ...result.out,
            picks: result.out.picks.map((pick) => {
              const map = translations[pick.slug];
              const why = pick.why.map((reason) => ({ ...reason, claim: zhRuleClaim(reason.claim, map) ?? reason.claim }));
              return translateWith(map, { ...pick, why });
            }),
          },
          guides: Object.fromEntries(Object.entries(result.guides).map(([slug, guide]) => [slug, translateWith(translations[slug], guide)])),
        };
  const now = options.now ?? (() => new Date());
  const cache = new Map<string, { at: number; result: SearchResult }>();
  /** Searches running now, by the same key as the cache: an identical one waits for this result. */
  const running = new Map<string, Promise<Searched | null>>();
  let inFlight = 0;
  /** Without the rate limiting binding: request times per hashed visitor key, this isolate only. */
  const recent = new Map<string, number[]>();

  function page(lang: Lang, origin: string, form: FormValues, results: string, status = 200, extra: Record<string, string> = {}): Response {
    const nonce = newNonce();
    const body = withLang(lang, () => renderPage({ nonce, origin, showcase: view(lang).showcase, form, results }));
    return html(body, status, nonce, extra);
  }

  async function allow(request: Request, env: Env): Promise<boolean> {
    const ip = request.headers.get('cf-connecting-ip') ?? 'unknown';
    const key = (await sha256(`${utcDay(now())} ${visitorKey(ip)}`)).slice(0, 32);
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
    const { lang } = pickLang(request);
    const shown = view(lang).catalog;
    /** `body` renders in the page's language; it must be synchronous (i18n.ts). */
    const respond = (form: FormValues, body: () => string, status = 200, extra: Record<string, string> = {}) => {
      const rendered = withLang(lang, body);
      return fragment ? html(rendered, status, null, extra) : page(lang, url.origin, form, rendered, status, extra);
    };
    const results = (result: SearchResult, form: FormValues, opts: Parameters<typeof renderResults>[3]) => () =>
      renderResults(localizeResult(result, lang), form, shown, opts);

    const text = await readBody(request, BODY_MAX_BYTES);
    if (text === null) {
      return respond(
        EMPTY_FORM,
        () => renderNotice('error', L('That request is too long', '需求太長了'), L(`Describe what you need in up to ${NEED_MAX} characters.`, `請用 ${NEED_MAX} 字以內描述你的需求。`)),
        413,
      );
    }
    const form = formFrom(new URLSearchParams(text));
    const chars = [...form.need].length;
    const parsed = findInput.safeParse(toFindArgs(form));
    if (chars < NEED_MIN || chars > NEED_MAX || !parsed.success) {
      return respond(
        form,
        () => {
          const said = chars > NEED_MAX ? L(`That is ${COUNT.format(chars)} characters. `, `目前是 ${COUNT.format(chars)} 字。`) : '';
          return renderNotice(
            'error',
            L('Describe what you need', '描述你的需求'),
            L(`${said}Write ${NEED_MIN} to ${NEED_MAX} characters about the job you want done, then search again.`, `${said}請用 ${NEED_MIN} 到 ${NEED_MAX} 字描述你想完成的工作，再搜尋一次。`),
          );
        },
        400,
      );
    }

    const t = now().getTime();
    const key = await sha256(JSON.stringify([form.need.toLowerCase().replace(/\s+/g, ' '), form.os, form.arch, form.free_only, form.offline]));
    for (;;) {
      const hit = cache.get(key);
      if (hit && t - hit.at < CACHE_TTL_MS) {
        console.log(JSON.stringify({ event: 'web_search', cached: true, picks: hit.result.out.picks.length }));
        return respond(form, results(hit.result, form, { cached: true }));
      }
      const same = running.get(key);
      if (!same) break;
      const shared = await same;
      if (shared) {
        console.log(JSON.stringify({ event: 'web_search', shared: true, picks: shared.result.out.picks.length }));
        return respond(form, results(shared.result, form, { budget: shared.budget }));
      }
      // The search this one waited for was refused (rate limit or busy): try for itself.
    }

    // Registered before any await, so an identical search arriving now waits for this one.
    let finish!: (searched: Searched | null) => void;
    running.set(key, new Promise((resolve) => (finish = resolve)));
    let searched: Searched;
    try {
      if (!(await allow(request, env))) {
        finish(null);
        console.log(JSON.stringify({ event: 'web_rate_limited' }));
        return respond(
          form,
          () =>
            renderNotice(
              'busy',
              L('Busy: too many searches from here', '忙碌中：這個連線的搜尋次數太多了'),
              L(
                'Each search asks a Meta model, so pickfit limits how often one connection can search. Try again in a minute.',
                '每次搜尋都會詢問 Meta 的模型，所以 pickfit 會限制同一個連線的搜尋頻率。請一分鐘後再試。',
              ),
            ),
          429,
          { 'retry-after': '60' },
        );
      }
      if (inFlight >= MAX_IN_FLIGHT) {
        finish(null);
        console.log(JSON.stringify({ event: 'web_busy', in_flight: inFlight }));
        return respond(
          form,
          () =>
            renderNotice(
              'busy',
              L('Busy: pickfit is answering other searches', '忙碌中：pickfit 正在回答其他搜尋'),
              L('A few searches are running right now. Try again in a few seconds.', '目前有幾個搜尋正在進行，請幾秒後再試。'),
            ),
          503,
          { 'retry-after': '10' },
        );
      }
      inFlight++;
      try {
        searched = await run(parsed.data, form, env, ctx);
      } finally {
        inFlight--;
      }
      finish(searched);
    } catch (err) {
      finish(null);
      throw err;
    } finally {
      running.delete(key);
    }
    const { result, budget } = searched;
    // A degraded answer is not kept: the next identical search should get to try the model again.
    if (!result.out.degraded) {
      cache.set(key, { at: t, result });
      for (const [k, v] of cache) if (cache.size > CACHE_MAX || t - v.at >= CACHE_TTL_MS) cache.delete(k);
    }
    console.log(JSON.stringify({ event: 'web_search', cached: false, picks: result.out.picks.length, degraded_reason: result.out.degraded_reason }));
    return respond(form, results(result, form, { budget }));
  }

  /** One search: reserve the worst-case cost, run find_software, release the hold. */
  async function run(input: Parameters<typeof findSoftware>[0], form: FormValues, env: Env, ctx: ExecutionContext): Promise<Searched> {
    const config = settings(env);
    const now0 = now();
    const day = utcDay(now0);
    const caps = { dailyCapUsd: Math.min(config.dailyCapUsd, webSettings(env).dailyCapUsd), totalCapUsd: config.totalCapUsd };
    let budget: BudgetStop | null = null;
    let held = false;
    if (config.modelEnabled && config.apiKey) {
      try {
        held = await reserveSpend(env.DB, now0, WEB_RESERVE_USD, caps);
        if (!held) {
          const state = await checkBudget(env.DB, now0, WEB_RESERVE_USD, caps);
          budget = state.totalUsd + WEB_RESERVE_USD > caps.totalCapUsd ? 'total' : 'web_daily';
        }
      } catch {
        budget = 'unavailable';
      }
    }
    // With the hold, find_software's own check must not count it a second time; without one, it must not call Meta.
    const ownHold = held ? WEB_RESERVE_USD : 0;
    const deps: Deps = {
      catalog,
      db: env.DB,
      settings: budget
        ? { ...config, dailyCapUsd: 0, totalCapUsd: 0 }
        : { ...config, dailyCapUsd: caps.dailyCapUsd + ownHold, totalCapUsd: caps.totalCapUsd + ownHold },
      now,
      waitUntil: (promise) => ctx.waitUntil(promise),
      fetch: options.fetch,
      client: 'web',
    };
    try {
      const out = await findSoftware(input, deps);
      return { result: { out, guides: guidesFor(out, form) }, budget };
    } finally {
      if (held) await releaseSpend(env.DB, day, WEB_RESERVE_USD).catch((err) => console.error(JSON.stringify({ event: 'web_release_failed', error: String(err) })));
    }
  }

  return {
    /** The page's response, or null when the request is not the page's (the Worker then answers as before). */
    async fetch(request: Request, env: Env, ctx: ExecutionContext, hosts: string[]): Promise<Response | null> {
      if (!webSettings(env).enabled) return null;
      const url = new URL(request.url);
      const { lang, remember } = pickLang(request);
      // ?lang= is remembered for the next pages (and for searches, which post without it).
      const keep: Record<string, string> = remember ? { 'set-cookie': langCookie(lang) } : {};
      const shown = view(lang).catalog;
      const render = (body: (nonce: string) => string, status = 200) => {
        const nonce = newNonce();
        return html(withLang(lang, () => body(nonce)), status, nonce, keep);
      };
      if (url.pathname === '/') {
        if (request.method !== 'GET' || !wantsHtml(request)) return null;
        return page(lang, url.origin, EMPTY_FORM, '', 200, keep);
      }
      if (url.pathname !== '/search') {
        // The catalog pages: read from the bundled index only, no model call and no D1.
        if (request.method !== 'GET' && request.method !== 'HEAD') return null;
        const tool = /^\/tool\/([^/]+)\/?$/.exec(url.pathname);
        if (tool) {
          const slug = decodeURIComponent(tool[1]).toLowerCase();
          const entry = SLUG.test(slug) ? shown.bySlug.get(slug) : undefined;
          return entry ? render((nonce) => renderTool(shown, entry, nonce)) : render((nonce) => renderNotFound(nonce), 404);
        }
        if (url.pathname === '/browse') return render((nonce) => renderBrowse(shown, url.searchParams, nonce));
        if (url.pathname === '/compare') return render((nonce) => renderCompare(shown, url.searchParams, nonce));
        if (url.pathname === '/how') return render((nonce) => renderHow(shown, nonce));
        if (url.pathname === '/agents') return render((nonce) => renderAgents(url.origin, nonce));
        // Anything else a browser asks for gets the not-found page; other clients keep the plain 404.
        return wantsHtml(request) ? render((nonce) => renderNotFound(nonce), 404) : null;
      }
      if (request.method === 'GET') return new Response(null, { status: 303, headers: { location: '/', ...keep } });
      if (request.method !== 'POST') return new Response('Method not allowed', { status: 405, headers: { allow: 'POST' } });
      return search(request, env, ctx, hosts);
    },
  };
}
