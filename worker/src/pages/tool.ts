/**
 * One tool, for a person deciding whether to use it: what it looks like (pickfit's clip of it running,
 * with chapters when the clip has them), how far pickfit got with it, what it does (each advertised
 * feature, ticked when a run checked it, with how to use it), and how to install it. How pickfit tested
 * it sits folded at the bottom, for anyone who wants the evidence. Read from the catalog only; nothing
 * here calls a model. The plain feature titles, steps and open hint come from the record's usage_guide,
 * which names the model that wrote them.
 */
import { bestGuide, isVerified, isWebApp, OSES, verifiedOn, webCheck, type Catalog, type Entry, type InstallGuide, type OS, type RunVideo } from '../catalog.ts';
import { featuresOut, type FeaturesOut } from '../features.ts';
import { L } from '../i18n.ts';
import { installGuide, type InstallOutput } from '../install.ts';
import { EMPTY_FORM, installSection, levelLine, stepText, webFactList } from '../page.ts';
import { day, guiSentence, KIND, KIND_PLURAL, levelLabel, OS_NAME, PRICE, PROCESSING, passed, webLevelLabel } from '../ui/facts.ts';
import { esc, link, listOf, safeUrl } from '../ui/html.ts';
import { icon, osMark, type IconName } from '../ui/icons.ts';
import { age, badge, compareToggle, coverage, fitz, kindTag, levelIcon, measure, osList, runFacts, tape, type FitzName, type MeasureRow } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';
import { posterOf, videoPath } from '../video.ts';
import { NO_INSTALL_LABEL, noInstallLabel, webRanSentence } from '../webapp.ts';

const MATURITY: Record<string, string> = {
  get stable() { return L('Stable', '穩定版'); },
  get beta() { return L('Beta', 'Beta 版'); },
  get alpha() { return L('Alpha', 'Alpha 版'); },
  get prototype() { return L('Prototype', '原型'); },
};

/** Fitz looks pleased only when a run reached the tool's main function and passed. */
function faceFor(entry: Entry): FitzName {
  const web = webCheck(entry);
  if (isWebApp(entry)) return web ? (web.level === 'install' ? 'testing' : 'success') : 'thinking';
  const guide = bestGuide(entry);
  if (!guide) return entry.verification.level === 'failed' ? 'test-failed' : 'thinking';
  if (!passed(guide.run.gui)) return 'neutral';
  return guide.run.level === 'install' ? 'testing' : 'success';
}

/** Where it runs, as the value of the sheet's "Runs" row (PROCESSING's words would repeat the label). */
const RUNS: Record<string, string> = {
  get local() { return L('On your machine', '在你的電腦上'); },
  get cloud() { return L('In the cloud', '雲端'); },
  get hybrid() { return L('Locally and in the cloud', '本機與雲端'); },
};

/**
 * At a glance, as a tailor's measurement record (measure()): one fact a row, the label joined to its value by a dotted
 * leader. Every fact keeps a value: what the profile does not say reads "not stated" (quiet), and a tool pickfit has
 * not run reads "Not verified yet" (caution), never an empty row.
 */
function factSheet(entry: Entry, now: Date): string {
  const web = isWebApp(entry);
  const check = webCheck(entry);
  /** A fact the profile has, or "not stated" in the quiet tone: a row never goes empty. */
  const fact = (label: string, value: string | null | undefined, html: (v: string) => string): MeasureRow =>
    value ? { label, value: html(value) } : { label, value: `<span class="unknown">${L('not stated', '未說明')}</span>`, tone: 'quiet' };
  /** The systems as their marks, named on hover and for screen readers (osList): three names would not fit a row. */
  const systems = (oses: OS[], tone: 'pass' | 'quiet') => osList(oses, { tone });
  const notYet: MeasureRow = { label: L('Verified on', '已驗證於'), value: esc(L('Not verified yet', '尚未驗證')), tone: 'caution' };
  const verified: MeasureRow = web
    ? check
      ? { label: notYet.label, value: L(`In a browser, ${esc(day(check.checked_at))}`, `在瀏覽器中，${esc(day(check.checked_at))}`), tone: 'pass' }
      : notYet
    : verifiedOn(entry).length
      ? { label: notYet.label, value: systems(verifiedOn(entry), 'pass'), tone: 'pass' }
      : notYet;
  const rows: MeasureRow[] = [
    { label: L('Kind', '類型'), value: kindTag(entry) },
    verified,
    web
      ? { label: L('Runs in', '執行環境'), value: esc(L('Any modern browser, nothing to install', '任何現代瀏覽器，免安裝')) }
      : // The README's claim, not a run: quiet either way.
        { ...fact(L('Claims to run on', '宣稱支援'), entry.platforms.length ? systems(entry.platforms, 'quiet') : null, (named) => named), tone: 'quiet' },
    fact(L('Price', '價格'), entry.pricing, (p) => esc(PRICE[p] ?? p) + (entry.pricing_note ? ` <small>${esc(entry.pricing_note)}</small>` : '')),
    ...(web ? [] : [fact(L('Runs', '執行位置'), entry.processing, (p) => esc(RUNS[p] ?? PROCESSING[p] ?? p))]),
    fact(L('Licence', '授權'), entry.license, (l) => `<code>${esc(l)}</code>${entry.open_source ? ` <small>${L('open source', '開源')}</small>` : ''}`),
    ...(web ? [] : [fact(L('Last release', '最新版本'), entry.last_release, (d) => `${esc(day(d))} <small>(${esc(age(d, now) ?? '')})</small>`)]),
  ];
  if (entry.maturity) rows.push({ label: L('Maturity', '成熟度'), value: esc(MATURITY[entry.maturity] ?? entry.maturity) });
  return measure(rows, { cls: 'glance-sheet' });
}

