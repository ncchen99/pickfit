I'd use **ollmcp** ([mcp-client-for-ollama](https://github.com/jonigl/mcp-client-for-ollama)). It's an MIT-licensed terminal chat client for Ollama that can use stdio MCP servers, plus SSE and HTTP ones. It talks only to your local Ollama, and you don't need an account.

I haven't run any of this; it comes from the projects' READMEs. pickfit's tested catalog had nothing for this request, so none of the tools below were checked in a sandbox. I'm assuming you have Python plus `uv` or `pip`, and Node.js if you want the official filesystem server.

## Main pick: ollmcp

**Install**
```bash
uv tool install --upgrade ollmcp      # recommended
# or: pip install --upgrade ollmcp
# or try it without installing: uvx ollmcp
```

**Pull a model that supports tool calling.** Tool use only works with models trained for it, such as `qwen2.5`, `qwen3` or `llama3.1`:
```bash
ollama pull qwen2.5:7b
ollama serve        # if Ollama isn't already running
```

**Set up your servers** in a file such as `~/mcp-servers.json`:
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/you/projects"]
    },
    "ourserver": {
      "command": "python3",
      "args": ["/path/to/our_server.py"],
      "env": { "SOME_VAR": "value" }
    }
  }
}
```
Change `/home/you/projects` to the folders the model is allowed to touch, and change the second entry to however you start your own server.

**First run**
```bash
ollmcp -m qwen2.5:7b -j ~/mcp-servers.json
```
To check it works, ask something like *"List the files in /home/you/projects and summarize the README."* You should see the model call the filesystem tool.

Useful extras:
- `/model` (or `/m`) switches models during a chat.
- `ollmcp mcp add <name> -- <command...>` registers a stdio server from the command line.
- `-s ./server.py` points straight at a single server script, which helps when testing your own server.

**Privacy:** the client connects to your local Ollama (`localhost:11434`) and starts the stdio servers as local processes. One exception: `npx -y` downloads the filesystem server package from npm the first time it runs. To stay fully offline after that, install it once with `npm i -g @modelcontextprotocol/server-filesystem` and use that binary as the command. I couldn't confirm from the README whether ollmcp has telemetry. If that matters to you, check the source or watch its network traffic.

## Alternatives
- **mcphost** (Go, MIT). It does the same job (`mcphost -m ollama/qwen2.5:7b`, configured in `~/.mcphost.yml`), but the repository is **archived and no longer maintained**. Its README tells users to move to **Kit** ([mark3labs/kit](https://github.com/mark3labs/kit)). I haven't checked whether Kit supports Ollama and stdio servers the same way.
- **oterm**. A full-screen terminal UI for Ollama that also supports MCP tools. Try it if you want something more polished than a plain chat prompt. I haven't verified its current setup steps.

Sources:
- https://github.com/jonigl/mcp-client-for-ollama
- https://github.com/mark3labs/mcphost