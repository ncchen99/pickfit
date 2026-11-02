# Recommendation: llama.cpp's `llama-server`

**Use `llama-server` from llama.cpp.** It's MIT-licensed and does all three things you asked for:

- **Loads GGUF files from where they already are.** You point it at the file with `-m /path/to/model.gguf`. Nothing gets copied or imported.
- **Handles several users at once.** It has parallel "slots" (`-np`) and continuous batching, so tokens for several requests are generated in the same pass instead of one request at a time.
- **Speaks the OpenAI API.** It serves `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings` and `/v1/models`. It also supports an API key and has a small web chat UI.

Ollama runs on llama.cpp underneath, so the speed per token will be about the same. What changes is that you control batching, threads and the number of slots directly.

**Assumptions:** an x86_64 Linux server with physical CPU cores and AVX2 or AVX-512, a team that mostly uses one model at a time, and GGUF files in `/srv/models`.

## Install

**Option A, a prebuilt binary:**
1. Go to https://github.com/ggml-org/llama.cpp/releases and download the latest `llama-<build>-bin-ubuntu-x64.zip`. It works on most glibc distros.
2. Unzip it, for example into `/opt/llama.cpp`. `llama-server` is inside the `bin/` folder.

**Option B, build it yourself.** This gives the best CPU tuning, because `GGML_NATIVE` uses your CPU's own instruction set.
```bash
sudo apt install -y build-essential cmake git libcurl4-openssl-dev
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build -j --target llama-server
# binary: build/bin/llama-server
```

## First run

```bash
llama-server \
  -m /srv/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --alias team-model \
  --host 0.0.0.0 --port 8080 \
  -t 16 -tb 32 \
  -np 4 \
  -c 32768 \
  --api-key "change-me"
```

What the flags do:
- **`-t`**: threads used to generate tokens. Set it to your number of **physical** cores (`lscpu`). Hyperthreads usually make it slower. `-tb` sets threads for reading prompts and can be higher.
- **`-np 4`**: four requests are served at once. Any others wait in a queue instead of all slowing each other down. Try values from 4 to 8.
- **`-c`**: the total context, shared across the slots. 32768 with 4 slots gives each request about 8k tokens. If you need more per request, raise `-c`. 64 GB of RAM leaves plenty of room for the cache with a 7–14B model.
- Continuous batching is on by default.

Check that it works:
```bash
curl http://SERVER:8080/v1/models -H "Authorization: Bearer change-me"
curl http://SERVER:8080/v1/chat/completions \
  -H "Authorization: Bearer change-me" -H "Content-Type: application/json" \
  -d '{"model":"team-model","messages":[{"role":"user","content":"Say hello"}]}'
```

Your teammates then set their OpenAI client's base URL to `http://SERVER:8080/v1` and use the key. If you want it running permanently, wrap that same command in a systemd service. To serve **several models from your folder**, recent llama.cpp builds have a router mode (`--models-dir`). I'm not fully sure how mature that mode is in your version, so check `llama-server --help`. A proven alternative is **llama-swap**, a small proxy that starts a `llama-server` for each model and switches between them on demand.

## Limits of a CPU-only server

- On a CPU, generation speed depends mostly on memory bandwidth. Batching gives you more **total** throughput, but each person's stream gets slower when several are active. With 10 users, that's acceptable with a 7–8B model at Q4_K_M. A 30B+ dense model will feel slow whatever server you use. Mixture-of-experts models such as Qwen3-30B-A3B run much better on a CPU than dense models of the same size.
- If you'd rather keep Ollama for now, setting `OLLAMA_NUM_PARALLEL=4` and `OLLAMA_MAX_LOADED_MODELS=1` helps somewhat. It still won't load GGUFs directly from your folder, though.

## Other options I checked

The pickfit tool found two lesser-known tools that it had installed and tested on Linux:
- **Xyntetik Runner**: a single binary with an OpenAI-compatible API, tested serving a GGUF.
- **Camelid**: a GGUF app aimed mainly at desktop use.

Neither has been shown to handle many users at once on a CPU, so I wouldn't pick either over llama-server for this. pickfit didn't test llama-server itself. My recommendation comes from its documented features, not from a pickfit test run.