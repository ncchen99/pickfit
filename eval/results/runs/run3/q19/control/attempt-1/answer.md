My top pick is **Aider**. It's free and open source (Apache‑2.0), runs in the terminal, and reads and edits files in your repo. It needs no account or login, works with any OpenAI‑compatible endpoint, and its analytics can be turned off for good with one setting.

I haven't run anything on your machine. I've assumed your server is at `http://llm.internal:8000/v1` and serves a model called `qwen-coder`. Replace those with your real values.

## Main recommendation: Aider

**Why it fits**
- You point it at your server with `openai-api-base`, or the `OPENAI_API_BASE` environment variable. The model name needs an `openai/` prefix so Aider sends requests to your endpoint.
- Analytics: `--analytics-disable` turns it off permanently. Putting it in the config file covers everyone.
- It works best inside a git repo, where it commits each change it makes. That makes changes easy to review and undo with `/undo` or `git revert`.

**Install** (Python 3.10–3.12; choose one)
```bash
uv tool install --python 3.12 aider-chat     # if you use uv
# or
pipx install aider-chat
```
If your network can't reach PyPI, mirror `aider-chat` in your internal package index.

**Configure once.** Put this in `~/.aider.conf.yml`, or in the repo root to share it with the team:
```yaml
model: openai/qwen-coder
openai-api-base: http://llm.internal:8000/v1
openai-api-key: dummy-or-your-internal-key   # Aider needs a value even if your server ignores it
analytics-disable: true
check-update: false          # no PyPI version check
show-release-notes: false
detect-urls: false           # don't offer to fetch URLs that show up in chat
```
Also set this in your shell profile so the LiteLLM library inside Aider uses its bundled model list and doesn't download one from GitHub:
```bash
export LITELLM_LOCAL_MODEL_COST_MAP=True
```

**First run**
```bash
cd /path/to/your/repo
aider src/foo.py src/bar.py      # add the files you want it to edit
```
Then type a request, such as "add input validation to parse_config". Aider shows a diff, writes the change, and commits it. Commands you'll use often: `/add <file>`, `/drop <file>`, `/ask` (questions only, no edits), `/undo`, `/run <cmd>`.

If Aider warns about an unknown context window, add a `.aider.model.metadata.json` file with your model's token limits.

**Downsides:** Aider is more "pair programmer" than "autonomous agent." You choose which files it sees, and it runs shell commands only when you ask. Development has also slowed compared with its peak.

## Alternative: OpenCode (MIT)
Pick this if you want a more autonomous agent that explores the repo and runs commands by itself. You add your server as a custom provider in `~/.config/opencode/opencode.jsonc`, using `"npm": "@ai-sdk/openai-compatible"` and `"options": { "baseURL": "http://llm.internal:8000/v1" }`. No login is needed for a custom provider.

It has some outbound features you'd need to turn off: session sharing to opencode.ai, auto‑update, and fetching a model catalog. I believe the settings are `"share": "disabled"` and `"autoupdate": false`, but I couldn't confirm the exact names, so check the current config docs before you roll it out.

## Enforce it at the network level too
Config settings are easy to get wrong or change by mistake. To actually guarantee the policy, block the developer machines (or the tool) from reaching anything except your model server, using an egress firewall or proxy allowlist. Then a bad setting or a future update can't send code out. It's also worth checking once with a packet capture or Little Snitch that the only connections go to your server.

Sources:
- [Aider analytics docs](https://aider.chat/docs/more/analytics.html)
- [Aider OpenAI-compatible APIs](https://aider.chat/docs/llms/openai-compat.html)
- [Aider with a custom endpoint (DEV)](https://dev.to/futurmix/how-to-use-aider-with-any-llm-provider-custom-api-endpoint-2jl3)
- [OpenCode providers docs](https://opencode.ai/docs/en/providers/)
- [OpenCode custom provider setup](https://haimaker.ai/blog/opencode-custom-provider-setup/)