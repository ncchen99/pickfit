# 技術調研：pickfit 的架構與技術選型

2026-10-28 · 調研進行中。每完成一節就更新並 push；中途中斷時，以「目前的結論」為準。

需求來源：[docs/brief.md](../brief.md)、[docs/hackathon-rules.md](../hackathon-rules.md)。

---

## 0. 目前的結論

**狀態（2026-10-28 06:30 台北）**：A（部分）、C、D、F 已有查證過的結論；B、E 查核中；G（整體架構）評審中。

| 問題 | 目前的結論 | 狀態 |
|---|---|---|
| A. 管道 | 黑客松接 5 條：**GitHub search API**、**Homebrew 第三方 tap analytics**（有真實安裝數、星數中位數 1）、**Show HN**（官方 API）、**PyPI**（`console_scripts`）、**提交入口**（只收 GitHub 連結）。補資料用 ecosyste.ms、deps.dev。Threads／Facebook **不能主動發現**，只能用 oEmbed 嵌入 | 社群、Meta 已查核；託管、套件查核中 |
| B. 品質 | 規則訊號（release、CI、文件、維護）＋沙盒驗證結果；知名度另外算 | 查核中 |
| C. 沙盒 | **Modal Sandbox** 主力（gVisor、網域 allowlist、可先開網路安裝再斷網執行），E2B 備案；Mac 只在 demo 那幾筆另外驗證。本機 Docker spike 實際驗證了 4 款真實工具，其中 2 款要先修正 README 才裝得起來 | 已查核 |
| D. Meta 模型 | `muse-spark-1.3`（Meta API，OpenAI 相容）做抽取、驗證 agent（Responses API＋tool calling）、截圖判讀、文件評分、配對；**Muse Spark Open @ Baseten** 只做大量初篩（同價，為了 credits 與加碼獎）；Glimmer 不用 | 已查核；**沒有 key，模型呼叫未實測** |
| E. MCP | 無狀態 Streamable HTTP，部署在 Cloudflare Workers | 查核中 |
| F. 儲存與配對 | git 裡每款一份 JSON 當正本，建置成索引打包進 Worker；事件寫 D1；配對是「條件篩選＋BM25 候選卡＋Muse Spark 取捨」，**不用向量搜尋** | 已調研 |

**最大的風險**：台灣帳號能否開 Meta Model API 未確認（第一件事就要註冊）；這個雲端 session 的 GitHub API 只開放本 repo，發現管線要在本機跑。

**調研方式**：每個主題由一個 agent 查官方文件並實測，另一個 agent 反向查核（找錯、標「未驗證」），最後由主控者整合。原始筆記在 [notes/](notes/)。

---

## A. 軟體從哪裡來：管道盤點

完整盤點（6 組、約 50 個管道）與要避開的清單：[channels.md](channels.md)。原始筆記在 [notes/](notes/)。**狀態**：社群、區域、Meta 平台已查核；託管、套件查核中；策展資料集、整合工程調研中。

### A.1 黑客松期間接的 5 條

| # | 管道 | 理由 | 工時 |
|---|---|---|---|
| 1 | GitHub search API（＋ repo、release、README） | 兩個類別的新作品主要在這；可直接篩「今年建立、最近有 push、星數 5–300」 | 6–9 h |
| 2 | Homebrew 第三方 tap（官方 analytics）＋ homebrew-core | 唯一同時有「真實安裝數」和「默默無聞」的訊號：30 天安裝 10–1000 次的新 tap formula 有 437 個，抽樣星數中位數 1；直接對上 Mac demo | 3–4 h |
| 3 | Hacker News Show HN（官方 API） | 作者本人發表、別人能試用；兩類別且連 GitHub 約 75 篇／週；86% ≤3 分 | 2–4 h |
| 4 | PyPI 新專案（`console_scripts` 篩 CLI） | 本地 AI 工具主要在這 | 3–4 h |
| 5 | 提交入口（MCP 工具＋GitHub Issue Form） | 供給端；只收 GitHub 連結，Threads 連結只嵌入 | 2–3 h |

補資料：ecosyste.ms、deps.dev、OpenSSF Scorecard。時間夠再加：V2EX、Qiita、阮一峰周刊（共 3.5–5 h）。

### A.2 Meta 平台（Threads、Facebook）實際開放到什麼程度

