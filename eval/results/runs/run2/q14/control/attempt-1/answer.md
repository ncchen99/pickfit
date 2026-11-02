I'd run **Infinity** (`michaelfeil/infinity`, MIT license) with **BAAI/bge-m3** for embeddings and **BAAI/bge-reranker-v2-m3** for reranking.

Infinity is the one open-source server I know of that does all of what you asked in a single process: it serves several models at once, gives you an OpenAI-compatible embeddings endpoint and a `/rerank` endpoint, and has CPU Docker images. Both models are strong on mixed Chinese and English text. bge-m3 is MIT-licensed and bge-reranker-v2-m3 is Apache-2.0, so commercial use is allowed. Check the model cards yourself before you ship.

**Main risk:** Infinity's development seems to have slowed. Its changelog's latest entry is July 2025, and I couldn't find a release from 2026 ([GitHub](https://github.com/michaelfeil/infinity)). It works for this use case, but pin the image version you test and don't expect new features. If that worries you, there's a fallback at the end.

## Assumptions
- Docker is available. If not, the pip steps are below.
- Memory is the tightest constraint. Both models are about 568M parameters, so expect roughly 4–5 GB of RAM total in fp32. That fits in 8 GB, but leave room for your app and vector database.
- I didn't run anything on this machine. Commands and flags are from the Infinity docs and my knowledge, so check them with `--help` on your version.

## Install and first run (Docker)

```bash
# 1. Pull the CPU image (pin a specific tag from Docker Hub once you've tested it)
docker pull michaelfeil/infinity:latest-cpu

# 2. Run both models in one server, with /v1 prefix for OpenAI-style paths
docker run -d --name infinity \
  -p 7997:7997 \
  -v $HOME/infinity-cache:/app/.cache \
  michaelfeil/infinity:latest-cpu \
  v2 \
  --model-id BAAI/bge-m3 \
  --model-id BAAI/bge-reranker-v2-m3 \
  --engine torch \
  --device cpu \
  --batch-size 8 \
  --url-prefix /v1 \
  --port 7997
```

The first start downloads about 4.5 GB of weights from Hugging Face. After that, everything runs offline from the mounted cache. You can set `HF_HUB_OFFLINE=1` once the cache is filled.

**Without Docker:**
```bash
python3 -m venv ~/infinity-venv && source ~/infinity-venv/bin/activate
pip install "infinity-emb[all]"
infinity_emb v2 --model-id BAAI/bge-m3 --model-id BAAI/bge-reranker-v2-m3 \
  --engine torch --device cpu --batch-size 8 --url-prefix /v1 --port 7997
```

**Smoke tests:**
```bash
# Embeddings (OpenAI-compatible)
curl http://localhost:7997/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-m3","input":["报销流程是什么？","How do I file an expense report?"]}'

# Rerank
curl http://localhost:7997/v1/rerank -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-reranker-v2-m3","query":"报销流程",
       "documents":["Expense reports are filed in the finance portal.","今天天气很好。"]}'

# Interactive API docs
open http://localhost:7997/docs
```

From your RAG code, point the OpenAI SDK at it with `OpenAI(base_url="http://localhost:7997/v1", api_key="unused")`. Then use `client.embeddings.create(model="BAAI/bge-m3", input=[...])`. For reranking, send a plain HTTP POST to `/v1/rerank`.

## Tips for CPU-only
- **Chunk to about 300–512 tokens.** bge-m3 accepts up to 8192 tokens, but long inputs are slow on CPU.
- **Rerank only the top 20–50 results** from vector search, not hundreds.
- **Low on RAM:** swap the reranker for `BAAI/bge-reranker-base` (about 278M parameters, good on Chinese and English; check its license on the model card). You can also try `--engine optimum` (ONNX) for faster CPU inference, but test it first because ONNX export doesn't work for every model.
- **Don't use** `jina-reranker-v2-*` or similar models with CC-BY-NC licenses, since they don't allow commercial use.

## Fallback if you want something more actively maintained
- **llama.cpp `llama-server`** with GGUF (Q8) versions of the same two models. It's lighter on RAM (roughly 0.6 GB per model) and very actively developed. It has `/v1/embeddings` and `/v1/rerank` (started with `--embedding --pooling rank --reranking`). However, pooling is set per process, so you'll most likely need **two processes on two ports** rather than one server ([rerank how-to](https://www.simplified.guide/llama-cpp/server-call-rerank-api), [embeddings docs](https://www.mintlify.com/ggml-org/llama.cpp/inference/embeddings)).
- **Hugging Face TEI** (Apache-2.0) is also solid on CPU, but it serves one model per instance, so it would also mean two containers.

Sources:
- [michaelfeil/infinity on GitHub](https://github.com/michaelfeil/infinity)
- [Superlinked: Infinity migration notes](https://superlinked.com/docs/migrate/infinity)
- [llama.cpp rerank API guide](https://www.simplified.guide/llama-cpp/server-call-rerank-api)
- [llama.cpp embeddings docs](https://www.mintlify.com/ggml-org/llama.cpp/inference/embeddings)
- [Lemonade llama.cpp API notes](https://lemonade-server.ai/api/llamacpp.html)
- [r/OpenWebUI: reranking with llama.cpp](https://redlib.hbubli.cc/r/OpenWebUI/comments/1kz72tn/reranking_with_llamacpp)