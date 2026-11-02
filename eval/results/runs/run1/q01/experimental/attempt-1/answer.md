I recommend **mcpshare**. It's free and open source, runs locally with no account, and supports Claude Code, Codex CLI and Gemini CLI. It's the closest match to what you asked for: you keep one master list of MCP servers, and `mcpshare sync` writes it into each agent's config in that agent's own format. According to its README, it replaces only the MCP section of each file, so your other settings stay. That includes Claude's state in `~/.claude.json`, Gemini's other settings, and the non-MCP sections of Codex's TOML file. It skips config files it can't parse instead of overwriting them.

**Things to know before you use it**
- pickfit, the tool-recommendation service I checked, had tested none of these tools. My information comes from a web search and each project's README. I haven't run any of them.
- mcpshare is a small, young project: about 19 commits, no tagged releases, and no license shown on its GitHub page. It has **no dry-run or backup option**, so back up your configs before your first sync.
- It has no `add` command. To add a server, you edit the master `mcp.json` file and then run `sync`.

## Install (macOS)
It's a Python tool installed with `uv`. I'm assuming you have Homebrew.
```bash
brew install uv                                            # skip if you already have uv
uv tool install git+https://github.com/eggboy/mcpshare.git
mcpshare --help                                            # check that it installed
```
Upgrade later with `uv tool upgrade mcpshare`.

## First run
1. **Back up your current configs:**
   ```bash
   mkdir -p ~/mcp-backup
   cp ~/.claude.json ~/.gemini/settings.json ~/.codex/config.toml ~/mcp-backup/
   ```
2. **Create mcpshare's config:** `mcpshare init` creates `~/.config/mcpshare/config.yaml` and the folder for the master list.
3. **Edit `config.yaml`.** By default it imports existing servers from VS Code and Copilot, so point it at the agents you use instead. The README names the keys `source`, `init-source`, `mode` and `targets`, with a `path` for each target. I'm guessing at the exact layout, so compare it with the file `init` creates:
   ```yaml
   init-source: [claude]        # import your existing servers from Claude Code
   targets:
     claude: { path: ~/.claude }
     codex:  { path: ~/.codex }
     gemini: { path: ~/.gemini }
   ```
4. **Import your current servers:** `mcpshare pull` copies them into the master `mcp.json` and doesn't write to any agent's config.
5. **Check before writing:** `mcpshare status` shows the master servers, the targets and any disabled servers.
6. **Sync:** `mcpshare sync`. Then compare each file with your backup, for example `diff ~/mcp-backup/config.toml ~/.codex/config.toml`, to confirm only the MCP sections changed.
7. **From now on:** add the server to the master `mcp.json` and run `mcpshare sync`. To turn a server off for one agent, use `mcpshare disable --servers <name> --ide gemini`.

## Other options
- **mcpport** (MIT license, needs Node 22+) has the safety features mcpshare lacks. Sync is a dry run unless you add `--apply`, it makes a timestamped `.bak` copy before every write, and it keeps comments and unrelated settings. It has no master list, though: you use one agent (say Claude Code) as the source and copy from it. For example, run `npx mcpport sync claude codex`, check the output, then run it again with `--apply`, and do the same for `gemini`. One catch: if your Gemini `settings.json` contains comments, mcpport reads it but never writes to it. Choose mcpport over mcpshare if you'd rather have dry runs and backups than a separate master list.
- **sync-agents-settings** also syncs from Claude Code to Gemini and Codex, and has `diff` and `doctor` commands. I didn't read its documentation closely.

Sources:
- [eggboy/mcpshare](https://github.com/eggboy/mcpshare)
- [Abdalkaderdev/mcpport](https://github.com/Abdalkaderdev/mcpport)
- [Leoyang183/sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings)
- [holstein13/mcp-config-manager](https://github.com/holstein13/mcp-config-manager)
- [EnjoyableWork/mcp-sync](https://github.com/EnjoyableWork/mcp-sync)