I found one tool that fits your workflow well: **cc-switch-cli**. It keeps one list of MCP servers, and `cc-switch mcp sync` writes it into the real user-level config files for all three agents. Its README doesn't explicitly confirm two of your requirements, though: that adding or syncing makes no network calls, and that it keeps your other settings in those files. The same is true of every other candidate I found. I only read READMEs, not source code.

## Candidates checked

**1. cc-switch-cli** — https://github.com/SaladDay/cc-switch-cli (best fit)
- **Command line, runs locally:** yes. It's a CLI/TUI with `cc-switch mcp list/add/edit/delete/enable/disable/sync/import`.
- **All three agents:** yes. It syncs one MCP list into `~/.claude.json` (Claude Code), `~/.codex/config.toml` (Codex) and `~/.gemini/settings.json` (Gemini), and you can turn servers on or off per agent with `--app`.
- **Free, no account:** MIT license. The README doesn't say MCP features need an account; the ChatGPT/Codex sign-in is a separate, optional feature.
- **No network while adding or syncing:** not documented. The tool does have network features (provider speed tests, skill update checks, `cc-switch update`), but the README doesn't link any of them to the MCP commands.
- **Keeps other settings:** not explicitly stated. It mentions safe "atomic" file writes and adapters for the TOML and JSON formats.

**2. Ruler** — https://github.com/intellectronica/ruler (runner-up)
- **Command line, runs locally:** yes, via `npm i -g @intellectronica/ruler`.
- **All three agents:** yes, but only per project. It writes `.mcp.json`, `.codex/config.toml` and `.gemini/settings.json`, and "never writes MCP configuration files outside your project root." For Codex you also have to set `CODEX_HOME` to the project's `.codex` folder. That doesn't match your one-list-for-the-whole-laptop setup.
- **Free, no account:** MIT, and no account is mentioned.
- **No network:** not stated for MCP. It only says it makes no network requests in a separate feature.
- **Keeps other settings:** merging is the default and it makes `.bak` backups, but the README doesn't say whether unrelated keys survive.

**3. agentsync** — https://github.com/dallay/agentsync
- **All three agents:** yes, but project-level files only (`.mcp.json`, `.codex/config.toml`, `.gemini/settings.json`).
- **Free, no account:** MIT, and no account is mentioned.
- **Keeps other settings:** by default it merges servers and keeps ones it didn't create. It doesn't say what happens to settings that aren't servers.
- **No network:** not documented, and it depends on an HTTP library (`reqwest`) without explaining why.

**4. sync-agents-settings** — https://github.com/Leoyang183/sync-agents-settings
- **All three agents:** fails. Claude Code is the source; it writes to Codex and Gemini but never writes MCP entries to Claude Code.
- It is MIT-licensed and its examples show existing settings kept, so it's a reasonable choice if you're happy to add servers with `claude mcp add` and copy them out from there.

**5. EnjoyableWork/mcp-sync** — https://github.com/EnjoyableWork/mcp-sync
- **All three agents:** fails, because neither Claude Code nor Gemini CLI is supported. This is a pity, since it's the only one that explicitly says other settings and comments survive a sync.

**6. ejfn/mcp-sync** (Python)
- **All three agents:** fails, because it only targets Claude Code and Gemini, with no evidence of Codex. Its GitHub page also returned 404.

**7. agentlink** (npm, v0.1.0)
- **All three agents:** fails in practice. It writes to the wrong files (`~/.claude/mcp.json`, `~/.gemini/mcp_servers.json`, `~/.codex/mcp.json`) instead of the ones each agent actually reads.

**8. mcpsync-cli** (npm)
- Couldn't verify: the npm page returned 403, and it only has claude/gemini/codex tags.

To check the two open points on cc-switch-cli, point `HOME` at a test folder with copies of your three config files, run `cc-switch mcp sync` with networking off, and compare the files before and after.

FOUND: cc-switch-cli https://github.com/SaladDay/cc-switch-cli

Sources:
- [SaladDay/cc-switch-cli](https://github.com/SaladDay/cc-switch-cli)
- [intellectronica/ruler](https://github.com/intellectronica/ruler)
- [agentsync on docs.rs](https://docs.rs/crate/agentsync/1.27.2) / [dallay/agentsync](https://github.com/dallay/agentsync)
- [Leoyang183/sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings)
- [EnjoyableWork/mcp-sync](https://github.com/EnjoyableWork/mcp-sync)
- [ejfn/mcp-sync](https://github.com/ejfn/mcp-sync), [pypi mcp-sync](https://pypi.org/project/mcp-sync/)
- [agentlink on pkgstats](https://www.pkgstats.com/pkg:@digimetalab/agentlink)
- [mcpsync-cli maintainers listing](https://packages.ecosyste.ms/registries/npmjs.org/packages/mcpsync-cli/maintainers)
- [holstein13/mcp-config-manager](https://github.com/holstein13/mcp-config-manager)