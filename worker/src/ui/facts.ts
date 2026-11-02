/**
 * Facts in words: how a run, a level, an OS or a price reads on the page. Shared
 * by every page so the same fact is always said the same way.
 */
import type { Arch, Entry, GuiEvidence, InstallGuide, OS } from '../catalog.ts';
import { operatedText } from '../evidence.ts';

export const OS_NAME: Record<OS, string> = { macos: 'macOS', linux: 'Linux', windows: 'Windows' };
export const DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
export const SHORT_DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });

export const osName = (os: OS | null | undefined) => (os ? OS_NAME[os] : 'an unknown OS');
export const system = (os: OS | null, arch: Arch | null) => `${osName(os)}${arch ? ` ${arch}` : ''}`;

export function day(iso: string | null, format = DAY): string {
  const date = new Date(iso ?? '');
  return Number.isNaN(date.getTime()) ? '' : format.format(date);
}

/** What the verification level proves, as a short headline. */
export const LEVEL_LABEL: Record<string, string> = {
  install: 'Installs and starts',
  function: 'Its main function works',
  service: 'Its service answers requests',
  inference: 'It produces model output',
};

const SCREEN_LABEL: Record<GuiEvidence['screen'], string> = {
  main_ui: 'It opens to its main screen',
  first_run: 'It opens to its first-run screen',
  sign_in_wall: 'It opens to a sign-in screen',
  crash_or_error: 'It showed an error on launch',
  blank_or_loading: 'Its window stayed blank',
  other: 'It opened a window',
};
const SCREEN_SEEN: Record<GuiEvidence['screen'], string> = {
  main_ui: 'its main screen rendered',
  first_run: 'its first-run (setup) screen rendered',
  sign_in_wall: 'it showed a sign-in screen, and nothing past it was checked',
  crash_or_error: 'it showed an error',
  blank_or_loading: 'the window was still blank or loading',
  other: 'it showed something other than its own UI',
};

/** What a run proves, by its evidence: a GUI app's screen, an MCP server's handshake, or the level. */
export function levelLabel(level: string, evidence: { gui?: GuiEvidence | null; mcp?: { called_tool: string | null } | null } = {}): string {
  if (evidence.gui && operatedText(evidence.gui)) return 'A feature worked when operated';
  if (evidence.gui) return SCREEN_LABEL[evidence.gui.screen] ?? 'It opened a window';
  if (evidence.mcp) return evidence.mcp.called_tool ? 'An MCP client called one of its tools' : 'An MCP client connects and lists its tools';
  return LEVEL_LABEL[level] ?? level;
}

/** The check mark is for runs that passed; a GUI app that showed an error or a blank window gets none. */
export const passed = (gui?: GuiEvidence | null) => !gui || gui.screen === 'main_ui' || gui.screen === 'first_run';

/** The GUI launch in words: where it ran, who looked, and whether a feature was operated and checked. */
export function guiSentence(gui: GuiEvidence): string {
  const operated = operatedText(gui);
  return (
    `pickfit launched it on a virtual display (${gui.display}), and a separate model reading a screenshot of its window judged that ${SCREEN_SEEN[gui.screen]}. ` +
    (operated
      ? `${operated[0].toUpperCase()}${operated.slice(1)}.`
      : 'That shows it installs and starts; pickfit did not use any of its features.') +
    `${gui.launch_offline ? ' The launch passed again with the network off.' : ''}`
  );
}

export const KIND: Record<string, string> = { dev_cli: 'Developer CLI', local_ai: 'Local AI', mcp_server: 'MCP server', other: 'Other' };
export const KIND_PLURAL: Record<string, string> = { dev_cli: 'Developer CLIs', local_ai: 'Local AI tools', mcp_server: 'MCP servers' };

/** The entry's own kind, in words (cli_tool, desktop_app, ...). */
export const FORM: Record<string, string> = {
  cli_tool: 'command-line tool',
  tui: 'terminal app',
  desktop_app: 'desktop app',
  server_daemon: 'local server',
  self_hosted_web_app: 'self-hosted web app',
  mcp_server_or_agent_plugin: 'MCP server',
  library: 'library',
};
export const formOf = (entry: Pick<Entry, 'kind'>) => FORM[entry.kind] ?? entry.kind.replace(/_/g, ' ');

/** "Local AI · command-line tool"; just "MCP server" when the two say the same thing. */
export function kindLine(entry: Pick<Entry, 'kind' | 'category'>): string {
  const kind = KIND[entry.category] ?? '';
  const form = formOf(entry);
  return kind.toLowerCase() === form.toLowerCase() || !kind ? form.charAt(0).toUpperCase() + form.slice(1) : `${kind} · ${form}`;
}

export const PRICE: Record<string, string> = { free: 'Free', freemium: 'Free tier, paid plans', paid: 'Paid', unknown: 'Price not stated' };
export const PROCESSING: Record<string, string> = { local: 'Runs on your machine', cloud: 'Uses a cloud service', hybrid: 'Local and cloud', unknown: '' };

/** Pitfalls that matter to a reader: not the ones only the sandbox hit or the tool fixed itself. */
export const readerIssues = <T extends { kind?: string | null }>(issues: T[]) => issues.filter((i) => i.kind === 'readme_wrong' || i.kind === 'note' || !i.kind);

/** "pickfit installed it in a fresh Linux x86_64 sandbox, replayed from scratch" for a run summary. */
export function howRan(run: InstallGuide['run']): string {
  return run.method === 'human'
    ? `Installed by hand on ${system(run.os, run.arch)}`
    : `Installed in a fresh ${system(run.os, run.arch)} sandbox${run.replayed ? ', replayed from scratch' : ''}`;
}

/** The setup cost of a guide, counted: commands pickfit ran and steps a person does. */
export function setupWords(steps: number, manual: number): string {
  const parts = [`${steps} ${steps === 1 ? 'command' : 'commands'}`];
  if (manual) parts.push(`${manual} by hand`);
  return parts.join(', ');
}
