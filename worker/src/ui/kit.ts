/**
 * The component kit (DESIGN.md section 5): small string helpers that every page
 * shares, so a badge, a tape meter or a notice looks and behaves the same
 * everywhere. Their CSS is in styles.ts. No helper invents a value: a meter
 * with no score says "not scored".
 */
import type { Arch, Entry, GuiEvidence, OS } from '../catalog.ts';
import { operatedText } from '../evidence.ts';
import type { FeaturesOut } from '../features.ts';
import { day, formOf, KIND, osName, system } from './facts.ts';
import { esc, listOf } from './html.ts';
import { icon, osMark, type IconName } from './icons.ts';

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

/**
 * A badge; `pop` names a popover that explains it. `marks` replaces the text with
 * icons (already drawn); the text then shows as a tooltip and is read out instead.
 */
export function badge(tone: BadgeTone, text: string, opts: { icon?: IconName; pop?: string; title?: string; cls?: string; marks?: string } = {}): string {
  const short = opts.marks !== undefined;
  const cls = `badge badge-${tone}${short ? ' badge-short' : ''}${opts.cls ? ` ${opts.cls}` : ''}`;
  const tip = short ? ` data-tip="${esc(opts.title ? `${text}: ${opts.title}` : text)}"` : '';
  const inner = `${opts.icon ? icon(opts.icon) : ''}${short ? `${opts.marks}<span class="sr">${esc(text)}</span>` : esc(text)}`;
  if (opts.pop) {
    return `<button type="button" class="${cls}" popovertarget="${opts.pop}" aria-label="${esc(text)}: what this means"${tip}>${inner}</button>`;
  }
  return `<span class="${cls}"${tip || (opts.title ? ` title="${esc(opts.title)}"` : '')}>${inner}</span>`;
}

// ---------------------------------------------------------------- marks for facts every card repeats

/** An icon per kind of tool, shown before its form ("Command-line tool"); the kind's name is the tooltip. */
const KIND_ICON: Record<string, IconName> = { dev_cli: 'terminal', local_ai: 'cpu', mcp_server: 'plug', other: 'package' };
export const kindIcon = (category: string): IconName => KIND_ICON[category] ?? 'package';

export function kindTag(entry: Pick<Entry, 'kind' | 'category'>): string {
  const kind = KIND[entry.category] ?? '';
  const form = formOf(entry);
  const named = kind && kind.toLowerCase() !== form.toLowerCase();
  return (
    `<span class="kind"${named ? ` data-tip="${esc(kind)}"` : ''}>${icon(kindIcon(entry.category))}` +
    `${named ? `<span class="sr">${esc(kind)}, </span>` : ''}${esc(form.charAt(0).toUpperCase() + form.slice(1))}</span>`
  );
}

/** An icon per verification level, matching levelLabel(): the same evidence always gets the same mark. */
const LEVEL_ICON: Record<string, IconName> = { install: 'power', function: 'play', service: 'server', inference: 'sparkles' };

export function levelIcon(level: string, evidence: { gui?: GuiEvidence | null; mcp?: unknown } = {}): IconName {
  if (evidence.gui) return operatedText(evidence.gui) ? 'mouse-pointer-click' : 'app-window';
  if (evidence.mcp) return 'plug';
  return LEVEL_ICON[level] ?? 'badge-check';
}

/** The marks of some OSes, named in a tooltip and for screen readers (`say` replaces the plain list of names). */
export function osList(oses: OS[], opts: { tone?: 'pass' | 'caution' | 'quiet'; say?: string } = {}): string {
  const say = opts.say ?? listOf(oses.map((os) => osName(os)));
  return `<span class="oses${opts.tone ? ` oses-${opts.tone}` : ''}" data-tip="${esc(say)}">${oses.map(osMark).join('')}<span class="sr">${esc(say)}</span></span>`;
}

/** A system as its OS mark and CPU ("[Tux] x86_64"), the OS named for screen readers and on hover. */
export const sysTag = (os: OS, arch: Arch | null) =>
  `<span class="sys" data-tip="${esc(osName(os))}">${osMark(os)}<span class="sr">${esc(osName(os))} </span>${esc(arch ?? '')}</span>`;

