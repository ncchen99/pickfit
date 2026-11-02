# Recommendation: you probably don't need a proxy

Ollama already serves an **OpenAI-compatible API** at `http://localhost:11434/v1`. It covers chat completions, completions, embeddings and model listing. The official `openai` Python package (v1+) reads `OPENAI_BASE_URL` and `OPENAI_API_KEY` from the environment. So you can point the script at Ollama by setting two environment variables, without editing the code. The one thing to deal with is model names (step 3).

**My assumptions:** Ollama runs on the same Ubuntu machine as the script, it was installed the usual way (as a systemd service), and the script uses chat completions or embeddings rather than OpenAI-only features like Assistants, file uploads, DALL·E or Whisper.

## Steps (no install needed)

**1. Check that Ollama's OpenAI endpoint responds**
```bash
ollama list                                  # shows which models you have, e.g. llama3.1:8b
curl http://localhost:11434/v1/models        # should return JSON listing those models
```

**2. Point the script at Ollama**
```bash
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama    # the client requires a value; Ollama ignores it
python your_script.py
```

**3. Fix the model name.** If the script asks for something like `model="gpt-4o"`, Ollama won't recognise it. You can either:
- change the model string in the script to a local model, such as `"llama3.1:8b"`, or
- avoid editing the code by giving a local model an alias with the OpenAI name:
  ```bash
  ollama cp llama3.1:8b gpt-4o
  ```
  Requests for `gpt-4o` will then go to your local model.

**4. Quick test in Python**
```python
from openai import OpenAI
c = OpenAI()  # picks up the env vars
r = c.chat.completions.create(model="gpt-4o", messages=[{"role":"user","content":"Say hi"}])
print(r.choices[0].message.content)
```

Notes:
- If the script runs on a different machine or in Docker, Ollama has to listen on more than localhost. Run `sudo systemctl edit ollama`, add `Environment="OLLAMA_HOST=0.0.0.0:11434"`, then run `sudo systemctl restart ollama`. Only do this on a trusted network, because Ollama has no authentication.
- Tool or function calling and JSON mode only work if the local model supports them.

## When a real gateway is worth it: LiteLLM Proxy

Install a gateway only if you need things Ollama doesn't do itself: mapping many OpenAI model names in one config, API keys and rate limits, logging and spend tracking, or falling back to OpenAI's cloud when a local model fails. **LiteLLM** is the standard choice for that.

```bash
python3 -m venv ~/litellm && source ~/litellm/bin/activate
pip install 'litellm[proxy]'
```
Create `config.yaml`:
```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: ollama_chat/llama3.1:8b
      api_base: http://localhost:11434
  - model_name: text-embedding-3-small
    litellm_params:
      model: ollama/nomic-embed-text
      api_base: http://localhost:11434
```
Run it, then point the script at the proxy:
```bash
litellm --config config.yaml --port 4000
export OPENAI_BASE_URL=http://localhost:4000
export OPENAI_API_KEY=anything   # or a master_key if you set one in the config
```

**Summary:** start with Ollama's built-in `/v1` endpoint plus the two environment variables. Add LiteLLM only if you need name mapping across several models, cloud fallback, or access control.