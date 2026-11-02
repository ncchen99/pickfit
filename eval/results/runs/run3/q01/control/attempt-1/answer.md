I recommend **sync-agents-settings**, which is free and MIT-licensed. It doesn't keep a separate master file. It treats your **Claude Code** MCP config as the one list and syncs it into **Codex CLI** (`~/.codex/config.toml`) and **Gemini CLI** (`~/.gemini/settings.json`). In practice you add a server once with `claude mcp add …` and then run one sync command. According to its README, it:

- runs locally with Node and needs no account
- keeps the other settings already in the target files
- backs up each file it changes to `~/.sync-agents-backup/<timestamp>/` before writing
- has a `--dry-run` preview, plus `diff`, `doctor` and `reconcile` commands

I'm assuming you mainly use servers at the user level (available in every project), not per-project `.mcp.json` files. I haven't tested this tool or any of the others below; these details come from their READMEs.

## Install and first run

You need Node.js and npm.

```bash
# Option A: try it without installing anything
npx sync-agents-settings list              # read-only: shows the servers it found in Claude Code
npx sync-agents-settings sync --dry-run    # preview what would change in Codex and Gemini
npx sync-agents-settings sync              # write the changes (backups are made first)

# Option B: install it globally
npm install -g sync-agents-settings
sync-agents list
sync-agents sync --dry-run
sync-agents sync
```

You can also install it as a Claude Code plugin, which adds a `/sync` slash command that shows a preview first:
```bash
claude plugin marketplace add Leoyang183/sync-agents-settings
claude plugin install sync-agents-settings
```

**Day-to-day use:** `claude mcp add <name> -- <command> …` adds the server, then `sync-agents sync` copies it to the other two.

**Before the first real sync:**
1. Make your own copies of `~/.claude.json`, `~/.codex/config.toml` and `~/.gemini/settings.json`.
2. Look over the `--dry-run` output. Pay attention to API keys and tokens in `env` and `headers`, because the sync copies them into the other files.
3. The README says it **never overwrites servers that already exist** in a target. If you later change a server's arguments in Claude Code, a plain `sync` may skip that server. Check `diff` or `reconcile` for those cases.
4. It's a small project (about 7 stars). Read the source or pin a version instead of running the latest from `npx` every time.

## Alternatives

| Tool | Best if… | Notes |
|---|---|---|
| **[mcpport](https://github.com/Abdalkaderdev/mcpport)** (`npm i -g mcpport`) | You want the most careful writes | `sync` only previews unless you add `--apply`. It keeps Codex TOML comments and unrelated tables, and it won't rewrite Gemini settings files that contain comments. It copies between agents (e.g. `mcpport sync claude gemini --apply`) instead of keeping a master list. Very new, 0 stars. |
| **[mcp-sync (EnjoyableWork)](https://github.com/EnjoyableWork/mcp-sync)** (`brew install EnjoyableWork/tap/mcp-sync`) | You want a real standalone master file | Keeps the list in `~/.config/mcp-sync/config.json`, keeps other settings, and has dry-run and restore. **Its README doesn't list Claude Code or Gemini CLI as targets**, so today it only covers Codex for you. |
| **[mcp-sync (Rust crate)](https://docs.rs/crate/mcp-sync/latest/source/README.md)** | You want one master `mcp.yaml` | Supports Claude Code and Codex, but **not Gemini CLI**. |
| **[Ruler](https://github.com/intellectronica/ruler)** (`npm i -g @intellectronica/ruler`) | Your servers are per project | Writes one `.ruler/ruler.toml` out to all three agents, but **only inside the project folder**, never to your user-level configs. Well established. |
| **mcpm.sh** | — | A [PR adds Codex and Gemini CLI support](https://github.com/pathintegral-institute/mcpm.sh/pull/210/files), but I couldn't confirm it was merged. Check before relying on it. |
| [mcp-config-manager](https://github.com/holstein13/mcp-config-manager) | — | Its README gives the wrong Codex config path (`~/.codex.json`), so I'd skip it. |

None of these is a widely used, mature project yet. sync-agents-settings is the one that covers all three of your agents at the user level and is set up for this exact workflow.

Sources:
- [sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings)
- [mcpport](https://github.com/Abdalkaderdev/mcpport)
- [mcp-sync (EnjoyableWork)](https://github.com/EnjoyableWork/mcp-sync)
- [mcp-sync Rust crate README](https://docs.rs/crate/mcp-sync/latest/source/README.md)
- [Ruler](https://github.com/intellectronica/ruler)
- [mcp-config-manager](https://github.com/holstein13/mcp-config-manager)
- [mcpm.sh PR #210](https://github.com/pathintegral-institute/mcpm.sh/pull/210/files)
- [PyPI mcp-sync](https://pypi.org/project/mcp-sync/)
- [inventivehq: adding MCP servers to AI CLIs](https://inventivehq.com/blog/add-mcp-server-to-ai-coding-cli)