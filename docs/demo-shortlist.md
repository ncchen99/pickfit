# Demo 情境候選（P5.6）

2026-11-02 · 給念誠挑 demo 主案與備案。只從現有、已經能用的紀錄挑；沒有改任何紀錄、配對程式或提示詞。

## 先講結論

- **建議主案：`mcp-audit`**（「我裝了一堆 MCP server，有沒有哪個有風險？」）。6 次呼叫都排第 1，回 3 個選項可以比較；服務等級；看的人多半自己就在用 MCP。
- **備案：`tcount`**（token 計數，4 項功能都驗過）、**`pando`**（給平行 coding agent 用的 git worktree）。
- **有影片的兩個 GUI app（`neon-vision-editor`、`breaktimer-app`）現在不能用來 demo**：線上 Worker 的 `find_software` 只要結果裡有功能等級的 GUI app 就會整個報錯（見下方「線上 bug」）。這個 bug 修好並部署之後，它們才能重新列入考慮。

## 篩選

從 `data/software/` 的 863 份紀錄篩出：`status: listed`；有 macOS arm64、等級 function 以上的 run（59 份）；再依下列條件刪減：

- 免費：`pricing` 是 `free`，或沒寫價格但有 OSI 授權。刪掉 `itsypad-macos`（freemium）、`stackengine`（freemium、沒有授權）、`cli`（沒有授權）。
- 安裝後能離線：功能檢查是在斷網時通過。刪掉 `halpradio`（網路電台，`network: required`）、`patient-zero`（每次都用 `npx -y …@latest`，smoke test 都不是離線）。
- 安全的安裝方式：brew／cask、pipx／uv、npm。刪掉 `script`、`binary`、`source`、`go`、`pip`、`other`（例如 `xyntetik-runner`、`shep`、`cluaiz`、`mi-lsp`）。
- 專案健康：授權清楚、最近有 release。
- 需求要大家都懂：刪掉很專門的（Allure TestOps、Darkube、Ark genomic enclaves、Tiingo、EPUB 編輯器 `sigil`），以及需要另外裝 Ollama 或模型、或要雲端 API key 的 coding agent。

剩下 8 個，每個寫 2 句使用者會打的需求，送進線上 Worker 試。

## 線上檢查

方法：直接用 HTTP 呼叫 `https://pickfit-mcp.ncchen99.workers.dev/mcp` 的 `tools/call find_software`。參數只有 `need`，加上 `os: macos`、`arch: arm64`（使用者在 Mac 上的 agent 會帶）；需求寫到「免費」的那一句加 `budget: free_only`。每句先跑 1 次篩選，排第 1 的再補 2 次。每次都是 `matched_by: muse-spark-1.3`、`degraded: false`、沒有追問。2026-11-02 約 17:15–17:28（台北），共 33 次呼叫。

「排名」＝目標工具在 picks 裡的位置；「—」＝沒出現；「錯誤」＝工具回傳錯誤（見下節）。

| 工具 | 需求（使用者會打的話） | 3 次的排名 | 同時回傳的其他選項 |
|---|---|---|---|
| `mcp-audit` | I've added a bunch of MCP servers to Claude and Cursor. Is there a way to check whether any of them are risky? | 1, 1, 1 | `patient-zero`、`penthera` |
| `mcp-audit` | scan my MCP config for security problems before I commit it | 1, 1, 1 | `patient-zero`、`penthera` |
| `tcount` | check how many tokens a prompt file is and whether it fits in the model's context window | 1, 1, 1 | 無（只回 1 個） |
| `tcount` | count the tokens in every file in my repo before I paste it into an LLM | 1, 1, 1 | 無 |
| `pando` | I run several coding agents on different branches at once. Something to manage git worktrees with a dev server for each | 1, 1, 1 | `orbit`、`vincent` |
| `pando` | keep a separate checkout per branch and run each one's app on its own port | 1, 1, 1 | 無 |
| `shine` | preview my README nicely right in the terminal and catch markdown mistakes before I publish | 1, 1, 1 | 無 |
| `shine` | read markdown docs in the terminal without opening a browser | 1, 1, 1 | 無 |
| `neon-vision-editor` | I want a free app for writing Markdown notes with a live preview | —（1 次） | 只回 `writer-computer`（install 等級） |
| `neon-vision-editor` | a lightweight native text editor for my Mac to open and tweak scripts and config files（`free_only`） | 錯誤、—（2 次） | 成功的那次只回 `writer-computer` |
| `breaktimer-app` | I sit at my laptop for hours. I want something that nags me to stand up and take a break every so often | 錯誤、錯誤 | — |
| `breaktimer-app` | an app that reminds me to rest my eyes every 20 minutes, but only during my work hours | 錯誤、錯誤 | — |
| `jitllm` | run a small language model locally on my MacBook, offline | —（1 次） | `llama-macos`、`camelid`、`bitrun` |
| `jitllm` | chat with an LLM on my own laptop without sending anything to the cloud | —（1 次） | `camelid`、`m1k3`、`hilbertraum` |

