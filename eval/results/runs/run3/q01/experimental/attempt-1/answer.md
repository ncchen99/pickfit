I recommend **sync-agents-settings**. I didn't install or test any of these tools. I read their READMEs, and pickfit's tested catalog had nothing for this job. I'm assuming you're on macOS with Node.js 18 or newer, and that you add servers with `claude mcp add` already.

## Main pick: sync-agents-settings

It's free (MIT), runs locally with no account, and you can run it from the terminal or inside Claude Code. It doesn't use a separate master file. Your Claude Code config (`~/.claude.json`) is the one list, and the tool copies its MCP servers into:
- Gemini CLI: `~/.gemini/settings.json`, under `mcpServers`
- Codex CLI: `~/.codex/config.toml`

It also supports Cursor, OpenCode, Qwen Code and others, if you add more agents later.

**How it fits what you asked for:**
- **Leaves your other settings alone:** the README's examples show existing settings like theme and model kept next to the synced servers.
- **Safe to test:** `--dry-run` previews the changes, and it backs up each config to `~/.sync-agents-backup/<timestamp>/` before writing.
- **Doesn't create configs:** if one agent's config folder doesn't exist, it skips that agent.

**Main limitation:** it only adds servers that are missing. It never overwrites a server entry that's already in a target, and the README doesn't say it handles removals. So if you change or delete a server in Claude Code, you still have to edit the Gemini and Codex configs by hand.

### Install
```bash
npm install -g sync-agents-settings
```
To try it without installing, use `npx sync-agents-settings list`. You can also install it as a Claude Code plugin, which gives you `/sync`, `/sync-diff` and similar commands:
```bash
claude plugin marketplace add Leoyang183/sync-agents-settings
claude plugin install sync-agents-settings
```

### First run
```bash
sync-agents list                          # show the MCP servers it found in Claude Code
sync-agents diff --target gemini codex    # compare Claude with the other two
sync-agents sync --target gemini --dry-run
sync-agents sync --target codex --dry-run
# if the previews look right:
sync-agents sync --target gemini
sync-agents sync --target codex
```
After that, adding a server looks like this: `claude mcp add …`, then `sync-agents sync --target gemini` and `sync-agents sync --target codex`. To catch drift or parse errors later, run `sync-agents doctor --target gemini codex`.

## Alternatives

- **[mcpport](https://github.com/Abdalkaderdev/mcpport)** (MIT, needs Node 22 or newer): supports Claude Code, Codex, Gemini CLI and Cursor. Usage is `npx mcpport sync <from> <to>`, which is a dry run until you add `--apply`. It backs up each file to `<file>.<timestamp>.bak` before writing and won't write to a file it can't parse. When it writes JSON it keeps keys unrelated to MCP, and when it writes Codex's TOML it keeps your comments and other tables. One catch: it drops server options the target agent doesn't understand, and it lists what it dropped. It copies from one agent to another and has no master file. Try it if you need changes to existing servers carried over, but I couldn't confirm from the README whether it does that.
- **[mcp-sync (Rust)](https://docs.rs/crate/mcp-sync/latest/source/README.md)** (MIT): this one does use a single `mcp.yaml` file as the master list, and it has `--dry-run`, backups and a `watch` mode. But its README lists Claude Code, Codex, OpenCode and Antigravity, **not Gemini CLI**, so it doesn't cover all three of your agents.
- **[mcp-config-manager](https://github.com/holstein13/mcp-config-manager)**: has a sync mode for Claude, Gemini and Codex. But its README gives the Codex config path as `~/.codex.json`, while Codex actually uses `~/.codex/config.toml`. I'd avoid it unless that's been fixed.

I didn't check how actively any of these projects are maintained. Run the dry run before your first real sync either way.

Sources:
- [sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings)
- [mcpport](https://github.com/Abdalkaderdev/mcpport)
- [mcp-sync (Rust crate README)](https://docs.rs/crate/mcp-sync/latest/source/README.md)
- [mcp-sync (EnjoyableWork)](https://github.com/EnjoyableWork/mcp-sync)
- [mcp-sync (PyPI)](https://pypi.org/project/mcp-sync/)
- [mcp-config-manager](https://github.com/holstein13/mcp-config-manager)
- [How to add an MCP server to any AI coding CLI](https://inventivehq.com/blog/add-mcp-server-to-ai-coding-cli)