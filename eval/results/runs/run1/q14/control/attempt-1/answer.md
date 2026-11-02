I'd run **[Infinity](https://github.com/michaelfeil/infinity)**, using the MIT-licensed Python **v2** server and its CPU Docker image, with two models:

- **Embeddings:** `BAAI/bge-m3` (MIT license, strong on mixed Chinese and English, handles inputs up to 8k tokens)
- **Rerank:** `BAAI/bge-reranker-v2-m3` (Apache-2.0, multilingual, built to pair with bge-m3)

One Infinity process can serve several models. It gives you an OpenAI-compatible `/v1/embeddings` endpoint and a `/v1/rerank` endpoint (Cohere/Jina style), and both models fit in 8 GB of RAM.

**Use v2, not v3.** The new native **v3** server, released in late October, puts its new code under a custom "Infinity Restricted MIT License" with restrictions on providers. The Python `infinity-emb` package and the `infinity_emb v2` command are still plain MIT. For an internal commercial tool, stick with v2 unless your legal team clears v3.

## Install and first run

I'm assuming an x86-64 Linux box with Docker installed, and internet access for the first model download only.

```bash
# 1. Make a folder to cache the models (~4.5 GB download the first time)
mkdir -p ~/infinity-cache

# 2. Start the server. Pin a specific *-cpu tag from Docker Hub (michaelf34/infinity) rather than latest-cpu.
docker run -d --name infinity --restart unless-stopped \
  -p 127.0.0.1:7997:7997 \
  -v ~/infinity-cache:/app/.cache \
  michaelf34/infinity:latest-cpu \
  v2 --engine torch \
     --model-id BAAI/bge-m3 \
     --model-id BAAI/bge-reranker-v2-m3 \
     --batch-size 8 --batch-size 8 \
     --url-prefix /v1 \
     --port 7997

# 3. Watch the logs until both models are loaded
docker logs -f infinity
```

Smoke tests:

```bash
# Embeddings (OpenAI format)
curl -s http://127.0.0.1:7997/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-m3","input":["How do I file an expense report?","如何提交报销单？"]}' | head -c 300

# Rerank
curl -s http://127.0.0.1:7997/v1/rerank -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-reranker-v2-m3","query":"报销流程","documents":["Expense reports are filed in Concur.","午餐菜单在这里。"]}'

# The full API reference is at http://127.0.0.1:7997/docs
```

To use it from code, point the OpenAI SDK at it: `OpenAI(base_url="http://127.0.0.1:7997/v1", api_key="unused")`, then call `client.embeddings.create(model="BAAI/bge-m3", input=[...])`. Rerank is a plain HTTP POST as shown above. LangChain and LlamaIndex both have Infinity integrations.

If you'd rather skip Docker: `pip install "infinity-emb[all]"`, then run `infinity_emb v2 ...` with the same flags.

## Tips for 8 GB, CPU only

- **Memory:** each model is about 568M parameters, roughly 2.2 GB in fp32, so about 5 GB total. Keep batch sizes small (4–8) and leave headroom for the OS and your app.
- **Speed:** indexing is the slow part on CPU. Chunk documents to about 300–512 tokens instead of using bge-m3's full 8k, and rerank only the top 20–50 results. Bulk indexing will take a while, but query-time latency should be fine.
- **Staying offline:** once the models are cached, add `-e HF_HUB_OFFLINE=1` so the server never contacts Hugging Face again.
- **Security:** the server has no authentication by default. Keep it bound to localhost (as above) or put it behind a reverse proxy. Check `infinity_emb v2 --help` for an `--api-key` option.

## Alternatives

- **[Hugging Face Text Embeddings Inference (TEI)](https://github.com/huggingface/text-embeddings-inference)** (Apache-2.0, actively maintained, CPU image around `cpu-1.8.x`): native `/v1/embeddings` and `/rerank`, and very fast on CPU. The catch is that it serves one model per instance, so you'd run two containers on different ports with the same two models. Choose this if being actively maintained matters more to you than having a single process.
- **Lighter or newer models:** `Qwen/Qwen3-Embedding-0.6B` and `Qwen/Qwen3-Reranker-0.6B` (Apache-2.0) are also very good at Chinese. Server support for the Qwen3 reranker varies, though, so try it before switching.
- **Licenses to avoid:** jina-embeddings-v3 and jina-reranker-v2 are CC-BY-NC, which doesn't allow commercial use.

Sources:
- [Infinity GitHub](https://github.com/michaelfeil/infinity)
- [Infinity v3.0.0 release notes (licensing, CPU image)](https://github.com/michaelfeil/infinity/releases/tag/v3.0.0)
- [Text Embeddings Inference GitHub](https://GitHub.com/huggingface/text-embeddings-inference)
- [TEI CPU release notes](https://releases.sh/release/rel_BwxGl_zBfEgFELWANCF50)