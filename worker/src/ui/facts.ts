/**
 * Facts in words: how a run, a level, an OS or a price reads on the page. Shared
 * by every page so the same fact is always said the same way.
 */
import type { Arch, Category, Entry, GuiEvidence, InstallGuide, NamedCategory, OS, WebCheck } from '../catalog.ts';
import { operatedText } from '../evidence.ts';
import { featuresOut, shownWorking, type FeaturesOut } from '../features.ts';
import { L, isZh } from '../i18n.ts';

export const OS_NAME: Record<OS, string> = { macos: 'macOS', linux: 'Linux', windows: 'Windows' };
export const DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
export const SHORT_DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });

export const osName = (os: OS | null | undefined) => (os ? OS_NAME[os] : L('an unknown OS', '未知的作業系統'));
export const system = (os: OS | null, arch: Arch | null) => `${osName(os)}${arch ? ` ${arch}` : ''}`;

const ZH_DAY = new Intl.DateTimeFormat('zh-TW', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
const ZH_SHORT_DAY = new Intl.DateTimeFormat('zh-TW', { day: 'numeric', month: 'long', timeZone: 'UTC' });

export function day(iso: string | null, format = DAY): string {
  const date = new Date(iso ?? '');
  if (Number.isNaN(date.getTime())) return '';
  // zh-TW pages: 2026年11月1日 (11月1日 for the short form).
  if (isZh()) return (format === SHORT_DAY ? ZH_SHORT_DAY : ZH_DAY).format(date);
  return format.format(date);
}

/** What the verification level proves, as a short headline. */
export const LEVEL_LABEL: Record<string, string> = {
  get install() { return L('Installs and starts', '可安裝並啟動'); },
  get function() { return L('Its main function works', '主要功能可用'); },
  get service() { return L('Its service answers requests', '服務能回應請求'); },
  get inference() { return L('It produces model output', '能產生模型輸出'); },
};

const SCREEN_LABEL: Record<GuiEvidence['screen'], string> = {
  get main_ui() { return L('It opens to its main screen', '能開到主畫面'); },
  get first_run() { return L('It opens to its first-run screen', '能開到首次設定畫面'); },
  get sign_in_wall() { return L('It opens to a sign-in screen', '停在登入畫面'); },
  get crash_or_error() { return L('It showed an error on launch', '啟動時顯示錯誤'); },
  get blank_or_loading() { return L('Its window stayed blank', '視窗一片空白'); },
  get other() { return L('It opened a window', '能開啟視窗'); },
};
const SCREEN_SEEN: Record<GuiEvidence['screen'], string> = {
  get main_ui() { return L('its main screen rendered', '它的主畫面已正常顯示'); },
  get first_run() { return L('its first-run (setup) screen rendered', '它的首次使用（設定）畫面已正常顯示'); },
  get sign_in_wall() { return L('it showed a sign-in screen, and nothing past it was checked', '它顯示了登入畫面，登入之後的內容都沒有檢查'); },
  get crash_or_error() { return L('it showed an error', '它顯示了錯誤'); },
  get blank_or_loading() { return L('the window was still blank or loading', '視窗仍是空白或還在載入'); },
  get other() { return L('it showed something other than its own UI', '它顯示的不是自己的介面'); },
};

/** What a run proves, by its evidence: a GUI app's screen, an MCP server's handshake, or the level. */
export function levelLabel(level: string, evidence: { gui?: GuiEvidence | null; mcp?: { called_tool: string | null } | null } = {}): string {
  if (evidence.gui && operatedText(evidence.gui)) return L('A feature worked when operated', '實際操作，功能可用');
  if (evidence.gui) return SCREEN_LABEL[evidence.gui.screen] ?? L('It opened a window', '能開啟視窗');
  if (evidence.mcp) return evidence.mcp.called_tool ? L('An MCP client called one of its tools', 'MCP 用戶端成功呼叫工具') : L('An MCP client connects and lists its tools', 'MCP 用戶端能連上並列出工具');
  return LEVEL_LABEL[level] ?? level;
}

/** What a web app's browser run proves, as a headline. */
export const webLevelLabel = (check: WebCheck) => (check.level === 'function' ? L('It worked when used in a browser', '瀏覽器實測可用') : L('It opens to its main screen', '能開到主畫面'));

/** The check mark is for runs that passed; a GUI app that showed an error or a blank window gets none. */
export const passed = (gui?: GuiEvidence | null) => !gui || gui.screen === 'main_ui' || gui.screen === 'first_run';

/** usage_guide's plain title for a feature, if it has one. */
export const guideTitle = (entry: Entry | null | undefined, feature: string) => entry?.usage_guide?.features.find((f) => f.feature === feature)?.title ?? null;

/**
 * The features a run's operations showed working, each once, by the plain title its feature row uses. With the run's
 * feature list, only the ones it counts as checked: an operation can pass while what it showed was judged not to show
 * the feature, and the page then lists that feature as not shown working, so the run sentence must not say it worked.
 */
export function workedFeatures(
  ops: { feature: string | null; passed: boolean }[],
  entry?: Entry | null,
  features?: FeaturesOut | null,
): { used: boolean; names: string[] } {
  const passed = ops.filter((o) => o.passed);
  // Not the ones checked only against a stand-in: this sentence says a feature worked.
  const counted = features?.recorded ? new Set(shownWorking(features).map((c) => c.feature)) : null;
  const names = passed
    .filter((o) => !counted || (o.feature !== null && counted.has(o.feature)))
    .map((o) => (o.feature ? (guideTitle(entry, o.feature) ?? o.feature) : L('a task', '一項任務')));
  return { used: passed.length > 0, names: [...new Set(names)] };
}

/** "pickfit then used it, and this worked: …", or what it did when nothing it used counts as working. */
const usedWords = (w: { used: boolean; names: string[] }, none: string) =>
  w.names.length
    ? L(`pickfit then used it, and this worked: ${w.names.join('; ')}.`, `pickfit 接著實際操作，這些功能可用：${w.names.join('；')}。`)
    : w.used
      ? L('pickfit then used it, but what it saw didn’t show a feature working.', 'pickfit 接著實際操作，但看到的結果沒有顯示功能可用。')
      : none;

/**
 * The GUI launch in words, for a reader: what it showed when pickfit opened it, and which features worked when pickfit
 * used it. How it was seen (the virtual display, the screen judge, the operator) is in how_we_know and on /how. With
 * the entry and the run's features, the features are named as their rows name them, and only the checked ones.
 */
export function guiSentence(gui: GuiEvidence, ctx: { entry?: Entry | null; features?: FeaturesOut | null } = {}): string {
  // operatedText() decides whether any operation counts (an action_checked run with one that passed).
  const worked = operatedText(gui) ? workedFeatures(gui.operations ?? [], ctx.entry, ctx.features) : { used: false, names: [] };
  return (
    L(`When pickfit opened it, ${SCREEN_SEEN[gui.screen]}. `, `pickfit 打開它時，${SCREEN_SEEN[gui.screen]}。`) +
    usedWords(worked, L('That shows it installs and starts; pickfit did not use any of its features.', '這證明它能安裝並啟動；pickfit 沒有操作它的任何功能。')) +
    `${gui.launch_offline ? L(' The launch passed again with the network off.', '斷網後再次啟動也通過。') : ''}`
  );
}

/**
 * A web app's browser run in a reader's words: when it opened, and which features worked when pickfit used them (only
 * the ones its feature list counts as checked), each once. webRanSentence (webapp.ts) words the same run for agents, with
 * the browser build, the model and the replay rule.
 */
export function webRunWords(entry: Entry, check: WebCheck): string {
  const worked = check.level === 'function' ? workedFeatures(check.operations, entry, featuresOut(entry, null)) : { used: false, names: [] };
  return (
    L(`When pickfit opened it in a browser on ${day(check.checked_at)}, the page loaded to its main screen. `, `pickfit 於 ${day(check.checked_at)} 在瀏覽器中打開它時，頁面已載入主畫面。`) +
    usedWords(worked, L('pickfit did not use any of its features.', 'pickfit 沒有使用它的任何功能。'))
  );
}

/** A category in words, one label per entry of CATEGORIES (catalog.ts): the type check fails when one is missing. */
export const KIND: Record<string, string> = {
  get dev_cli() { return L('Developer CLI', '開發者 CLI'); },
  get local_ai() { return L('Local AI', '本機 AI'); },
  get mcp_server() { return L('MCP server', 'MCP 伺服器'); },
  get infra_devops() { return L('Infra & DevOps', '維運與容器'); },
  get security_net() { return L('Security & networking', '資安與網路'); },
  get data_db() { return L('Data & databases', '資料與資料庫'); },
  get productivity_docs() { return L('Productivity & docs', '生產力與文件'); },
  get media_files() { return L('Media & files', '影音與檔案工具'); },
  get other() { return L('Other', '其他'); },
} satisfies Record<Category, string>;
/** The shelves of Browse: every named category, and web apps (a kind, across categories). */
export const KIND_PLURAL: Record<string, string> = {
  get dev_cli() { return L('Developer CLIs', '開發者 CLI'); },
  get local_ai() { return L('Local AI tools', '本機 AI 工具'); },
  get mcp_server() { return L('MCP servers', 'MCP 伺服器'); },
  get infra_devops() { return L('Infra & DevOps tools', '維運與容器工具'); },
  get security_net() { return L('Security & networking tools', '資安與網路工具'); },
  get data_db() { return L('Data & database tools', '資料與資料庫工具'); },
  get productivity_docs() { return L('Productivity & docs tools', '生產力與文件工具'); },
  get media_files() { return L('Media & file tools', '影音與檔案工具'); },
  get web_app() { return L('Web apps', '網頁應用'); },
} satisfies Record<NamedCategory | 'web_app', string>;

/** The entry's own kind, in words (cli_tool, desktop_app, ...). */
export const FORM: Record<string, string> = {
  get cli_tool() { return L('command-line tool', '命令列工具'); },
  get tui() { return L('terminal app', '終端機應用程式'); },
  get desktop_app() { return L('desktop app', '桌面應用程式'); },
  get server_daemon() { return L('local server', '本機伺服器'); },
  get self_hosted_web_app() { return L('self-hosted web app', '自架網頁應用'); },
  get web_app() { return L('web app', '網頁應用'); },
  get mcp_server_or_agent_plugin() { return L('MCP server', 'MCP 伺服器'); },
  get library() { return L('library', '函式庫'); },
};
export const formOf = (entry: Pick<Entry, 'kind'>) => FORM[entry.kind] ?? entry.kind.replace(/_/g, ' ');

/** "Local AI · command-line tool"; just "MCP server" when the two say the same thing. */
export function kindLine(entry: Pick<Entry, 'kind' | 'category'>): string {
  // A web app outside the named categories is just a web app.
  const kind = entry.kind === 'web_app' && entry.category === 'other' ? '' : (KIND[entry.category] ?? '');
  const form = formOf(entry);
  return kind.toLowerCase() === form.toLowerCase() || !kind ? form.charAt(0).toUpperCase() + form.slice(1) : `${kind} · ${form}`;
}

export const PRICE: Record<string, string> = {
  get free() { return L('Free', '免費'); },
  get freemium() { return L('Free tier, paid plans', '免費／付費方案'); },
  get paid() { return L('Paid', '付費'); },
  get unknown() { return L('Price not stated', '未標示價格'); },
};
export const PROCESSING: Record<string, string> = {
  get local() { return L('Runs on your machine', '在你的電腦上執行'); },
  get cloud() { return L('Uses a cloud service', '使用雲端服務'); },
  get hybrid() { return L('Local and cloud', '本機與雲端'); },
  unknown: '',
};

/** Pitfalls that matter to a reader: not the ones only the sandbox hit or the tool fixed itself. */
export const readerIssues = <T extends { kind?: string | null }>(issues: T[]) => issues.filter((i) => i.kind === 'readme_wrong' || i.kind === 'note' || !i.kind);

/** "pickfit installed it in a fresh Linux x86_64 sandbox, replayed from scratch" for a run summary. */
export function howRan(run: InstallGuide['run']): string {
  return run.method === 'human'
    ? L(`Installed by hand on ${system(run.os, run.arch)}`, `在 ${system(run.os, run.arch)} 上手動安裝`)
    : L(
        `Installed in a fresh ${system(run.os, run.arch)} sandbox${run.replayed ? ', replayed from scratch' : ''}`,
        `在全新的 ${system(run.os, run.arch)} 沙盒中安裝${run.replayed ? '，並從頭重跑' : ''}`,
      );
}

/** The setup cost of a guide, counted: commands pickfit ran and steps a person does. */
export function setupWords(steps: number, manual: number): string {
  const parts = [L(`${steps} ${steps === 1 ? 'command' : 'commands'}`, `${steps} 個指令`)];
  if (manual) parts.push(L(`${manual} by hand`, `${manual} 個手動步驟`));
  return parts.join(isZh() ? '，' : ', ');
}

/** A card field (cards.ts CARD_FIELDS) in plain words, for the "From its profile" line under a reason; an unknown field
 * keeps its name. */
const FIELD: Record<string, [string, string]> = {
  name: ['Name', '名稱'],
  summary: ['Summary', '簡介'],
  why_worth_it: ['Why it is worth it', '值得用的原因'],
  category: ['Category', '類別'],
  kind: ['Kind of tool', '工具類型'],
  maturity: ['Maturity', '成熟度'],
  tags: ['Tags', '標籤'],
  use_cases: ['Use cases', '用途'],
  features_checked: ['Features pickfit checked', 'pickfit 檢查過的功能'],
  features_not_checked: ['Features not checked', '沒有檢查的功能'],
  alternatives_to: ['An alternative to', '可替代'],
  platforms: ['Systems', '支援的系統'],
  verified_on: ['Where pickfit ran it', 'pickfit 在哪裡跑過'],
  verified_on_user_os: ['Checked on your system', '在你的系統上檢查過'],
  install_method_user_os: ['How it installs on your system', '在你的系統上怎麼安裝'],
  manual_steps: ['Steps you do by hand', '要手動做的步驟'],
  pricing: ['Price', '價格'],
  pricing_note: ['Price note', '價格說明'],
  open_source: ['Open source', '開源'],
  license: ['License', '授權'],
  processing: ['Where it runs', '在哪裡執行'],
  gpu: ['GPU', 'GPU'],
  network: ['Network', '網路需求'],
  api_keys: ['API keys', 'API 金鑰'],
  apple_silicon_only: ['Apple silicon only', '只支援 Apple 晶片'],
  min_ram_gb: ['Memory needed (GB)', '需要的記憶體（GB）'],
  runtimes: ['Runtimes', '執行環境'],
  system_packages: ['System packages', '系統套件'],
  last_release: ['Last release', '最近一次發布'],
  quality: ['Quality score', '品質分數'],
  popularity: ['Popularity', '知名度'],
  mcp_tools: ['MCP tools', 'MCP 工具'],
  mcp_env_vars: ['MCP settings', 'MCP 設定'],
  no_install: ['No install', '免安裝'],
  account_needed: ['Account needed', '需要帳號'],
  ads_seen: ['Ads seen', '有沒有廣告'],
  third_party_domains: ['Other sites it contacts', '連到的其他網站'],
  data_sent: ['What you type leaves the device', '輸入內容是否離開裝置'],
  works_offline: ['Works offline', '能離線使用'],
  capabilities_matched: ['What its docs say it can do', '文件寫它能做的事'],
};
export const fieldLabel = (field: string) => (FIELD[field] ? L(...FIELD[field]) : field);
