I recommend **Open WebUI** connected to your Ollama setup. It's the closest open-source match to the Claude website: chat history, folders, file and image uploads, model switching, and math formulas display properly. It works in a browser on your Mac or phone. If you'd rather not run anything yourself, **TypingMind** (paid, hosted) is the best alternative.

**My assumption:** GLM-5.1 (~750B parameters) and Kimi-K2.6 (~1T) are too big for most personal machines, so you're probably using the `:cloud` versions (`glm-5.1:cloud`, `kimi-k2.6:cloud`) through an Ollama account. That matters because any chat app can then reach your models without your Mac being on.

## Main pick: Open WebUI

**Why it fits you**
- It's the most widely used and actively developed open-source chat app for Ollama. It connects to Ollama directly and also to any OpenAI-compatible service.
- It displays math formulas properly, which helps with homework. You can paste a photo of a problem if the model accepts images.
- It runs as a website, so on your phone you can open it and use "Add to Home Screen" to get an app-like icon. I found no reliable native phone app for Open WebUI, LibreChat or Msty.

**Install (Mac, easiest with Docker Desktop)**
```bash
# 1. Install Docker Desktop from docker.com and start it
# 2. Run Open WebUI, pointing it at Ollama on your Mac
docker run -d -p 3000:8080 \
  --add-host=host.docker.internal:host-gateway \
  -v open-webui:/app/backend/data \
  --name open-webui --restart always \
  ghcr.io/open-webui/open-webui:main
```
Without Docker: `pip install open-webui` (needs Python 3.11), then `open-webui serve`, and the address is `http://localhost:8080`.

**First run**
1. Make sure Ollama is running and signed in (`ollama signin`), and pull the cloud models: `ollama pull glm-5.1:cloud`, `ollama pull kimi-k2.6:cloud`.
2. Open `http://localhost:3000`. The first account you create becomes the admin account.
3. Your Ollama models should appear in the model picker automatically. If not, go to **Admin Settings → Connections** and set the Ollama address to `http://host.docker.internal:11434`.
4. Optional: set GLM-5.1 as your default model and add a short system prompt, e.g. "Explain math step by step; use LaTeX."

**Using it on your phone and away from home**
- **Free option:** install [Tailscale](https://tailscale.com) on your Mac and phone, then open `http://<your-mac's-tailscale-name>:3000` on the phone and add it to your home screen. Your Mac has to be on.
- **Paid, always-on option:** rent a small server for about $5–10/month (for example Hetzner or DigitalOcean) and run the same Docker command there. Instead of local Ollama, connect it to Ollama Cloud with your API key under **Admin Settings → Connections**. I believe the OpenAI-compatible address is `https://ollama.com/v1`, but check Ollama's docs. Put Tailscale or a login in front of it, since it's reachable from the internet.

## If you'd rather pay than run anything yourself

- **TypingMind:** a polished hosted chat app that works on phones. You bring your own Ollama Cloud API key, and they have a [specific guide for Kimi-K2.6](https://www.typingmind.com/guide/ollama-cloud/kimi-k2.6). This is the closest to "pay a fee and it just works."
- **Ollama's own desktop app:** the simplest option and already installed. It's fine for quick questions on your Mac but has fewer features and no phone app.
- **Msty:** a nice desktop app (about $79/year for the paid tier), also with no phone app.
- **LibreChat:** good, but it's a heavier setup (four separate services). Only worth it if you need things Open WebUI lacks.

## Things to know
- **Billing:** sources conflict on how Ollama Cloud charges. Some describe Free/Pro/Max subscription tiers, while TypingMind's page lists per-token API prices. Check ollama.com/pricing before committing.
- **Newer models:** `glm-5.2:cloud` and `kimi-k2.7-code:cloud` have appeared since the versions you're using. One June report said Kimi K2.6 sometimes produces garbled text while it's reasoning, and GLM-5.1 had no such reports. Open WebUI makes it easy to try both side by side.

Sources:
- [awesome-ollama-models (cloud model list)](https://github.com/RedBeret/awesome-ollama-models)
- [Ollama Cloud vs API vs subscriptions](https://yage.ai/share/ollama-cloud-vs-api-vs-subscriptions-en-20260428.html)
- [TypingMind + Ollama Cloud Kimi-K2.6 guide](https://www.typingmind.com/guide/ollama-cloud/kimi-k2.6)
- [Open WebUI alternatives docs](https://docs.openwebui.com/alternatives.md)
- [Open WebUI vs LibreChat (docs)](https://docs.openwebui.com/alternatives/librechat.txt)
- [AnythingLLM vs Open WebUI vs LibreChat 2026 (DEV)](https://dev.to/jovan_chan_9500711396d4e6/anythingllm-vs-open-webui-vs-librechat-in-2026-which-self-hosted-ai-interface-should-you-use-24cl)
- [LM Studio vs Msty vs LibreChat vs Open WebUI (2026)](https://recapio.com/digest/lm-studio-vs-msty-vs-librechat-vs-openweb-ui-vs-anythingllm-local-ai-apps-exposed-2026-by-savage-rev)
- [Reddit r/ollama snapshot](https://reddit.sentinel-team.org/posts/1u7u1ry/snapshots/2026-06-18T01%3A49%3A50.745015Z)