/**
 * The home page and the results of one search. Pure functions over
 * find_software's and get_install_guide's own outputs (and, before a search,
 * the catalog itself), so the page shows what an agent gets. Every value that
 * comes from the data or the model goes through esc(); links must be http(s).
 *
 * Design (DESIGN.md): the fitting room. A pick is a fitting ticket: the claim
 * on top, then a seam of stitches, then the run record it rests on. A tool
 * pickfit has not verified gets no stitches, no badge, no steps and no link.
 */
import { bestGuide, isVerified, isWebApp, verifiedOn, verifiedOnUserSystem, webCheck, type Arch, type Catalog, type Entry, type InstallGuide, type OS } from './catalog.ts';
import type { FindOutput, PickOut } from './find.ts';
import { fitNote } from './fit.ts';
import { isZh, L, withLang } from './i18n.ts';
import { PIPE_TO_SHELL, type InstallOutput, type VerifiedInPickfit } from './install.ts';
import { compareTable } from './pages/compare.ts';
import { day, guiSentence, howRan, levelLabel, osName, PRICE, PROCESSING, passed, readerIssues, setupWords, SHORT_DAY, system, webLevelLabel } from './ui/facts.ts';
import { esc, link, listOf } from './ui/html.ts';
import { icon, osMark, type IconName } from './ui/icons.ts';
import { badge, command, compareToggle, coverage, fitz, kindTag, levelIcon, measure, notice, osList, runFacts, says, SEAM, sysTag, tape, type FitzName, type MeasureRow } from './ui/kit.ts';
import { renderShell } from './ui/shell.ts';
import { NO_INSTALL_LABEL, noInstallLabel, webFacts, webRanSentence } from './webapp.ts';

export { esc, safeUrl } from './ui/html.ts';
export { guiSentence, LEVEL_LABEL, levelLabel, osName } from './ui/facts.ts';

export interface FormValues {
  need: string;
  os: OS | '';
  arch: Arch | '';
  free_only: boolean;
  offline: boolean;
  /** What the person types must not leave their machine. */
  private: boolean;
}

export const EMPTY_FORM: FormValues = { need: '', os: '', arch: '', free_only: false, offline: false, private: false };

/** Why the web page did not ask the model: its daily share, the total cap, or no way to count spend. */
export type BudgetStop = 'web_daily' | 'total' | 'unavailable';

/** One search: find_software's output and get_install_guide's for each pick (by slug). */
export interface SearchResult {
  out: FindOutput;
  guides: Record<string, InstallOutput>;
}

export interface CatalogStats {
  listed: number;
  verified: number;
  replayed: number;
  byHand: number;
  gems: number;
  /** Web apps a sandboxed browser run passed on (they have no install steps to replay). */
  web: number;
}

const runsOf = (entry: Entry) => Object.values(entry.install).map((guide) => guide!.run);

export function catalogStats(catalog: Catalog): CatalogStats {
  return {
    listed: catalog.count,
    verified: catalog.entries.filter(isVerified).length,
    replayed: catalog.entries.filter((e) => runsOf(e).some((r) => r.method === 'sandbox' && r.replayed)).length,
    byHand: catalog.entries.filter((e) => runsOf(e).some((r) => r.method === 'human')).length,
    gems: catalog.entries.filter((e) => e.scores?.treasure).length,
    web: catalog.entries.filter((e) => isWebApp(e) && webCheck(e) !== null).length,
  };
}

/** What the page shows before any search, all read from the catalog: no model call, nothing invented. */
export interface Showcase {
  stats: CatalogStats;
  /** The newest hidden gem whose run found something the README got wrong (else the newest run). */
  featured: { entry: Entry; guide: InstallGuide } | null;
  /** Another hidden gem whose README the run corrected, for the runs section. */
  fix: { entry: Entry; guide: InstallGuide } | null;
  /** The newest runs, one per tool. */
  recent: { entry: Entry; guide: InstallGuide }[];
}

export function catalogShowcase(catalog: Catalog, recentCount = 3): Showcase {
  const runs = catalog.entries
    .flatMap((entry) => {
      const guide = bestGuide(entry);
      return guide ? [{ entry, guide }] : [];
    })
    .sort((a, b) => b.guide.run.checked_at.localeCompare(a.guide.run.checked_at) || a.entry.slug.localeCompare(b.entry.slug));
  const corrected = runs.filter((r) => r.entry.scores?.treasure && readerIssues(r.guide.pitfalls).length > 0 && r.guide.steps.length > 0);
  const featured = corrected[0] ?? runs[0] ?? null;
  const fix = corrected.find((r) => r !== featured) ?? null;
  return { stats: catalogStats(catalog), featured, fix, recent: runs.slice(0, recentCount) };
}

// ---------------------------------------------------------------- the run record in words

/** "pickfit installed it in a fresh Linux x86_64 sandbox and replayed the steps from scratch on 29 Oct 2026." */
export function ranSentence(v: PickOut['verification']): string {
  if (!v.os) return L('pickfit has no recorded run of its install steps.', 'pickfit 還沒有這款工具的安裝測試紀錄。');
  const when = v.checked_at ? ` on ${day(v.checked_at)}` : '';
  // Chinese puts the date before the place.
  const whenZh = v.checked_at ? `於 ${day(v.checked_at)} ` : '';
  const where = system(v.os, v.arch);
  if (v.method === 'human') return L(`pickfit installed it by hand on ${where}${when}.`, `pickfit ${whenZh}在 ${where} 上手動安裝了它。`);
  return v.replayed
    ? L(
        `pickfit installed it in a fresh ${where} sandbox and replayed the steps from scratch${when}.`,
        `pickfit ${whenZh}在全新的 ${where} 沙盒裡裝好它，再從頭重跑一次步驟。`,
      )
    : L(`pickfit installed it in a ${where} sandbox${when}.`, `pickfit ${whenZh}在 ${where} 沙盒裡裝好了它。`);
}

/** The "your system" line: verified_on_user_os in words, including when it is not true. */
export function yourSystem(v: PickOut['verification'], form: FormValues): { state: 'yes' | 'no' | 'unknown'; text: string } {
  if (v.verified_on_user_os === true) {
    return {
      state: 'yes',
      text: form.arch
        ? L(`Verified on your system: it ran on ${system(v.os, v.arch)}.`, `已在你的系統上驗證：在 ${system(v.os, v.arch)} 上執行過。`)
        : L(`Verified on your OS: it ran on ${system(v.os, v.arch)}.`, `已在你的作業系統上驗證：在 ${system(v.os, v.arch)} 上執行過。`),
    };
  }
  if (v.verified_on_user_os === false) {
    return {
      state: 'no',
      text:
        v.os === form.os && form.arch
          ? L(
              `Not verified on your system: it ran on ${system(v.os, v.arch)}, not ${form.arch}.`,
              `你的系統尚未驗證：測試是在 ${system(v.os, v.arch)} 上跑的，不是 ${form.arch}。`,
            )
          : L(
              `Not verified on your system: it ran on ${system(v.os, v.arch)}, and pickfit hasn’t run it on ${osName(form.os || null)} yet.`,
              `你的系統尚未驗證：測試是在 ${system(v.os, v.arch)} 上跑的，pickfit 還沒在 ${osName(form.os || null)} 上試過。`,
            ),
    };
  }
  return {
    state: 'unknown',
    text: L('Choose your OS above to see whether it ran on your system.', '在上方選好作業系統，就能看它有沒有在你的系統上跑過。'),
  };
}

const CHECK = '<svg class="check" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.2 8.6l3 3 6.6-7.2"/></svg>';
/** The level a run reached: its own mark when it passed (else the check), a warning when it did not. */
export const levelLine = (label: string, ok: boolean, mark?: IconName) =>
  `<p class="level${ok ? '' : ' level-caution'}">${ok ? (mark ? `<span class="level-i">${icon(mark)}</span>` : CHECK) : icon('triangle-alert')}${esc(label)}</p>`;

function facts(pick: PickOut): string {
  const items: string[] = [];
  const item = (mark: string, text: string) => `<li class="rf">${mark}${text}</li>`;
  if (pick.open_source === true)
    items.push(
      item(
        icon('scroll-text'),
        pick.license ? L(`Open source (${esc(pick.license)})`, `開源（${esc(pick.license)}）`) : L('Open source', '開源'),
      ),
    );
  if (pick.open_source === false) items.push(item(icon('scroll-text'), L('Not open source', '非開源')));
  // A web app's own facts (where data goes, which OS) are in its test record.
  const where = pick.web_app ? '' : PROCESSING[pick.processing];
  if (where) items.push(item(icon('laptop'), esc(where)));
  if (pick.web_app) items.push(item(icon('globe'), L('In any modern browser', '任何現代瀏覽器都能用')));
  else if (pick.platforms.length) {
    const names = listOf(pick.platforms.map((os) => osName(os)));
    items.push(`<li class="rf">${osList(pick.platforms, { tone: 'quiet', say: L(`Claims to run on ${names}`, `宣稱支援 ${names}`) })}</li>`);
  }
  return items.length ? `<ul class="run-facts">${items.join('')}</ul>` : '';
}

