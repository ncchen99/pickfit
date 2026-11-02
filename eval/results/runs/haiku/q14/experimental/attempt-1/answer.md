## Recommendation: Infinity serving BAAI/bge-m3 and BAAI/bge-reranker-v2-m3

Run [Infinity](https://github.com/michaelfeil/infinity) (MIT) as one server. It exposes an embeddings endpoint and a rerank endpoint on CPU, and it hosts both models on one port. Use these models:

- **Embeddings: `BAAI/bge-m3`** (MIT). Multilingual, strong on English and Chinese, 8192-token input, dense output of 1024 dimensions.
- **Reranker: `BAAI/bge-reranker-v2-m3`** (Apache-2.0). A multilingual cross-encoder built for the same family as bge-m3.

Both licenses allow commercial use. Confirm them on each model card before you ship, since licenses can change between versions.

I have not tested this stack on your hardware. The memory numbers below are estimates.

## Install

Docker is the simplest route. Check the Infinity README for the current image tag and flags first.

```bash
docker run -d --name infinity -p 7997:7997 \
  -v "$HOME/.cache/infinity:/app/.cache" \
  michaelfeil/infinity:latest \
  v2 --model-id BAAI/bge-m3 --model-id BAAI/bge-reranker-v2-m3 --port 7997
```

Without Docker, install into a virtualenv:

```bash
python3 -m venv ~/rag-serve && source ~/rag-serve/bin/activate
pip install "infinity-emb[all]"
infinity_emb v2 --model-id BAAI/bge-m3 --model-id BAAI/bge-reranker-v2-m3 --port 7997
```

The first start downloads about 4–5 GB of weights from Hugging Face. Plan for that.

## First run and checks

1. Open `http://localhost:7997/docs` to confirm the server is up and to see the routes it actually exposes.
2. Test embeddings:
```bash
curl http://localhost:7997/embeddings -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-m3","input":["用于测试的中文句子","An English test sentence"]}'
```
3. Test reranking:
```bash
curl http://localhost:7997/rerank -H 'Content-Type: application/json' \
  -d '{"model":"BAAI/bge-reranker-v2-m3","query":"退款政策","documents":["退款需在30天内提交申请。","The cafeteria opens at 8am."]}'
```

The refund document should score higher. If it doesn't, check the model name in the request.

Infinity's route names and whether it also serves a `/v1/` prefix have changed across versions. Check `/docs` and point your client at what it shows. Your code can be written against the OpenAI client by setting `base_url` to `http://localhost:7997`.

## Things to watch on 8 GB CPU-only

- **Memory:** Both models in fp32 need roughly 5 GB together, plus overhead. That fits, but leaves little room for anything else. Close other heavy processes, and test with your real batch sizes.
- **Speed:** The reranker is a cross-encoder, so it scores each query-document pair. Rerank only the top 20–50 retrieved chunks, not the whole corpus.
- **Chunk size:** Keep chunks around 256–512 tokens. Embedding long inputs on CPU is slow, even though bge-m3 accepts 8192 tokens.
- **Mixed-language retrieval:** bge-m3 handles Chinese and English in one vector space, so you can use a single index. Test with a few real Chinese and English queries before you trust it.

## Fallback and upgrade paths

- **If Infinity's multi-model setup gives you trouble:** run [llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-server` (MIT) with GGUF builds of both models, one process per model. Use `--embedding` for embeddings and `--reranking` for rerank. This uses less memory if you pick quantized GGUFs, but the quality can shift slightly.
- **Newer option:** Qwen3-Embedding-0.6B and Qwen3-Reranker-0.6B are Apache-2.0 and worth benchmarking against bge on your own documents. Check how well your serving tool supports them before you switch.

## Assumptions

- Your Linux box can run Docker or Python 3.10+ and has outbound access during setup. After the models are cached, it can run offline.
- "OpenAI-compatible" means the request and response shapes match. You will need to confirm the exact route paths on the running server.