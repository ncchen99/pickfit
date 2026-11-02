**My recommendation is `@ivotoby/openapi-mcp-server`** ([GitHub: ivo-toby/mcp-openapi-server](https://github.com/ivo-toby/mcp-openapi-server)). It's MIT-licensed and runs locally through `npx`. You point it at your OpenAPI spec and your API's base URL, and it turns each operation into an MCP tool. When an agent calls a tool, it sends the HTTP request to your base URL with whatever headers you set. You don't write any server code and you don't need an account or hosted service.

**How I checked:** I read the project's README. I didn't install or test it, and pickfit (the catalogue I searched) has no tested tools for this job. The steps below come from the docs and haven't been run on a Mac.

**My assumptions:** macOS with Node.js 18+ available; your agent is Claude Code or Claude Desktop (any MCP client works the same way); your API authenticates with a header such as a bearer token or API key.

## Install and first run

1. **Requirement:** Node.js 18 or later (`brew install node` if you don't have it). Nothing else to install, because `npx` downloads the package on first run.

2. **Test it in your terminal first** using HTTP transport, which makes it easy to check:
   ```bash
   npx -y @ivotoby/openapi-mcp-server \
     --api-base-url https://internal-api.example.corp \
     --openapi-spec ./openapi.yaml \
     --headers "Authorization:Bearer $INTERNAL_API_TOKEN" \
     --transport http --port 3000
   ```
   The server listens on `http://127.0.0.1:3000/mcp`. `--openapi-spec` takes either a file path or a URL. Give it only one spec source, or it exits with an error.

3. **Register it with your agent** using stdio, the default transport, so the agent starts the server itself.

   Claude Code:
   ```bash
   claude mcp add internal-api \
     -e API_BASE_URL=https://internal-api.example.corp \
     -e OPENAPI_SPEC_PATH=/absolute/path/to/openapi.yaml \
     -e API_HEADERS="Authorization:Bearer YOUR_TOKEN" \
     -- npx -y @ivotoby/openapi-mcp-server
   ```
   Claude Desktop, or any client that reads `mcpServers` JSON (on a Mac, Claude Desktop's file is `~/Library/Application Support/Claude/claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "internal-api": {
         "command": "npx",
         "args": ["-y", "@ivotoby/openapi-mcp-server"],
         "env": {
           "API_BASE_URL": "https://internal-api.example.corp",
           "OPENAPI_SPEC_PATH": "/absolute/path/to/openapi.yaml",
           "API_HEADERS": "Authorization:Bearer YOUR_TOKEN"
         }
       }
     }
   }
   ```

4. **First task:** In Claude Code, run `/mcp` to check that `internal-api` is connected and to see its tools. Then ask the agent to call something harmless, like "list the first 5 items using the internal API."

## Useful options
- **Large APIs:** `--tools dynamic` gives the agent just three tools (`list-api-endpoints`, `get-api-endpoint-schema`, `invoke-api-endpoint`) instead of one per operation, which keeps the agent's context small.
- **Limiting what agents can reach:** you can filter by `--tag`, `--exclude-tag`, `--resource /prefix`, `--operation get`, or list exact operations with `--tools explicit --tool <operationId>`. For example, `--operation get` gives you a read-only setup. The docs note that these filters only control which tools exist, not who's allowed to do what, so your API's own auth still has to protect sensitive endpoints.
- **Tokens:** pass your token through an environment variable or your client's env config instead of committing it into a shared config file.

## Alternative: FastMCP (Python)
Pick [FastMCP](https://gofastmcp.com/integrations/openapi) if you want more control, such as mapping some routes to resources instead of tools, excluding routes by regex, or custom auth. It's open source and runs locally, but you have to write a short Python script, so it doesn't strictly meet your "no code" requirement:
```python
import httpx
from fastmcp import FastMCP

client = httpx.AsyncClient(base_url="https://internal-api.example.corp",
                           headers={"Authorization": "Bearer YOUR_TOKEN"})
spec = httpx.get("https://internal-api.example.corp/openapi.json").json()
mcp = FastMCP.from_openapi(openapi_spec=spec, client=client, name="Internal API")

if __name__ == "__main__":
    mcp.run()
```
Install with `uv pip install fastmcp` or `pip install fastmcp`. Then register it with `claude mcp add internal-api -- python /path/to/server.py`. pickfit hasn't tested FastMCP either.

**Tip:** whichever tool you use, the tool names and descriptions come from your spec's `operationId`s and summaries. Clear, unique values for those make a big difference to how well agents choose the right call.

Sources:
- https://github.com/ivo-toby/mcp-openapi-server
- https://gofastmcp.com/integrations/openapi