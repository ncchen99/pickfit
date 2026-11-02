I recommend **`mlx-lm`**, Apple's own MLX package (github.com/ml-explore/mlx-lm). It's MIT-licensed and free, needs no account or GUI, and covers everything you asked for:

- **Terminal only:** you start the server with `mlx_lm.server`.
- **OpenAI-compatible API:** `POST /v1/chat/completions` and `GET /v1/models`, on `localhost:8080` by default.
- **Streaming:** your editor turns this on by sending `"stream": true`, and the server returns OpenAI-style `chat.completion.chunk` events.
- **Model loading:** `--model` takes either a Hugging Face repo (it downloads and caches it on first use) or a local folder path.

I haven't installed or tested it. pickfit has no verified tool for this request and only listed mlx-lm as an unverified "well-known option." The server details above come from the project's `SERVER.md` docs. I didn't run any commands on your machine.

## Install
I'm assuming you're on Apple silicon with a native arm64 Python 3.10 or newer, not Rosetta. Pick one:

```bash
# Option A: uv (installs it as an isolated CLI tool)
brew install uv
uv tool install mlx-lm

# Option B: pipx
brew install pipx && pipx ensurepath
pipx install mlx-lm

# Option C: plain venv
python3 -m venv ~/.venvs/mlx && source ~/.venvs/mlx/bin/activate
pip install mlx-lm
```

Check the install with `mlx_lm.server --help`, which lists all the flags, including `--host` and `--port`.

## First run
1. **Quick test in the terminal (optional):**
   ```bash
   mlx_lm.generate --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --prompt "Write hello world in Rust"
   ```
   The first run downloads the model to `~/.cache/huggingface`.

2. **Start the server:**
   ```bash
   # From Hugging Face
   mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --port 8080
   # Or from a local MLX-format folder
   mlx_lm.server --model ~/models/my-mlx-model --port 8080
   ```
   It listens on localhost only by default, so leave it that way. The docs say the server has only basic security checks and isn't meant for production, so don't expose it to your network.

3. **Test streaming:**
   ```bash
   curl -N localhost:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"messages":[{"role":"user","content":"Say this is a test"}],"stream":true}'
   ```
   You should see `data: {...chat.completion.chunk...}` lines arrive one by one.

4. **Point your editor or coding tool at it:**
   - Base URL: `http://localhost:8080/v1`
   - API key: any placeholder like `sk-local`, if the tool insists on one.
   - Model: the same repo ID or path you started the server with. `curl localhost:8080/v1/models` shows the exact ID.

## Tips
- **Choosing a model:** look for MLX models under the `mlx-community` organization on Hugging Face. 4-bit 7–14B models run well on 16–32 GB Macs, and bigger ones need more unified memory.
- **Converting a model yourself:** `mlx_lm.convert --hf-path <org/model> -q` creates a local MLX folder that you can pass to `--model`.
- **Long contexts:** `--kv-bits 4` saves memory, but then the server handles requests one at a time.

## Other options (also not verified)
- **mlx-omni-server** and **vllm-mlx** are community MLX servers with broader OpenAI API coverage, such as tools/function calling and embeddings. They're worth trying if your coding tool depends on tool calls and mlx-lm's support isn't enough.
- **LM Studio** has an MLX backend but is a GUI app, so I left it out.