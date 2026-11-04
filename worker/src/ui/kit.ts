/**
 * The component kit (DESIGN.md section 5): small string helpers that every page
 * shares, so a badge, a tape meter or a notice looks and behaves the same
 * everywhere. Their CSS is in styles.ts. No helper invents a value: a meter
 * with no score says "not scored".
 */
import type { Arch, Entry, GuiEvidence, OS } from '../catalog.ts';
import { operatedText } from '../evidence.ts';
import type { FeaturesOut } from '../features.ts';
import { L } from '../i18n.ts';
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
/** The same icon with a cream outline, so the silhouette holds on the dark page (brand/mascot/README.md). */
export const ICON_32_DARK = `${FITZ_BASE}icons/fitz-32-dark.svg`;
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
    return `<button type="button" class="${cls}" popovertarget="${opts.pop}" aria-label="${L(`${esc(text)}: what this means`, `${esc(text)}：這是什麼意思`)}"${tip}>${inner}</button>`;
  }
  return `<span class="${cls}"${tip || (opts.title ? ` title="${esc(opts.title)}"` : '')}>${inner}</span>`;
}

// ---------------------------------------------------------------- marks for facts every card repeats

/** An icon per kind of tool, shown before its form ("Command-line tool"); the kind's name is the tooltip. */
const KIND_ICON: Record<string, IconName> = { dev_cli: 'terminal', local_ai: 'cpu', mcp_server: 'plug', other: 'package' };
export const kindIcon = (category: string): IconName => KIND_ICON[category] ?? 'package';

export function kindTag(entry: Pick<Entry, 'kind' | 'category'>): string {
  // A web app gets the globe; outside the three categories it is just a web app.
  const web = entry.kind === 'web_app';
  const kind = web && entry.category === 'other' ? '' : (KIND[entry.category] ?? '');
  const form = formOf(entry);
  const named = kind && kind.toLowerCase() !== form.toLowerCase();
  return (
    `<span class="kind"${named ? ` data-tip="${esc(kind)}"` : ''}>${icon(web ? 'globe' : kindIcon(entry.category))}` +
    `${named ? `<span class="sr">${esc(kind)}${L(', ', '，')}</span>` : ''}${esc(form.charAt(0).toUpperCase() + form.slice(1))}</span>`
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
  /** The sandbox's GPU and simulated microphone (index runs only); absent or null: none. */
  gpu?: string | null;
  microphone?: string | null;
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
          opts.mine === true
            ? L('Verified on your OS', '已在你的作業系統上驗證')
            : opts.mine === false
              ? L('Not your OS', '不是你的系統')
              : undefined,
        ),
    run.method === 'human'
      ? item('', icon('hand'), L('Installed by hand', '手動安裝'))
      : item('', icon('refresh-cw'), run.replayed ? L('Replayed from scratch', '從頭重跑') : L('Sandbox install', '沙盒安裝')),
    run.gpu ? item('', icon('cpu'), L(`GPU: ${esc(run.gpu)}`, `GPU：${esc(run.gpu)}`), L('The sandbox had this GPU', '沙盒配有這張 GPU')) : '',
    run.microphone
      ? item(
          '',
          icon('mic'),
          L('Simulated microphone', '模擬麥克風'),
          L('A simulated microphone played words pickfit spoke for each check', '檢查時用模擬麥克風播放 pickfit 念的字詞'),
        )
      : '',
    opts.offline === true
      ? item('', icon('wifi-off'), L('Works offline', '可離線使用'), L('Its checks passed again with the network off', '斷網後檢查仍通過'))
      : opts.offline === false
        ? item('no', icon('wifi'), L('Needed the network', '需要網路'), L('Its checks failed with the network off', '斷網後檢查失敗'))
        : opts.askedOffline
          ? item('', icon('wifi'), L('Offline not checked', '未檢查能否離線'))
          : '',
    run.checked_at
      ? item('', icon('calendar'), `${L('<span class="sr">Checked on </span>', '<span class="sr">檢查於 </span>')}${esc(day(run.checked_at))}`)
      : '',
    run.tool_version
      ? item('', icon('package'), `${L('<span class="sr">Version </span>', '<span class="sr">版本 </span>')}${esc(run.tool_version)}`)
      : '',
  ];
  return `<ul class="run-facts">${items.join('')}</ul>`;
}

