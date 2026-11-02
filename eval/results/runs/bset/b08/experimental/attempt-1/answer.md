I recommend **Open WebUI**, connected to the Ollama you already have. It's the closest open-source match to the Claude website and app, and it's what most people end up using for Ollama. You get Claude-style chat, saved conversation history, LaTeX math rendering for homework, file and image uploads, and a model picker that shows every Ollama model you have, including `:cloud` ones. You can also open it on your phone and add it to your home screen, so it works much like an app.

**My assumptions:** you're on a Mac (that's what this machine is). Because GLM-5.1 and Kimi-K2.6 are far too big to run on most Macs, I'm assuming you use them through Ollama's cloud tags (for example `kimi-k2.6:cloud`).

I haven't installed or tested Open WebUI here. Pickfit (the tool-recommendation service I checked) also hasn't verified it. The commands below are the standard ones from its documentation.

## Install and first run (Mac)

**Option A: Docker** (the most common setup)
1. Install Docker Desktop or OrbStack, and make sure Ollama is running.
2. Run:
   ```bash
   docker run -d -p 3000:8080 \
     --add-host=host.docker.internal:host-gateway \
     -v open-webui:/app/backend/data \
     --name open-webui --restart always \
     ghcr.io/open-webui/open-webui:main
   ```
3. Open http://localhost:3000. The first account you create becomes the admin.
4. Pick `glm-5.1:cloud` or `kimi-k2.6:cloud` from the model menu at the top and start chatting. If the list is empty, go to **Admin Settings → Connections** and set the Ollama URL to `http://host.docker.internal:11434`.

**Option B: no Docker**
```bash
brew install uv
DATA_DIR=~/.open-webui uvx --python 3.11 open-webui@latest serve
```
Then open http://localhost:8080.

**For math homework:** ask something like "Solve ∫x·eˣ dx and show the steps." The answer should display as formatted equations. If you see raw `$...$` symbols instead, look for the LaTeX rendering toggle in Settings → Interface.

**To use it on your phone:** install Tailscale (free for personal use) on both your Mac and your phone. Then open `http://<your-mac's-tailscale-name>:3000` in the phone's browser and choose "Add to Home Screen." The catch is that your Mac has to be on and awake for this to work.

## Where paying makes sense

- **Ollama's cloud plan.** If you hit the free usage limits on the cloud models, Ollama sells paid tiers. That's probably the most worthwhile subscription for you, since Open WebUI itself is free.
- **Always-on hosting.** If you don't want to depend on your Mac being awake, run Open WebUI on a cheap server (about $5–10/month) or use a managed host that offers Open WebUI as a one-click app. Then point it at Ollama's cloud API with an API key instead of your local Ollama. Check Ollama's current docs for the exact API address and how it handles keys before you set this up.

## Other options

- **The models' own chat apps.** Kimi (kimi.com) and Z.ai (chat.z.ai, the makers of GLM) have free, polished web and mobile chat apps for exactly these models. You don't have to host anything. The downside is that your conversations go to those companies, so check their privacy terms first.
- **OpenRouter's chat page** lets you pay per message for many open models, including GLM and Kimi, through a hosted web chat.
- **LobeChat** is a nicer-looking alternative to Open WebUI, and it's good if you also want to use Claude or OpenAI models from the same interface.
- **Msty or Jan** are good if you only want a native Mac app and don't need phone access.
- **OvertChat** came up through pickfit. It's a self-hosted alternative to Open WebUI with mobile apps and voice chat. Pickfit only tested that it installs on Linux; it never confirmed that chatting actually works, and it hasn't tested it on Mac. I'd treat it as something to try later, not your main setup.

Sources:
- [Open WebUI + Ollama guide (inkeybit)](https://inkeybit.pages.dev/blog/open-webui-ollama-guide)
- [Best Ollama clients 2026 (askimo)](https://askimo-site2.pages.dev/blog/best-ollama-clients-2026/)
- [GUI options for Ollama in 2026 (askimo)](https://askimo-site.pages.dev/app/ollama/best-gui-for-ollama/)
- [Best Ollama clients (localaimaster)](https://localaimaster.com/blog/best-ollama-clients)
- [Top 5 local LLM tools and models (pinggy)](https://pinggy.io/blog/top_5_local_llm_tools_and_models/)
- [OvertChat repo](https://github.com/yoloyash/overtchat)