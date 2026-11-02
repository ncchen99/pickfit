/**
 * The page shell every route shares: head, navigation, footer, the compare tray,
 * the ticket legend dialog and the script. Styles and the script run under the
 * response's CSP nonce; there are no inline style attributes.
 */
import { L, lang } from '../i18n.ts';
import { esc } from './html.ts';
import { icon, OS_SPRITE } from './icons.ts';
import { fitz, FITZ_BASE, ICON_32, marksLegend, popover } from './kit.ts';
import { script } from './script.ts';
import { CSS, CSS_ZH } from './styles.ts';

export type NavKey = 'find' | 'browse' | 'compare' | 'how' | 'agents' | null;

export interface ShellInput {
  nonce: string;
  title: string;
  description: string;
  active: NavKey;
  /** Classes on <body>: the page's layout mode. */
  bodyClass?: string;
  /** false on reading pages: the compare tray would only cover the text. */
  tray?: boolean;
  main: string;
}

const NAV = (): [Exclude<NavKey, null>, string, string][] => [
  ['find', '/', L('Find', '搜尋')],
  ['browse', '/browse', L('Browse', '瀏覽')],
  ['compare', '/compare', L('Compare', '比較')],
  ['how', '/how', L('How it works', '運作方式')],
  ['agents', '/agents', L('For agents', '給 agent')],
];

/** The wordmark: Fitz's 32 px icon and the name, with the cap-rufous dot over the i. */
export const BRAND = `<a class="brand" href="/" translate="no"><img src="${ICON_32}" width="32" height="32" alt=""><span>pickf<span class="i-dot">i</span>t</span></a>`;

/** The other language, on the same page: ?lang= is remembered in a cookie (i18n.ts); the script keeps the page's other query parameters. */
function langSwitch(): string {
  const [to, tag, text] = lang() === 'zh-TW' ? ['en', 'en', 'English'] : ['zh-TW', 'zh-Hant-TW', '中文'];
  return `<a class="lang-switch" href="?lang=${to}" data-lang="${to}" hreflang="${tag}" lang="${tag}">${icon('globe')}${text}</a>`;
}

function nav(active: NavKey): string {
  const links = NAV().map(
    ([key, href, text]) =>
      `<a href="${href}"${key === active ? ' aria-current="page"' : ''}${key === 'compare' ? ' data-tray-link' : ''}>${esc(text)}` +
      `${key === 'compare' ? '<span class="count" data-tray-count hidden></span>' : ''}</a>`,
  ).join('');
  return (
    `<header class="top mat"><div class="wrap top-row">${BRAND}` +
    `<nav class="nav" aria-label="${L('Main', '主選單')}">${links}</nav>` +
    `<div class="top-end">${langSwitch()}` +
    `<details class="menu"><summary aria-label="${L('Menu', '選單')}">${icon('menu')}</summary><nav class="menu-nav" aria-label="${L('Main, small screens', '主選單（小螢幕）')}">${links}</nav></details>` +
    `</div></div></header>`
  );
}

const FOOTER = () => `<footer class="foot mat">
<div class="wrap foot-grid">
<div class="foot-brand">${BRAND}<p>${L('Every tool, tested first. pickfit installs every tool it suggests in a fresh sandbox, and hands you the steps that worked.', '每款軟體，都先幫你試過。pickfit 推薦的每款工具都先在全新沙盒裡裝過，再把可行的步驟交給你。')}</p></div>
<nav class="foot-links" aria-label="${L('Footer', '頁尾')}"><p class="foot-h">${L('Use pickfit', '使用 pickfit')}</p><a href="/">${L('Find software', '搜尋軟體')}</a><a href="/browse">${L('Browse verified tools', '瀏覽已驗證的工具')}</a><a href="/compare">${L('Compare tools', '比較工具')}</a><a href="/agents">${L('Connect your agent', '接上你的 agent')}</a></nav>
<nav class="foot-links" aria-label="${L('About', '關於')}"><p class="foot-h">${L('Why trust it', '為什麼可以信任')}</p><a href="/how">${L('How Fitz checks a tool', 'Fitz 如何檢查工具')}</a><a href="/how#labels">${L('What the labels mean', '標籤說明')}</a><a href="/how#rules">${L('Fitz’s rules', 'Fitz 的原則')}</a></nav>
</div>
<div class="wrap foot-notes">
<p>${L('pickfit ranks by fit, not stars. No ads, no paid placement, no referral links, and it doesn’t make any of the software it suggests.', 'pickfit 看合不合身排序，不看星數。沒有廣告、付費排名或推薦連結，推薦的軟體也沒有一款是自家做的。')}</p>
<p>${L('No account and no IP address stored. Your sentence goes to Meta’s Muse Spark with storage turned off; pickfit keeps only the conditions it parsed, such as the task and the OS.', '免帳號，也不記錄 IP。你輸入的句子會送到 Meta 的 Muse Spark（已關閉資料保存）；pickfit 只保留從中解析出的條件，例如任務和作業系統。')}</p>
</div>
<div class="ruler" aria-hidden="true"></div>
</footer>`;

