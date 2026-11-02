# Use Ollama's built-in OpenAI-compatible API instead of a proxy

You probably don't need to install anything. Ollama already serves an OpenAI-compatible API at `http://localhost:11434/v1`, which handles chat completions, completions, embeddings and model listing. The official `openai` Python package can connect to it directly. You only need to point the client at that address.

**Assumptions:** The script uses `openai` version 1.x or later, and Ollama runs on the same machine on its default port (11434). I didn't run anything on your machine.

## Setup and first run

1. **Check that Ollama is running and has a model:**
   ```bash
   systemctl status ollama        # or just: ollama list
   ollama pull llama3.1:8b        # use any model you want
   ```

2. **Test the endpoint:**
   ```bash
   curl http://localhost:11434/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"Say hi"}]}'
   ```

3. **Point the script at Ollama using environment variables.** The `openai` package reads both of these automatically, so you don't have to change the code:
   ```bash
   export OPENAI_BASE_URL=http://localhost:11434/v1
   export OPENAI_API_KEY=ollama     # the client needs a key; Ollama ignores it
   python your_script.py
   ```
   If the script sets `base_url` or `api_key` in the code, change it there instead:
   ```python
   client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
   ```

4. **Handle hardcoded model names.** If the script asks for something like `model="gpt-4o"`, either edit that line or make a copy of your model under that name:
   ```bash
   ollama cp llama3.1:8b gpt-4o
   ```
   Now requests for `gpt-4o` go to your local model.

## Things to watch for

- **Context length:** Ollama's default context window may be smaller than what your script expects. Long prompts can get cut off without any error. You can raise the limit, for example with `OLLAMA_CONTEXT_LENGTH=16384` in the Ollama service environment (`sudo systemctl edit ollama`), and then restart the service.
- **Unsupported endpoints:** The Assistants API, file uploads, fine-tuning and image generation won't work. Support for the newer Responses API depends on your Ollama version. If your script uses `client.responses...`, upgrade Ollama and test it.
- **Tool calling and JSON mode:** These work, but only with models that support them, such as Llama 3.1+, Qwen 2.5/3 or Mistral.

## When to add a gateway: LiteLLM Proxy

A gateway is worth it if you need model aliasing across several backends, a fallback to the real OpenAI service, virtual API keys, logging, or one endpoint that serves several machines. In that case, LiteLLM is the standard choice:

```bash
python3 -m venv ~/litellm && source ~/litellm/bin/activate
pip install 'litellm[proxy]'
```

`config.yaml`:
```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: ollama_chat/llama3.1:8b
      api_base: http://localhost:11434
```

```bash
litellm --config config.yaml       # serves on http://localhost:4000
export OPENAI_BASE_URL=http://localhost:4000
export OPENAI_API_KEY=anything     # or a master_key, if you set one
```

**Security note:** In March 2026, two LiteLLM releases on PyPI (1.82.7 and 1.82.8) were compromised in a supply-chain attack. Pin a version that the project's security advisories list as clean, and check those advisories before you install.

**Recommendation:** Use the environment variables in step 3. Only add LiteLLM if you hit one of the cases above.