export interface RunFacts {
  os: OS | null;
  arch: Arch | null;
  method: string | null;
  replayed: boolean | null;
  checked_at: string | null;
  tool_version?: string | null;
}

/**
 * A run in one row of marks: where it ran, how, whether it passed offline, when.
 * `mine` says whether that is the reader's OS; `askedOffline` shows an offline run that was never checked;
 * `named`: a heading above already names the system.
 */
export function runFacts(run: RunFacts, opts: { offline?: boolean | null; mine?: boolean | null; askedOffline?: boolean; named?: boolean } = {}): string {
  if (!run.os) return '';
  const item = (cls: string, mark: string, text: string, tip?: string) =>
    `<li class="rf${cls ? ` rf-${cls}` : ''}"${tip ? ` data-tip="${esc(tip)}"` : ''}>${mark}${text}</li>`;
  const items = [
    opts.named
      ? ''
      : item(
          opts.mine === true ? 'yes' : opts.mine === false ? 'no' : '',
          osMark(run.os),
          esc(system(run.os, run.arch)),
          opts.mine === true ? 'Verified on your OS' : opts.mine === false ? 'Not your OS' : undefined,
        ),
    run.method === 'human'
      ? item('', icon('hand'), 'Installed by hand')
      : item('', icon('refresh-cw'), run.replayed ? 'Replayed from scratch' : 'Sandbox install'),
    opts.offline === true
      ? item('', icon('wifi-off'), 'Works offline', 'Its checks passed again with the network off')
      : opts.offline === false
        ? item('no', icon('wifi'), 'Needed the network', 'Its checks failed with the network off')
        : opts.askedOffline
          ? item('', icon('wifi'), 'Offline not checked')
          : '',
    run.checked_at ? item('', icon('calendar'), `<span class="sr">Checked on </span>${esc(day(run.checked_at))}`) : '',
    run.tool_version ? item('', icon('package'), `<span class="sr">Version </span>${esc(run.tool_version)}`) : '',
  ];
  return `<ul class="run-facts">${items.join('')}</ul>`;
}

/** What the marks mean, as rows of a dl.legend: shared by the ticket legend and the how-it-works page. */
export function marksLegend(): string {
  const row = (dt: string, dd: string) => `<div><dt>${dt}</dt><dd>${dd}</dd></div>`;
  const lvl = (level: string, evidence = {}) => `<span class="level-i">${icon(levelIcon(level, evidence))}</span>`;
  return (
    row(
      `<span class="mark-sample">${osList(['macos', 'linux', 'windows'], { tone: 'pass' })}</span>Where it ran`,
      'Green OS marks: pickfit ran the install steps there. Grey ones: the README says it runs there, and pickfit has not tried.',
    ) +
    row(
      `<span class="mark-sample">${lvl('install')}${lvl('function')}${lvl('service')}${lvl('inference')}</span>How far the run got`,
      'Installs and starts, its main function works, its service answers, it produces model output. A window means a desktop app opened; a plug, an MCP client used it.',
    ) +
    row(
      `<span class="mark-sample rf">${icon('refresh-cw')}${icon('hand')}${icon('wifi-off')}${icon('calendar')}</span>About the run`,
      'Replayed from scratch in a new sandbox, or installed by hand; passed again with the network off; the day it ran.',
    ) +
    row(
      `<span class="mark-sample rf">${icon('terminal')}${icon('cpu')}${icon('plug')}</span>Kind of tool`,
      'Developer CLI, local AI tool, MCP server. The words after the mark say its form: command-line tool, desktop app, local server.',
    ) +
    row(
      `<span class="mark-sample rf">${icon('file-text')}</span>Source of a reason`,
      'Every reason a pick fits rests on one profile field. Open the reason to see the field and the value it relies on.',
    )
  );
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

/** One at-a-glance cell: an icon and its value, which say enough; the label is for screen readers and the hover title. */
export function glance(ico: IconName | { svg: string }, label: string, value: string, tone: 'pass' | 'caution' | 'fail' | 'quiet' | 'plain' = 'plain'): string {
  return `<div class="gl gl-${tone}" title="${esc(label)}">${typeof ico === 'string' ? icon(ico) : ico.svg}<span class="gl-label sr">${esc(label)}: </span><span class="gl-value">${value}</span></div>`;
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