/** What the README says you need first; nothing when it lists nothing. */
function prerequisites(entry: Entry): string {
  const p = entry.prerequisites;
  const items: string[] = [];
  if (p.runtimes.length) {
    const list = p.runtimes.map((r) => `<code>${esc(r)}</code>`).join(', ');
    items.push(L(`Runtimes: ${list}`, `執行環境：${list}`));
  }
  if (p.system_packages.length) {
    const list = p.system_packages.map((r) => `<code>${esc(r)}</code>`).join(', ');
    items.push(L(`System packages: ${list}`, `系統套件：${list}`));
  }
  if (p.gpu === 'required') items.push(L('A GPU is required', '需要 GPU'));
  else if (p.gpu === 'optional') items.push(L('A GPU is optional', '可選用 GPU'));
  if (p.min_ram_gb) items.push(L(`At least ${p.min_ram_gb} GB of RAM`, `至少 ${p.min_ram_gb} GB 記憶體`));
  if (p.apple_silicon_only) items.push(L('Apple silicon only', '僅支援 Apple 晶片'));
  if (p.network === 'required') items.push(L('Needs the network', '需要網路'));
  if (p.api_keys.length) {
    const list = p.api_keys.map(esc).join(', ');
    items.push(L(`Keys or accounts: ${list}`, `金鑰或帳號：${list}`));
  }
  return items.length ? `<div class="prereq"><h4>${L('You need first', '需要先準備')}</h4><ul>${items.map((i) => `<li>${i}</li>`).join('')}</ul></div>` : '';
}

// ---------------------------------------------------------------- the clip, with chapters

/** The first run with a clip: install guides first (they are what a reader follows), then other passed runs. */
function firstVideo(entry: Entry): RunVideo | null {
  const runs = [...OSES.flatMap((os) => (entry.install[os] ? [entry.install[os].run] : [])), ...entry.verification.passed_runs];
  return runs.find((r) => r.video)?.video ?? null;
}

/** usage_guide's plain title for a feature, if it has one. */
const guideTitle = (entry: Entry, feature: string) => entry.usage_guide?.features.find((f) => f.feature === feature)?.title ?? null;

/** The clip opened at a time (a media fragment), so a chapter link works without the page script too. */
const atTime = (slug: string, video: RunVideo, s: number) => `${videoPath(slug, video.clip)}#t=${s}`;

/** m:ss for a time in seconds. */
export const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

export interface Chapter {
  start: number;
  end: number;
  title: string;
}

/** The clip's chapters for the page: a feature's plain title when there is one, fixed words for the two cards. */
/** Desktop and web apps: the visual deduction that is in the quality score. An app not checked yet says so plainly:
 * nothing is taken off for that. */
export function visualLine(entry: Entry): string {
  const v = entry.visual;
  if (!v) return '';
  if (v.status === 'not_checked') {
    return `<p class="small quiet visual-check">${L('Not visually checked yet, so nothing is taken off.', '尚未做視覺檢查，所以不扣分。')}</p>`;
  }
  if (v.status === 'clean') {
    return `<p class="small visual-check">${L('Visual check: no defect found.', '視覺檢查：沒有發現缺陷。')}</p>`;
  }
  const items = (v.defects ?? []).map((d) => `<li>${esc(d.problem)}</li>`).join('');
  return `<div class="small visual-check"><p>${L('Visual check found a defect: −5%', '視覺檢查發現缺陷：−5%')}</p>` +
    (items ? `<ul>${items}</ul>` : '') + `</div>`;
}

export function chaptersOf(entry: Entry, video: RunVideo): Chapter[] {
  const list = [...(video.chapters ?? [])].filter((c) => c.start_s >= 0 && c.start_s < video.seconds).sort((a, b) => a.start_s - b.start_s);
  return list.map((c, i) => ({
    start: c.start_s,
    end: i + 1 < list.length ? list[i + 1].start_s : video.seconds,
    title: c.feature
      ? (guideTitle(entry, c.feature) ?? c.title)
      : i === 0
        ? L('Recorded by pickfit', 'pickfit 錄製')
        : L('Unedited recordings', '原始錄影'),
  }));
}

