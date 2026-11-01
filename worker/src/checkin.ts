/**
 * get_install_guide's check_in: how the agent finds out, weeks later, whether
 * the user still uses a tool pickfit recommended, with nothing resident on the
 * machine (brief 3.1). The agent runs a few read-only commands itself, only
 * when the user agrees, and sends report_outcome one stage and a coarse
 * last_used; never the output, an exact time, paths or other software.
 * Commands come from the recorded install steps and check, never from a model.
 */
import type { Entry, InstallGuide, OS } from './catalog.ts';
import { REC_TTL_LATER_DAYS } from './events.ts';
import { SERVER_NAME_MAX } from './mcpconfig.ts';

export interface CheckIn {
  /** Not before this many days after the install. */
  after_days: number;
  /** The rec_id counts for still_using, replaced and abandoned until then. */
  valid_until: string;
  commands: { command: string; shows: string }[];
  how: string;
}

export const CHECK_IN_AFTER_DAYS = 7;
const MAX_COMMANDS = 4;

const NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const NPM_NAME = /^(@[a-z0-9._-]+\/)?[a-z0-9._-]{1,100}$/i;
const APP_NAME = /^[A-Za-z0-9][A-Za-z0-9 .+_-]{0,60}$/;
// First words of a check command that are not the tool's own command.
const NOT_THE_TOOL = new Set([
  '.', 'bash', 'brew', 'bun', 'bunx', 'cargo', 'cat', 'cd', 'chmod', 'claude', 'cmd', 'command', 'cp', 'curl', 'deno',
  'docker', 'echo', 'env', 'export', 'false', 'for', 'git', 'go', 'if', 'java', 'ln', 'ls', 'mkdir', 'mv', 'node', 'npm',
  'npx', 'open', 'pip', 'pip3', 'pipx', 'powershell', 'printf', 'pwsh', 'python', 'python3', 'rm', 'set', 'sh',
  'source', 'sudo', 'tar', 'test', 'timeout', 'true', 'unzip', 'uv', 'uvx', 'wget', 'which', 'while', 'zsh',
]);

type Manager = 'npm' | 'uv' | 'pipx' | 'pip' | 'brew' | 'cargo';

