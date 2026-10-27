# 管道盤點：軟體從哪裡來

2026-10-28 · [architecture.md](architecture.md) A 節的詳細版。各組的原始筆記、實測腳本與來源在 [notes/](notes/)；每組都由一個 agent 調研、另一個 agent 反向查核。查證日一律 2026-10-28。

**狀態**：社群、區域、Meta 平台三組已查核；程式碼託管、套件生態兩組已調研、查核中；策展與資料集、整合工程兩組調研中。查核完成後更新本頁。

---

## 0. 結論

**黑客松期間接這 5 條**（理由見第 2 節）：

| # | 管道 | 為什麼 | 工時 |
|---|---|---|---|
| 1 | **GitHub search API**（＋ repo、release、README 補資料） | 兩個類別的新作品主要都在這；能直接篩「今年建立、最近有 push、星數 5–300」；官方 API、條款清楚 | 6–9 h |
| 2 | **Homebrew 第三方 tap**（官方 analytics）＋ homebrew-core 當知名度基準 | 最好的「默默無聞但有人在用」訊號：30 天內新出現 4,066 個 tap formula，其中 437 個 30 天安裝 10–1000 次；抽 40 個，36 個今年才建、星數中位數 1。直接對上 Mac demo | 3–4 h |
| 3 | **Hacker News Show HN**（官方 Firebase API＋Algolia） | 規則要求「你親自做的、別人能試用的」；每週約 990 篇，兩類別且連 GitHub 的約 75 篇；86% 只有 ≤3 分，正是沒人注意到的 | 2–4 h |
| 4 | **PyPI 新專案**（RSS＋`changelog_since_serial`，看 wheel 的 `console_scripts`） | 本地 AI 工具主要在這；約每小時 40 個新專案，`console_scripts` 能篩出 CLI | 3–4 h |
| 5 | **作者或使用者提交**（MCP `submit_software` 工具＋GitHub Issue Form） | 供給端入口；只收 GitHub 連結＋說明；Threads 貼文連結只用官方 oEmbed **嵌入**，不讀內容 | 2–3 h |

**補資料（不是發現來源）**：ecosyste.ms（repo metadata、release 檔案清單；資料 CC BY-SA 4.0）、deps.dev（套件 ↔ repo 的對應有沒有發布簽章證明；CC-BY 4.0）、OpenSSF Scorecard API。

**時間夠再加**：V2EX「分享创造」＋ Qiita `個人開発` ＋ 阮一峰周刊「工具」（三條共 3.5–5 h，讓「全球」不只是英文圈）。

**要避開**（第 4 節）：爬任何 Meta 網站、Threads keyword search、Reddit、Product Hunt、X（要付費）、Lobsters 自動抓取、LinkedIn、Discord 抓取、GitHub trending 頁、GitLab 大量輪詢、SourceHut、掘金、PTT、Dcard、Hatena（未取得書面同意前）、libraries.io、pypistats 大量抓取。

**brief 要改的地方**（詳見 architecture.md J 節）：
- 「任何人貼 Threads 連結就收錄」做不到：Threads 的 oEmbed 回傳裡沒有貼文文字，條款也禁止抽取；用 Threads 登入讀作者貼文再交給模型，也不在 `threads_basic` 的允許用途內。改成「提交 GitHub 連結＋說明，Threads 連結只用來嵌入」。
- winget 沒有公開安裝數；Homebrew analytics 的資料授權沒寫明（只取數字當訊號、不轉發原始資料）。

---

## 1. 總表

訊號品質指「找出默默無聞的好軟體」的幫助。工時是一個人接上的估計。

### 1.1 程式碼與模型託管（查核中）

