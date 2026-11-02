I couldn't find a single well-established tool that does exactly this. The closest fit is **sync-agents-settings**. It treats Claude Code's own config as your one list and copies those servers into Gemini CLI and Codex CLI, leaving their other settings alone. I've only read the READMEs and haven't run any of these tools. All of them are small projects with few stars, so skim the code before you let one write to your configs.

**My assumptions:** you want your user-wide configs synced (`~/.claude.json`, `~/.gemini/settings.json`, `~/.codex/config.toml`) rather than per-project files, and you have Node.js installed.

## Main recommendation: sync-agents-settings

[Leoyang183/sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings), MIT license, runs locally, no account.

**Why it fits:**
- You keep adding servers the usual way (`claude mcp add …`), and Claude Code's config becomes the master list.
- It writes Gemini's JSON and Codex's TOML for you. HTTP/SSE servers are converted to a `url` entry for Codex.
- The README says existing settings stay intact (for example, a Gemini theme). It also backs up each file to `~/.sync-agents-backup/<timestamp>/` before writing.
- It has `--dry-run`, `diff` and `doctor` (checks for drift and parse errors), and it skips any agent that isn't installed.

**Limitations:**
- **It only adds servers.** It never overwrites a server that already exists in a target, and the README doesn't document any way to remove servers. If you change or delete a server in Claude Code, you'll still need to fix it by hand in the other two, or try its `reconcile` command, whose exact behaviour I couldn't confirm.
- The README only shows one `--target` per `sync` command.

**Install (needs Node 18+):**
```bash
npm install -g sync-agents-settings
# or run it without installing: npx sync-agents-settings <command>
```

**First run:**
```bash
sync-agents list                         # servers it found in Claude Code
sync-agents diff --target gemini codex   # how the others differ
sync-agents sync --target gemini --dry-run
sync-agents sync --target codex --dry-run
sync-agents sync --target gemini         # write for real (backs up first)
sync-agents sync --target codex
sync-agents doctor --target gemini codex # check for drift or parse errors
```
After that, each time you add a server: `claude mcp add …`, then run the two `sync` commands again.

## Alternatives

| Tool | Why you might pick it | Drawback |
|---|---|---|
| [mcpport](https://github.com/Abdalkaderdev/mcpport) (`npm i -g mcpport`, Node 22+) | Covers Claude Code, Codex, Gemini CLI and Cursor. `sync` only previews unless you add `--apply`. Keeps unrelated keys, and keeps comments in Codex's TOML. Makes timestamped backups. | No separate master file: you sync from one agent to another, e.g. `mcpport sync claude gemini --apply`. 0 stars. |
| [EnjoyableWork/mcp-sync](https://github.com/EnjoyableWork/mcp-sync) (`brew install EnjoyableWork/tap/mcp-sync`) | Has its own master file (`~/.config/mcp-sync/config.json`), keeps other settings, never deletes servers on its own. | Its documented targets are Codex, Claude Desktop, Cursor, Windsurf, VS Code and Kiro. **It doesn't list Claude Code or Gemini CLI.** |
| [mcp-config-manager](https://github.com/holstein13/mcp-config-manager) (Python) | Built for Claude, Gemini and Codex, with enable/disable and backups. | The Codex path in its README is `~/.codex.json`, not `config.toml`, which suggests it's out of date for current Codex. Its installer is `curl \| bash`. It doesn't say whether it keeps other settings. |
| [mcp-sync (Rust)](https://docs.rs/crate/mcp-sync/latest/source/README.md) | Master `mcp.yaml`, `--dry-run`, `--clean` to remove servers that aren't in the master file. | Doesn't support Gemini CLI. |
| [Ruler](https://github.com/intellectronica/ruler) (~3k stars) | The most established tool here. Its `ruler.toml` keeps one MCP list for Claude, Codex and Gemini. | **Per-project only.** It never writes MCP config outside the project folder, so it doesn't fit if you want user-wide settings. |

**Bottom line:** use sync-agents-settings if you're happy for Claude Code to hold the master list. Try mcpport if you'd rather see a preview before every write and want Codex's TOML comments kept. Use Ruler only if you manage MCP servers per project. Whichever you choose, back up the three config files yourself before the first real sync.

Sources:
- [sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings)
- [mcpport](https://github.com/Abdalkaderdev/mcpport)
- [EnjoyableWork/mcp-sync](https://github.com/EnjoyableWork/mcp-sync)
- [holstein13/mcp-config-manager](https://github.com/holstein13/mcp-config-manager)
- [mcp-sync (docs.rs)](https://docs.rs/crate/mcp-sync/latest/source/README.md)
- [intellectronica/ruler](https://github.com/intellectronica/ruler)
- [ejfn/mcp-sync](https://github.com/ejfn/mcp-sync) (appeared in search, but the repo returned 404)