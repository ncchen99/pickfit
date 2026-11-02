**Recommendation: `ollmcp` (MCP Client for Ollama)**, a Python terminal app that connects local Ollama models to MCP servers over stdio. It's free and open source, has no account or cloud service, and talks only to your local Ollama server and the MCP servers you configure. I didn't check the license or the source code, so confirm both on its [GitHub wiki](https://github.com/jonigl/mcp-client-for-ollama/wiki) and [PyPI page](https://pypi.org/project/mcp-client-for-ollama/) before you rely on it.

A good alternative is **MCPHost** (`mark3labs/mcphost`), a Go CLI that also supports Ollama and stdio servers, configured with a JSON or YAML file. Install it with `go install github.com/mark3labs/mcphost@latest`. Pick it if you'd rather have a single binary and a config file than a Python tool.

**Install and first run (Linux)**

1. Make sure Ollama is running and has a model that supports tool calling. Something like `qwen2.5` or `llama3.1` works:
   ```
   ollama pull qwen2.5:7b
   ```
   If Ollama isn't running as a service, start it with `ollama serve`.
2. Install `uv`, which keeps the tool in its own environment. Use your distro's package if you'd rather not run the install script.
   ```
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. Install the client:
   ```
   uv tool install --upgrade ollmcp
   ```
   Avoid `pip install` into the system Python. Recent Debian/Ubuntu systems block it, and `--break-system-packages` can break OS packages.
4. Register your MCP servers as stdio commands. The `--` separates the client's flags from the server command:
   ```
   ollmcp mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem /home/you/projects
   ollmcp mcp add mytool -- python3 /home/you/dev/mytool/server.py
   ollmcp mcp list
   ```
   Limit the filesystem server to the directories you want the model to see.
5. Start the chat:
   ```
   ollmcp
   ```
   Choose your model and confirm the tools from both servers are listed. Run `ollmcp --help` if a flag differs in your version.

**Privacy notes**

- Model inference stays on your machine through Ollama on `localhost`.
- `npx` downloads the filesystem server from npm the first time it runs. Your chats are not sent during that download, but it is a network fetch. Install it ahead of time if you want to avoid it.
- Your own server runs with your privileges. Anything it calls over the network is outside this setup, so review its code.

Sources:
- [MCPHost / MCP client for Ollama results (LobeHub listing)](https://lobehub.com/zh-TW/mcp/mark3labs-mcphost)
- [MCP Client for Ollama wiki](https://github.com/jonigl/mcp-client-for-ollama/wiki)
- [mcp-client-for-ollama on PyPI](https://pypi.org/project/mcp-client-for-ollama/)
- [How to use MCP servers with Ollama and local LLMs (DEV Community)](https://dev.to/hola_gus/how-to-use-mcp-servers-with-ollama-and-local-llms-f3)