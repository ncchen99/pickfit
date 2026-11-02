# Recommendation: llama.cpp's `llama-server`

Use **`llama-server` from llama.cpp** (MIT license). Ollama is built on the same engine, so you'll get the same inference speed. The difference is that you control concurrency directly.

- **Loads GGUF from any path.** `-m /path/to/model.gguf` reads the file where it is. Nothing is copied or converted.
- **Handles concurrent requests on CPU.** It splits the server into several request slots with `--parallel N` and uses continuous batching, which is on by default. Requests from different people are combined into one forward pass instead of waiting in line. On CPU, generating each token is mostly limited by memory bandwidth, so batching 4–8 users raises total tokens per second a lot compared with serving them one at a time.
- **OpenAI-compatible API.** It serves `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings` and `/v1/models`, plus a built-in web chat UI. It also supports optional `--api-key` auth.

**Assumptions:** an x86-64 Linux server and models in the 7B–32B range. I haven't checked the current release for exact flag names, so confirm them with `llama-server --help`.

## Install (pick one)

**A. Prebuilt binary (simplest)**
1. Go to https://github.com/ggml-org/llama.cpp/releases.
2. Download the `llama-<build>-bin-ubuntu-x64.zip` asset (the CPU build) and unzip it, for example to `/opt/llama.cpp`.
3. Check it runs: `/opt/llama.cpp/llama-server --version`

**B. Docker**
```bash
docker run -d --name llama -p 8080:8080 \
  -v /srv/gguf:/models:ro \
  ghcr.io/ggml-org/llama.cpp:server \
  -m /models/Qwen2.5-14B-Instruct-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 -c 32768 -np 4 -t 16
```
The `:ro` mount keeps your GGUF folder read-only and in place.

**C. Build from source (best CPU tuning, since it compiles for your exact CPU)**
```bash
sudo apt install -y build-essential cmake git libcurl4-openssl-dev
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON
cmake --build build -j --target llama-server
# binary: build/bin/llama-server
```

## First run
```bash
llama-server \
  -m /srv/gguf/Qwen2.5-14B-Instruct-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 \
  -np 4 \                 # 4 concurrent request slots
  -c 32768 \              # TOTAL context, divided across slots (~8k each here)
  -t 16 \                 # = number of PHYSICAL cores, not hyperthreads
  -a team-model \         # model name clients will use
  --api-key "change-me"
```

Test it:
```bash
curl http://SERVER:8080/v1/chat/completions \
  -H "Authorization: Bearer change-me" -H "Content-Type: application/json" \
  -d '{"model":"team-model","messages":[{"role":"user","content":"Hello"}]}'
```
To point existing clients at it, set the base URL to `http://SERVER:8080/v1` and the API key to `change-me`.

## Tuning for 10 users on CPU
- **`-np`:** start at 4. Try 6–8 if replies stay fast enough. More slots give more total throughput, but each user's stream gets slower.
- **`-c`:** this is shared across all slots. For example, 8 slots × 8k tokens means `-c 65536`. The KV cache uses RAM, so check memory use after changing it.
- **`-t`:** set it to physical cores (`lscpu`: cores per socket × sockets). Going above that usually makes things slower. On dual-socket servers, also try `--numa distribute`.
- **Model size matters more than anything else.** On CPU, a 7–14B model at Q4_K_M is responsive for a team. 32B+ will feel slow under load no matter which server you use.
- **Watch it with `/metrics`** (enable with `--metrics`) or `/slots` to see whether requests are queuing.
- **Keep it running** under a systemd unit with `Restart=always` that wraps the command above.

## Several models from one folder
A single `llama-server` process normally serves one model. You have two options:
- **Router mode:** recent builds can point at a whole folder with `--models-dir /srv/gguf` and load models on demand, picked by the request's `model` field. Check `--help` for your build, since this feature is newer.
- **llama-swap** (https://github.com/mostlygeek/llama-swap, MIT): a small proxy that starts and stops `llama-server` per model, still reading files from your folder.

Either way, keep only 1–2 models loaded at once. Every loaded model takes RAM and CPU from the others.

## Other options I considered
- **Tune Ollama instead:** `OLLAMA_NUM_PARALLEL=4` and `OLLAMA_MAX_LOADED_MODELS=1` may fix much of the slowdown. But importing GGUF into Ollama (`FROM /path` in a Modelfile) copies the file into its blob store, which you said you want to avoid.
- **LocalAI:** also open source and OpenAI-compatible, and it uses llama.cpp underneath. It's heavier, and its main benefit is supporting more kinds of models.
- **vLLM (CPU build):** strong batching, but its GGUF support is experimental and its CPU path is weaker. Not a good fit here.
- **KoboldCpp:** loads GGUF from a path, but it's aimed at single users and handles concurrency less well.

**Bottom line:** run `llama-server` with `-np 4–8`, `-t` set to your physical cores, and a mid-sized Q4 model. Add router mode or llama-swap if you need to switch between models.