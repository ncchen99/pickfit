I recommend **Infinity's MIT-licensed v2 server (`infinity-emb`), CPU Docker image**, running **BAAI/bge-m3** for embeddings and **BAAI/bge-reranker-v2-m3** for reranking. pickfit had no verified tool for this, so this comes from the project docs and my own knowledge. I haven't tested it on your setup.

## Why this setup
- **One process serves both models.** It has an OpenAI-compatible embeddings endpoint and a `/rerank` endpoint.
- **Both models handle mixed English and Chinese well.** They're from the BGE-M3 family, which is multilingual.
- **Licenses allow commercial use:**
  - Infinity v2: MIT
  - bge-m3: MIT
  - bge-reranker-v2-m3: Apache-2.0
- **License warning:** In Oct 2026 the repo added a new Rust "v3" server under a custom *"Infinity Restricted MIT License 1.0"*. Only the Python `infinity-emb` packages are still plain MIT. **Pin a v2 `x.x.x-cpu` tag. Don't use the `infinity_v3` images.** Ask whoever handles licensing at your company to confirm this.

## Install and first run
I'm assuming Docker is available. I believe 0.0.77 is the latest v2 tag, but check Docker Hub before you pin it.

```bash
mkdir -p ~/infinity-cache
docker run -d --name infinity -p 7997:7997 \
  -v ~/infinity-cache:/app/.cache \
  michaelf34/infinity:0.0.77-cpu \
  v2 --model-id BAAI/bge-m3 --model-id BAAI/bge-reranker-v2-m3 \
     --url-prefix /v1 --port 7997 --batch-size 8
```

The first start downloads about 4–5 GB of weights. After that it runs fully offline from the cache folder. Watch progress with `docker logs -f infinity`.

Test it:
```bash
curl localhost:7997/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-m3","input":["退款政策是什么？","What is the refund policy?"]}'

curl localhost:7997/v1/rerank -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-reranker-v2-m3","query":"refund policy",
       "documents":["退款须在30天内申请。","Our office is in Berlin."]}'
```

In your RAG code, point an OpenAI client at `base_url="http://<box>:7997/v1"` with any dummy API key.

Things I'm assuming here, so check them if something fails:
- Running two models by repeating `--model-id`, and getting the `/v1` paths from `--url-prefix /v1`, is how v2 worked as far as I know.
- Without `--url-prefix`, the paths are `/embeddings` and `/rerank`.
- The interactive docs at `localhost:7997/docs` show the exact paths.

## Memory on 8 GB
- Each model has about 568M parameters, so both together use roughly 4.5–5 GB of RAM in fp32 on CPU. That fits, but not with much to spare.
- Keep the batch size small.
- If it's too much, swap the embedder for `intfloat/multilingual-e5-small` (MIT, about 118M parameters). Retrieval quality will drop somewhat.
- Expect reranking on CPU to take a noticeable amount of time. Rerank only the top 20–50 results.

## Alternatives
1. **llama.cpp `llama-server`** (MIT, actively maintained). Best if RAM is the real limit.
   - Quantized GGUF versions of the same two models use much less memory.
   - It has `/v1/embeddings` (with `--embedding`) and `/v1/rerank` (with `--reranking`).
   - The docs don't say one process can do both, so plan on running two instances, e.g. ports 8080 and 8081.
2. **LocalAI** (MIT). One server with both `/v1/embeddings` and `/v1/rerank` (its reranker uses the `rerankers` backend).
   - It's heavier, and reranking needs the non-"core" images that include Python.

Sources:
- [michaelfeil/infinity (GitHub)](https://github.com/michaelfeil/infinity)
- [Infinity LICENSE](https://github.com/michaelfeil/infinity/blob/main/LICENSE)
- [michaelf34/infinity tags (ecosyste.ms)](https://packages.ecosyste.ms/registries/hub.docker.com/namespaces/michaelf34)
- [HF discussion on Infinity tags](https://huggingface.co/WhereIsAI/UAE-Large-V1/discussions/22)
- [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [LocalAI reranker docs](https://localai.io/docs/features/reranker/)