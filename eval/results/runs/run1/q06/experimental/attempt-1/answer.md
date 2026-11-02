I recommend **`@ivotoby/openapi-mcp-server`** ([GitHub](https://github.com/ivo-toby/mcp-openapi-server)). It's MIT-licensed and runs locally through `npx`. You give it your spec and your API's base URL, and it turns each operation in the spec into an MCP tool. When an agent calls a tool, it sends the request to that base URL. You don't write any server code and you don't need an account or hosted service.

**How I checked:** I looked in pickfit, a directory of tools it has installed and tested, and none of them fit this request. I read the project's README for the flags and config below, but I haven't run the tool myself. Test it against a non-production copy of your API first.

**What I assumed:** You're on macOS (this machine is a Mac). You have Node.js 18 or later. Your API takes a header-based token, which you can change if it doesn't.

## Install and first run

1. **Check Node:** `node --version`. If it's missing, install it with `brew install node`.
2. **Try it once by hand.** Nothing is installed globally because `npx` fetches the package. The `--operation get` flag exposes only read-only endpoints, which is a safer first test:
   ```bash
   npx -y @ivotoby/openapi-mcp-server \
     --api-base-url https://internal-api.example.corp \
     --openapi-spec ./openapi.yaml \
     --headers "Authorization:Bearer $INTERNAL_API_TOKEN" \
     --operation get \
     --verbose
   ```
   `--openapi-spec` takes a file path or a URL. By default the server talks over stdio, so it will start and wait for input. That means it's working. Stop it with Ctrl-C.
3. **Register it with Claude Code:**
   ```bash
   claude mcp add internal-api \
     -e API_BASE_URL=https://internal-api.example.corp \
     -e OPENAPI_SPEC_PATH=/absolute/path/to/openapi.yaml \
     -e API_HEADERS="Authorization:Bearer <token>" \
     -- npx -y @ivotoby/openapi-mcp-server --operation get
   ```
   For Claude Desktop or Cursor, use the same settings as JSON:
   ```json
   {
     "mcpServers": {
       "internal-api": {
         "command": "npx",
         "args": ["-y", "@ivotoby/openapi-mcp-server", "--operation", "get"],
         "env": {
           "API_BASE_URL": "https://internal-api.example.corp",
           "OPENAPI_SPEC_PATH": "/absolute/path/to/openapi.yaml",
           "API_HEADERS": "Authorization:Bearer <token>"
         }
       }
     }
   }
   ```
4. **Test it:** In Claude Code, run `/mcp` and check that `internal-api` is connected and its tools are listed. Then ask the agent to call a simple GET endpoint, such as listing some items.

## Useful options
- **Exposing fewer tools:** Large specs can swamp the agent with tools. You can narrow them down with `--tag <tag>`, `--exclude-tag`, `--resource /prefix`, `--operation get|post|...` or `--tool <id>`. Another option is `--tools dynamic`, which gives the agent just three tools: one to list endpoints, one to look one up and one to call it.
- **Several agents sharing one server:** Add `--transport http --port 3000`. The server listens on `127.0.0.1:3000/mcp` by default.
- **mTLS or an internal CA:** Use `--client-cert`, `--client-key` and `--ca-cert`.
- **Security:** The tag filters only decide which tools show up. They don't block access. Your API still has to enforce permissions, so give the server a token with the least access the agents need. Turn on write operations (`post`, `put`, `delete`) only when you choose to.

## Alternative
**FastMCP** (Python, open source) can build a server from a spec with `FastMCP.from_openapi(...)`. It does the same job, but you'd write a short Python script of about 10 lines, so it doesn't quite meet your "no hand-written code" requirement. I haven't tested it either. Use it if you want to change behavior in code, such as custom authentication or response shaping.

Sources:
- [ivo-toby/mcp-openapi-server (GitHub)](https://github.com/ivo-toby/mcp-openapi-server)