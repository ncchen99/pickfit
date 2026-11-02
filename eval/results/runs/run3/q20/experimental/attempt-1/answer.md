# You probably don't need a proxy

**My recommendation is to skip the gateway.** Ollama already serves an OpenAI-compatible API at `http://localhost:11434/v1`. The official `openai` Python package (v1.x and later) can use it if you set two environment variables, so you have nothing extra to install or keep running.

I'm assuming the script calls Chat Completions (`client.chat.completions.create`) or Embeddings, and that it builds its client with plain `OpenAI()`. If it hardcodes `base_url` or `api_key`, change those two arguments in the code instead.

## Steps (Ollama only)

1. **Check that Ollama is running and has a model:**
   ```bash
   ollama --version          # newer versions have better /v1 coverage
   ollama list               # see what you've pulled
   ollama pull llama3.2      # if you need a model (pick whatever you like)
   curl http://localhost:11434/v1/models
   ```

2. **Point the script at Ollama.** The `openai` package reads these variables automatically:
   ```bash
   export OPENAI_BASE_URL="http://localhost:11434/v1"
   export OPENAI_API_KEY="ollama"     # required by the client, ignored by Ollama
   python your_script.py
   ```

3. **Fix the model name.** Ollama will reject `model="gpt-4o"` unless a model by that name exists. You have two options:
   - Change the model string in the script to an Ollama tag, such as `"llama3.2"` or `"qwen2.5:7b"`.
   - If you can't edit the script, add an alias so the existing name works. This creates a copy under the new name:
     ```bash
     ollama cp llama3.2 gpt-4o
     ```

4. **Run a quick test:**
   ```python
   from openai import OpenAI
   c = OpenAI()  # picks up the env vars
   r = c.chat.completions.create(model="llama3.2",
         messages=[{"role": "user", "content": "Say hi"}])
   print(r.choices[0].message.content)
   ```

**Endpoints:** Ollama supports `/v1/chat/completions` (including streaming, tools/function calling, JSON mode and vision on capable models), `/v1/completions`, `/v1/embeddings` and `/v1/models`. Recent versions also support `/v1/responses`. Assistants, Files, Batch and most audio endpoints won't work.

## When to add a gateway: LiteLLM Proxy

Install a proxy only if one of these applies:
- The script uses endpoints or parameters Ollama doesn't handle.
- You want several model names mapped to different local models without making copies.
- You want an API key, logging or rate limits in front of Ollama.
- You want to fall back to the real OpenAI when a local model fails.

**Install** in a virtual environment, not with system pip:
```bash
sudo apt install python3-venv          # if needed
python3 -m venv ~/litellm-venv
~/litellm-venv/bin/pip install 'litellm[proxy]'
```
Pin a version you've checked against recent security advisories. LiteLLM is a large, fast-moving package that has had supply-chain problems before.

**Configure** it in `~/litellm-config.yaml`:
```yaml
model_list:
  - model_name: gpt-4o                 # name your script asks for
    litellm_params:
      model: ollama_chat/llama3.2      # the Ollama model that answers
      api_base: http://localhost:11434
  - model_name: text-embedding-3-small
    litellm_params:
      model: ollama/nomic-embed-text
      api_base: http://localhost:11434
```

**Run it:**
```bash
~/litellm-venv/bin/litellm --config ~/litellm-config.yaml --port 4000
```

**Point the script at the proxy:**
```bash
export OPENAI_BASE_URL="http://localhost:4000/v1"
export OPENAI_API_KEY="anything"   # or set a master_key in the config and use that
```

## Troubleshooting

- **404 "model not found":** the model name doesn't match anything in `ollama list` (step 3).
- **Connection refused:** Ollama isn't running. Start it with `systemctl status ollama` or `ollama serve`.
- **Slow or truncated answers:** local models have a smaller default context window. Raise `num_ctx` with a Modelfile or use a bigger model.

I didn't run any of these commands. They're based on Ollama's and LiteLLM's documented behaviour, so check the versions on your machine.