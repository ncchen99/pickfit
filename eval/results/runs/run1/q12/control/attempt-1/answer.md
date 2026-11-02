I recommend **`mlx-lm`**, Apple's own MLX package, which includes a built-in server called `mlx_lm.server`. It's MIT-licensed, terminal-only and needs no account. It provides OpenAI-style endpoints (`/v1/chat/completions`, `/v1/models`) and streams when a request includes `"stream": true`. `--model` accepts either a Hugging Face repo ID (downloaded and cached on first use) or a local folder.

I haven't run anything on your machine. I checked the server's current docs; below are my assumptions and the steps.

## Assumptions
- You have a native arm64 Python 3.10 or newer, not one running under Rosetta, and a recent macOS. Check with `python3 -c "import platform; print(platform.machine())"`, which should print `arm64`.
- You want a single-user server bound to localhost. The project says this server "is not recommended for production" because it has only basic security checks, so don't expose it to your network.

## Install
Either of these keeps it in its own isolated environment:
```bash
# Option A: uv (recommended)
brew install uv            # or: curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install mlx-lm

# Option B: pipx
brew install pipx && pipx ensurepath
pipx install mlx-lm
```
(Running `pip install mlx-lm` inside a venv also works.)

## First run
1. **Optional: try generation first.** This downloads the model the first time:
   ```bash
   mlx_lm.generate --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --prompt "Write hello world in Rust"
   ```
   Most quantized MLX models are under the `mlx-community` org on Hugging Face. As a rough guide, 4-bit 7–14B models suit 16–32 GB of RAM, and larger models need more.

2. **Start the server:**
   ```bash
   mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --host 127.0.0.1 --port 8080
   # or a local folder:
   mlx_lm.server --model ~/models/my-mlx-model
   ```
   It listens on localhost:8080 by default. Run `mlx_lm.server --help` to see all options, such as KV-cache quantization with `--kv-bits`.

3. **Test streaming** from a second terminal:
   ```bash
   curl -N http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"messages":[{"role":"user","content":"Say hi"}],"stream":true,"max_tokens":50}'
   ```
   You should see `chat.completion.chunk` events arriving one at a time.

4. **Point your editor or tools at the server:**
   - Base URL: `http://127.0.0.1:8080/v1`
   - API key: any placeholder string, such as `local`, if the tool requires one
   - Model name: the same repo ID or path you passed to `--model`. `GET /v1/models` lists what's available.

## Tips
- To convert or quantize your own model: `mlx_lm.convert --hf-path <repo> -q`. This writes a local folder that you can pass to `--model`.
- Downloads are cached in `~/.cache/huggingface`. You can change the location with `HF_HOME`.
- It handles one user well. If you need concurrent requests from several tools, look at the alternatives below.

## Alternatives (also free, terminal-only)
- **mlx-omni-server**: an MLX server that implements more of the OpenAI API, including tools/function calling and embeddings. It's worth trying if your coding tool depends on tool calls.
- **vllm-mlx**: a vLLM-style MLX server built for batching and concurrent requests.

Both are community projects and change more often than `mlx-lm`, so check their READMEs before installing.

Source: [mlx-lm SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)