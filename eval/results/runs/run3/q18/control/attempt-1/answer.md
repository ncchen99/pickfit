I haven't run anything or changed any files. This is based on the projects' docs.

## Recommendation: use ollmcp (MCP Client for Ollama)

[ollmcp](https://github.com/jonigl/mcp-client-for-ollama/wiki) fits what you described:
- It's a free, open-source (MIT) terminal chat app for local Ollama models.
- It starts stdio MCP servers as subprocesses. Stdio is its default transport.
- It needs no account. It talks to your local Ollama at `http://localhost:11434`.
- It can reload your servers without restarting (`rs`), which is useful while you work on your own server.

### Install
```bash
# Requires Python 3.10+ and Ollama already installed
uv tool install --upgrade ollmcp      # or: pipx install ollmcp / pip install --upgrade ollmcp
```

### First run
1. **Pull a model that supports tool calling.** Models without tool support will chat but never call your tools.
   ```bash
   ollama pull qwen2.5:7b      # or qwen3, llama3.1:8b, mistral-nemo, etc.
   ```
   Make sure Ollama is running: `systemctl status ollama` or `ollama serve`.

2. **Add your stdio servers.** The command to launch each server goes after `--`.
   ```bash
   # Filesystem server, limited to the directories you list
   ollmcp mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem ~/projects ~/notes

   # Your own server (adjust the command to how you launch it)
   ollmcp mcp add ourtool --env API_MODE=local -- python3 /path/to/our_server.py
   # or: ollmcp mcp add ourtool -- uv run --directory /path/to/ourtool server.py

   ollmcp mcp list
   ```

3. **Start chatting.**
   ```bash
   ollmcp --model qwen2.5:7b
   ```
   It connects to the saved servers on its own. Use the in-app help to switch tools on or off, change models, or reload servers (`rs`) after you edit your server code.

Flags and subcommands have changed between versions, so check `ollmcp --help` and `ollmcp mcp --help` for the version you install.

## Keeping everything on your machine
- **Avoid Ollama cloud models.** Models with a `:cloud` tag, or anything reached through ollama.com sign-in, run remotely. Use only models you've pulled locally.
- **Downloads are separate from your chats.** Installing ollmcp, pulling models and the first `npx -y` fetch of the filesystem server all download from the internet. None of that sends your conversations anywhere. To be fully offline afterward, install the filesystem server once (`npm i -g @modelcontextprotocol/server-filesystem`) and point the command at it instead of using `npx -y`.
- **Leave the other providers off.** ollmcp can also talk to OpenAI-compatible endpoints. As long as you only use Ollama on localhost, nothing goes out.
- **Limit what the model can touch.** Give the filesystem server only the directories you want the model to read or write. Keep ollmcp's tool confirmation on so you approve each tool call.

## Alternatives
- **[MCPHost](https://github.com/mark3labs/mcphost)** is a Go CLI. Install it with `go install github.com/mark3labs/mcphost@latest`. You list servers in `~/.mcphost.json` or `.yml`, then run `mcphost -m ollama:qwen2.5:7b`. It's a good choice if you'd rather have a single binary and a config file, or want to use it in scripts. Its config format has changed between versions (newer ones use `"type": "local"` for stdio), so check the README ([ClickHouse guide](https://clickhouse.com/docs/guides/use-cases/ai-ml/MCP/ollama) has an example).
- **oterm** is a full-screen terminal chat app built for Ollama, and it also supports MCP servers. It's worth a look if you mainly want a nicer chat window.

Sources:
- [mcp-client-for-ollama wiki](https://github.com/jonigl/mcp-client-for-ollama/wiki)
- [ollmcp on PyPI](https://pypi.org/project/mcp-client-for-ollama/0.35.1/)
- [mcp.so listing](https://mcp.so/servers/mcp-client-for-ollama)
- [ClickHouse: MCP with Ollama (MCPHost)](https://clickhouse.com/docs/guides/use-cases/ai-ml/MCP/ollama)
- [MCPHost PR/README](https://github.com/mark3labs/mcphost/pull/44/files)
- [localaimaster Ollama MCP guide](https://localaimaster.com/blog/ollama-mcp-integration)