/** What the marks mean, as rows of a dl.legend: shared by the ticket legend and the how-it-works page. */
export function marksLegend(): string {
  const row = (dt: string, dd: string) => `<div><dt>${dt}</dt><dd>${dd}</dd></div>`;
  const lvl = (level: string, evidence = {}) => `<span class="level-i">${icon(levelIcon(level, evidence))}</span>`;
  const chk = (tone: 'pass' | 'caution' | 'fail' | 'open', name: IconName, count = 0) =>
    `<span class="mark-${tone}">${icon(name)}${count ? `<span class="check-count">${count}</span>` : ''}</span>`;
  return (
    row(
      `<span class="mark-sample">${osList(['macos', 'linux', 'windows'], { tone: 'pass' })}</span>${L('Where it ran', '在哪裡測過')}`,
      L(
        'Green OS marks: pickfit ran the install steps there. Grey ones: the README says it runs there, and pickfit has not tried.',
        '綠色系統標記：pickfit 在該系統跑過安裝步驟。灰色：README 說支援，但 pickfit 還沒試過。',
      ),
    ) +
    row(
      `<span class="mark-sample">${lvl('install')}${lvl('function')}${lvl('service')}${lvl('inference')}</span>${L('How far the run got', '測試進行到哪一步')}`,
      L(
        'Installs and starts, its main function works, its service answers, it produces model output. A window means a desktop app opened; a plug, an MCP client used it. The mark sits beside the run’s result, under “Why it fits and how we know” and in “How pickfit tested it”.',
        '能安裝並啟動、主要功能可用、服務有回應、能產生模型輸出。視窗代表桌面應用程式已開啟；插頭代表 MCP 用戶端用過它。標記在測試結果旁邊：展開「為什麼適合、我們怎麼知道」，或在「pickfit 怎麼測的」裡。',
      ),
    ) +
    // The two checks on a tool page's At a glance (tool.ts checkMark): an eye and a shield, in the state's colour, and
    // the same icon basted (dashed) in grey when not checked. Here so a touch screen, which shows a mark's words only
    // after a tap, can read them all at once.
    row(
      `<span class="mark-sample checks" aria-hidden="true">${chk('pass', 'eye-check')}${chk('caution', 'eye', 2)}${chk('open', 'eye')}</span>${L('Visual check', '視覺檢查')}`,
      L(
        'pickfit looked at screenshots of the app. Green: it looks right. Amber with a number: things that look wrong; open it to see them. Grey and dashed: not checked yet.',
        'pickfit 看過應用程式的截圖。綠色：畫面正常。黃色加數字：有看起來不對的地方，點開就能看到。灰色虛線：還沒檢查。',
      ),
    ) +
    row(
      `<span class="mark-sample checks" aria-hidden="true">${chk('pass', 'shield-check')}${chk('fail', 'shield-alert', 7)}${chk('open', 'shield')}</span>${L('Known vulnerabilities', '已知漏洞')}`,
      L(
        'Known high or critical vulnerabilities (OSV.dev) in what it installs. Green: none known. Red with a number: how many; open it for the list, and read it before you install. Grey and dashed: not checked, which does not mean safe.',
        '它安裝的套件有沒有已知的高風險或嚴重漏洞（OSV.dev）。綠色：沒有已知漏洞。紅色加數字：有幾個，點開看清單，安裝前先看過。灰色虛線：沒有檢查，不代表安全。',
      ),
    ) +
    // Everything else about a run (replayed, offline, the kind of tool) is said in words, so only these two marks remain.
    row(
      `<span class="mark-sample rf">${icon('calendar')}${icon('package')}</span>${L('About the run', '關於這次測試')}`,
      L('The day it ran, and the version that ran.', '測試日期，以及測到的版本。'),
    ) +
    row(
      `<span class="mark-sample rf">${icon('file-text')}</span>${L('Source of a reason', '理由的來源')}`,
      L(
        'Every reason a pick fits rests on one profile field. Open the reason to see the field and the value it relies on.',
        '每個推薦理由都依據簡介裡的一個欄位。展開理由就能看到欄位和值。',
      ),
    )
  );
}

/** A popover (native popover API) and the little "?" that opens it. */
export function popover(id: string, title: string, body: string): string {
  return (
    `<div popover id="${id}" class="pop" role="dialog" aria-label="${esc(title)}">` +
    `<p class="pop-title">${esc(title)}</p>${body}` +
    `<button type="button" class="pop-close" popovertarget="${id}" popovertargetaction="hide" aria-label="${L('Close', '關閉')}">${icon('x')}</button></div>`
  );
}

