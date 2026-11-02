I recommend **Aider**. It's open source (Apache-2.0), runs in the terminal, and works inside a git repo. It reads your files, edits them, and commits each change. It can use any OpenAI-compatible endpoint, and it needs no account or login.

Aider wasn't on the list of tested tools I checked. I confirmed its endpoint and analytics settings from its official docs, but I haven't installed it.

## Why Aider fits
- **Self-hosted endpoint:** set `OPENAI_API_BASE` to your server and add the `openai/` prefix to the model name. It works with vLLM, llama.cpp server, Ollama's `/v1`, TGI, LiteLLM proxy and similar servers.
- **No account:** it only needs an API key, and that can be any placeholder if your server doesn't check keys.
- **Telemetry:** analytics are opt-in. By default Aider asks a random subset of users whether they want to share analytics. Running `--analytics-disable` once turns it off for good, and you'll never be asked.
- **Other outbound calls:** these don't send code, but you should switch them off anyway (see below). Aider checks PyPI for updates and may download model metadata. I'm not certain the metadata setting below covers every case, so check it with a firewall or proxy log.

## Install (macOS)
```bash
python3 -m pip install aider-install
aider-install          # installs aider in its own isolated environment via uv
```
If your network is locked down, you can use `pipx install aider-chat` or `uv tool install aider-chat` against an internal PyPI mirror instead.

## Configure (once)
Put this in your shell profile:
```bash
export OPENAI_API_BASE=https://llm.internal.example.com/v1   # your server
export OPENAI_API_KEY=dummy-or-real-key
export LITELLM_LOCAL_MODEL_COST_MAP=True   # stop fetching model metadata from GitHub
```
Optionally, add `~/.aider.conf.yml` so these settings apply to everyone:
```yaml
model: openai/<your-model-name>
analytics-disable: true
check-update: false
show-release-notes: false
```

## First run
```bash
aider --analytics-disable          # once, to permanently opt out
cd /path/to/your/repo
aider --model openai/<your-model-name>
```
Inside Aider:
- Run `/add src/foo.py` to put files in its working set.
- Ask for a change, e.g. "add input validation to parse_config and a test for it." Aider edits the file and makes a git commit.
- Run `/diff` to review the change and `/undo` to revert it.

**Assumptions:**
- Your server exposes `/v1/chat/completions`.
- The model is at least about 30B-class coder quality, such as Qwen-Coder. Small models often don't follow Aider's edit format well.
- If you see warnings about context size or an unknown model, they're harmless. You can set limits with `--model-metadata-file`.

## Alternatives
- **OpenCode** (MIT): a more "agentic" terminal UI that can also run shell commands. It supports custom OpenAI-compatible providers in `opencode.json`. To keep it fully internal, you'd need to turn off its session sharing and auto-update. Like Aider, I haven't tested it.
- **The tested-tools list I checked** offered Nedster and orangu, and neither is a good fit for you:
  - **Nedster** is alpha and built around Ollama.
  - **orangu** is built around its own on-device GGUF models rather than a remote OpenAI-compatible server. It was only tested on Linux.

  Neither tool's core coding loop was actually exercised in testing.

Whatever you choose, run it once behind an egress firewall (Little Snitch or a proxy log) to confirm it only contacts your model server. That gives you concrete evidence for your security team.

Sources:
- [Aider analytics docs](https://aider.chat/docs/more/analytics.html)
- [Aider OpenAI-compatible API docs](https://aider.chat/docs/llms/openai-compat.html)