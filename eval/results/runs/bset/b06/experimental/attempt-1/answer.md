I've checked the plugin's docs and current local-model options. Here's my recommendation.

## Recommendation: Qwen3.6‑35B‑A3B (`qwen3.6:35b`, about 4‑bit) on Ollama, with the context window raised to at least 32K

**Plan for about 28–32 GB of VRAM.** A 32 GB GPU or a Mac with 36 GB or more of unified memory runs it fully on the GPU.

**If you only have 24 GB:** use `qwen3.6:27b`, the dense model (about 18–19 GB of weights). Or run the 35B and let Ollama push a few layers onto the CPU. Only about 3B parameters are active per token, so it stays usable.

**If you only have 16 GB:** use `gpt-oss:20b` (about 14 GB). Expect noticeably weaker multi‑step investigations than with Haiku 4.5.

**If you have 80 GB or more:** `gpt-oss:120b` or a larger Qwen3.6 tier gets closest to Haiku‑level reliability.

### Why this model, and why Qwen 2.5 probably failed
- **No official guidance:** Ask O11y's README and troubleshooting docs don't recommend any model. They only say the Grafana LLM plugin needs a configured provider. This pick is my judgement, not something the plugin authors have tested.
- **The plugin depends on tool calling:** it sends 56+ Grafana tool definitions and runs multi‑step tool loops. Small or older models break on exactly that. Qwen3.6 lists tool calling as a supported capability, has a 256K context window, and is recent enough to be much better at agent work than Qwen 2.5.
- **The likely main cause of your trouble was context size, not just the model.** Ollama's default context is only a few thousand tokens. The system prompt plus 56 tool schemas plus query results easily go past that, and Ollama cuts off the excess silently. The model then "forgets" tools or produces broken calls. The Grafana LLM plugin talks to Ollama through its OpenAI‑compatible API, which can't set the context size per request, so you have to set it on the server.
- **Assumption:** I took "Qwen 2.5 13B" to mean Qwen2.5‑14B, since there's no 13B version.

### VRAM estimate (Q4_K_M quantization)
| Model | Weights | KV cache + overhead at 32K context | Total to plan for |
|---|---|---|---|
| qwen3.6:35b (MoE, 3B active) | ~23 GB | ~3–6 GB | **~28–32 GB** |
| qwen3.6:27b (dense) | ~18–19 GB | ~3–5 GB | ~22–24 GB (tight on a 24 GB card) |
| gpt-oss:20b | ~14 GB | ~2–3 GB | ~16–18 GB |
| gpt-oss:120b | ~65 GB | ~4–6 GB | ~70–80 GB |

Weight sizes are from Ollama's listings. The KV‑cache numbers are rough, so check them on your own hardware after loading (see step 3). A 64K context adds a few more GB.

## Install and first run (for you to run; I haven't run anything)

1. **Install Ollama:** on macOS, `brew install ollama` or the app from ollama.com. On Linux, the install script from ollama.com (read it before you pipe it to a shell).
2. **Start the server with a larger context and pull the model:**
   ```bash
   OLLAMA_CONTEXT_LENGTH=32768 OLLAMA_HOST=0.0.0.0:11434 ollama serve
   # in another terminal:
   ollama pull qwen3.6:35b
   ```
   If you use the Mac app instead, run `launchctl setenv OLLAMA_CONTEXT_LENGTH 32768` and restart the app.
3. **Check it works:** `ollama run qwen3.6:35b "hello"`, then `ollama ps`. The PROCESSOR column should read `100% GPU`. If it shows a CPU/GPU split, drop to the 27b model or a smaller context.
4. **Point the Grafana LLM plugin at Ollama:** go to Administration → Plugins → Grafana LLM → Configuration.
   - Provider: OpenAI‑compatible / custom.
   - URL: `http://<ollama-host>:11434`. If Grafana runs in Docker on the same Mac, use `http://host.docker.internal:11434`. If you get 404 errors, try the URL with `/v1` added, or without it if you had added it.
   - API key: any placeholder value.
   - Model mappings: set both **Base** and **Large** to `qwen3.6:35b`.
   - Save, then use the plugin's health check.
5. **First test in Ask O11y:** ask something that needs a tool call, such as "List my data sources, then show the 5 busiest Prometheus jobs over the last hour." If the answer clearly calls tools and returns real data, the setup works. If it invents data or stops after one step, raise the context to 65536 before you change models.

**Two more tips:** Qwen3.6 "thinks" before answering, which adds delay. For faster replies, put `/no_think` in the system prompt or a skill. Plan to keep Haiku 4.5 set up as a fallback for long investigations. Even the best open model at this size will do worse than Haiku on long tool chains.

Sources:
- [Ask O11y plugin (GitHub)](https://github.com/Consensys/ask-o11y-plugin)
- [Ask O11y troubleshooting](https://github.com/Consensys/ask-o11y-plugin/blob/main/TROUBLESHOOTING.md)
- [Ask O11y on the Grafana plugin catalog](https://grafana.com/grafana/plugins/consensys-asko11y-app/)
- [Grafana LLM plugin: choosing models and providers](https://grafana.com/blog/2024/12/18/grafana-llm-plugin-updates-choose-the-large-language-models-and-providers-that-work-best-for-you/)
- [Grafana: using LLMs and MCP in app plugins](https://grafana.com/developers/plugin-tools/how-to-guides/app-plugins/use-llms-and-mcp)
- [Ollama qwen3.6 library page](https://ollama.com/library/qwen3.6)
- [Best local agent models by GPU tier](https://intelligibberish.com/articles/2026-03-17-best-local-agent-models-2026-tool-use-vram-comparison/)
- [Best local LLM for agents and tool calling](https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/)
- [Best small local models for tool calling](https://www.promptquorum.com/power-local-llm/best-local-models-tool-calling-2026)