/**
 * The app itself, first: pickfit's own clip of it running. With chapters, the page script swaps the native
 * controls for a seek bar cut into the chapters (data-player), and the list under the clip jumps to each one.
 * Without the script, or without chapters, it is the browser's own player.
 */
function showcase(entry: Entry): string {
  const video = firstVideo(entry);
  if (!video) return '';
  const slug = entry.slug;
  const chapters = chaptersOf(entry, video);
  const seconds = Math.round(video.seconds);
  const player = chapters.length
    ? `<div class="player-bar" data-bar hidden>` +
      `<button type="button" class="player-btn" data-play aria-label="${L('Play', '播放')}" data-label-play="${L('Play', '播放')}" data-label-pause="${L('Pause', '暫停')}">${icon('play')}${icon('pause')}</button>` +
      `<div class="chap-track" data-track role="slider" tabindex="0" aria-label="${L('Seek by chapter', '依段落跳轉')}" aria-valuemin="0" aria-valuemax="${seconds}" aria-valuenow="0">` +
      chapters
        .map((c) => `<span class="chap-seg" data-start="${c.start}" data-end="${c.end}" data-title="${esc(c.title)}"><span class="chap-fill"></span></span>`)
        .join('') +
      `<span class="chap-tip" data-tip-box hidden></span></div>` +
      `<span class="player-time" data-time>0:00 / ${clock(video.seconds)}</span>` +
      `<button type="button" class="player-btn" data-mute aria-label="${L('Mute', '靜音')}">${icon('volume-2')}${icon('volume-x')}</button>` +
      `<button type="button" class="player-btn" data-full aria-label="${L('Full screen', '全螢幕')}">${icon('maximize')}</button>` +
      `</div>`
    : '';
  // The chapters sit beside the clip on a wide screen (one column with it), under it on a narrow one.
  const list = chapters.length
    ? `<div class="chap-list"><h2 class="chap-head" id="chapters-title">${L('Chapters', '段落')}</h2>` +
      `<ol class="chapters" aria-labelledby="chapters-title">` +
      chapters
        .map((c, i) => `<li><a href="${esc(atTime(slug, video, c.start))}" data-seek="${c.start}"${i === 0 ? ' aria-current="true"' : ''}><span class="chap-time">${clock(c.start)}</span><span class="chap-title">${esc(c.title)}</span></a></li>`)
        .join('') +
      `</ol></div>`
    : '';
  return (
    `<figure class="showcase"${chapters.length ? ' data-player' : ''}>` +
    `<div class="player">` +
    `<video controls preload="metadata" playsinline poster="${esc(videoPath(slug, posterOf(video.clip)))}" aria-describedby="showcase-cap">` +
    `<source src="${esc(videoPath(slug, video.clip))}" type="video/mp4">` +
    `<a href="${esc(videoPath(slug, video.clip))}">${L('Download the clip', '下載影片')}</a></video>` +
    player +
    `</div>` +
    `<figcaption id="showcase-cap">${L(
      `${esc(entry.name)} running, recorded by pickfit on ${esc(day(video.recorded_at))} · ${seconds} s`,
      `${esc(entry.name)} 實際執行，由 pickfit 於 ${esc(day(video.recorded_at))} 錄製 · ${seconds} 秒`,
    )}</figcaption>` +
    list +
    `</figure>`
  );
}

// ---------------------------------------------------------------- how far pickfit got

type StageState = 'done' | 'open' | 'warn';
interface Stage {
  label: string;
  state: StageState;
  tip: string;
}

const featuresWork = (checked: number, total: number) => L(`${checked} of ${total} features work`, `${total} 項功能中 ${checked} 項可用`);

/** A run's progress in four stages a reader can scan: installed, started, used, offline. */
function stagesFor(entry: Entry, g: InstallGuide): Stage[] {
  const r = g.run;
  const gui = r.gui ?? null;
  const f = featuresOut(entry, g);
  const total = f.checked.length + f.not_checked.length;
  const deep = r.level !== 'install' || f.checked.length > 0;
  const started: Stage = gui
    ? passed(gui)
      ? {
          label: gui.screen === 'main_ui' ? L('Opens', '可以開啟') : L('Opens to its setup screen', '開啟後進入設定畫面'),
          state: 'done',
          tip: L('Its window came up on a clean machine', '在乾淨的機器上能開出視窗'),
        }
      : { label: L('Window shows a problem', '視窗顯示異常'), state: 'warn', tip: L('Its window showed an error or stayed blank', '視窗出現錯誤或一直空白') }
    : g.mcp
      ? { label: L('Connects', '可以連線'), state: 'done', tip: L('An MCP client connected and listed its tools', 'MCP 用戶端連上並列出它的工具') }
      : { label: L('Starts', '可以啟動'), state: 'done', tip: L('It ran on a clean machine', '在乾淨的機器上能執行') };
  const used: Stage =
    f.recorded && total
      ? { label: featuresWork(f.checked.length, total), state: f.checked.length ? 'done' : 'open', tip: L('Features pickfit used and checked', 'pickfit 實際用過並檢查的功能') }
      : deep
        ? {
            label: g.mcp
              ? L('A tool call works', '工具呼叫可用')
              : r.level === 'inference'
                ? L('Produces output', '能產生輸出')
                : r.level === 'service'
                  ? L('Answers requests', '能回應請求')
                  : L('Main function works', '主要功能可用'),
            state: 'done',
            tip: L('pickfit used it, not just started it', 'pickfit 實際用過，不只是啟動'),
          }
        : { label: L('Not used yet', '還沒實際使用'), state: 'open', tip: L('pickfit started it but did not use a feature', 'pickfit 啟動了它，但沒有使用功能') };
  const offline = gui ? gui.launch_offline : g.works_offline;
  const net: Stage =
    offline === true
      ? { label: L('Works offline', '可離線使用'), state: 'done', tip: L('It passed again with the network off', '關掉網路後再次通過') }
      : offline === false
        ? { label: L('Needs the network', '需要網路'), state: 'open', tip: L('It needed the network to work', '它需要網路才能運作') }
        : { label: L('Offline not checked', '未檢查離線'), state: 'open', tip: L('pickfit did not try it without the network', 'pickfit 沒有在無網路下試過') };
  return [{ label: L('Installs', '可以安裝'), state: 'done', tip: L('Its install steps worked on a clean machine', '安裝步驟在乾淨的機器上可行') }, started, used, net];
}

