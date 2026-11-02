# You probably don't need a proxy

**My recommendation is to install nothing extra.** Ollama already serves an OpenAI-compatible API at `http://localhost:11434/v1`. The official `openai` Python package can talk to it directly once you point it there. Only add a gateway if you hit one of the limits listed further down. In that case, use **LiteLLM Proxy**.

## Steps (no new software)

I'm assuming your script uses `openai` v1 or later (`from openai import OpenAI`) and runs on the same Ubuntu machine as Ollama.

**1. Check that Ollama is running and has a model:**
```bash
ollama list                      # see installed models
ollama pull llama3.2             # or any model you prefer, if none listed
curl http://localhost:11434/v1/models   # should return JSON listing your models
```

**2. Point the script at Ollama.** You can do this without changing any code, using environment variables:
```bash
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama     # required by the client but ignored by Ollama; any value works
python your_script.py
```
Or set it in code:
```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
```

**3. Fix the model name.** Ollama won't recognize a name like `"gpt-4o"`. Either change the script to use a local name such as `model="llama3.2"`, or, if you can't edit the script, give a local model that name:
```bash
ollama cp llama3.2 gpt-4o        # the script's "gpt-4o" requests now go to llama3.2
```

**4. Quick test:**
```python
r = client.chat.completions.create(model="llama3.2",
        messages=[{"role": "user", "content": "Say hi"}])
print(r.choices[0].message.content)
```

**If the script runs on a different machine:** by default Ollama only listens on localhost. To change that, run `sudo systemctl edit ollama` and add:
```
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```
Then run `sudo systemctl restart ollama` and use `http://<desktop-ip>:11434/v1`. Only do this on a network you trust, because Ollama has no authentication.

## When to add LiteLLM Proxy instead

Use it if you need any of these:
- To map many OpenAI model names to local models, or to route between Ollama and cloud providers
- Real API keys, rate limits, logging, or spend tracking in front of Ollama
- To smooth over endpoints or parameters that Ollama's compatibility layer handles poorly

Ollama supports chat completions, completions, embeddings, and model listing. It doesn't support things like Assistants, Files, or Batch, and support for newer endpoints depends on your Ollama version. A proxy won't add these features either, because the local model still has to do the work.

**Install and first run:**
```bash
python3 -m venv ~/litellm && source ~/litellm/bin/activate
pip install 'litellm[proxy]'
```
Create `config.yaml`:
```yaml
model_list:
  - model_name: gpt-4o            # name your script asks for
    litellm_params:
      model: ollama_chat/llama3.2  # actual local model
      api_base: http://localhost:11434
```
```bash
litellm --config config.yaml --port 4000
```
Then point the script at it:
```bash
export OPENAI_BASE_URL=http://localhost:4000
export OPENAI_API_KEY=anything   # unless you set a master_key in the config
```

**Summary:** start with the two environment variables plus the right model name (or an `ollama cp` alias). That covers most scripts that only use `chat.completions`.