| 管道 | 訊號品質 | 取得方式 | 主要限制 | 工時 | 建議 |
|---|---|---|---|---|---|
| GitHub search API | 中高 | REST／GraphQL | 每個 query 最多 1,000 筆、search 30 次／分；AUP 只明列研究與封存用途、禁止重製或轉售服務 → 只走 API、只存自己抽出的事實＋連結 | 4–6 h | **接（主力）** |
| GitHub repo／release／README | 高（品質訊號） | REST、raw | core 5,000 次／時 | 2–3 h | **接** |
| GitHub events API／GH Archive／BigQuery | 低 | API、每小時 dump | 實測 2025-10 起每小時檔 0 筆新 repo 事件（查核中） | — | 避開 |
| GitHub trending 頁 | 中，偏已爆紅 | 只有 HTML | 沒有官方 API；爬 HTML 不在 AUP 允許用途 | — | 避開 |
| Hugging Face Spaces | 低–中 | API（免金鑰） | 多是線上 demo，本地 AI 關鍵字 7 天 20 筆、可安裝的 0 | 2–3 h | 之後 |
| Hugging Face models | 低（是模型不是軟體） | API | — | — | 只當輔助訊號 |
| GitLab.com | 低 | API | API Terms 禁止 bulk collection | 1–2 h | 之後（只收提交連結） |
| Codeberg | 中 | API | robots.txt `Disallow: /api/`；混有帳號農場工具 | 1–2 h | 之後（只收提交連結） |
| Gitee、SourceHut | 低 | API | Gitee 未登入搜尋 0 筆；SourceHut 條款禁止營利收集與 LLM 相關內容 | — | 避開 |

### 1.2 套件生態（查核中）

| 管道 | 訊號品質 | 取得方式 | 主要限制 | 工時 | 建議 |
|---|---|---|---|---|---|
| Homebrew 第三方 tap（analytics） | **高** | formulae.brew.sh analytics JSON＋讀 tap repo 的 `.rb` | 沒有 rate limit 或條款說明；資料授權未明示 | 3–4 h | **接** |
| homebrew-core | 中（新作品進不去：要 75 星、repo 滿 30 天） | `formula.json`（有 `executables` 欄位）、analytics | 同上 | 1–2 h | **接**（知名度基準） |
| PyPI | 中 | RSS（只涵蓋約 1 小時）、XML-RPC `changelog_since_serial`、JSON API；wheel 的 `console_scripts` 用 HTTP Range 讀 | ToS：過度請求可停權；要可識別的 User-Agent | 3–4 h | **接** |
| npm | 低–中（72% scoped、placeholder 多） | replicate `_changes`、registry、downloads API | 不准爬網站、不准當通用資料庫 | 3 h | 之後 |
| crates.io | 中（91% 連 GitHub，`bin_names` 可判斷 CLI） | API、每日 db dump | 1 req/s、必須帶 User-Agent | 2 h | 之後 |
| Go（index＋pkg.go.dev） | 低（量極大） | index feed、pkg.go.dev v1 API | 45 QPS／IP block | 3–4 h | 之後 |
| winget-pkgs | 中（無安裝數、GUI 多） | Git repo（MIT） | — | 2–3 h | 之後 |
| AUR | 中（80% 連 GitHub，只限 Arch） | metadata dump、RPC | RPC 每 IP 每天 4,000 次（未驗證） | 1–2 h | 之後 |
| Scoop、Nixpkgs、conda-forge、Docker Hub | 低 | Git repo／API | 有星數門檻或無上架日期 | — | 不當發現來源 |
| ecosyste.ms | 中高（補資料） | API、Postgres dump | 匿名 5,000 次／時，帶 mailto 15,000 次／時；**CC BY-SA 4.0**；PyPI 新套件延遲約 34 小時 | 2 h | **接（補資料）** |
| deps.dev | 中（補資料，有發布簽章證明的 repo 對應） | API v3、BigQuery | Google API ToS；資料 CC-BY 4.0；不含 Homebrew | 1 h | **接（補資料）** |
| libraries.io | 低（與 ecosyste.ms 重複） | API（要 key） | 60 次／分；公開 dump 停在 2020 | — | 避開 |

### 1.3 社群與社交（已查核）

