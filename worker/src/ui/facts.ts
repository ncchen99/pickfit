/**
 * Facts in words: how a run, a level, an OS or a price reads on the page. Shared
 * by every page so the same fact is always said the same way.
 */
import type { Arch, Entry, GuiEvidence, InstallGuide, OS, WebCheck } from '../catalog.ts';
import { operatedText } from '../evidence.ts';
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

/** The GUI launch in words: where it ran, who looked, and whether a feature was operated and checked. */
export function guiSentence(gui: GuiEvidence): string {
  const operated = operatedText(gui);
  return (
    L(
      `pickfit launched it on a virtual display (${gui.display}), and a separate model reading a screenshot of its window judged that ${SCREEN_SEEN[gui.screen]}. `,
      `pickfit 在虛擬顯示器（${gui.display}）上啟動它，再由另一個模型看視窗截圖判斷：${SCREEN_SEEN[gui.screen]}。`,
    ) +
    (operated
      ? L(`${operated[0].toUpperCase()}${operated.slice(1)}.`, `${operated[0].toUpperCase()}${operated.slice(1)}。`)
      : L('That shows it installs and starts; pickfit did not use any of its features.', '這證明它能安裝並啟動；pickfit 沒有操作它的任何功能。')) +
    `${gui.launch_offline ? L(' The launch passed again with the network off.', '斷網後再次啟動也通過。') : ''}`
  );
}

export const KIND: Record<string, string> = {
  get dev_cli() { return L('Developer CLI', '開發者 CLI'); },
  get local_ai() { return L('Local AI', '本機 AI'); },
  get mcp_server() { return L('MCP server', 'MCP 伺服器'); },
  get other() { return L('Other', '其他'); },
};
export const KIND_PLURAL: Record<string, string> = {
  get dev_cli() { return L('Developer CLIs', '開發者 CLI'); },
  get local_ai() { return L('Local AI tools', '本機 AI 工具'); },
  get mcp_server() { return L('MCP servers', 'MCP 伺服器'); },
  get web_app() { return L('Web apps', '網頁應用'); },
};

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
  // A web app outside the three categories is just a web app.
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
