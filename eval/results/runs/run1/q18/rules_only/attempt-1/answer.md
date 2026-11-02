I recommend **ollmcp** (`mcp-client-for-ollama`, MIT license). It's a terminal chat app made for exactly this setup. It talks to your local Ollama at `http://localhost:11434` and launches stdio MCP servers from a config file in the usual `mcpServers` JSON format, the same one Claude Desktop uses. You don't need an account or API key when you use the Ollama provider.

I first checked pickfit's catalogue of tested tools, but nothing in it actually matches this need. Its closest picks were model servers, not MCP clients. So this recommendation comes from my own knowledge and the project's current README. I haven't installed it myself.

## Install and first run

I'm assuming Python 3.11+ (required), Ollama already running, and a model that supports tool calling, such as `qwen3`, `qwen2.5`, `llama3.1`/`llama3.2` or `mistral-nemo`. Models without tool support will chat but won't call tools.

1. **Install it:**
   ```bash
   uv tool install --upgrade ollmcp     # recommended
   # or: pip install --upgrade ollmcp
   ```

2. **Pull a model that can call tools**, if you don't have one:
   ```bash
   ollama pull qwen3:8b
   ```

3. **Write a server config**, for example `~/.config/ollmcp/mcp-servers/config.json`:
   ```json
   {
     "mcpServers": {
       "filesystem": {
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/you/projects"]
       },
       "ours": {
         "command": "/usr/bin/python3",
         "args": ["/home/you/code/our-mcp-server/server.py"],
         "env": { "LOG_LEVEL": "info" }
       }
     }
   }
   ```
   Use absolute paths. Only give the filesystem server the directories it actually needs. You can turn a server off with `"disabled": true`.

4. **Start chatting:**
   ```bash
   ollmcp -j ~/.config/ollmcp/mcp-servers/config.json -m qwen3:8b
   ```
   For quick tests you can skip the JSON file and point it at a script with `ollmcp -s ./server.py` (it accepts `.py`/`.js` scripts, and you can repeat the flag).

5. **First task:** ask something like *"List the files in /home/you/projects and summarize the README."* You should see a filesystem tool call, then the answer. Inside the app you can turn individual tools on or off and require approval before each tool runs. With a small local model, keeping only the tools you need switched on makes its tool choices more reliable.

## Privacy

- With the Ollama provider, everything stays on your machine: the model, the client and the stdio servers.
- The client has an **update notification** feature. It probably checks PyPI for new versions, which is a small outbound request. The README doesn't mention telemetry.
- `npx -y` downloads the filesystem server from npm the first time it runs. If you want nothing fetched at runtime, install it globally once and point `command` at that binary.
- Nothing has to touch the network after setup, but that's only true if your own MCP servers stay offline too.
- ollmcp can also use cloud providers, such as OpenAI. Leave the provider set to Ollama and don't save an API key, because keys passed with `--api-key` are stored in plain text.

## Alternatives if ollmcp doesn't suit you

All of these are free and open source and work with Ollama and stdio MCP servers. I haven't checked their current versions.
- **mcphost** (Go, single binary, from mark3labs): similar config format. Run it with `-m ollama:qwen3:8b`.
- **oterm**: a fuller terminal UI for Ollama that also supports MCP tools.
- **Goose CLI** (Block): a heavier agent tool that works with Ollama and supports MCP "extensions". It's a good fit if you want more of an autonomous agent than a chat client.

Sources:
- [jonigl/mcp-client-for-ollama (GitHub)](https://github.com/jonigl/mcp-client-for-ollama)