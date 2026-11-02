**Recommendation: `ollmcp` (mcp-client-for-ollama)**, a free, MIT-licensed Python terminal client. It connects to your local Ollama server, supports stdio MCP servers, and its README documents no telemetry or account requirement.

I have not run anything on your machine. Install and first-run steps below are from the project docs, not from a sandboxed install.

**Install (Linux, Python 3.11+)**

Recommended, using uv:
```
uv tool install --upgrade ollmcp
```
Or with pip:
```
pip install --upgrade ollmcp
```

**First run**

1. Make sure Ollama is running and has a model. If you don't have one yet:
   ```
   ollama pull llama3.2:3b
   ```
   Use a model that supports tool calling. Small models often handle tools poorly, so test with one you trust.
2. Add your servers. Everything after `--` is the launch command:
   ```
   ollmcp mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem /home/you/projects
   ollmcp mcp add mytools -- python /path/to/your_server.py
   ```
   Use `-e KEY=VALUE` to pass environment variables.
3. Start the client, choosing the model:
   ```
   ollmcp --model llama3.2:3b
   ```
   You can switch models in the session with `/model`.

**Things to check**

- **Keep it local:** the default host is `http://localhost:11434`. Don't select Ollama Cloud models, a non-Ollama `--provider`, or remote SSE/HTTP MCP servers if nothing should leave the machine.
- **Logs** go to `~/.config/ollmcp/logs/`. The client checks for new versions over the network, and the README doesn't say how. Block that check if you need zero outbound traffic.
- **Your own server:** if it fails to connect, run its launch command by hand first to confirm it speaks MCP over stdio.

**Alternatives**

- **MCPHost** (`go install github.com/mark3labs/mcphost@latest`, MIT) also works with Ollama and stdio servers, using a `.mcphost.yml` config. However, its repo is archived and the maintainers recommend migrating to Kit (github.com/mark3labs/kit), so I wouldn't start new work on it.
- **Goose** is a well-known open-source agent that may fit. Pickfit has not verified it, so I haven't checked its Linux support, offline behavior or setup.

Pickfit's own database returned no verified picks for this request, so the recommendation rests on the project docs and not on a pickfit install test.

Sources:
- [mark3labs/mcphost](https://github.com/mark3labs/mcphost)
- [jonigl/mcp-client-for-ollama](https://github.com/jonigl/mcp-client-for-ollama)
- [ollmcp on PyPI](https://pypi.org/project/mcp-client-for-ollama/0.30.0/)
- [MCPHost overview (LobeHub)](https://lobehub.com/nl/mcp/mark3labs-mcphost)