/**
 * The MCP client config get_install_guide returns for an MCP server, written by code from the
 * launch argv a fresh sandbox actually started (the run's handshake), never from README text.
 * Environment variables the README marks as required become placeholders the user fills in;
 * pickfit never had a value for them.
 */
import type { Entry, InstallGuide } from './catalog.ts';

export interface McpClientConfig {
  transport: 'stdio' | 'streamable_http';
  /** stdio: what the client starts. streamable_http: what to start first and keep running. */
  command: string;
  args: string[];
  /** streamable_http: where the client connects once the server runs; null over stdio. */
  url: string | null;
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
export const SERVER_NAME_MAX = 40;
const ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*=/;

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
  if (!handshake || handshake.launch.length === 0) return null;
  const http = handshake.transport === 'streamable_http';
  if (http ? !handshake.url : handshake.transport !== 'stdio') return null;
  // An HTTP server's start command may set variables first (VAULT_PATH=... server); those are not the command.
  const assignments = http ? handshake.launch.findIndex((w) => !ASSIGNMENT.test(w)) : 0;
  const start = assignments < 0 ? handshake.launch.length : assignments;
  const [command, ...args] = handshake.launch.slice(start);
  if (!command) return null;
  const name = entry.slug.slice(0, SERVER_NAME_MAX);
  const env = (entry.mcp?.env_vars ?? [])
    .filter((v) => v.required === true && ENV_NAME.test(v.name))
    .map((v) => ({ name: v.name, required: v.required, purpose: v.purpose, placeholder: `<${v.name}>` }));
  const envFlags = env.map((v) => `-e ${v.name}=${shellQuote(v.placeholder)}`);
  const claude = http
    ? ['claude mcp add --transport http', name, shellQuote(handshake.url!)].join(' ')
    : ['claude mcp add', name, ...envFlags, '--', ...handshake.launch.map(shellQuote)].join(' ');
  const server: Record<string, unknown> = http ? { type: 'http', url: handshake.url } : { command, args };
  if (env.length && !http) server.env = Object.fromEntries(env.map((v) => [v.name, v.placeholder]));
  const notes: string[] = [];
  if (http) {
    notes.push(
      `This server speaks HTTP: start it first and keep it running (${handshake.launch.map(shellQuote).join(' ')}${env.length ? ', with ' + env.map((v) => v.name).join(', ') + ' set' : ''}), then add the URL.`,
    );
  }
  if (handshake.launch.some(pathLike)) {
    notes.push("The sandbox run started it with paths inside pickfit's sandbox; point them at the user's own files or install location.");
  }
  if (env.length) {
    notes.push(`Ask the user for ${env.map((v) => v.name).join(', ')}; pickfit never had a value, so these are placeholders.`);
  }
  return {
    transport: http ? 'streamable_http' : 'stdio',
    command,
    args,
    url: http ? handshake.url! : null,
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
