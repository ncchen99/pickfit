# YouTube 上傳用：標題與說明

影片：`video/out/pickfit-demo.mp4`（2:59，1920×1080，30 fps）。公開或不公開清單皆可，但要「任何有連結的人都能看」（比賽規則）。

## 標題（擇一，建議第一個）

1. **pickfit: software tested before it's recommended, for you and your AI agent**
2. pickfit: the right software, for the person who needs it (Meta hackathon demo)
3. Your agent doesn't need to guess: pickfit tests software first

## 說明（直接貼上）

```
pickfit finds software, installs and tests it in a sandbox first, then tells you (or your AI agent) which one fits your need, with the exact steps that worked. Ranked by fit, not stars. No ads.

Built for the Meta Global AI Developer Hackathon (Oct 27 – Nov 4, 2026). Before the hackathon we had idea and planning notes only; all the code, the catalog, the website and this video were made during the hackathon.

What you see is real:
• pickfit.app, recorded live in a browser
• Claude Code on a Mac using pickfit over MCP to install MangoDisk, then the app's first use
• the same agent finding a CLI (patient-zero) and an MCP server (gutenberg-mcp-server) it didn't have
Waits are sped up and every sped-up part shows its speed on screen. Consent prompts play at real speed. The Mac's interface language is Chinese, so English captions translate those moments.

How Meta models do the work:
• Muse Spark 1.3 reads each README and keeps the quotes, judges what passed, and matches your request live
• Muse Spark Open, Meta's open-weight model, does the first cut and operates desktop apps on a fresh macOS VM to check each feature

As of Nov 5, 2026: 1,050 tools listed (CLI tools, desktop apps, MCP servers, web apps), 732 verified at least through install. The rest are marked "not verified".

Try it
• Web: https://pickfit.app
• MCP (any agent): https://pickfit-mcp.ncchen99.workers.dev/mcp
• Code: https://github.com/ncchen99/pickfit

Chapters
0:00 One evening, one full disk
0:38 Ask pickfit on the web
0:50 Watch pickfit run it first
1:02 Your agent installs it, after asking
1:26 Your agent finds tools too: a CLI and an MCP server
1:50 Following the stitch: how pickfit tests software
2:26 The maker, and what's next
2:44 Ask through your agent, or on the web

Credits: narration in the developer's own voice, generated with ElevenLabs; music and sound effects by ElevenLabs; 3D scenes made with three.js and GSAP; Fitz the tailorbird is original artwork made for pickfit.

#AIagents #MCP #MetaAI #hackathon
```

## 上傳前確認

- 影片長度 ≤ 3:00（目前 2:59）。
- 第一句旁白是賽前揭露。
- 說明裡的數字（1,050／732）與錄影當天的目錄一致；若重新發布資料後數字變了，標題卡與說明一起改。
- repo 轉 public 之後，Code 連結才打得開。
