**Recommendation: use [Serena](https://github.com/oraios/serena) as your one structured-code MCP server.** Keep ripgrep and a short AGENTS.md alongside it. Only add a semantic or vector search server if you later find a specific gap.

I'm an AI, so I can't tell you what I've "settled on" from my own use. This is my read of the tools and of how agents tend to behave with them.

## Why Serena

- **The agent actually uses it.** Its tools work at the level of symbols: find a symbol, find everything that references it, list a file's symbols, and edit or replace a whole function body. That lines up with how agents already plan work ("find X, see who calls it, change it"), so the model picks these tools up without much coaching. Vector search tools return chunks of text, which the model then has to re-read and check with grep anyway.
- **Answers come from real language servers (LSP).** Serena runs the same language servers your editor uses, for 40+ languages. "Who calls `save()`?" gets a type-aware answer instead of every line containing the string `save`. Grep struggles most with overloaded names, interfaces and similar method names across a big codebase.
- **It can edit, not just read.** It can rename and edit symbols. Codanna, CodeGraphContext and claude-context are read-only.
- **It's light to run.** You need `uv`, nothing else: no Neo4j, no Milvus, no embedding API key or cost. The language server keeps its index current as files change, so there's no separate embedding index to rebuild.
- **It has client-specific modes.** There are `claude-code` and `codex` contexts that switch off Serena tools that duplicate the client's own file and shell tools.

## What to watch for

- **Agents still fall back to grep.** Claude Code especially has strong habits around its built-in Grep and Read tools. Add one line to AGENTS.md or CLAUDE.md, for example: *"For code navigation (definitions, references, call sites), prefer Serena's symbol tools over grep."* That noticeably changes behaviour.
- **Startup can be slow.** The language server can take a while to start on a big repo, and some languages need extra dependencies (see the Language Support page).
- **License change.** Serena moved to GPL-3.0-or-later around October 2026. Running it locally is fine; it only matters if you redistribute it.
- **No "find code by meaning" search.** Serena can't answer vague queries like "where do we handle retries?". For that you'd need [claude-context](https://github.com/zilliztech/claude-context), which is hybrid keyword plus vector search but needs Milvus/Zilliz and an embeddings provider. Alternatively, a graph tool like CodeGraphContext or Codanna can answer call-graph and impact questions. Several comparisons suggest the same pairing: Serena plus at most one search or graph tool.

## Is it worth it over ripgrep and AGENTS.md?

- **Probably not** for small to medium repos, especially in dynamic languages. A good AGENTS.md (layout, conventions, entry points, how to run tests) plus ripgrep gets you most of the benefit, and the extra tool descriptions also take up context.
- **Yes** for large or unfamiliar repos, statically typed languages (TypeScript, Java, Go, Rust, C#), and refactors that touch many call sites. In those cases precise lookups mean fewer wasted file reads and fewer missed call sites.
- **Cheap test:** run the same 3–5 real tasks with and without Serena and compare tokens used, wrong edits and missed references. That will tell you more than any comparison article.

## Install and first run

I'm assuming you use Claude Code or Codex on macOS. These commands come from Serena's current README and client docs. I haven't run them, so check `serena --help` if anything differs.

1. **Install uv** (if you don't have it): `curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`
2. **Install Serena:**
   ```bash
   uv tool install -p 3.13 serena-agent
   serena init            # uses the LSP backend by default (JetBrains users: serena init -b JetBrains)
   ```
   The README says to avoid installing through MCP or plugin marketplaces because those commands are out of date.
3. **Connect it to your agent:**
   - Claude Code, quick setup: `serena setup claude-code`
   - Or manually, for all projects:
     ```bash
     claude mcp add --scope user serena -- serena start-mcp-server --context claude-code --project-from-cwd
     ```
   - Codex: `serena setup codex`, or add this to `~/.codex/config.toml`:
     ```toml
     [mcp_servers.serena]
     startup_timeout_sec = 15
     command = "serena"
     args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]
     ```
   - Other clients: run `serena start-mcp-server --context ide` and add `--project-from-cwd` or `--project <path>`.
4. **First run:**
   - Start the agent from the repo root, run `/mcp`, and check that Serena is connected.
   - If it times out on a big repo, set `export MCP_TIMEOUT=60000`.
   - A local dashboard (it was on port 24282 in older versions) shows logs and language-server status.
   - Older guides pre-index with `serena project index`, which speeds up the first language-server start on large repos. Check it still exists in v2.
   - Give it a real test, e.g. *"Using Serena, find all callers of `<some function>` and summarise them."* Then check whether it used `find_referencing_symbols` or quietly went back to grep.
5. **Add the AGENTS.md nudge** from above.

Sources:
- [Serena GitHub README](https://github.com/oraios/serena)
- [Serena client setup docs](https://oraios.github.io/serena/02-usage/030_clients.html)
- [Playbooks: Serena MCP server](https://playbooks.com/mcp/oraios-serena)
- [zenn.dev: install serena](https://zenn.dev/splusl_at/articles/install-serena)
- [Local code-graph MCP servers compared (zzet.org)](https://zzet.org/gortex/local-code-graph-mcp-servers-compared/)
- [Code Intelligence for AI Agents (rywalker.com)](https://rywalker.com/research/code-intelligence-tools)
- [Sverklo: Best MCP Servers for Code Intelligence (2026)](https://sverklo.com/blog/practical-guide-mcp-code-intelligence/)
- [Code Index MCP Comparison 2026 (baeseokjae)](https://baeseokjae.github.io/posts/ai-coding-agent-code-index-mcp-comparison-2026/)
- [Repowise: Best Code Graph MCP Servers (2026)](https://repowise.dev/blog/comparisons/best-code-graph-mcp-servers)
- [qartez-mcp](https://github.com/kuberstar/qartez-mcp)