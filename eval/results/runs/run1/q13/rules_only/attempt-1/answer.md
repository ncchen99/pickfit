# Recommendation: llama.cpp's `llama-server`

`llama-server` is the HTTP server that ships with llama.cpp (MIT license). Ollama runs on llama.cpp under the hood, so running the server directly removes a layer and fits your needs:

- **Loads GGUF from a path:** `-m /models/foo.gguf`. Nothing is copied or converted, and there's no model store.
- **Handles concurrent requests:** `--parallel N` creates N slots, and continuous batching (on by default) puts all active requests into the same forward pass. On CPU, generating each token is limited mostly by memory bandwidth. Batching reads the weights once per step for every active user, so total throughput goes up a lot compared with requests waiting in line. Ollama hides or caps this behind `OLLAMA_NUM_PARALLEL` and its default settings, which is likely why yours crawls.
- **OpenAI-compatible API:** `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings` and `/v1/models`, with streaming. It also has `--api-key`, a Prometheus `/metrics` endpoint and a small built-in web UI.

**What it won't fix:** one CPU box doesn't have much compute. Batching raises total tokens per second, but each person still gets fewer tokens per second when 10 are active. Reading long prompts is limited by compute and doesn't speed up much. Model size and quantization matter more than anything else (see the tuning section).

## Install (Linux x86_64, no GPU needed)

Pick one:

1. **Prebuilt binary:** from https://github.com/ggml-org/llama.cpp/releases, download the `llama-<build>-bin-ubuntu-x64.zip` asset, unzip it and use `build/bin/llama-server`.
2. **Build from source:** this gets you CPU-specific tuning such as AVX2 or AVX-512.
   ```bash
   sudo apt install -y build-essential cmake git libcurl4-openssl-dev
   git clone https://github.com/ggml-org/llama.cpp
   cd llama.cpp
   cmake -B build -DCMAKE_BUILD_TYPE=Release
   cmake --build build -j"$(nproc)"
   # binary: build/bin/llama-server
   ```
3. **Docker:**
   ```bash
   docker run -p 8080:8080 -v /srv/gguf:/models:ro ghcr.io/ggml-org/llama.cpp:server \
     -m /models/your-model.gguf --host 0.0.0.0 --port 8080 -np 8 -c 32768
   ```

## First run

```bash
./build/bin/llama-server \
  -m /srv/gguf/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --alias qwen7b \
  --host 0.0.0.0 --port 8080 \
  --parallel 8 \
  -c 32768 \
  -t 16 --threads-batch 16 \
  --api-key "change-me" \
  --metrics
```

What the options do:
- `--parallel 8`: 8 requests can generate at once. More requests than that wait in a queue.
- `-c 32768`: the **total** context, split between slots. Here each slot gets 4096 tokens. If people need 8k per request, use `-c 65536`. The KV cache uses RAM, but you have 64 GB.
- `-t`: set this to the number of **physical** cores, not hyperthreads (check `lscpu`). On a two-socket server, also add `--numa distribute`.

Test it:
```bash
curl http://SERVER:8080/v1/chat/completions \
  -H "Authorization: Bearer change-me" -H "Content-Type: application/json" \
  -d '{"model":"qwen7b","messages":[{"role":"user","content":"Hello"}]}'
```
Teammates' tools connect with `base_url = http://SERVER:8080/v1` and the API key. Once it works, run it as a systemd service with `Restart=always`.

## Tuning for 10 users on CPU

- **Use small quantized models:** 7–8B models at Q4_K_M are the practical choice for this many people on CPU. Mixture-of-experts GGUFs that activate only a few billion parameters per token (for example Qwen3-30B-A3B) work especially well on CPU. You get the quality of a larger model at roughly the speed of a 3B one.
- **Try a few slot counts:** start with `--parallel` at 4–8 and watch `/metrics`. Past some point, more slots only make each user slower.
- **One model per process:** this is the main trade-off versus Ollama. If you want several models from your folder behind one endpoint:
  - **Router mode:** recent llama-server builds include a router mode that loads models from a folder on demand (`--models-dir`). Check `llama-server --help` on your build. I'm assuming your build is recent enough to have it.
  - **[llama-swap](https://github.com/mostlygeek/llama-swap):** a small, mature proxy written in Go. It starts and stops llama-server processes by model name, using paths you list in a YAML file.

## Other options I considered

- **LocalAI** (MIT): runs llama.cpp underneath, reads GGUFs from a models directory and serves an OpenAI API covering many models. It's heavier, but it's the most Ollama-like option if you want several models and a management layer.
- **vLLM (CPU build):** very good at concurrency on GPUs, but its GGUF support is experimental and the CPU backend is a weaker fit here.
- **Tuning Ollama instead** (`OLLAMA_NUM_PARALLEL`, `OLLAMA_MAX_LOADED_MODELS`) helps somewhat. But `ollama create` still copies your GGUFs into its blob store, which you said you don't want.
- I also checked pickfit's catalog of lesser-known tools. It returned TurboLLM, Xyntetik Runner and Vortelio, all matched on keywords alone. None of them showed CPU concurrency or batching, so I wouldn't use them for this.

I haven't run any of these commands on your system. The flags and install steps come from llama.cpp's documented usage, so check them against `llama-server --help` for the build you install.