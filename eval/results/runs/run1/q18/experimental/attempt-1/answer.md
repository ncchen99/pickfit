I'd recommend **`ollmcp`** ([mcp-client-for-ollama](https://github.com/jonigl/mcp-client-for-ollama)). It's an MIT-licensed terminal chat client made for Ollama. It runs your local models and starts stdio MCP servers as tools. You don't need an account, and it talks to your local Ollama.

**What I assumed:** Ollama runs at the default `localhost:11434`, and you have Python 3.11+ or `uv`.

**Before you install**, I checked these limits:
- I didn't install or test ollmcp. Everything here comes from its README, which I read today (2026-11-02).
- The README says it **checks for new versions** to show update notices. That's an outbound request, but it doesn't send your chats. If you need zero network traffic, look in the source or settings for a way to turn the check off, or block it with a firewall.
- `npx -y @modelcontextprotocol/server-filesystem` downloads from npm the first time it runs. To stay offline after that, install it ahead of time: `npm i -g @modelcontextprotocol/server-filesystem`.
- Tool calling only works with **models that support tools**. The README lists qwen3.5, llama3.2, mistral and gemma4. Small models often call tools badly, so use the largest tool-capable model your laptop can handle.

## Install
```bash
uv tool install --upgrade ollmcp     # or: pip install --upgrade ollmcp
ollama pull qwen3.5                  # or another tool-capable model you already have
```

## Add your MCP servers (stdio is the default)
```bash
# Filesystem server, limited to one directory
ollmcp mcp add --scope user filesystem -- npx -y @modelcontextprotocol/server-filesystem /home/you/projects

# Your own stdio server
ollmcp mcp add --scope user myserver --env MY_VAR=value -- python3 /path/to/your_server.py
ollmcp mcp list
```
`--scope user` saves the servers in `~/.config/ollmcp/mcp.json`. If you want a config you can commit with your project, use `--scope project` instead, which writes a `.mcp.json` in the repo.

You can also skip the `add` commands and pass a JSON file with `ollmcp -j servers.json`:
```json
{ "mcpServers": {
    "filesystem": { "command": "npx", "args": ["-y","@modelcontextprotocol/server-filesystem","/home/you/projects"] },
    "myserver":   { "command": "python3", "args": ["/path/to/your_server.py"], "env": {"MY_VAR":"value"} }
}}
```

## First run
```bash
ollmcp -m qwen3.5
```
- Inside the chat, type `/model` to switch models.
- Try a prompt that should use a tool, such as *"List the files in /home/you/projects and summarize README.md"*. Then try one that should call your own server's tool.
- If something goes wrong, the logs are in `~/.config/ollmcp/logs/`.

## Other options
- **MCPHost** (`mark3labs/mcphost`, MIT): a Go client that runs `mcphost -m ollama/<model>` and reads servers from `~/.mcphost.yml`. It works, but it was **archived on 13 April 2026** and gets no more updates. Its authors point to **Kit** (`github.com/mark3labs/kit`) as the replacement. I haven't checked Kit myself.
- My recommendation tool (pickfit) suggested `python-ai-agent-ollama`. That's a prototype, and nothing showed it supporting MCP servers, so it doesn't do what you need.

Sources:
- https://github.com/jonigl/mcp-client-for-ollama
- https://github.com/mark3labs/mcphost