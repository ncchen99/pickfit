**Recommendation: don't install a proxy. Ollama already serves an OpenAI-compatible API at `http://localhost:11434/v1`.** Point the official `openai` client at it, and your script can often run unchanged.

I'm assuming Ollama is already installed and working, and that the script uses the `openai` v1 Python client (`from openai import OpenAI`). If you're on an older Ollama build, update it first.

## Setup

1. **Confirm Ollama is installed and running.** On Ubuntu the install script sets up a systemd service:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   systemctl status ollama
   ```
   If the service isn't running, start it with `sudo systemctl start ollama`, or run `ollama serve` in a separate terminal.

2. **Pull a model.** Use whichever fits your hardware:
   ```bash
   ollama pull llama3.2        # small, runs on most machines
   ollama pull qwen2.5-coder   # better for code
   ```

3. **Smoke-test the endpoint:**
   ```bash
   curl http://localhost:11434/v1/models
   ```
   You should see your pulled models listed.

## Point the script at Ollama

Option A: no code changes, using environment variables. The v1 `openai` client reads these by default:
```bash
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama   # required by the client, ignored by Ollama
python your_script.py
```

Option B: change the client in code:
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",  # any non-empty string
)

resp = client.chat.completions.create(
    model="llama3.2",  # must be an Ollama model name, not "gpt-4o"
    messages=[{"role": "user", "content": "Hello"}],
)
print(resp.choices[0].message.content)
```

**Things to check in your script:**
- **Model names.** Anything like `gpt-4o` or `gpt-4.1` must become a model you've pulled, such as `llama3.2`. If you don't want to edit every call, add a `model=` mapping at the top of the script.
- **Unsupported features.** Ollama covers chat completions, streaming, embeddings, and most tool calling and JSON mode, depending on the model. It does not support OpenAI-only APIs such as Assistants, Files, Batch, or fine-tuning. Check the Ollama OpenAI compatibility docs if your script uses one of those.

## When you'd want a gateway instead

Install **LiteLLM Proxy** only if you need something Ollama doesn't provide, such as one endpoint that routes to several backends (Ollama plus a cloud model), per-key limits, or logging:
```bash
python3 -m venv ~/litellm && source ~/litellm/bin/activate
pip install 'litellm[proxy]'
litellm --model ollama/llama3.2 --port 4000
```
Then set `base_url="http://localhost:4000"`. Start with the direct Ollama approach, since it has fewer moving parts.

Sources (from memory, not checked against live pages this session):
- Ollama OpenAI compatibility: https://github.com/ollama/ollama/blob/main/docs/openai.md
- LiteLLM proxy quickstart: https://docs.litellm.ai/docs/proxy/quick_start