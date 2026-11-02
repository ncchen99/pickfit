I'd run **Infinity v2** (`infinity-emb`, MIT license) in its CPU Docker image, serving two models:

- **Embeddings: `BAAI/bge-m3`** (MIT license). It handles mixed English and Chinese well, takes up to 8K tokens, and has 1024 dimensions.
- **Reranker: `BAAI/bge-reranker-v2-m3`** (Apache 2.0). It's the matching multilingual reranker.

One process loads both models and exposes an OpenAI-style embeddings endpoint plus a `/rerank` endpoint. The latest PyPI release is 0.0.78 (Oct 19, 2026), so the project is still being updated.

**Use v2, not v3.** The project now also has a "v3" Rust server. It's built only for NVIDIA GPUs, and new v3 code is under a custom "Infinity Restricted MIT License," which is source-available rather than plain MIT. The Python v2 server and its Docker images stay standard MIT. That's the one you want.

## Install and first run (CPU, Docker)

```bash
mkdir -p ~/infinity-cache

docker run -d --name infinity \
  -p 7997:7997 \
  -v ~/infinity-cache:/app/.cache \
  michaelf34/infinity:latest-cpu \
  v2 \
  --model-id BAAI/bge-m3 \
  --model-id BAAI/bge-reranker-v2-m3 \
  --port 7997 \
  --url-prefix /v1
```

- After it works, pin a version tag instead of `latest-cpu`. The project uses `x.x.x-cpu` tags, so `0.0.78-cpu` should exist, but check Docker Hub.
- The first start downloads about 4–5 GB of model weights into `~/infinity-cache`. After that you can add `-e HF_HUB_OFFLINE=1` so the server never contacts Hugging Face.
- Without Docker, you can run `pip install "infinity-emb[all]"` and then the same `infinity_emb v2 --model-id ... --model-id ...` command.

**Check it's working.** Open `http://localhost:7997/docs` to see the exact routes. I'm assuming `--url-prefix /v1` puts every route under `/v1/...`:

```bash
# Embeddings
curl -s localhost:7997/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-m3","input":["报销流程是什么？","How do I file an expense report?"]}'

# Rerank
curl -s localhost:7997/v1/rerank -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-reranker-v2-m3","query":"报销流程",
       "documents":["Expense reports are filed in the HR portal.","今天天气很好。"]}'
```

**Use it from your RAG code.** Point the OpenAI SDK at the server with `OpenAI(base_url="http://<box>:7997/v1", api_key="unused")` and call `client.embeddings.create(model="BAAI/bge-m3", input=[...])`. The OpenAI SDK has no rerank method, so call `/v1/rerank` with a plain HTTP POST.

## Fitting in 8 GB of RAM

- In fp32, each model takes roughly 2.2–2.5 GB, so both together use about 5 GB. That fits, but leave headroom. Don't run a local LLM on the same box.
- CPU speed is fine for queries. Indexing a large set of documents will be slow, so do it in batches (for example, `--batch-size 8`) and only once.
- Rerank only the top 20–50 results per query. The reranker is the slower step per query.
- If memory or speed becomes a problem:
  - Swap the reranker for **`BAAI/bge-reranker-base`**. It's about half the size and still handles Chinese and English.
  - Try `--engine optimum` (ONNX), which is usually faster on CPU. It needs an ONNX export of each model.

## Licenses to watch

- **Avoid `jina-reranker-v2`.** It's CC-BY-NC, which doesn't allow commercial use.
- **Infinity v3 images** carry the restricted license mentioned above.
- I didn't re-check the BGE model licenses today. Confirm MIT for bge-m3 and Apache 2.0 for bge-reranker-v2-m3 on each model card before you ship.

## Alternatives

- **Hugging Face Text Embeddings Inference (TEI)**, Apache 2.0. It has a fast CPU build and good `/v1/embeddings` and `/rerank` endpoints, but it serves one model per process. You'd run two containers, which doesn't meet your "one server" requirement.
- **LocalAI** (MIT) or **Xinference** (Apache 2.0). Each gives you embeddings and rerank in one server, but both are heavier, general-purpose platforms.
- **Qwen3-Embedding-0.6B and Qwen3-Reranker-0.6B** (Apache 2.0) are strong on Chinese. I'm not sure Infinity supports them well, so start with the BGE pair.

Sources:
- [michaelfeil/infinity (GitHub)](https://github.com/michaelfeil/infinity)
- [infinity-emb on PyPI](https://pypi.org/project/infinity-emb)
- [AarhusAI/embedding_infinity_docker](https://github.com/AarhusAI/embedding_infinity_docker)
- [sourcepulse: infinity](https://www.sourcepulse.org/projects/1827666)