I recommend **ollmcp** (the `mcp-client-for-ollama` project by jonigl). It's a free, open-source terminal chat client built for Ollama. It starts your MCP servers as local stdio subprocesses and lets the model call their tools. It needs no account, and it only talks to your local Ollama at `http://localhost:11434` by default. It reads the same `mcpServers` JSON format as Claude Desktop, so a filesystem server and your own stdio server go in one file.

**Assumptions:** you have Python 3.10+ and Ollama running locally, and Node.js if you use the official filesystem server. I didn't audit ollmcp's code for telemetry. I'm going by its design: it's a local client pointed at local Ollama. If you need proof that nothing leaves the machine, check the source or watch outbound traffic on the first run.

## Install

```bash
# Option A: install as a tool (pipx keeps it out of system Python)
pipx install ollmcp          # or: pip install --upgrade ollmcp

# Option B: run without installing
uvx ollmcp
```

Pick a model that supports **tool calling**, or it won't use the MCP tools. ollmcp's default is `qwen2.5:7b`. `llama3.1`/`3.2` and `qwen3` also support tools.

```bash
ollama pull qwen2.5:7b
```

## First run

1. Create `~/.config/ollmcp/servers.json` (the path is your choice):

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/YOU/projects"]
    },
    "ours": {
      "command": "python3",
      "args": ["/home/YOU/code/our_mcp_server/server.py"],
      "env": { "LOG_LEVEL": "info" }
    }
  }
}
```

   - Give the filesystem server only the directories you want the model to reach.
   - Use absolute paths for your own server. If it uses a virtualenv, set `command` to that venv's `python`.

2. Start it:

```bash
ollmcp --servers-json ~/.config/ollmcp/servers.json --model qwen2.5:7b
```

   To test just your own server, run `ollmcp --mcp-server /path/to/server.py`.

3. In the chat, ask it to list the tools or try something like "list the files in my projects folder." The interactive commands let you turn tools on or off, switch models, and save your choices. Saved settings go to `~/.config/ollmcp/config.json`.

## Network notes

Three things need the internet once; chatting doesn't:
- `pip`/`uvx` downloads ollmcp from PyPI when you install it.
- `npx -y` downloads the filesystem server on first use. If you want it to start fully offline later, install it globally with `npm i -g @modelcontextprotocol/server-filesystem` and point `command` at the installed binary.
- `ollama pull` downloads the model.

After that, chatting runs entirely on your laptop: Ollama on localhost plus the stdio servers it spawns.

Flags differ between ollmcp versions, so run `ollmcp --help` on the version you install.

## Alternative: MCPHost (`mark3labs/mcphost`)

This is a Go CLI with Ollama support, if you'd rather have a single binary than a Python tool:

```bash
go install github.com/mark3labs/mcphost@latest
```

It reads `~/.mcphost.yml` or `~/.mcphost.json` with an `mcpServers` section, where local servers use `"type": "local"`. Run it with something like `mcphost -m ollama:qwen2.5:7b`, and set `OLLAMA_HOST` if Ollama isn't on the default address. Its config format has changed between versions, so check the exact field names in the README.

Sources:
- [mcp-client-for-ollama on PyPI](https://pypi.org/project/mcp-client-for-ollama/)
- [PyPI 0.25.2](https://pypi.org/project/mcp-client-for-ollama/0.25.2/) · [0.28.1](https://pypi.org/project/mcp-client-for-ollama/0.28.1/) · [0.5.0](https://pypi.org/project/mcp-client-for-ollama/0.5.0/) · [0.3.0](https://pypi.org/project/mcp-client-for-ollama/0.3.0/)
- [mcpservers.org listing for jonigl/mcp-client-for-ollama](https://mcpservers.org/id/servers/jonigl/mcp-client-for-ollama)
- [MCPHost config notes (lobehub mirror)](https://lobehub.com/de/mcp/imashish-in-ollama-mcp)
- [mcp.so mcphost-server (a fork, for comparison)](https://mcp.so/servers/mcphost-server)