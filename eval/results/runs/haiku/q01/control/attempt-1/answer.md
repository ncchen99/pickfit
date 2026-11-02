**Recommendation: mcpup** (`github.com/mohammedsamin/mcpup`). It is a free, MIT-licensed Go CLI that keeps one canonical server list at `~/.mcpup/config.json` and writes into each client's native config. Its client list includes Claude Code and Codex. Its README says "Gemini" without saying Gemini CLI, so confirm that on your first run. It needs no account, and it makes a backup before every write and supports rollback. I couldn't find a last-commit date, and the repo is small (about 24 commits), so treat it as young.

**Fallback: ejfn/mcp-sync**, if mcpup doesn't cover Gemini CLI for you. It reads a Claude-style `mcpServers` file and writes to Claude Code, Gemini CLI, and Codex. Its Codex writer only handles stdio servers. It is run with `uvx --from git+https://github.com/ejfn/mcp-sync mcp-sync -c ~/.claude.json`. I didn't check its backup behavior.

**Install (mcpup, macOS):**
```
brew tap mohammedsamin/tap
brew install mcpup
```
Or, with Go: `go install github.com/mohammedsamin/mcpup/cmd/mcpup@latest`

**First run:**
1. `mcpup setup`, the guided onboarding. It should detect the clients installed on this laptop.
2. `mcpup add <name>` for each server. Add it once to the canonical list.
3. `mcpup enable <name> --client claude-code`, then the same for `codex` and `gemini`. Check `mcpup --help` for the exact client IDs.
4. `mcpup doctor` to check the result.
5. If anything looks wrong, `mcpup rollback --client <client>` restores the backup.

**Before you trust it with your other settings:** back up `~/.codex/config.toml` and `~/.gemini/settings.json` yourself, then diff them after the first sync. I could not confirm from the README that comments and unrelated Codex keys survive a write, so the diff is the check.

I only read READMEs and third-party summaries. I didn't install or run anything.

Sources:
- [mcpup repo](https://github.com/mohammedsamin/mcpup)
- [mcpup listing (mdskills.ai)](https://www.mdskills.ai/mcp-servers/mcpup)
- [ejfn/mcp-sync](https://github.com/ejfn/mcp-sync)
- [EnjoyableWork/mcp-sync](https://github.com/EnjoyableWork/mcp-sync), ruled out because it doesn't support Claude Code or Gemini CLI
- [mcpm (pathintegral-institute)](https://github.com/pathintegral-institute/mcpm.sh/pull/210/files), Gemini and Codex support was only in an open PR when I checked