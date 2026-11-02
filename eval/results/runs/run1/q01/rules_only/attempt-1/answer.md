I'd go with **mcpshare**. It's the only tool I found that keeps a separate master list of your MCP servers and pushes it into Claude Code, Codex CLI and Gemini CLI. Most similar tools treat Claude Code's own config as the master copy instead.

I'm assuming you're on macOS (that's what this machine reports) and that you want your global, user-level configs synced rather than per-project ones. I haven't installed or tested any of these tools; everything below comes from their READMEs. pickfit, the tool-recommendation service I checked first, had no tested tool for this job.

## Recommendation: mcpshare

**Why it fits:**
- **One list:** your servers live in a single `mcp.json` file in a folder you choose. `mcpshare sync` converts that list into each agent's format: `~/.claude.json` for Claude Code, `~/.codex/config.toml` (TOML) for Codex, and `~/.gemini/settings.json` for Gemini. It also supports VS Code, Copilot CLI, Antigravity and OpenCode.
- **Leaves your other settings alone:** it replaces only the MCP servers section of each file. Other keys and non-MCP sections of Codex's TOML file stay as they are. If a config file is broken, it skips that file instead of overwriting it.
- **Local, free, no account:** it's a Python CLI that only edits files on your machine.
- **Bonus:** you can turn a server off for one agent only (`enable` / `disable`).

**Caveats:**
- The README doesn't mention a dry-run mode or automatic backups, so make your own backup before the first sync.
- The repo page doesn't show a license, and it's a small community project.

### Install
You need `uv`. If you don't have it, run `brew install uv`.
```bash
uv tool install git+https://github.com/eggboy/mcpshare.git
```

### First run
```bash
# 0. Back up your current configs (mcpshare doesn't mention backups)
cp ~/.claude.json ~/.claude.json.bak
cp ~/.codex/config.toml ~/.codex/config.toml.bak
cp ~/.gemini/settings.json ~/.gemini/settings.json.bak

# 1. Create ~/.config/mcpshare/config.yaml and the folder for your master list
mcpshare init

# 2. Edit ~/.config/mcpshare/config.yaml: set `source` (where the master mcp.json lives),
#    `init-source` (which agents to collect servers from) and your targets
#    (Claude Code, Codex, Gemini CLI)

# 3. Copy the servers you already have into the master mcp.json (doesn't change the agents' configs)
mcpshare pull

# 4. Check the master list and the targets
mcpshare status

# 5. Write the list to all three agents
mcpshare sync
```
After that, to add a server: put it in the master `mcp.json` and run `mcpshare sync`. To check the result, run `claude mcp list` and `codex mcp list`, and `/mcp` inside Gemini CLI.

## Alternatives
- **[mcpport](https://github.com/Abdalkaderdev/mcpport)** (MIT, `npm i -g mcpport`, needs Node 22+): the most careful about writing files. It previews changes unless you pass `--apply`, makes a timestamped `.bak` before each write, keeps comments in Codex's TOML, and won't rewrite a Gemini file that has comments. But it copies between agents (e.g. `mcpport sync claude codex --apply`) rather than keeping one master list. It's also brand new (0 stars). Even if you use mcpshare, it's handy for checking configs and spotting differences.
- **[sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings)** (MIT, `npx sync-agents-settings`): treats Claude Code as the master copy and syncs to Gemini and Codex. It has `--dry-run`, automatic backups, and `diff` / `reconcile` commands. One catch: it never overwrites a server that already exists in a target, so if you change a server's settings, the change won't reach the other agents on its own.
- **[agentsync](https://github.com/spyrae/agentsync)** (MIT, `pipx install agentsync-cli`): also uses Claude Code as the master. It doesn't list a Gemini CLI adapter (only Antigravity), so it's not a good fit here.

Sources:
- [eggboy/mcpshare](https://github.com/eggboy/mcpshare)
- [Abdalkaderdev/mcpport](https://github.com/Abdalkaderdev/mcpport)
- [Leoyang183/sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings)
- [spyrae/agentsync](https://github.com/spyrae/agentsync)
- [holstein13/mcp-config-manager](https://github.com/holstein13/mcp-config-manager)
- [EnjoyableWork/mcp-sync](https://github.com/EnjoyableWork/mcp-sync)