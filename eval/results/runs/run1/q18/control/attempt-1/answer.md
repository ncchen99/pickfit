Yes. I'd use **ollmcp** ([mcp-client-for-ollama](https://pypi.org/project/mcp-client-for-ollama/0.5.0/)). It's a free, open-source terminal chat client made for Ollama. It runs stdio MCP servers (it also supports SSE and Streamable HTTP) and talks to Ollama at `http://localhost:11434`. It needs no account and has no cloud backend. A good second choice is **MCPHost** from mark3labs, which I cover below.

I'm assuming Ollama runs locally on the default port, you have Python 3.10+ and Node.js (for the filesystem server), and your own server is a Python or Node script started from the command line. I didn't run anything on your machine.

## Main recommendation: ollmcp

### 1. Pick a model that supports tool calling
Tools only work if the model supports tool calling. Good local options are `qwen2.5` / `qwen3`, `llama3.1` / `llama3.2`, and `mistral-nemo`. ollmcp's default model is `qwen2.5:7b`.
```bash
ollama pull qwen2.5:7b
```

### 2. Install
```bash
pipx install ollmcp          # or: uv tool install ollmcp
# one-off without installing: uvx ollmcp
```

### 3. Describe your servers in a standard `mcpServers` JSON file
For example, save this as `~/mcp-servers.json`:
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/you/projects"]
    },
    "ourserver": {
      "command": "python3",
      "args": ["/home/you/code/our-mcp-server/server.py"],
      "env": { "LOG_LEVEL": "info" }
    }
  }
}
```
Give the filesystem server only the directories you want the model to access.

### 4. First run
```bash
ollmcp --servers-json ~/mcp-servers.json --model qwen2.5:7b
# or, for a single script: ollmcp --mcp-server /path/to/server.py --model qwen2.5:7b
```
When it starts, check that both servers and their tools are listed. Then ask something like "list the files in my projects folder" and watch the tool call happen. Inside the client you can switch models, turn individual tools on or off, and save the setup. The docs say saved configs go in `~/.config/ollmcp/`, but one third-party listing gives a different path, so check what your version actually uses.

If you start ollmcp with no server options, it tries to find servers in a Claude Desktop config. Pass `--servers-json` explicitly so it uses only your servers.

## Alternative: MCPHost (single Go binary)
[MCPHost](https://gb.xjqchip.workers.dev/mark3labs/mcphost) is a CLI host that supports Ollama models through `ollama:<model>`.
```bash
go install github.com/mark3labs/mcphost@latest
```
It reads `~/.mcphost.json` or `~/.mcphost.yml`. Its server format is slightly different: `command` is an array and stdio servers use `"type": "local"`:
```json
{
  "mcpServers": {
    "filesystem": { "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/home/you/projects"] },
    "ourserver": { "type": "local",
      "command": ["python3", "/home/you/code/our-mcp-server/server.py"] }
  }
}
```
```bash
mcphost -m ollama:qwen2.5:7b      # add --config /path/to/file to use a different config
```
Older versions used `$HOME/mcp.json` and a different format, so follow the README for the version you install.

## Making sure nothing leaves your machine
- **The clients:** both only talk to your local Ollama and the servers you list.
- **`npx -y`:** this downloads the filesystem server package from npm the first time. That's a download, not your data going out. To avoid even that, install it once with `npm i -g @modelcontextprotocol/server-filesystem` and run the installed binary directly.
- **Your servers:** MCP servers can make their own network calls, so data could still leave through a server you add. Your filesystem server and your own server are fine if they don't make network requests.
- **To confirm:** leave `OLLAMA_HOST` at `127.0.0.1`, then watch connections with `ss -tp` while you chat, or test with Wi-Fi turned off.

Sources:
- [mcp-client-for-ollama on PyPI](https://pypi.org/project/mcp-client-for-ollama/0.5.0/)
- [x-cmd: mcp-client-for-ollama](https://x-cmd.com/install/mcp-client-for-ollama)
- [LobeHub: jonigl/mcp-client-for-ollama](https://lobehub.com/zh/mcp/jonigl-mcp-client-for-ollama)
- [mark3labs/mcphost (mirror)](https://gb.xjqchip.workers.dev/mark3labs/mcphost)
- [mcphost-server on mcp.so (a separate fork)](https://mcp.so/servers/mcphost-server)