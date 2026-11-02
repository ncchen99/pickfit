# Recommendation: use llama.cpp's `llama-server`

It's free (MIT license) and meets all three requirements:

- **Loads GGUF from a path.** `-m /path/to/model.gguf` reads the file where it is. Nothing gets copied or imported.
- **Handles concurrent requests on CPU.** You set a number of parallel slots, and it batches active requests into one forward pass (continuous batching). Ollama runs on the same engine, but its defaults are conservative and it adds its own scheduling on top.
- **Exposes an OpenAI-compatible API.** It serves `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings` and `/v1/models`, plus a built-in web UI.

**Assumptions:** an x86-64 Linux server, about 10 users, and mostly one model at a time (7–14B, Q4_K_M or similar). Multi-model setups are covered further down.

## What CPU can and can't do

CPU inference is limited by memory bandwidth. Batching raises total throughput a lot, so 10 users no longer queue behind each other. But each person's tokens per second will drop when several people are generating at once. The biggest gains come from:
- Using a smaller or more quantized model, such as 7–8B at Q4_K_M instead of 14B+ or Q8.
- Setting threads to the number of **physical** cores, not hyperthreads.
- Keeping the context per slot reasonable.

## Install

Pick one option:

**A. Prebuilt binary (easiest)**
1. Download the latest `llama-<build>-bin-ubuntu-x64.zip` (or the `.tar.gz`) from https://github.com/ggml-org/llama.cpp/releases.
2. Unpack it to `/opt/llama.cpp`. `llama-server` is in the extracted folder.

**B. Build from source (tuned for your exact CPU, e.g. AVX-512)**
```bash
sudo apt install -y build-essential cmake git libcurl4-openssl-dev
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_NATIVE=ON
cmake --build build --config Release -j
# binary: build/bin/llama-server
```

**C. Docker**
```bash
docker pull ghcr.io/ggml-org/llama.cpp:server
```

## First run

Check your physical core count with `lscpu` (Cores per socket × Sockets). Then:

```bash
llama-server \
  -m /data/gguf/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 \
  --parallel 8 \
  -c 32768 \
  --threads 16 --threads-batch 16 \
  --api-key "change-me" \
  --alias team-model
```

- `--parallel 8` gives 8 simultaneous request slots. With 10 users, not everyone generates at the same moment, so 4–8 is usually right. Extra requests wait in a queue instead of thrashing the CPU.
- `-c` is the **total** context, split evenly across slots. 32768 / 8 gives each request 4096 tokens. Raise it if people paste long documents. With 64 GB RAM you have room for that.
- Continuous batching is on by default in current builds. Older builds need `-cb`.
- Docker equivalent: `docker run -p 8080:8080 -v /data/gguf:/models:ro ghcr.io/ggml-org/llama.cpp:server -m /models/<file>.gguf --host 0.0.0.0 --parallel 8 -c 32768 --threads 16 --api-key change-me`. Mounting the folder read-only (`:ro`) makes it impossible for anything to be written into your model folder.

**Test it:**
```bash
curl http://SERVER:8080/v1/chat/completions \
  -H "Authorization: Bearer change-me" -H "Content-Type: application/json" \
  -d '{"model":"team-model","messages":[{"role":"user","content":"Hello"}]}'
```
Teammates point any OpenAI SDK or tool at `base_url=http://SERVER:8080/v1` with that API key. Open WebUI, Continue and similar tools also work this way. To see slot usage, use `GET /slots` (enable it with `--slots`) or `/metrics` (enable it with `--metrics`).

**Run it permanently:** put the command in a systemd unit with `Restart=always`. If you need TLS, put nginx or Caddy in front.

## If you need several models from your folder

- **llama-swap** (MIT, https://github.com/mostlygeek/llama-swap) is a small proxy that sits in front of `llama-server`. You list each GGUF path in a YAML config. It starts or swaps the right model based on the `model` field in the request and serves a single OpenAI endpoint. With 64 GB you can keep one or two small models loaded at the same time.
- Recent `llama-server` builds have also added a built-in multi-model "router" mode that points at a models directory. I'm less sure of the exact flags, so check `llama-server --help` on your build before relying on it.

## Alternatives I'd rank lower for your case

- **LocalAI** (MIT) is also OpenAI-compatible and runs llama.cpp underneath. It's more of an all-in-one, but heavier, and you usually tune concurrency through its config files.
- **vLLM on CPU** has strong batching, but its GGUF support is experimental and the CPU backend is fussier to set up. It's not worth it here.
- **Staying on Ollama:** setting `OLLAMA_NUM_PARALLEL=4–8` and `OLLAMA_MAX_LOADED_MODELS=1` would help. But Ollama still imports models into its own blob store, which you want to avoid.