const words = (command: string) =>
  command
    .split(/&&|\|\||[;|\n]/)
    .map((part) => part.trim().split(/\s+/).map((w) => w.replace(/^["']|["']$/g, '')).filter(Boolean));

/** The package a recorded install step installed, per package manager; plain names only. */
function packages(guide: InstallGuide): [Manager, string][] {
  const found: [Manager, string][] = [];
  const add = (manager: Manager, raw: string | undefined) => {
    if (!raw) return;
    // A brew formula from a tap (owner/tap/name) is listed by its last part.
    const plain = manager === 'brew' ? raw.split('/').pop()! : raw;
    const name = manager === 'npm' ? plain.replace(/(.)@[^/]*$/, '$1') : plain.split(/[[=<>~!@]/)[0];
    const ok = manager === 'npm' ? NPM_NAME.test(name) : NAME.test(name);
    if (ok && !found.some(([m, n]) => m === manager && n === name)) found.push([manager, name]);
  };
  for (const step of guide.steps) {
    for (const w of words(step.command)) {
      const args = (from: number) => w.slice(from).filter((a) => !a.startsWith('-') && !a.startsWith('2>'));
      if (w[0] === 'npm' && ['install', 'i', 'add'].includes(w[1]) && w.some((a) => a === '-g' || a === '--global')) {
        add('npm', args(2)[0]);
      } else if (w[0] === 'uv' && w[1] === 'tool' && w[2] === 'install') add('uv', args(3)[0]);
      else if (w[0] === 'pipx' && w[1] === 'install') add('pipx', args(2)[0]);
      else if (w[0] === 'brew' && w[1] === 'install') add('brew', args(2)[0]);
      else if (w[0] === 'cargo' && w[1] === 'install') add('cargo', args(2)[0]);
      // pip steps also install test and build helpers, so only a pip guide's own step counts.
      else if (guide.method === 'pip' && /^pip3?$/.test(w[0]) && w[1] === 'install') add('pip', args(2)[0]);
    }
  }
  return found;
}

/** The tool's own command, from the recorded check (`foo --version`, `command -v foo`, `which foo`). */
function toolCommand(guide: InstallGuide): string | null {
  const first = guide.check ? words(guide.check.command)[0] ?? [] : [];
  const word = first[0] === 'which' ? first[1] : first[0] === 'command' && first[1] === '-v' ? first[2] : first[0];
  return word && NAME.test(word) && !NOT_THE_TOOL.has(word) ? word : null;
}

function listCommand(manager: Manager, name: string, os: OS): string {
  const only = (pattern: string) => (os === 'windows' ? ` | Select-String -Pattern '${pattern}'` : ` | grep -i -- '${pattern}'`);
  switch (manager) {
    case 'npm':
      return `npm ls -g --depth=0 ${name}`;
    case 'uv':
      return `uv tool list${only(`^${name} `)}`;
    case 'pipx':
      return `pipx list --short${only(`^${name} `)}`;
    case 'brew':
      return `brew list --versions ${name}`;
    case 'cargo':
      return `cargo install --list${only(`^${name} `)}`;
    case 'pip':
      return `${os === 'windows' ? 'py' : 'python3'} -m pip show ${name}`;
  }
}

const validUntilFrom = (now: Date) => new Date(now.getTime() + REC_TTL_LATER_DAYS * 86_400_000).toISOString().slice(0, 10);

/** A web app's check-in: ask the user, and only ask. Nothing on the machine says whether a website is still used. */
export function webCheckIn(entry: Entry, url: string, now: Date): CheckIn {
  const validUntil = validUntilFrom(now);
  return {
    after_days: CHECK_IN_AFTER_DAYS,
    valid_until: validUntil,
    commands: [],
    how:
      `Not now. Keep this rec_id and the slug (with the user's OK, in your memory or notes). ` +
      `From ${CHECK_IN_AFTER_DAYS} days after they first opened it until ${validUntil}, the next time the user talks with you about software, or when they ask, ` +
      `ask whether they still use ${entry.name} (${url}): this week, this month, or longer ago? Only ask: never read their browser history, ` +
      `bookmarks, cookies, open tabs or anything else on the machine. ` +
      `Then report_outcome with this rec_id: still_using if they still use it; abandoned if they stopped; replaced, with replaced_by, if they switched to something else. ` +
      `Pass last_used: this_week, this_month, older or unknown. Send only that. If the user says no, report nothing.`,
  };
}

export function checkIn(entry: Entry, guide: InstallGuide | null, os: OS, now: Date): CheckIn {
  const commands: CheckIn['commands'] = [];
  const mcp = entry.category === 'mcp_server' || entry.kind === 'mcp_server_or_agent_plugin';
  if (mcp) {
    const server = entry.slug.slice(0, SERVER_NAME_MAX);
    commands.push({
      command: `claude mcp get ${server}`,
      shows: `Whether Claude Code still has the server; in another client, look for "${server}" in its mcpServers config only`,
    });
  }
  const bin = guide ? toolCommand(guide) : null;
  if (bin) {
    commands.push(
      os === 'windows'
        ? { command: `Get-Command ${bin} -ErrorAction SilentlyContinue`, shows: 'Its path if it is still installed; nothing if not' }
        : { command: `command -v ${bin}`, shows: 'Its path if it is still installed; nothing if not' },
    );
  }
  for (const [manager, name] of guide ? packages(guide) : []) {
    commands.push({ command: listCommand(manager, name, os), shows: `Whether ${manager} still lists ${name}, and nothing else` });
  }
  if (os === 'macos' && entry.kind === 'desktop_app' && APP_NAME.test(entry.name)) {
    commands.push({
      command: `mdls -name kMDItemLastUsedDate -raw "/Applications/${entry.name}.app"`,
      shows: 'When macOS last saw the app opened ((null) if never, or if the app is not there); turn it into last_used, never send the date',
    });
  }
  const validUntil = validUntilFrom(now);
  return {
    after_days: CHECK_IN_AFTER_DAYS,
    valid_until: validUntil,
    commands: commands.slice(0, MAX_COMMANDS),
    how:
      `Not now. Keep this rec_id and the slug (with the user's OK, in your memory or notes). ` +
      `From ${CHECK_IN_AFTER_DAYS} days after the install until ${validUntil}, the next time the user talks with you about software, or when they ask, ` +
      `ask whether you may check if they still use ${entry.name}. Only after a yes, run these read-only commands` +
      (commands.length ? '' : " (none recorded: use the list command of whatever installed it, filtered to this tool)") +
      `, and ask at most one question: did they use it this week, this month, or longer ago? ` +
      `Then report_outcome with this rec_id: still_using if it is installed and they still use it; abandoned if it is gone or they stopped; ` +
      `replaced, with replaced_by, if they switched to something else. Pass last_used: this_week, this_month, older or unknown. ` +
      `Send only that: never the command output, an exact date, a path, or other software. If the user says no, report nothing. ` +
      `If they would rather check on their own, offer to save rec_id, slug, name and check_in to a file for pickfit's one-shot ` +
      `scripts/checkin.py (github.com/ncchen99/pickfit): it shows what it will send and sends only after a yes.`,
  };
}
