I'd use **llama.cpp's `llama-server`**. It's free and MIT-licensed, it loads a GGUF file from whatever path you give it, it batches concurrent requests on CPU, and it serves an OpenAI-compatible API at `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings` and `/v1/models`.

Ollama is built on llama.cpp, so you keep the same model support and quantizations. The difference is that you control how requests are batched instead of Ollama's defaults.

## Why it fixes the slowdown

- **Slots plus continuous batching.** `--parallel N` creates N slots. Requests in different slots are decoded together in one batched forward pass instead of waiting in line. On CPU, generation speed is mostly limited by memory bandwidth. Batching reads the weights once per step for all active users, so total throughput goes up a lot while each user's speed drops only a little.
- **One model kept in memory.** Ollama can unload, reload or switch models between users. `llama-server` keeps one model loaded and memory-mapped from your folder, with no copying.
- **Assumptions:** an x86_64 server, a recent distro, and that your team mostly shares one main model. With 64 GB RAM, a 7–14B model at Q4_K_M/Q5_K_M is the realistic size. On CPU, a 70B model would be too slow for 10 users whatever server you use.

## Install (pick one)

**A. Prebuilt binary (easiest)**
1. Go to https://github.com/ggml-org/llama.cpp/releases and download the latest `llama-<build>-bin-ubuntu-x64.zip`.
2. `unzip` it into something like `/opt/llama.cpp/`. `llama-server` is in its `bin/` folder.

**B. Build from source (tuned to your exact CPU, often a bit faster)**
```bash
sudo apt install -y build-essential cmake git libcurl4-openssl-dev
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON
cmake --build build -j"$(nproc)"
# binary: build/bin/llama-server
```

**C. Docker**
```bash
docker run -d --name llama -p 8080:8080 -v /srv/gguf:/models:ro \
  ghcr.io/ggml-org/llama.cpp:server \
  -m /models/your-model.Q4_K_M.gguf --host 0.0.0.0 --port 8080 \
  --parallel 6 -c 24576 -t 16 --api-key CHANGE_ME
```

## First run

```bash
llama-server \
  -m /srv/gguf/Qwen2.5-14B-Instruct-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 \
  --parallel 6 \          # concurrent slots; start at 4–8
  -c 24576 \              # TOTAL context, split across slots (24576/6 ≈ 4096 each)
  -t 16 \                 # = number of PHYSICAL cores, not hyperthreads
  -tb 32 \                # threads for prompt processing (can use all logical cores)
  --api-key CHANGE_ME \
  --metrics
```

Then test it from another machine:
```bash
curl http://SERVER:8080/v1/chat/completions \
  -H "Authorization: Bearer CHANGE_ME" -H "Content-Type: application/json" \
  -d '{"model":"any","messages":[{"role":"user","content":"Say hello"}]}'
```
Your teammates point any OpenAI client at `http://SERVER:8080/v1` and use that key. A simple web chat UI is also served at `http://SERVER:8080/`.

## Tuning tips

- **`-c` is shared across slots.** If people paste long documents, raise `-c` or lower `--parallel`. The KV cache is the main thing that grows with these settings. A q8 KV cache (`--cache-type-k q8_0 --cache-type-v q8_0`) roughly halves that memory.
- **Find your `--parallel` sweet spot.** Try 4, 6 and 8 with a few simultaneous requests and watch tokens/s per user. Stop increasing it when per-user speed becomes unacceptable.
- **Pick the model size for speed.** On CPU, a smaller quant or model (for example 8B at Q4_K_M) usually helps the team more than a bigger one.
- **Several models:** run one `llama-server` per model on different ports, or put **llama-swap** in front. llama-swap is open source, reads your GGUF paths from a YAML config and gives you a single OpenAI endpoint that routes by the `model` name.
- **Run it as a service:** wrap the command above in a systemd unit with `Restart=always`.
- **If you'd rather stay on Ollama:** `OLLAMA_NUM_PARALLEL` and `OLLAMA_MAX_LOADED_MODELS=1` help with concurrency. But importing a model through a Modelfile still copies the GGUF into Ollama's blob store, so it doesn't solve your copying problem.

## Other options I checked (not recommended)

I asked pickfit, which installs lesser-known tools and tests them in a sandbox, for Ollama replacements. None of its three picks was a better fit:
- **Xyntetik Runner** serves a GGUF file from a path over an OpenAI API (verified on Linux x86_64). But nothing in the test shows it handles concurrent users efficiently, which is your main problem.
- **SunnyNet** is a CPU-focused runtime, but it only runs RWKV-style models, and its OpenAI server wasn't tested.
- **Camelid** is mainly a desktop chat app and isn't suited to serving several users at once.

pickfit didn't list llama.cpp and hasn't tested it. My recommendation comes from llama.cpp's own documentation and how widely it's used, not from a sandbox test. I haven't run anything on your machine, as you asked.