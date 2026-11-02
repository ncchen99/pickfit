**Recommendation: `mlx-lm` (Apple's MLX project, MIT-licensed).** It is the official MLX text-generation package. It runs MLX-format models from Hugging Face or a local folder, and it includes `mlx_lm.server`, a terminal server with OpenAI-compatible endpoints and streaming. It has no GUI and no account.

Caveat: pickfit did not verify it. Its search found no verified tool that matched, and it named `mlx-lm` from general knowledge. I did confirm the server details below against the project's own `SERVER.md` and its issue tracker, but I did not install or test it.

**Install** (assumes macOS on Apple silicon, Python 3.10+; I haven't checked your setup)

1. Install `uv`, a Python tool manager. Use `brew install uv` if you have Homebrew, or the official `curl` installer from docs.astral.sh/uv. The curl installer pipes a script into a shell, so review it first if you want.
2. Install the server:
   ```
   uv tool install mlx-lm
   ```
   This puts `mlx_lm.server` on your PATH in an isolated environment. The alternative is `pip install -U mlx-lm` in a virtualenv.

**First run**

1. Start the server with an MLX model from Hugging Face. Pick a 4-bit model from the `mlx-community` org, for example a small Qwen or Llama instruct model that fits your RAM:
   ```
   mlx_lm.server --model mlx-community/<model-name> --port 8080
   ```
   The first run downloads the weights. Public models need no account. To use a local folder, pass its path instead: `--model /path/to/mlx-model`.
2. Check that it is up. In a second terminal, run `curl http://localhost:8080/v1/models`.
3. Test streaming. Send a `POST` to `http://localhost:8080/v1/chat/completions` with a JSON body containing `"stream": true`.
4. In your editor's OpenAI-compatible settings, set the base URL to `http://localhost:8080/v1`, set any non-empty API key, and set the model name to the same repo ID or path you passed to `--model`.

**Things to know**

- The default `max_tokens` is 512, so raise it in your editor settings for long coding answers.
- The official docs say the server has only basic security checks and is not for production. Keep it bound to localhost.
- The server is listed as a lower-stability option compared with llama.cpp. Known issues include chat-completions failures with transformers 5.0+ (issue #897) and tool-calling errors on some models (issues #905 and #1885). If your editor relies on tool calls, test that path before you depend on it.
- If you need broader OpenAI API coverage or more polished tool calling, the third-party `mlx-openai-server` package is an alternative. It is not part of the official project, and I have not checked it.

Sources:
- [mlx-lm SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)
- [mlx-lm issue #897 (transformers 5.0 chat completions)](https://github.com/ml-explore/mlx-lm/issues/897)
- [mlx-lm issue #905 (Qwen 3.5 tools)](https://github.com/ml-explore/mlx-lm/issues/905)
- [mlx-lm issue #1885 (MiniCPM5 tool calling)](https://github.com/ml-explore/mlx-lm/issues/1885)
- [mlx-lm discussion #1005 (server docs location)](https://github.com/ml-explore/mlx-lm/discussions/1005)
- [mlx-openai-server](https://github.com/cubist38/mlx-openai-server)