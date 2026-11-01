/**
 * The component kit (DESIGN.md section 5): small string helpers that every page
 * shares, so a badge, a tape meter or a notice looks and behaves the same
 * everywhere. Their CSS is in styles.ts. No helper invents a value: a meter
 * with no score says "not scored".
 */
import type { FeaturesOut } from '../features.ts';
import { esc } from './html.ts';
import { icon, type IconName } from './icons.ts';

// ---------------------------------------------------------------- Fitz

/** Fitz's assets (worker/public/assets/fitz, copied from brand/mascot) with their drawn size. */
const FITZ = {
  hello: ['states/fitz-hello.svg', 200, 200],
  idle: ['states/fitz-idle.svg', 200, 200],
  searching: ['states/fitz-searching.svg', 200, 200],
  testing: ['states/fitz-testing.svg', 300, 200],
  recommending: ['states/fitz-recommending.svg', 250, 200],
  'test-failed': ['states/fitz-test-failed.svg', 300, 200],
  success: ['states/fitz-success.svg', 210, 200],
  resting: ['states/fitz-resting.svg', 200, 200],
  comparing: ['states/fitz-comparing.svg', 280, 200],
  neutral: ['expressions/fitz-neutral.svg', 200, 200],
  happy: ['expressions/fitz-happy.svg', 200, 200],
  thinking: ['expressions/fitz-thinking.svg', 200, 200],
  surprised: ['expressions/fitz-surprised.svg', 200, 200],
  sorry: ['expressions/fitz-sorry.svg', 200, 200],
  proud: ['expressions/fitz-proud.svg', 200, 200],
  peek: ['fitz-peek.svg', 200, 112],
} as const;

export type FitzName = keyof typeof FITZ;
export const FITZ_BASE = '/assets/fitz/';
export const ICON_32 = `${FITZ_BASE}icons/fitz-32.svg`;
export const ICON_64 = `${FITZ_BASE}icons/fitz-64.svg`;

/** Fitz at a given height (px). Decorative by default: the text beside it says what happened. */
export function fitz(name: FitzName, height: number, opts: { alt?: string; cls?: string; eager?: boolean } = {}): string {
  const [file, w, h] = FITZ[name];
  const width = Math.round((w / h) * height);
  return (
    `<img class="fitz fitz-${name}${opts.cls ? ` ${opts.cls}` : ''}" src="${FITZ_BASE}${file}" width="${width}" height="${height}" ` +
    `alt="${esc(opts.alt ?? '')}" decoding="async"${opts.eager ? '' : ' loading="lazy"'}>`
  );
}

/** Fitz with a speech bubble: the page's own voice for status and summaries. */
export function says(name: FitzName, body: string, opts: { role?: 'status' | 'alert'; cls?: string; size?: number } = {}): string {
  return (
    `<div class="says${opts.cls ? ` ${opts.cls}` : ''}"${opts.role ? ` role="${opts.role}"` : ''}>` +
    fitz(name, opts.size ?? 96, { eager: true }) +
    `<div class="bubble">${body}</div></div>`
  );
}

// ---------------------------------------------------------------- small parts

export type BadgeTone = 'pass' | 'gem' | 'free' | 'caution' | 'quiet' | 'fail' | 'info';

/** A badge; `pop` names a popover that explains it. */
export function badge(tone: BadgeTone, text: string, opts: { icon?: IconName; pop?: string; title?: string; cls?: string } = {}): string {
  const cls = `badge badge-${tone}${opts.cls ? ` ${opts.cls}` : ''}`;
  const inner = `${opts.icon ? icon(opts.icon) : ''}${esc(text)}`;
  if (opts.pop) {
    return `<button type="button" class="${cls}" popovertarget="${opts.pop}" aria-label="${esc(text)}: what this means">${inner}</button>`;
  }
  return `<span class="${cls}"${opts.title ? ` title="${esc(opts.title)}"` : ''}>${inner}</span>`;
}

/** A popover (native popover API) and the little "?" that opens it. */
export function popover(id: string, title: string, body: string): string {
  return (
    `<div popover id="${id}" class="pop" role="dialog" aria-label="${esc(title)}">` +
    `<p class="pop-title">${esc(title)}</p>${body}` +
    `<button type="button" class="pop-close" popovertarget="${id}" popovertargetaction="hide" aria-label="Close">${icon('x')}</button></div>`
  );
}

export function helpButton(id: string, label: string): string {
  return `<button type="button" class="help" popovertarget="${id}" aria-label="${esc(label)}">${icon('circle-help')}</button>`;
}

/** A command with a copy button (the button shows once the script runs). */
export function command(text: string): string {
  return `<div class="cmd"><pre translate="no"><code>${esc(text)}</code></pre><button type="button" class="copy" aria-label="Copy command">${icon('copy')}<span>Copy</span></button></div>`;
}

/** The stitch: drawn only on verified evidence. */
export const SEAM = '<div class="seam" aria-hidden="true"></div>';

