My recommendation is **`mlx_lm.server`**, the server that comes with Apple's own `mlx-lm` package (ml-explore/mlx-lm, MIT license). It meets every requirement you listed. It runs on MLX rather than llama.cpp, runs in the terminal only, is free and open source, and needs no account. It serves an OpenAI-compatible `/v1/chat/completions` endpoint with streaming (`"stream": true` returns `chat.completion.chunk` events), plus `/v1/models`. `--model` accepts either a Hugging Face repo ID or a local folder.

**Other tools I checked:** pickfit (a catalog of tools it has test-installed) had nothing that fit. Its three closest matches all run GGUF/llama.cpp, so I'm not recommending any of them. That means nobody actually ran the steps below. They come from the mlx-lm docs (SERVER.md) and what I know about the tool. I didn't run anything on your machine.

**My assumptions:** You're on macOS 14 or later with Python 3.10 or newer, you're happy with `uv` or `pip`, and your editor or tools let you set a custom OpenAI base URL.

## Install

Pick one. `uv` keeps the tool isolated from your system Python:
```bash
# Option A (recommended): uv
brew install uv            # skip if you already have uv
uv tool install mlx-lm     # puts mlx_lm.server, mlx_lm.generate, etc. on your PATH

# Option B: a plain virtualenv
python3 -m venv ~/.venvs/mlx && source ~/.venvs/mlx/bin/activate
pip install -U mlx-lm
```

## First run

1. **Start the server with a model from Hugging Face.** The first run downloads it into `~/.cache/huggingface`. No login is needed for public `mlx-community` models.
   ```bash
   mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --host 127.0.0.1 --port 8080
   ```
   Or load a local folder of MLX weights (relative paths count from the folder you start the server in):
   ```bash
   mlx_lm.server --model ~/models/my-mlx-model
   ```
   You can turn your own Hugging Face model into MLX format with `mlx_lm.convert --hf-path <repo> -q`.

2. **Check that streaming works** from a second terminal:
   ```bash
   curl -N http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"messages":[{"role":"user","content":"Write a Python hello world"}],"stream":true,"max_tokens":100}'
   ```
   You should see `data: {...chat.completion.chunk...}` lines appear one at a time. Then run `curl http://127.0.0.1:8080/v1/models` to list the available models.

3. **Point your coding tools at it:**
   - Base URL: `http://127.0.0.1:8080/v1`
   - API key: any placeholder string, if the tool insists on one
   - Model: the same repo ID or path you passed to `--model`

## Tips and caveats
- **Security:** Keep it on `127.0.0.1`. The docs say it "only implements basic security checks" and isn't meant for production, so don't bind it to `0.0.0.0` on networks you don't trust.
- **Long contexts:** `--kv-bits 4` saves memory. It also makes the server handle one request at a time, and the docs suggest lowering `--prefill-step-size` when you use it.
- **Model size:** Choose a size that fits your unified memory. A 4-bit 7–14B model is comfortable on 16–32 GB. `mlx-community` on Hugging Face has thousands of ready-made MLX conversions.
- Run `mlx_lm.server --help` for all the options, such as adapters and a draft model for speculative decoding.

## If it falls short
- **mlx-omni-server** (`pip install mlx-omni-server`) is another MLX-based server that also offers Anthropic-style endpoints and more OpenAI endpoints. It's worth trying if a tool needs function or tool calling that `mlx_lm.server` doesn't handle the way you need. I haven't verified it, so check its README before you rely on it.
- I left out LM Studio because it's a GUI app.

Sources:
- [mlx-lm SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)
- [ml-explore/mlx-lm](https://github.com/ml-explore/mlx-lm)