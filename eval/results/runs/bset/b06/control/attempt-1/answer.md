# Recommended local model for Ask O11y

**My main pick is Qwen3-30B-A3B-Instruct-2507, quantized to Q4_K_M, with a context window of at least 32k tokens. Plan on 24 GB of VRAM, or a Mac with 32 GB or more of unified memory.**

If you only have about 16 GB, use **gpt-oss-20b** instead. If you have 64–96 GB or more, **gpt-oss-120b** or **GLM-4.5-Air** will get closest to Haiku 4.5.

Neither the Ask O11y listing nor its GitHub README recommends any local model. They only say to configure a provider in the Grafana LLM plugin. The picks above are my own judgment. Open models change quickly, so check whether a newer version of one of these families is out before you download.

## Why Qwen 2.5 probably struggled

I'm assuming you meant Qwen2.5-14B, since Qwen 2.5 has no 13B size. Two problems likely added up:

1. **Context truncation (most likely cause).** Ask O11y sends 56+ tool definitions plus a system prompt and query results. That can easily be 10–20k tokens before your question. Ollama's default context is small (4k in many versions) and it cuts off the excess without any error. The model never sees the tools, so it fails or makes things up. Whatever model you pick, set the context length explicitly.
2. **Weak tool calling.** Qwen2.5-14B is an older model with mediocre multi-step tool use. Ask O11y is an agent: it chains queries, reads the results and calls more tools. The Qwen3-2507 and gpt-oss models are much better at this.

## Model and VRAM sizing

These are estimates: Q4 weights plus KV cache, plus about 1–2 GB of overhead.

| Tier | Model | Weights | KV cache @ 32k | Total @ 32k | Fits on |
|---|---|---|---|---|---|
| Budget | gpt-oss-20b (MXFP4) | ~13 GB | ~1 GB | **~15–16 GB** | 16 GB GPU, or Mac with 24 GB+ |
| **Recommended** | **Qwen3-30B-A3B-Instruct-2507 Q4_K_M** | ~18.6 GB | ~3 GB (~6 GB @ 64k) | **~22–23 GB** | 24 GB GPU (3090/4090), or Mac with 32 GB+ |
| Better | gpt-oss-120b (MXFP4) | ~63 GB | ~2–3 GB | **~68 GB** | 80 GB GPU, or Mac with 96 GB+ |
| Better | GLM-4.5-Air Q4 | ~65–70 GB | ~5+ GB | **~75 GB** | 2×48 GB GPUs, or Mac with 128 GB |

How to estimate other models:
- **Weights:** at Q4_K_M, roughly 0.6 GB per billion parameters.
- **KV cache:** about 2 × layers × KV heads × head size × 2 bytes per token. For Qwen3-30B-A3B that's about 96 KB per token, so 32k tokens comes to about 3 GB. Setting the KV cache to q8 roughly halves that.
- **Dense 32B models are a poor fit for 24 GB.** Qwen3-32B, for example, needs about 20 GB for weights plus about 8 GB of KV cache at 32k, which doesn't fit. The 30B-A3B model is a mixture-of-experts model, so its cache is smaller and it runs 3–5× faster. Speed matters for an agent that makes many calls in a row.
- **On a Mac:** by default macOS lets the GPU use only about 65–75% of RAM. A 32 GB Mac gives about 21–24 GB, which is just enough for the recommended tier. Keep the context at 32k.

## Install and first run (Ollama)

I haven't run any of this on your machine. These steps are for you to run.

**1. Install Ollama and download the model**
```bash
brew install ollama          # or install the app from ollama.com
ollama pull qwen3:30b-a3b-instruct-2507-q4_K_M
# 16 GB option instead:  ollama pull gpt-oss:20b
```
Tag names change, so if a pull fails, check the tag on ollama.com/library/qwen3.

**2. Start the server with a large context (this is the key step)**
```bash
OLLAMA_CONTEXT_LENGTH=32768 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve
```
If memory allows, use 65536 instead of 32768.

**3. Check that tool calling works before involving Grafana**
```bash
curl http://localhost:11434/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "qwen3:30b-a3b-instruct-2507-q4_K_M",
  "messages": [{"role":"user","content":"What is the CPU usage of host web-1?"}],
  "tools": [{"type":"function","function":{"name":"query_prometheus",
    "parameters":{"type":"object","properties":{"expr":{"type":"string"}},"required":["expr"]}}}]
}'
```
The response should contain a `tool_calls` entry with a PromQL expression. Then run `ollama ps`. The model should show **100% GPU**. If part of it shows as CPU, it's spilling out of VRAM and will be slow.

**4. Point the Grafana LLM plugin at Ollama**

Go to Administration → Plugins → LLM → Configuration. Exact labels differ between versions.
- Provider: **OpenAI-compatible / Custom**
- API URL: `http://localhost:11434`. If Grafana runs in Docker, use `http://host.docker.internal:11434`. Depending on the plugin version, you may need to add `/v1` to the end.
- API key: any placeholder, such as `ollama`
- Map **both** the base and the large model to `qwen3:30b-a3b-instruct-2507-q4_K_M`. Ask O11y skills can request either class.
- Save, then use the plugin's health or test check.

**5. Tune Ask O11y**
- Set the **LLM token budget** below your context length, around 24k for a 32k context.
- Lower **max parallel tool calls** to 1–2. Local models handle sequential calls more reliably, and a single GPU handles them faster.
- If your MCP setup lets you turn off tool groups you don't need, do it. Fewer tools means a smaller prompt and better tool choices.
- Start with a simple question, such as "Which services have the highest error rate in the last hour?", before trying full root-cause investigations.

## What to expect

Even the recommended model will be noticeably weaker than Haiku 4.5. Expect more wrong PromQL or LogQL, and long investigations that stop early. The 120B-class models narrow that gap a lot. If results are still poor after fixing the context length, switch to llama.cpp's `llama-server --jinja -c 32768` or to vLLM. Both often handle tool calls more strictly than Ollama.

Sources:
- [Ask O11y on the Grafana plugin catalog](https://grafana.com/grafana/plugins/consensys-asko11y-app/)
- [Ask O11y on GitHub (Consensys/ask-o11y-plugin)](https://github.com/Consensys/ask-o11y-plugin)
- [Grafana LLM plugin updates: choosing models and providers](https://grafana.com/blog/2024/12/18/grafana-llm-plugin-updates-choose-the-large-language-models-and-providers-that-work-best-for-you/)
- [Grafana LLM plugin setup docs](https://grafana.com/docs/grafana-cloud/ai-tools/llm-plugin/llm-setup.md)