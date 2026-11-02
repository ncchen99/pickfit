I ran nothing on your machine. pickfit, a tool that recommends software it has installed and tested, had no verified match for this, so the suggestions below come from the projects' READMEs. I haven't tested any of them myself.

## Main recommendation: sync-agents-settings (free, MIT licence)

[sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings) is a Node CLI that runs locally and needs no account.

- **The single list is your Claude Code config.** You add MCP servers to Claude Code as usual, then one command writes them into Gemini CLI and Codex CLI. It handles Gemini's `mcpServers` JSON format and Codex's `[mcp_servers.*]` TOML format for you.
- **Other settings:** the README's examples show existing settings kept, and it says it never overwrites servers that already exist. It also copies each config file to `~/.sync-agents-backup/<timestamp>/` before writing.
- **Checking before it writes:** `--dry-run` shows the changes without writing anything. `diff` and `doctor` show where the three configs differ.

**Caveats (from the README, not tested):**
- Because it never overwrites existing servers, changing a server's arguments or environment variables in Claude probably won't reach Codex or Gemini. You'd have to fix those by hand or delete that entry from the other configs and sync again. Removing a server from Claude probably isn't copied over either.
- I'm assuming it reads your user-scope Claude servers in `~/.claude.json`. Check that with `list` first.

### Install
Requires Node.js or npm. Choose one:
```sh
# No install, run each time:
npx sync-agents-settings list

# Or install globally (adds the `sync-agents` command):
npm install -g sync-agents-settings
```
There's also a Claude Code plugin: `claude plugin marketplace add Leoyang183/sync-agents-settings`, then `claude plugin install sync-agents-settings`.

### First run
```sh
sync-agents list                         # see which servers it found in Claude Code
sync-agents diff                         # compare Claude with the Gemini and Codex configs
sync-agents sync --dry-run               # preview the changes; nothing is written
sync-agents sync --target gemini         # try one target first (check the target name in --help)
sync-agents sync                         # sync to all targets (backups are made automatically)
sync-agents doctor                       # confirm nothing has drifted and there are no parse errors
```
After that, adding a server takes two steps: `claude mcp add --scope user <name> -- <command…>`, then `sync-agents sync`.

## Alternatives

- **[mcpshare](https://github.com/eggboy/mcpshare)** is closest to the "one list" you described. It keeps its own `mcp.json` that belongs to no agent and writes it out to Claude Code, Codex and Gemini.
  - Per its README, it keeps the rest of `~/.claude.json`, the non-MCP sections of Codex's TOML file and your other Gemini settings. It skips a file rather than overwrite it if the file is malformed.
  - It has `enable`/`disable` commands for each agent.
  - Downsides: no dry-run mode is documented, no licence is stated, and there are no releases yet.
  - Install with `uv tool install git+https://github.com/eggboy/mcpshare.git`. Then run `mcpshare init`, `mcpshare pull` (imports your existing servers), `mcpshare status` and `mcpshare sync`.
- **[mcp-sync (Rust)](https://docs.rs/crate/mcp-sync/latest/source/README.md)** uses its own `mcp.yaml` and has `--dry-run`, `diff`, `watch` and `--clean`, which removes servers that aren't in the list. However, its README **doesn't list Gemini CLI**, so it doesn't fit what you need.
- **[mcpport](https://github.com/Abdalkaderdev/mcpport)** says it can list, lint, sync and convert configs across Claude Code, Codex and Gemini. I didn't look into it further.

**Summary:** choose sync-agents-settings if you're happy for Claude Code to hold the list and want dry-runs and backups. Choose mcpshare if you want a separate file as the one list and can accept a younger project with no stated licence. With either one, make your own backup of `~/.claude.json`, `~/.codex/config.toml` and `~/.gemini/settings.json` before the first real sync.

Sources:
- [sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings)
- [mcpshare](https://github.com/eggboy/mcpshare)
- [mcp-sync (docs.rs)](https://docs.rs/crate/mcp-sync/latest/source/README.md)
- [mcpport](https://github.com/Abdalkaderdev/mcpport)
- [ejfn/mcp-sync](https://github.com/ejfn/mcp-sync)
- [mcp-config-manager](https://github.com/holstein13/mcp-config-manager)