I recommend **Hugging Face Text Embeddings Inference (TEI)**, CPU build, serving **BAAI/bge-m3** for embeddings and **BAAI/bge-reranker-v2-m3** for reranking.

I haven't installed or tested any of this. The pickfit catalog had no tested tool for this job and also named TEI as an untested suggestion. The details below come from the project READMEs and what I already know.

**One assumption you should know about:** TEI runs **one model per process**. So "one server" here means one Docker Compose stack with two containers from the same image. If you need a single port, put a 5-line reverse proxy in front. If it must be a single process, see the alternative at the end.

## Why this setup
- **Licenses allow commercial use:** TEI is Apache-2.0, bge-m3 is MIT and bge-reranker-v2-m3 is Apache-2.0.
- **Endpoints:** TEI has an OpenAI-style `/v1/embeddings` route and a `/rerank` route.
- **English and Chinese:** BAAI trained both models on large Chinese and English data, and they're among the strongest open models for mixed zh/en retrieval. bge-m3 handles inputs up to 8192 tokens.
- **Runs on CPU only:** there's an official CPU image, `ghcr.io/huggingface/text-embeddings-inference:cpu-1.9` (use `cpu-arm64-1.9` on ARM).
- **Memory:** each model is about 568M parameters, roughly 2.2–2.5 GB in fp32. Together they need about 5–6 GB, which fits in 8 GB but leaves little room. If you run short, switch the reranker to **BAAI/bge-reranker-base** (about 278M parameters, MIT, en/zh). That saves about 1.5 GB at some cost in quality.

## Install and first run
Requirements: Docker with Compose, and about 5 GB of disk for the model downloads.

1. Create `docker-compose.yml`:
```yaml
services:
  embed:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.9
    command: --model-id BAAI/bge-m3 --served-model-name bge-m3 --max-batch-tokens 8192 --auto-truncate
    ports: ["8080:80"]
    volumes: ["./tei-data:/data"]
    restart: unless-stopped
  rerank:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.9
    command: --model-id BAAI/bge-reranker-v2-m3 --max-batch-tokens 8192 --auto-truncate
    ports: ["8081:80"]
    volumes: ["./tei-data:/data"]
    restart: unless-stopped
```
2. Start it with `docker compose up -d`, then follow the logs with `docker compose logs -f`. The first start downloads the models into `./tei-data`. After that it runs fully offline.
3. Test the embeddings endpoint (OpenAI format):
```bash
curl -s localhost:8080/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"model":"bge-m3","input":["报销流程是什么？","How do I file an expense report?"]}' | head -c 300
```
4. Test the rerank endpoint:
```bash
curl -s localhost:8081/rerank -H 'Content-Type: application/json' \
  -d '{"query":"报销流程","texts":["Expense reports are filed in the HR portal.","公司年会在十二月举行。"]}'
```
   The expense-report text should score highest, which shows matching works across languages.
5. To use it from your app, point any OpenAI SDK at it with `base_url="http://<box>:8080/v1"`, `api_key="unused"` and `model="bge-m3"`. Call `:8081/rerank` with plain HTTP. LangChain and LlamaIndex both have TEI integrations.
6. Optional single port: add nginx or Caddy and route `/v1/embeddings` to `embed:80` and `/rerank` to `rerank:80`.

**Tuning tips:**
- If memory gets tight, lower `--max-batch-tokens` (try 4096) and the concurrency on the client side.
- Chunk documents to about 512–1024 tokens. Long inputs are slow on CPU, especially for the reranker.
- Only rerank the top 20–50 results.

## Alternatives
- **Infinity (`infinity_emb`, Python)** serves both models from **one process**, for example `infinity_emb v2 --model-id BAAI/bge-m3 --model-id BAAI/bge-reranker-v2-m3 --device cpu --url-prefix /v1`. **License caveat:** the Python package is MIT, but the repo's new v3 server (Oct 2026) uses a custom "Infinity Restricted MIT License." If you choose it, pin a pre-v3 `infinity-emb` release and have someone check the license.
- **llama.cpp `llama-server`** (MIT) supports `--embeddings` and `--reranking` with GGUF-quantized models, which use less RAM. It also runs one model per instance, so you'd still need two processes.
- **Avoid the jina-embeddings-v3 and jina-reranker-v2 weights.** They're CC-BY-NC, which doesn't allow commercial use.

Sources: [TEI on GitHub](https://github.com/huggingface/text-embeddings-inference), [Infinity on GitHub](https://github.com/michaelfeil/infinity)