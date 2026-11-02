# You probably don't need a proxy: point the script at Ollama directly

**My recommendation is to install nothing extra.** Ollama already serves an **OpenAI-compatible API** at `http://localhost:11434/v1`. It supports chat completions, completions, embeddings and model listing. The official `openai` Python package (v1.x) reads `OPENAI_BASE_URL` and `OPENAI_API_KEY` from the environment, so you may not even need to edit the script.

I'm assuming the script uses `openai` v1 or later (`from openai import OpenAI`) and calls chat completions.

## Steps

1. **Check that Ollama is running and has a model:**
   ```bash
   ollama list                      # see installed models
   ollama pull llama3.1             # if you need one
   curl http://localhost:11434/v1/models
   ```

2. **Point the script at Ollama with environment variables:**
   ```bash
   export OPENAI_BASE_URL=http://localhost:11434/v1
   export OPENAI_API_KEY=ollama     # needed by the client, but Ollama ignores it
   python your_script.py
   ```
   You can also set it in code:
   ```python
   client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
   ```

3. **Fix the model name.** If the script asks for a fixed name like `"gpt-4o"`, Ollama will return "model not found." You can either change the name in the script to a local model (e.g. `"llama3.1"`), or make a copy of the local model under the OpenAI name so the script works unchanged:
   ```bash
   ollama cp llama3.1 gpt-4o
   ```

4. **Test it quickly:**
   ```bash
   curl http://localhost:11434/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Say hi"}]}'
   ```

**Limits:** Plain chat, streaming, JSON mode, embeddings and (with models that support it) tool calling work well. Newer endpoints are less certain. If your script uses the Assistants API, the Responses API (`client.responses.create`), audio or image generation, check Ollama's OpenAI-compatibility docs for your version. Some of these may not be supported.

## If you do want a gateway: LiteLLM Proxy

A gateway is worth adding if you want name mapping, fallback to the real OpenAI, several backends, API keys or request logging. LiteLLM is the standard choice for that.

```bash
python3 -m venv ~/litellm && source ~/litellm/bin/activate
pip install 'litellm[proxy]'
```

`config.yaml`:
```yaml
model_list:
  - model_name: gpt-4o              # name your script asks for
    litellm_params:
      model: ollama_chat/llama3.1   # local Ollama model
      api_base: http://localhost:11434
```

Run it and point the script at it:
```bash
litellm --config config.yaml        # listens on port 4000 by default
export OPENAI_BASE_URL=http://localhost:4000
export OPENAI_API_KEY=anything      # or a master_key if you configure one
python your_script.py
```

**In short:** start with Ollama's built-in `/v1` endpoint and two environment variables. Add LiteLLM only if you need features Ollama doesn't provide.