`neon-vision-editor`、`jitllm` 篩選時就沒排上，沒有補跑。

## 線上 bug：功能等級的 GUI app 讓 `find_software` 報錯

Worker 回的是 `isError: true`，內容是：

> Output validation error: Invalid structured content for tool find_software: picks.0.verification.gui.tier: Invalid option: expected one of "window"|"ui_rendered"

原因：`worker/src/server.ts:93` 的輸出 schema 寫 `.enum(['window', 'ui_rendered'])`，但 `worker/src/catalog.ts:37` 與資料裡已經有 `action_checked`（GUI 功能驗證過，也就是所有功能等級的 GUI app）。`main`、`origin/main`、本機所有分支都還是這樣。影響不只 demo：任何使用者的需求只要配到功能等級的 GUI app（`breaktimer-app`、`neon-vision-editor`、`sigil` 等），整個回答都會失敗，而且 Muse 的配對已經跑完、花了錢。我沒有改（這個 session 不改程式），交給協調的 session 決定。修好之後算是修 bug，不是為了 demo 調整，GUI app 才能重新當候選（`breaktimer-app` 的兩句要重跑才知道排名）。

註：一開始有 3 次錯誤因為我的腳本解析失敗，沒存下原始回應（`neon` 第 2 句 1 次、`breaktimer` 兩句各 1 次）；之後每次都存下了，內容都是上面那段。

## 候選情境

| # | 需求（建議用的那句） | 3 次排名 | 為什麼大家都懂 | 影片 | 風險 |
|---|---|---|---|---|---|
| 1（主案） | I've added a bunch of MCP servers to Claude and Cursor. Is there a way to check whether any of them are risky? | 1, 1, 1（另一句也是 1, 1, 1） | 會看這支影片的人（評審、MCP 使用者）多半自己就裝了好幾個 MCP server；「裝的東西安不安全」大家都會擔心。而且很自然帶出 pickfit 自己就是 MCP server。 | 沒有；CLI 的 run 沒有影片錄製器（只錄 GUI 操作）。念誠在 Mac 上跑一次 `mcp-audit scan` 錄螢幕即可。 | 安裝要 `uv`（`uv tool install mcp-audit-scanner`），Mac 上沒裝 uv 要先裝。在念誠的 Mac 上掃會印出真的 MCP 設定路徑，可能有 token 或 key，錄影前要檢查、必要時打馬賽克。macOS 驗到「掃描」與「攻擊圖 dashboard」；「鎖定核准的 server」、「跨 server 的危險組合」沒驗到，旁白不要講。第 2 名 `patient-zero` 每次都用 `npx …@latest`，不是離線。 |
| 2 | check how many tokens a prompt file is and whether it fits in the model's context window | 1, 1, 1（另一句也是 1, 1, 1） | 有在用 LLM 的人都遇過「這段塞不塞得進 context」。 | 沒有（CLI）；終端機輸出畫面很清楚，好錄。 | 只回 1 個選項，沒有比較的畫面。Claude、Gemini 的數字是估算（工具自己標 Approx），旁白不要說「精確」。最新 release v0.7.0 是 9/12，約 7 週前。brew 要從作者的 tap 裝（`lancekrogers/tap/tcount`）。 |
| 3 | I run several coding agents on different branches at once. Something to manage git worktrees with a dev server for each | 1, 1, 1（另一句也是 1, 1, 1） | 平行跑 coding agent 是現在很多開發者在做的事，和 demo 的觀眾很貼近。回 3 個選項（`orbit`、`vincent`）。 | 沒有（TUI）。 | **需求說的「每個 worktree 一個 dev server」在 macOS 沒驗過**（agent 的 box 通過，全新 box 重播沒過）；驗過的只有建立、刪除 worktree。要用這個就換成另一句（keep a separate checkout per branch …），旁白只講 worktree。AGPL-3.0。public URL、服務副本要 cloudflared、Docker。 |
| 4 | preview my README nicely right in the terminal and catch markdown mistakes before I publish | 1, 1, 1（另一句也是 1, 1, 1） | 寫 README、發布前檢查 markdown，大部分開發者都做過。treasure 分數 65.9，這幾個裡最高。 | 沒有（TUI）。 | 最新 release v0.1.2 是 7/10，4 個月前，「最近有 release」偏弱；版本號 0.1.x。只回 1 個選項。npm 要裝指定版本 `@nk02/shine@0.1.2`。行內圖片沒驗到。 |
| （修好 bug 才能用） | I sit at my laptop for hours. I want something that nags me to stand up and take a break every so often | 錯誤 ×4 | 最大眾的需求，非開發者也懂；而且有 Muse Spark Open 剪的驗證影片（passed-only 版，49 秒，3 項功能）。 | 有（passed-only） | 現在線上會報錯，要先修 Worker 的 schema 並部署。最新 release v2.0.3 是 2025-11-13，快一年。「只在上班時間提醒」那項沒驗過，影片也拿掉了，所以不要用第 2 句。修好之後排名要重測。 |

