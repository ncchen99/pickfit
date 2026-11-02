My recommendation is **`@ivotoby/openapi-mcp-server`** ([ivo-toby/mcp-openapi-server](https://github.com/ivo-toby/mcp-openapi-server)). It's MIT-licensed and runs locally with `npx`. You point it at your spec and your API's base URL, and it turns each operation into an MCP tool. When an agent calls a tool, it sends the HTTP request to that base URL. You don't write any server code and you don't need an account.

**My assumptions:** you have Node.js 18 or newer, your spec is JSON or YAML (a local file or a URL), and your API uses header-based auth such as a bearer token or API key. I haven't run any of this on your machine. The flags below come from the project's current README.

## Install and first run

**1. Install.** Nothing to install globally. `npx -y` downloads and runs the package. If you want a fixed version for reproducibility, pin one, e.g. `@ivotoby/openapi-mcp-server@<version>`, and check npm for the latest.

**2. Smoke-test it with the MCP Inspector** before connecting any agents:
```bash
npx @modelcontextprotocol/inspector \
  npx -y @ivotoby/openapi-mcp-server \
    --api-base-url https://internal-api.example.corp \
    --openapi-spec ./openapi.yaml \
    --headers "Authorization:Bearer $INTERNAL_API_TOKEN"
```
In the Inspector UI, connect and open **Tools**. Check that your operations appear, then call a harmless GET and confirm it reaches your API.

**3. Connect your agent.** Stdio is the default transport.

- **Claude Code:**
  ```bash
  claude mcp add internal-api \
    -e API_BASE_URL=https://internal-api.example.corp \
    -e OPENAPI_SPEC_PATH=/abs/path/openapi.yaml \
    -e API_HEADERS="Authorization:Bearer YOUR_TOKEN" \
    -- npx -y @ivotoby/openapi-mcp-server
  ```
- **Any JSON-configured client** (Claude Desktop, Cursor, etc.):
  ```json
  {
    "mcpServers": {
      "internal-api": {
        "command": "npx",
        "args": ["-y", "@ivotoby/openapi-mcp-server"],
        "env": {
          "API_BASE_URL": "https://internal-api.example.corp",
          "OPENAPI_SPEC_PATH": "/abs/path/openapi.yaml",
          "API_HEADERS": "Authorization:Bearer YOUR_TOKEN"
        }
      }
    }
  }
  ```
- **Several agents sharing one server:** run it over HTTP instead. Add `--transport http --port 3000` and point the clients at `http://127.0.0.1:3000/mcp`. The health check is at `/health`, and the server binds to 127.0.0.1 by default.

## Settings worth knowing
- **Limit what agents can do.** By default every operation becomes a tool. You can narrow that with `--tag`, `--exclude-tag`, `--tool`, `--resource <path-prefix>`, or `--operation get`. For example, `--operation get` makes the agents read-only until you trust the setup.
- **Big specs:** `--tools dynamic` gives agents a few tools for discovering and calling endpoints, instead of hundreds of separate tools that fill up their context.
- **Internal TLS:** `--ca-cert` adds your corporate CA, and `--client-cert`/`--client-key` handle mTLS. Use this rather than `--reject-unauthorized false`.
- **Keep tokens out of committed config.** Use environment variables or your client's secret handling. Also note that verbose logging is on by default.

## Alternatives
- **[`mcp-openapi-proxy`](https://pypi.org/project/mcp-openapi-proxy/)** (Python, MIT): run it with `uvx mcp-openapi-proxy`. It's configured with `OPENAPI_SPEC_URL`, which can be a URL or `file://` path, plus `SERVER_URL_OVERRIDE` for your base URL, `API_KEY`, and `TOOL_WHITELIST`. Choose this if your team prefers Python. Option names have changed between releases, so check the [README](https://github.com/matthewhand/mcp-openapi-proxy) first.
- **FastMCP's `FastMCP.from_openapi(...)`** (Python): about 10 lines of code. Use it if you later need custom auth or want to reshape responses.
- **`openapi-mcp-generator`**: generates a TypeScript server project from the spec instead of proxying at runtime. That's useful if you want code you own and can edit, but you then have to maintain the generated code.

Sources:
- [ivo-toby/mcp-openapi-server (GitHub)](https://github.com/ivo-toby/mcp-openapi-server)
- [mcp-openapi-proxy on PyPI](https://pypi.org/project/mcp-openapi-proxy/0.1.1741466171/)
- [mcp-openapi-proxy listing (LobeHub)](https://lobehub.com/pt-BR/mcp/gwyntel-mcp-openapi-proxy)