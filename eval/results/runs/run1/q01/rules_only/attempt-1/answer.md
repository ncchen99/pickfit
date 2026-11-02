## My recommendation: **sync-agents-settings** (free, MIT, local, no account)

It fits your setup best: you keep adding servers in Claude Code the usual way (`claude mcp add …`), and the tool copies them into Codex CLI's TOML and Gemini CLI's JSON. It also has the safety features you want:
- **`--dry-run`** shows what would change without writing anything.
- **Automatic backups** of each file it touches go to `~/.sync-agents-backup/<timestamp>/`.
- **Other settings are left alone.** The README's examples show unrelated keys like Gemini's `theme` being kept, and it says existing servers are never overwritten, so running it again is safe.
- **`diff`, `doctor` and `reconcile`** let you catch differences between the three configs later.

**My assumption:** you're happy for Claude Code to hold the master list, since you already use it. If you'd rather have a neutral master file that no agent owns, see mcpshare below.

### Install (macOS, needs Node.js)
```bash
# Try it without installing:
npx sync-agents-settings list

# Or install globally:
npm install -g sync-agents-settings
```

### First run
```bash
# 0. (Optional but wise) make your own copies first
cp ~/.claude.json ~/.claude.json.manual-bak
cp ~/.codex/config.toml ~/.codex/config.toml.manual-bak
cp ~/.gemini/settings.json ~/.gemini/settings.json.manual-bak

sync-agents list                 # list the MCP servers it found in Claude Code
sync-agents diff                 # compare against Codex and Gemini
sync-agents sync --dry-run       # preview the changes
sync-agents sync                 # write them (backups are made automatically)
```
You can limit a sync to certain agents with `--target`; check `sync-agents --help` for the exact target names. After syncing, run `/mcp` inside Gemini CLI and Codex to confirm the servers appear.

From then on: `claude mcp add …` → `sync-agents sync`.

**One thing to watch:** since it never overwrites existing servers, editing or removing a server in Claude Code may not carry over automatically. Check whether `reconcile` handles that before you depend on it.

## Alternatives
- **mcpshare** (`uv tool install git+https://github.com/eggboy/mcpshare.git`). This is the closest to "one list, synced everywhere": you keep a master `mcp.json` and run `mcpshare init` → `mcpshare pull` (imports your existing servers) → `mcpshare sync`. It only replaces the MCP section of each file, skips target files it can't parse instead of overwriting them, and can turn servers off for individual agents. The downsides: its README mentions no dry-run or backups, and I couldn't see a license.
- **mcpport** (`npx mcpport sync claude codex`, needs Node 22+, MIT). It reads each agent's own config with no master file. Syncs are dry runs unless you add `--apply`, it makes timestamped `.bak` files, and it keeps comments in Codex's TOML. One catch: it won't write Gemini settings files that contain comments.
- **mcp-sync** (Rust crate): uses a canonical `mcp.yaml` and has watch and dry-run modes. Check that its Gemini support covers what you need.

## What I checked
I didn't install or test any of these. Pickfit (a catalog of tools it has test-installed) had nothing that does this job, so these come from a web search and the projects' READMEs. Because the tools are small, young projects, back up your configs and do a dry run first. Codex only supports some server types, and Gemini names the remote-URL field differently (`httpUrl` instead of `url`), so check those settings after your first sync.

Sources:
- [sync-agents-settings](https://github.com/Leoyang183/sync-agents-settings)
- [mcpshare](https://github.com/eggboy/mcpshare)
- [mcpport](https://github.com/Abdalkaderdev/mcpport)
- [mcp-sync (Rust)](https://docs.rs/crate/mcp-sync/latest/source/README.md)
- [mcp-sync (ejfn)](https://github.com/ejfn/mcp-sync)
- [mcp-config-manager](https://github.com/holstein13/mcp-config-manager)
- [Adding MCP servers to each CLI (format differences)](https://inventivehq.com/blog/add-mcp-server-to-ai-coding-cli)