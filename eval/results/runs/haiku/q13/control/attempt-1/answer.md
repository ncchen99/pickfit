## Recommendation: llama.cpp's `llama-server`

It's free and MIT-licensed, loads any GGUF directly from a path with `-m`, serves OpenAI-compatible endpoints (`/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`), and handles parallel requests with continuous batching across slots. It never touches Ollama's model store.

I'm working from memory of current llama.cpp behavior and couldn't check the latest release here, so run `llama-server --help` on your build to confirm flag names.

**Assumptions:** Ubuntu/Debian-style Linux, GGUF files readable by the user running the server, and teammates reaching the server over your LAN.

## Install

```bash
sudo apt update && sudo apt install -y build-essential cmake git libcurl4-openssl-dev
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON
cmake --build build --config Release -j "$(nproc)" --target llama-server
```

`-DGGML_NATIVE=ON` compiles for your CPU's AVX2/AVX-512 support, which matters a lot for CPU speed. Prebuilt Linux CPU binaries are also on the project's GitHub Releases page if you'd rather skip compiling.

## First run

```bash
export LLAMA_KEY="$(openssl rand -hex 24)"   # shared secret for teammates

~/llama.cpp/build/bin/llama-server \
  -m /path/to/your/gguf/folder/model-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8080 \
  -np 4 \                 # 4 parallel slots
  -c 16384 \              # total context, split across slots (4096 each)
  -t "$(nproc)" \         # set to physical core count if the box has hyperthreading
  --api-key "$LLAMA_KEY"
```

Quick test from another machine:

```bash
curl http://SERVER_IP:8080/v1/chat/completions \
  -H "Authorization: Bearer $LLAMA_KEY" -H "Content-Type: application/json" \
  -d '{"model":"local","messages":[{"role":"user","content":"Say hi"}]}'
```

Teammates set their OpenAI-compatible client to `base_url=http://SERVER_IP:8080/v1` with the key as the API key. The `model` field is mostly ignored because the server runs one model.

## Things to set expectations on

- **CPU concurrency has limits.** Token generation is limited by memory bandwidth, so parallel requests share that bandwidth. Batching helps throughput, but per-user speed still drops as more people generate at once. With 10 teammates, plan for roughly 2–4 active slots, and expect queuing at peak times.
- **Model size is the biggest lever.** Start with a 7–8B model at Q4_K_M (about 5 GB) and step up only if speed is acceptable. A 30B-class model at Q4 needs about 20 GB and will be much slower per user.
- **Memory grows per slot.** Each slot holds its own KV cache, so raise `-np` and `-c` together and watch RAM with `free -h` under load.
- **Ollama may not be the only cause.** Check whether you're running a large model with many concurrent requests. Ollama also defaults to parallel slots, so comparing the same model and settings in both tools is a fair test.

## Alternatives, if llama-server doesn't fit

- **LocalAI** (MIT): loads GGUF from a models folder and offers an OpenAI API. It's heavier to set up.
- **llama-cpp-python server** (MIT): a Python wrapper with the same engine. Simpler to script, but usually with less concurrency control.
- **vLLM CPU** (Apache-2.0): better batching in theory, but its GGUF support is limited and it's built around safetensors, so I wouldn't start there.

Sources: none; this answer is from knowledge, not a live lookup. The llama.cpp project is at https://github.com/ggml-org/llama.cpp.