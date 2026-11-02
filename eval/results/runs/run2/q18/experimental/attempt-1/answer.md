I recommend **ollmcp** (`mcp-client-for-ollama`, MIT license). It's a Python terminal chat client made for Ollama. You point it at stdio MCP servers using the usual `mcpServers` JSON format, and the model calls their tools while you chat. You don't need an account or an API key, and it talks to your local Ollama at `http://localhost:11434` by default.

**How I checked:** I didn't run anything on your machine. I looked in pickfit's index of tested tools and it had nothing for this request. The details below come from the project's README. The README doesn't mention telemetry either way, so if you need to be certain nothing leaves the machine, read the source or watch its network traffic once.

**Assumptions:** You have Python 3.11 or newer, Ollama is already running, and your own server runs as a command such as `python server.py`.

## Install

```bash
uv tool install --upgrade ollmcp     # recommended
# or: pip install --upgrade ollmcp
# or run without installing: uvx ollmcp
```

You also need a model that supports tool calling. For example:
```bash
ollama pull qwen2.5:7b      # llama3.1 and qwen3 also handle tools
```

## Configure your servers

Create a file such as `~/.config/ollmcp/mcp-servers/config.json`. The README suggests keeping it separate from `~/.config/ollmcp/config.json`, which only stores the app's own preferences.

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/you/projects"]
    },
    "ourserver": {
      "command": "python",
      "args": ["/home/you/code/our-mcp-server/server.py"],
      "env": { "LOG_LEVEL": "info" }
    }
  }
}
```

The `npx` line downloads the filesystem server from npm the first time it runs. To stay fully offline after that, install it globally with `npm i -g @modelcontextprotocol/server-filesystem` and use the installed binary as the `command`. The filesystem server can only read and write the directories you list in `args`.

## First run

```bash
ollmcp -j ~/.config/ollmcp/mcp-servers/config.json -m qwen2.5:7b
```

Once it's running:
- `/tools` (`/t`) shows the tools from both servers and lets you turn them on or off.
- Try asking: *"List the files in /home/you/projects and summarize the README."*
- `/human-in-the-loop` (`/hil`) turns approval prompts on or off before each tool call. Leave them on while you test the filesystem server.
- `/reload-servers` (`/rs`) reconnects the servers after you edit your own server's code.
- `/model` switches models, `/save-config` saves your settings, and `/quit` exits.

There's also a shortcut for quick tests of your own server: `ollmcp -s ./server.py -m qwen2.5:7b`. It accepts `.py` and `.js` files and can be repeated.

## Other options

- **mcphost** (Go, MIT) works well with Ollama: `mcphost -m ollama/qwen2.5:7b`, with servers listed in `~/.mcphost.yml`. However, its README says the project is **archived** and points users to its successor, **Kit** (`github.com/mark3labs/kit`). I haven't checked Kit, so try ollmcp first.

## Tips

- If tool calls fail or the model makes them up, the model is usually the cause, not the client. Use a model with tool support, preferably 7B or larger.
- Your stdio server must write only MCP messages to stdout. Send logs to stderr, or the connection will break.

Sources:
- [jonigl/mcp-client-for-ollama](https://github.com/jonigl/mcp-client-for-ollama)
- [mark3labs/mcphost](https://github.com/mark3labs/mcphost)