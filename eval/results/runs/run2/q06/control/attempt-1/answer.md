I recommend **`@ivotoby/openapi-mcp-server`** (repo: [ivo-toby/mcp-openapi-server](https://github.com/ivo-toby/mcp-openapi-server)). It's MIT-licensed and runs locally. You give it your OpenAPI 3 spec and your API's base URL. It turns each operation in the spec into an MCP tool and sends the agents' tool calls to that base URL. It doesn't generate any code, and it needs no hosted service or account. By default it uses stdio, which is what Claude Code, Claude Desktop, Cursor and similar tools expect. It can also run over HTTP.

**My assumptions:** Node.js 18 or newer is installed. Your spec is a JSON or YAML file, or a URL. The API uses header-based auth such as a bearer token or API key. I checked the flags below against the project README today. I haven't run it.

## Install

You don't need a separate install because `npx` fetches the package when it runs. To pin a version for your team, install it once:
```bash
npm install -g @ivotoby/openapi-mcp-server
```

## First run (manual smoke test)
```bash
npx -y @ivotoby/openapi-mcp-server \
  --api-base-url https://internal-api.example.corp \
  --openapi-spec ./openapi.yaml \
  --headers "Authorization:Bearer $API_TOKEN"
```
It will wait silently on stdio, which means it started correctly. To browse the tools it creates, run it under the MCP Inspector:
```bash
npx @modelcontextprotocol/inspector npx -y @ivotoby/openapi-mcp-server \
  --api-base-url https://internal-api.example.corp --openapi-spec ./openapi.yaml
```

## Connect it to your agents

**Claude Code:**
```bash
claude mcp add internal-api \
  -e API_BASE_URL=https://internal-api.example.corp \
  -e OPENAPI_SPEC_PATH=/abs/path/openapi.yaml \
  -e API_HEADERS="Authorization:Bearer YOUR_TOKEN" \
  -- npx -y @ivotoby/openapi-mcp-server
```

**Claude Desktop, Cursor or another JSON-config client:**
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

## Useful options
- **Limit which tools are exposed.** A large API can flood the agent with tools, so this matters. Use `--tag <tag>`, `--exclude-tag <tag>`, `--operation get` (for example, read-only GETs to start), `--tool <id>`, or `--tools dynamic`, which exposes only a few meta-tools for finding and calling endpoints.
- **Share one server across several agents:** `--transport http --port 3000` serves `http://127.0.0.1:3000/mcp`.
- **mTLS for internal APIs:** `--client-cert`, `--client-key` and `--ca-cert`.
- **Other spec sources:** `--spec-from-stdin` or `--spec-inline`.

## Cautions
- Put tokens in environment variables, not in config files that get committed.
- Start with read-only operations or a non-production base URL. Agents will call any POST or DELETE you expose.
- Clear `operationId`s and descriptions in your spec make the tools much easier for agents to use, because the tool names and descriptions come from the spec.

## Alternative: FastMCP (Python)
If your team prefers Python, [FastMCP's `FastMCP.from_openapi()`](https://gofastmcp.com/integrations/openapi) does the same job. It's also open source and local. It needs a short script of about 10 lines: you set up an HTTP client with the base URL and auth headers, load the spec, and call `mcp.run()`. In return, you get more control over the result. Route maps let you leave out endpoints or expose some as resources, and you can rename tools. The FastMCP docs say that auto-converted servers work worse with LLMs than hand-curated ones on large APIs. That's true for both tools, so filtering the tools down is worth doing whichever one you choose.

Sources:
- [ivo-toby/mcp-openapi-server](https://github.com/ivo-toby/mcp-openapi-server)
- [FastMCP OpenAPI integration](https://gofastmcp.com/integrations/openapi)