`neon-vision-editor`（有影片）在兩句 markdown／文字編輯器需求裡都沒排上，被 install 等級的 `writer-computer` 搶走（其中一次是報錯），不建議當 demo。

## 供給端那一幕：要提交的 3 個 repo

條件：第三方（不是念誠的作品）、在 pickfit 的類別裡、從來沒送進 pickfit。查了三個地方，三個 repo 都不在：

- `data/software/`：主 checkout 與所有 worktree 的紀錄，`repo.full_name` 都比對過。
- 本機 pipeline 資料庫：主 checkout 與所有 worktree 的 `runs/*.db`，加上 `~/.pickfit/eval-snapshot-20261102/` 裡的快照，`candidates.full_name` 與 `aliases` 合起來 7,935 個 repo，都比對過。
- 線上 D1 的 `submissions`（`wrangler d1 execute pickfit --remote`，只讀查詢）：目前只有 2 筆，沒有這三個。

| repo | 類別 | 是什麼 | Mac 安裝 | 授權、活躍度 | 為什麼適合錄影 |
|---|---|---|---|---|---|
| [heydeer/pngdeer](https://github.com/heydeer/pngdeer) | dev_cli | 壓縮 PNG（輸出 PNG 或 WebP），自動挑品質；CLI 與瀏覽器（WebAssembly）同一份 Rust 程式 | `brew install heydeer/tap/pngdeer` | MIT；10/25 建立，11/2 還有 push；422 star；**還沒有 GitHub release** | 「壓圖」大家都懂（TinyPNG 的離線替代），結果是看得到的檔案大小變化。 |
| [scarletkc/seiso](https://github.com/scarletkc/seiso) | dev_cli | 給 AI 寫、人和 agent 讀的專案文件用的 Markdown 規範與 linter | `uv tool install seiso`、`pipx install seiso`、`npm install -g @scarletkc/seiso`（有 darwin-arm64 預編譯檔） | MIT；v0.4.0（10/13）；195 star | 三種安全安裝方式都有，驗證成功的機率高；和 demo 的「coding agent」主題接得上。 |
| [Graphicle-AI/graphicle](https://github.com/Graphicle-AI/graphicle) | mcp_server | 給 coding agent 的程式碼圖與記憶，一個 Rust 程式（Claude Code、Codex、Cursor） | `brew install graphicle-ai/tap/graphicle`；release 有 `aarch64-apple-darwin` 檔與 `.mcpb` | Apache-2.0；v0.1.11（11/2）；492 star | 示範 MCP 類別；release 很新。 |

備用：[init-co-jp/diff-tour](https://github.com/init-co-jp/diff-tour)（dev_cli，像資深工程師那樣帶你走過一個 diff 的 TUI；MIT；v0.6.1 10/29 有 darwin_arm64 檔；但官方安裝是 `go install`，README 說 macOS 還沒測過）。

風險：三個都還沒經過 pickfit 驗證，錄影那天實際送出才知道結果（這正是那一幕要呈現的）。`pngdeer` 沒有 release，如果 pickfit 的抽取或計分看重 release，結果可能比較弱；最穩的是 `seiso`。三個都是 10 月才建立的新專案，錄影前要再確認還沒被別人送進來（查 D1 `submissions` 就好），而且 P5 的完成標準測試**不能用掉要錄影的那一個**。