export function helpButton(id: string, label: string): string {
  return `<button type="button" class="help" popovertarget="${id}" aria-label="${esc(label)}">${icon('circle-help')}</button>`;
}

/**
 * A word of a command the browser could break inside (after a hyphen or a slash, at a bracket): `--` and `appdir` on two
 * lines would read as two words. Such a word is kept whole (.w), so the line wraps at a space before it; only a word
 * longer than the line breaks inside. The span adds no text: Copy and a selection still copy exactly the command.
 */
const BREAKABLE = /[^\s]*[-/|?!%)\]}][^\s]*/g;
const words = (line: string) => esc(line).replace(BREAKABLE, (w) => `<span class="w">${w}</span>`);

/**
 * A command: a left-ruled block of monospace on the ground it sits on (no box), with a quiet Copy (shown once the
 * script runs) on the first line's baseline. Several lines: each is its own block, so a long one wraps under itself
 * (a hanging indent) and the next starts flush. The newlines stay in the text, so Copy copies exactly what was run.
 */
export function command(text: string): string {
  const multi = text.includes('\n');
  const body = multi
    ? text
        .split('\n')
        .map((line, i, all) => `<span class="ln">${words(line)}${i < all.length - 1 ? '\n' : ''}</span>`)
        .join('')
    : words(text);
  return `<div class="cmd${multi ? ' cmd-multi' : ''}"><pre translate="no"><code>${body}</code></pre><button type="button" class="copy" aria-label="${L('Copy command', '複製指令')}">${icon('copy')}<span>${L('Copy', '複製')}</span></button></div>`;
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
  const head = `<span class="meter-label">${esc(label)}${opts.pop ? helpButton(opts.pop, L(`About ${label.toLowerCase()}`, `關於${label}`)) : ''}</span>`;
  const ticks: string[] = [];
  for (let x = 10; x < 100; x += 10) ticks.push(`M${x * 2} 0V${x % 50 === 0 ? 9 : 6}`);
  if (value === null) {
    return (
      `<div class="meter meter-none">${head}<svg class="tape" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">` +
      `<rect class="tape-track" x="0" y="0" width="200" height="14" rx="3"/><path class="tape-ticks" d="${ticks.join('')}"/></svg>` +
      `<span class="meter-read">${L('not scored', '未評分')}</span></div>`
    );
  }
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    `<div class="meter meter-${opts.tone ?? 'tape'}" role="img" aria-label="${L(`${esc(label)}: ${v} out of 100`, `${esc(label)}：${v} 分（滿分 100）`)}${opts.note ? `${L(', ', '，')}${esc(opts.note)}` : ''}">${head}` +
    `<svg class="tape" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true"><rect class="tape-track" x="0" y="0" width="200" height="14" rx="3"/>` +
    `<rect class="tape-fill" x="0" y="0" width="${v * 2}" height="14" rx="3"/><path class="tape-ticks" d="${ticks.join('')}"/>` +
    `<path class="tape-mark" d="M${v * 2} -2V16"/></svg>` +
    `<span class="meter-read" aria-hidden="true">${v}</span>${opts.note ? `<span class="meter-note">${esc(opts.note)}</span>` : ''}</div>`
  );
}

/** Why a part of the quality score has no data, in a reader's words. */
const UNMEASURED: Record<string, () => string> = {
  sandbox_verification: () => L('no install test yet', '還沒有安裝測試'),
  install_docs: () => L('install docs not graded', '安裝文件沒有評分'),
  maintenance: () => L('no maintenance data', '沒有維護資料'),
  engineering_hygiene: () => L('no engineering data', '沒有工程品質資料'),
  responsiveness: () => L('too few outside issues to judge responses', '外部 issue 太少，無法評估回應速度'),
  usage_outcomes: () => L('fewer than 3 reports from real use', '實際使用的回報不到 3 筆'),
  browser_facts: () => L('nothing the browser could tell', '瀏覽器沒有觀察到相關資訊'),
};

/**
 * How much of the quality score rests on evidence, and in a tooltip (hover, or focus on a touch screen) what is
 * missing: the features nobody reached a verdict on come first, by name, since that is what a reader can act on.
 */
