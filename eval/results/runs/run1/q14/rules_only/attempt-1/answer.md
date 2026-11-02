I recommend running **Infinity v2**, the Python CPU build (MIT license), with two models: **BAAI/bge-m3** for embeddings (MIT) and **BAAI/bge-reranker-v2-m3** for reranking (Apache-2.0). One process loads both models and serves an OpenAI-compatible `/v1/embeddings` endpoint plus a `/v1/rerank` endpoint. Both models are trained for multilingual text and are among the most widely used choices for mixed Chinese and English RAG. Both licenses allow commercial use.

I haven't run any of this. These steps come from the docs and should be tested on your box.

**Assumptions:** Docker is available, the box is x86_64, and it can reach Hugging Face once to download the models. After that it works offline.

## Use v2, not v3
Infinity released a v3 rewrite in Rust in late October 2026. On its README, v3 only comes as an NVIDIA GPU image, and its new code is under a custom "Infinity Restricted MIT License", which is not a standard open-source license. That rules it out for you. The older Python v2 server still exists separately, is plain MIT, and has CPU Docker images. The trade-off is that the latest dated news I could find for v2 is from late 2024, so treat it as stable but not actively developed. Pin a specific image tag.

## Install and first run
```bash
# 1. Model cache directory, so the models download only once
mkdir -p ~/infinity-cache

# 2. Start the server (CPU image; replace latest-cpu with a pinned x.x.x-cpu tag from Docker Hub)
docker run -d --name infinity --restart unless-stopped \
  --memory 7g -p 7997:7997 \
  -v ~/infinity-cache:/app/.cache \
  michaelfeil/infinity:latest-cpu \
  v2 --model-id BAAI/bge-m3 --model-id BAAI/bge-reranker-v2-m3 \
     --batch-size 8 --batch-size 8 \
     --url-prefix /v1 --port 7997

# 3. Watch the logs until both models finish loading
docker logs -f infinity
```

Test it:
```bash
# Embeddings (OpenAI format)
curl -s localhost:7997/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-m3","input":["报销流程是什么？","How do I file an expense report?"]}' | head -c 300

# Rerank
curl -s localhost:7997/v1/rerank -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-reranker-v2-m3","query":"报销流程",
       "documents":["Expense reports are filed in the HR portal.","今天天气很好。"]}'
```
Point your OpenAI client at `base_url="http://<host>:7997/v1"` with any dummy API key. The endpoint list is at `http://<host>:7997/docs`.

## Fitting in 8 GB of RAM
- In fp32, each model takes about 2.3 GB, so both together plus the runtime come to roughly 5–6 GB. That fits, but not with much room to spare. Keep the batch size small and keep `--memory` set so the container can't push the machine into swap.
- Split documents into chunks of about 300–512 tokens. bge-m3 accepts up to 8k tokens, but long inputs are very slow on CPU.
- You can try `--engine optimum` (ONNX) to speed up CPU inference. Keep the default torch engine until it works.
- Don't use the Jina v2 rerankers. They are CC-BY-NC, which bans commercial use.

## Fallback: llama.cpp `llama-server` (MIT)
Use this if v2's age worries you or memory is too tight. llama.cpp is actively maintained and runs well on CPU. It serves `/v1/embeddings` and `/v1/rerank`, and its docs name `bge-reranker-v2-m3` as a supported reranker. With 8-bit quantized GGUF copies of the same two models, each needs only about 0.6 GB.

The catch is that each process normally serves one model. You would run two processes and put a small reverse proxy in front if you want a single URL:
```bash
llama-server -m bge-m3-Q8_0.gguf --embedding --pooling cls -ub 8192 --port 8081
llama-server -m bge-reranker-v2-m3-Q8_0.gguf --reranking -ub 8192 --port 8082
```
Download the GGUF files from Hugging Face and check each repo's license. Newer builds have a router mode that serves several models from one process, but I couldn't confirm from the official docs that you can enable embedding or reranking per model in that mode.

I also asked pickfit, a catalog of tested lesser-known tools. It had nothing matching this request.

Sources:
- [Infinity GitHub (v3 README, license, endpoints)](https://github.com/michaelfeil/infinity)
- [Infinity releases](https://github.com/michaelfeil/infinity/releases)
- [infinity-emb on PyPI](https://pypi.org/project/infinity-emb)
- [Superlinked: Infinity migration doc](https://superlinked.com/docs/migrate/infinity.md)
- [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [Llama-Server router mode guide](https://glukhov.org/llm-hosting/llama-cpp/llama-server-router-mode/)
- [LocalAI reranker docs](https://localai.io/docs/features/reranker/)