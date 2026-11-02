I recommend **`mlx-lm`'s built-in server (`mlx_lm.server`)**. It's Apple's own MLX language-model package (MIT license) and runs from the terminal with no GUI and no account. It serves OpenAI-style `POST /v1/chat/completions` and `GET /v1/models`, streams responses when the request sets `"stream": true`, and takes either a Hugging Face repo or a local folder through `--model`.

**What I assumed:** You're on a recent macOS with Python 3.10 or later. I didn't run anything on your machine. I checked the start command, the endpoints and streaming against the current `SERVER.md` in the `ml-explore/mlx-lm` repo. That page doesn't list `--host`/`--port`, so I've taken those flag names from memory. Run `mlx_lm.server --help` to confirm them.

## Install

Pick one:

```bash
# Option A: isolated CLI install (recommended)
brew install uv            # or: pipx, if you already use it
uv tool install mlx-lm

# Option B: a plain virtualenv
python3 -m venv ~/.venvs/mlx && source ~/.venvs/mlx/bin/activate
pip install -U mlx-lm
```

## First run

1. **Quick test in the terminal** (downloads the model to `~/.cache/huggingface` the first time):
   ```bash
   mlx_lm.generate --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --prompt "Write hello world in Rust"
   ```
   Any repo under `mlx-community/` on Hugging Face is already in MLX format. Choose a size that fits your unified memory. Roughly, 7–8B 4-bit models need about 5 GB and 30B-class 4-bit models need about 18 GB.

2. **Start the server:**
   ```bash
   mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --host 127.0.0.1 --port 8080
   # local folder instead:
   mlx_lm.server --model ~/models/my-mlx-model
   ```
   The default is `localhost:8080`. Keep it on `127.0.0.1`: the docs say the server has only basic security checks and isn't meant for production.

3. **Check streaming:**
   ```bash
   curl -N http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"messages":[{"role":"user","content":"Say hi"}],"stream":true,"max_tokens":50}'
   ```
   You should see `chat.completion.chunk` events arrive as they're generated. `curl http://127.0.0.1:8080/v1/models` lists the models available locally.

4. **Point your editor or tools at it:**
   - Base URL: `http://127.0.0.1:8080/v1`
   - API key: any placeholder, such as `sk-local`. Some clients require a value even though the server doesn't check it.
   - Model name: the HF repo id or the local path you started the server with.

## Optional extras

- **Convert your own model:** `mlx_lm.convert --hf-path <hf-repo> -q --mlx-path ~/models/name-4bit` turns a regular Hugging Face model into a quantized MLX folder.
- **Long contexts:** `--kv-bits 4` quantizes the KV cache to save memory. Pair it with `--prefill-step-size 512`. With this flag on, the server handles one request at a time.
- **LoRA adapters:** set these per request with the `adapters` field, not with a startup flag.

## Alternatives (also free, terminal-only, MLX-based)

- **mlx-omni-server:** use this if you need more of the OpenAI API, such as tool/function calling, embeddings or audio endpoints, or an Anthropic-style endpoint.
- **vllm-mlx:** use this if you need several requests at once (continuous batching) instead of mostly single-user editor traffic.

For one person's coding tools, plain `mlx_lm.server` is the simplest choice and needs the least upkeep.

Source: [mlx-lm SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)