| 管道 | 訊號品質 | 取得方式 | 主要限制 | 工時 | 建議 |
|---|---|---|---|---|---|
| **Hacker News Show HN** | **高** | 官方 Firebase API、Algolia（都免金鑰） | YC 條款禁止爬網站 → 只走 API、只存連結與 metadata；`/v0/showstories` 只是排序過的子集，要用 Algolia 按天切或輪詢 `/v0/newstories` | 2–4 h | **接** |
| Bluesky | 中 | Jetstream（免認證、不計量） | 未登入搜尋只拿得到第一頁；Developer Guidelines 要求處理刪除 | 3–4 h | 可選（@mention 提交） |
| dev.to `#showdev` | 中 | Forem API（免金鑰） | 網站條款只允許「personal, non-commercial transitory viewing」 | 2–3 h | 之後（先取得 DEV 書面同意） |
| Mastodon／fediverse | 低–中 | hashtag timeline API | 約一半帳號 `indexable=false`；社群反感未經同意的抓取 | 3 h | 之後（只做 @mention 提交） |
| X | 中 | API v2（按則計費） | 讀一則 $0.005，沒有免費讀取層 | 3–4 h＋費用 | 之後 |
| Reddit | 中 | Data API | 任何 API 存取都要先申請核准；禁止商用與訓練 | — | **避開** |
| Product Hunt | 中（SaaS 為主） | GraphQL API v2 | 「must not be used for commercial purposes」 | — | **避開** |
| Lobsters | 高但量極少（約 3 篇／週） | JSON、RSS | robots.txt `Disallow: /`、`ai-input=no` | — | **避開**（連提交的 Lobsters 連結也不抓，請提交者給 GitHub 連結） |
| Indie Hackers、LinkedIn | 低 | 無公開 API／讀取要核准 | — | — | **避開** |
| Discord | 中高（只限 bot 被邀請的伺服器） | Bot＋Gateway | Developer Policy 禁止 mine／scrape、禁止拿訊息訓練 AI | — | **避開**（之後可做「作者邀 bot」） |

### 1.4 Meta 平台（已查核）

| 管道 | 能做什麼 | 主要限制 | 建議 |
|---|---|---|---|
| Threads oEmbed（免 token） | 嵌入原貼文 | 回傳的 html **沒有貼文文字**；條款禁止抽取、保存內容 | **接**（只嵌入） |
| Threads Web Intents（分享按鈕） | 被收錄的作者一鍵分享 | 無審核 | **接** |
| Threads 自家帳號發文（`threads_content_publish`） | 發「今日寶藏」 | 讀別人的回覆再收錄：允許用途未驗證、風險高 | 可選（只發文） |
| Threads 登入讀作者貼文交給模型 | — | `threads_basic` 允許用途只限「把貼文顯示給作者本人」，Development mode 也不豁免 | **避開** |
| Threads keyword／topic search | — | 未審核只搜得到自己的貼文；允許用途是「管理社群形象」，消費者 app 嚴格禁止 | **避開** |
| Threads mentions、profile discovery | — | 未審核只回 tester／4 個 Meta 官方帳號 | 之後（mentions）／避開 |
| Facebook Groups API | — | 2024-04-22 已移除 | **避開** |
| Facebook 粉專（PPCA）、Instagram hashtag | — | App Review＋商家驗證；用途不符 | **避開** |
| Meta Content Library | — | 只開放學術或非營利研究機構 | **避開** |
| 爬 threads.com／facebook.com／instagram.com | — | robots.txt 與 Automated Data Collection Terms 禁止 | **避開** |

實測：HN 一年內只有 33 則 story 連到 Threads 貼文（Show HN 1 則），連到 X 的至少 1,110 則。Threads 在英文開發者圈不是主要發表管道。

### 1.5 各地區開發者社群（已查核）

| 管道 | 訊號品質 | 量 | 取得方式 | 主要限制 | 工時 | 建議 |
|---|---|---|---|---|---|---|
| V2EX「分享创造」 | 高（節點就是發表作品） | 約 270 篇／週，40% 連 repo | Atom（免金鑰，含全文） | 沒有一般條款，只有 API 公平使用規則（反對拿輸出填充網站內容）→ 只存連結、標題、日期 | 1–1.5 h | 時間夠再接 |
| Qiita `tag:個人開発` | 中高（likes 中位數 1） | 約 200 篇／週，29% 連 repo | API v2（免金鑰 60 次／時） | 利用規約：不可轉貼 | 1–1.5 h | 時間夠再接 |
| 阮一峰周刊「工具」 | 中高（人工精選，混有爆紅大專案） | 12–18 個／週 | GitHub raw 檔 | CC BY-NC-ND 3.0 → 只取連結，不抄描述；只取標「投稿」的 | 0.5–1 h | 時間夠再接 |
| GeekNews Show GN（韓） | 高 | 約 70 篇／週 | RSS（不含原始連結） | robots 擋 Meta 的爬蟲 UA，絕不用 | 2 h | 可選 |
| Zenn、HelloGitHub、Gitee | 中／低 | — | RSS／raw／API | Zenn 禁止轉載；HelloGitHub CC BY-NC-ND | — | 之後 |
| Hatena Bookmark | 中 | 約 45 repo／週 | RSS | Developer Center 規約禁止把資訊提供給第三方 | — | 之後（先取得書面同意） |
| 掘金、PTT、Dcard、velog、Habr、OSChina、iThome | 低 | — | 無官方 API 或條款不允許 | 掘金條款禁止機器人；PTT 擋 AI agent；Habr 禁止商用 | — | **避開** |

