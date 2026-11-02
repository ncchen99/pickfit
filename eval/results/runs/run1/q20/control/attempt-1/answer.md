# You don't need a proxy: point the script at Ollama directly

Ollama already serves an OpenAI-compatible API at `http://localhost:11434/v1`. The official `openai` Python package reads its endpoint and key from environment variables, so you may not have to change your script at all.

## Steps

**1. Check that Ollama is running and has a model:**
```bash
ollama list                      # shows the models you've pulled
curl http://localhost:11434/v1/models
```
If you have no models yet, pull one, for example `ollama pull llama3.1`.

**2. Set the base URL and key before running the script:**
```bash
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama     # the client needs a value, but Ollama ignores it
python your_script.py
```
This works as long as the script creates a plain `OpenAI()` client. If it passes `base_url=` or `api_key=` in the code, change those values there instead:
```python
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
```

**3. Handle the model name.** The script probably asks for something like `model="gpt-4o"`, and Ollama will return "model not found" for that. You have two options:
- Change the model string in the script to a local model, such as `"llama3.1"`.
- Or, if you don't want to edit the script, create an alias so the OpenAI name maps to a local model:
  ```bash
  ollama cp llama3.1 gpt-4o
  ```

## What works and what doesn't
- **Works:** `chat.completions` (including streaming, and tool calling or JSON mode on models that support them), `completions`, `embeddings` and `models.list`. Recent Ollama versions also support the Responses API to some degree. Check the OpenAI compatibility page in Ollama's docs for your version.
- **Doesn't work:** OpenAI-hosted features such as Assistants/threads, file uploads, fine-tuning, batch, and image generation.

## When a gateway would make sense: LiteLLM Proxy
Install a gateway only if you need things Ollama can't do by itself, such as:
- mapping many OpenAI model names to local models,
- falling back to OpenAI's cloud when a local call fails,
- API keys, logging or spend tracking,
- serving several machines or backends.

LiteLLM is the standard choice for that.

```bash
pipx install 'litellm[proxy]'     # or: pip install 'litellm[proxy]' in a venv
```
Create a `config.yaml`:
```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: ollama_chat/llama3.1
      api_base: http://localhost:11434
```
Start it:
```bash
litellm --config config.yaml --port 4000
```
Then set `OPENAI_BASE_URL=http://localhost:4000` and `OPENAI_API_KEY=anything`. If you configure a master key in LiteLLM, use that key instead.

## Assumptions
- The script and Ollama run on the same Ubuntu machine. If they don't, run Ollama with `OLLAMA_HOST=0.0.0.0` (for the systemd service, set it with `sudo systemctl edit ollama`), use the desktop's IP address in the URL, and make sure the port isn't exposed to untrusted networks.
- The script uses chat completions or something similar, not Assistants or other cloud-only features.

My recommendation is to use Ollama's built-in endpoint with the two environment variables, and add LiteLLM only if you later need routing or fallback.