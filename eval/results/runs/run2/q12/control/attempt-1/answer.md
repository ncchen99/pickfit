# Running MLX models behind a local OpenAI-compatible server

## Recommendation: `mlx-lm` and its built-in server (`mlx_lm.server`)

`mlx-lm` is Apple's own MLX language-model package from the `ml-explore` org. It's MIT-licensed, runs only in the terminal and needs no account. It includes an HTTP server that implements the OpenAI `/v1/chat/completions`, `/v1/completions` and `/v1/models` endpoints. It streams responses as server-sent events when a request sets `"stream": true`. You can give `--model` either a Hugging Face repo ID (it downloads and caches the model) or a local folder.

**My assumptions:** you have an M-series Mac with a recent macOS and a native arm64 Python 3.10 or newer. I wrote this from what I know and didn't check it against the latest release, so check `mlx_lm.server --help` for the exact flags on your version.

### Install (choose one)

```bash
# Option A: isolated CLI tool with uv (cleanest)
brew install uv
uv tool install mlx-lm

# Option B: plain pip in a virtual environment
python3 -m venv ~/.venvs/mlx && source ~/.venvs/mlx/bin/activate
pip install -U mlx-lm

# Option C: Homebrew formula, if you prefer
brew install mlx-lm
```

### First run

1. **Quick test from the terminal.** This also downloads the model:
   ```bash
   mlx_lm.generate --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit \
     --prompt "Write a Python function that reverses a string."
   ```
   Models in the `mlx-community` org on Hugging Face are already converted to MLX and don't need a login. A 4-bit 7B model uses about 5 GB of memory. With 32 GB or more you can try 14B–32B coder models.

2. **Start the server:**
   ```bash
   mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit \
     --host 127.0.0.1 --port 8080
   ```
   To use a local folder instead: `--model ~/models/my-mlx-model`. The folder needs `config.json`, `*.safetensors` and the tokenizer files.

3. **Check that streaming works:**
   ```bash
   curl -N http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
          "messages":[{"role":"user","content":"Hello"}],
          "stream":true,"max_tokens":200}'
   ```
   You should see `data: {...}` chunks arrive one after another, ending with `data: [DONE]`.

4. **Point your editor or coding tool at it:**
   - Base URL: `http://127.0.0.1:8080/v1`
   - API key: any placeholder, such as `sk-local`. The server ignores it, but some clients require one.
   - Model: the same repo ID or path you passed to `--model`.

### Useful extras

- **Converting a model that isn't on `mlx-community`:**
  `mlx_lm.convert --hf-path Qwen/Qwen2.5-Coder-7B-Instruct -q --mlx-path ~/models/qwen-coder-7b-4bit`
  (`-q` quantizes to 4-bit by default.)
- **Offline use:** downloaded models are stored in `~/.cache/huggingface/hub`. After the first download, setting `HF_HUB_OFFLINE=1` stops any network calls.
- **Gated models** like some Llama versions are the only case where you'd need a Hugging Face token. Choosing ungated `mlx-community` models avoids needing an account at all.
- **Big models near your RAM limit:** macOS caps how much memory the GPU can use. You can raise that cap with `sudo sysctl iogpu.wired_limit_mb=<MB>`. It resets when you reboot.

### Caveats

- The project describes the server as basic and not meant for production. Keep it bound to `127.0.0.1`. It runs one model at a time and handles one request at a time, which is fine for a single person.
- Whether tool calling or function calling works depends on the model and your `mlx-lm` version. If your coding agent relies on tools, test it early.

## Alternatives, if `mlx_lm.server` falls short

- **mlx-omni-server** (`pip install mlx-omni-server`): built on MLX and also provides OpenAI-compatible endpoints. It has more complete tool calling and structured output, and can switch between multiple models.
- **vllm-mlx**: a vLLM-style server on MLX with continuous batching. It's worth a look if you send several requests at once.
- **Not recommended for what you described:** LM Studio has MLX support, but it's a GUI app. Ollama uses its own model store, not plain Hugging Face or local MLX folders, so it doesn't fit your setup as well.

As you asked, I didn't run anything or change any files on your machine.