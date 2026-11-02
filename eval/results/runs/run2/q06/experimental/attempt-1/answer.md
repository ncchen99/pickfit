I recommend **`@ivotoby/openapi-mcp-server`** ([ivo-toby/mcp-openapi-server](https://github.com/ivo-toby/mcp-openapi-server)). It's MIT-licensed and needs no account or hosted service. It reads an OpenAPI 3 spec (JSON or YAML, from a local file or a URL) and turns each operation into an MCP tool. When an agent calls a tool, it sends the HTTP request to the base URL you set with `--api-base-url`.

**Not tested:** I took these details from the project's README and didn't install or run it. pickfit (the tool-recommendation service I checked) had no tested match for this need, so please try it on a non-production API first.

**What I assumed:** you're on macOS (that's what this machine is), Node.js 18+ is installed, the spec is a local file, and the API uses header-based auth such as a bearer token or API key.

## Why it fits
- **Spec source:** a local file or URL via `--openapi-spec`, or passed through stdin or inline.
- **Forwarding:** `--api-base-url` sets where requests go. You can add auth headers with `--headers`, and it supports mTLS and a custom CA (`--client-cert`, `--client-key`, `--ca-cert`), which helps with internal APIs.
- **Transports:** `stdio` by default. There's also local HTTP (`--transport http`), which listens on 127.0.0.1:3000 at `/mcp` by default.
- **Limiting the tool list:** big APIs can swamp an agent with tools. You can filter with `--tag`, `--exclude-tag`, `--resource <path-prefix>`, `--operation get` or `--tool <id>`. Another option is `--tools dynamic`, which exposes just three meta-tools: list endpoints, get an endpoint's schema, and invoke an endpoint.
  - The project notes these filters only control which tools appear. They don't enforce access, so your API's own auth still has to protect sensitive endpoints.

## Install and first run
You don't need to install anything up front, because `npx` fetches the package when it runs.

1. **Smoke test in a terminal.** This runs over stdio and waits for a client, so press Ctrl-C after it starts without errors:
   ```bash
   npx -y @ivotoby/openapi-mcp-server \
     --api-base-url https://internal-api.example.corp \
     --openapi-spec /absolute/path/to/openapi.yaml \
     --headers "Authorization:Bearer $INTERNAL_API_TOKEN" \
     --operation get        # optional: read-only tools to start with
   ```

2. **Register it with Claude Code:**
   ```bash
   claude mcp add internal-api \
     -e API_BASE_URL=https://internal-api.example.corp \
     -e OPENAPI_SPEC_PATH=/absolute/path/to/openapi.yaml \
     -e API_HEADERS="Authorization:Bearer <token>" \
     -- npx -y @ivotoby/openapi-mcp-server
   ```
   For Claude Desktop or any other client that uses `mcpServers` JSON (on macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`), add:
   ```json
   {
     "mcpServers": {
       "internal-api": {
         "command": "npx",
         "args": ["-y", "@ivotoby/openapi-mcp-server"],
         "env": {
           "API_BASE_URL": "https://internal-api.example.corp",
           "OPENAPI_SPEC_PATH": "/absolute/path/to/openapi.yaml",
           "API_HEADERS": "Authorization:Bearer <token>"
         }
       }
     }
   }
   ```

3. **First task:** restart the client, run `/mcp` in Claude Code to check that the tools are listed, then ask something like *"Use the internal-api tools to list the first 5 <resources>."*

**Tips:**
- Pin a version (`@ivotoby/openapi-mcp-server@x.y.z`) so an upstream release can't change how it behaves without you noticing.
- Use absolute spec paths.
- Keep tokens out of shared config files.
- If tool names get too long, they're shortened by default. Leave that on, because `--disable-abbreviation` can cause errors when names go over 64 characters.

## Alternative: `mcp-openapi-proxy` (Python)
If your team prefers Python, try `uvx mcp-openapi-proxy`. You set the spec with `OPENAPI_SPEC_URL`, the target base URL with `SERVER_URL_OVERRIDE`, and filter tools with `TOOL_WHITELIST`. Auth uses `API_KEY` / `API_AUTH_TYPE` / `EXTRA_HEADERS`, and YAML specs need `OPENAPI_SPEC_FORMAT=yaml`. I could only confirm these from PyPI pages and third-party listings, not the project's current README, so treat it as second choice and check its docs first.

Sources:
- [ivo-toby/mcp-openapi-server (GitHub)](https://github.com/ivo-toby/mcp-openapi-server)
- [mcp-openapi-proxy on PyPI](https://pypi.org/project/mcp-openapi-proxy/0.1.1741395034/)
- [mcp-openapi-proxy listing (LobeHub)](https://lobehub.com/pt-BR/mcp/gwyntel-mcp-openapi-proxy)