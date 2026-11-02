I'd go with **Aider** (Apache-2.0, runs in the terminal, `pip install aider-chat`).

**My assumptions:** you're on macOS (that's what this machine runs). Your model server (vLLM, llama.cpp, Ollama, TGI, LiteLLM, etc.) serves `/v1/chat/completions`. Your repo is a git repo. I haven't run anything here; the flags below come from Aider's current documentation.

## Why Aider fits
- **Free and open source**, with no vendor account or login.
- **Reads and edits files in your repo directly.** It also maps the codebase, shows diffs and commits each change to git, so every edit can be undone.
- **Works with any OpenAI-compatible endpoint:** set `OPENAI_API_BASE` and use `--model openai/<your-model-name>`.
- **Telemetry is opt-in, and you can switch it off for good.** The docs say "analytics are only collected if you agree and opt-in." Setting `--analytics-disable` (or `AIDER_ANALYTICS_DISABLE=true`) turns it off permanently.
- **One other outbound call to turn off:** by default it checks PyPI for updates. Disable that with `--no-check-update`.

## Install
Use a Python 3.10–3.12 environment. Any one of these works:
```bash
# Option A: uv (isolated tool install)
uv tool install --python 3.12 aider-chat

# Option B: pipx
pipx install aider-chat

# Option C: the official installer
python -m pip install aider-install && aider-install
```
If your machines can't reach the internet, install from your internal PyPI mirror, or build a wheelhouse on a connected machine and copy it over.

## Lock down the config
Put this in `~/.aider.conf.yml`, or in `.aider.conf.yml` at the repo root so the whole team shares it:
```yaml
model: openai/your-model-name          # e.g. openai/qwen3-coder
openai-api-base: https://llm.internal.example.com/v1
analytics-disable: true                # permanent opt-out, no prompt
check-update: false                    # no PyPI calls
show-release-notes: false
detect-urls: false                     # don't offer to fetch URLs found in chat
show-model-warnings: false             # quiet "unknown model" warnings for self-hosted names
auto-commits: true                     # every edit becomes an undoable git commit
```
Then set the key in your shell. If your server doesn't check keys, any placeholder like `sk-local` works:
```bash
export OPENAI_API_KEY=sk-local
```
Aider doesn't know the context window of a self-hosted model, so describe it in `.aider.model.metadata.json`:
```json
{
  "openai/your-model-name": {
    "max_input_tokens": 131072,
    "max_output_tokens": 8192,
    "input_cost_per_token": 0,
    "output_cost_per_token": 0,
    "litellm_provider": "openai",
    "mode": "chat"
  }
}
```

## First run
```bash
cd /path/to/your/repo
aider                          # picks up the config above
```
Inside the session:
- `/add src/foo.py src/bar.py` adds files to the chat so Aider can edit them.
- Then just type a request, e.g. `Add input validation to parse_config and a unit test`.
- `/diff` shows what changed, and `/undo` reverts the last Aider commit.
- `/ask ...` asks a question without editing anything. `/architect` uses a plan-then-edit mode.
- `/run pytest` runs a command and lets you send its output back to the model.

If your server is only reachable over plain HTTP or uses an internal CA, set `SSL_CERT_FILE` or `REQUESTS_CA_BUNDLE` to your CA bundle. Don't turn off TLS checking.

## Check that nothing leaks
Before rolling it out, run one session with a firewall like LuLu or Little Snitch, or with egress rules that only allow your model host. Confirm the only traffic goes to your endpoint. Pin the Aider version you've checked.

## Alternatives
- **OpenCode** (MIT, terminal UI, more of an "agent" feel with tool calls and sub-agents). In `opencode.json`, add a provider using `@ai-sdk/openai-compatible` with `options.baseURL` pointing at your server. The provider docs don't say anything about telemetry or update checks, so audit its network traffic before approving it.
- **OpenAI Codex CLI** (Apache-2.0). It can use a custom `model_providers` entry in `~/.codex/config.toml` pointing at your endpoint, without signing in. Its defaults are built around OpenAI, though, so check its egress the same way.
- **Avoid:** Charm's Crush, whose license isn't OSI-approved. Also avoid Gemini-CLI forks unless you've confirmed usage statistics are turned off, because the upstream sends them by default.

Choose Aider if you want git-backed edits with little setup. Choose OpenCode if you want a more autonomous agent that runs tools and multi-step tasks.

Sources:
- [Aider analytics](https://aider.chat/docs/more/analytics.html)
- [Aider OpenAI-compatible APIs](https://aider.chat/docs/llms/openai-compat.html)
- [Aider options reference](https://aider.chat/docs/config/options.html)
- [OpenCode providers](https://opencode.ai/docs/providers/)