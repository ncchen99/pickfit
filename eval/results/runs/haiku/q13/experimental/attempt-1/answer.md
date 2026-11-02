## Recommendation: llama.cpp's `llama-server`

It loads a `.gguf` file from any path, so nothing is copied into Ollama's store. It runs on CPU, serves several requests at once with continuous batching across parallel slots, and exposes `/v1/chat/completions`, `/v1/completions`, and `/v1/embeddings`. It is MIT-licensed and actively maintained.

Ollama is built on llama.cpp, so the engine is the same. The gain comes from managing concurrency yourself with explicit slot and thread settings.

**Assumptions:** x86_64 Linux, the server is reachable only from your team's network, and your models are quantized (roughly 7B to 32B; a Q4_K_M 14B is about 9 GB on disk).

## Install (pick one)

**Option A: Docker (simplest).** Assumes Docker is installed.
```bash
docker run -d --name llama -p 8080:8080 \
  -v /path/to/your/gguf:/models:ro \
  ghcr.io/ggml-org/llama.cpp:server \
  -m /models/your-model.Q4_K_M.gguf --host 0.0.0.0 --port 8080 \
  -np 4 -c 16384 -t 16 --alias team-model
```

**Option B: build from source (no Docker).** Assumes git, cmake, and a C++ compiler are installed.
```bash
git clone https://github.com/ggml-org/llama.cpp
cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build llama.cpp/build --config Release -j
./llama.cpp/build/bin/llama-server -m /path/to/your-model.gguf \
  --host 0.0.0.0 --port 8080 -np 4 -c 16384 -t 16 --alias team-model
```

## Settings to tune

- **`-np 4`** (parallel slots): the number of requests processed at once. Extra requests queue. On CPU, more slots raise total throughput but lower each user's speed. Start at 4 for 10 users and adjust.
- **`-c 16384`** (context): this is the total context shared across slots. With 4 slots, each gets about 4096 tokens. Raise it if people need longer prompts, since the KV cache uses more RAM.
- **`-t 16`** (threads): set this to your physical core count, not the hyperthread count. Oversubscribing threads is a common cause of the slowdown you see.
- **Auth:** add `--api-key <long-random-string>` (or set `LLAMA_ARG_API_KEY`). Don't expose port 8080 to the internet. If remote access is needed, put it behind a TLS reverse proxy.

## First-run check

From another machine on the network:
```bash
curl http://SERVER:8080/health
curl http://SERVER:8080/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" -H "Content-Type: application/json" \
  -d '{"model":"team-model","messages":[{"role":"user","content":"Say hi"}]}'
```

Clients connect with base URL `http://SERVER:8080/v1` and the API key. Any OpenAI SDK or tool that accepts a custom base URL works.

## Alternatives

- **LocalAI** (MIT): OpenAI-compatible and can load GGUF files from a folder, with multi-model management. Heavier to set up, and I'd expect it to have less per-request tuning than llama-server.
- **Ollama with tuning:** you can keep it and set `OLLAMA_NUM_PARALLEL` and `OLLAMA_MAX_QUEUE`, but it still copies or registers models in its own store unless you use Modelfiles that point at your files. The CPU limit remains.
- **vLLM:** not a good fit for GGUF on CPU.

I haven't run any of these commands here, so the flags are from the llama.cpp docs as I know them. Check `llama-server --help` on your build, since flag names change between releases.

Sources: none fetched. This answer is from my own knowledge, not a live search.