function stageRow(stages: Stage[]): string {
  const mark: Record<StageState, IconName> = { done: 'check', open: 'circle-dashed', warn: 'triangle-alert' };
  return (
    `<ol class="prog-stages">` +
    stages.map((s) => `<li class="prog-stage prog-${s.state}" data-tip="${esc(s.tip)}"><span class="prog-bar"></span><span class="prog-label">${icon(mark[s.state])}${esc(s.label)}</span></li>`).join('') +
    `</ol>`
  );
}

const progressTitle = () => `<h2 id="progress-title">${L('How far pickfit got', 'pickfit 測到哪一步')}</h2>`;

/** One row per verified system, and the systems the project claims that pickfit has not tried. */
function progress(entry: Entry): string {
  if (isWebApp(entry)) {
    const check = webCheck(entry);
    if (!check) return '';
    const f = featuresOut(entry, null);
    const total = f.checked.length + f.not_checked.length;
    const stages: Stage[] = [
      { label: L('Opens in a browser', '可在瀏覽器開啟'), state: 'done', tip: L('Its main screen loaded in pickfit’s browser', '主畫面在 pickfit 的瀏覽器中載入') },
      total
        ? { label: featuresWork(f.checked.length, total), state: f.checked.length ? 'done' : 'open', tip: L('Features pickfit used and checked', 'pickfit 實際用過並檢查的功能') }
        : check.level === 'function'
          ? { label: L('Used in a browser', '已在瀏覽器中使用'), state: 'done', tip: webLevelLabel(check) }
          : { label: L('Not used yet', '還沒實際使用'), state: 'open', tip: webLevelLabel(check) },
    ];
    return `<section class="block progress" aria-labelledby="progress-title">${progressTitle()}${stageRow(stages)}</section>`;
  }
  const oses = OSES.filter((os) => entry.install[os]);
  if (!oses.length) {
    return (
      // The head's Fitz already wears the thinking face: one Fitz on the screen.
      `<section class="block" aria-labelledby="progress-title">${progressTitle()}` +
      `<div class="empty"><div><p>` +
      L(
        `<b>pickfit hasn’t verified ${esc(entry.name)} yet</b>, so it gives no install steps and never suggests it.`,
        `<b>pickfit 還沒驗證過 ${esc(entry.name)}</b>，所以不提供安裝步驟，也不會推薦它。`,
      ) +
      `</p><p class="quiet">${entry.verification.level === 'failed' ? L('A verification run did not pass. ', '有一次驗證測試沒通過。') : ''}${L('What follows comes from its README only.', '以下只依據它的 README。')}</p></div></div></section>`
    );
  }
  const rows = oses.map((os) => {
    const g = entry.install[os]!;
    return `<div class="progress-row" data-os="${os}"><p class="progress-sys">${osMark(os)}${esc(OS_NAME[os])}${g.run.arch ? ` <span class="arch">${esc(g.run.arch)}</span>` : ''}</p>${stageRow(stagesFor(entry, g))}</div>`;
  });
  // More than one system: the page script keeps the reader's own (or the first) in view and folds the rest here.
  // Without the script every row stays, one under the other.
  const more = rows.length > 1 ? `<details class="progress-more" data-progress-more hidden><summary>${L('Other systems', '其他系統')}${icon('chevron-down')}</summary></details>` : '';
  const untried = entry.platforms.filter((os) => !entry.install[os]);
  const names = esc(listOf(untried.map((os) => OS_NAME[os])));
  const note = untried.length
    ? `<p class="small quiet">${L(`${names}: the project says it runs there; pickfit hasn’t tried it.`, `${names}：專案說支援，但 pickfit 還沒試過。`)}</p>`
    : '';
  return `<section class="block progress" aria-labelledby="progress-title">${progressTitle()}${rows.join('')}${more}${note}</section>`;
}

