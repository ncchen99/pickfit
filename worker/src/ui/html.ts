/** Escaping and links: every value from the data or the model goes through esc(); links must be http(s). */

const ESC: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function esc(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
}

/** Only http(s) URLs become links; anything else (javascript:, data:, garbage) is dropped. */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : null;
  } catch {
    return null;
  }
}

/** An outside link that opens in a new tab. `text` must already be escaped. */
export function link(url: string | null | undefined, text: string, cls = ''): string {
  const href = safeUrl(url);
  return href ? `<a${cls ? ` class="${cls}"` : ''} href="${esc(href)}" target="_blank" rel="noopener noreferrer">${text}</a>` : '';
}

export function listOf(items: string[]): string {
  return items.length <= 1 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** A slug as it may appear in a path: the catalog's own shape, nothing else. */
export const SLUG = /^[a-z0-9][a-z0-9._-]{0,99}$/;