/** The legend for a fitting ticket, opened from results and tool pages. */
const LEGEND = () => `<dialog class="sheet" id="legend" aria-labelledby="legend-title">
<form method="dialog" class="sheet-close"><button class="btn btn-ghost btn-icon" aria-label="${L('Close', '關閉')}">${icon('x')}</button></form>
<div class="sheet-head">${fitz('neutral', 72)}<h2 id="legend-title">${L('How to read a tool card', '怎麼看工具卡')}</h2></div>
<dl class="legend">
<div><dt><span class="seam-sample" aria-hidden="true"></span>${L('Stitching', '縫線')}</dt><dd>${L('pickfit installed this tool itself. Everything under the stitches comes from that run. A tool pickfit has not run never gets stitches.', 'pickfit 親自安裝過這款工具，縫線下方的內容都來自那次測試。沒測過的工具，一律沒有縫線。')}</dd></div>
<div><dt><span class="badge badge-pass">${icon('check')}${L('Verified on your OS', '已在你的作業系統上驗證')}</span></dt><dd>${L('The install steps ran on the system you chose. “Ran on Linux only” means it has not been run on yours yet.', '安裝步驟在你選的系統上跑過。「只在 Linux 上執行過」表示還沒在你的系統上跑過。')}</dd></div>
${marksLegend()}
<div><dt><span class="badge badge-gem">${icon('gem')}${L('Hidden gem', '寶藏')}</span></dt><dd>${L('High quality, little known: quality 80 or more, popularity 45 or less.', '品質高、少有人知：品質 80 以上，知名度 45 以下。')}</dd></div>
<div><dt><span class="tape-sample" aria-hidden="true"></span>${L('Quality and popularity', '品質與知名度')}</dt><dd>${L('Two separate scores out of 100. Quality comes mostly from the sandbox run and the install docs; popularity from stars, downloads and Hacker News. Fitz ranks by fit, not by either.', '兩個獨立的分數，滿分都是 100。品質主要看沙盒測試和安裝文件；知名度看星數、下載量和 Hacker News。Fitz 看合不合身排序，不看這兩個分數。')}</dd></div>
<div><dt><span class="cov-sample" aria-hidden="true"></span>${L('Features checked', '已檢查的功能')}</dt><dd>${L('Of the main features the README advertises, how many the run actually exercised (green), and how many failed (red). Grey ones were not checked, and the card says why.', 'README 宣傳的主要功能裡，實測通過幾項（綠色）、失敗幾項（紅色）。灰色是沒檢查的，工具卡會說明原因。')}</dd></div>
<div><dt><span class="badge badge-quiet">${icon('circle-dashed')}${L('Not verified', '未驗證')}</span></dt><dd>${L('A well-known tool Fitz mentions from general knowledge. No run record, no steps, no score.', 'Fitz 依一般知識提到的知名工具。沒有測試紀錄、沒有步驟、沒有分數。')}</dd></div>
</dl>
</dialog>`;

const TRAY = () => `<aside class="tray" id="tray" aria-label="${L('Compare tray', '比較匣')}" hidden>
<div class="wrap tray-row">${fitz('comparing', 44)}
<ul class="tray-list" data-tray-list></ul>
<span class="tray-note" data-tray-note></span>
<button type="button" class="btn btn-ghost btn-sm" data-tray-clear>${L('Clear', '清除')}</button>
<a class="btn btn-primary btn-sm" data-tray-go href="/compare">${icon('scale')}${L('Compare', '比較')}</a>
</div></aside>
<div class="toasts" role="status" aria-live="polite" data-toasts></div>`;

export function renderShell(input: ShellInput): string {
  const { nonce } = input;
  return `<!doctype html>
<html lang="${lang() === 'zh-TW' ? 'zh-Hant-TW' : 'en'}">
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
<style nonce="${nonce}">${CSS}${lang() === 'zh-TW' ? CSS_ZH : ''}</style>
</head>
<body class="${esc(input.bodyClass ?? '')}"${input.tray === false ? ' data-tray="off"' : ''}>
<a class="skip" href="#main">${L('Skip to content', '跳到主要內容')}</a>
${OS_SPRITE}
${nav(input.active)}
<main id="main">${input.main}</main>
${FOOTER()}
${TRAY()}
${LEGEND()}
${popover('pop-quality', L('Quality score', '品質分數'), L('<p>Out of 100. Mostly what pickfit saw itself: how far the sandbox run got and how many README fixes it needed (40%), and how complete the install docs are (25%). Then maintenance, issue responsiveness and engineering hygiene. Scored apart from popularity.</p><p><a href="/how#scores">How scores work</a></p>', '<p>滿分 100。主要看 pickfit 親自測到的：沙盒測試走到哪一步、README 要修幾處（40%），以及安裝文件完不完整（25%）。其次是維護狀況、issue 回應速度和工程品質。與知名度分開計分。</p><p><a href="/how#scores">分數怎麼算</a></p>'))}
${popover('pop-popularity', L('Popularity score', '知名度分數'), L('<p>Out of 100, from public counts against other tools of the same kind: GitHub stars and forks, release and package downloads, Hacker News points. Low is not bad: pickfit looks for tools that are good and little known.</p>', '<p>滿分 100，依公開數據與同類工具比較：GitHub 星數和 fork 數、發行版與套件下載量、Hacker News 分數。分數低不代表不好：pickfit 要找的正是好用卻少有人知的工具。</p>'))}
${popover('pop-features', L('Feature checks', '功能檢查'), L('<p>The verification agent tries the main features the README advertises, one by one, in the sandbox. Some need an account, a GPU or a display the sandbox doesn’t have, so they stay unchecked, and the card says which and why.</p>', '<p>驗證 agent 會在沙盒裡逐一試用 README 宣傳的主要功能。有些功能需要帳號、GPU 或螢幕，沙盒裡沒有，就會標為未檢查，工具卡會說明是哪些、為什麼。</p>'))}
${popover('pop-gem', L('Hidden gem', '寶藏'), L('<p>A verified tool with a quality score of 80 or more and a popularity score of 45 or less: well made, and not yet widely known.</p>', '<p>品質分數 80 以上、知名度分數 45 以下的已驗證工具：做得好，但還沒有廣為人知。</p>'))}
<script nonce="${nonce}">${script()}</script>
</body>
</html>`;
}