// ---------------------------------------------------------------- what it does

/** features.ts writes "<reason>: <the run's note>"; a person needs only the note when there is one. */
const featureWhy = (detail: string) => {
  const at = detail.indexOf(': ');
  return (at > 0 ? detail.slice(at + 2) : detail).replace(/^not checked:?\s*/i, '');
};

/** Why the features come from the profile alone: a run from before feature checks, or no run at all. */
const notRecorded = (entry: Entry, ran: boolean) =>
  ran
    ? L(
        'This run came before pickfit checked features one by one, so these come from the README only.',
        '這次測試早於 pickfit 開始逐項檢查功能，所以以下只依據 README。',
      )
    : L(
        `pickfit hasn’t run it yet, so these come from ${isWebApp(entry) ? 'its own site' : 'the README'} only.`,
        `pickfit 還沒測過它，所以以下只依據${isWebApp(entry) ? '它自己的網站' : ' README'}。`,
      );

/** Where to watch one feature: its chapter in the clip, else the raw recording that shows it. */
function featureClip(entry: Entry, feature: string): string {
  const video = firstVideo(entry);
  if (!video) return '';
  const chapter = video.chapters?.find((c) => c.feature === feature);
  if (chapter) {
    return `<a class="watch" href="${esc(atTime(entry.slug, video, chapter.start_s))}" data-seek="${chapter.start_s}">${L(`Watch it at ${clock(chapter.start_s)}`, `從 ${clock(chapter.start_s)} 開始看`)}</a>`;
  }
  const at = video.features.indexOf(feature);
  const raw = at < 0 ? undefined : video.raw.find((r) => r.feature_index === at);
  return raw
    ? `<a class="watch" href="${esc(videoPath(entry.slug, raw.file))}">${L(`Watch it (${Math.round(raw.seconds)} s)`, `觀看（${Math.round(raw.seconds)} 秒）`)}</a>`
    : '';
}


function featureList(entry: Entry, f: FeaturesOut): string {
  const guide = entry.usage_guide ?? null;
  const titles = new Map((guide?.features ?? []).map((g) => [g.feature, g]));
  const title = (feature: string) => esc(titles.get(feature)?.title ?? feature.charAt(0).toUpperCase() + feature.slice(1));
  const items = [
    ...f.checked.map(({ feature }) => {
      const steps = titles.get(feature)?.steps ?? [];
      const clip = featureClip(entry, feature);
      const how =
        steps.length || clip
          ? `<details class="how-to"><summary>${L('How to use it', '怎麼使用')}</summary>${steps.length ? `<ol>${steps.map((s) => `<li>${stepText(s)}</li>`).join('')}</ol>` : ''}${clip}</details>`
          : '';
      return `<li class="feat-ok"><div><span class="feat-title">${title(feature)}</span>${how}</div><span class="feat-state">${icon('check')}${L('Tested', '已測試')}</span></li>`;
    }),
    // The feature is the row; whether pickfit tested it is the mark on the right, and why not is only its tooltip.
    ...f.not_checked.map((n) => {
      const failed = n.reason === 'test_failed';
      const why = esc(featureWhy(n.detail));
      return (
        `<li class="${failed ? 'feat-fail' : 'feat-open'}"><div><span class="feat-title">${title(n.feature)}</span></div>` +
        `<span class="feat-state" tabindex="0" data-tip="${why}">${icon(failed ? 'x' : 'circle-dashed')}${failed ? L('Test failed', '測試未通過') : L('Not tested', '未測試')}</span></li>`
      );
    }),
  ];
  if (!items.length) return '';
  const ran = bestGuide(entry) !== null || webCheck(entry) !== null;
  const from = f.recorded ? '' : `<p class="quiet">${notRecorded(entry, ran)}</p>`;
  return `${from}<ul class="feat-list">${items.join('')}</ul>`;
}

/** What the project says it is good for, and what it stands in for: README words, so quieter than the features a run ticked. */
function goodFor(entry: Entry, heading: boolean): string {
  const uses = entry.use_cases.length ? `<ul class="uses">${entry.use_cases.map((u) => `<li>${esc(u)}</li>`).join('')}</ul>` : '';
  const alt = entry.alternatives_to.length ? `<p><span class="lead-in">${L('An alternative to', '可替代')}</span> ${esc(listOf(entry.alternatives_to))}${L('.', '。')}</p>` : '';
  if (!uses && !alt) return '';
  const title = L('Good for', '適合用來');
  return heading
    ? `<section class="block good-for" aria-labelledby="uses-title"><h2 id="uses-title">${title}</h2>${uses}${alt}</section>`
    : `${uses ? `<h3>${title}</h3>${uses}` : ''}${alt}`;
}

