I recommend **mlx-lm**, Apple's own MLX package for running language models. It's MIT-licensed and needs no account or GUI. Its `mlx_lm.server` command starts an OpenAI-compatible HTTP server with streaming.

I haven't run any of this on your machine. pickfit hasn't installed or tested mlx-lm either; it named mlx-lm as an unverified option. I checked the project's server docs for the server details below.

## Why it fits
- **MLX, not GGUF:** it runs on Apple's MLX framework and loads MLX-format weights, such as the ones under `mlx-community/*` on Hugging Face.
- **Hugging Face or a local folder:** `--model` takes a Hugging Face repo ID, which downloads into `~/.cache/huggingface` the first time, or a local path.
- **OpenAI-compatible with streaming:** it serves `POST /v1/chat/completions` and `GET /v1/models`, and sends tokens as they're generated when a request sets `"stream": true`. That's what editor plugins send.
- **Terminal only:** it's a Python CLI.

## Install
Assumptions: Apple silicon, Python 3.10 or newer, and at least 16 GB of RAM.

```bash
# Option A: isolated CLI install (recommended)
brew install uv            # or: pipx, if you already use it
uv tool install mlx-lm     # puts mlx_lm.server, mlx_lm.generate etc. on PATH

# Option B: plain venv
python3 -m venv ~/.venvs/mlx && source ~/.venvs/mlx/bin/activate
pip install -U mlx-lm
```

## First run
1. **Quick check, no server:**
   ```bash
   mlx_lm.generate --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit \
     --prompt "Write a Python function that reverses a string."
   ```
2. **Start the server.** It listens on `127.0.0.1:8080` by default:
   ```bash
   mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --port 8080
   # or a local MLX folder:
   mlx_lm.server --model ~/models/my-mlx-model --port 8080
   ```
   A local path given without a leading `~/` or `/` is read relative to the folder you start the server from, so absolute paths are safer.
3. **Test streaming:**
   ```bash
   curl -N http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
          "messages":[{"role":"user","content":"Hello"}],
          "stream":true}'
   ```
   You should see `data: {...}` chunks arrive one after another.
4. **Point your coding tools at it:**
   - Base URL: `http://127.0.0.1:8080/v1`
   - API key: any placeholder string, like `sk-local`
   - Model: the same repo ID or path you used in step 2

## Useful options and caveats
- `mlx_lm.server --help` lists every flag.
- For long contexts, `--kv-bits 4 --prefill-step-size 512` saves memory. With those flags the server handles only one request at a time.
- To use a Hugging Face model that isn't already in MLX format, convert it: `mlx_lm.convert --hf-path <repo> -q`. This writes a 4-bit MLX folder you can serve.
- **Model size:** 7B–14B models at 4 bits suit 16–32 GB Macs. With 48 GB or more, try larger coding models from `mlx-community`.
- **Security:** the docs say the server is not meant for production and has only basic security checks. Keep it on `127.0.0.1` and don't bind it to `0.0.0.0`.
- If your editor needs the older `/v1/completions` endpoint (some autocomplete plugins do), check `--help` for your version.

## Other options if mlx-lm doesn't work out
None of these were verified by pickfit or by me:
- **mlx-omni-server:** another MLX server that also offers OpenAI-style endpoints.
- **LM Studio:** has an MLX engine, but it's a GUI app and not fully open source, so it doesn't meet your requirements.

Sources:
- [mlx-lm SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)
- pickfit `find_software` result