### 1.6 策展、榜單與公開資料集（調研中）

awesome 清單、newsletter、GH Archive、OSS Insight、BigQuery、ClickHouse playground 等。結果待補。

---

## 2. 為什麼是這 5 條

| 評估角度 | GitHub search | Homebrew tap | Show HN | PyPI | 提交 |
|---|---|---|---|---|---|
| 新作品多 | 極多 | 每月數千 | 每週約 990 | 每小時約 40 | 靠作者 |
| 默默無聞 | 可用星數篩 | 星數中位數 1 | 86% ≤3 分 | likes 無；用下載量 | 作者自選 |
| 有使用訊號 | 星數 | **真實安裝數** | 分數、留言 | 下載量 | 無 |
| 兩個 demo 類別 | 兩類都多 | CLI 為主，15/40 和 AI 相關 | 兩類約 75 篇／週 | 本地 AI 多 | 兩類 |
| 條款風險 | 低（只走 API） | 低（官方 JSON） | 低（只走 API） | 低 | 低 |
| 一個人接上 | 6–9 h | 3–4 h | 2–4 h | 3–4 h | 2–3 h |

合計約 16–24 小時，扣掉其他工作，第 2–3 天可完成前 3 條，第 5 天補提交入口。

---

## 3. 本 session 的限制（要在本機跑）

這個雲端 session 的 proxy 把 GitHub API 綁在 `ncchen99/pickfit`：`/search/repositories` 與其他 repo 的 `/repos/...` 回 403，GraphQL 也被擋。所以：
- 兩個類別在 GitHub 上的 7／14 天筆數**沒量到**。腳本 `spikes/ch_hosting_github.py` 已寫好，念誠用自己的 PAT（fine-grained、不勾任何權限就能讀公開 repo）在本機跑約 3 分鐘。
- 發現管線要在本機或 Modal 跑，不能放在這種雲端 session。

---

## 4. 要避開的管道與原因

| 管道 | 原因 | 來源 |
|---|---|---|
| 爬 threads.com、facebook.com、instagram.com | robots.txt 與 Automated Data Collection Terms 要求書面許可 | [ADC Terms](https://www.facebook.com/legal/automated_data_collection_terms) |
| Threads keyword search、Threads 登入讀貼文交給模型 | 允許用途不符；消費者 app 嚴格禁止 | [Permissions](https://developers.facebook.com/documentation/development/permissions) |
| Reddit | 任何 API 存取都要先核准；禁止商用與訓練 | 見 [notes/channels-communities.md](notes/channels-communities.md) |
| Product Hunt | API 禁止商用 | 同上 |
| X | 沒有免費讀取層 | 同上 |
| Lobsters 自動抓取 | robots.txt 全擋、`ai-input=no` | 同上 |
| LinkedIn、Indie Hackers、Discord 抓取 | 沒有讀取權限或條款禁止 | 同上 |
| GitHub trending 頁、GitHub HTML | 沒有 API；爬 HTML 不在 AUP 允許用途 | 見 [notes/channels-hosting.md](notes/channels-hosting.md) |
| GitLab 大量輪詢、SourceHut、Gitee | 條款禁止大量收集／營利收集／未登入拿不到 | 同上 |
| 掘金、PTT、Dcard、Habr、velog | 條款禁止機器人或商用；擋 AI agent；垃圾內容多 | 見 [notes/channels-regional.md](notes/channels-regional.md) |
| Hatena | 規約禁止把資訊提供給第三方（先取得書面同意） | 同上 |
| libraries.io、pypistats 大量抓取 | 要 key 且資料過舊；官方明說不要大量抓 | 見 [notes/channels-packages.md](notes/channels-packages.md) |
| 任何 Meta 爬蟲 User-Agent（`meta-externalagent` 等） | 很多網站專門擋 | — |

---

## 5. 整合方式（調研中）

增量抓取、去重、正規化、漏斗與提交入口的設計。結果待補，見 [notes/channels-integration.md](notes/channels-integration.md)（調研中）。