/** What it does: the features, each ticked when a run checked it. With no feature list, what it is good for says what it does instead. */
function about(entry: Entry, f: FeaturesOut): string {
  const features = featureList(entry, f);
  const parts = [entry.why_worth_it ? `<p class="fit">${esc(entry.why_worth_it)}</p>` : '', features, features ? '' : goodFor(entry, false)].join('');
  return parts ? `<section class="block about" aria-labelledby="about-title"><h2 id="about-title">${L('What it does', '它能做什麼')}</h2>${parts}</section>` : '';
}

// ---------------------------------------------------------------- install

/** The guide as a reader follows it: README mistakes only, no trailing stderr redirect, and for a GUI app where to find it instead of a shell command. */
function readerGuide(out: InstallOutput, hint: string | null, gui: boolean): InstallOutput {
  return {
    ...out,
    steps: out.steps.map((s) => ({ ...s, command: s.command.replace(/\s+2>&1$/, '') })),
    known_issues: out.known_issues.filter((k) => k.kind === 'readme_wrong' || !k.kind),
    first_task: gui && hint ? null : out.first_task,
    first_task_setup: gui && hint ? [] : out.first_task_setup,
  };
}

const installTitle = (en: string, zh: string) => `<h2 id="install-title">${L(en, zh)}</h2>`;

function install(catalog: Catalog, entry: Entry): string {
  if (isWebApp(entry) && entry.web) return webRun(entry);
  const oses = OSES.filter((os) => entry.install[os]);
  if (!oses.length) {
    const needs = prerequisites(entry);
    return needs ? `<section class="block" aria-labelledby="install-title">${installTitle('Use it', '使用')}${needs}</section>` : '';
  }
  const hint = entry.usage_guide?.open_hint ?? null;
  // What you need first sits in each system's install step, where it can differ by system.
  const needs = prerequisites(entry);
  const tabbed = oses.length > 1;
  const sysLabel = (os: OS) => {
    const arch = entry.install[os]!.run.arch;
    return `${osMark(os)}${esc(OS_NAME[os])}${arch ? ` <span class="arch">${esc(arch)}</span>` : ''}`;
  };
  // One section on the page ground: the systems as text tabs across its top, then that system's steps (no card).
  const panels = oses.map((os: OS) => {
    const g = entry.install[os]!;
    const out = readerGuide(installGuide(catalog, { slug: entry.slug, os }), hint, !!g.run.gui);
    return (
      `<div class="run-panel" id="install-${os}"${tabbed ? ` role="tabpanel" aria-labelledby="tab-${os}" data-os="${os}"` : ''}>` +
      `<div class="run-head"><h3>${sysLabel(os)}</h3></div>` +
      installSection(out, { ...EMPTY_FORM, os }, true, true, { hint, needs }) +
      `</div>`
    );
  });
  // More than one system: tabs, which the page script shows and turns to the reader's own system.
  // Without the script every system's steps stay, one under the other.
  const tabs = tabbed
    ? `<div class="os-tabs" role="tablist" aria-label="${L('Your system', '你的系統')}" data-os-tabs hidden>` +
      oses.map((os, i) => `<button type="button" role="tab" id="tab-${os}" aria-controls="install-${os}" aria-selected="${i === 0}" data-os="${os}"${i ? ' tabindex="-1"' : ''}>${sysLabel(os)}</button>`).join('') +
      `</div>`
    : '';
  return `<section class="block" aria-labelledby="install-title">${installTitle('Use it', '使用')}<div class="use-it">${tabs}${panels.join('')}</div></section>`;
}

/** A web app: open it, and the facts a person weighs before typing anything in. */
function webRun(entry: Entry): string {
  const check = webCheck(entry);
  const url = entry.web!.url;
  const open = link(url, L('Open the site', '開啟網站'), 'btn btn-primary btn-sm');
  if (!check) {
    return (
      `<section class="block" aria-labelledby="install-title">${installTitle('Open it', '開啟')}` +
      `<div class="empty"><div><p>` +
      L(
        `<b>pickfit hasn’t checked ${esc(entry.name)} in its browser yet</b>, so it never suggests it.`,
        `<b>pickfit 還沒在瀏覽器中檢查過 ${esc(entry.name)}</b>，所以不會推薦它。`,
      ) +
      `</p><p class="quiet">${L('The profile above comes from its own site only.', '上方簡介只依據它自己的網站。')}</p></div></div></section>`
    );
  }
  return (
    `<section class="block" aria-labelledby="install-title">${installTitle('Open it', '開啟')}` +
    `<div class="use-it use-web" id="run-web"><div class="run-head"><h3>${esc(noInstallLabel())}</h3></div>` +
    // Where it opens, the address written on a ruled line with the one action at its end; then what pickfit's browser saw.
    (open
      ? `<div class="web-bar"><span class="web-addr">${icon('globe')}<span translate="no">${esc(url.replace(/^https?:\/\//, '').replace(/\/$/, ''))}</span></span>${open}</div>`
      : '') +
    webFactList(entry, 'web-facts-grid') +
    `</div></section>`
  );
}

// ---------------------------------------------------------------- how pickfit tested it

