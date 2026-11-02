**Recommendation: don't install a proxy. Ollama already serves an OpenAI-compatible API at `http://localhost:11434/v1`.** Point the `openai` client at it. This is the simplest option and adds nothing to maintain.

I'm assuming your script uses chat completions, which Ollama supports. I haven't run anything on your machine.

## Install and first run (Ubuntu)

1. **Install Ollama**, if you don't have it. This pipes a script into `sh`, so review it first if you prefer:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```
2. **Pull a model** (pick one that fits your RAM/VRAM):
   ```bash
   ollama pull llama3.2
   ```
3. **Check the endpoint** responds:
   ```bash
   curl http://localhost:11434/v1/models
   ```
4. **Change the client in your script.** The simplest route needs no code change, because the `openai` package reads these environment variables automatically:
   ```bash
   export OPENAI_BASE_URL=http://localhost:11434/v1
   export OPENAI_API_KEY=ollama   # any non-empty string; Ollama ignores it
   python your_script.py
   ```
   Or set it in code:
   ```python
   from openai import OpenAI

   client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
   resp = client.chat.completions.create(
       model="llama3.2",  # must match a name from `ollama list`
       messages=[{"role": "user", "content": "Say hi"}],
   )
   print(resp.choices[0].message.content)
   ```

## Things to watch

- **Model names:** If the script passes `gpt-4o` or similar, Ollama will reject it. Change the name to a local model, or use the LiteLLM option below.
- **Unsupported features:** Some OpenAI-only features (Assistants API, file uploads, fine-tuning, some parameters) won't work. Chat, streaming, and common tool calling generally do, depending on the model.
- **Keep the script's OpenAI calls unchanged** by using the env vars above, so the same script can still reach OpenAI when you want it to.

## When a gateway is worth it

If you need model-name aliasing (keep `gpt-4o` in code but route it to a local model), logging, or routing across several providers, use **LiteLLM Proxy**:

```bash
pip install 'litellm[proxy]'
```

Then write a config that maps `gpt-4o` to `ollama/llama3.2` with `api_base: http://localhost:11434`, and run `litellm --config config.yaml`. Point the script at `http://localhost:4000`. This is a well-established option, but it adds a service to run. I haven't verified its current config syntax, so check its docs first.

I didn't use pickfit or web search for this, since Ollama's built-in compatibility layer answers the question directly. Let me know if your script uses features beyond chat completions and I'll check what's supported.