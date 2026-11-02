My recommendation is **mcpport**, a free MIT-licensed CLI that runs locally on Node and needs no account. It's the only tool I found that handles all three of your agents at the user level and makes a point of leaving your other settings alone.

One thing to know up front: mcpport doesn't keep its own master file. It reads each agent's own config, compares them, and copies servers from one agent to the others in the right format. So I'm assuming you'll treat **Claude Code's user config as your one list**. You add servers there and mcpport copies them to Codex and Gemini.

## Why mcpport fits

- **Covers all three:** `~/.claude.json`, `~/.codex/config.toml` (TOML) and `~/.gemini/settings.json`. Cursor too, if you ever need it.
- **Leaves other settings alone:** unrelated JSON keys are kept, and Codex TOML comments and other tables are kept. It won't rewrite a Gemini `settings.json` that contains comments, because that would lose them. If a file can't be parsed, it isn't written.
- **Safe by default:** `sync` only shows what it would do until you add `--apply`. Before writing, it backs up the file to `<file>.<timestamp>.bak` and writes atomically. Servers that conflict are skipped unless you pass `--force`. Secrets are hidden in its output.

**Main caveat:** the project is very new and small, with about 14 commits, 0 stars and no tagged releases. Keep the dry run and backups in your routine for now.

## Install

Requires **Node 22 or newer**. Check with `node -v`.

```bash
npm i -g mcpport        # or run it without installing: npx mcpport <command>
```

## First run

1. **See what you have now.** These two commands only read files:
   ```bash
   mcpport list        # every server, which agents have it, and whether the copies differ
   mcpport lint        # problems in the existing configs
   ```
2. **Make Claude Code the master list.** Add new servers at **user** scope:
   ```bash
   claude mcp add --scope user <name> -- <command> <args...>
   ```
   mcpport treats Claude's default "local" (per-project) scope as read-only, so servers added without `--scope user` won't be copied.
3. **Preview the copy.** I'm assuming the syntax is `sync <from> <to>`, based on the README's `sync claude cursor` example:
   ```bash
   mcpport sync claude codex
   mcpport sync claude gemini
   ```
4. **Write the changes** once the preview looks right:
   ```bash
   mcpport sync claude codex --apply
   mcpport sync claude gemini --apply
   ```
   Only add `--force` when you've changed a server's settings in Claude and want that version to replace the other copies.
5. **Check:** run `mcpport list` again. The servers should show in all three agents with no differences. Your backups sit next to each file as `*.bak`.

After that, adding a server takes three commands: `claude mcp add --scope user …` and then the two `sync … --apply` commands. A small shell alias can run all three.

## Alternatives

- **sync-agents-settings** (`npm i -g sync-agents-settings`, then `sync-agents sync --dry-run`, then `sync-agents sync`). It also uses Claude Code as the source and covers Gemini, Codex and about 10 other agents. It backs up to `~/.sync-agents-backup/`. It has more activity (7 stars, 37 commits), but **it never overwrites servers that already exist**, so later edits to a server won't be copied over. Its docs also don't say whether Codex TOML comments are kept.
- **mcp-sync** (Rust) does keep a real master file (`mcp.yaml`), and supports dry runs, backups and removing servers that aren't in the master. But it **doesn't support Gemini CLI**, and you have to build it from source.
- **Ruler** (about 3k stars) is popular but **only writes project-level** MCP files, never user-level ones. It also generates instruction files like `AGENTS.md` and `CLAUDE.md`. It doesn't fit what you're after.

I took these details from each project's README and haven't tested the tools myself.

Sources:
- [mcpport](https://github.com/Abdalkaderdev/mcpport)
- [sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings)
- [mcp-sync (Rust) README](https://docs.rs/crate/mcp-sync/latest/source/README.md)
- [mcp-sync (EnjoyableWork)](https://github.com/EnjoyableWork/mcp-sync)
- [mcp-sync on PyPI](https://pypi.org/project/mcp-sync/)
- [mcp-config-manager](https://github.com/holstein13/mcp-config-manager)
- [Ruler](https://github.com/intellectronica/ruler)
- [mcpm.sh](https://github.com/lox/mcpm.sh)
- [InventiveHQ: adding MCP servers to AI coding CLIs](https://inventivehq.com/blog/add-mcp-server-to-ai-coding-cli)