export function confidenceRow(confidence: number | undefined, unmeasured: string[] | undefined, features: FeaturesOut): string {
  if (confidence === undefined) return '';
  const pct = Math.round(confidence * 100);
  const lines = [L(`Quality rests on ${pct}% of what it could.`, `品質分數有 ${pct}% 的項目有資料。`)];
  const gaps = unmeasured ?? [];
  if (gaps.includes('feature_results')) {
    const names = features.not_checked.filter((f) => f.reason !== 'test_failed').map((f) => f.feature);
    const shown = names.slice(0, 4).join(L(', ', '、'));
    const more = names.length > 4 ? L(` and ${names.length - 4} more`, ` 等 ${names.length} 項`) : '';
    lines.push(names.length
      ? L(`Features not confirmed: ${shown}${more}.`, `沒有驗證到的功能：${shown}${more}。`)
      : L('No feature was tested one by one.', '沒有逐項測試功能。'));
  }
  const others = gaps.filter((g) => g !== 'feature_results').map((g) => UNMEASURED[g]?.() ?? g);
  if (others.length) lines.push(L(`Also missing: ${others.join(', ')}.`, `另外缺少：${others.join('、')}。`));
  const say = lines.join(' ');
  return (
    `<div class="meter meter-none meter-conf"><span class="meter-label">${L('Quality confidence', '品質信心度')}</span>` +
    `<span class="meter-read conf-read" tabindex="0" data-tip="${esc(say)}">${pct}%<span class="sr"> ${esc(say)}</span></span></div>`
  );
}

/** Features the run exercised vs the README's list: one segmented bar, counts in words beside it. */
export function coverage(features: FeaturesOut, opts: { pop?: string } = {}): string {
  const checked = features.checked.length;
  const failed = features.not_checked.filter((f) => f.reason === 'test_failed').length;
  const open = features.not_checked.length - failed;
  const total = checked + failed + open;
  const label = `<span class="meter-label">${L('Features checked', '已檢查的功能')}${opts.pop ? helpButton(opts.pop, L('About feature checks', '關於功能檢查')) : ''}</span>`;
  if (!features.recorded || total === 0) {
    return `<div class="meter meter-none">${label}<span class="meter-read meter-wide">${total ? L('not checked one by one', '未逐項檢查') : L('no feature list', '沒有功能清單')}</span></div>`;
  }
  const w = (n: number) => (n / total) * 200;
  let x = 0;
  const seg = (n: number, cls: string) => {
    if (!n) return '';
    const out = `<rect class="${cls}" x="${x.toFixed(1)}" y="0" width="${Math.max(0, w(n) - 2).toFixed(1)}" height="14" rx="3"/>`;
    x += w(n);
    return out;
  };
  const words = [
    L(`${checked} of ${total} checked`, `已檢查 ${checked}/${total} 項`),
    failed ? L(`${failed} failed`, `${failed} 項失敗`) : '',
  ]
    .filter(Boolean)
    .join(L(', ', '，'));
  return (
    `<div class="meter meter-cov" role="img" aria-label="${L(`Features: ${esc(words)}`, `功能：${esc(words)}`)}">${label}` +
    `<svg class="tape" viewBox="0 0 200 14" preserveAspectRatio="none" aria-hidden="true">${seg(checked, 'cov-ok')}${seg(failed, 'cov-fail')}${seg(open, 'cov-open')}</svg>` +
    `<span class="meter-read meter-wide" aria-hidden="true">${esc(words)}</span></div>`
  );
}

/**
 * The checkbox that pins a tool to the compare tray (the tray is script; without it, the link to /compare works).
 * Its mark is the dressmaker's pin; once the tool is pinned the chip's check takes the pin's place, as on every chip.
 */
export function compareToggle(slug: string, name: string): string {
  return (
    `<label class="chip chip-compare js-only"><input type="checkbox" data-compare="${esc(slug)}" data-name="${esc(name)}">` +
    `${icon('pin')}<span>${L('Compare', '比較')}</span></label>`
  );
}

// ---------------------------------------------------------------- the measurement sheet

export type MeasureTone = 'pass' | 'caution' | 'fail' | 'quiet';

export interface MeasureRow {
  /** The label, plain text (escaped here); in words through L() so the zh-TW page reads 「價格」, not "Price". */
  label: string;
  /** The value as HTML: escape text first. One fact per row; an OS mark or a <small> note may sit inside it. */
  value: string;
  /** Colours the value only: pass for what a run proved, caution for a partial or other-system fact, quiet for "not stated". */
  tone?: MeasureTone;
}

