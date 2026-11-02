**Recommendation: `@ivotoby/openapi-mcp-server`** (MIT licensed, on npm, source at [github.com/ivo-toby/mcp-openapi-server](https://github.com/ivo-toby/mcp-openapi-server)). It reads an OpenAPI 3 spec, exposes each operation as an MCP tool, and forwards tool calls to your API's base URL. It needs no account or hosted service, and you don't write any server code.

I haven't run anything here. The details below come from the project README, so check the flags against the version you install.

**Install and first run**

1. Install Node.js (current LTS) so `npx` is available. There's no global install step.
2. Keep your spec as a local file, such as `./openapi.yaml`, or use a URL the machine can reach. JSON and YAML both work.
3. Test that the server starts. It speaks MCP over stdio, so it will sit waiting for input, which is expected:
   ```sh
   npx -y @ivotoby/openapi-mcp-server \
     --api-base-url https://api.internal.example.com \
     --openapi-spec ./openapi.yaml
   ```
   Environment variables work too: `API_BASE_URL` and `OPENAPI_SPEC_PATH`.
4. Register it with each agent. Your agents launch the server themselves, so you don't run it by hand. A typical MCP client entry looks like this:
   ```json
   {
     "mcpServers": {
       "our-api": {
         "command": "npx",
         "args": ["-y", "@ivotoby/openapi-mcp-server",
                  "--api-base-url", "https://api.internal.example.com",
                  "--openapi-spec", "/absolute/path/to/openapi.yaml"],
         "env": { "API_HEADERS": "Authorization:Bearer <token>" }
       }
     }
   }
   ```
   Put this in your client's MCP config. The exact file location varies by agent.
5. Confirm the tools appear in the agent, then make one read-only call against a test environment.

**Things to know**

- **Auth:** Pass headers with `API_HEADERS` or `--headers` as comma-separated `key:value` pairs. Keep real tokens out of committed config files. The README also covers mutual TLS flags (`--client-cert`, `--client-key`, `--ca-cert`).
- **Tool surface:** By default it exposes every operation, which is a lot for an agent. Use `--tag`, `--exclude-tag`, `--resource`, `--operation`, or `--tool` to narrow it. `--tools dynamic` gives the agent a few meta-tools instead. The README says tag filters are not an authorization boundary, so enforce permissions on the API side.
- **Transport:** The default is stdio, which suits local agents. The `--transport http` option exists if you need a shared server, but you'd then be running it yourself.
- **Naming:** Long operation names can exceed 64 characters, and the README warns about this. Abbreviation is on by default; `DISABLE_ABBREVIATION` turns it off.

**Alternative:** [FastMCP's `from_openapi()`](https://gofastmcp.com/integrations/openapi) (Python) can also turn a spec into an MCP server. I did not confirm its license, so check that before adopting it. Its docs also say auto-generated servers work better when curated, so either tool benefits from filtering to the operations your agents actually need.

I did not verify the exact current npm version or whether the package's flags changed recently. Check the README on the version you install.

Sources:
- [ivo-toby/mcp-openapi-server (GitHub README)](https://github.com/ivo-toby/mcp-openapi-server)
- [lobehub listing for ivo-toby mcp openapi server](https://lobehub.com/bg/mcp/ivo-toby-mcp-openapi-server) (cross-check only; its flag names conflicted with the README)
- [FastMCP OpenAPI integration docs](https://gofastmcp.com/integrations/openapi)