/** When the steps ran on another system than the one the person chose: said in words, before the steps. */
function systemCaution(guide: InstallOutput, form: FormValues): string {
  const v = guide.verification;
  const match = guide.applies_to_user_system.match;
  if (match === 'other_os' && form.os) {
    return `<p class="caution">${L(
      `These steps ran on ${esc(system(v.os, v.arch))}. pickfit hasn’t run them on ${esc(osName(form.os))}, so expect differences.`,
      `這些步驟是在 ${esc(system(v.os, v.arch))} 上跑的；pickfit 還沒在 ${esc(osName(form.os))} 上試過，結果可能不同。`,
    )}</p>`;
  }
  if (match === 'same_os_other_arch' && form.arch) {
    return `<p class="caution">${L(
      `These steps ran on ${esc(system(v.os, v.arch))}, not ${esc(form.arch)}. A download may need the other build.`,
      `這些步驟是在 ${esc(system(v.os, v.arch))} 上跑的，不是 ${esc(form.arch)}；下載時可能要換另一個版本。`,
    )}</p>`;
  }
  return '';
}

/** The first pick shows every step of the run that worked above its fold when there are this many or fewer. */
const STEPS_SHOWN = 3;

/** The steps get_install_guide returns, for a person instead of an agent. `inRun`: inside a run card that already names the system, so no fold of its own. */
export function installSection(guide: InstallOutput, form: FormValues, open: boolean, inRun = false, stepper: { hint: string | null; needs?: string } | null = null): string {
  const v = guide.verification;
  if (guide.steps.length === 0) return '';
  const caution = systemCaution(guide, form);
  const cautions: string[] = caution ? [caution] : [];
  const steps = guide.steps.map((step) => {
    const notes: string[] = [];
    if (step.needs_sudo) notes.push(L('Uses sudo.', '需要 sudo。'));
    if (PIPE_TO_SHELL.test(step.command)) notes.push(L('Runs a downloaded script: read it before you run it.', '會執行下載來的腳本，執行前請先看過內容。'));
    return (
      `<li>${step.purpose ? `<p>${esc(step.purpose)}</p>` : ''}${command(step.command)}` +
      `${notes.length ? `<p class="caution small">${notes.join(' ')}</p>` : ''}</li>`
    );
  });
  const stepList = `<ol class="steps">${steps.join('')}</ol>`;
  const manual = guide.manual_steps.length
    ? `<h4>${L('You do these yourself', '需要你手動做的')}</h4><ul><li>${guide.manual_steps.map((s) => esc(s.title)).join('</li><li>')}</li></ul>`
    : '';
  const verify = guide.verify
    ? `<h4>${L('Check that it works', '確認能用')}</h4>${command(guide.verify.command)}` +
      `<p class="quiet small">${L(
        `The output should contain “${esc(guide.verify.expected_contains)}”.`,
        `輸出應包含「${esc(guide.verify.expected_contains)}」。`,
      )}</p>`
    : '';
  const first = guide.first_task
    ? `<h4>${L('First thing to try', '先試試這個')}</h4>${guide.first_task_setup.map((s) => command(s.command)).join('')}${command(guide.first_task)}`
    : '';
  const cfg = guide.mcp_client_config;
  let agent = '';
  if (cfg) {
    const env = cfg.env.length
      ? `<h4>${L('You fill in', '你要填的')}</h4><ul>${cfg.env
          .map(
            (e) =>
              `<li><code translate="no">${esc(e.name)}</code>${e.purpose ? L(`: ${esc(e.purpose)}`, `：${esc(e.purpose)}`) : ''}${e.required ? L(' (required)', '（必填）') : ''}</li>`,
          )
          .join('')}</ul>`
      : '';
    agent =
      `<h4>${L('Add it to your agent', '加進你的 agent')}</h4>${command(cfg.claude_code)}` +
      `<details class="json"><summary class="small">${L('JSON for Claude Desktop, Cursor and other clients', 'Claude Desktop、Cursor 等用戶端用的 JSON')}</summary>${command(cfg.json)}</details>` +
      env +
      (cfg.note ? `<p class="quiet small">${esc(cfg.note)}</p>` : '');
  }
  const issueList = readerIssues(guide.known_issues);
  const issues = issueList.length
    ? // Folded: the steps above already work as written; the differences are for the curious.
      `<details class="issues-fold"><summary>${L('Where the README and reality differ', 'README 與實測不符之處')}</summary><ul class="issues">${issueList
        .map(
          (i) =>
            `<li><span class="quiet">${L('README:', 'README 寫：')}</span> ${esc(i.readme_said)}<br><span class="quiet">${L('What worked:', '實際可行：')}</span> ${esc(i.actually_needed)}</li>`,
        )
        .join('')}</ul></details>`
    : '';
  const ran = guide.verified_in_pickfit;
  if (ran) cautions.push(...sandboxNotes(ran));
  const asRun = ran ? verifiedFold(ran) : '';
  const sysSpan = `<span class="sys">${v.os ? osMark(v.os) : ''}${esc(system(v.os, v.arch))}</span>`;
  const body = stepper
    ? installStages([
        { name: L('Install', '安裝'), html: (stepper?.needs ?? '') + cautions.join('') + stepList + manual + issues + asRun },
        { name: L('Check it works', '確認能用'), html: verify, cls: 'inst-check' },
        { name: L('Start using it', '開始使用'), html: first + agent + (stepper.hint ? `<p class="open-hint">${icon('arrow-right')}<span>${stepText(stepper.hint)}</span></p>` : '') },
      ])
    : `<div class="install-body">${[...cautions, stepList, manual, verify, first, agent, issues, asRun].join('')}</div>`;
  // Inside a run card the steps sit straight in the card: a fold inside it would be a box inside a box.
  if (inRun) return body;
  return (
    `<details class="install"${open ? ' open' : ''}><summary><span>${L(`Install steps that worked on ${sysSpan}`, `在 ${sysSpan} 上可行的安裝步驟`)}</span>${icon('chevron-down')}</summary>` +
    `${body}</details>`
  );
}

/** What a reader must act on when the run's commands named pickfit's sandbox: a path $HOME could not replace, a folder to make.
 *  (That the sandbox's home became $HOME goes unsaid; the fold below keeps the commands exactly as run.) */
function sandboxNotes(ran: VerifiedInPickfit): string[] {
  const home = `<code translate="no">${esc(ran.sandbox_home)}</code>`;
  const notes: string[] = [];
  if (ran.not_portable.length) {
    notes.push(
      `<p class="caution small">${L(
        `${esc(ran.not_portable.join(', '))} still names ${home} inside single quotes, where <code translate="no">$HOME</code> would not work: put your own home folder there before running it.`,
        `${esc(ran.not_portable.join('、'))} 的單引號裡還寫著 ${home}（那裡 <code translate="no">$HOME</code> 不會展開）：執行前請換成你自己的家目錄。`,
      )}</p>`,
    );
  }
  if (ran.needs_workdir) {
    notes.push(
      `<p class="caution small">${L(
        'These steps ran from a folder named <code translate="no">work</code> in the home folder, which already existed. Make it and run them from there:',
        '這些步驟是在家目錄裡一個已經存在的 <code translate="no">work</code> 資料夾裡跑的。請先建立它，再從那裡執行：',
      )}</p>${command('mkdir -p "$HOME/work" && cd "$HOME/work"')}`,
    );
  }
  return notes;
}

/** The commands exactly as pickfit's run executed them, folded away under the ones a reader runs. */
function verifiedFold(ran: VerifiedInPickfit): string {
  const list = (cmds: string[]) => cmds.map((c) => `<pre class="quiet small"><code translate="no">${esc(c)}</code></pre>`).join('');
  const first = [...ran.first_task_setup.map((s) => s.command), ...(ran.first_task ? [ran.first_task] : [])];
  return (
    `<details class="as-run"><summary class="small">${L('Verified in pickfit: the commands exactly as its sandbox ran them', '在 pickfit 驗證過的原始指令（沙盒裡實際執行的）')}</summary>` +
    `<p class="quiet small">${L(`For the record only: they name the sandbox's home, ${esc(ran.sandbox_home)}.`, `僅供查核：裡面是沙盒的家目錄 ${esc(ran.sandbox_home)}。`)}</p>` +
    list(ran.steps.map((s) => s.command)) +
    (ran.verify ? list([ran.verify.command]) : '') +
    (first.length ? list(first) : '') +
    `</details>`
  );
}

