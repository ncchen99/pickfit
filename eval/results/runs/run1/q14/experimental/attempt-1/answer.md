**Status:** I checked pickfit's catalog, which had no verified tool for this, and then checked the project docs. None of this was installed or tested on my side.

## Recommendation: Xinference (Apache-2.0) serving bge-m3 and bge-reranker-v2-m3

Xinference is the simplest way to get both endpoints from **one server process**:

- **Embeddings:** `POST /v1/embeddings` (OpenAI-compatible)
- **Rerank:** `POST /v1/rerank` (body: `model`, `query`, `documents`, `top_n`; Cohere/Jina-style)
- It has an official **CPU Docker image** (`xprobe/xinference:latest-cpu`).
- It's built by a Chinese team, so English+Chinese models are a core use case.

**Models (licenses allow commercial use):**

| Role | Model | License | Notes |
|---|---|---|---|
| Embeddings | `BAAI/bge-m3` | MIT | Strong in Chinese and English, 8k context, 1024-dim |
| Rerank | `BAAI/bge-reranker-v2-m3` | Apache-2.0 | Same model family, built for multiple languages |

**Avoid** `jina-embeddings-v3` and `jina-reranker-v2`. They're CC-BY-NC, which doesn't allow commercial use. Check each model's license on its Hugging Face card before you deploy.

**RAM assumption:** Both models are about 570M parameters and run in full precision on CPU. Together with Xinference's own overhead, expect roughly **5–6 GB**. That fits in 8 GB, but not with much room to spare. If memory gets tight, see the fallbacks below.

### Install and first run (Docker assumed)

```bash
# 1. Start the server; the volume keeps downloaded models across restarts
docker run -d --name xinference -p 9997:9997 \
  -v $HOME/xinference:/root/.xinference \
  -v $HOME/.cache/huggingface:/root/.cache/huggingface \
  xprobe/xinference:latest-cpu \
  xinference-local --host 0.0.0.0 --port 9997
# (If Hugging Face is slow or blocked from your network, add: -e XINFERENCE_MODEL_SRC=modelscope)

# 2. Load the two models (they download on first launch)
docker exec xinference xinference launch --model-name bge-m3 --model-type embedding \
  --endpoint http://127.0.0.1:9997
docker exec xinference xinference launch --model-name bge-reranker-v2-m3 --model-type rerank \
  --endpoint http://127.0.0.1:9997

# 3. Test embeddings (OpenAI-compatible)
curl http://localhost:9997/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"model":"bge-m3","input":["报销流程是什么？","What is the expense process?"]}'

# 4. Test rerank
curl http://localhost:9997/v1/rerank -H 'Content-Type: application/json' \
  -d '{"model":"bge-reranker-v2-m3","query":"报销流程",
       "documents":["Expense reports are filed in the HR portal.","午餐菜单每周更新。"],"top_n":2}'
```

**In your app:** point the OpenAI SDK at `base_url="http://<host>:9997/v1"` with any dummy API key, and call `/v1/rerank` directly. Models aren't reloaded automatically after a container restart, so put the two `launch` commands in a startup script. Once the models are cached, nothing leaves the machine. If you set `HF_HUB_OFFLINE=1`, it also stops checking Hugging Face for updates.

## Fallbacks

1. **llama.cpp `llama-server` (MIT): the lowest-RAM option.** It serves `/v1/embeddings` and `/v1/rerank` from 8-bit GGUF versions of the same two models, at roughly 600 MB each. The catch is one model per process, so you'd run two processes on two ports (for example, `llama-server -m bge-m3-Q8_0.gguf --embedding --port 8081` and `llama-server -m bge-reranker-v2-m3-Q8_0.gguf --reranking --port 8082`). Choose this if Xinference uses too much memory.
2. **Hugging Face Text Embeddings Inference (Apache-2.0).** It's fast and lightweight on CPU (`ghcr.io/huggingface/text-embeddings-inference:cpu-<version>`; the newest tag I found was `cpu-1.8.1`). It also serves only one model per container, so you'd need two containers. Its rerank route is `/rerank`, not `/v1/rerank`. To my knowledge it also has an OpenAI-style `/v1/embeddings` route, but I didn't confirm that here, so check the `/docs` page once it's running.
3. **Smaller models if you stay on Xinference:** `Qwen3-Embedding-0.6B` and `Qwen3-Reranker-0.6B` (both Apache-2.0, very good at Chinese). Neither of these is much smaller than the bge pair, though. To actually save RAM, swap in a smaller reranker such as `bge-reranker-base`.

**Why not Infinity:** Its newer v3 server uses a custom "Infinity Restricted MIT" license, and for company use that needs a legal review first. **Why not Ollama:** it has no rerank endpoint.

## Sources
- [Xinference rerank docs](https://inference.readthedocs.io/en/latest/models/model_abilities/rerank.html) · [Xinference Docker image docs](https://inference.readthedocs.io/en/latest/getting_started/using_docker_image.html) · [Railway Xinference guide](https://railway.com/deploy/xinference) · [cnblogs CPU bge-reranker-v2-m3 deployment](https://www.cnblogs.com/tan-cong/p/22745462)
- [LocalAI reranker docs](https://localai.io/docs/features/reranker/) (another single-server option: `/v1/rerank` through the `rerankers` backend, MIT, needs a Python-enabled image)
- [Hugging Face TEI](https://GitHub.com/huggingface/text-embeddings-inference) · [TEI release notes](https://releases.sh/release/rel_BwxGl_zBfEgFELWANCF50)
- [michaelfeil/infinity](https://github.com/michaelfeil/infinity) · [Superlinked Infinity migration note](https://superlinked.com/docs/migrate/infinity.md)