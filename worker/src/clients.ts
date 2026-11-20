/**
 * How to add an MCP server to each common client (X1): pickfit itself on /agents, and an MCP server pickfit recommends
 * (mcpconfig.ts). Formats are the ones each client's own docs gave on 2026-11-20:
 * - Claude Code: `claude mcp add` (an entry with a url but no type is read as stdio, so the JSON names the type).
 * - Cursor: mcp.json with mcpServers; a remote server is just `url`.
 * - VS Code: `code --add-mcp` with the server as JSON and a `name`.
 * - Claude Desktop: claude_desktop_config.json starts local (stdio) servers only; a remote server is added under
 *   Settings > Connectors > Add custom connector, which needs a public https address.
 * - Codex CLI: a [mcp_servers.<name>] table in ~/.codex/config.toml, `url` for a remote server.
 * - Gemini CLI: `gemini mcp add --transport http`, or settings.json, where streamable HTTP is `httpUrl` (`url` is SSE).
 * Windsurf is left out: its docs moved (Devin Desktop) and did not show the remote key.
 */
import { L } from './i18n.ts';

export type ClientId = 'claude_code' | 'cursor' | 'vscode' | 'claude_desktop' | 'codex' | 'gemini';

export interface ClientSetup {
  client: ClientId;
  /** The client's name as people know it. */
  label: string;
  /** Where the text goes: a terminal, a file, or (Claude Desktop remote) the app's settings. */
  where: string;
  /** What to paste or run; null when the client takes it through its own settings only. */
  text: string | null;
}

export type ServerSpec =
  | { url: string }
  | { command: string; args: string[]; env?: Record<string, string> };

const LABEL: Record<ClientId, string> = {
  claude_code: 'Claude Code',
  cursor: 'Cursor',
  vscode: 'VS Code',
  claude_desktop: 'Claude Desktop',
  codex: 'Codex CLI',
  gemini: 'Gemini CLI',
};

const SAFE_WORD = /^[A-Za-z0-9_@%+=:,./-]+$/;
const sh = (word: string) => (SAFE_WORD.test(word) ? word : `'${word.replace(/'/g, `'\\''`)}'`);
const toml = (text: string) => JSON.stringify(text);
const json = (value: unknown) => JSON.stringify(value, null, 2);

/** Every client's setup for one server. `remotePublic`: a URL the internet can reach (pickfit), not a server the user
 * starts on their own machine; only then can Claude Desktop take it as a connector. */
export function clientSetups(name: string, spec: ServerSpec, remotePublic = false): ClientSetup[] {
  const setups: ClientSetup[] = [];
  const add = (client: ClientId, where: string, text: string | null) => setups.push({ client, label: LABEL[client], where, text });
  if ('url' in spec) {
    add('claude_code', L('In a terminal', '在終端機執行'), `claude mcp add --transport http ${sh(name)} ${sh(spec.url)}`);
    add('cursor', L('In ~/.cursor/mcp.json (or .cursor/mcp.json in a project)', '寫進 ~/.cursor/mcp.json（或專案裡的 .cursor/mcp.json）'), json({ mcpServers: { [name]: { url: spec.url } } }));
    add('vscode', L('In a terminal', '在終端機執行'), `code --add-mcp ${sh(JSON.stringify({ name, type: 'http', url: spec.url }))}`);
    add(
      'claude_desktop',
      remotePublic
        ? L('Settings > Connectors > Add custom connector, then paste this URL', '設定 > Connectors > Add custom connector，貼上這個網址')
        : L('Claude Desktop adds remote servers only as connectors with a public https address, so it cannot reach a server on your machine', 'Claude Desktop 只能把有公開 https 網址的遠端伺服器加成 connector，連不到你電腦上的伺服器'),
      remotePublic ? spec.url : null,
    );
    add('codex', L('In ~/.codex/config.toml', '寫進 ~/.codex/config.toml'), `[mcp_servers.${name}]\nurl = ${toml(spec.url)}`);
    add('gemini', L('In a terminal', '在終端機執行'), `gemini mcp add --transport http -s user ${sh(name)} ${sh(spec.url)}`);
    return setups;
  }
  const env = spec.env && Object.keys(spec.env).length ? spec.env : undefined;
  const server = { command: spec.command, args: spec.args, ...(env ? { env } : {}) };
  const envFlags = env ? Object.entries(env).map(([k, v]) => `-e ${k}=${sh(v)}`) : [];
  add('claude_code', L('In a terminal', '在終端機執行'), ['claude mcp add', sh(name), ...envFlags, '--', sh(spec.command), ...spec.args.map(sh)].join(' '));
  add('cursor', L('In ~/.cursor/mcp.json (or .cursor/mcp.json in a project)', '寫進 ~/.cursor/mcp.json（或專案裡的 .cursor/mcp.json）'), json({ mcpServers: { [name]: server } }));
  add('vscode', L('In a terminal', '在終端機執行'), `code --add-mcp ${sh(JSON.stringify({ name, type: 'stdio', ...server }))}`);
  add('claude_desktop', L('In claude_desktop_config.json (Settings > Developer > Edit Config), then restart the app', '寫進 claude_desktop_config.json（設定 > Developer > Edit Config），再重開應用程式'), json({ mcpServers: { [name]: server } }));
  const tomlEnv = env ? `\nenv = { ${Object.entries(env).map(([k, v]) => `${k} = ${toml(v)}`).join(', ')} }` : '';
  add('codex', L('In ~/.codex/config.toml', '寫進 ~/.codex/config.toml'), `[mcp_servers.${name}]\ncommand = ${toml(spec.command)}\nargs = [${spec.args.map(toml).join(', ')}]${tomlEnv}`);
  add('gemini', L('In ~/.gemini/settings.json', '寫進 ~/.gemini/settings.json'), json({ mcpServers: { [name]: server } }));
  return setups;
}
