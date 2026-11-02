**Main recommendation: `sync-agents-settings` (MIT, npm package, no account).** It's the only candidate I could check against its own docs. Claude Code is the source of truth, and it writes the same servers into Gemini CLI and Codex CLI. pickfit returned no matching picks for this request, so this comes from web research, not pickfit's sandbox testing.

**What it does, and what it doesn't**
- You keep your list in Claude Code's config (`~/.claude.json`, under `mcpServers`), not in a separate file. Claude is the source, so you add servers there and sync from it.
- Targets: `~/.gemini/settings.json` (under `mcpServers`) and `~/.codex/config.toml`.
- It backs up the target files to `~/.sync-agents-backup/<timestamp>/` before writing, and `--dry-run` previews changes without writing.
- Existing server entries are never overwritten, so re-running is safe.
- Limits: OAuth servers such as Slack sync as URL-only and need manual auth in each CLI. `${CLAUDE_PLUGIN_ROOT}` doesn't resolve outside Claude. Codex doesn't support `${VAR:-default}`, so the tool expands it at sync time.
- Your "leave other settings alone" requirement is confirmed for Gemini. The docs don't say this for Codex, so check your `config.toml` after the first real run.
- The docs don't show a last-commit date, and it has only 37 commits. Read the code before pointing it at your real configs.

**Install (not run; you approve each step)**
1. Try it without installing: `npx sync-agents-settings list`
2. Optional global install: `npm install -g sync-agents-settings`, then run `sync-agents`. This needs Node/npm.
3. Alternatively, install it as a Claude Code plugin: `claude plugin marketplace add Leoyang183/sync-agents-settings`, then `claude plugin install sync-agents-settings`.

**First run**
1. Back up `~/.codex/config.toml` and `~/.gemini/settings.json` yourself, in addition to the tool's backups.
2. Run a preview with `--dry-run` and read the output. I didn't confirm the exact sync flags, so check `sync-agents --help` first.
3. Run the sync for real, then open each config to confirm your other settings are intact.
4. Add a test server, sync again, and check it appears in all three CLIs.

**Other options I found but did not verify**
- `ejfn/mcp-sync` (Python) looked like a close fit in search snippets. Its GitHub page returned 404, so I couldn't confirm it exists or its status. Skip it unless you find a live repo.
- `levnikolaevich/ln-004-agent-sync` is a Claude Code skill that also merges MCP config into Codex. It doesn't cover Gemini in the snippet I saw.
- `jnk234/mcp-multiverse` covers Claude Code and Gemini CLI. The snippet didn't mention Codex CLI.

Sources:
- [Leoyang183/sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings) (fetched; install, targets, backup, limits)
- [mcp sync (ejfn)](https://github.com/ejfn/mcp-sync) (search result only; page returned 404)
- [ln-004 agent sync](https://skills.cat/skills/levnikolaevich/claude-code-skills/ln-004-agent-sync) (search result)
- [jnk234 mcp multiverse](https://lobehub.com/mcp/jnk234-mcp-multiverse) (search result)