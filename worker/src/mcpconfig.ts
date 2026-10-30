/**
 * The MCP client config get_install_guide returns for an MCP server, written by code from the
 * launch argv a fresh sandbox actually started (the run's handshake), never from README text.
 * Environment variables the README marks as required become placeholders the user fills in;
 * pickfit never had a value for them.
 */
import type { Entry, InstallGuide } from './catalog.ts';

export interface McpClientConfig {
  transport: 'stdio';
  command: string;
  args: string[];
  /** One line for Claude Code. */
  claude_code: string;
  /** An mcpServers entry for Claude Desktop, Cursor and other clients that read that JSON. */
  json: string;
  env: { name: string; required: boolean | null; purpose: string | null; placeholder: string }[];
  /** Tool names the handshake listed in the sandbox. */
  tools: string[];
  tool_count: number;
  /** A tool pickfit called without an error, or null when only the handshake was checked. */
  called_tool: string | null;
  /** true: the handshake also completed with the network off. */
  works_offline: boolean | null;
  note: string | null;
}

const SAFE_WORD = /^[A-Za-z0-9_@%+=:,./-]+$/;
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;
const SERVER_NAME_MAX = 40;

/** POSIX shell quoting: plain words stay as they are, anything else goes in single quotes. */
export function shellQuote(word: string): string {
  if (word.startsWith('~/') && SAFE_WORD.test(word.slice(2))) return word; // keep ~ expanding
  return SAFE_WORD.test(word) ? word : `'${word.replace(/'/g, `'"'"'`)}'`;
}

/** An argument that names a file or directory (the sandbox's, not the user's). */
function pathLike(arg: string): boolean {
  const value = arg.includes('=') ? arg.slice(arg.indexOf('=') + 1) : arg;
  if (value.includes('://')) return false;
  return /^(~|\.{1,2})?\//.test(value) || value.includes('/home/sbx') || (!value.startsWith('-') && value.includes('/'));
}

export function clientConfig(entry: Entry, guide: InstallGuide | null): McpClientConfig | null {
  const handshake = guide?.mcp;
  if (!handshake || handshake.transport !== 'stdio' || handshake.launch.length === 0) return null;
  const [command, ...args] = handshake.launch;
  const name = entry.slug.slice(0, SERVER_NAME_MAX);
  const env = (entry.mcp?.env_vars ?? [])
    .filter((v) => v.required === true && ENV_NAME.test(v.name))
    .map((v) => ({ name: v.name, required: v.required, purpose: v.purpose, placeholder: `<${v.name}>` }));
  const envFlags = env.map((v) => `-e ${v.name}=${shellQuote(v.placeholder)}`);
  const claude = ['claude mcp add', name, ...envFlags, '--', ...handshake.launch.map(shellQuote)].join(' ');
  const server: Record<string, unknown> = { command, args };
  if (env.length) server.env = Object.fromEntries(env.map((v) => [v.name, v.placeholder]));
  const notes: string[] = [];
  if (args.some(pathLike) || pathLike(command)) {
    notes.push("The sandbox run started it with paths inside pickfit's sandbox; point them at the user's own files or install location.");
  }
  if (env.length) {
    notes.push(`Ask the user for ${env.map((v) => v.name).join(', ')}; pickfit never had a value, so these are placeholders.`);
  }
  return {
    transport: 'stdio',
    command,
    args,
    claude_code: claude,
    json: JSON.stringify({ mcpServers: { [name]: server } }, null, 2),
    env,
    tools: handshake.tools,
    tool_count: handshake.tool_count,
    called_tool: handshake.called_tool,
    works_offline: handshake.offline,
    note: notes.length ? notes.join(' ') : null,
  };
}
