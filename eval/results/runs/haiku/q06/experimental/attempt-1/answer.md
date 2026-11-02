**Main recommendation: `openapi-2-mcp` (or its close relative `openapi-to-mcp`), run as a local stdio CLI.** I have not verified either one on your machine, and pickfit found no verified match for this job. The recommendation comes from web search results and their READMEs, so treat the flags below as unconfirmed until `--help` shows them.

**Why this one:** It's a CLI, so you write no server code. It reads your spec and forwards each operation to `--base-url`. Per the search results, `openapi-to-mcp` exposes only `GET` and `HEAD` by default and needs `--allow-write` for other methods, which is a sensible default when agents are calling an internal API.

**Install and first run (assumed macOS, Node.js installed):**

1. Check the package exists and read its options before installing. Run `npm view openapi-2-mcp` and `npx openapi-2-mcp --help`. The search didn't confirm the exact package name, so this step matters.
2. Keep the spec local, for example `~/mcp/our-api/openapi.yaml`.
3. Test the server by hand. The search results suggest this form:
   `npx -y openapi-2-mcp ~/mcp/our-api/openapi.yaml --base-url https://api.internal.example.com --stdio`
   Use Ctrl+C to stop it. The point of this step is to confirm it starts and lists tools without errors.
4. Register it with Claude Code, using the same command after `--`:
   `claude mcp add our-api -- npx -y openapi-2-mcp ~/mcp/our-api/openapi.yaml --base-url https://api.internal.example.com --stdio`
5. Check it with `claude mcp list`, then ask the agent to call one read-only operation and confirm the request reaches your API.
6. For other agents (Cursor, Codex, etc.), add the same command to their MCP config. Their file formats differ, so check each one's docs.

**Things to check first:**
- Auth: if your API needs a token, check how the tool passes headers or environment variables. Don't put secrets in the spec or in the command line.
- Write methods: keep them disabled unless the agents truly need to modify data.
- Spec quality: the generated tool names and descriptions come from `operationId` and `summary`, so unclear names will hurt tool selection.

**Alternative if the CLI doesn't fit:** Python's FastMCP has built-in OpenAPI support (`FastMCP.from_openapi(...)`). It's free and open source, and well maintained. However, it needs a short Python script, so it's not zero-code.

**Sources:**
- [openapi-2-mcp / openapi-to-mcp search results](https://github.com/quickdeployai/openapi-2-mcp)
- [openapi-to-mcp (glama listing)](https://glama.ai/mcp/servers/YusufBeratZengin/openapi-to-mcp/tree)
- [openapi-mcp-generator (Infusionsoft)](https://github.com/infusionsoft/openapi-mcp-generator)
- [@lucid-spark/openapi-mcp-server](https://lobehub.com/mcp/lucivuc-openapi-mcp-server)