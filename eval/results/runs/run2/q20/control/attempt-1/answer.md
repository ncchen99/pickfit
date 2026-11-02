# Recommendation: you probably don't need a proxy

Ollama already serves an **OpenAI-compatible API** at `http://localhost:11434/v1`. The official `openai` Python package can talk to it directly. You just point the client at that URL. Nothing extra to install.

**Assumptions:** your script uses `openai` v1.x or later and mostly calls `chat.completions` (and maybe `embeddings`), and Ollama runs on the same desktop as the script.

## Steps (no proxy)

1. **Check that Ollama is running and you have a model:**
   ```bash
   systemctl status ollama          # or: curl http://localhost:11434/api/version
   ollama list
   ollama pull llama3.1:8b          # if you don't have one yet; pick any model you like
   ```

2. **Test the OpenAI-compatible endpoint:**
   ```bash
   curl http://localhost:11434/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"Say hi"}]}'
   ```

3. **Point your script at Ollama.** The `openai` package reads these environment variables, so if the script creates `OpenAI()` with no arguments you may not need to edit it at all:
   ```bash
   export OPENAI_BASE_URL=http://localhost:11434/v1
   export OPENAI_API_KEY=ollama     # must be set, but Ollama ignores the value
   python your_script.py
   ```
   Or set it in code:
   ```python
   from openai import OpenAI
   client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
   ```

4. **Fix the model name.** If the script asks for `"gpt-4o"`, Ollama will return "model not found". You have two options:
   - Change the model string in the script to a local model, e.g. `"llama3.1:8b"`, or
   - Leave the script alone and create an alias in Ollama:
     ```bash
     ollama cp llama3.1:8b gpt-4o
     ```

### Things to watch for
- **Context length:** Ollama's default context window is smaller than OpenAI's. Long prompts can get cut off without any error. To raise it, set `OLLAMA_CONTEXT_LENGTH=16384` (or similar) in the Ollama service environment with `sudo systemctl edit ollama`, then restart the service.
- **Feature coverage:** chat, streaming, tools/function calling (on models that support it), JSON mode, vision and embeddings all work. Some OpenAI-only features won't: Assistants, file uploads, batch, `logprobs` and some Responses API features. Newer Ollama versions have basic `/v1/responses` support, so update Ollama if your script uses `client.responses`.

## When to add a gateway: LiteLLM Proxy

Install a gateway only if you need things Ollama doesn't do itself: mapping several OpenAI model names to local models in one config file, real API keys, usage logging, or falling back to OpenAI's cloud when a local model fails. In that case, **LiteLLM Proxy** is the standard choice.

**Install** (in a virtualenv, with the version pinned):
```bash
python3 -m venv ~/litellm-venv && source ~/litellm-venv/bin/activate
pip install 'litellm[proxy]==<current-stable-version>'
```
Pin a version you've checked against LiteLLM's GitHub releases and security notes. In 2026 some LiteLLM releases on PyPI were compromised, so don't install the latest version blindly.

**Configure** `~/litellm/config.yaml`:
```yaml
model_list:
  - model_name: gpt-4o                 # name your script asks for
    litellm_params:
      model: ollama_chat/llama3.1:8b   # what actually runs
      api_base: http://localhost:11434
  - model_name: text-embedding-3-small
    litellm_params:
      model: ollama/nomic-embed-text
      api_base: http://localhost:11434
```

**First run:**
```bash
litellm --config ~/litellm/config.yaml --port 4000
# in another shell:
export OPENAI_BASE_URL=http://localhost:4000
export OPENAI_API_KEY=anything     # or a master_key if you set one in the config
python your_script.py
```

## Summary
Start by setting `OPENAI_BASE_URL=http://localhost:11434/v1` and `OPENAI_API_KEY=ollama`, then match the model names. Most scripts work after that with no extra software. Add LiteLLM later only if you need model mapping, keys, logging or cloud fallback.