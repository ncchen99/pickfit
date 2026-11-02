I haven't used these in long-running daily work, so I can't tell you which one I've "settled on." What follows comes from the projects' docs, one comparison write-up, and sandbox install checks from pickfit. I'm assuming you're on macOS (the environment here is Darwin), you use Claude Code or Codex, your code is mostly in typed languages, and you want something free and local.

## Main recommendation: Serena, and start without the extras

**Serena** ([oraios/serena](https://github.com/oraios/serena)) is the safest first choice:

- **How it works:** it sits on top of language servers (LSP) for more than 40 languages. That gives the agent exact find-symbol, find-references, a symbol overview per file, and edits made at the symbol level. Renames and signature changes are real refactors, not text replacements.
- **No index to build or keep fresh.** The language server does the work, so setup is mostly "install and connect." The cost is that some languages need their own language server or toolchain installed, and startup can be slow.
- **It edits code as well as reading it**, which none of the graph or vector tools do.
- **It's honest about the main problem in this space:** its own docs admit that in long sessions agents tend to drift back to grep and file reads. It ships hooks that remind the agent to use Serena and a system-prompt override to counter this. That matches your concern about whether the agent actually uses the structured data. Without some nudging, it often doesn't.

**What it doesn't do:** semantic search ("find code by meaning") or whole-repo call graphs and impact analysis. If you need those, add a graph tool next to it (see below) rather than replacing it.

### Install and first run (macOS, Claude Code)
I haven't run these. They're copied from Serena's current README and clients guide, so check them against the docs before running.

```bash
# 1. Prerequisite: uv
brew install uv

# 2. Install Serena. The docs say NOT to use an MCP or plugin marketplace; those commands are outdated
uv tool install -p 3.13 serena-agent
serena init

# 3. Connect it to Claude Code (for all projects, using the current directory)
claude mcp add --scope user serena -- serena start-mcp-server --context claude-code --project-from-cwd
#    or for one project only:
#    claude mcp add serena -- serena start-mcp-server --context claude-code --project "$(pwd)"
#    or: serena setup claude-code

# 4. If it times out on startup
export MCP_TIMEOUT=60000   # add to your shell profile
```
- For Codex, run `serena setup codex`, or add an `[mcp_servers.serena]` entry with `startup_timeout_sec = 15` and `args = ["start-mcp-server","--project-from-cwd","--context=codex"]`.
- For Cursor, use `--context ide`.

**First run:**
1. Open `claude` in your repo and run `/mcp` to confirm Serena is connected.
2. Give it a task that plays to its strengths, for example: *"Using Serena, find every caller of `X`, then rename it to `Y` and update the call sites."* Check that it calls `mcp__serena__*` tools rather than `rg`.
3. **Stop the drift back to grep (recommended):** add the Serena hooks in `~/.claude/settings.json`:
   - `SessionStart` runs `serena-hooks activate --client=claude-code`
   - `PreToolUse` runs `serena-hooks remind --client=claude-code`
   - optionally, auto-approve on `mcp__serena__*`

   Hooks are marked alpha, so get the exact JSON from the [clients guide](https://oraios.github.io/serena/02-usage/030_clients.html). You can also start Claude with `claude --system-prompt="$(serena prompts print-cc-system-prompt-override)"`.

## If you also want call graphs and impact analysis

- **codebase-memory-mcp:** a persistent local knowledge graph with tools like `trace_path` and `detect_changes` ("what does this diff touch?"). Semantic search uses an embedding model built into the binary, so no API key is needed, and it's read-only. The comparison I read suggests pairing it with Serena: the graph maps the impact and Serena makes the edits.
  - **Watch out:** the default installer also changes your agent's configuration (hooks, skills, instructions). Read the script first, or install with `--skip-config` and add the server yourself. Like any static analysis, it misses dynamic dispatch.
- **Claude Context (Zilliz):** hybrid BM25 + vector search. By default it sends code chunks to an embedding API and stores vectors in Zilliz Cloud. It's only worth it if you already run Milvus or are fine with that data leaving your machine.

**Lesser-known options from pickfit**, which installs MCP servers in a sandbox and checks that they answer. They're less proven than the tools above:
- **code-cortex-mcp:** a knowledge-graph MCP server, verified on macOS arm64. Indexing and graph-augmented search worked, but the check didn't show caller lookup or call-path tracing producing results. It needs CMake and a C++23 compiler to build.
- **indexio:** lexical, semantic and hybrid search plus `who_calls`. It's local and Apache-2.0, but was verified only on Linux.
- **agent-lsp:** the same LSP-based idea as Serena, with 65 tools. It installed and answered in the sandbox, but no features were tested one by one.

If you want any of these, I can get pickfit's tested install steps.

## Is it worth it over ripgrep and AGENTS.md?

My view:
- **Start with ripgrep and a good AGENTS.md.** Current models use grep well, and a short AGENTS.md (architecture map, where things live, build and test commands) often gives more than any MCP server. It costs no context for tool definitions and has no startup cost.
- **Add Serena when you see these problems:** the agent reads whole large files to find one function, misses call sites during refactors, or the codebase is large and typed (TypeScript, Java, Go, Rust, C#). That's where exact references and symbol-level edits clearly beat text search.
- **Add a graph tool only if** you often ask "what breaks if I change this?" in code you don't know well.
- **Don't run several at once.** Every server adds tool descriptions to the context, and overlapping tools make the agent's choice of tool worse, not better.

I found no independent head-to-head benchmarks; the "fewer tokens" claims come from the vendors. The cheapest way to decide is to install Serena on your real repo, give it 3–4 refactor or navigation tasks with and without it, and compare how many tokens and wrong turns each run takes.

Sources:
- [Serena README](https://github.com/oraios/serena)
- [Serena clients guide](https://oraios.github.io/serena/02-usage/030_clients.html)
- [developertoolkit.ai: Serena, codebase-memory-mcp, Claude Context and Repomix](https://developertoolkit.ai/en/ecosystem/mcp/code-intelligence-mcp/)
- [Claude Market blog](https://claudemarket.ai/blog/best-mcp-servers-for-claude-code)
- pickfit sandbox results for [indexio](https://github.com/IOServicesLabs/indexio), [code-cortex-mcp](https://github.com/tigercosmos/code-cortex-mcp) and [agent-lsp](https://github.com/blackwell-systems/agent-lsp)