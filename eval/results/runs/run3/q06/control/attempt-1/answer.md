## Recommendation: `openapi-mcp-generator` (MIT, runs locally, no account needed)

I'd use [openapi-mcp-generator](https://github.com/harsha-iiiv/openapi-mcp-generator). It reads your OpenAPI 3 spec (JSON or YAML, from a file or URL) and writes out a complete TypeScript MCP server project. Each operation becomes an MCP tool, and each tool call becomes an HTTP request to your API's base URL. You don't write any server code, and the generated server runs entirely on your machine.

Why it fits what you asked for:
- **Base URL:** It's taken from the spec's `servers` list, or set with `--base-url`. At runtime you can change it with the `API_BASE_URL` environment variable without regenerating.
- **Auth:** Credentials come from environment variables tied to your spec's security schemes, such as `BEARER_TOKEN_<SCHEME>`, `API_KEY_<SCHEME>` or `BASIC_USERNAME_/PASSWORD_<SCHEME>`. If a credential is missing, the tool returns an error instead of sending the request without it.
- **Choosing which endpoints become tools:** Use `--include-tags`, `--exclude-tags`, `--include-operations` and `--exclude-operations`. Use them. Agents work noticeably better with a small, focused set of tools than with every endpoint.
- **Transports:** `stdio` is the default and the right choice for local coding agents. `streamable-http` is also available if several agents need to share one server.

### Install
You need Node.js 22.19 or later.
```bash
npm install -g openapi-mcp-generator
```

### First run
```bash
# 1. Generate the server
openapi-mcp-generator \
  --input ./openapi.yaml \
  --output ./internal-api-mcp \
  --base-url https://api.internal.example.com \
  --exclude-tags admin          # optional curation

# 2. Build it
cd internal-api-mcp
npm install
npm run build
```

I'm assuming the build command is `npm run build` and the output goes to `build/index.js`, since that's the usual layout for these projects. Check the `scripts` section of the generated `package.json` to confirm.

```bash
# 3. Configure (in .env or the agent config)
API_BASE_URL=https://api.internal.example.com
BEARER_TOKEN_BEARERAUTH=...     # suffix = your securityScheme name
```

**4. Register it with your agent.** For example, with Claude Code:
```bash
claude mcp add internal-api --env BEARER_TOKEN_BEARERAUTH=... -- node /abs/path/internal-api-mcp/build/index.js
```
Other agents (Cursor, VS Code, etc.) use the same command and arguments in their `mcpServers` JSON config.

**5. Test it.** Ask the agent to list its tools, then call one read-only endpoint. You can also check the tools with `npx @modelcontextprotocol/inspector node build/index.js`.

If the spec changes, run the generator again with `--force`.

## Alternative: FastMCP (Python), if you'd rather not generate a project
`pip install fastmcp`, then write about 10 lines of glue code. It's not quite "no code," but there's nothing to regenerate:
```python
import httpx, yaml
from fastmcp import FastMCP
spec = yaml.safe_load(open("openapi.yaml"))
client = httpx.AsyncClient(base_url="https://api.internal.example.com",
                           headers={"Authorization": "Bearer ..."}, timeout=30)
mcp = FastMCP.from_openapi(openapi_spec=spec, client=client, name="internal-api")
if __name__ == "__main__":
    mcp.run()   # stdio
```
It reads the spec when the server starts, so changes to the spec take effect without a regeneration step. `RouteMap` rules let you exclude routes or allow only specific ones. One caveat: the current FastMCP docs show `httpx2` in their example rather than `httpx`, so check which client your installed version expects. The FastMCP docs themselves say this auto-conversion is best for prototyping, and that a curated set of tools works better for large APIs.

## Options I'd skip
Stainless and Speakeasy can also generate MCP servers, but they're hosted or need an account, which you ruled out.

Whichever tool you choose, don't expose destructive operations (DELETE, admin routes) as tools until you've decided agents should call them unsupervised.

Sources:
- https://github.com/harsha-iiiv/openapi-mcp-generator
- https://gofastmcp.com/integrations/openapi