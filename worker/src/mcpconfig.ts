/**
 * The MCP client config get_install_guide returns for an MCP server, written by code from the
 * launch argv a fresh sandbox actually started (the run's handshake), never from README text.
 * Environment variables the README marks as required become placeholders the user fills in;
 * pickfit never had a value for them.
 *
 * The argv is written the way a user starts it (userLaunch): the sandbox home becomes $HOME, and files the run made up
 * for its test become placeholders. The record keeps the argv exactly as run.
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
  if (word.startsWith('$HOME/') && SAFE_WORD.test(word.slice(6))) return word; // and $HOME
  return SAFE_WORD.test(word) ? word : `'${word.replace(/'/g, `'"'"'`)}'`;
}

const SANDBOX_HOME = /^(?:\/home\/sbx|\/Users\/sbx|~|\$HOME|\$\{HOME\})(?=\/|$)/;
/** Scratch space the run wrote its test files to, and the work folder it pointed tools at: not the user's. */
const SCRATCH = /^(?:\/tmp|\/private\/tmp|\/var\/folders|\$HOME\/work)(?=\/|$)/;
const OPTION_OR_VAR = /^(-{0,2}[A-Za-z_][\w.-]*)=(.*)$/s;
const INSTALL_FOLDER = '<install-folder>';

/**
 * The run's launch argv as a user starts it. pickfit's own probe around the server is dropped; the sandbox home becomes
 * $HOME; a file or folder the run made for its test becomes a placeholder named after its option; a path relative to
 * where the sandbox happened to run hangs off the folder the user installed into.
 */
export function userLaunch(launch: string[]): { words: string[]; fills: string[] } {
  const probe = launch.findIndex((w) => w.endsWith('/mcp_probe.py'));
  const after = probe < 0 ? -1 : launch.indexOf('--', probe);
  const argv = after < 0 ? launch : launch.slice(after + 1);
  const fills = new Set<string>();
  const words = argv.map((word, i) => {
    const set = OPTION_OR_VAR.exec(word);
    const value = set ? set[2] : word;
    const prefix = set ? `${set[1]}=` : '';
    const home = value.replace(SANDBOX_HOME, '$HOME');
    if (SCRATCH.test(home)) {
      const option = set ? set[1] : argv[i - 1]?.startsWith('-') && argv[i - 1] !== '--' ? argv[i - 1] : 'path';
      const fill = `<${option.replace(/^-+/, '')}>`;
      fills.add(fill);
      return prefix + fill;
    }
    if (home.startsWith('$HOME')) return prefix + home;
    // A relative path: not an option, a package (@scope/name), a URL or spec (git+https:, github:), or a placeholder.
    if (/^[^-@$</][^:]*\//.test(value)) {
      fills.add(INSTALL_FOLDER);
      return `${prefix}${INSTALL_FOLDER}/${value.replace(/^\.\//, '')}`;
    }
    return word;
  });
  return { words, fills: [...fills] };
}

/** A JSON client starts the command without a shell, so nothing would expand $HOME: a small shell around it does. */
function throughShell(words: string[]): string[] {
  const quoted = words.map((w) => (w.includes('$HOME') ? `"${w.replace(/(["\\`])/g, '\\$1')}"` : shellQuote(w)));
  return ['sh', '-c', `exec ${quoted.join(' ')}`];
}

export function clientConfig(entry: Entry, guide: InstallGuide | null): McpClientConfig | null {
  const handshake = guide?.mcp;
  if (!handshake || handshake.launch.length === 0) return null;
  const { words: launch, fills } = userLaunch(handshake.launch);
  const http = handshake.transport === 'streamable_http';
  if (http ? !handshake.url : handshake.transport !== 'stdio') return null;
  // An HTTP server's start command may set variables first (VAULT_PATH=... server); those are not the command.
  const assignments = http ? launch.findIndex((w) => !ASSIGNMENT.test(w)) : 0;
  const start = assignments < 0 ? launch.length : assignments;
  const [ran, ...ranArgs] = launch.slice(start);
  // The shell only where $HOME has to expand; `sh` is on every system pickfit runs MCP servers on (Linux, macOS).
  const [command, ...args] = !http && launch.some((w) => w.includes('$HOME')) ? throughShell(launch) : [ran, ...ranArgs];
  if (!ran) return null;
  const name = entry.slug.slice(0, SERVER_NAME_MAX);
  const env = (entry.mcp?.env_vars ?? [])
    .filter((v) => v.required === true && ENV_NAME.test(v.name))
    .map((v) => ({ name: v.name, required: v.required, purpose: v.purpose, placeholder: `<${v.name}>` }));
  const envFlags = env.map((v) => `-e ${v.name}=${shellQuote(v.placeholder)}`);
  const claude = http
    ? ['claude mcp add --transport http', name, shellQuote(handshake.url!)].join(' ')
    : ['claude mcp add', name, ...envFlags, '--', ...launch.map(shellQuote)].join(' ');
  const server: Record<string, unknown> = http ? { type: 'http', url: handshake.url } : { command, args };
  if (env.length && !http) server.env = Object.fromEntries(env.map((v) => [v.name, v.placeholder]));
  const notes: string[] = [];
  if (http) {
    notes.push(
      `This server speaks HTTP: start it first and keep it running (${launch.map(shellQuote).join(' ')}${env.length ? ', with ' + env.map((v) => v.name).join(', ') + ' set' : ''}), then add the URL.`,
    );
  }
  const own = fills.filter((f) => f !== INSTALL_FOLDER);
  if (own.length) notes.push(`Replace ${own.join(', ')} with your own path.`);
  if (fills.includes(INSTALL_FOLDER)) notes.push(`Replace ${INSTALL_FOLDER} with the folder you ran the install steps in.`);
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
