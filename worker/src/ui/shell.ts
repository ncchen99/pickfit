/**
 * The page shell every route shares: head, navigation, footer, the compare tray,
 * the ticket legend dialog and the script. Styles and the script run under the
 * response's CSP nonce; there are no inline style attributes.
 */
import { esc } from './html.ts';
import { icon } from './icons.ts';
import { fitz, FITZ_BASE, ICON_32, popover } from './kit.ts';
import { SCRIPT } from './script.ts';
import { CSS } from './styles.ts';

export type NavKey = 'find' | 'browse' | 'compare' | 'how' | 'agents' | null;

export interface ShellInput {
  nonce: string;
  title: string;
  description: string;
  active: NavKey;
  /** Classes on <body>: the page's layout mode. */
  bodyClass?: string;
  main: string;
}

const NAV: [Exclude<NavKey, null>, string, string][] = [
  ['find', '/', 'Find'],
  ['browse', '/browse', 'Browse'],
  ['compare', '/compare', 'Compare'],
  ['how', '/how', 'How it works'],
  ['agents', '/agents', 'For agents'],
];

/** The wordmark: Fitz's 32 px icon and the name, with the cap-rufous dot over the i. */
export const BRAND = `<a class="brand" href="/" translate="no"><img src="${ICON_32}" width="32" height="32" alt=""><span>pickf<span class="i-dot">i</span>t</span></a>`;

function nav(active: NavKey): string {
  const links = NAV.map(
    ([key, href, text]) =>
      `<a href="${href}"${key === active ? ' aria-current="page"' : ''}${key === 'compare' ? ' data-tray-link' : ''}>${esc(text)}` +
      `${key === 'compare' ? '<span class="count" data-tray-count hidden></span>' : ''}</a>`,
  ).join('');
  return (
    `<header class="top mat"><div class="wrap top-row">${BRAND}` +
    `<nav class="nav" aria-label="Main">${links}</nav>` +
    `<details class="menu"><summary aria-label="Menu">${icon('menu')}</summary><nav class="menu-nav" aria-label="Main, small screens">${links}</nav></details>` +
    `</div></header>`
  );
}

const FOOTER = `<footer class="foot mat">
<div class="wrap foot-grid">
<div class="foot-brand">${BRAND}<p>Software that fits, tried on first. pickfit installs every tool it suggests in a fresh sandbox, and hands you the steps that worked.</p></div>
<nav class="foot-links" aria-label="Footer"><p class="foot-h">Use pickfit</p><a href="/">Find software</a><a href="/browse">Browse verified tools</a><a href="/compare">Compare tools</a><a href="/agents">Connect your agent</a></nav>
<nav class="foot-links" aria-label="About"><p class="foot-h">Why trust it</p><a href="/how">How Fitz checks a tool</a><a href="/how#labels">What the labels mean</a><a href="/how#rules">Fitz’s rules</a></nav>
</div>
<div class="wrap foot-notes">
<p>pickfit ranks by fit, not stars. No ads, no paid placement, no referral links, and it doesn’t make any of the software it suggests.</p>
<p>No account and no IP address stored. Your sentence goes to Meta’s Muse Spark with storage turned off; pickfit keeps only the conditions it parsed, such as the task and the OS.</p>
</div>
<div class="ruler" aria-hidden="true"></div>
</footer>`;

/** The legend for a fitting ticket, opened from results and tool pages. */
const LEGEND = `<dialog class="sheet" id="legend" aria-labelledby="legend-title">
<form method="dialog" class="sheet-close"><button class="btn btn-ghost btn-icon" aria-label="Close">${icon('x')}</button></form>
<div class="sheet-head">${fitz('neutral', 72)}<h2 id="legend-title">How to read a fitting ticket</h2></div>
<dl class="legend">
<div><dt><span class="seam-sample" aria-hidden="true"></span>Stitching</dt><dd>pickfit installed this tool itself. Everything under the stitches comes from that run. A tool pickfit has not run never gets stitches.</dd></div>
<div><dt><span class="badge badge-pass">${icon('check')}Verified on your OS</span></dt><dd>The install steps ran on the system you chose. “Ran on Linux only” means it has not been run on yours yet.</dd></div>
<div><dt><span class="badge badge-gem">${icon('gem')}Hidden gem</span></dt><dd>High quality, little known: quality 80 or more, popularity 45 or less.</dd></div>
<div><dt><span class="tape-sample" aria-hidden="true"></span>Quality and popularity</dt><dd>Two separate scores out of 100. Quality comes mostly from the sandbox run and the install docs; popularity from stars, downloads and Hacker News. Fitz ranks by fit, not by either.</dd></div>
<div><dt><span class="cov-sample" aria-hidden="true"></span>Features checked</dt><dd>Of the main features the README advertises, how many the run actually exercised (green), and how many failed (red). Grey ones were not checked, and the ticket says why.</dd></div>
<div><dt><span class="badge badge-quiet">${icon('circle-dashed')}Not verified</span></dt><dd>A well-known tool Fitz mentions from general knowledge. No run record, no steps, no score.</dd></div>
</dl>
</dialog>`;

const TRAY = `<aside class="tray" id="tray" aria-label="Compare tray" hidden>
<div class="wrap tray-row">${fitz('comparing', 44)}
<ul class="tray-list" data-tray-list></ul>
<span class="tray-note" data-tray-note></span>
<button type="button" class="btn btn-ghost btn-sm" data-tray-clear>Clear</button>
<a class="btn btn-primary btn-sm" data-tray-go href="/compare">${icon('scale')}Compare</a>
</div></aside>
<div class="toasts" role="status" aria-live="polite" data-toasts></div>`;

export function renderShell(input: ShellInput): string {
  const { nonce } = input;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(input.title)}</title>
<meta name="description" content="${esc(input.description)}">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#1D3D2A">
<link rel="icon" href="${ICON_32}" type="image/svg+xml">
<link rel="preload" href="/assets/fonts/bricolage-grotesque.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="${FITZ_BASE}states/fitz-searching.svg" as="image" type="image/svg+xml">
<style nonce="${nonce}">${CSS}</style>
</head>
<body class="${esc(input.bodyClass ?? '')}">
<a class="skip" href="#main">Skip to content</a>
${nav(input.active)}
<main id="main">${input.main}</main>
${FOOTER}
${TRAY}
${LEGEND}
${popover('pop-quality', 'Quality score', '<p>Out of 100. Mostly what pickfit saw itself: how far the sandbox run got and how many README fixes it needed (40%), and how complete the install docs are (25%). Then maintenance, issue responsiveness and engineering hygiene. Scored apart from popularity.</p><p><a href="/how#scores">How scores work</a></p>')}
${popover('pop-popularity', 'Popularity score', '<p>Out of 100, from public counts against other tools of the same kind: GitHub stars and forks, release and package downloads, Hacker News points. Low is not bad: pickfit looks for tools that are good and little known.</p>')}
${popover('pop-features', 'Feature checks', '<p>The verification agent tries the main features the README advertises, one by one, in the sandbox. Some need an account, a GPU or a display the sandbox doesn’t have, so they stay unchecked, and the ticket says which and why.</p>')}
${popover('pop-gem', 'Hidden gem', '<p>A verified tool with a quality score of 80 or more and a popularity score of 45 or less: well made, and not yet widely known.</p>')}
<script nonce="${nonce}">${SCRIPT}</script>
</body>
</html>`;
}
