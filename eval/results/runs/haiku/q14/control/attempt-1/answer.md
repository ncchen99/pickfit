## Recommendation

Run **Hugging Face Text Embeddings Inference (TEI)** in two CPU containers, one for embeddings and one for reranking:

- **Embeddings:** `BAAI/bge-m3` (MIT license). It is multilingual, strong on both English and Chinese, and supports up to 8k tokens.
- **Reranker:** `BAAI/bge-reranker-v2-m3` (Apache-2.0). It is the cross-encoder companion to bge-m3.

TEI is Apache-2.0 and serves an OpenAI-compatible `/v1/embeddings` route plus a `/rerank` route. Each container hosts one model, so you run two containers.

**Alternative:** Qwen3-Embedding-0.6B and Qwen3-Reranker-0.6B (both Apache-2.0) are newer and also strong on Chinese. Use them if bge-m3 quality is not enough on your data. Check the MTEB multilingual and Chinese leaderboards before switching, since I haven't benchmarked them on your documents.

## Install

Assumes Docker Engine is installed on the Linux box and you have roughly 10 GB of free disk for model downloads and cache.

```bash
# 1. Pick the CPU image tag from the TEI releases page (github.com/huggingface/text-embeddings-inference).
#    I'm writing "cpu-1.8" as a placeholder; confirm the current tag before pulling.
docker pull ghcr.io/huggingface/text-embeddings-inference:cpu-1.8

# 2. Cache directory so models download once
mkdir -p ~/tei-cache
```

## First run

```bash
# Embeddings server on :8080
docker run -d --name tei-embed -p 8080:80 -v ~/tei-cache:/data \
  ghcr.io/huggingface/text-embeddings-inference:cpu-1.8 \
  --model-id BAAI/bge-m3 --max-batch-tokens 8192

# Reranker server on :8081
docker run -d --name tei-rerank -p 8081:80 -v ~/tei-cache:/data \
  ghcr.io/huggingface/text-embeddings-inference:cpu-1.8 \
  --model-id BAAI/bge-reranker-v2-m3 --max-batch-tokens 8192

# Wait for the first model download, then check health
docker logs -f tei-embed     # wait for "Ready"
```

Smoke tests:

```bash
# OpenAI-compatible embeddings
curl http://localhost:8080/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"BAAI/bge-m3","input":["quarterly revenue report","季度营收报告"]}'

# Rerank (TEI format: query + texts, returns index and score per text)
curl http://localhost:8081/rerank \
  -H "Content-Type: application/json" \
  -d '{"query":"refund policy","texts":["Refunds within 30 days","Office parking rules"]}'
```

Your RAG app can point any OpenAI SDK at `http://localhost:8080/v1` for embeddings. Rerank calls go to `http://localhost:8081/rerank`, which is not an OpenAI-standard endpoint.

## Things to watch

- **Memory:** Both models are about 0.5–0.6B parameters. Expect roughly 2–3 GB each at runtime. That fits in 8 GB but leaves little headroom. If the box swaps, lower `--max-batch-tokens` or run the reranker only when needed.
- **Speed:** CPU embedding of long Chinese documents is slow. Chunk to roughly 512 tokens and embed in batches during ingestion, not at query time.
- **Air-gapped use:** Download the models once on a connected machine, copy `~/tei-cache` over, and mount it. The servers then need no internet access.
- **Version pins:** I did not verify current TEI tags or endpoint details live in this session. Check the TEI README for the `/v1/embeddings` route and the current CPU tag before relying on them.
- **Single-server option:** If you want one process serving both, look at Infinity (`michaelfeil/infinity`, MIT). It exposes OpenAI-compatible embeddings and a rerank endpoint, and installs with pip. It is a reasonable fallback, but I'd still start with TEI because its CPU images are simpler to run.