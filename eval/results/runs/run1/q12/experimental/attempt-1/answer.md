I recommend **mlx-lm**, the command-line package from Apple's ML Explore team. Its `mlx_lm.server` command runs a local OpenAI-compatible server.

It meets each of your requirements:
- **Uses MLX, not GGUF/llama.cpp:** it runs MLX-format models directly on Apple silicon.
- **Terminal only, no account:** it's a pip package under the MIT license, with no GUI and no sign-up. Public models on Hugging Face download without logging in.
- **OpenAI-compatible:** it serves `POST /v1/chat/completions` and `GET /v1/models` on `localhost:8080` by default.
- **Streaming:** if a request sets `"stream": true`, the server sends `chat.completion.chunk` events as tokens are generated, which is what editors expect.
- **Hugging Face or local folder:** `--model` takes either a Hugging Face repo ID (downloaded to the HF cache) or a local path.

I checked these details against the project's `SERVER.md` docs. pickfit, a tool that recommends software it has installed and tested, didn't have a tested option for this request. It also named mlx-lm, but hasn't tested it, and I haven't run any of the steps below on your machine.

## Install
I'm assuming you have a native arm64 Python 3.9 or newer, such as Homebrew's or one managed by uv. An x86 Python running under Rosetta won't work with MLX. Pick one of these:

```bash
# Option A: uv (installs the CLI in its own isolated environment)
brew install uv
uv tool install mlx-lm

# Option B: pipx
brew install pipx && pipx ensurepath
pipx install mlx-lm

# Option C: a plain virtual environment
python3 -m venv ~/.venvs/mlx && source ~/.venvs/mlx/bin/activate
pip install -U mlx-lm
```

## First run
1. **Quick test in the terminal.** This downloads the model the first time:
   ```bash
   mlx_lm.generate --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --prompt "Write a Python hello world"
   ```
   The `mlx-community` organization on Hugging Face has many models already converted to MLX. A 7B model at 4-bit uses roughly 5 GB of memory. On a 32 GB Mac or larger, 14B–32B 4-bit models also run well.

2. **Start the server:**
   ```bash
   mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --port 8080
   # or from a local folder:
   mlx_lm.server --model ~/models/my-mlx-model --port 8080
   ```
   Run `mlx_lm.server --help` to see all options, such as `--host` and KV-cache quantization with `--kv-bits`.

3. **Check that streaming works:**
   ```bash
   curl -N http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"mlx-community/Qwen2.5-Coder-7B-Instruct-4bit","messages":[{"role":"user","content":"Hi"}],"stream":true}'
   ```
   You should see `data: {...chat.completion.chunk...}` lines arrive one after another.

4. **Point your editor or coding tools at it:**
   - Base URL: `http://127.0.0.1:8080/v1`
   - API key: any placeholder like `sk-local`, since many clients require the field to be filled in
   - Model: the repo ID or path you started the server with

## Using models that aren't on mlx-community yet
You can convert and quantize a regular Hugging Face model to MLX yourself:
```bash
mlx_lm.convert --hf-path Qwen/Qwen2.5-Coder-7B-Instruct -q --mlx-path ~/models/qwen-coder-7b-4bit
```
Then pass that folder to `--model`.

## Things to know
- **Security:** the docs say the server only has "basic security checks" and isn't meant for production. Keep it on `127.0.0.1` and don't expose it to your network.
- **One model at a time:** it serves the model you start it with, although a request's `model` field can name another repo or path. If you use `--kv-bits`, requests are handled one at a time with no batching.
- **Possible gap:** your tools might need endpoints this server doesn't document, like the newer `/v1/responses` API or embeddings. If so, **mlx-omni-server** (`pip install mlx-omni-server`) is another free, MLX-based, OpenAI-compatible server to try. I haven't checked its current feature set.