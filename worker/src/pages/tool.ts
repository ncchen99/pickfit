/**
 * One tool, for a person deciding whether to use it: what it looks like (pickfit's clip of it running,
 * with chapters when the clip has them), how far pickfit got with it, what it does (each advertised
 * feature, ticked when a run checked it, with how to use it), and how to install it. How pickfit tested
 * it sits folded at the bottom, for anyone who wants the evidence. Read from the catalog only; nothing
 * here calls a model. The plain feature titles, steps and open hint come from the record's usage_guide,
 * which names the model that wrote them.
 */
import { bestGuide, isVerified, isWebApp, OSES, securityOf, verifiedOn, webCheck, type Catalog, type Entry, type InstallGuide, type OS, type RunVideo, type GapCategory, type SecurityCheck, type SecurityFinding } from '../catalog.ts';
import { featuresOut, shownWorking, standInOnly, type FeaturesOut, type NotCheckedReason } from '../features.ts';
import { advisoriesOf } from '../security.ts';
import { freshness, passedAt } from '../freshness.ts';
import { ERROR_EXCERPT_MAX } from '../outcome.ts';
import { L, lang } from '../i18n.ts';
import { installGuide, type InstallOutput } from '../install.ts';
import { EMPTY_FORM, installSection, levelLine, stepText, webFactList } from '../page.ts';
import { day, guideTitle, guiSentence, KIND, KIND_PLURAL, levelLabel, OS_NAME, PRICE, PROCESSING, passed, webLevelLabel, webRunWords } from '../ui/facts.ts';
import { esc, link, listOf, safeUrl } from '../ui/html.ts';
import { icon, osMark, type IconName } from '../ui/icons.ts';
import { age, badge, compareToggle, confidenceRow, coverage, fitz, kindTag, levelIcon, measure, osList, popover, runFacts, tape, type FitzName, type MeasureRow } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';
import { coverageSection } from '../ui/coverage.ts';
import { captionsOf, posterOf, videoPath } from '../video.ts';
import { NO_INSTALL_LABEL, noInstallLabel } from '../webapp.ts';

const MATURITY: Record<string, string> = {
  get stable() { return L('Stable', '穩定版'); },
  get beta() { return L('Beta', 'Beta 版'); },
  get alpha() { return L('Alpha', 'Alpha 版'); },
  get prototype() { return L('Prototype', '原型'); },
};

/** Fitz looks pleased only when a run reached the tool's main function and passed. */
function faceFor(entry: Entry): FitzName {
  if (entry.standing === 'broken') return 'test-failed';
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
  rows.push(fact(L('For', '給誰用'), entry.used_by ? USED_BY[entry.used_by] : null, esc), freshnessRow(entry, now));
  return measure(rows, { cls: 'glance-sheet' });
}

/** Who uses it once recommended (brief 15.2): the record's used_by, in words. */
const USED_BY: Record<string, string> = {
  get agent() { return L('Agents', 'Agent'); },
  get human() { return L('People', '人'); },
  get both() { return L('People and agents', '人與 Agent'); },
};

/**
 * How fresh the last passing check is (brief 15.4): its age and the record's own re-verification cycle (else
 * STALE_DAYS). Pass while inside the cycle, caution once due, fail when the latest re-verification failed.
 */
function freshnessRow(entry: Entry, now: Date): MeasureRow {
  const label = L('Freshness', '驗證新鮮度');
  const v = entry.verification;
  const f = freshness(passedAt(entry), null, now, { cycleDays: v.reverify_cycle_days ?? null, dueAt: v.reverify_due_at ?? null, standing: entry.standing ?? null });
  const every = `<small>${esc(L(`re-verified every ${f.cycle_days} days`, `每 ${f.cycle_days} 天重驗`))}</small>`;
  if (entry.standing === 'broken') {
    const when = v.checked_at ? L(` on ${day(v.checked_at)}`, `（${day(v.checked_at)}）`) : '';
    return { label, value: `${esc(L(`Re-verification failed${when}`, `最近一次重驗失敗${when}`))} ${every}`, tone: 'fail' };
  }
  if (f.age_days === null) return { label, value: esc(L('Not verified yet', '尚未驗證')), tone: 'caution' };
  const ago = f.age_days === 0 ? L('Passed today', '今天通過') : L(`Passed ${f.age_days} ${f.age_days === 1 ? 'day' : 'days'} ago`, `${f.age_days} 天前通過`);
  return { label, value: `${esc(ago)} ${every}`, tone: f.overdue ? 'caution' : 'pass' };
}

/**
 * The tool's latest re-verification failed (standing broken, brief 15.4): said at the top of the page, before anything
 * that reads like a recommendation. The record is kept, not deleted, so an agent does not spend a try on it.
 */
