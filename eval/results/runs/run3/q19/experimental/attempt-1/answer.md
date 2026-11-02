I recommend **Aider** (Apache-2.0, `github.com/Aider-AI/aider`). It's a mature open-source coding agent that runs in the terminal. It reads and edits files in your repo, can run your tests and linter, and commits its changes to git. It works with any OpenAI-compatible endpoint, needs no account or login, and its analytics are opt-in only, with a flag to turn them off for good.

**My assumptions:** you're on macOS, the model server is something like vLLM, llama.cpp server, TGI or LiteLLM at a URL such as `https://llm.internal.example/v1`, and the model is a decent coding model, ideally 30B or larger. Aider's output is only as good as the model behind it.

## Why Aider fits your rules
- **Self-hosted endpoint:** set `OPENAI_API_BASE` to your server and use `--model openai/<model-name>`. The `openai/` prefix tells it to use the OpenAI-compatible protocol.
- **No login:** it only needs a key in `OPENAI_API_KEY`. If your server doesn't check keys, any placeholder string works.
- **Telemetry:** Aider's docs say analytics are collected only if you opt in. Running `aider --analytics-disable` once turns them off permanently.
- **Other outbound calls to block:** Aider also checks for updates, and its model library (LiteLLM) can download a model-pricing file from GitHub. Neither sends code, but turn both off (step 3) if your policy is strict. To be sure, run a session behind a firewall or proxy that only allows your model host.

## Install
```bash
# Option A: the official installer (it pulls in uv and Python)
python3 -m pip install aider-install
aider-install

# Option B: if you already use pipx or uv
pipx install aider-chat        # or: uv tool install aider-chat
```

## First run
1. Point Aider at your server, in `~/.zshrc` or your shell profile:
   ```bash
   export OPENAI_API_BASE="https://llm.internal.example/v1"
   export OPENAI_API_KEY="dummy-or-your-internal-key"
   export LITELLM_LOCAL_MODEL_COST_MAP=True   # don't download model pricing from GitHub
   ```
2. Turn analytics off permanently (run once):
   ```bash
   aider --analytics-disable
   ```
3. Optionally, add `~/.aider.conf.yml` (or put it in the repo root) so you don't have to type flags each time:
   ```yaml
   model: openai/your-model-name
   analytics-disable: true
   check-update: false
   show-release-notes: false
   ```
4. Start it from the repo:
   ```bash
   cd /path/to/your/repo
   aider --model openai/your-model-name src/foo.py src/foo_test.py
   ```
   Then ask, for example: `add input validation to parse_config and a test for it`. Aider shows the diff, writes the change and makes a git commit, which you can undo with `/undo`. Use `/add` and `/drop` to change which files are in the chat, and `/run pytest` to feed test output back to the model.

You'll probably see a warning that the model is unknown, because Aider doesn't know your model's context size. You can ignore it, or set the context size in `.aider.model.settings.yml`.

## Alternative
**OpenCode** (`sst/opencode`, MIT) is a more "agentic" terminal app with a full-screen interface. You configure an OpenAI-compatible provider with a `baseURL` in `opencode.json`. Set `"share": "disabled"` and `"autoupdate": false`. I didn't check its telemetry behavior as carefully as Aider's, so test it behind your firewall first.

## What I didn't recommend
The pickfit tool suggested two lesser-known tools, Nedster and orangu, but neither is a good fit:
- **Nedster** is alpha software built around Ollama.
- **orangu** was checked only on Linux, and pickfit couldn't confirm it works with an OpenAI-compatible endpoint.
- Pickfit didn't see the main coding features of either tool working.

I haven't installed any of these tools myself, and I didn't run anything on your machine.

Sources:
- [Aider analytics](https://aider.chat/docs/more/analytics.html)
- [Aider with OpenAI-compatible APIs](https://aider.chat/docs/llms/openai-compat.html)