/**
 * The web page in English or Traditional Chinese (zh-TW). Only the page is
 * bilingual: the MCP tools, find_software's own sentences and every log stay
 * English, because nothing outside withLang() ever sees another language.
 *
 * How a page picks its language: ?lang=zh-TW or ?lang=en (remembered in a
 * cookie), else that cookie, else the browser's Accept-Language (zh-* means
 * zh-TW). Rendering is synchronous, so withLang() sets the language for one
 * render and puts the previous one back; it must never span an await.
 *
 * The data: data/i18n/zh-TW/<slug>.json maps a tool's English sentences
 * (summary, features, step purposes, run notes…) to Chinese, written by
 * scripts/translate_zh.py. localize() swaps a sentence only when that tool's
 * map has exactly that English text, so a record that changed since it was
 * translated shows its new English, never a stale translation. Commands,
 * names, URLs, tags and every value the code branches on are never swapped.
 */
import type { Catalog, Entry } from './catalog.ts';

export type Lang = 'en' | 'zh-TW';
export const LANGS: readonly Lang[] = ['en', 'zh-TW'];
export const LANG_COOKIE = 'pickfit_lang';

/** Per tool slug: English sentence -> zh-TW sentence. */
export type Translations = Record<string, Record<string, string>>;

let current: Lang = 'en';

/** The language of the render in progress ('en' outside withLang). */
export const lang = (): Lang => current;
export const isZh = () => current === 'zh-TW';

/** The visible text in the render's language. */
export const L = (en: string, zh: string): string => (current === 'zh-TW' ? zh : en);

/** Run one synchronous render in `language`, then put the previous language back. */
export function withLang<T>(language: Lang, render: () => T): T {
  const previous = current;
  current = language;
  try {
    return render();
  } finally {
    current = previous;
  }
}

/** ?lang= first (and whether to remember it), then the cookie, then Accept-Language. */
export function pickLang(request: Request): { lang: Lang; remember: boolean } {
  const asked = normalize(new URL(request.url).searchParams.get('lang'));
  if (asked) return { lang: asked, remember: true };
  const cookie = (request.headers.get('cookie') ?? '')
    .split(';')
    .map((part) => part.trim().split('='))
    .find(([name]) => name === LANG_COOKIE)?.[1];
  const saved = normalize(cookie ? decodeURIComponent(cookie) : null);
  if (saved) return { lang: saved, remember: false };
  const accept = (request.headers.get('accept-language') ?? '').toLowerCase();
  const first = accept.split(',')[0]?.trim() ?? '';
  return { lang: first.startsWith('zh') ? 'zh-TW' : 'en', remember: false };
}

function normalize(value: string | null): Lang | null {
  const v = (value ?? '').trim().toLowerCase();
  if (v === 'en') return 'en';
  if (v === 'zh-tw' || v === 'zh' || v === 'zh-hant') return 'zh-TW';
  return null;
}

export const langCookie = (language: Lang) => `${LANG_COOKIE}=${language}; Path=/; Max-Age=31536000; SameSite=Lax; Secure`;

/** Keys whose values are commands, names, ids, URLs or values the code compares: never translated. */
const KEEP = new Set([
  'slug', 'name', 'repo', 'repo_url', 'homepage', 'url', 'evidence_url', 'command', 'commands', 'launch', 'snippet',
  'json', 'claude_code', 'first_task', 'expected_signal', 'expected_contains', 'observed_excerpt', 'readme_said',
  'tags', 'kind', 'category', 'level', 'os', 'arch', 'method', 'runner', 'tier', 'screen', 'transport', 'check',
  'status', 'failure', 'replay', 'processing', 'pricing', 'license', 'platforms', 'tools', 'called_tool', 'field',
  'value', 'alternatives_to', 'runtimes', 'system_packages', 'clip', 'file', 'raw', 'id', 'run_id', 'browser',
  'third_party_hosts', 'data_sent', 'offline', 'match', 'quality', 'formula_version', 'server_name',
  'client', 'display', 'reason', 'basis', 'maturity', 'audience', 'unverified_reason', 'works_offline', 'gpu', 'microphone', 'tool_version', 'checked_at', 'recorded_at', 'built_at', 'kind_label',
]);

/** A deep copy of `value` with every sentence `map` knows put in Chinese; anything else is returned as is. */
export function translateWith<T>(map: Record<string, string> | undefined, value: T): T {
  if (!map) return value;
  const walk = (v: unknown): unknown => {
    if (typeof v === 'string') return map[v] ?? v;
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === 'object') {
      const out: Record<string, unknown> = {};
      for (const [k, x] of Object.entries(v)) out[k] = KEEP.has(k) ? x : walk(x);
      return out;
    }
    return v;
  };
  return walk(value) as T;
}

/** The catalog with each entry's sentences in Chinese, for the zh-TW pages (search still runs on the English one). */
export function localizedCatalog(catalog: Catalog, translations: Translations): Catalog {
  const entries: Entry[] = catalog.entries.map((entry) => translateWith(translations[entry.slug], entry));
  return { ...catalog, entries, bySlug: new Map(entries.map((entry) => [entry.slug, entry])) };
}
