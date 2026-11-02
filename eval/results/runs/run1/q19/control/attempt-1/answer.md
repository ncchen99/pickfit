# Recommendation: Aider, with OpenCode as the alternative

**Main pick: [Aider](https://aider.chat)** (Apache-2.0, Python, runs in the terminal).

- **Reads and edits your repo:** You add files to the chat and Aider writes the edits directly to disk. It also uses a repo map so the model understands the rest of the codebase. If you're in a git repo, it commits each change, so every edit is easy to review or undo.
- **Works with your own server:** It connects to any OpenAI-compatible endpoint through LiteLLM. You only set a base URL and a model name.
- **No account or login:** You only need an API key if your own server asks for one, and it can be a dummy value otherwise.
- **Telemetry is off unless you agree:** Analytics only run if you opt in. Aider sometimes asks a random sample of users whether they want to, and `--analytics-disable` turns it off permanently. You can also send analytics to your own PostHog instance.
- **Handles self-hosted models well:** It edits files with text formats like search/replace blocks and diffs, so it doesn't need reliable function calling. That matters because function calling is often weak in open-weight models.

**Limitation:** Aider is more a pair programmer than a fully autonomous agent. It doesn't run shell commands on its own. You trigger them with `/run` and `/test`, and it can automatically run your linter and tests after each edit. If you want the agent to explore and run commands by itself, see OpenCode below.

**Assumptions:** you're on macOS, your server serves `/v1/chat/completions` at something like `https://llm.internal.example.com/v1`, and its model ID is something like `qwen-coder`. Replace these with your real values.

## Install

```bash
# Option A (recommended): isolated install with uv
brew install uv
uv tool install --python 3.12 aider-chat

# Option B: pipx
brew install pipx && pipx install aider-chat
```

The install pulls packages from PyPI, but no code is sent anywhere. If your company requires it, point uv or pip at an internal package mirror.

## Configure (once per repo, or in `~/.aider.conf.yml` for all repos)

`.aider.conf.yml`:
```yaml
model: openai/qwen-coder          # "openai/" prefix = generic OpenAI-compatible
openai-api-base: https://llm.internal.example.com/v1
openai-api-key: dummy             # or your server's real key; better: set via env
analytics-disable: true           # permanently off
check-update: false               # no PyPI version check
show-release-notes: false
show-model-warnings: false        # silence "unknown model" warnings
auto-commits: true                # set false if you don't want auto git commits
```

Add this to your shell profile. It stops LiteLLM from downloading its model price list from GitHub at startup:
```bash
export LITELLM_LOCAL_MODEL_COST_MAP=True
export OPENAI_API_KEY=...         # if your server needs auth
```

Optional: Aider won't know your model's context size. To tell it, create `.aider.model.metadata.json`:
```json
{ "openai/qwen-coder": { "max_input_tokens": 131072, "max_output_tokens": 8192,
  "input_cost_per_token": 0, "output_cost_per_token": 0, "litellm_provider": "openai", "mode": "chat" } }
```

## First run

```bash
cd your-repo
aider src/foo.py src/bar.py       # files you want it allowed to edit
```
Then in the chat:
```
> add input validation to parse_config and a unit test for it
> /test pytest -q                 # run tests; failures go back to the model
> /undo                           # revert the last AI commit if you dislike it
```
Use `/add` and `/drop` to change which files it can edit, `/ask` to ask questions without editing, and `/help` to see all commands.

## Alternative: OpenCode, if you want a more autonomous agent

[OpenCode](https://opencode.ai) is MIT-licensed and has a terminal UI. It lets the model use tools on its own: reading, searching, editing and running shell commands. It works best with a model that handles tool calling well.

```bash
brew install sst/tap/opencode     # or: npm i -g opencode-ai
```
`opencode.json` in the repo:
```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "inhouse": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "In-house LLM",
      "options": { "baseURL": "https://llm.internal.example.com/v1", "apiKey": "{env:INHOUSE_KEY}" },
      "models": { "qwen-coder": { "name": "Qwen Coder", "limit": { "context": 131072, "output": 8192 } } }
    }
  },
  "model": "inhouse/qwen-coder",
  "autoupdate": false,
  "share": "disabled"
}
```
Run `opencode` in the repo, then use `/models` to pick your model.

Some caveats:
- **Downloads at runtime:** It fetches the `@ai-sdk/openai-compatible` npm package the first time it runs, so you need npm access or an internal mirror.
- **Background network calls:** By default it downloads a model catalog from models.dev. I believe the environment variable `OPENCODE_DISABLE_MODELS_FETCH=1` turns that off, but I haven't checked it against the current docs.
- **Sharing:** Keep `share` set to `disabled` so nobody can accidentally publish a session to opencode.ai.

## Enforce it on the network as well

Settings only control what the tool tries to do. To actually guarantee that code never leaves, add an egress rule so developer machines can reach only your LLM host, a package mirror, and other approved destinations. Then a future update or a wrong setting can't send code out.

I didn't install or run anything here. I checked Aider's analytics behavior and OpenCode's custom-provider config against their current docs.

Sources:
- [Aider analytics docs](https://aider.chat/docs/more/analytics.html)
- [OpenCode providers docs](https://opencode.ai/docs/providers/)