function brokenBanner(entry: Entry): string {
  if (entry.standing !== 'broken') return '';
  const v = entry.verification;
  const failed = v.checked_at ? day(v.checked_at) : null;
  const last = v.last_passed_at ? day(v.last_passed_at) : null;
  const text = L(
    `pickfit re-ran it${failed ? ` on ${failed}` : ''} and it no longer works as recorded, so pickfit does not recommend it.` +
      (last ? ` It last passed on ${last}.` : '') +
      ' The record stays here so agents and people don’t spend a try on it.',
    `pickfit ${failed ? `在 ${failed} ` : ''}重驗時，它已經不能照紀錄運作，所以 pickfit 不推薦它。` +
      (last ? `上次通過是 ${last}。` : '') +
      '紀錄保留在這裡，讓 agent 和人不必白試一次。',
  );
  const note = entry.standing_note ? `<p class="small">${esc(entry.standing_note)}</p>` : '';
  return (
    `<div class="broken-banner" role="note" aria-labelledby="broken-title">${icon('triangle-alert')}<div>` +
    `<h2 id="broken-title">${L('Its latest re-verification failed', '最近一次重驗失敗')}</h2><p>${esc(text)}</p>${note}</div></div>`
  );
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

/** The clip opened at a time (a media fragment), so a chapter link works without the page script too. */
const atTime = (slug: string, video: RunVideo, s: number) => `${videoPath(slug, video.clip)}#t=${s}`;

/** m:ss for a time in seconds. */
export const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

export interface Chapter {
  start: number;
  end: number;
  title: string;
  /** Where the chapter's first segment is in its unedited recording (a clip cut since 11/19): the file, seconds. */
  raw?: { file: string; at: number };
}

// ---------------------------------------------------------------- the checks, as marks

type MarkTone = 'pass' | 'caution' | 'fail' | 'open';

/**
 * One check as a mark (DESIGN.md §8): its icon in the state's colour, the fact in words on hover, on focus and for screen
 * readers. Not checked is the same icon basted (dashed) in grey, so it never reads as passed. `label` names the check
 * beside the icon (screen readers get the fact instead); `count` puts the number found after it; `href` or `pop` makes
 * the mark open what it counts.
 */
function checkMark(tone: MarkTone, name: IconName, label: string, say: string, opts: { count?: number; href?: string; pop?: string } = {}): string {
  const cls = `check-mark mark-${tone}`;
  const tip = ` data-tip="${esc(say)}"`;
  const inner =
    `${icon(name)}<span class="check-label" aria-hidden="true">${esc(label)}</span>` +
    `${opts.count ? `<span class="check-count" aria-hidden="true">${opts.count}</span>` : ''}<span class="sr">${esc(say)}</span>`;
  if (opts.href) return `<a class="${cls}" href="${esc(opts.href)}"${tip}>${inner}</a>`;
  if (opts.pop) return `<button type="button" class="${cls}" popovertarget="${opts.pop}"${tip}>${inner}</button>`;
  return `<span class="${cls}" tabindex="0"${tip}>${inner}</span>`;
}

/** The checks' names, written beside their marks so the icon is never left to explain itself. */
const VISUAL = () => L('Visual check', '視覺檢查');
const SECURITY = () => L('Security check', '安全性檢查');

/** Desktop and web apps: what pickfit's visual check of its own screenshots found, as an eye. A defect's mark opens the
 * list of what looks wrong; nothing for a tool with no window. */
export function visualMark(entry: Entry): string {
  const v = entry.visual;
  if (!v) return '';
  if (v.status === 'not_checked') return checkMark('open', 'eye', VISUAL(), L('Not visually checked yet', '尚未做視覺檢查'));
  if (v.status === 'clean') {
    return checkMark('pass', 'eye-check', VISUAL(), L('Visual check: it looks right on screen, no defects on pickfit’s screenshots', '視覺檢查：畫面正常，pickfit 的截圖上沒有發現缺陷'));
  }
  const defects = v.defects ?? [];
  const n = defects.length;
  if (!n) return checkMark('caution', 'eye', VISUAL(), L('Visual check: a defect on pickfit’s screenshots', '視覺檢查：pickfit 的截圖上有缺陷'));
  const date = v.checked_at ? day(v.checked_at) : '';
  const body =
    `<ul class="visual-defects">${defects.map((d) => `<li>${esc(d.problem)}</li>`).join('')}</ul>` +
    `<p class="quiet">${L(`Seen on pickfit’s screenshots${date ? `, ${esc(date)}` : ''}.`, `來自 pickfit 的截圖${date ? `，${esc(date)}` : ''}。`)}</p>`;
  return (
    checkMark(
      'caution',
      'eye',
      VISUAL(),
      L(`Visual check: ${n} ${n === 1 ? 'defect' : 'defects'} on pickfit’s screenshots. Open to see what looks wrong`, `視覺檢查：pickfit 的截圖上有 ${n} 個缺陷，點開看哪裡不對`),
      { count: n, pop: 'pop-visual' },
    ) + popover('pop-visual', L('What looks wrong on screen', '畫面上哪裡不對'), body)
  );
}

/** Why a tool was not checked for known vulnerabilities, as the end of a sentence. */
const securityReason = (reason: string | undefined): string => {
  switch (reason) {
    case 'no_source':
      return L('there is no repository or package to read', '沒有可讀取的 repo 或套件');
    case 'no_lockfile':
      return L('there is no lockfile to read', '沒有可讀取的 lockfile');
    case 'lockfile_not_supported':
      return L('it uses a lockfile pickfit cannot read yet', '它用的 lockfile pickfit 還讀不了');
    case 'resolve_failed':
      return L('its dependencies could not be resolved', '無法解析它的相依套件');
    default:
      return '';
  }
};

/** Why part of a sec.v2 check could not be done, by its first gap's category, as the end of a sentence. */
const gapReason = (category: GapCategory | undefined): string => {
  switch (category) {
    case 'lockfile_missing':
      return L('part of it has no lockfile to read', '有一部分沒有可讀取的 lockfile');
    case 'lockfile_unreadable':
      return L('part of it uses a lockfile pickfit cannot read yet', '有一部分用的 lockfile pickfit 還讀不了');
    case 'resolve_failed':
      return L('some dependencies could not be resolved', '有些相依套件無法解析');
    case 'no_adapter':
      return L('part of it is in a language pickfit cannot read dependencies of yet', '有一部分是 pickfit 還讀不了相依套件的語言');
    case 'advisory_db':
      return L('the vulnerability database has no data for part of it', '漏洞資料庫沒有其中一部分的資料');
    case 'binary_no_metadata':
      return L('its binaries do not list what they were built from', '它的執行檔沒有列出用了哪些套件');
    case 'no_source':
      return L('there is no repository or package to read', '沒有可讀取的 repo 或套件');
    case 'tool_error':
      return L('a step of the check failed and will be retried', '檢查有一步失敗了，之後會重試');
    case 'platform_unsupported':
      return L('pickfit cannot list what installs on macOS or Windows yet', 'pickfit 還無法列出在 macOS 或 Windows 上裝了什麼');
    default:
      return '';
  }
};

/** How pickfit knows a finding's code is not used, as the end of a sentence (sec.v2's reachability methods). */
const unusedBecause = (method: string | null): string => {
  switch (method) {
    case 'entry_point_grep':
      return L('it never loads that part of the package', '程式沒有載入套件的這個部分');
    case 'option_grep':
      return L('it never turns on the option the hole needs', '程式沒有開啟漏洞需要的選項');
    case 'symbol_grep':
      return L('it never calls the affected code', '程式沒有呼叫受影響的程式碼');
    case 'import_grep':
      return L('it never imports the affected package', '程式沒有匯入受影響的套件');
    case 'govulncheck_binary':
    case 'govulncheck_source':
      return L('govulncheck found the affected code is never called', 'govulncheck 確認受影響的程式碼沒被呼叫');
    default:
      return L('pickfit found it is not used', 'pickfit 確認沒有用到');
  }
};

/** A finding's preconditions (pickfit/security.py's codes) as what follows "only when"; '' when it names none. */
export function whenItMatters(codes: string[] = []): string {
  const words = codes
    .map((c) => {
      const value = esc(c.slice(c.indexOf(':') + 1));
      if (c.startsWith('option:')) return L(`${value} is turned on`, `開啟了 ${value}`);
      if (c.startsWith('symbol:')) return L(`its code calls ${value}`, `程式呼叫了 ${value}`);
      if (c.startsWith('entry:')) return L(`it uses ${value}`, `用到 ${value}`);
      switch (c) {
        case 'local_access':
          return L('someone already has access to the machine', '對方已經能操作這台電腦');
        case 'adjacent_network':
          return L('the attacker is on the same network', '攻擊者和你在同一個網路');
        case 'physical_access':
          return L('someone has the device in hand', '對方拿得到這台裝置');
        case 'user_interaction':
          return L('you open a crafted file or link', '你打開特製的檔案或連結');
        case 'high_privileges':
          return L('the attacker already has high privileges', '攻擊者已經拿到高權限');
        case 'high_complexity':
          return L('specific conditions line up', '特定條件同時成立');
        case 'denial_of_service':
          return L('it gets crafted input (it can crash or hang, nothing leaks)', '收到特製的輸入（只會讓它當掉或卡住，不會外洩資料）');
        case 'server_side':
          return L('it runs as a server', '以伺服器模式執行');
        default:
          return '';
      }
    })
    .filter(Boolean);
  return [...new Set(words)].slice(0, 3).join(L(', or ', '或'));
}

/** Every tool: known vulnerabilities (OSV.dev) in what it brings, as a shield. A check from before levels (sec.v1) reads
 * by its status: a vulnerable one carries the count and jumps to the warning before the install steps, where the list
 * is; one pickfit could not check says so (a grey, dashed shield), never clean. A sec.v2 check reads by its level:
 * blocked and exposed are red, conditional amber (both jump to the list); present_unreachable and not_shipped are green
 * and say what was found where it does not run; partial is grey like unchecked, never clean. */
export function securityMark(entry: Entry): string {
  const s = securityOf(entry);
  const date = s.checked_at ? day(s.checked_at) : '';
  if (s.level) {
    const marked = securityLevelMark(entry, s, date);
    if (marked) return marked;
  }
  if (s.status === 'clean') {
    const n = s.packages_checked ?? 0;
    return checkMark(
      'pass',
      'shield-check',
      SECURITY(),
      L(
        `No known high or critical vulnerabilities (OSV.dev${date ? `, checked ${date}` : ''}, ${n} ${n === 1 ? 'package' : 'packages'})`,
        `沒有已知的高風險或嚴重漏洞（OSV.dev${date ? `，${date} 檢查` : ''}，共 ${n} 個套件）`,
      ),
    );
  }
  if (s.status === 'unchecked') {
    const why = securityReason(s.reason);
    return checkMark(
      'open',
      'shield',
      SECURITY(),
      why ? L(`Not checked for known vulnerabilities: ${why}`, `沒有檢查已知漏洞：${why}`) : L('Not checked for known vulnerabilities yet', '尚未檢查已知漏洞'),
    );
  }
  const vulns = advisoriesOf(s, Math.max(s.count ?? 0, s.findings?.length ?? 0, 1));
  return checkMark(
    'fail',
    'shield-alert',
    SECURITY(),
    L(
      `${vulns} known high or critical ${vulns === 1 ? 'vulnerability' : 'vulnerabilities'} in ${isWebApp(entry) ? 'the packages the site is built from' : 'packages it installs'} (OSV.dev${date ? `, ${date}` : ''}). See the list`,
      `${isWebApp(entry) ? '這個網站用到的' : '它安裝的'}套件有 ${vulns} 個已知的高風險或嚴重漏洞（OSV.dev${date ? `，${date}` : ''}）。看清單`,
    ),
    { count: vulns, href: '#security' },
  );
}

/** "pickfit checked N of M packages", when a sec.v2 check's coverage is partial; '' otherwise. */
const checkedPart = (s: SecurityCheck): string => {
  const c = s.coverage;
  if (!c || c.state !== 'partial') return '';
  const why = gapReason(c.gaps[0]?.category);
  const of = c.packages_found > c.packages_checked ? L(` of ${c.packages_found}`, `（已知至少 ${c.packages_found} 個）`) : '';
  return L(
    ` pickfit checked ${c.packages_checked}${of} packages${why ? `; ${why}` : ''}.`,
    `pickfit 檢查了 ${c.packages_checked} 個套件${of}${why ? `，${why}` : ''}。`,
  );
};

/** The shield of a sec.v2 check by its level and, apart, its coverage. '' for none with complete or no coverage, and
 * for an unchecked one: those read as sec.v1's clean and unchecked do. */
function securityLevelMark(entry: Entry, s: SecurityCheck, date: string): string {
  const web = isWebApp(entry);
  const where = web ? L('the packages the site is built from', '這個網站用到的套件') : L('packages it installs', '它安裝的套件');
  const n = s.packages_checked ?? 0;
  const counts = s.counts ?? {};
  const state = s.coverage?.state ?? 'complete';
  if (state === 'partial' && !(s.level === 'blocked' || s.level === 'exposed' || s.level === 'conditional')) {
    // Partly checked: never clean, never a vulnerability. What was found where it does not run is said too.
    const unused = Math.max(counts.present_unreachable ?? 0, s.unreachable?.length ?? 0);
    const only = counts.not_shipped ?? 0;
    const extra = [
      unused ? L(`${unused} found in code it installs but does not use`, `${unused} 個在裝了但沒用到的程式碼裡`) : '',
      only ? L(`${only} only in development or build tools`, `${only} 個只在開發或建置工具裡`) : '',
    ].filter(Boolean);
    return checkMark(
      'open',
      'shield',
      SECURITY(),
      L(
        `Only partly checked for known vulnerabilities: none known in the part pickfit could read.${checkedPart(s)}${extra.length ? ` Also ${extra.join(', ')}.` : ''}`,
        `已知漏洞只檢查了一部分，讀得到的部分沒有已知漏洞。${checkedPart(s)}${extra.length ? `另有${extra.join('、')}。` : ''}`,
      ),
    );
  }
  if (state === 'unchecked') return '';
  if (s.level === 'blocked' || s.level === 'exposed' || s.level === 'conditional') {
    const vulns = advisoriesOf(s, Math.max(s.count ?? 0, s.findings?.length ?? 0, 1));
    const plural = vulns === 1 ? 'vulnerability' : 'vulnerabilities';
    const say =
      s.level === 'blocked'
        ? L(
            `${vulns} known ${plural} in ${where}, with a malicious package or a hole attackers already exploit (OSV.dev, CISA${date ? `, ${date}` : ''}). See the list`,
            `${where}有 ${vulns} 個已知漏洞，其中有惡意套件或已遭實際利用的漏洞（OSV.dev、CISA${date ? `，${date}` : ''}）。看清單`,
          )
        : s.level === 'exposed'
          ? L(
              `${vulns} known high or critical ${plural} in ${where}, reached in normal use (OSV.dev${date ? `, ${date}` : ''}). See the list`,
              `${where}有 ${vulns} 個已知的高風險或嚴重漏洞，一般使用就會碰到（OSV.dev${date ? `，${date}` : ''}）。看清單`,
            )
          : L(
              `${vulns} known high or critical ${plural} in ${where} that matter only in some uses (OSV.dev${date ? `, ${date}` : ''}). See when`,
              `${where}有 ${vulns} 個已知的高風險或嚴重漏洞，只在某些用法下才會碰到（OSV.dev${date ? `，${date}` : ''}）。看是哪些情況`,
            );
    return checkMark(s.level === 'conditional' ? 'caution' : 'fail', 'shield-alert', SECURITY(), `${say}${checkedPart(s) ? `${L('.', '。')}${checkedPart(s)}` : ''}`, {
      count: vulns,
      href: '#security',
    });
  }
  const clean = L(
    `No known high or critical vulnerabilities in what it runs (OSV.dev${date ? `, checked ${date}` : ''}, ${n} ${n === 1 ? 'package' : 'packages'})`,
    `執行到的部分沒有已知的高風險或嚴重漏洞（OSV.dev${date ? `，${date} 檢查` : ''}，共 ${n} 個套件）`,
  );
  if (s.level === 'present_unreachable') {
    const unused = s.unreachable ?? [];
    const m = Math.max(counts.present_unreachable ?? 0, unused.length);
    const say = `${clean}${L(`. ${m} more in code it installs but does not use: open to see`, `。另有 ${m} 個在裝了但沒用到的程式碼裡，點開看`)}`;
    const body =
      `<ul class="vuln-list small">${unused
        .map((f) => {
          const cite = f.evidence.find((e) => /^\S+:\d+:/.test(e));
          return `<li><code>${esc(f.package)} ${esc(f.version)}</code> — ${advisoryLink(f)}${L(`: ${unusedBecause(f.method)}`, `：${unusedBecause(f.method)}`)}${cite ? ` <code>${esc(cite)}</code>` : ''}</li>`;
        })
        .join('')}</ul>` + (m > unused.length ? `<p class="quiet">${L(`${m - unused.length} more not listed here.`, `另有 ${m - unused.length} 筆未列出。`)}</p>` : '');
    return checkMark('pass', 'shield-check', SECURITY(), say, { pop: 'pop-security' }) + popover('pop-security', L('Found, but not in code it runs', '有找到，但不在執行到的程式碼裡'), body);
  }
  if (s.level === 'not_shipped') {
    const m = counts.not_shipped ?? 0;
    return checkMark('pass', 'shield-check', SECURITY(), m ? `${clean}${L(`. ${m} more only in development or build tools`, `。另有 ${m} 個只在開發或建置工具裡`)}` : clean);
  }
  return '';
}

/** At a glance's checks: the visual check (desktop and web apps) and known vulnerabilities, one mark each. */
const checkMarks = (entry: Entry) =>
  `<ul class="check-marks" aria-label="${L('Checks', '檢查')}">${[visualMark(entry), securityMark(entry)]
    .filter(Boolean)
    .map((m) => `<li>${m}</li>`)
    .join('')}</ul>`;

const severityOf = (f: SecurityFinding) =>
  f.malicious
    ? L('malicious package', '惡意套件')
    : f.severity === 'CRITICAL'
      ? L('critical', '嚴重')
      : f.severity === 'HIGH'
        ? L('high', '高風險')
        : f.severity === 'MODERATE'
          ? L('moderate', '中風險')
          : f.severity === 'LOW'
            ? L('low', '低風險')
            : L('unrated', '未評等');
const fixOf = (f: SecurityFinding) => (f.malicious ? '' : f.fixed_in ? L(`, fixed in ${esc(f.fixed_in)}`, `，${esc(f.fixed_in)} 已修正`) : L(', no fix yet', '，尚無修正版本'));
const advisoryLink = (f: Pick<SecurityFinding, 'advisory'>) => link(`https://osv.dev/vulnerability/${encodeURIComponent(f.advisory)}`, esc(f.advisory));
/** sec.v2, a finding that matters only in some uses: when, in one line (nothing when the check could not tell). */
const onlyWhen = (s: SecurityCheck, f: SecurityFinding) => {
  if (s.level !== 'conditional' || f.level !== 'conditional') return '';
  const when = whenItMatters(f.preconditions);
  return when
    ? ` <span class="quiet">${L(`Only when ${when}.`, `只在${when}時才會碰到。`)}</span>`
    : ` <span class="quiet">${L('pickfit could not tell when it applies.', 'pickfit 判斷不出在什麼情況下會碰到。')}</span>`;
};

/** Before the first install step, or beside the site's address: a known vulnerability, so a person reading the page
 * weighs it before installing, as an agent is told to through the install guide's warning. The worst two packages, then
 * the rest the check kept in a fold. Nothing for clean or unchecked. A sec.v2 check that matters only in some uses
 * (conditional) is amber and says when for each; blocked says not to install it. */
export function securityNotice(entry: Entry): string {
  const s = securityOf(entry);
  if (s.status !== 'vulnerable') return '';
  const all = s.findings ?? [];
  const count = Math.max(s.count ?? 0, all.length, 1);
  const vulns = advisoriesOf(s, count);
  const web = isWebApp(entry);
  // The worst of the first two packages (findings come worst first), so two advisories on one package do not hide a second.
  const worst = all.filter((f, i) => all.findIndex((g) => g.package === f.package) === i).slice(0, 2);
  const items = worst
    .map((f) => `<li><code>${esc(f.package)} ${esc(f.version)}</code>${f.summary ? ` ${esc(f.summary)}` : ''} ${L(`(${advisoryLink(f)}, ${severityOf(f)}${fixOf(f)})`, `（${advisoryLink(f)}，${severityOf(f)}${fixOf(f)}）`)}${onlyWhen(s, f)}</li>`)
    .join('');
  // The rest the check kept (at most 10 in all), and how many more it counted: the count above stays the full one.
  const rest = count - all.length;
  const more = (cls: string) =>
    rest > 0 ? `<p class="${cls}">${L(`${rest} more ${rest === 1 ? 'finding' : 'findings'} not listed here.`, `另有 ${rest} 筆未列出。`)}</p>` : '';
  // The fold holds the ones not named above, so no advisory is listed twice.
  const others = all.filter((f) => !worst.includes(f));
  const list = others.length
    ? `<details class="vuln-list small"><summary>${L(`See ${others.length} more`, `再看 ${others.length} 個`)}</summary><ul>` +
      others.map((f) => `<li><code>${esc(f.package)} ${esc(f.version)}</code> — ${advisoryLink(f)}${L(` (${severityOf(f)})`, `（${severityOf(f)}）`)}${fixOf(f)}${onlyWhen(s, f)}</li>`).join('') +
      `</ul>${more('quiet')}</details>`
    : more('small quiet');
  const date = s.checked_at ? day(s.checked_at) : '';
  const conditional = s.level === 'conditional';
  const heading =
    s.level === 'blocked'
      ? web
        ? L('Do not use it: a malicious package or an exploited hole', '不要使用：有惡意套件或已遭利用的漏洞')
        : L('Do not install it: a malicious package or an exploited hole', '不要安裝：有惡意套件或已遭利用的漏洞')
      : conditional
        ? web
          ? L('Before you use it: known vulnerabilities in some uses', '使用前先知道：某些用法下有已知漏洞')
          : L('Before you install: known vulnerabilities in some uses', '安裝前先知道：某些用法下有已知漏洞')
        : web
          ? L('Before you use it: known vulnerabilities', '使用前先知道：有已知漏洞')
          : L('Before you install: known vulnerabilities', '安裝前先知道：有已知漏洞');
  const reached = s.level === 'exposed' ? L(' Normal use reaches them.', '一般使用就會碰到。') : '';
  const lead = conditional
    ? L(
        ` Each matters only in some uses, which pickfit could not rule out. See when below before you ${web ? 'use it' : 'install it'}.`,
        `這些漏洞只在某些用法下才會碰到，pickfit 無法排除。${web ? '使用' : '安裝'}前先看看下面列的情況。`,
      )
    : L(` Weigh this before you ${web ? 'use it' : 'install it'}.`, `${web ? '使用' : '安裝'}前請先考慮。`);
  return (
    `<div class="notice ${conditional ? 'busy' : 'error'} security-notice" role="note" id="security">${fitz(conditional ? 'thinking' : 'sorry', 64)}<div>` +
    `<h3>${heading}</h3>` +
    `<p>${L(
      `pickfit found ${vulns} known high or critical ${vulns === 1 ? 'vulnerability' : 'vulnerabilities'}${count > vulns ? ` (${count} findings, one per affected package version)` : ''} in ${web ? 'the packages this site is built with' : 'the packages a fresh install brings'}${date ? ` (OSV.dev, ${esc(date)})` : ''}.${reached}${lead}`,
      `pickfit 在${web ? '這個網站用到的套件' : '安裝時會一併裝上的套件'}裡找到 ${vulns} 個已知的高風險或嚴重漏洞${count > vulns ? `（共 ${count} 筆，每個受影響的套件版本一筆）` : ''}${date ? `（OSV.dev，${esc(date)}）` : ''}，${reached ? reached : ''}${lead}`,
    )}</p>` +
    (items ? `<ul class="small">${items}</ul>` : '') +
    list +
    `</div></div>`
  );
}

/**
 * The clip's chapters for the page: its features, each by its plain title when there is one. A clip cut before 11/19
 * opens and closes on a card; those are not chapters (what they said is in "How pickfit tested it"): the last
 * feature's chapter runs to the clip's end.
 */
export function chaptersOf(entry: Entry, video: RunVideo): Chapter[] {
  const list = [...(video.chapters ?? [])]
    .filter((c) => c.feature && c.start_s >= 0 && c.start_s < video.seconds)
    .sort((a, b) => a.start_s - b.start_s);
  return list.map((c, i) => {
    const raw = c.raw != null ? video.raw[c.raw] : undefined;
    return {
      start: c.start_s,
      end: i + 1 < list.length ? list[i + 1].start_s : video.seconds,
      title: guideTitle(entry, c.feature!) ?? c.title,
      ...(raw && c.raw_s != null ? { raw: { file: raw.file, at: c.raw_s } } : {}),
    };
  });
}

/**
 * The app itself, first: pickfit's own clip of it running. With chapters, the page script swaps the native
 * controls for a seek bar cut into the chapters (data-player), and the list under the clip jumps to each one.
 * Without the script, or without chapters, it is the browser's own player. A clip has no sound (no mute button)
 * and, since 11/19, no words on its picture: its captions are a WebVTT track in the page's language, on by default,
 * with a CC button on the bar. Each chapter of such a clip also links to the moment in its unedited recording.
 */
function showcase(entry: Entry): string {
  const video = firstVideo(entry);
  if (!video) return '';
  const slug = entry.slug;
  const chapters = chaptersOf(entry, video);
  const seconds = Math.round(video.seconds);
  const captioned = !!video.captions?.length;
  const player = chapters.length
    ? `<div class="player-bar" data-bar hidden>` +
      `<button type="button" class="player-btn" data-play aria-label="${L('Play', '播放')}" data-label-play="${L('Play', '播放')}" data-label-pause="${L('Pause', '暫停')}">${icon('play')}${icon('pause')}</button>` +
      `<div class="chap-track" data-track role="slider" tabindex="0" aria-label="${L('Seek by chapter', '依段落跳轉')}" aria-valuemin="0" aria-valuemax="${seconds}" aria-valuenow="0">` +
      chapters
        .map((c) => `<span class="chap-seg" data-start="${c.start}" data-end="${c.end}" data-title="${esc(c.title)}"><span class="chap-fill"></span></span>`)
        .join('') +
      `<span class="chap-tip" data-tip-box hidden></span></div>` +
      `<span class="player-time" data-time>0:00 / ${clock(video.seconds)}</span>` +
      (captioned ? `<button type="button" class="player-btn" data-cc aria-pressed="true" aria-label="${L('Captions', '字幕')}">${icon('captions')}${icon('captions-off')}</button>` : '') +
      `<button type="button" class="player-btn" data-full aria-label="${L('Full screen', '全螢幕')}">${icon('maximize')}</button>` +
      `</div>`
    : '';
  // The chapters sit beside the clip on a wide screen (one column with it), under it on a narrow one.
  const list = chapters.length
    ? `<div class="chap-list"><h2 class="chap-head" id="chapters-title">${L('Chapters', '段落')}</h2>` +
      `<ol class="chapters" aria-labelledby="chapters-title">` +
      chapters
        .map(
          (c, i) =>
            `<li><a href="${esc(atTime(slug, video, c.start))}" data-seek="${c.start}"${i === 0 ? ' aria-current="true"' : ''}><span class="chap-time">${clock(c.start)}</span><span class="chap-title">${esc(c.title)}</span></a>` +
            (c.raw
              ? `<a class="chap-raw" href="${esc(`${videoPath(slug, c.raw.file)}#t=${c.raw.at}`)}" aria-label="${esc(L(`${c.title}: the unedited recording`, `${c.title}：原始錄影`))}">${L('Unedited', '原始錄影')}</a>`
              : '') +
            `</li>`,
        )
        .join('') +
      `</ol></div>`
    : '';
  const track = captioned
    ? `<track kind="captions" default srclang="${lang() === 'zh-TW' ? 'zh-Hant-TW' : 'en'}" label="${L('English', '中文')}" src="${esc(videoPath(slug, captionsOf(video.clip, lang())))}">`
    : '';
  return (
    `<figure class="showcase"${chapters.length ? ' data-player' : ''}>` +
    `<div class="player">` +
    `<video controls preload="metadata" playsinline poster="${esc(videoPath(slug, posterOf(video.clip)))}" aria-describedby="showcase-cap">` +
    `<source src="${esc(videoPath(slug, video.clip))}" type="video/mp4">` +
    track +
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

/** "2 of 4 features work": only the ones seen working. The ones checked against a stand-in are said apart, never counted as working. */
function featuresWork(f: FeaturesOut): string {
  const total = f.checked.length + f.not_checked.length;
  const works = shownWorking(f).length;
  const standIn = standInOnly(f).length;
  return (
    L(`${works} of ${total} features work`, `${total} 項功能中 ${works} 項可用`) +
    (standIn ? L(`, ${standIn} more checked against a stand-in`, `，另有 ${standIn} 項是用替身驗的`) : '')
  );
}

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
      ? { label: featuresWork(f), state: shownWorking(f).length ? 'done' : 'open', tip: L('Features pickfit used and checked', 'pickfit 實際用過並檢查的功能') }
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
        ? { label: featuresWork(f), state: shownWorking(f).length ? 'done' : 'open', tip: L('Features pickfit used and checked', 'pickfit 實際用過並檢查的功能') }
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
        `<b>pickfit hasn’t verified ${esc(entry.name)} yet</b>, so there are no tested install steps.`,
        `<b>pickfit 還沒驗證過 ${esc(entry.name)}</b>，所以沒有測過的安裝步驟。`,
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

/** Why a feature was not tested, in a reader's words (features.ts words it for agents, with the sandbox's own terms). */
const WHY_NOT: Record<NotCheckedReason, () => string> = {
  needs_account: () => L('It needs an account or an API key', '需要帳號或 API 金鑰'),
  needs_gpu: () => L('It needs a GPU', '需要 GPU'),
  needs_display: () => L('It needs a display or a browser', '需要螢幕或瀏覽器'),
  needs_hardware: () => L('It needs hardware such as a microphone, a camera or a device', '需要麥克風、相機或其他裝置'),
  needs_service: () => L('It needs an outside service or server', '需要外部服務或伺服器'),
  needs_more_resources: () => L('It needs more memory, disk or time than the test machine has', '需要的記憶體、磁碟或時間超過測試機器'),
  needs_container: () => L('It needs Docker or another container engine', '需要 Docker 或其他容器引擎'),
  needs_root: () => L('It needs root or a system service', '需要 root 權限或系統服務'),
  needs_toolchain: () => L('It needs a build from source with a compiler', '需要用編譯器從原始碼建置'),
  other_os: () => L('It runs only on another system', '只能在其他系統上執行'),
  not_attempted: () => L('pickfit didn’t get to it', 'pickfit 沒有測到這一項'),
  not_shown: () => L('What pickfit saw didn’t show it working', 'pickfit 看到的結果沒有顯示它可用'),
  operator_limit: () => L('pickfit couldn’t get through the app to it', 'pickfit 沒能在應用程式裡操作到這一步'),
  check_not_met: () => L('pickfit used it but didn’t see the result', 'pickfit 操作過，但沒有看到結果'),
  app_error: () => L('The app crashed or showed an error', '應用程式當掉或顯示錯誤'),
  needs_desktop: () => L('It needs a desktop part the test machine lacks', '需要測試機器沒有的桌面元件'),
  beyond_budget: () => L('pickfit didn’t test this one by one', '這一項 pickfit 沒有逐項測試'),
  test_failed_in_sandbox: () => L('Its test failed because of the test machine’s limits, not the tool', '測試沒通過，原因是測試機器的限制，不是工具本身'),
  test_failed: () => L('Its test failed with the tool’s own error; you may hit it too (not confirmed on a real machine)', '測試沒通過，是工具本身的錯誤，你也可能遇到（尚未在實體機器上確認）'),
  not_recorded: () => L('Not checked one by one', '沒有逐項檢查'),
  other: () => L('Not checked', '未檢查'),
};

/** A run note that only describes pickfit's own checker (its budget, its boxes, its record), in English or as translated. */
const CHECKER_NOTE = /install-only run|budget|first \d+ listed features|agent's box|too long for the record|僅安裝|僅執行安裝|預算|額度已用盡|agent 的(?:沙盒|環境)|過長/i;

/** features.ts writes "<reason>: <the run's note>". The note says what the run saw, so it is kept when there is one,
 * without the checker's own lead-in; otherwise, or when the note is only about the checker, the reason in plain words. */
const featureWhy = (n: { reason: NotCheckedReason; detail: string }) => {
  const at = n.detail.indexOf(': ');
  const note = (at > 0 ? n.detail.slice(at + 2) : '')
    .replace(/^its check passed, but the output does not show it:\s*/i, '')
    .replace(/^檢查通過，但輸出未顯示[：:]\s*/, '')
    .trim();
  if (!note || CHECKER_NOTE.test(note)) return WHY_NOT[n.reason]();
  // "Output shows only an error, not …" says what was seen; the mark's label (Not shown working) says why it does not count.
  return note.charAt(0).toUpperCase() + note.slice(1);
};

/** The mark beside a feature pickfit did not see work: failed, used but not shown working, or not tested. */
const featureState = (reason: NotCheckedReason) =>
  reason === 'test_failed'
    ? L('Test failed', '測試未通過')
    : reason === 'not_shown' || reason === 'check_not_met'
      ? L('Not shown working', '沒有看到它可用')
      : L('Not tested', '未測試');

/** Why the features come from the profile alone: a run that did not check them one by one, or no run at all. */
const notRecorded = (entry: Entry, ran: boolean) =>
  ran
    ? L('These come from the README; pickfit didn’t check them one by one.', '以下依據 README；pickfit 沒有逐項檢查。')
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


/** Under a feature whose check ran against a stand-in (a mail sink, a storage emulator, a tiny model, an HTTP mock). */
const STAND_IN_NOTE = () =>
  L('Checked against a stand-in: this shows it connects, not that it works with the real service.', '用替身驗的：只確認接得上，沒有對真的服務驗過。');
/** Under a ticked feature whose check went through a compatible endpoint with a real model behind it. */
const COMPATIBLE_NOTE = () => L('Checked through a compatible endpoint, not the service it names.', '用相容的端點驗的，不是它指定的那個服務。');

function featureList(entry: Entry, f: FeaturesOut): string {
  const guide = entry.usage_guide ?? null;
  const titles = new Map((guide?.features ?? []).map((g) => [g.feature, g]));
  const title = (feature: string) => esc(titles.get(feature)?.title ?? feature.charAt(0).toUpperCase() + feature.slice(1));
  const items = [
    ...f.checked.map(({ feature, fidelity }) => {
      const steps = titles.get(feature)?.steps ?? [];
      const clip = featureClip(entry, feature);
      const how =
        steps.length || clip
          ? `<details class="how-to"><summary>${L('How to use it', '怎麼使用')}</summary>${steps.length ? `<ol>${steps.map((s) => `<li>${stepText(s)}</li>`).join('')}</ol>` : ''}${clip}</details>`
          : '';
      // Checked against a stand-in: it connected, which is not the feature working, so no tick; a quiet plug and one line.
      if (fidelity === 'stand_in') {
        return (
          `<li class="feat-standin"><div><span class="feat-title">${title(feature)}</span><span class="feat-note">${STAND_IN_NOTE()}</span>${how}</div>` +
          `<span class="feat-state">${icon('plug')}${L('Stand-in only', '只用替身驗')}</span></li>`
        );
      }
      const note = fidelity === 'compatible' ? `<span class="feat-note">${COMPATIBLE_NOTE()}</span>` : '';
      return `<li class="feat-ok"><div><span class="feat-title">${title(feature)}</span>${note}${how}</div><span class="feat-state">${icon('check')}${L('Tested', '已測試')}</span></li>`;
    }),
    // The feature is the row; whether pickfit tested it is the mark on the right, and why not is only its tooltip.
    ...f.not_checked.map((n) => {
      const failed = n.reason === 'test_failed';
      const why = esc(featureWhy(n));
      return (
        `<li class="${failed ? 'feat-fail' : 'feat-open'}"><div><span class="feat-title">${title(n.feature)}</span></div>` +
        `<span class="feat-state" tabindex="0" data-tip="${why}">${icon(failed ? 'x' : 'circle-dashed')}${featureState(n.reason)}</span></li>`
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

/** What else the tool's own docs say it can do (capabilities): folded away and apart from the features, since pickfit
 * did not test these one by one. A list-like one (formats, services) shows its members after the label. */
function moreCapabilities(entry: Entry): string {
  const caps = entry.capabilities ?? [];
  if (!caps.length) return '';
  const rows = caps.map((c) => {
    const items = c.items?.length ? ` <span class="cap-items">${esc(listOf(c.items))}</span>` : '';
    return `<li><span class="cap-label">${esc(c.label.charAt(0).toUpperCase() + c.label.slice(1))}</span>${items}</li>`;
  });
  return (
    `<details class="more-caps"><summary>${L(`More it can do, from its docs (${caps.length})`, `文件寫的其他功能（${caps.length} 項）`)}</summary>` +
    `<p class="small quiet">${L('From the tool’s own documentation and help. pickfit didn’t test these one by one.', '依據工具自己的文件和說明，pickfit 沒有逐項測試。')}</p>` +
    `<ul class="cap-list">${rows.join('')}</ul></details>`
  );
}

/** What it does: the features, each ticked when a run checked it, then what else its docs say (folded). With no feature
 * list, what it is good for says what it does instead. */
function about(entry: Entry, f: FeaturesOut): string {
  const features = featureList(entry, f);
  const parts = [
    entry.why_worth_it ? `<p class="fit">${esc(entry.why_worth_it)}</p>` : '',
    features,
    features ? '' : goodFor(entry, false),
    moreCapabilities(entry),
  ].join('');
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

function install(catalog: Catalog, entry: Entry, reported = false): string {
  if (isWebApp(entry) && entry.web) return webRun(entry);
  const oses = OSES.filter((os) => entry.install[os]);
  if (!oses.length) {
    // A vulnerable tool keeps its warning (the target of the head badge and the shield) even with nothing else to say here.
    const needs = prerequisites(entry);
    const notice = securityNotice(entry);
    return needs || notice ? `<section class="block" aria-labelledby="install-title">${installTitle('Use it', '使用')}${notice}${needs}</section>` : '';
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
      runAge(g, entry, new Date(catalog.built_at)) +
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
  return `<section class="block" aria-labelledby="install-title">${installTitle('Use it', '使用')}${securityNotice(entry)}<div class="use-it">${tabs}${panels.join('')}</div>${reportForm(entry, oses, reported)}</section>`;
}

/** When pickfit ran these steps, as a day and how long ago (against the catalog's build, like the fact sheet), and a
 * warning when the project released after the check or the check is old (freshness.ts, D2). */
function runAge(g: InstallGuide, entry: Entry, now: Date): string {
  const f = freshness(g.run.checked_at, entry.last_release, now);
  if (f.age_days === null) return '';
  return (
    `<p class="run-age small quiet">${L('pickfit ran these steps on', 'pickfit 執行這些步驟的日期：')} ${esc(day(g.run.checked_at))} (${esc(age(g.run.checked_at, now) ?? '')})</p>` +
    (f.warning ? `<p class="run-stale small" role="note">${icon('triangle-alert')}${esc(f.warning)}</p>` : '')
  );
}

/**
 * "It didn't install for me" (F1): a report_outcome install_failed with the OS and, if the person gives it, the end of
 * the error. Without a rec_id it is stored for people to read and neither counts toward the score nor queues a re-run,
 * and the form says so. Posts without the page script too.
 */
function reportForm(entry: Entry, oses: OS[], reported: boolean): string {
  if (reported) {
    return `<div class="notice info report-done" role="status" id="report"><div><h3>${L('Thanks, it’s recorded', '謝謝，已經記下來了')}</h3><p>${L(
      'pickfit’s maintainers read these reports. One report doesn’t change the score or start a new check by itself.',
      'pickfit 的維護者會看這些回報。單一回報不會改變分數，也不會自動重新檢查。',
    )}</p></div></div>`;
  }
  const options = oses.map((os) => `<option value="${os}">${esc(OS_NAME[os])}</option>`).join('');
  return (
    `<details class="report" id="report"><summary class="small">${L('It didn’t install for me', '我裝不起來')}</summary>` +
    `<form method="post" action="/report" class="report-form">` +
    `<input type="hidden" name="slug" value="${esc(entry.slug)}">` +
    `<label>${L('Your system', '你的系統')} <select name="os">${options}</select></label>` +
    `<label>${L('The last lines of the error (optional; leave out names, paths and keys)', '錯誤訊息的最後幾行（選填；請拿掉名字、路徑和金鑰）')}` +
    `<textarea name="error" rows="4" maxlength="${ERROR_EXCERPT_MAX}"></textarea></label>` +
    `<p class="small quiet">${L('No account and no IP address is stored. A maintainer reads it; it doesn’t change the score by itself.', '不需要帳號，也不記錄 IP。維護者會看；單一回報不會改變分數。')}</p>` +
    `<button type="submit" class="btn btn-quiet btn-sm">${L('Send the report', '送出回報')}</button></form></details>`
  );
}

/** A web app: open it, and the facts a person weighs before typing anything in. */
function webRun(entry: Entry): string {
  const check = webCheck(entry);
  const url = entry.web!.url;
  const open = link(url, L('Open the site', '開啟網站'), 'btn btn-primary btn-sm');
  if (!check) {
    return (
      `<section class="block" aria-labelledby="install-title">${installTitle('Open it', '開啟')}${securityNotice(entry)}` +
      `<div class="empty"><div><p>` +
      L(
        `<b>pickfit hasn’t checked ${esc(entry.name)} in its browser yet</b>.`,
        `<b>pickfit 還沒在瀏覽器中檢查過 ${esc(entry.name)}</b>。`,
      ) +
      `</p><p class="quiet">${L('The profile above comes from its own site only.', '上方簡介只依據它自己的網站。')}</p></div></div></section>`
    );
  }
  return (
    `<section class="block" aria-labelledby="install-title">${installTitle('Open it', '開啟')}${securityNotice(entry)}` +
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

/**
 * The unedited recordings the clip was cut from, each named by the feature it shows, to download, with its sha256 (the
 * clip's own mp4 names them too): a clip cut since 11/19 has no last card for these, and its marks are explained here.
 */
function rawList(entry: Entry, video: RunVideo): string {
  const raw = video.raw
    .map((r, i) => {
      const shows = r.feature_index != null ? video.features[r.feature_index] : null;
      const name = shows ? (guideTitle(entry, shows) ?? shows.charAt(0).toUpperCase() + shows.slice(1)) : L(`Recording ${i + 1}`, `錄影 ${i + 1}`);
      return (
        `<li><a href="${esc(videoPath(entry.slug, r.file))}" download>${esc(name)}</a> <span class="quiet">${L(`(${Math.round(r.seconds)} s)`, `（${Math.round(r.seconds)} 秒）`)}</span>` +
        `<br><span class="quiet">sha256</span> <code class="hash">${esc(r.sha256)}</code></li>`
      );
    })
    .join('');
  const picked = video.captions?.length
    ? `<p class="small quiet">${L(
        'In the clip, sped-up parts are marked 2×, and where unchanged screen was cut out, the seconds removed are marked.',
        '影片中加速的部分標著 2×；剪掉畫面沒變化的片段時，會標出剪去的秒數。',
      )}</p>`
    : '';
  return raw ? `<p class="small">${L('The clip was cut from these unedited recordings:', '影片剪輯自以下原始錄影：')}</p><ul class="small raw-list">${raw}</ul>${picked}` : '';
}

/** Everything a skeptic wants and a user doesn't: where each run ran, who looked, the raw recordings, the sandbox-only differences. */
function tested(catalog: Catalog, entry: Entry): string {
  const parts: string[] = [];
  const recordLink = (url: string | null) => (url ? `<p>${link(url, L('Run record', '測試紀錄'))}</p>` : '');
  if (isWebApp(entry)) {
    const check = webCheck(entry);
    if (!check) return '';
    parts.push(levelLine(webLevelLabel(check), true) + `<p>${esc(webRunWords(entry, check))}</p>` + recordLink(safeUrl(check.evidence_url)));
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
        (r.gui ? `<p>${esc(guiSentence(r.gui, { entry, features: featuresOut(entry, g) }))}</p>` : '') +
        mcpLine +
        (r.video ? rawList(entry, r.video) : '') +
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
    `<p class="quiet">${L('Each run starts from a clean machine and follows the steps above.', '每次測試都從乾淨的機器開始，照上面的步驟執行。')} <a href="/how">${L('How pickfit verifies', 'pickfit 怎麼驗證')}</a></p>` +
    `${parts.join('')}</details>`
  );
}

/** The kind a profile sits under in Browse: web apps have their own shelf. */
const crumb = (entry: Entry) => {
  const kind = isWebApp(entry) ? 'web_app' : entry.category;
  return `<a href="/browse?kind=${esc(kind)}">${esc(KIND_PLURAL[kind] ?? KIND[kind] ?? '')}</a>`;
};

export function renderTool(catalog: Catalog, entry: Entry, nonce: string, opts: { reported?: boolean } = {}): string {
  const now = new Date(catalog.built_at);
  const guide = bestGuide(entry);
  const features = featuresOut(entry, guide);
  const verified = isVerified(entry);
  const web = isWebApp(entry) ? webCheck(entry) : null;
  const on = listOf(verifiedOn(entry).map((os) => OS_NAME[os]));
  const badges = [
    entry.standing === 'broken' ? `<a class="badge-link" href="#broken-title">${badge('fail', L('Not recommended', '不列入推薦'), { icon: 'triangle-alert' })}</a>` : '',
    web ? badge('info', L(NO_INSTALL_LABEL, '免安裝'), { icon: 'globe' }) : '',
    web
      ? badge('pass', L('Tested in a browser', '已在瀏覽器實測'), { icon: 'badge-check' })
      : verified && on
        ? badge('pass', L(`Tested on ${on}`, `已在 ${on} 上測試`), {
            icon: 'badge-check',
            marks: `<span aria-hidden="true">${L('Tested', '已測試')}</span>${verifiedOn(entry).map(osMark).join('')}`,
          })
        : badge('quiet', L('Not verified yet', '尚未驗證'), { icon: 'circle-dashed' }),
    securityOf(entry).status === 'vulnerable'
      ? `<a class="badge-link" href="#security">${
          securityOf(entry).level === 'conditional'
            ? badge('caution', L('Known vulnerabilities in some uses', '某些用法下有已知漏洞'), { icon: 'triangle-alert' })
            : badge('fail', L('Known vulnerabilities', '有已知漏洞'), { icon: 'triangle-alert' })
        }</a>`
      : '',
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
    `<div class="tool-facts"><p class="badges">${badges}</p><p class="tool-links">${links}${verified ? compareToggle(entry.slug, entry.name) : ''}</p></div>` +
    brokenBanner(entry) +
    `</div>` +
    `${fitz(faceFor(entry), 96, { eager: true })}</div></section>` +
    (wide ? `<div class="wrap tool-clip">${clip}</div>` : '') +
    `<div class="wrap layout tool-layout"><div class="tool-main">` +
    (wide ? '' : clip) +
    (ran ? '' : progress(entry)) +
    (clip ? about(entry, features) + install(catalog, entry, opts.reported) : install(catalog, entry, opts.reported) + about(entry, features)) +
    `<div class="tool-more">` +
    (ran ? progress(entry) : '') +
    (features.checked.length + features.not_checked.length ? goodFor(entry, true) : '') +
    tested(catalog, entry) +
    coverageSection(entry.coverage) +
    `</div></div><aside class="side" aria-label="${L('At a glance', '一覽')}">` +
    `<div class="panel"><h2>${L('At a glance', '一覽')}</h2>${factSheet(entry, now)}<div class="panel-measure">` +
    tape(L('Quality', '品質'), entry.scores?.quality ?? null, { pop: 'pop-quality' }) +
    confidenceRow(entry.scores?.confidence, entry.scores?.unmeasured, features) +
    tape(L('Popularity', '知名度'), entry.scores?.popularity ?? null, { pop: 'pop-popularity', tone: 'quiet' }) +
    coverage(features, { pop: 'pop-features' }) +
    checkMarks(entry) +
    `</div><p class="small quiet"><a href="/how#scores">${L('How scores work', '評分方式')}</a></p></div>` +
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