export function notice(kind: 'busy' | 'error' | 'info', title: string, text: string, who: FitzName): string {
  const role = kind === 'error' ? 'alert' : 'status';
  return (
    `<div class="notice ${kind}" role="${role}">${fitz(who, 88, { eager: true })}` +
    `<div><h2>${esc(title)}</h2><p>${esc(text)}</p></div></div>`
  );
}

// ---------------------------------------------------------------- measurements

/**
 * A measuring-tape meter for a 0–100 score: the reading is on the tape, the number beside it.
 * Drawn in SVG attributes (no inline styles under the CSP); the fill grows in on reveal.
 */
export function tape(label: string, value: number | null, opts: { pop?: string; note?: string; tone?: 'tape' | 'quiet' } = {}): string {
  const head = `<span class="meter-label">${esc(label)}${opts.pop ? helpButton(opts.pop, `About ${label.toLowerCase()}`) : ''}</span>`;
  const ticks: string[] = [];
  for (let x = 10; x < 100; x += 10) ticks.push(`M${x * 2} 0V${x % 50 === 0 ? 9 : 6}`);
  if (value === null) {
    return (
      `<div class="meter meter-none">${head}<svg class="tape" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">` +
      `<rect class="tape-track" x="0" y="0" width="200" height="14" rx="3"/><path class="tape-ticks" d="${ticks.join('')}"/></svg>` +
      `<span class="meter-read">not scored</span></div>`
    );
  }
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    `<div class="meter meter-${opts.tone ?? 'tape'}" role="img" aria-label="${esc(label)}: ${v} out of 100${opts.note ? `, ${esc(opts.note)}` : ''}">${head}` +
    `<svg class="tape" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true"><rect class="tape-track" x="0" y="0" width="200" height="14" rx="3"/>` +
    `<rect class="tape-fill" x="0" y="0" width="${v * 2}" height="14" rx="3"/><path class="tape-ticks" d="${ticks.join('')}"/>` +
    `<path class="tape-mark" d="M${v * 2} -2V16"/></svg>` +
    `<span class="meter-read" aria-hidden="true">${v}</span>${opts.note ? `<span class="meter-note">${esc(opts.note)}</span>` : ''}</div>`
  );
}

/** Features the run exercised vs the README's list: one segmented bar, counts in words beside it. */
export function coverage(features: FeaturesOut, opts: { pop?: string } = {}): string {
  const checked = features.checked.length;
  const failed = features.not_checked.filter((f) => f.reason === 'test_failed').length;
  const open = features.not_checked.length - failed;
  const total = checked + failed + open;
  const label = `<span class="meter-label">Features checked${opts.pop ? helpButton(opts.pop, 'About feature checks') : ''}</span>`;
  if (!features.recorded || total === 0) {
    return `<div class="meter meter-none">${label}<span class="meter-read meter-wide">${total ? 'not checked one by one' : 'no feature list'}</span></div>`;
  }
  const w = (n: number) => (n / total) * 200;
  let x = 0;
  const seg = (n: number, cls: string) => {
    if (!n) return '';
    const out = `<rect class="${cls}" x="${x.toFixed(1)}" y="0" width="${Math.max(0, w(n) - 2).toFixed(1)}" height="14" rx="3"/>`;
    x += w(n);
    return out;
  };
  const words = [`${checked} of ${total} checked`, failed ? `${failed} failed` : ''].filter(Boolean).join(', ');
  return (
    `<div class="meter meter-cov" role="img" aria-label="Features: ${esc(words)}">${label}` +
    `<svg class="tape" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">${seg(checked, 'cov-ok')}${seg(failed, 'cov-fail')}${seg(open, 'cov-open')}</svg>` +
    `<span class="meter-read meter-wide" aria-hidden="true">${esc(words)}</span></div>`
  );
}

/** One at-a-glance cell: an icon, a short label and its value; the tone carries meaning only. */
export function glance(ico: IconName, label: string, value: string, tone: 'pass' | 'caution' | 'fail' | 'quiet' | 'plain' = 'plain'): string {
  return `<div class="gl gl-${tone}">${icon(ico)}<span class="gl-label">${esc(label)}</span><span class="gl-value">${value}</span></div>`;
}

/** The checkbox that puts a tool in the compare tray (the tray is script; without it, the link to /compare works). */
export function compareToggle(slug: string, name: string): string {
  return (
    `<label class="chip chip-compare js-only"><input type="checkbox" data-compare="${esc(slug)}" data-name="${esc(name)}">` +
    `${icon('scale')}<span>Compare</span></label>`
  );
}

/** Relative age of a day, against the catalog's build time so a cached page does not drift. */
export function age(iso: string | null, now: Date): string | null {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const days = Math.max(0, Math.floor((now.getTime() - then.getTime()) / 86_400_000));
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 60) return `${days} days ago`;
  const months = Math.floor(days / 30.4);
  if (months < 24) return `${months} months ago`;
  return `${Math.floor(days / 365)} years ago`;
}
