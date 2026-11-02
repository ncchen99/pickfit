Assumptions: you're on macOS (that's what this machine runs), you want a stdio MCP server your agents launch themselves, and your API uses bearer-token auth or none. I haven't run or installed anything.

## Main recommendation: AWS Labs `openapi-mcp-server`

This is a ready-made CLI, not a code generator. It reads your OpenAPI 3 spec at startup, turns each operation into an MCP tool, and sends tool calls to the base URL you give it.

- **Free and open source:** it's in the `awslabs/mcp` repo. I believe the repo is Apache-2.0, but the page I read didn't name the license, so check the LICENSE file.
- **Runs locally:** no account or hosted service needed, despite the "AWS" in the name. It works with any REST API.
- **Settings:** spec from a file (`--spec-path`) or a URL (`--spec-url`), base URL (`--api-url`), and auth (`basic`, `bearer`, or `api_key` in a header, query or cookie). You can include or exclude operations by tag, which helps keep the tool list small.
- **Internal APIs:** it blocks private-network addresses and plain HTTP by default. For an internal API you'll probably need `--allow-private-networks`, and `--allow-insecure-http` if the API isn't on HTTPS.

**Caveat:** pickfit, the tool-testing service I checked, had no verified tool for this job. Its closest matches were unrelated memory and hub servers. Everything below comes from the project's README, and nobody has tested it on your setup.

### Install
```bash
brew install uv            # gives you uvx; skip if you already have it
# Optional if your spec is YAML (uvx users can instead run: uvx --from "awslabs.openapi-mcp-server[yaml]" ...)
pip install "awslabs.openapi-mcp-server[yaml]"
```

### First run (test it by hand)
```bash
uvx awslabs.openapi-mcp-server@latest \
  --api-name internal \
  --api-url https://api.internal.example.com \
  --spec-path ./openapi.yaml \
  --auth-type bearer --auth-token "$INTERNAL_API_TOKEN" \
  --allow-private-networks \
  --log-level INFO
```
If it starts and logs the operations it loaded, it's working.

### Connect your agent
Claude Code:
```bash
claude mcp add internal-api \
  -e API_NAME=internal \
  -e API_BASE_URL=https://api.internal.example.com \
  -e API_SPEC_PATH=/abs/path/openapi.yaml \
  -e AUTH_TYPE=bearer -e AUTH_TOKEN=$INTERNAL_API_TOKEN \
  -e ALLOW_PRIVATE_NETWORKS=true \
  -- uvx awslabs.openapi-mcp-server@latest
```
For Cursor, Claude Desktop and other clients that use JSON config:
```json
{
  "mcpServers": {
    "internal-api": {
      "command": "uvx",
      "args": ["awslabs.openapi-mcp-server@latest"],
      "env": {
        "API_NAME": "internal",
        "API_BASE_URL": "https://api.internal.example.com",
        "API_SPEC_PATH": "/abs/path/openapi.yaml",
        "AUTH_TYPE": "bearer",
        "AUTH_TOKEN": "<token>",
        "ALLOW_PRIVATE_NETWORKS": "true",
        "LOG_LEVEL": "ERROR"
      }
    }
  }
}
```
To check it end to end, ask the agent: "List the tools from internal-api and call a read-only GET endpoint." For a large API, use `INCLUDE_TAGS` to limit which operations become tools. Agents struggle when they're given hundreds of tools.

## Fallback: FastMCP `FastMCP.from_openapi` (Python, Apache-2.0)
Use this if you want more control, such as custom headers, renaming tools, or mapping some routes to resources or excluding them. It needs about 10 lines of glue code, but you still don't write any server logic:
```python
# pip install fastmcp
import json, httpx
from fastmcp import FastMCP
client = httpx.AsyncClient(base_url="https://api.internal.example.com",
                           headers={"Authorization": "Bearer ..."}, timeout=30)
mcp = FastMCP.from_openapi(openapi_spec=json.load(open("openapi.json")), client=client, name="internal")
if __name__ == "__main__":
    mcp.run()   # stdio
```
Then register it with `claude mcp add internal-api -- python /abs/path/server.py`. The current docs example imports `httpx2` instead of `httpx`, so use whichever one your installed FastMCP version shows. FastMCP's own docs say auto-converted servers are good for getting started, but a curated set of tools usually works better for large APIs.

## Not recommended
- **`openapi-2-mcp`** (MIT, works through npx and has `--base-url`): it has 0 stars, 3 commits, and no documented auth options.
- **`openapi-mcp-generator`** generates a TypeScript project that you then have to maintain, which is more than you asked for.

Sources:
- [awslabs openapi-mcp-server](https://github.com/awslabs/mcp/tree/main/src/openapi-mcp-server)
- [FastMCP OpenAPI integration](https://gofastmcp.com/integrations/openapi)
- [openapi-2-mcp](https://github.com/quickdeployai/openapi-2-mcp)
- [openapi-mcp-generator](https://github.com/infusionsoft/openapi-mcp-generator)
- [OpenMCP](https://github.com/getdatanaut/openmcp)