/**
 * The widths (rem) at which a row of the sheet stops fitting on one line. measure() estimates the width a row needs
 * (needRem) and tags it with the smallest of these that covers it, as m-fit<rem×10> (m-fit215: 21.5rem); styles.ts
 * turns each into a container query that puts the value under the label in a sheet narrower than that. A row that
 * needs less than the first never stacks; one that needs more than the last stacks in any single-column sheet.
 */
export const MEASURE_FITS = [16, 17, 18, 19, 20, 21.5, 23, 25, 27, 30, 36];

const CJK = /[\u1100-\u115f\u2e80-\ua4cf\uac00-\ud7a3\uf900-\ufaff\ufe30-\ufe4f\uff00-\uff60\uffe0-\uffe6]/;

/** Text width in rem, roughly, at `em` rem per Latin character (a CJK character is a full em, more or less). */
function textRem(text: string, em: number): number {
  let n = 0;
  for (const ch of text) n += CJK.test(ch) ? 2.15 : 1;
  return n * em;
}

/**
 * The width (rem) a row needs on one line: the label (.92rem), the value (.95rem, its <small> .85rem, its <code>
 * monospace), an OS mark, the shortest leader and the gaps (2.6rem) and a little slack. Calibrated on SF and Segoe-sized
 * system faces to within about half a rem; when it falls short, the row's value wraps to the next line instead.
 */
function needRem(label: string, value: string): number {
  const plain = (h: string) => h.replace(/<[^>]*>/g, '').replace(/&[#a-z0-9]+;/gi, '.');
  let rem = textRem(label, 0.465);
  // Words for screen readers only (osList's and kindTag's names) take no room on the line.
  let rest = value.replace(/<span class="sr">[^<]*<\/span>/g, '');
  rest = rest.replace(/<small\b[^>]*>([\s\S]*?)<\/small>/g, (_, t: string) => ((rem += textRem(plain(t), 0.38)), ''));
  rest = rest.replace(/<code\b[^>]*>([\s\S]*?)<\/code>/g, (_, t: string) => ((rem += textRem(plain(t), 0.5)), ''));
  rem += (rest.match(/<svg class="os\b/g)?.length ?? 0) * 1.6;
  return rem + textRem(plain(rest), 0.47) + 2.9;
}

/**
 * A measurement sheet (DESIGN.md §5): facts written as a tailor's measurement record, one row per fact, the label
 * (--ink-3, system face) joined to its value (--ink, tabular figures) by a dotted leader. No box: it sits on whatever
 * ground it is on, the first pick's --voice included. At most about 30rem wide. A row too long for a narrow sheet
 * puts its value under the label. A row is never dropped: one with an empty value reads "not stated", in the quiet
 * tone, so a fact the caller could not fill stays visibly unknown (a caller leaves out a row it does not want).
 */
export function measure(rows: MeasureRow[], opts: { cls?: string } = {}): string {
  const items = rows
    .map((r) => (r.value === '' ? { ...r, value: `<span class="unknown">${L('not stated', '未說明')}</span>`, tone: 'quiet' as const } : r))
    .map((r) => {
      const need = needRem(r.label, r.value);
      const fit = need < MEASURE_FITS[0] ? 0 : (MEASURE_FITS.find((w) => w >= need) ?? MEASURE_FITS[MEASURE_FITS.length - 1]);
      const cls = `m${r.tone ? ` m-${r.tone}` : ''}${fit ? ` m-fit${Math.round(fit * 10)}` : ''}`;
      return `<div class="${cls}"><dt>${esc(r.label)}</dt><dd>${r.value}</dd></div>`;
    })
    .join('');
  return `<dl class="measure${opts.cls ? ` ${opts.cls}` : ''}">${items}</dl>`;
}

/** Relative age of a day, against the catalog's build time so a cached page does not drift. */
export function age(iso: string | null, now: Date): string | null {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const days = Math.max(0, Math.floor((now.getTime() - then.getTime()) / 86_400_000));
  if (days === 0) return L('today', '今天');
  if (days === 1) return L('yesterday', '昨天');
  if (days < 60) return L(`${days} days ago`, `${days} 天前`);
  const months = Math.floor(days / 30.4);
  if (months < 24) return L(`${months} months ago`, `${months} 個月前`);
  return L(`${Math.floor(days / 365)} years ago`, `${Math.floor(days / 365)} 年前`);
}
