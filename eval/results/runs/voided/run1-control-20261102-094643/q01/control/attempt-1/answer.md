I recommend **cc-switch-cli**, with **sync-agents-settings** as the more cautious alternative. I only researched this and didn't run anything on your machine.

## Main pick: cc-switch-cli

[cc-switch-cli](https://github.com/SaladDay/cc-switch-cli) is free (MIT), runs locally, and supports Claude Code, Codex CLI and Gemini CLI. It keeps one MCP list in its own local database (`~/.cc-switch/cc-switch.db`). For each server you choose which agents get it, and one command writes that into:
- `~/.claude.json`
- `~/.codex/config.toml` (TOML)
- `~/.gemini/settings.json`

It handles the format differences for you. No account is needed: ChatGPT sign-in and WebDAV sync are optional. It's also the most widely used option I found (about 5.4k stars, Homebrew package).

**The catch:** Its README doesn't explicitly say it leaves the rest of those files alone. It does say it writes files safely (temp file, then rename) and has a backup/restore command. The tool also switches API providers, which is a separate feature. If you don't use that feature, it should only touch MCP entries, but check that yourself on the first run (step 3 below).

### Install and first run
1. **Install:** `brew install cc-switch-cli`, or use the `install.sh` script or a release binary from the repo.
2. **Back up the three config files yourself**, since I couldn't confirm it backs them up automatically before an MCP sync:
   `cp ~/.claude.json ~/.claude.json.bak; cp ~/.codex/config.toml ~/.codex/config.toml.bak; cp ~/.gemini/settings.json ~/.gemini/settings.json.bak`
3. **Import, assign and sync:**
   - `cc-switch mcp import --app claude` copies your existing Claude Code servers into the shared list. The docs show `--app claude`; I'm assuming `codex` and `gemini` also work.
   - `cc-switch mcp list` shows the IDs.
   - `cc-switch mcp enable <id> --app codex` and `cc-switch mcp enable <id> --app gemini` choose which agents get each server.
   - `cc-switch mcp sync` writes the files.
   - Run `diff ~/.codex/config.toml.bak ~/.codex/config.toml` (and the same for the other two files). Only the MCP sections should have changed.
4. **From then on:** `cc-switch mcp add` (interactive), then `enable … --app …`, then `cc-switch mcp sync`. You never edit the three files by hand.

## Alternative if keeping your other settings safe matters most: sync-agents-settings

[sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings) treats your Claude Code config as the master list: you add servers with `claude mcp add`, as you do now. It then copies them into Codex and Gemini.

**What it documents that cc-switch-cli doesn't:**
- It keeps unrelated settings.
- It backs up files automatically to `~/.sync-agents-backup/<timestamp>/`.
- It has a `--dry-run` preview.

**Downsides:**
- It's a small project (about 7 stars).
- It doesn't overwrite servers that already exist in Codex or Gemini, so editing a server in Claude won't update the copies.
- It doesn't say whether it removes servers you deleted in Claude.

**Install and run:** `npm i -g sync-agents-settings` (or use `npx sync-agents-settings`), then `sync-agents sync --dry-run`, then `sync-agents sync`.

## Ruled out
- **[Ruler](https://app.unpkg.com/@intellectronica/ruler@0.3.10/files/README.md):** only writes config inside a project folder, never your home-directory configs.
- **[vsync](https://github.com/nicepkg/vsync)** and the Rust **[mcp-sync](https://docs.rs/crate/mcp-sync/latest/source/README.md):** no Gemini CLI support listed.
- **[EnjoyableWork mcp-sync](https://github.com/EnjoyableWork/mcp-sync):** has a good single-list design and promises to keep your other settings, but doesn't list Claude Code or Gemini CLI.
- **[mcpport](https://github.com/Abdalkaderdev/mcpport):** keeps other settings, previews by default and makes backups, but copies from one agent to another (`sync <from> <to>`) instead of keeping one list. It also has no users yet (0 stars).
- **[mcp-config-manager](https://github.com/holstein13/mcp-config-manager):** lists Codex at `~/.codex.json`, not the real `~/.codex/config.toml`.

Whichever you pick, remote servers and environment variables are written differently in each agent (Gemini uses `httpUrl`, for example). After the first sync, open each agent and confirm the servers load.

Sources: [cc-switch-cli](https://github.com/SaladDay/cc-switch-cli) · [sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings) · [mcpport](https://github.com/Abdalkaderdev/mcpport) · [EnjoyableWork mcp-sync](https://github.com/EnjoyableWork/mcp-sync) · [mcp-sync crate](https://docs.rs/crate/mcp-sync/latest/source/README.md) · [ejfn mcp-sync](https://github.com/ejfn/mcp-sync) · [mcp-config-manager](https://github.com/holstein13/mcp-config-manager) · [Ruler README](https://app.unpkg.com/@intellectronica/ruler@0.3.10/files/README.md) · [vsync](https://github.com/nicepkg/vsync) · [Codex config management article](https://codex.danielvaughan.com/2026/03/30/codex-cli-config-management-multi-tool/) · [InventiveHQ MCP guide](https://inventivehq.com/blog/add-mcp-server-to-ai-coding-cli)