function rawList(slug: string, video: RunVideo): string {
  const raw = video.raw
    .map((r) => {
      const shows = r.feature_index != null ? video.features[r.feature_index] : null;
      return (
        `<li><a href="${esc(videoPath(slug, r.file))}" download>${esc(r.file)}</a> <span class="quiet">${L(`(${Math.round(r.seconds)} s)`, `（${Math.round(r.seconds)} 秒）`)}${shows ? ` ${esc(shows)}` : ''}</span>` +
        `<br><span class="quiet small">sha256</span> <code class="hash" translate="no">${esc(r.sha256)}</code></li>`
      );
    })
    .join('');
  return (
    `<p class="small">${L('Clip', '影片')} <code class="hash" translate="no">${esc(video.clip)}</code>, sha256 <code class="hash" translate="no">${esc(video.clip_sha256)}</code>. ` +
    `${L('It was cut from these unedited recordings:', '剪輯自以下原始錄影：')}</p><ul class="small raw-list">${raw}</ul>`
  );
}

/** Everything a skeptic wants and a user doesn't: where each run ran, who looked, the raw recordings, the sandbox-only differences. */
function tested(catalog: Catalog, entry: Entry): string {
  const parts: string[] = [];
  const recordLink = (url: string | null) => (url ? `<p>${link(url, L('Run record', '測試紀錄'))}</p>` : '');
  if (isWebApp(entry)) {
    const check = webCheck(entry);
    if (!check) return '';
    parts.push(levelLine(webLevelLabel(check), true) + `<p>${esc(webRanSentence(check))}</p>` + recordLink(safeUrl(check.evidence_url)));
  }
  for (const os of OSES.filter((o) => entry.install[o])) {
    const g = entry.install[os]!;
    const r = g.run;
    const evidence = { gui: r.gui, mcp: g.mcp };
    const box = installGuide(catalog, { slug: entry.slug, os }).known_issues.filter((k) => k.kind && k.kind !== 'readme_wrong');
    let mcpLine = '';
    if (g.mcp) {
      const transport = g.mcp.transport === 'stdio' ? 'stdio' : 'HTTP';
      mcpLine = `<p>${L(
        `An MCP client handshake over ${transport} listed ${g.mcp.tool_count} tool${g.mcp.tool_count === 1 ? '' : 's'}${g.mcp.called_tool ? `, and a call to <code>${esc(g.mcp.called_tool)}</code> returned a result` : ''}.`,
        `MCP 用戶端透過 ${transport} 連線，列出 ${g.mcp.tool_count} 個工具${g.mcp.called_tool ? `，呼叫 <code>${esc(g.mcp.called_tool)}</code> 也回傳了結果` : ''}。`,
      )}</p>`;
    }
    parts.push(
      `<div class="tested-run"><h3>${osMark(os)}${esc(OS_NAME[os])}${r.arch ? ` <span class="arch">${esc(r.arch)}</span>` : ''}</h3>` +
        levelLine(levelLabel(r.level, evidence), passed(r.gui), levelIcon(r.level, evidence)) +
        runFacts(r, { offline: r.gui ? null : g.works_offline, named: true }) +
        (r.gui ? `<p>${esc(guiSentence(r.gui))}</p>` : '') +
        mcpLine +
        (r.video ? rawList(entry.slug, r.video) : '') +
        (box.length
          ? `<h4>${L('Differences the test machine hit', '測試機器遇到的差異')}</h4><ul class="issues">${box
              .map((i) => `<li><span class="quiet">README:</span> ${esc(i.readme_said)}<br><span class="quiet">${L('In the test:', '測試中：')}</span> ${esc(i.actually_needed)}</li>`)
              .join('')}</ul>`
          : '') +
        recordLink(safeUrl(r.evidence_url)) +
        `</div>`,
    );
  }
  if (!parts.length) return '';
  return (
    `<details class="block tested"><summary><h2>${L('How pickfit tested it', 'pickfit 怎麼測的')}</h2>${icon('chevron-down')}</summary>` +
    `<p class="quiet">${L(
      'Each run starts from a clean machine, follows the steps above, and checks the result itself.',
      '每次測試都從乾淨的機器開始，照上面的步驟執行，並自行檢查結果。',
    )} <a href="/how">${L('How pickfit verifies', 'pickfit 怎麼驗證')}</a></p>` +
    `${parts.join('')}</details>`
  );
}

/** The kind a profile sits under in Browse: web apps have their own shelf. */
const crumb = (entry: Entry) => {
  const kind = isWebApp(entry) ? 'web_app' : entry.category;
  return `<a href="/browse?kind=${esc(kind)}">${esc(KIND_PLURAL[kind] ?? KIND[kind] ?? '')}</a>`;
};