- **不能拿來主動發現**：Threads keyword search、IG hashtag、FB 粉專都要 App Review，允許用途也不是建軟體目錄；未審核時 keyword search 只搜得到自己的貼文（[文件](https://developers.facebook.com/documentation/threads/keyword-search)）。
- **oEmbed 免 token，但只能嵌入**：回傳 html 沒有貼文文字，條款禁止抽取與保存。
- **「作者用 Threads 登入、讀貼文交給模型」也不行**：`threads_basic` 的允許用途只限把貼文顯示給作者本人。
- Facebook Groups API 已在 2024-04-22 移除；Meta Content Library 只給研究機構。
- **能做的**：提交表單收 GitHub 連結，Threads 連結用 oEmbed 嵌入原貼文；Threads 分享按鈕；用自家帳號發「今日寶藏」。這讓 brief 第 5 節 demo 第 5 幕要改寫（見 J 節）。

### A.3 重要限制

- 這個雲端 session 的 GitHub API 只開放本 repo，GitHub search 的實際筆數沒量到；發現管線要在念誠本機或 Modal 用自己的 PAT 跑。
- GitHub 公開事件流（GH Archive）2025-10 起每小時 0 筆新 repo 事件（查核中），不能靠它找新 repo。

## B. 怎麼判斷「可用的軟體」與「品質好」

細節、規則表與試算：[notes/quality-scoring.md](notes/quality-scoring.md)（經查核，查證日 2026-10-28）。spike：`spikes/quality_signals.py`。

### B.1 「可用的軟體」vs 函式庫、demo、作業、模板

先用規則做第一層，判不準的交給 Muse Spark：

| 類型 | 規則訊號（例） |
|---|---|
| 工具（正向） | README 有安裝／用法小節與安裝指令（`brew install`、`pipx`、`cargo install`…）；**強訊號**：release 附二進位檔、套件中繼資料有執行入口（npm `bin`、`[project.scripts]`、Cargo `src/main.rs`、Go `cmd/*/main.go`）、被套件庫收錄 |
| 不是軟體 | 名稱或 topics 有 awesome、homework、assignment、tutorial、template、starter、dotfiles；`is_template`；README 大多是連結清單；沒有程式碼檔 |
| 函式庫 | `main`／`exports` 但沒有 `bin`；只有 `src/lib.rs`；README 只示範 `import`／`go get`；描述寫 library、SDK |

判定順序：不是軟體 → 函式庫（要多個訊號且沒有強訊號）→ 工具 → 其他交給模型。

**實測**（227 個 2026 年的 Show HN GitHub repo）：工具 142、交給模型 34、函式庫 1、沒資料 50。目測 40 個「工具」中 32 個正確、4 個錯（benchmark 網站、模型權重等）。**精確率未驗證**（沒有標註集）。規則漏掉的類型（benchmark、模型權重、MCP server、韌體）要靠模型。

Muse Spark 判斷：類型（18 類 enum）、給終端使用者還是給開發者 import、成熟度（alpha、PoC）、處理在本機還是雲端、平台與前置需求、文件完整度；每個判斷附 README 原文。**分數由程式算，不讓模型直接給 0–100**；README 視為不可信輸入。

### B.2 和知名度無關的品質訊號

| 來源 | 對長尾專案的實用度 | 理由 |
|---|---|---|
| OpenSSF Scorecard API | **低** | 只涵蓋每週掃描清單（約 131 萬個 repo）或自己發布的 repo；227 個 Show HN repo 只有 7 個（3.1%）有資料，ollama 也是 404。Maintained 對建立未滿 90 天的 repo 給 0；Code-Review、Contributors 對單人專案不公平 |
| Scorecard CLI `--local` | 中 | 不需要 token，小 repo 1–2 秒；可在沙盒 clone 後順便跑 |
| CHAOSS 指標 | 中（挑著用） | Issue Response Time、Change Request Closure、Release Frequency 可用；Bus Factor 小專案一定是 1，不計分 |
| ecosyste.ms | **高（補資料）** | 一個來源就有 release 下載數、issue 關閉時間、套件下載量、檔案列表；涵蓋率 repos 78%、issues 44%；資料 CC BY-SA 4.0 |
| deps.dev | 中 | 涵蓋 28%；能確認套件 ↔ repo 對應有沒有發布簽章 |
| **pickfit 自己的** | **最高** | 沙盒驗證結果、安裝步驟數、README 和實際操作的差距、模型依 rubric 評的文件完整度、`report_outcome` 成功率 |

**關鍵發現**：用規則算的品質會飽和。5 個 2026 年的小工具「若驗證通過」是 80–100 分，bat 是 90，分不開。CI、測試、changelog 用 AI 很容易做出來。所以品質要靠**沙盒驗證**和**模型 rubric**拉開。

### B.3 計分草案

**quality（0–100）**

| 分項 | 權重 | 怎麼算 |
|---|---|---|
| 沙盒驗證 | 35 | 通過且 ≤3 步 1.0；4–6 步 0.85；>6 步 0.7；要修正 README 才成功再 ×0.8；失敗 0 |
| 安裝與文件 | 20 | Muse Spark 依 8 項 rubric 評 0／1／2 分（做什麼、適合誰、前置需求、各 OS 安裝、第一次執行範例、設定與金鑰、疑難排解與移除、授權與平台） |
| 維護 | 15 | 最近 push、最近 release、一年 ≥2 次 release；**不計 commit 數** |
| 工程衛生 | 10 | CI、測試、OSI 授權、changelog、lockfile |
| 回應 | 10 | 外部使用者 issue 的關閉比例與時間（≥2 筆才算） |
| 使用結果 | 10 | `report_outcome` 成功率（≥3 筆才算） |

- 缺資料的分項從分母拿掉後重新正規化，另外輸出 `confidence`。
- 上限：archived 30；驗證失敗 40；不是工具 50；**還沒驗證 69**（剛好低於寶藏門檻）。

**popularity（0–100）**：7 個訊號各自對數正規化 `100 × log10(1+x) ÷ log10(1+ref)` 後加權：stars 0.35、每月下載 0.15、forks 0.10、dependents 0.10、release 下載 0.10、HN 最高分 0.10、收錄套件庫數 0.10。ref 依類別不同（本地 AI 的星數普遍較高）；建立滿 3 個月加 25% 的成長速度。ref 是**未校準的初始猜測**，收完候選後改用類別內 P95。

**寶藏**：工具＋驗證通過＋未 archived，且 quality ≥ 70、popularity ≤ 45；排序看 `gap = quality − popularity`。推薦時先配對條件，寶藏只在合格候選中加分（「推薦是配對，不是排名」）。

**試算**（spike，假設驗證通過）：datui、convkit、photoc、mere-run、pasteface 的知名度 9–38，都是寶藏候選；bat 品質 90 但知名度 96，不是；gollama（函式庫）、awesome-cli-apps（清單、archived）被正確封頂。

**防灌水**：星數只算進知名度；不計 commit 數；release 只看有沒有；只計外部使用者開的 issue；星數暴增（單週 >50% 且 >200）或 forks／stars 異常就人工抽查。StarScout 研究（[arXiv 2412.13459](https://arxiv.org/abs/2412.13459)）指出假星常用來推 AI/LLM 與工具類 repo，正是我們的兩個類別。

## C. 沙盒驗證

細節與來源：[notes/sandbox-compare.md](notes/sandbox-compare.md)、[notes/sandbox-verify-design.md](notes/sandbox-verify-design.md)（都經查核，查證日 2026-10-28）。

### C.1 方案比較

| 方案 | 隔離 | 費用 | 啟動 | GPU | 網路控制 | 單次上限 | 結論 |
|---|---|---|---|---|---|---|---|
| **Modal Sandbox** | gVisor 或 VM（建立時明確設 `runtime="gvisor"`） | CPU／記憶體按一般價 3 倍；5 分鐘、1 core＋2 GiB 約 $0.016；比賽 $100＋Starter 每月 $30 | 官方只說「sub-second」，未實測 | 有（T4 $0.59/h、L4 $0.80/h） | 預設可出網；`block_network`、CIDR、網域 allowlist（Beta）；執行中改政策（Alpha）→ 可做「先開網路安裝、再斷網執行」 | 24 小時 | **主力** |
| E2B | Firecracker microVM | Hobby 免卡、$100 一次性 | 約 80 ms | 無 | 有 allow/deny，deny 不支援網域 | 1 小時（Hobby） | Linux 備案 |
| Daytona | 容器 | 有 free credits | — | 有 | Tier 1、2 只能連「必要服務」清單，連不到一般專案網域；Tier 3 要儲值 $500 | — | 不選：照 README 下載安裝腳本會被擋 |
| Cloudflare Sandbox／Containers | Firecracker | 要 Workers Paid（$5/月） | 1–3 秒 | 文件沒列 | — | — | 不選：只能從 Worker 用 TS 操作，工時最高 |
| Vercel Sandbox | Firecracker | Hobby 每月 5 CPU-h | — | 無 | — | 45 分鐘 | 不選 |
| GitHub Actions（macOS runner） | 每次全新 VM | public repo 免費 | 數十秒（未量） | 無 | 全開 | 6 小時 | **只跑 demo 那幾筆的 Mac 驗證**（條款限制，見下） |
| 本機 Docker（加限制） | 容器（runc） | 免費 | 0.2–0.5 秒（本環境實測） | 看機器 | 自己控 | 無 | 開發期間的 spike 與除錯 |

**macOS 的問題**：demo 使用者在 Mac，但雲端沙盒都是 Linux。
- GitHub Actions 條款限 hosted runner 只能做「與該 repo 軟體專案相關」的事（[原文](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features)），違規可能停用 repo 或帳號，而交件要用 GitHub repo。所以**大量驗證第三方軟體不走 Actions**，只拿來跑 demo 那 3–5 筆的 Mac 驗證（有風險，見 K 節的決定）。
- 其他按分鐘計的雲端 Mac：CircleCI Free（每月約 150 分鐘 M4 Pro）、Codemagic（每月 500 分鐘 M2），條款**未驗證**。整台出租的 Mac（AWS EC2 Mac 等）依 Apple 授權至少租 24 小時，mac2 至少 $15.6。
- 念誠如果有 Apple silicon Mac，可用 Tart 在本機跑 macOS VM（Apple 授權允許每台 Mac 跑 2 個 VM 做開發與測試；驗證第三方軟體算不算，屬解讀問題）。
- **結論**：主驗證在 Linux 沙盒做；結果標明平台；Mac 的 brew 安裝路徑標「未驗證」，demo 那幾筆另外在 Mac 上驗證並註明方式。

### C.2 驗證 agent 怎麼跑

| 步 | 誰 | 做什麼 |
|---|---|---|
| 1 列出安裝方式 | 程式 | 從套件資料（Homebrew formula、PyPI `console_scripts`、npm `bin`、GitHub release 檔名）列出可行方式並排序：套件管理器 → release 二進位 → 從原始碼建置 |
| 2 選方式、執行 | Muse Spark（tool calling） | 只在候選裡選；讀 README 決定參數、要先裝什麼 |
| 3 修錯 | 規則表 → Muse Spark | 先套 15 類常見錯誤的規則（缺系統函式庫、PATH、Python 版本等）；規則處理不了才交給模型，必要時用 `web_search` 查錯誤 |
| 4 smoke test | Muse Spark 提出、程式執行 | CLI：`--version` 或 `--help` 過一個即可，再跑 README 的第一個範例；本地 AI：起服務、打 `/health`、`/v1/models`，用極小模型跑一次推論 |
| 5 判讀 | 程式＋Muse Spark（看截圖與 log） | 規則（exit code、輸出）和模型判讀都同意才算過 |
| 6 重播 | 程式 | 在全新沙盒照記錄的步驟重跑一次；只把重播成功的步驟寫進檔案，另記下「和 README 不同的地方」（pitfalls） |

**spike 實測**（`spikes/sandbox_docker_install.py`，本環境的 Docker，非 root、2 CPU、2 GiB、pids 256、cap-drop ALL、唯讀根目錄、tmpfs 上限、容器內 timeout）：
- 4 款真實工具都通過，每款總計 2–29 秒（差異主要是前置下載）。
- 2 款要先修正一次：`evnx` 照 README 跑會 exit 2，要先 `evnx sync`；`llama.cpp` 缺 `libgomp1`。這種「照 README 做會卡住」的修正，正是 `get_install_guide` 最有價值的內容。
- `llama.cpp` 搭配 1.2 MB 的 `stories260K.gguf`，只用 CPU 就打得通 `/health`、`/v1/models`、`/v1/completions`：本地 LLM 工具可以做到「推論驗證」。
- 防護自我檢查有效：記憶體炸彈被 OOM 殺、塞磁碟停在上限、fork bomb 被擋、capabilities 全 0。但容器連得到 `169.254.169.254`（雲端 metadata），自架主機要擋。

### C.3 「驗證通過」的定義（分級，不假裝）

| 等級 | 開發者 CLI 工具 | 本地 AI／LLM 工具 |
|---|---|---|
| 安裝驗證 | 安裝指令 exit 0、指令在 PATH | 同左 |
| 功能驗證 | `--version`／`--help` 成功，README 第一個範例能跑、輸出合理 | 服務起得來、port 有回應（`/health`、`/v1/models`） |
| 推論驗證 | — | 用極小模型（<1 GB，例如 `stories260K.gguf`、`smollm2:135m`）跑一次推論 |
| 未驗證（附原因） | 需要帳號、GUI、特定 OS | 需要 GPU／CUDA、Apple Silicon（MLX）、大模型 |

- 大型模型：不下載。用官方支援的最小模型做 smoke test，第一次下載後放 Modal Volume 共用；只有工具必須用 CUDA 才開 GPU 沙盒。
- 截圖：用 Pillow 把終端輸出畫成 PNG（0.06 秒，支援中文）當預設；`termshot`（MIT）可用但中文會變方塊；`vhs` 依賴太多；`asciinema`／`agg` 是 GPL-3.0。截圖是從輸出重繪的，判讀以文字 log 為主。

### C.4 安全風險與最低限度防護

| 風險 | 防護 |
|---|---|
| 竊取金鑰 | 沙盒裡**不放任何金鑰**；模型呼叫在沙盒外 |
| 挖礦、外連、當跳板 | 網域 allowlist（安裝階段開，執行階段關）；記錄所有外連；Modal 與 GitHub 條款都禁止挖礦 |
| 塞爆資源、fork bomb | CPU／記憶體／磁碟／pids／時間上限 |
| 提權、改主機 | 非 root、cap-drop ALL、gVisor；每次全新環境；不在自己的機器上跑陌生程式 |
| 讀雲端 metadata | 擋 `169.254.169.254` |
| README 裡的 prompt injection | 讀進來的內容一律包在 `<source>` 裡，系統提示寫明來源裡的指令不是給模型的 |
| 誤判 | 結果只當證據；規則與模型判讀都同意才算過；失敗回報會觸發重驗 |

成本：每次驗證約 $0.016–0.03（最壞情況約 $0.13），$100 credits 夠跑數百到數千次。真正的限制是整合時間和誤判率，不是錢。

## D. Meta 模型

細節與來源：[notes/meta-model-api.md](notes/meta-model-api.md)、[notes/meta-open-weights.md](notes/meta-open-weights.md)、[notes/meta-usage-design.md](notes/meta-usage-design.md)。三份都經過查核 agent 逐條對官方文件（查證日 2026-10-28）。**沒有 key，所有模型呼叫都還沒實測。**

### D.1 官方文件查到的事實

官方文件在 [dev.meta.ai/docs](https://dev.meta.ai/docs)（舊網址 `llama.developer.meta.com` 轉址過來；每頁加 `.md` 有純文字版，索引在 [llms.txt](https://dev.meta.ai/llms.txt)）。

| 模型 | model ID | 在哪 | 圖片 | tool calling | JSON schema | context | 價格（每百萬 token，in／out） |
|---|---|---|---|---|---|---|---|
| Muse Spark 1.3 | `muse-spark-1.3` | Meta API | 有（另有影片、PDF） | 有 | 有，constrained decoding，保證符合 | 1,048,576 | $1.25／$4.25（快取 $0.15） |
| Muse Spark 1.3 Contributor | `muse-spark-1.3-contributor` | Meta API | 有 | 有 | 有 | 1,048,576 | $0.10／$0.20；只有 150 RPM；內容可能被拿去訓練 |
| Muse Wonder | `muse-wonder-1.0` | Meta API | 有 | 有 | 有 | 1,048,576 | $4／$20 |
| Muse Voice Transcribe | `muse-voice-transcribe-1.0` | Meta API | — | 無 | 無 | — | $0.18／小時音訊；檔案模式只收 WAV、≤10 分鐘 |
| Muse Spark Open | Baseten：`meta-models/muse-spark-open`（比賽用 `-1026`，**未驗證**） | 開放權重；Baseten、Modal、Together 等 | 有 | 有 | Baseten 接受但**不強制** | 1,048,576 | Baseten／Modal 與 Spark 標準版同價 |
| Muse Glimmer | `meta-models/Muse-Glimmer-30B` | 開放權重（29.6B dense，Apache 2.0） | 有 | 有，一回合只能一個 | 未驗證 | 131,072 | 只有 Together／DeepInfra 按 token 計價，**都不是比賽合作夥伴** |

| API 事實 | 對 pickfit 的意思 |
|---|---|
| base URL `https://api.meta.ai/v1`，OpenAI 相容（`/chat/completions`、`/responses`），另有 Anthropic 相容的 `/messages`；Bearer 認證，變數名 `MODEL_API_KEY` | 直接用 `openai` 套件改 `base_url`，不需專用 SDK |
| `tool_choice` 只能 `auto`；不支援 `stop`、`n>1`、`logprobs` | 不能強制呼叫某工具；要固定格式用 structured output |
| 一定會推理（`reasoning_effort: none` 回 400），推理 token 算輸出 | 大量工作設 `minimal`／`low`，成本要算推理 |
| Chat Completions 不跨回合保留推理；多步工具迴圈官方建議 Responses API | 驗證 agent 用 Responses API＋`previous_response_id` |
| Responses 有內建 `web_search`（$2.50／千次）、`reasoning.summary` | 驗證時查錯誤訊息；推理摘要可當 demo 的 trace |
| 沒有 Batch API；Spend Limit 只寄 email，不會停止扣款 | 程式自己記帳，超過門檻就停 |
| 3,000 RPM／4M TPM（以 team 計） | 一個人的規模完全夠 |
| 台灣帳號能否註冊、綁卡：地理政策沒擋台灣，8 月宣布全球開放，但**未實際確認** | **今天第一件事就是註冊**；失敗則全部改走 Baseten 上的 Spark Open |

### D.2 開放權重：用在哪、為什麼

- 開放權重**不會比較便宜**：Spark Open 在 Baseten／Modal 和 Meta 標準版同價；Meta 的 Contributor 版還便宜約 12–20 倍。
- 用它的理由是：比賽給的 Baseten credits、獨立的 rate limit、以及 Best Build on Meta Open Weight Models 加碼獎。
- 所以只放在**初篩**這一個環節：Spark Open @ Baseten，`reasoning_effort: low`，輸出用 pydantic 在程式端驗證（Baseten 不強制 schema）；低信心才升級到 `muse-spark-1.3` 複查。
- Glimmer 不用：合作夥伴都只提供專屬 GPU（Modal H100 約 $3.95／小時），自架的時間不划算。
- 授權要求產品顯示「Built with Muse Spark Open」，README 要放。

### D.3 每個環節怎麼用（讓評審一眼看出是核心）

**原則：模型做判斷，程式做守門。** 每個環節都有一個沒有模型就做不了的決定；程式負責搬資料、限制步數與花費、檢查輸出。產品執行期不用任何非 Meta 的 LLM。

| 環節 | 模型 | 模型做的決定 | 程式做的事 | 每 100 筆（估算） |
|---|---|---|---|---:|
| 1 初篩 | Spark Open @ Baseten | 是不是可用的軟體、哪一類、為什麼不是（不給星數，避免知名度偏誤） | 前置規則、JSON 驗證、5% 抽樣和 1.3 比對 | $1.4 |
| 2 抽取 | `muse-spark-1.3` | 讀 README、release notes、貼文、截圖，填欄位，**每欄附原文引用** | 檢查引用真的出現在來源；授權、release 等事實欄位用 API 值 | $2.4–2.8 |
| 3a 驗證 agent | `muse-spark-1.3`（Responses＋function tools＋`web_search`） | 每一步跑什麼、錯了怎麼修、何時結束 | 沙盒、步數／時間／花費上限 | $10–27 |
| 3b 畫面判讀 | `muse-spark-1.3`（圖片＋schema） | 截圖裡的軟體是否真的在運作，框出證據（0–1000 座標） | 和 exit code、重播結果合併 | $1.3 |
| 3c 重播 | 不用模型 | — | 在乾淨沙盒照記錄的步驟重跑一次，確認可重現 | — |
| 4 計分 | `muse-spark-1.3` | 文件完整度、安裝說明準確度（0–3 分，有錨點與引用） | 驗證、維護、知名度、寶藏分數都用規則算 | $3.8 |
| 5 配對 | `muse-spark-1.3` | 需求 → 條件、比較 2–3 個候選、找最好的免費選項、最多問 1–2 個問題 | 結構化篩選；檢查理由對得上欄位 | $2.4／100 次查詢 |

- 驗證 agent 是最能證明「核心」的地方：Muse Spark 自己決定安裝方式、讀錯誤、改指令、跑 smoke test。官方 cookbook 有 Muse Spark 1.3 在拋棄式 Docker 沙盒自主跑 48 個 shell 指令的例子，同一個模式。
- 停止條件：呼叫 `finish`，或 25 回合、15 個指令、20 分鐘、每款 $0.50、同一個錯誤 3 次。
- 成本（估算，推理 token 未實測）：收錄並驗證 100 款，Meta API 約 $18–35，Baseten 約 $1.4。$150 credits 約可處理 400–800 款，demo 規模（100–300 款）夠用。
- Demo 與 README：每一步標出模型、model ID、token、花費、推理摘要；數字從 trace log 自動產生。

### D.4 未驗證、拿到 key 後先測

| # | 項目 | 備案 |
|---|---|---|
| 1 | 台灣帳號能否開 Meta Model API | 全部改走 Spark Open @ Baseten |
| 2 | Baseten 的 `meta-models/muse-spark-open-1026` 是否存在 | 用 `/v1/models` 查；不行就用公開 ID |
| 3 | 截圖放在 tool 輸出裡模型看不看得到（文件互相矛盾） | 截圖放 user 訊息，或只交給 3b 判讀 |
| 4 | `text.format` 能否和 tools 同一請求 | 用 `finish` 工具＋程式驗證 |
| 5 | 推理 token 實際用量 | 調 `reasoning.effort`；先用 spike 的 `usage` 換掉估算 |

spike：`spikes/meta_api_hello.py`（文字、JSON schema、tool calling、圖片）、`spikes/meta_responses_agent_probe.py`（多輪工具迴圈、截圖放哪、schema＋tools、web_search）、`spikes/meta_baseten_hello.py`。設好環境變數就能跑。

## E. MCP server

（進行中）

## F. 儲存與配對

細節、DDL、JSON Schema 草案與 spike：[notes/storage-matching.md](notes/storage-matching.md)（查證日 2026-10-28）。

### F.1 儲存：git 裡的 JSON 當正本，D1 只放事件

| | git 中的 JSON（每款一檔） | SQLite 檔 | Cloudflare D1 | Postgres（Neon／Supabase） |
|---|---|---|---|---|
| 開發時間 | 最短 | 短，要遷移 | 中 | 最長，多一個服務 |
| MCP（Worker）怎麼讀 | 建置時轉成索引，打包進 Worker | Worker 不能直接開，要 sql.js（WASM）或先轉 JSON | binding 直接查 | 要 HTTP driver |
| 可審計性 | **最好**：每次改動一個 commit，也是「比賽期間做的」證據 | 二進位，diff 看不懂 | 只能還原，看不到逐欄位變更 | 要自己做 audit 表 |
| 人工抽查 | 開檔改 | 要 SQL | 要 SQL | 要 SQL |

**建議**：

| # | 決定 | 理由 |
|---|---|---|
| 1 | 正本：`data/software/<slug>.json`，用 JSON 不用 YAML | diff 就是審計紀錄；不必處理 YAML 的隱式型別 |
| 2 | 建置時把全部檔案轉成一個 `index.json`（候選卡＋預先算好的 BM25 倒排），**打包進 Worker** | spike：3,000 筆 bundle 約 1 MB；8,198 筆 `JSON.parse` 16.5 ms，查詢中位數 <1 ms，離 Worker 啟動 1 秒上限很遠（本機量測） |
| 3 | 事件（查詢、安裝指南、回報、提交）寫 **D1**：`events`、`reverify_queue`、`meta_budget` 三張表 | 要 SQL 彙總與去重；KV 免費版每天只能寫 1,000 個 key、最終一致，不適合 |
| 4 | push → Workers Builds 自動 `validate → build_index → deploy` | 不用自己寫同步程式；資料壞了就不會部署 |
| 5 | 失敗回報進 `reverify_queue` → 驗證 agent 重跑 → 新步驟 commit 回 git | 「回報 → 重驗 → 安裝步驟被修正」留下一個 git diff，是「不是 RAG」最直接的證據 |
| 6 | 不記 IP，不存需求原文，只存模型解析後的條件 | brief 第 11 節 |

Cloudflare 免費額度（[Workers limits](https://developers.cloudflare.com/workers/platform/limits/)、[D1 limits](https://developers.cloudflare.com/d1/platform/limits/)）：Workers 每天 10 萬請求、每請求 CPU 10 ms；D1 每天讀 500 萬列、寫 10 萬列。demo 用不完。**未驗證**：Free 方案冷啟動時解析索引是否算進 10 ms CPU；出現 Error 1102 就改 Paid（每月 $5）。

### F.2 配對：條件篩選為主，模型負責理解與取捨

| 步 | 誰 | 做什麼 |
|---|---|---|
| A 解析需求 | Muse Spark | 自然語言 → 條件（OS、預算、隱私、類別、必要功能、目前在用的工具）＋英文 `search_terms` |
| B 硬條件篩選 | 程式 | 只留 `listed`、該 OS 驗證過、符合本機執行／免費等條件的 |
| C 取候選 | 程式 | 在合格清單上用 BM25 查 `search_terms`，取前 25 張候選卡（每張約 350 tokens） |
| D 該不該問 | 程式＋Muse Spark | 程式先找「前 5 名在這個屬性上不同、但需求沒說」的屬性；沒有就不准問；有的話由模型判斷問了會不會改變第一名 |
| E 比較取捨 | Muse Spark | 選 1–3 個，每個理由附對應欄位；寫和知名工具的取捨、最好的免費選項、「不需要新軟體」的情況 |
| F 守門 | 程式 | slug 必須在候選裡、理由對得上欄位；模型失敗就退回寶藏分數排序＋模板理由，標 `generated_by: rules` |
| G 安裝 | 程式 | `get_install_guide` 只回傳重播過的步驟，不呼叫模型 |
| H 回報 | 程式 | `report_outcome` 寫 D1；失敗就排入重驗 |

**和基本 RAG 的差別**：

| | 基本 RAG | pickfit |
|---|---|---|
| 知識從哪來 | 現成文件切塊 | 自己產生：模型讀懂、沙盒實際安裝、程式重播後寫成結構化檔案 |
| 候選怎麼來 | 向量相似度取段落 | 硬條件篩選＋關鍵字；模型負責改寫需求 |
| 模型做什麼 | 摘要檢索到的段落 | 轉條件、決定要不要問、比較取捨、找免費選項；每個理由要對得上欄位 |
| 輸出 | 一段文字 | 可執行的東西：重播過的安裝步驟、驗證指令 |
| 之後 | 結束 | 回報 → 重驗 → git 裡的步驟被修正 |

### F.3 不用向量搜尋

- Meta Model API 文件裡**沒有 embedding 模型或 `/v1/embeddings`**（沒有 key 無法用 `/v1/models` 確認，標未驗證）。用別家 embedding 等於在配對核心放非 Meta 模型，而「向量庫＋LLM」正是基本 RAG 的樣子。
- spike（`spikes/sm_index_bench.mjs`）：用 Homebrew 8,198 個 formula 的描述當語料、10 題。使用者原話直接查 BM25，好答案進前 25 名的只有 5／10；換成「模型會產生的英文關鍵字」（手寫模擬，不是模型輸出）後是 10／10。
- 結論：語意落差交給 Muse Spark 在兩端處理（抽取時寫 `use_cases`、`alternatives_to`；查詢時寫 `search_terms`）。評測時若有 2 題以上好答案沒進前 25 名，再考慮向量。

## G. 整體架構

（進行中）

## H. 每天的實作計畫

（進行中）

## I. 風險

（進行中）

## J. 建議修改 brief

（進行中）

## K. 需要念誠決定或提供的東西

（進行中）
