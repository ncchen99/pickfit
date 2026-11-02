# Recommendation: `llama-server` from llama.cpp

**llama.cpp's `llama-server`** fits all your requirements. It's free and MIT-licensed. It loads a `.gguf` file straight from any path, so nothing gets copied or imported. It handles concurrent requests with parallel slots and continuous batching, and it serves an OpenAI-compatible API (`/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/models`).

Ollama runs on the llama.cpp engine internally. Running `llama-server` yourself gives you direct control over the settings that matter most for concurrency: how many requests run at once, the batch size, the thread count and the context size per request.

**Assumptions:** an x86_64 server with AVX2 or AVX-512, quantized models in the 7–14B range (for example Q4_K_M), and models stored in `/srv/models`. Change the paths to match your setup.

---

## Install (choose one)

**A. Prebuilt binary (simplest)**
1. Go to https://github.com/ggml-org/llama.cpp/releases and download the latest `llama-*-bin-ubuntu-x64.zip`.
2. Unzip it into a directory such as `/opt/llama.cpp` and add that directory to your `PATH`.

**B. Build from source (best CPU tuning, because it compiles for your exact CPU)**
```bash
sudo apt install -y build-essential cmake git libcurl4-openssl-dev
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --target llama-server
# binary: build/bin/llama-server
```

**C. Docker**
```bash
docker run -d --name llama -p 8080:8080 -v /srv/models:/models:ro \
  ghcr.io/ggml-org/llama.cpp:server \
  -m /models/your-model.gguf --host 0.0.0.0 --port 8080 -c 32768 -np 4
```

## First run

```bash
llama-server \
  -m /srv/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 \
  -c 32768 \
  -np 4 \
  -t 16 -tb 32 \
  --api-key "change-me"
```

What each flag does:
- **`-np 4`**: the number of requests decoded at the same time. Continuous batching is on by default, so new requests join the running batch instead of waiting in a queue. Start with 4, then try 6–8 while watching latency.
- **`-c` is shared across all slots.** With `-c 32768 -np 4`, each request gets 8K tokens of context. Each slot's KV cache uses RAM, which is fine with 64 GB at these sizes.
- **`-t`**: set this to the number of *physical* cores, not hyperthreads. Generation speed is limited by memory bandwidth, so adding more threads often makes it slower. **`-tb`** sets the threads used for prompt processing, and that can go higher.
- **`--api-key`**: clients send this as `Authorization: Bearer change-me`.

**Test it:**
```bash
curl http://SERVER:8080/health
curl http://SERVER:8080/v1/chat/completions \
  -H "Authorization: Bearer change-me" -H "Content-Type: application/json" \
  -d '{"model":"any","messages":[{"role":"user","content":"Hello"}]}'
```
Your teammates point their OpenAI SDK or tools at `http://SERVER:8080/v1` and use that key. The server also includes a simple web chat UI at `http://SERVER:8080/`.

**Keep it running:** wrap the command in a systemd unit with `Restart=always`, running as a non-root user that has read-only access to `/srv/models`.

## Serving several GGUFs from the folder

One `llama-server` process serves one model. To let users choose a model by its `model` name:
- **llama-swap** (https://github.com/mostlygeek/llama-swap, MIT) is a small Go proxy. You list each GGUF path in a YAML config, and it starts and stops `llama-server` instances on demand behind a single OpenAI-compatible endpoint.
- Recent llama.cpp builds also have a built-in multi-model "router" mode that points at a models directory. Run `llama-server --help` on your version to check whether it's there and what the flag is called.

On a CPU-only machine, I'd suggest keeping **one main model loaded all the time** rather than switching between models. Loading a model and warming its cache takes a long time.

## What to expect

Batching raises **total** throughput, but CPU inference is limited by memory bandwidth. When 10 people send requests at once, each person still gets fewer tokens per second than a single user would. Long prompts are the main cause of slowdowns, because prompt processing on CPU is compute-heavy. What helps most:
- Use a smaller model or a smaller quant, such as a 7–8B model at Q4_K_M, instead of 14B+.
- Cap `max_tokens` and keep `-c` per slot modest.
- Leave prompt caching on (the default) so repeated system prompts are reused.

**Quick alternative check:** if you'd rather stay on Ollama for now, setting `OLLAMA_NUM_PARALLEL` (and `OLLAMA_MAX_LOADED_MODELS=1`) can partly fix the queuing. It still won't load GGUFs in place, though, which is why I recommend `llama-server`.

**Other options I considered and ranked lower:**
- **LocalAI:** heavier, and it wraps llama.cpp anyway.
- **KoboldCpp:** aimed at a single user.
- **vLLM CPU backend:** its GGUF support is limited and experimental.