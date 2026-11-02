I'd go with **sync-agents-settings** ([GitHub](https://github.com/Leoyang183/sync-agents-settings)). It's free, MIT-licensed, runs locally with no account, and is installed through npm.

I couldn't find a tool that's been tested for this. pickfit's catalogue had nothing that fits, so these picks come from web research and the project READMEs. I haven't installed or run any of them.

## Main pick: sync-agents-settings

**Assumption:** you're fine with Claude Code's own config being your "one list". This tool doesn't keep a separate master file. It reads your Claude Code MCP servers and writes them into Gemini CLI, Codex CLI and about nine other agents. In practice you keep adding servers the way you already do (`claude mcp add …`) and then run one command.

**Why it fits:**
- **Leaves other settings alone.** It writes only the `mcpServers` section of `~/.gemini/settings.json`, so keys like `theme` and `model` stay. In `~/.codex/config.toml` it writes MCP server entries. It handles the format differences for you: JSON vs TOML, and Gemini calling the URL field `httpUrl`.
- **Safe to try.** `--dry-run` shows the changes first. Every real sync backs up the files it touches to `~/.sync-agents-backup/<timestamp>/`.
- **Has checking tools.** `list`, `diff`, and `doctor` show where the configs disagree.

**Limitations:**
- **Sync only adds servers.** It never overwrites a server that already exists in a target. If you change a server's settings in Claude, the change won't reach Gemini or Codex, and the README doesn't say that removing a server in Claude removes it elsewhere either. `diff`/`doctor` will show the mismatch, but for now you'd fix changes and removals by hand.
- **Only some Claude config is read.** It reads `~/.claude.json` and servers from enabled plugins, but not project-level `.mcp.json` files.
- **OAuth servers come across as a bare URL.** You'll need to log in to them again in each CLI.
- **Codex project folders.** If a project has its own `.codex/` folder, Codex ignores the global config there. Use `--codex-home` for that case.
- **Small project.** About 7 stars and 37 commits.

### Install
Needs Node.js 18 or newer.
```bash
npm install -g sync-agents-settings      # gives you the `sync-agents` command
# or skip installing: npx sync-agents-settings <command>
```
It's also available as a Claude Code plugin: `claude plugin marketplace add Leoyang183/sync-agents-settings`, then `claude plugin install sync-agents-settings`.

### First run
```bash
sync-agents list                              # check it sees your Claude Code servers
sync-agents diff                              # compare Claude with the other agents
sync-agents sync --target gemini --dry-run    # preview the changes, writes nothing
sync-agents sync --target codex  --dry-run
sync-agents sync --target gemini              # apply (backs up first)
sync-agents sync --target codex
```
After that, whenever you add a server: `claude mcp add …`, then `sync-agents sync`. To check later: `sync-agents doctor`.

## Alternatives
- **mcpshare** ([GitHub](https://github.com/eggboy/mcpshare)) keeps a real standalone master `mcp.json` and writes it to Claude Code, Codex, Gemini CLI and others. It replaces only the MCP section of each file and leaves everything else, including the other state in `~/.claude.json`. That should mean edits and removals carry over, which the main pick can't do. The catch: it has no stars, no releases and no dry-run or backup that I could find, so back up your three config files yourself first. Install with `uv tool install git+https://github.com/eggboy/mcpshare.git`, then `mcpshare init` → `mcpshare pull` → `mcpshare sync`. You'll probably need to set `init-source` in `~/.config/mcpshare/config.yaml` so `pull` reads from Claude; by default it reads from VS Code and Copilot.
- **mcpport** ([GitHub](https://github.com/Abdalkaderdev/mcpport)) is the most cautious about writing files. Nothing is written unless you pass `--apply`, it saves a `.bak` copy before every write, keeps comments in TOML files, and won't rewrite a JSON file that contains comments. It copies one config to another (`npx mcpport sync <from> <to>`) rather than keeping a single list. Needs Node 22+. It's very new (14 commits).

Other projects exist but don't cover your three CLIs: [mcp-sync](https://docs.rs/crate/mcp-sync/latest/source/README.md) has no Gemini CLI support, and [agentsync](https://github.com/spyrae/agentsync) doesn't list Gemini. All of these are small, young projects, so the dry run and backups are worth using the first time.

Sources: [sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings), [mcpshare](https://github.com/eggboy/mcpshare), [mcpport](https://github.com/Abdalkaderdev/mcpport), [mcp-sync](https://docs.rs/crate/mcp-sync/latest/source/README.md), [agentsync](https://github.com/spyrae/agentsync), [mcp-config-manager](https://github.com/holstein13/mcp-config-manager), [InventiveHQ guide on MCP config locations](https://inventivehq.com/blog/add-mcp-server-to-ai-coding-cli)