export function renderTool(catalog: Catalog, entry: Entry, nonce: string): string {
  const now = new Date(catalog.built_at);
  const guide = bestGuide(entry);
  const features = featuresOut(entry, guide);
  const verified = isVerified(entry);
  const web = isWebApp(entry) ? webCheck(entry) : null;
  const on = listOf(verifiedOn(entry).map((os) => OS_NAME[os]));
  const badges = [
    web ? badge('info', L(NO_INSTALL_LABEL, '免安裝'), { icon: 'globe' }) : '',
    web
      ? badge('pass', L('Tested in a browser', '已在瀏覽器實測'), { icon: 'badge-check' })
      : verified && on
        ? badge('pass', L(`Tested on ${on}`, `已在 ${on} 上測試`), {
            icon: 'badge-check',
            marks: `<span aria-hidden="true">${L('Tested', '已測試')}</span>${verifiedOn(entry).map(osMark).join('')}`,
          })
        : badge('quiet', L('Not verified yet', '尚未驗證'), { icon: 'circle-dashed' }),
    entry.scores?.treasure ? badge('gem', L('Hidden gem', '寶藏'), { icon: 'gem', pop: 'pop-gem' }) : '',
  ].join('');
  const webUrl = entry.web?.url ?? null;
  // Links are underlined words; the one switch (Compare) keeps its pill.
  const links = [
    webUrl ? link(webUrl, L('Open it', '開啟'), 'tool-link') : '',
    !web && OSES.some((os) => entry.install[os]) ? `<a class="tool-link" href="#install-title">${L('Install', '安裝')}</a>` : '',
    link(entry.repo_url, L('Source code', '原始碼'), 'tool-link'),
    entry.homepage && entry.homepage !== entry.repo_url && entry.homepage !== webUrl ? link(entry.homepage, L('Homepage', '首頁'), 'tool-link') : '',
  ].join('');
  const sources = entry.sources
    .map((s) => safeUrl(s))
    .filter((s): s is string => !!s)
    .map((s) => `<li>${link(s, esc(s.replace(/^https?:\/\//, '').replace(/^api\.github\.com\/repos\//, 'github.com/')))}</li>`)
    .join('');
  // The clip is the page's focal point: with chapters it gets its own row, the chapters beside it where
  // At a glance would be; a clip without chapters leads the main column. Without a clip, how to use it leads
  // (the screen's one action), then what it does.
  const video = firstVideo(entry);
  const wide = !!video && chaptersOf(entry, video).length > 0;
  const clip = showcase(entry);
  // An unverified tool leads with that fact; a verified one keeps how far pickfit got below how to use it.
  const ran = OSES.some((os) => entry.install[os]) || !!web;
  const main =
    `<section class="head tool-head"><div class="wrap head-row"><div>` +
    `<p class="crumbs"><a href="/browse">${L('Browse', '瀏覽')}</a><span class="crumb-sep" aria-hidden="true">/</span>${crumb(entry)}</p>` +
    `<h1>${esc(entry.name)}</h1><p class="lede">${esc(entry.summary)}</p>` +
    `<div class="tool-facts"><p class="badges">${badges}</p><p class="tool-links">${links}${verified ? compareToggle(entry.slug, entry.name) : ''}</p></div></div>` +
    `${fitz(faceFor(entry), 96, { eager: true })}</div></section>` +
    (wide ? `<div class="wrap tool-clip">${clip}</div>` : '') +
    `<div class="wrap layout tool-layout"><div class="tool-main">` +
    (wide ? '' : clip) +
    (ran ? '' : progress(entry)) +
    (clip ? about(entry, features) + install(catalog, entry) : install(catalog, entry) + about(entry, features)) +
    `<div class="tool-more">` +
    (ran ? progress(entry) : '') +
    (features.checked.length + features.not_checked.length ? goodFor(entry, true) : '') +
    tested(catalog, entry) +
    `</div></div><aside class="side" aria-label="${L('At a glance', '一覽')}">` +
    `<div class="panel"><h2>${L('At a glance', '一覽')}</h2>${factSheet(entry, now)}<div class="panel-measure">` +
    tape(L('Quality', '品質'), entry.scores?.quality ?? null, { pop: 'pop-quality' }) +
    tape(L('Popularity', '知名度'), entry.scores?.popularity ?? null, { pop: 'pop-popularity', tone: 'quiet' }) +
    coverage(features, { pop: 'pop-features' }) +
    `</div>${visualLine(entry)}<p class="small quiet">${L('Scored apart; ranked by neither.', '兩項分開計分，排序不看分數。')} <a href="/how#scores">${L('How scores work', '評分方式')}</a></p></div>` +
    (sources ? `<details class="panel sources"><summary>${L('Sources', '來源')}</summary><ul class="small">${sources}</ul><p class="small quiet">${L('Every field in the profile cites one of these.', '簡介裡的每個欄位都引用下列其中一個來源。')}</p></details>` : '') +
    `</aside></div>`;
  return renderShell({
    nonce,
    title: `${entry.name}: ${web ? L('checked in a browser', '瀏覽器實測') : verified ? L('verified install steps', '已驗證的安裝步驟') : L('profile', '簡介')} · pickfit`,
    description: entry.summary,
    active: 'browse',
    main,
  });
}
