## Recommendation: `mlx-lm` (Apple's MLX project)

Use **`mlx-lm`**. It is the MLX project's own LLM package, it is open source (MIT), and it has no GUI or account requirement. Its `mlx_lm.server` command provides an OpenAI-compatible `/v1/chat/completions` endpoint with streaming. It loads models from a Hugging Face repo ID (downloaded and cached automatically) or from a local folder.

If you later need several models behind one server, tool calling, or embeddings, consider [mlx-openai-server](https://github.com/cubist38/mlx-openai-server) as the alternative. It is also open source and pip-installable, and it has a YAML config for multiple models. Check which `--model-type` value your installed version expects, because the [PyPI release notes](https://pypi.org/project/mlx-openai-server/1.2.3/) show the flag changed between versions.

I could not reach the official `mlx-lm` docs during this search, so **verify the flags with `mlx_lm.server --help` before relying on them.**

## Install

Requirements: Apple silicon Mac, Python 3.10 or newer (`uv` handles this for you). No account is needed for public models in the `mlx-community` org on Hugging Face.

```sh
# 1. Install uv, a small Python tool manager (skip if you have it)
brew install uv

# 2. Install mlx-lm as an isolated command-line tool
uv tool install mlx-lm

# 3. Confirm the server command exists and check its options
mlx_lm.server --help
```

## First run

```sh
# Downloads the model on first use (several GB), then serves it
mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --host 127.0.0.1 --port 8080
```

Pick a 4-bit quantized model that fits your unified memory. On a 16 GB machine, 7B-class 4-bit models are a safe starting point. Browse `mlx-community` on Hugging Face for current coder models.

To use a local folder instead, point `--model` at it:

```sh
mlx_lm.server --model ~/models/my-mlx-model --host 127.0.0.1 --port 8080
```

A local folder must contain MLX-format weights and a config. To convert an existing Hugging Face model yourself, use `mlx_lm.convert --hf-path <repo> -q` (`-q` quantizes).

Test streaming from a second terminal:

```sh
curl -N http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mlx-community/Qwen2.5-Coder-7B-Instruct-4bit","stream":true,"messages":[{"role":"user","content":"Say hi"}]}'
```

You should see `data:` chunks arrive incrementally.

## Connect your editor

Most OpenAI-compatible editor integrations need:

- **Base URL:** `http://127.0.0.1:8080/v1`
- **API key:** any non-empty string (the server does not check it)
- **Model name:** the same repo ID or path you passed to `--model`

Keep the server bound to `127.0.0.1` so it is not reachable from your network.

## Assumptions and caveats

- I assumed you want a single model served at a time. The default `mlx_lm.server` is simplest for that; check its help output if you need per-request model switching.
- Model and memory figures are rough. Measure with Activity Monitor once a model loads.
- Some coding tools expect tool/function calling. Verify it works with your chosen model and server before depending on it.

Sources:
- [mlx-openai-server on GitHub](https://github.com/cubist38/mlx-openai-server)
- [mlx-openai-server on PyPI (1.2.3)](https://pypi.org/project/mlx-openai-server/1.2.3/)
- [defilantech mlx-server (Swift alternative)](https://github.com/defilantech/mlx-server)