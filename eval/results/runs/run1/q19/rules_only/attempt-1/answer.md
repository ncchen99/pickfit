I recommend **Aider** (Apache-2.0, [aider.chat](https://aider.chat)). It's a mature open-source coding agent that runs in the terminal. It reads and edits the files in your repo and connects to any OpenAI-compatible endpoint. It needs no account or login. Its analytics are opt-in, and you can turn them off for good.

**Two caveats:**
- I checked the install and analytics details against Aider's current docs. pickfit hasn't tested Aider, though. pickfit's own suggestions were weak matches: the closest, Nedster, is built around Ollama and doesn't mention OpenAI-compatible endpoints. So I'm not recommending those.
- I'm assuming you're on macOS (that's what this machine runs) and that your model server is at something like `https://llm.internal.example.com/v1`.

## Install (macOS)

```bash
python3 -m pip install aider-install
aider-install          # puts aider in its own isolated environment
```
(`pipx install aider-chat` or `uv tool install aider-chat` also work.)

## Lock it down before the first run

1. **Point it at your server** (for example in `~/.zshrc`):
   ```bash
   export OPENAI_API_BASE="https://llm.internal.example.com/v1"
   export OPENAI_API_KEY="anything-or-your-internal-key"   # use any placeholder if your server doesn't check keys
   ```
2. **Turn off outbound extras.** Add this to `~/.aider.conf.yml`:
   ```yaml
   analytics-disable: true      # permanent opt-out; same as running `aider --analytics-disable` once
   check-update: false          # no PyPI version check
   show-release-notes: false
   ```
   Also add this to your shell profile:
   ```bash
   export LITELLM_LOCAL_MODEL_COST_MAP=True   # stops LiteLLM (inside Aider) from downloading its model price list from GitHub
   ```
   I'm fairly sure the `check-update` and `LITELLM_LOCAL_MODEL_COST_MAP` settings work as described, but I didn't confirm them against today's docs. The only reliable proof is to watch the network. For the first run, use Little Snitch/LuLu or your egress firewall, or block outbound traffic except to your LLM host. Then check that Aider only contacts your server.

## First run

```bash
cd ~/code/your-repo
aider --model openai/<your-model-name>
```
- Keep the `openai/` prefix. It tells Aider to use the generic OpenAI-compatible client.
- It may warn about an "unknown model" (no context size or cost info). You can ignore that, or add the details in `.aider.model.settings.yml`.
- Add files to the chat with `/add src/foo.py`, then describe the change you want. Aider edits the files and, by default, makes a git commit for each change, which makes it easy to undo with `/undo`. Use `--no-auto-commits` if you don't want that.
- Results depend heavily on how well your model follows Aider's edit formats. Strong instruction-following code models such as Qwen-Coder or DeepSeek-Coder do best. If edits keep failing, try `--edit-format whole`.

## Alternatives (not verified by pickfit)
- **OpenCode** (MIT, sst/opencode): a terminal agent with a nicer interface and more autonomy (it runs commands and works across many files). It supports custom OpenAI-compatible providers in `opencode.json`. To keep it offline, you'd also need to turn off auto-update and session sharing (`"share": "disabled"`) and confirm it doesn't fetch its model list from models.dev. That's more lockdown work than Aider needs.
- **OpenAI Codex CLI** (Apache-2.0): it can use a custom `model_provider` with your `base_url` and no login. But it's designed around OpenAI's own models, and smaller self-hosted models often struggle with its tool-calling.

Whichever you choose, test it once behind a firewall that only allows your model server. That's the evidence your security team will want, more than any vendor promise.