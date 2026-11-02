# My recommendation: llama.cpp's `llama-server`

**`llama-server` from llama.cpp** (MIT license) does what you need:

- **Loads a GGUF from any path** with `-m /path/to/model.gguf`. Nothing gets copied or imported.
- **Handles many users at once on CPU.** It splits the context into N parallel slots (`-np`) and batches them together. On CPU, generating each token is limited mostly by memory bandwidth. Batching lets several users share one pass over the model weights, so 8 requests at once cost much less than 8 requests one after another.
- **OpenAI-compatible API**: `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings` and `/v1/models`, with streaming and an optional API key. It also includes a simple web chat UI.
- It's the engine Ollama is built on, so your GGUFs will work as-is and you'll be closer to the newest CPU optimizations.

**What I assumed:** an x86_64 Linux server, one main shared model, and teammates who connect over the LAN.

## Install (choose one)

**A. Prebuilt binary (simplest)**
1. From https://github.com/ggml-org/llama.cpp/releases, download the latest `…-bin-ubuntu-x64` archive.
2. Extract it into its own directory, for example `/opt/llama.cpp/`. `llama-server` is inside.

**B. Build from source (tuned to your CPU's AVX2/AVX-512 support)**
```bash
sudo apt install -y build-essential cmake git
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"
# binary: build/bin/llama-server
```

**C. Docker**: `ghcr.io/ggml-org/llama.cpp:server`, with your GGUF folder mounted read-only (`-v /data/gguf:/models:ro`).

## First run
```bash
./llama-server \
  -m /data/gguf/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 \
  -np 8 -c 32768 \
  -t $(nproc --ignore=2) \
  --api-key "change-me" \
  --metrics
```
- `-np 8` gives 8 parallel slots. Requests beyond 8 wait in a queue instead of slowing everyone down.
- `-c 32768` is the total context across all slots, so each slot gets about 4K tokens. If people need longer prompts, raise `-c` or lower `-np`.
- For `-t`, use the number of **physical** cores. Hyperthreads usually don't help.
- Flag defaults change between releases, so check `./llama-server --help` against your build.

**Test it:**
```bash
curl http://SERVER:8080/v1/chat/completions \
  -H "Authorization: Bearer change-me" -H "Content-Type: application/json" \
  -d '{"model":"any","messages":[{"role":"user","content":"Hello"}]}'
```
Teammates set their OpenAI client's base URL to `http://SERVER:8080/v1` and use the key. To keep it running permanently, wrap the command in a systemd unit.

## Tips for CPU-only serving
- **Model size matters more than anything else.** A 7–8B model at Q4_K_M will feel responsive for about 10 users. A 30B+ dense model will be slow on any CPU server, whatever the software. Mixture-of-experts models, like the Qwen3-30B-A3B class, are often a good fit for CPU with 64 GB of RAM.
- **Serving several models from your folder:** add **llama-swap** (also open source). It sits in front of `llama-server` and starts the right model based on the `model` field in each request, still reading from your paths.
- **If you'd rather keep Ollama for now:** setting `OLLAMA_NUM_PARALLEL` and `OLLAMA_MAX_QUEUE` may reduce the slowdown. But it still wants its own model store, and `llama-server` gives you more direct control.

## What I checked and didn't use
I searched pickfit's catalog of tools it has test-installed. It returned two little-known projects:
- **Xyntetik Runner:** it serves GGUF over an OpenAI-compatible API, but its handling of many users on CPU wasn't tested.
- **SunnyNet:** it only supports GGUF for RWKV-style models, and its API wasn't tested.

Neither is as well suited as `llama-server` here. Pickfit didn't test llama.cpp itself; I'm recommending it from my own knowledge, and I haven't run any of these steps on your server.