/** `code` spans in generated text; everything else escaped. */
export const stepText = (s: string) => esc(s).replace(/`([^`]+)`/g, '<code translate="no">$1</code>');

/**
 * The guide one stage at a time (install, check, use), with Back and Next naming the stage they go to.
 * Without the page script every stage shows, one under the other.
 */
function installStages(all: { name: string; html: string; cls?: string }[]): string {
  const stages = all.filter((s) => s.html);
  if (stages.length < 2) return `<div class="install-body">${stages.map((s) => s.html).join('')}</div>`;
  const tabs =
    `<ol class="stage-tabs js-only">` +
    stages.map((s, i) => `<li><button type="button" data-goto="${i}" aria-label="${esc(s.name)}"${i ? '' : ' aria-current="step"'}><span class="n">${i + 1}</span><span class="lbl">${esc(s.name)}</span></button></li>`).join('') +
    `</ol>`;
  const panels = stages.map((s, i) => {
    const back = i ? `<button type="button" class="btn btn-quiet btn-sm" data-goto="${i - 1}">${icon('arrow-left')}${L(`Back: ${esc(stages[i - 1].name)}`, `上一步：${esc(stages[i - 1].name)}`)}</button>` : '';
    const next = i + 1 < stages.length ? `<button type="button" class="btn btn-primary btn-sm stage-next" data-goto="${i + 1}">${L(`Next: ${esc(stages[i + 1].name)}`, `下一步：${esc(stages[i + 1].name)}`)}${icon('arrow-right')}</button>` : '';
    return `<section class="inst-stage${s.cls ? ` ${s.cls}` : ''}" data-stage aria-label="${esc(s.name)}">${s.html}<div class="stage-nav js-only">${back}${next}</div></section>`;
  });
  return `<div class="install-body" data-stepper>${tabs}${panels.join('')}</div>`;
}

/** The run record: the evidence half of a pick, under the seam. Each fact once, as a mark; only a mismatch with the reader's OS is said in words. */
function record(pick: PickOut, guide: InstallOutput | undefined, form: FormValues): string {
  const v = pick.verification;
  const mine = yourSystem(v, form);
  const mcp = guide?.mcp_client_config ?? null;
  const shown = (tools: string[]) => tools.slice(0, 6).join(', ') + (tools.length > 6 ? ', …' : '');
  const mcpLine = mcp
    ? L(
        `An MCP client handshake over ${mcp.transport === 'stdio' ? 'stdio' : 'HTTP'} listed its ${mcp.tool_count} tool${mcp.tool_count === 1 ? '' : 's'}`,
        `MCP 用戶端透過 ${mcp.transport === 'stdio' ? 'stdio' : 'HTTP'} 連線，列出它的 ${mcp.tool_count} 個工具`,
      ) +
      (mcp.tools.length ? L(` (${shown(mcp.tools)})`, `（${shown(mcp.tools)}）`) : '') +
      (mcp.called_tool ? L(`, and a call to ${mcp.called_tool} returned a result`, `，呼叫 ${mcp.called_tool} 也回傳了結果`) : '') +
      L('.', '。')
    : '';
  // A GUI app's launch sentence already says whether the launch passed offline.
  const offline = v.gui ? null : guide?.verification.works_offline;
  return (
    `<section class="record" aria-label="${L('Test record', '測試紀錄')}">` +
    `<p class="record-title">${icon('badge-check')}${L('Test record', '測試紀錄')}</p>` +
    levelLine(levelLabel(v.level, { gui: v.gui, mcp }), passed(v.gui), levelIcon(v.level, { gui: v.gui, mcp })) +
    (v.os ? runFacts(v, { offline, mine: v.verified_on_user_os, askedOffline: form.offline && !v.gui }) : `<p>${esc(ranSentence(v))}</p>`) +
    (mcpLine ? `<p>${esc(mcpLine)}</p>` : '') +
    (v.gui ? `<p>${esc(guiSentence(v.gui))}</p>` : '') +
    (mine.state === 'no' ? `<p class="mine mine-no">${esc(mine.text)}</p>` : mine.state === 'unknown' ? `<p class="small quiet">${esc(mine.text)}</p>` : '') +
    `<details class="how"><summary>${L('How we know', '我們怎麼知道的')}</summary><p>${esc(pick.how_we_know)}</p></details>` +
    `</section>`
  );
}

const MATCH_LABEL = {
  get good() {
    return L('Good match', '高度符合');
  },
  get partial() {
    return L('Partial match', '部分符合');
  },
  get weak() {
    return L('Weak match', '勉強符合');
  },
};
const MATCH_TONE = { good: 'pass', partial: 'caution', weak: 'caution' } as const;

/** Rules only: which of the request's words the profile mentions, and which it does not. */
function matchCoverage(match: NonNullable<PickOut['match']>): string {
  const list = (words: string[]) => words.slice(0, 6).map((w) => `“${esc(w)}”`).join(', ');
  const parts = [
    match.covers.length ? L(`Its profile mentions ${list(match.covers)}.`, `它的簡介提到了 ${list(match.covers)}。`) : '',
    match.missing.length ? L(`It does not mention ${list(match.missing)}.`, `它沒有提到 ${list(match.missing)}。`) : '',
  ].filter(Boolean);
  return parts.length ? `<p class="coverage">${parts.join(' ')}</p>` : '';
}

/** find.ts adds this tradeoff for agents when the run was on another system; the test record says it in full. */
const RAN_ELSEWHERE = /^Verified on \S+(?: \S+)? only; pickfit has not run its /;

/** The rows every pick's sheet ends with: how far the run got is said by the caller; the price is a field. */
const priceRow = (pick: PickOut): MeasureRow => ({
  label: L('Price', '價格'),
  value: esc(PRICE[pick.pricing]),
  tone: pick.pricing === 'unknown' ? 'quiet' : undefined,
});
/** Offline, when a run checked it; the label says offline, so the value says only whether it worked. */
const offlineRow = (works: boolean): MeasureRow => ({
  label: L('Offline', '離線'),
  value: works ? L('Works', '可用') : L('Needed the network', '需要網路'),
  tone: works ? 'pass' : 'caution',
});

/**
 * The verdict as a measurement sheet (measure()): the facts people decide on first, one row each, each from a field
 * or the run. The first pick shows it as a sheet beside its fit sentence; "Also fits" shows the same values on one
 * line, without the setup row (their steps are in the fold and on the tool page).
 */
function verdictSheet(pick: PickOut, guide: InstallOutput | undefined, form: FormValues, first: boolean): string {
  const v = pick.verification;
  const where = esc(system(v.os, v.arch));
  const mark = v.os ? osMark(v.os) : '';
  const yours = L('Your system', '你的系統');
  const rows: MeasureRow[] = [
    v.verified_on_user_os === true
      ? { label: yours, value: mark + L(`Ran on ${where}`, `在 ${where} 上執行過`), tone: 'pass' }
      : v.verified_on_user_os === false
        ? { label: yours, value: mark + L(`Ran on ${where} only`, `只在 ${where} 上執行過`), tone: 'caution' }
        : { label: L('Ran on', '測試環境'), value: v.os ? mark + where : L('No run', '尚未測試') },
  ];
  const evidence = { gui: v.gui, mcp: guide?.mcp_client_config ?? null };
  rows.push({ label: L('How far the run got', '測試進行到哪一步'), value: esc(levelLabel(v.level, evidence)), tone: passed(v.gui) ? 'pass' : 'caution' });
  // Offline when the run checked it; a failed check only when the person asked for offline.
  const off = guide?.verification.works_offline;
  if (off === true || (off === false && form.offline)) rows.push(offlineRow(off));
  if (first && guide && guide.steps.length)
    rows.push({ label: L('Setup steps', '安裝步驟'), value: esc(setupWords(guide.steps.length, guide.manual_steps.length)) });
  rows.push(priceRow(pick));
  return measure(rows, { cls: 't-sheet' });
}

/** The evidence no one else has, in one plain line: what the README got wrong and what worked, verbatim. */
function readmeFix(guide: InstallOutput): string {
  const issues = readerIssues(guide.known_issues);
  const fix = issues.find((i) => i.kind === 'readme_wrong') ?? issues[0];
  return fix ? `<p class="t-fix"><b>${L('README fix:', 'README 修正：')}</b> ${esc(fix.actually_needed)}</p>` : '';
}

/**
 * The one action on a ticket. The first pick shows every command of the run that worked (up to three) in one
 * block with one Copy, named by the system it ran on; the others show the first command of it.
 * Steps that ran on another OS than the one chosen say so before the command, and their Copy is not the
 * screen's one solid yellow (t-elsewhere). Steps with sudo get a Copy each: pasted together into a shell
 * without bracketed paste, sudo's password prompt would swallow the lines after it.
 */
function quickInstall(guide: InstallOutput | undefined, form: FormValues, index: number): string {
  const first = guide?.steps[0];
  if (!guide || !first) return '';
  const v = guide.verification;
  const elsewhere = guide.applies_to_user_system.match === 'other_os' && !!form.os;
  const cls = `t-install${elsewhere ? ' t-elsewhere' : ''}`;
  if (index === 0 && guide.steps.length <= STEPS_SHOWN) {
    const n = guide.steps.length;
    const where = esc(system(v.os, v.arch));
    const byHand = guide.manual_steps.length;
    const sudo = guide.steps.some((s) => s.needs_sudo);
    const apart = sudo && n > 1;
    // The same cautions the full steps carry, said once under the block.
    const notes: string[] = [];
    if (sudo) notes.push(apart ? L('Uses sudo, so run the steps one at a time.', '需要 sudo，請一次執行一個步驟。') : L('Uses sudo.', '需要 sudo。'));
    if (guide.steps.some((s) => PIPE_TO_SHELL.test(s.command)))
      notes.push(L('Runs a downloaded script: read it before you run it.', '會執行下載來的腳本，執行前請先看過內容。'));
    return (
      `<div class="${cls}"><p class="t-install-label">${icon('terminal')}<b>${L('Install', '安裝')}</b><span class="quiet">${
        n === 1 ? L(`1 step, as pickfit ran it on ${where}`, `pickfit 在 ${where} 上跑的 1 個步驟`) : L(`${n} steps, as pickfit ran them on ${where}`, `pickfit 在 ${where} 上跑的 ${n} 個步驟`)
      }${byHand ? L(`, plus ${byHand} by hand`, `，另有 ${byHand} 個手動步驟`) : ''}</span></p>` +
      systemCaution(guide, form) +
      (apart ? guide.steps.map((s) => command(s.command)).join('') : command(guide.steps.map((s) => s.command).join('\n'))) +
      (notes.length ? `<p class="caution small">${notes.join(' ')}</p>` : '') +
      readmeFix(guide) +
      `</div>`
    );
  }
  const more = guide.steps.length - 1 + guide.manual_steps.length;
  const total = guide.steps.length + guide.manual_steps.length;
  return (
    `<div class="${cls}"><p class="t-install-label">${icon('terminal')}${L('Install', '安裝')}${
      elsewhere ? L(`, as it ran on ${esc(system(v.os, v.arch))}`, `（${esc(system(v.os, v.arch))} 上的步驟）`) : ''
    }` +
    `${more ? `<span class="quiet">${L(` · step 1 of ${total}`, ` · 第 1 步，共 ${total} 步`)}</span>` : ''}</p>${command(first.command)}` +
    readmeFix(guide) +
    `</div>`
  );
}

// ---------------------------------------------------------------- a web app's ticket

/** A web app's facts as a short list, each with its tone; the same words on the ticket and the profile. */
export function webFactList(entry: Entry, cls = ''): string {
  const check = webCheck(entry);
  if (!check) return '';
  const tone = { pass: 'yes', caution: 'no', plain: '' } as const;
  return `<ul class="web-facts${cls ? ` ${cls}` : ''}">${webFacts(check)
    .map((f) => `<li${tone[f.tone] ? ` class="${tone[f.tone]}"` : ''}>${f.tone === 'pass' ? icon('check') : f.tone === 'caution' ? icon('triangle-alert') : icon('info')}${esc(f.text)}</li>`)
    .join('')}</ul>`;
}

/** The run record of a web app: what pickfit's browser saw, under the seam. */
function webRecord(pick: PickOut, entry: Entry | undefined): string {
  const check = entry ? webCheck(entry) : null;
  if (!check || !entry) return '';
  return (
    `<section class="record" aria-label="${L('Test record', '測試紀錄')}">` +
    `<p class="record-title">${icon('badge-check')}${L('Test record', '測試紀錄')}</p>` +
    levelLine(webLevelLabel(check), true) +
    `<p>${esc(webRanSentence(check))}</p>` +
    webFactList(entry) +
    `<p class="mine mine-yes">${esc(L('Nothing to install: it opens in a browser on any OS.', '免安裝：任何系統的瀏覽器都能打開。'))}</p>` +
    `<details class="how"><summary>${L('How we know', '我們怎麼知道的')}</summary><p>${esc(pick.how_we_know)}</p></details>` +
    `</section>`
  );
}

/** A web app's verdict sheet: where it runs, how far the browser run got, offline when checked, the setup (none) and the price. */
function webSheet(pick: PickOut, entry: Entry | undefined, first: boolean): string {
  const check = entry ? webCheck(entry) : null;
  const web = pick.web_app!;
  const rows: MeasureRow[] = [
    { label: L('Runs in', '執行環境'), value: L('Any browser', '任何瀏覽器'), tone: 'pass' },
    { label: L('How far the run got', '測試進行到哪一步'), value: check ? esc(webLevelLabel(check)) : L('No run', '尚未測試'), tone: check ? 'pass' : 'caution' },
  ];
  if (web.works_offline === 'verified') rows.push(offlineRow(true));
  if (first) rows.push({ label: L('Setup steps', '安裝步驟'), value: L('Nothing to install', '免安裝') });
  rows.push(priceRow(pick));
  return measure(rows, { cls: 't-sheet' });
}

/** The one action on a web app's ticket: open it. */
function webOpen(pick: PickOut): string {
  const web = pick.web_app!;
  const open = link(web.url, `${icon('external-link')}${L('Open the site', '開啟網站')}`, 'btn btn-primary btn-sm');
  return open
    ? `<div class="t-install"><p class="t-install-label">${icon('globe')}${esc(noInstallLabel())}</p><p class="t-open">${open}<span class="quiet small" translate="no">${esc(web.url)}</span></p></div>`
    : '';
}

function pickHtml(pick: PickOut, index: number, result: SearchResult, form: FormValues, catalog: Catalog, instead = ''): string {
  const { out } = result;
  const entry = catalog.bySlug.get(pick.slug);
  const best = out.best_free?.slug === pick.slug ? out.best_free : null;
  const web = pick.web_app;
  const badges = [
    web ? badge('info', L(NO_INSTALL_LABEL, '免安裝'), { icon: 'globe' }) : '',
    pick.match ? badge(MATCH_TONE[pick.match.quality], MATCH_LABEL[pick.match.quality], { cls: `match-${pick.match.quality}` }) : '',
    best ? badge('free', L('Best free option', '最佳免費選擇'), { icon: 'leaf' }) : '',
    pick.scores.treasure ? badge('gem', L('Hidden gem', '寶藏'), { icon: 'gem', pop: 'pop-gem' }) : '',
  ].join('');
  // Each reason leads with the mark of the fact it rests on; the cited profile field opens from the claim.
  const why = pick.why
    .map(
      (r) =>
        `<li><details class="why-src"><summary>${esc(r.claim)}${icon('file-text')}</summary>` +
        `<p class="cite">${L(
          `From its profile: <code>${esc(r.field)}</code> is “${esc(r.value)}”`,
          `依據簡介：<code>${esc(r.field)}</code> 是「${esc(r.value)}」`,
        )}</p></details></li>`,
    )
    .join('');
  // Tradeoffs come from find_software in English, so the note they may repeat is compared in English.
  const fitSaid = pick.match ? withLang('en', () => fitNote(pick.match!)) : null;
  const tradeoffs = pick.tradeoffs
    .filter((t) => !RAN_ELSEWHERE.test(t) && t !== fitSaid)
    .map((t) => `<li>${esc(t)}</li>`)
    .join('');
  const guide = result.guides[pick.slug];
  const kind = entry ? kindTag(entry) : '';
  const links = [
    web ? link(web.url, `${icon('external-link')}${L('Open it', '開啟')}`) : '',
    link(pick.repo, `${icon('external-link')}${L('Source code', '原始碼')}`),
    pick.homepage && pick.homepage !== pick.repo && pick.homepage !== web?.url
      ? link(pick.homepage, `${icon('external-link')}${L('Homepage', '首頁')}`)
      : '',
    link(pick.verification.os || web?.checked_at ? pick.evidence_url : null, `${icon('external-link')}${L('Run record', '測試紀錄')}`),
  ].filter(Boolean);
  const gemNote = pick.scores.treasure ? L('little known', '鮮為人知') : undefined;
  // At a glance: who it is, why it fits in one sentence, the verdict, and the command. The rest waits behind one expander.
  return (
    `<article class="pick" id="pick-${esc(pick.slug)}" aria-labelledby="name-${esc(pick.slug)}">` +
    `<div class="t-top"><div>` +
    `<h3 class="t-name" id="name-${esc(pick.slug)}"><a href="/tool/${esc(pick.slug)}">${esc(pick.name)}</a></h3>` +
    (kind ? `<p class="t-kind">${kind}</p>` : '') +
    `</div>` +
    (badges ? `<p class="badges">${badges}</p>` : '') +
    `</div>` +
    `<p class="fit">${esc(pick.fit)}</p>` +
    (web ? webSheet(pick, entry, index === 0) : verdictSheet(pick, guide, form, index === 0)) +
    instead +
    SEAM +
    (web ? webOpen(pick) : quickInstall(guide, form, index)) +
    `<details class="t-more"><summary>${icon('chevron-down')}${L('Why it fits and how we know', '為什麼適合、我們怎麼知道')}</summary><div class="t-more-body">` +
    `<div class="t-body"><div class="t-claim">` +
    // On the rules path the fit sentence is the summary: say it once.
    (pick.fit === pick.summary ? '' : `<p class="summary">${esc(pick.summary)}</p>`) +
    (pick.match ? matchCoverage(pick.match) : '') +
    (why ? `<h4>${L('Why it fits', '為什麼適合')}</h4><ul class="why why-marks">${why}</ul>` : '') +
    (tradeoffs ? `<h4>${L('Tradeoffs', '取捨')}</h4><ul class="tradeoffs">${tradeoffs}</ul>` : '') +
    (pick.vs_well_known
      ? `<p class="vs"><span class="lead-in">${L('Compared with better-known tools:', '和知名工具相比：')}</span> ${esc(pick.vs_well_known)}</p>`
      : '') +
    facts(pick) +
    `</div><div class="t-measure">` +
    tape(L('Quality', '品質'), pick.scores.quality, { pop: 'pop-quality' }) +
    tape(L('Popularity', '知名度'), pick.scores.popularity, { pop: 'pop-popularity', tone: 'quiet', note: gemNote }) +
    coverage(pick.features, { pop: 'pop-features' }) +
    `</div></div>` +
    (web ? webRecord(pick, entry) : record(pick, guide, form)) +
    // Open for the first pick only when the steps above it are not all of them; otherwise it would repeat them.
    (guide && !web ? installSection(guide, form, index === 0 && guide.steps.length > STEPS_SHOWN) : '') +
    (links.length ? `<p class="t-links">${links.join('')}</p>` : '') +
    `</div></details>` +
    `<div class="t-foot"><a class="more" href="/tool/${esc(pick.slug)}">${L('Full profile', '完整介紹')}${icon('arrow-right')}</a><span class="grow"></span>${compareToggle(pick.slug, pick.name)}</div>` +
    `</article>`
  );
}

const BY_RULES = () =>
  L(
    'these results are ranked by rules (the words in your request, then no-install web apps among close fits, then verification on your OS, then the hidden-gem score) without Muse Spark',
    '這次改用規則排序、沒有用 Muse Spark（依序看需求裡的字詞、相近結果中免安裝的網頁應用、是否在你的作業系統上驗證過、寶藏分數）',
  );
const BUDGET: Record<BudgetStop | 'other', { title: string; text: string }> = {
  get web_daily() {
    return {
      title: L('Model matching paused until 00:00 UTC', '模型比對暫停至 UTC 00:00'),
      text: L(
        `Today’s Meta spend, by this page and by agents together, has reached the share this page may use, so ${BY_RULES()}.`,
        `今天本頁和 agent 合計的 Meta 花費已用完本頁的額度，因此${BY_RULES()}。`,
      ),
    };
  },
  get total() {
    return {
      title: L('Model matching is paused', '模型比對已暫停'),
      text: L(
        `pickfit’s overall budget for Meta model calls is used up, so ${BY_RULES()}.`,
        `pickfit 呼叫 Meta 模型的總預算已用完，因此${BY_RULES()}。`,
      ),
    };
  },
  get unavailable() {
    return {
      title: L('Ranked without the model this time', '這次沒用模型排序'),
      text: L(
        `pickfit couldn’t check its model budget, so it didn’t call Muse Spark: ${BY_RULES()}. Search again in a minute.`,
        `pickfit 無法確認模型預算，所以${BY_RULES()}。請過一分鐘再搜尋一次。`,
      ),
    };
  },
  get other() {
    return {
      title: L('Model matching is paused for now', '模型比對暫時停止'),
      text: L(
        `pickfit’s budget for Meta model calls is used up for now, so ${BY_RULES()}.`,
        `pickfit 呼叫 Meta 模型的預算目前已用完，因此${BY_RULES()}。`,
      ),
    };
  },
};

// Every entry is a getter so its text follows the render's language (no_api_key and model_timeout included).
const DEGRADED: Record<string, { title: string; text: string }> = {
  get budget_unavailable() {
    return {
      title: L('Ranked without the model this time', '這次沒用模型排序'),
      text: L(
        'pickfit couldn’t check its model budget, so it didn’t call Muse Spark and ranked these by rules. Search again in a minute.',
        'pickfit 無法確認模型預算，這次沒呼叫 Muse Spark，改用規則排序。請過一分鐘再搜尋一次。',
      ),
    };
  },
  get model_off() {
    return {
      title: L('Model matching is off on this server', '這台伺服器未啟用模型比對'),
      text: L(
        'These results are ranked by rules: the words in your request, then no-install web apps among close fits, then verification on your OS, then the hidden-gem score.',
        '這些結果依規則排序，依序看需求裡的字詞、相近結果中免安裝的網頁應用、是否在你的作業系統上驗證過、寶藏分數。',
      ),
    };
  },
  get no_api_key() {
    return DEGRADED.model_off;
  },
  get model_timeout() {
    return {
      title: L('Ranked without the model this time', '這次沒用模型排序'),
      text: L(
        'Muse Spark didn’t answer in time, so these results are ranked by rules. Search again to retry.',
        'Muse Spark 沒有及時回應，這次改用規則排序。再搜尋一次就會重試。',
      ),
    };
  },
};
const MODEL_FAILED = () => ({
  title: L('Ranked without the model this time', '這次沒用模型排序'),
  text: L(
    'Muse Spark didn’t return a usable answer, so these results are ranked by rules. Search again to retry.',
    'Muse Spark 的回答無法使用，這次改用規則排序。再搜尋一次就會重試。',
  ),
});

/** The results heading says what came back, in words. */
function resultsTitle(out: FindOutput): string {
  const n = out.picks.length;
  if (n === 0) return L('Nothing fits yet', '目前沒有合適的工具');
  const tools = `${n} ${n === 1 ? 'tool' : 'tools'}`;
  if (out.matched_by === 'rules') {
    if (out.match_quality === 'none') return L('No clear fit, ranked by rules', '沒有明顯合適的，依規則排序');
    if (out.match_quality === 'partial') return L('Partial fits, ranked by rules', '部分符合，依規則排序');
    return L(`${tools} ranked by rules`, `${n} 款工具，依規則排序`);
  }
  return L(`${tools} ${n === 1 ? 'fits' : 'fit'} your need`, `${n} 款工具符合你的需求`);
}

function matchLine(out: FindOutput): string {
  const n = out.picks.length;
  const meet = L(
    `${out.considered} verified ${out.considered === 1 ? 'tool meets' : 'tools meet'} your conditions`,
    `${out.considered} 款已驗證工具符合你的條件`,
  );
  if (out.matched_by === 'rules') return L(`${meet}; these are ranked by rules, without a model.`, `${meet}；以下依規則排序，沒有用模型。`);
  // When more than the card limit meet them, coverage_note says how many the model compared.
  return (
    L(
      `${meet}; Meta’s ${esc(out.matched_by)} ${n === 0 ? 'found none that fits' : `picked ${n === 1 ? 'one' : n}`}.`,
      `${meet}；Meta 的 ${esc(out.matched_by)} ${n === 0 ? '沒有找到合適的' : `挑出了 ${n} 款`}。`,
    ) + (n ? L(' Code checked every reason against the tool’s profile.', '每個理由都已由程式對照簡介查核。') : '')
  );
}

/**
 * find_software's coverage_note stays English (the MCP answers carry it), so the zh page says the same
 * sentences in Chinese. The patterns follow the notes find.ts writes; a note none of them reads whole
 * is shown in English as before, never half translated.
 */
const NOTE_ZH: [RegExp, (m: RegExpMatchArray) => string][] = (() => {
  const what = (w: string) => (w === 'alternative' ? '替代工具' : '工具');
  const words = (s: string) => s.split(', ').join('、');
  const miss = (s: string): string | null => {
    if (s === 'none of them covers enough of the request') return '沒有一款涵蓋足夠的需求';
    let m = /^none of them mentions (.+)$/.exec(s);
    if (m) return `沒有一款提到 ${words(m[1])}`;
    m = /^each mentions only part of it \(the top one does not mention (.+)\)$/.exec(s);
    return m ? `每款都只涵蓋一部分（排第一的沒有提到 ${words(m[1])}）` : null;
  };
  const each = '每款的符合度標示了它涵蓋哪些部分。';
  const known = 'pickfit 的資料還沒涵蓋所有工具，知名工具仍可能適合你。';
  return [
    [/^No verified (tool|alternative) in pickfit meets these conditions\. Coverage today: .+? pickfit's catalog doesn't cover every tool yet, so a well-known one may still fit\./,
      (m) => `pickfit 沒有符合這些條件的已驗證${what(m[1])}。目前涵蓋開發者 CLI 工具、本機 AI／LLM 工具、MCP 伺服器、桌面 GUI 應用和部分網頁應用。${known}`],
    [/^None of the (\d+) verified tools that meet the conditions fits this request\./, (m) => `符合條件的 ${m[1]} 款已驗證工具中，沒有一款適合這個需求。`],
    [/^None of the listed (tool|alternative)s clearly does this job: judging by their profiles, (.+?)\. They are listed as the top-ranked \1s; each pick's match says what it covers\./,
      (m) => `列出的${what(m[1])}都不太能完成這件事：從簡介看，${miss(m[2]) ?? '\u0000'}。它們只是排名最前的${what(m[1])}；${each}`],
    [/^pickfit has no verified (tool|alternative) that clearly does this job\. Judging by their profiles, the listed \1s are the closest it has, but (.+?); each pick's match says what it covers\. pickfit's catalog doesn't cover every tool yet, so a well-known one may still fit\./,
      (m) => `pickfit 沒有明顯能完成這件事的已驗證${what(m[1])}。從簡介看，列出的是最接近的，但${miss(m[2]) ?? '\u0000'}；${each}${known}`],
    [/^No listed (tool|alternative) covers the whole request(?:: the closest, (.+?), does not mention (.+?))?\. Each pick's match says what it covers\./,
      (m) => `沒有一款${what(m[1])}涵蓋你的全部需求${m[2] ? `：最接近的 ${m[2]} 沒有提到 ${words(m[3])}` : ''}。${each}`],
    [/^(\d+) tools met the conditions; the (\d+) compared were the (\d+) whose profiles best match the request's words and the (\d+) other tools with the highest treasure scores\./,
      (m) => `有 ${m[1]} 款工具符合條件；比較的 ${m[2]} 款是簡介最符合需求字詞的 ${m[3]} 款，加上寶藏分數最高的另外 ${m[4]} 款。`],
    [/^(\d+) tools met the conditions; no profile matched the request's words, so the (\d+) with the highest treasure scores were compared\./,
      (m) => `有 ${m[1]} 款工具符合條件；沒有簡介符合需求字詞，所以比較的是寶藏分數最高的 ${m[2]} 款。`],
  ];
})();

/** The coverage note in the page's language: each of its sentences in Chinese, or the English note whole. */
function coverageNote(note: string): string {
  if (!isZh()) return note;
  const out: string[] = [];
  let rest = note.trim();
  while (rest) {
    let said: string | null = null;
    for (const [re, zh] of NOTE_ZH) {
      const m = re.exec(rest);
      if (!m) continue;
      said = zh(m);
      rest = rest.slice(m[0].length).trim();
      break;
    }
    if (said === null || said.includes('\u0000')) return note;
    out.push(said);
  }
  return out.join('');
}

/** Fitz's face for a result: it only looks pleased when it has verified picks that fit. */
function resultsFitz(out: FindOutput): FitzName {
  if (out.picks.length === 0) return 'sorry';
  if (out.matched_by === 'rules') return out.match_quality === 'good' ? 'neutral' : 'thinking';
  return 'recommending';
}

/**
 * The answer's second line, as the MCP answer gives it: "On Linux instead? Use babelscribe." Only for a system
 * another pick ran on and the first did not (a run that passed), and only the person's own system when they chose
 * one. What follows the name is that run's level label, verbatim, so nothing is guessed.
 */
function insteadLines(picks: PickOut[], catalog: Catalog, form: FormValues): string {
  const [top, ...rest] = picks;
  const topEntry = top ? catalog.bySlug.get(top.slug) : undefined;
  if (!topEntry || top.web_app || rest.length === 0) return '';
  const covered = new Set<OS>(verifiedOn(topEntry));
  const lines: string[] = [];
  for (const pick of rest) {
    const entry = catalog.bySlug.get(pick.slug);
    if (!entry || pick.web_app) continue;
    for (const os of verifiedOn(entry)) {
      const guide = entry.install[os]!;
      if (covered.has(os) || (form.os && os !== form.os) || !passed(guide.run.gui)) continue;
      covered.add(os);
      const name = `<a href="/tool/${esc(entry.slug)}">${esc(pick.name)}</a>`;
      const said = esc(levelLabel(guide.run.level, { gui: guide.run.gui, mcp: guide.mcp }));
      const where = esc(system(guide.run.os, guide.run.arch));
      const on = esc(osName(os));
      lines.push(
        `<p class="instead">${L(
          `On ${on}${form.os ? '' : ' instead'}? Use ${name}. ${said} on ${where}.`,
          `如果你用 ${on}，改用 ${name}：在 ${where} 上，${said}。`,
        )}</p>`,
      );
    }
  }
  return lines.join('');
}

/** The results area for one search. `catalog` names a best free option that is not among the picks. */
export function renderResults(
  result: SearchResult,
  form: FormValues,
  catalog: Catalog,
  opts: { cached?: boolean; budget?: BudgetStop | null } = {},
): string {
  const { out } = result;
  const parts: string[] = [];
  const said: string[] = [`<h2 class="results-title">${esc(resultsTitle(out))}</h2>`];
  if (out.considered > 0) said.push(`<p class="match-line">${matchLine(out)}</p>`);
  if (out.picks.length === 0) {
    said.push(
      `<p class="match-line">${esc(
        (out.coverage_note ? coverageNote(out.coverage_note) : null) ??
          L(
            'pickfit covers developer CLI tools, local AI tools, MCP servers and some web apps today.',
            'pickfit 目前涵蓋開發者 CLI 工具、本機 AI 工具、MCP 伺服器和部分網頁應用。',
          ),
      )}</p>`,
    );
  }
  // A partial or missing fit is said before the picks, not after them.
  const fitFirst = out.picks.length > 0 && (out.match_quality === 'partial' || out.match_quality === 'none') && out.coverage_note;
  const slugs = out.picks.map((p) => p.slug);
  const cmpHref = `/compare?tools=${slugs.map(encodeURIComponent).join(',')}${form.os ? `&amp;os=${form.os}` : ''}${form.arch ? `&amp;arch=${form.arch}` : ''}`;
  const tools = out.picks.length
    ? `<div class="res-tools"><button type="button" class="btn btn-quiet btn-sm js-only" data-open-legend>${icon('circle-help')}${L('How to read a tool card', '怎麼看工具卡')}</button>` +
      (out.picks.length > 1 ? `<a class="btn btn-quiet btn-sm" href="${cmpHref}">${icon('pin')}${L('Compare these', '比較這幾款')}</a>` : '') +
      `</div>`
    : '';
  // Everything else the search has to say goes in one quiet status list under Fitz: one Fitz per screen.
  const status: string[] = [];
  if (out.degraded) {
    const d = out.degraded_reason === 'over_budget' ? BUDGET[opts.budget ?? 'other'] : (DEGRADED[out.degraded_reason ?? ''] ?? MODEL_FAILED());
    status.push(`<li class="st st-busy" role="status">${icon('clock')}<span><strong>${esc(d.title)}${L('.', '。')}</strong> ${esc(d.text)}</span></li>`);
  }
  if (fitFirst) {
    const note = coverageNote(out.coverage_note!);
    // The first sentence is the summary; Chinese ends it with 。 and needs no space after it.
    const zh = note !== out.coverage_note;
    const cut = zh ? note.indexOf('。') : note.indexOf('. ');
    const gap = zh ? 1 : 2;
    status.push(
      cut > 0 && cut < note.length - gap
        ? `<li class="st st-caution">${icon('triangle-alert')}<details><summary>${esc(note.slice(0, cut + 1))}</summary>${esc(note.slice(cut + gap))}</details></li>`
        : `<li class="st st-caution">${icon('triangle-alert')}<span>${esc(note)}</span></li>`,
    );
  }
  if (out.clarifying_question) {
    status.push(
      `<li class="st st-info">${icon('circle-help')}<span><strong>${L('To narrow it down:', '想縮小範圍：')}</strong> ${esc(out.clarifying_question)}${L(' Set it above and search again.', '請在上方設定後再搜尋。')}</span></li>`,
    );
  }
  const head =
    `<div class="res-head">${says(resultsFitz(out), said.join(''), { size: 104 })}${tools}</div>` +
    (status.length ? `<ul class="res-status">${status.join('')}</ul>` : '');
  // "Built-in is enough" is said before anything is sold.
  if (out.no_install_option) {
    parts.push(
      // No Fitz of its own: the one over the results says it (one Fitz per screen).
      `<div class="aside ask-note"><h3>${L('You may not need to install anything', '也許不用另外安裝')}</h3><p>${esc(out.no_install_option)}</p>` +
        `<p class="quiet small">${L('From Muse Spark’s general knowledge; pickfit hasn’t checked it.', '這是 Muse Spark 的一般知識，pickfit 沒有驗證過。')}</p></div>`,
    );
  }
  if (out.picks.length) {
    // The answer first: one pick in full, then the others under their own heading.
    const instead = insteadLines(out.picks, catalog, form);
    const close = out.matched_by === 'rules' && out.match_quality !== undefined && out.match_quality !== 'good';
    const also = out.picks.length > 1 ? `<h3 class="also">${close ? L('Also close', '其他接近的') : L('Also fits', '也適合')}</h3>` : '';
    parts.push(
      `<div class="picks">${out.picks.map((pick, i) => (i === 1 ? also : '') + pickHtml(pick, i, result, form, catalog, i === 0 ? instead : '')).join('')}</div>`,
    );
    if (out.coverage_note && !fitFirst) parts.push(`<p class="quiet small">${esc(coverageNote(out.coverage_note))}</p>`);
    const entries = slugs.map((s) => catalog.bySlug.get(s)).filter((e): e is Entry => !!e);
    if (entries.length > 1) {
      parts.push(
        `<details class="sbs"><summary>${icon('chevron-down')}${L('See these side by side', '並排比較')}</summary>` +
          compareTable(entries, { os: form.os || undefined, arch: form.arch || undefined, now: new Date(catalog.built_at) }) +
          `</details>`,
      );
    }
  }
  const free = out.best_free && !out.picks.some((p) => p.slug === out.best_free!.slug) ? catalog.bySlug.get(out.best_free.slug) : undefined;
  const freeWeb = free ? webCheck(free) : null;
  if (free && out.best_free && isWebApp(free)) {
    parts.push(
      `<div class="aside best-free"><p><span class="lead-in">${L('Best free option:', '最佳免費選擇：')}</span> ` +
        `<a href="/tool/${esc(free.slug)}">${esc(free.name)}</a>. ${esc(out.best_free.reason)}</p>` +
        (freeWeb ? `<p class="quiet">${esc(webRanSentence(freeWeb))}</p>` : '') +
        `<p class="mine mine-yes">${esc(L(`${NO_INSTALL_LABEL}: it opens in a browser.`, '免安裝，用瀏覽器打開就能用。'))}</p></div>`,
    );
  } else if (free && out.best_free) {
    const guide = bestGuide(free, form.os || undefined);
    const v: PickOut['verification'] = {
      level: guide?.run.level ?? free.verification.level,
      os: guide?.run.os ?? null,
      arch: guide?.run.arch ?? null,
      method: guide?.run.method ?? null,
      replayed: guide?.run.replayed ?? false,
      checked_at: guide?.run.checked_at ?? null,
      verified_on_user_os: verifiedOnUserSystem(free, form.os || undefined, form.arch || undefined),
      gui: guide?.run.gui ?? null,
    };
    const mine = yourSystem(v, form);
    parts.push(
      `<div class="aside best-free"><p><span class="lead-in">${L('Best free option:', '最佳免費選擇：')}</span> ` +
        `<a href="/tool/${esc(free.slug)}">${esc(free.name)}</a>. ${esc(out.best_free.reason)}</p>` +
        (v.os ? runFacts(v, { mine: v.verified_on_user_os }) : `<p class="quiet">${esc(ranSentence(v))}</p>`) +
        (mine.state === 'no' ? `<p class="mine mine-no">${esc(mine.text)}</p>` : '') +
        `</div>`,
    );
  }
  // Not verified: no stitches, no badge, no steps, no link. The missing record is the label.
  const wk = out.well_known_option;
  const outside = wk
    ? `<aside class="outside" aria-label="${L('Not verified by pickfit', '未經 pickfit 驗證')}">` +
      `<h3>${L(`Also consider ${esc(wk.name)}, not verified by pickfit`, `也可以考慮 ${esc(wk.name)}（未經 pickfit 驗證）`)}</h3>${icon('circle-dashed')}` +
      `<p class="unchecked">${L(
        'pickfit has not installed or tested it. There is no run record and no install guide.',
        'pickfit 沒有安裝或測試過它，所以沒有測試紀錄和安裝指南。',
      )}</p>` +
      `<p>${esc(wk.why)}</p><p class="quiet small">${esc(wk.how_we_know)}</p></aside>`
    : '';
  if (outside && out.picks.length === 0) {
    // Nothing fits: Fitz's note on the left, the unverified option beside it.
    parts.unshift(`<div class="nofit"><div>${head}</div>${outside}</div>`);
  } else {
    parts.unshift(head);
    if (outside) parts.push(outside);
  }
  if (opts.cached)
    parts.push(`<p class="quiet small">${L('Shown from the same search made in the last few minutes.', '這是幾分鐘前同一個搜尋的結果。')}</p>`);
  return parts.join('');
}

export function renderNotice(kind: 'busy' | 'error', title: string, text: string): string {
  return notice(kind, title, text, kind === 'busy' ? 'resting' : 'sorry');
}

// ---------------------------------------------------------------- home page

/** Examples on the page: tasks the catalog covers, written for this page. */
export const EXAMPLES: [string, string][] = [
  ['Offline subtitles', 'Turn a folder of interview recordings into subtitles, offline'],
  ['Audit my MCP configs', 'Check my MCP server configs for risky permissions before I install one'],
  ['Codebase map for agents', 'An MCP server that gives my coding agent a map of my codebase'],
  ['Free up port 3000', 'See which process holds port 3000 and stop it'],
];

/** The same examples in zh-TW; EXAMPLES stays English for other modules. */
const EXAMPLES_ZH: [string, string][] = [
  ['離線把錄音轉成字幕', '把一整個資料夾的訪談錄音離線轉成字幕'],
  ['檢查我的 MCP 設定', '安裝 MCP 伺服器前，先檢查我的 MCP 設定有沒有危險權限'],
  ['給 agent 的程式碼地圖', '一個 MCP 伺服器，讓我的 coding agent 看懂整個程式碼庫的結構'],
  ['釋放連接埠 3000', '找出佔用連接埠 3000 的程序並關掉它'],
];
const examples = (): [string, string][] => (isZh() ? EXAMPLES_ZH : EXAMPLES);

const OS_CHOICES = (): [OS | '', string][] => [
  ['', L('Any OS', '不限')],
  ['macos', 'macOS'],
  ['linux', 'Linux'],
  ['windows', 'Windows'],
];
const ARCH_CHOICES = (): [Arch | '', string][] => [
  ['', L('Any CPU', '不限 CPU')],
  ['arm64', L('ARM64, Apple silicon', 'ARM64（Apple 晶片）')],
  ['x86_64', L('x86-64, Intel or AMD', 'x86-64（Intel 或 AMD）')],
];

/** The request: the need in the person's words, and their measurements. */
export function searchForm(form: FormValues): string {
  // A system is its mark, named in a tooltip and to screen readers; "any" stays a word.
  const os = OS_CHOICES().map(
    ([v, text]) =>
      `<label${v ? ` class="seg-icon" data-tip="${text}"` : ''}><input type="radio" name="os" value="${v}"${v === form.os ? ' checked' : ''}${v ? ` aria-label="${text}"` : ''}>${v ? osMark(v) : text}</label>`,
  ).join('');
  const arch = ARCH_CHOICES().map(([v, text]) => `<option value="${v}"${v === form.arch ? ' selected' : ''}>${text}</option>`).join('');
  return (
    `<form id="search" class="ask-card" method="post" action="/search#results">` +
    `<div class="ask"><label for="need">${L('I need', '我需要')}</label>` +
    `<textarea id="need" name="need" rows="1" minlength="3" maxlength="500" required autocomplete="off" spellcheck="true" ` +
    `placeholder="${L('a free way to transcribe meeting recordings offline…', '免費離線轉錄會議錄音…')}">${esc(form.need)}</textarea></div>` +
    `<div class="ask-meta"><div class="ask-opts"><span class="label" id="os-label">${L('Runs on', '執行環境')}</span>` +
    `<div class="seg" role="radiogroup" aria-labelledby="os-label">${os}</div>` +
    `<select class="select" name="arch" data-dropdown aria-label="${L('CPU architecture', 'CPU 架構')}">${arch}</select>` +
    `<label class="chip"><input type="checkbox" name="free_only" value="1"${form.free_only ? ' checked' : ''}>${icon('leaf')}${L('Free', '免費')}</label>` +
    `<label class="chip"><input type="checkbox" name="offline" value="1"${form.offline ? ' checked' : ''}>${icon('wifi-off')}${L('Offline', '不需網路')}</label>` +
    `<label class="chip"><input type="checkbox" name="private" value="1"${form.private ? ' checked' : ''}>${icon('laptop')}${L('Data stays local', '資料在本地')}</label></div>` +
    `<div class="ask-go"><span class="counter" data-counter aria-live="polite"></span>` +
    `<button type="submit" class="btn btn-primary go"><span class="btn-label">${L('Find tools', '幫我挑')}</span>${icon('arrow-right')}</button></div>` +
    `</div></form>`
  );
}

/** "How Fitz picks": the four steps, one line each; Fitz's own state shows what happens. */
function stagesSection(): string {
  const stages: { name: string; who: FitzName; text: string }[] = [
    { name: L('Read', '閱讀'), who: 'thinking', text: L('Muse Spark reads the README and writes a profile.', 'Muse Spark 讀 README，整理成簡介。') },
    { name: L('Install', '試裝'), who: 'testing', text: L('Installed in a fresh sandbox, then replayed from scratch.', '在全新沙盒裡安裝，再從頭重跑一次。') },
    {
      name: L('Match', '比對'),
      who: 'searching',
      text: L('Your sentence meets every verified profile. Each reason is checked.', '你的需求逐一比對已驗證的簡介，理由都會查核。'),
    },
    { name: L('Get the steps', '交給你'), who: 'recommending', text: L('You get the commands that worked.', '交給你真的能用的指令。') },
  ];
  return (
    `<section id="how" class="sec wrap" aria-labelledby="how-title">` +
    `<div class="sec-head"><h2 id="how-title">${L('How Fitz picks a tool', 'Fitz 怎麼幫你挑')}</h2><a class="more" href="/how">${L('See the full method', '看完整做法')}${icon('arrow-right')}</a></div>` +
    `<ol class="stages">${stages
      .map((s) => `<li class="stage"><div class="stage-fitz">${fitz(s.who, 130)}</div><h3>${esc(s.name)}</h3><p>${esc(s.text)}</p></li>`)
      .join('')}</ol></section>`
  );
}

/**
 * "Recently tested": the newest runs as a ledger (the day, the tool, where it ran), one row per run on hairlines,
 * and beside it one README the run corrected, as a left-ruled quote: what the README said, then what worked.
 */
function freshSection(showcase: Showcase): string {
  const { stats, recent, fix } = showcase;
  if (!recent.length) return '';
  const issue = fix ?? showcase.featured;
  const fixIssue = issue ? readerIssues(issue.guide.pitfalls)[0] : null;
  const fixNote =
    issue && fixIssue
      ? `<figure class="fix"><p class="fix-kicker">${L('A README the run corrected', '實測糾正的 README')}</p>` +
        `<h3><a href="/tool/${esc(issue.entry.slug)}">${esc(issue.entry.name)}</a></h3>` +
        `<ul class="readme-vs"><li class="was"><b>${L('README said', 'README 寫的')}</b><span>${esc(fixIssue.readme_said)}</span></li>` +
        `<li class="now"><b>${L('What worked', '實際可行')}</b><span>${esc(fixIssue.actually_needed)}</span></li></ul>` +
        `<figcaption>${sysTag(issue.guide.run.os, issue.guide.run.arch)} · ${esc(day(issue.guide.run.checked_at))}</figcaption></figure>`
      : '';
  const rows = recent
    .map(({ entry, guide }) => {
      const r = guide.run;
      return (
        `<li class="run-row"><time class="when" datetime="${esc(r.checked_at.slice(0, 10))}">${esc(day(r.checked_at, SHORT_DAY))}</time>` +
        `<div class="what"><p class="name-line"><a class="name" href="/tool/${esc(entry.slug)}">${esc(entry.name)}</a>` +
        (entry.scores?.treasure ? badge('gem', L('Hidden gem', '寶藏'), { icon: 'gem' }) : '') +
        `</p><p class="sum">${esc(entry.summary)}</p></div>` +
        `<p class="meta">${kindTag(entry)}${sysTag(r.os, r.arch)}</p></li>`
      );
    })
    .join('');
  return (
    `<section id="recent" class="sec wrap home-only" aria-labelledby="recent-title">` +
    `<div class="sec-head"><div><h2 id="recent-title">${L('Recently tested', '最近試過的工具')}</h2>` +
    `<p>${L(
      `Of ${stats.listed} tools, ${stats.replayed} have been installed and rerun${stats.web ? `, and ${stats.web} web ${stats.web === 1 ? 'app has' : 'apps have'} been used in a browser` : ''}. pickfit only suggests these.`,
      `收錄的 ${stats.listed} 款工具裡，${stats.replayed} 款已經實際裝過、重跑過${stats.web ? `，另外 ${stats.web} 款網頁應用也在瀏覽器裡用過` : ''}。只有這些會被推薦。`,
    )}</p></div>` +
    `<a class="more" href="/browse">${L(`Browse all ${stats.verified}`, `瀏覽全部 ${stats.verified} 款`)}${icon('arrow-right')}</a></div>` +
    `<div class="fresh"><ul class="runs-list">${rows}</ul>${fixNote}</div></section>`
  );
}

/** Fitz's rules, one line each: the words say it, so no marks. */
const RULES = (): string[] => [
  L('Tested before it’s suggested', '試過才推薦'),
  L('Ranked by fit, not stars', '看適不適合你，不看星星數'),
  L('Untested tools are labeled', '沒試過就老實說'),
  L('Says when built-in tools will do', '內建的夠用，就不叫你裝'),
  L('No ads, no referral links', '沒有廣告，也沒有推薦連結'),
];

export function rulesLabel(): string {
  return (
    `<ul class="rules" aria-label="${L('Fitz’s rules', 'Fitz 的原則')}">` +
    RULES().map((title) => `<li>${esc(title)}</li>`).join('') +
    `</ul>`
  );
}

export interface PageInput {
  nonce: string;
  /** This deployment's origin, for the MCP URL. */
  origin: string;
  showcase: Showcase;
  form: FormValues;
  /** Rendered results or a notice; empty before the first search. */
  results: string;
}

export function renderPage(input: PageInput): string {
  const { form, showcase } = input;
  const { stats } = showcase;
  const mcp = `${input.origin}/mcp`;
  const served = input.results !== '';
  const main =
    `<section class="hero mat after-top" aria-labelledby="title"><div class="wrap hero-grid"><div class="hero-main">` +
    `<h1 id="title">${L('Every tool, <em>tested</em> first', '先幫你<em>試過</em>推薦的軟體')}</h1>` +
    `<p class="lede">${L(
      'Tell pickfit what you want to do. It suggests tools it has already installed and tested, with commands that work.',
      '說說你想做什麼，pickfit 會推薦它親自裝過、測過的工具，還附上實際跑得動的指令',
    )}</p>` +
    `<div class="hero-form">${searchForm(form)}</div>` +
    `<div class="tries js-only"><span class="label">${L('Or try', '或試試')}</span>${examples()
      .map(([label, need]) => `<button type="button" class="try" data-need="${esc(need)}" title="${esc(need)}">${esc(label)}</button>`)
      .join('')}</div>` +
    `<ul class="proof"><li>${icon('book-open')}<span>${L(`<strong>${stats.listed}</strong> READMEs read`, `讀過 <strong>${stats.listed}</strong> 份 README`)}</span></li>` +
    `<li>${icon('shield-check')}<span>${L(
      `<strong>${stats.replayed}</strong> replayed in a sandbox`,
      `<strong>${stats.replayed}</strong> 款在沙盒中安裝並重跑`,
    )}</span></li>` +
    (stats.web
      ? `<li>${icon('globe')}<span>${L(
          `<strong>${stats.web}</strong> web ${stats.web === 1 ? 'app' : 'apps'} tried in a browser`,
          `<strong>${stats.web}</strong> 款網頁應用在瀏覽器實測過`,
        )}</span></li>`
      : '') +
    `<li>${icon('gem')}<span>${L(`<strong>${stats.gems}</strong> hidden gems`, `<strong>${stats.gems}</strong> 款寶藏`)}</span></li></ul>` +
    `</div><div class="hero-fitz">${fitz('hello', 320, { eager: true })}</div></div>` +
    `<div class="ruler" aria-hidden="true"></div></section>` +
    `<p id="status" class="sr" aria-live="polite"></p>` +
    `<section id="results" class="results wrap" tabindex="-1" aria-label="${L('Results', '結果')}">${input.results}</section>` +
    `<div class="home-only">` +
    stagesSection() +
    freshSection(showcase) +
    `<section id="rules" class="sec wrap" aria-labelledby="rules-title"><div class="care"><div>` +
    `<h2 id="rules-title">${L('Fitz is on your side', 'Fitz 只站你這邊')}</h2>` +
    `<p class="quiet">${L('No ads, no paid placement, no commissions', '不打廣告、不收業配，也不抽佣金')}</p>` +
    `<a class="more" href="/how#rules">${L('Why you can trust a pick', '為什麼可以放心參考')}${icon('arrow-right')}</a></div>${rulesLabel()}</div></section>` +
    // On the ground under a hairline, like every group; its way on is a link, since Find tools is the screen's one yellow.
    `<section id="agents" class="sec wrap" aria-labelledby="agents-title"><div class="agents-band">` +
    `<div class="sec-head"><div><h2 id="agents-title">${L('Use it from your agent', '在 agent 裡也能用')}</h2>` +
    `<p>${L('Connect over MCP and get the same suggestions in Claude Code or any other client', '接上 MCP，Claude Code 和其他用戶端都能拿到一樣的推薦')}</p></div>` +
    `<a class="more" href="/agents">${L('Connect your agent', '接上你的 agent')}</a></div>` +
    command(`claude mcp add --transport http pickfit ${mcp}`) +
    `</div></section>` +
    `</div>` +
    `<template id="loading"><div class="loading" role="status">` +
    says(
      'searching',
      `<h2>${L(`Checking ${stats.verified} verified tools for you…`, `正在從 ${stats.verified} 款驗證過的工具裡幫你挑…`)}</h2>` +
        `<ol><li>${L(
          'Keep the tools that meet your OS, price, offline and privacy conditions',
          '篩出符合你的系統、價格、離線與隱私條件的工具',
        )}</li><li>${L(
          'Muse Spark reads every remaining profile and picks the best fits',
          'Muse Spark 閱讀剩下的每份簡介，挑出最合適的',
        )}</li><li>${L('Code checks each reason against the profile', '程式對照簡介檢查每個理由')}</li></ol>` +
        `<p class="quiet small">${L('Usually 5 to 15 seconds.', '通常需要 5 到 15 秒。')}</p><div class="unroll" aria-hidden="true"></div>`,
      { size: 104 },
    ) +
    `<div class="skel" aria-hidden="true"><i></i><i></i><i></i><i></i></div><div class="skel" aria-hidden="true"><i></i><i></i><i></i><i></i></div></div></template>` +
    `<template id="offline">${notice(
      'error',
      L('Couldn’t reach pickfit', '無法連上 pickfit'),
      L('Check your connection and search again.', '請檢查網路連線後再搜尋一次。'),
      'test-failed',
    )}</template>`;
  return renderShell({
    nonce: input.nonce,
    title: L('pickfit: every tool, tested first', 'pickfit：先幫你試過推薦的軟體'),
    description: L(
      'Describe the job in one sentence. pickfit suggests developer CLI tools, local AI tools, MCP servers, desktop apps and web apps it has tested itself, including good ones few people know yet, with the evidence and the steps that worked.',
      '用一句話描述你要做的事。pickfit 會推薦它親自測試過的開發者 CLI 工具、本機 AI 工具、MCP 伺服器、桌面應用和網頁應用，也包括還少有人知道的好工具，並附上證據和實際可行的步驟。',
    ),
    active: 'find',
    bodyClass: served ? 'is-results' : '',
    main,
  }).replace('<body class="is-results">', '<body class="is-results" data-served="1">');
}

/** Used by the browse and tool pages: verified OSes as a short phrase. */
export const verifiedOnWords = (entry: Entry) => {
  if (isWebApp(entry))
    return webCheck(entry) ? L('Checked in a browser, any OS', '已在瀏覽器實測，不限系統') : L('Not verified yet', '尚未驗證');
  const oses = verifiedOn(entry);
  const names = listOf(oses.map((os) => osName(os)));
  return oses.length ? L(`Verified on ${names}`, `已在 ${names} 上驗證`) : L('Not verified yet', '尚未驗證');
};

export { howRan, PRICE };
