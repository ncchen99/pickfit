I recommend **Aider** (Apache-2.0). It's a mature, free terminal coding agent. It reads your repo, edits files directly and commits each change to git. It works with any OpenAI-compatible endpoint and needs no vendor account or login. Its analytics are opt-in, and you can turn them off permanently.

**Assumptions:** you're on macOS (that's what this machine reports), and your model server serves `/v1/chat/completions`, as vLLM, llama.cpp server, Ollama, LM Studio and TGI all do. I haven't run anything here, so these steps come from Aider's docs, not a test install.

## Why Aider over the other options

- **OpenCode** (MIT) is a good agent, but its docs say it uses a "small model" for side tasks like session titles. By default that's **gpt-5-nano, hosted by OpenCode**, so some of your content could leave the network unless you override `small_model`. It also fetches model metadata from models.dev. You can lock it down, but it doesn't start out safe.
- **Codex CLI and Qwen Code** can also point at custom endpoints. But they're vendor-built tools whose defaults expect the vendor's services, so you'd have more settings to audit.
- **What pickfit offered:** Nedster (alpha, Ollama-only, its main feature wasn't tested) and orangu (runs its own GGUF models, only tested on Linux). Neither clearly fits the "our own OpenAI-compatible server" requirement, so I wouldn't use either here.

## Install (macOS)

Pick one:
```bash
brew install aider
# or
python3 -m pip install aider-install && aider-install
# or
pipx install aider-chat
```
Aider needs `git`, because it commits its edits.

## Lock it down before first use

Create `~/.aider.conf.yml`:
```yaml
analytics-disable: true      # permanent opt-out (same as running `aider --analytics-disable` once)
check-update: false          # no PyPI version check
show-release-notes: false
model: openai/<your-model-name>
openai-api-base: https://llm.internal.example.com/v1
```
Then add this to your shell profile (`~/.zshrc`):
```bash
export OPENAI_API_KEY=<internal-key-or-any-dummy-string>
export LITELLM_LOCAL_MODEL_COST_MAP=True   # stop LiteLLM fetching model metadata from GitHub
```
I'm fairly sure about the LiteLLM variable, but check that it works on your version.

If Aider warns about an "unknown model", add a `.aider.model.metadata.json` file that sets the context window. The warning is harmless.

## First run

```bash
cd /path/to/your/repo
aider                                # uses the config above
# or with explicit flags:
aider --model openai/<model-name> --openai-api-base https://llm.internal.example.com/v1 --no-analytics
```
Inside Aider:
```
/add src/utils.py            # put files in the chat so Aider can edit them
Add type hints to parse_config and handle a missing file gracefully.
/diff                        # see what it changed
/undo                        # revert the last AI commit if you don't like it
```
Two useful flags: `--no-auto-commits` if you'd rather commit yourself, and `--edit-format whole` if your model has trouble with diff-style edits. That's common with smaller models.

## Recommendations
1. **Back the settings up with a network rule.** Config flags can drift between versions. A firewall or proxy rule that only lets developer machines reach your model server (plus package mirrors during install) is the only real guarantee that code stays inside.
2. **Use a strong coding model.** How well Aider works depends mostly on the model. Pick a modern open coding model with a large context window, ideally 32k tokens or more.