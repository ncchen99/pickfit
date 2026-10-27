# 管道盤點：軟體從哪裡來

2026-10-28 · [architecture.md](architecture.md) A 節的詳細版。7 組原始筆記、實測腳本與來源在 [notes/](notes/)（`channels-*.md`）；每組都由一個 agent 調研、另一個 agent 反向查核（找錯、改正、標「未驗證」）。查證日一律 2026-10-28。

**狀態**：7 組都已調研並查核。

---

## 0. 結論

**值得接的 5 條**（理由見第 2 節）。依 [architecture.md](architecture.md) H 節的工時，**一定接前 3 條，第 4、5 條進度超前才接**：

| # | 管道 | 層級 | 為什麼 | 工時（最低版本／完整版） |
|---|---|---|---|---|
| 1 | **GitHub search API**（＋ repo、release、README 補資料） | 核心 | 兩個類別的新作品主要都在這；能直接篩「今年建立、最近有 push、星數 5–300」；16 條 query 已寫好 | 4 h／6–9 h |
| 2 | **提交入口**（MCP `submit_software`；GitHub Issue Form 選做，共用一個佇列） | 核心 | 供給端，也是 demo 第 5 幕；收 GitHub repo 連結；Threads 貼文連結只用官方 oEmbed **嵌入**，不讀內容 | 2 h／2–3 h |
| 3 | **Hacker News Show HN**（官方 Firebase API＋Algolia） | 計畫內 | 規則要求「你親自做的、別人能試用的」；每週約 990 篇，兩類別且連 GitHub 約 75 篇；86% 只有 ≤3 分；spike 已寫好 | 1.5 h／2–4 h |
| 4 | **Homebrew 第三方 tap**（官方 analytics）＋ homebrew-core 當知名度基準 | 超前才做 | 唯一同時有「安裝數」和「默默無聞」的訊號：30 天內新出現 4,066 個 tap formula，437 個安裝 10–1000 次；抽 40 個，36 個今年才建、星數中位數 1。**以 CLI 為主**（本地 AI 約 3／40）；對上 Mac demo | 2 h／3–4 h |
| 5 | **PyPI 新專案**（RSS 每 20–30 分鐘輪詢；看 wheel 的 `console_scripts`） | 超前才做 | 本地 AI 工具很多在這；約每小時 40 個新專案；27／39 個有 Trusted Publishing provenance，可確認套件 ↔ repo | 3 h／3–4 h |

本地 AI 類別在最低版本靠 GitHub search 的 topic（`ollama`、`llama-cpp`、`local-llm` 等）與 Show HN 涵蓋。

**之後擴充（依序）**：
1. awesome 清單的 diff：`rothgar/awesome-tuis`（CLI，近 90 天新增 51 筆、星數中位數 42）、`EndoTheDev/awesome-ollama`（本地 AI，新增 43 筆、中位數 12）。兩份都沒有授權檔，只取 repo 連結當內部訊號，不轉載描述、不公開重建清單。約 2–3 h。
2. V2EX「分享创造」＋ Qiita `個人開発` ＋ 阮一峰周刊「工具」（讓「全球」不只是英文圈）。約 3.5–5 h。
3. Bluesky @mention 提交、dev.to `#showdev`（先取得 DEV 書面同意）、crates.io、npm、winget、Hugging Face Spaces（只看連回作者 GitHub 的）、Console.dev（先寫信）。

**補資料（不是發現來源）**：GitHub REST API（metadata、release、README）、deps.dev（套件 ↔ repo 的對應有沒有發布簽章；只有它自產的關聯資料是 CC-BY 4.0）、Scorecard CLI `--local`（沙盒裡順便跑）。**ecosyste.ms 要先寄信取得書面同意**才放進管線（條款 §9 禁止未經同意的腳本擷取）。

**要避開**（第 4 節）：爬任何 Meta 網站、Threads keyword search、Threads 登入讀貼文交給模型、Reddit、Product Hunt、X（要付費）、Lobsters 自動抓取、LinkedIn、Discord 抓取、GitHub trending 頁、GH Archive／BigQuery／ClickHouse／OSS Insight（資料已失準）、RSSHub（多數路由抓 HTML）、GitLab 大量輪詢、SourceHut、掘金、PTT、Dcard、Hatena（未取得書面同意前）、libraries.io、pypistats 大量抓取、PyPI XML-RPC 新整合。

**條款上的共同做法**：只走官方 API 或 feed；只存我們自己抽出的事實＋連結；不轉貼 README 或貼文全文；不存個資；不用任何 Meta 爬蟲 User-Agent。GitHub AUP §7 對 API 取得的資料也限制用途（明列研究、封存），推薦服務算不算在內有解讀空間（未驗證）；黑客松照上述做法，正式商用前先向 GitHub 確認。

---

## 1. 總表

訊號品質指「找出默默無聞的好軟體」的幫助。工時是一個人接上的估計。

### 1.1 程式碼與模型託管（[notes/channels-hosting.md](notes/channels-hosting.md)）

| 管道 | 訊號品質 | 取得方式 | 主要限制 | 工時 | 建議 |
|---|---|---|---|---|---|
| GitHub search API | 中高 | REST／GraphQL | 每個 query 最多 1,000 筆、不能依建立時間排序 → 用 `created:` 分片；search 30 次／分；AUP §7 用途限制也適用 API 資料 | 4–6 h | **接（主力）** |
| GitHub repo／release／README | 高（品質訊號） | REST、raw | core 5,000 次／時；回 304 的條件請求不計 | 2–3 h | **接** |
| GitHub events API／GH Archive／BigQuery | 低 | API、每小時 dump | 新 repo 事件 2025-10-09 起歸零；2026-10-26 起每小時事件驟降到約 2,800 筆 | — | 避開 |
| GitHub trending 頁 | 中，偏已爆紅 | 只有 HTML | 沒有官方 API；爬 HTML 屬 scraping | — | 避開 |
| Hugging Face Spaces | 低–中 | API（免金鑰） | 多是線上 demo；README 連回作者 GitHub 的才有可安裝工具（例：ollama-hud） | 2–3 h | 之後 |
| Hugging Face models | 低（是模型不是軟體） | API | — | — | 只當旁證 |
| GitLab.com | 低 | API | API Terms 禁止 bulk collection；2026-10-19 起未登入每 IP 60 次／時 | 1–2 h | 之後（只處理提交連結，要帶 token） |
| Codeberg | 中 | API | robots.txt `Disallow: /api/`；有帳號一天建 40 個帳號農場工具 | 1–2 h | 之後（只處理提交連結） |
| Gitee、SourceHut | 低 | API | Gitee 未登入搜尋 0 筆；SourceHut 禁止營利收集與 LLM 相關內容 | — | 避開 |

### 1.2 套件生態（[notes/channels-packages.md](notes/channels-packages.md)）

| 管道 | 訊號品質 | 取得方式 | 主要限制 | 工時 | 建議 |
|---|---|---|---|---|---|
| Homebrew 第三方 tap（analytics） | **高**（CLI） | formulae.brew.sh analytics JSON＋讀 tap repo 的 `.rb` | 沒有 rate limit 或條款說明；資料授權未明示；安裝數沒排除 CI，只當弱訊號 | 3–4 h | **接** |
| homebrew-core | 中（新作品進不去：75 星、repo 滿 30 天） | `formula.json`（有 `executables`）、analytics | 同上 | 1–2 h | **接**（知名度基準、官方安裝方式） |
| PyPI | 中（本地 AI 主力） | RSS（約 1 小時，每 20–30 分鐘輪詢）、JSON API；wheel 的 `console_scripts` 用 HTTP Range 讀 | 官方：「No new integrations should use the XML-RPC APIs」；過度請求可停權 | 3–4 h | **接** |
| npm | 低–中（72% scoped、placeholder 多） | replicate `_changes`、downloads API | 不准自動化存取網站 | 3 h | 之後 |
| crates.io | 中（91% 連 GitHub，`bin_names` 判斷 CLI） | API、RSS、每日 db dump | 1 req/s、必須帶 User-Agent | 2 h | 之後 |
| Go（index＋pkg.go.dev） | 低（量極大） | index feed、pkg.go.dev v1 API | 45 QPS／IP block | 3–4 h | 之後 |
| winget-pkgs | 中（**沒有安裝數**、GUI 多） | Git repo（MIT） | — | 2–3 h | 之後 |
| AUR | 中（80% 連 GitHub，只限 Arch） | metadata dump、RPC | RPC 限制正式站未驗證 | 1–2 h | 之後 |
| Scoop、Nixpkgs、conda-forge、Docker Hub | 低 | Git repo／API | 星數門檻或無上架日期 | — | 不當發現來源 |
| deps.dev | 中（補資料） | API v3 | Google API ToS；只有 deps.dev 自產的關聯是 CC-BY 4.0，星數不能當 CC-BY 存；不含 Homebrew | 1 h | **接（補資料）** |
| ecosyste.ms | 中高（補資料） | API | 資料 CC BY-SA 4.0（ShareAlike）；**Terms §9 禁止未經書面同意的腳本擷取，§11(c) 只授權個人使用** | 2 h | **寄信取得同意後才接** |
| libraries.io | 低 | API（要 key） | 公開 dump 停在 2020 | — | 避開 |

### 1.3 策展、榜單與公開資料集（[notes/channels-curation.md](notes/channels-curation.md)）

| 管道 | 訊號品質 | 取得方式 | 主要限制 | 工時 | 建議 |
|---|---|---|---|---|---|
| `rothgar/awesome-tuis` | 高（近 90 天 +51、星數中位數 42） | git diff | 沒有授權檔 → 只取連結 | 2（共用腳本） | 時間夠再接（CLI） |
| `EndoTheDev/awesome-ollama` | 中高（新增 43、中位數 12） | git diff（比對名稱＋URL） | 沒有授權檔 → 只取連結 | 0.5 | 時間夠再接（本地 AI） |
| `agarrharr/awesome-cli-apps` | 中（已封存） | git | CC0 | 0.5 | 一次性匯入約 550 筆當「已知工具」對照組 |
| `rafska/awesome-local-llm`、`vince-lam/awesome-local-llms` | 低（新增項目星數中位數上萬） | git | MIT | 0.5 | 當「已知名」名單 |
| awesome-shell、terminals-are-sexy、janhq/awesome-local-ai | 低（停更） | git | — | — | 避開 |
| awesome-selfhosted | 中（要求首次 release 滿 4 個月） | git（YAML） | CC BY-SA 3.0 | 1 | 之後 |
| Console.dev | 中高（人工評測，偏商業） | RSS、免金鑰 API、MCP | 條款允許「為評估工具而查詢」；儲存、轉載要先聯絡 | 1＋寫信 | 之後（先寫信） |
| This Week in Rust | 中高（量小、只有 Rust） | RSS | CC BY-SA | 1 | 之後 |
| TLDR、HelloGitHub | 低–中 | RSS／git | HelloGitHub CC BY-NC-ND | 1.5–2 | 之後 |
| Terminal Trove | 中高（CLI 目錄），但讀不到 | 被 Cloudflare 擋 | 條款未驗證；不要繞過 | — | 之後（寫信問） |
| Changelog News／Nightly、Golang Weekly、Python Weekly | — | — | 停刊、資料失準、追蹤轉址被 robots 擋、沒有 RSS | — | 避開 |
| GH Archive、BigQuery `githubarchive`、ClickHouse playground、OSS Insight | 低 | dump／SQL／API | 新 repo 事件歸零；ClickHouse 停在 2026-07-02；OSS Insight trends 2026-03-01 起停用 | — | 避開 |
| Hugging Face trending | 低（多是大公司 demo） | API | — | 1 | 之後（旁證） |
| **自算 trending**：GitHub search＋stargazers `starred_at` | 高 | API | 同 GitHub search | 已含在 #1 | **接**（取代公開資料集） |

### 1.4 社群與社交（[notes/channels-communities.md](notes/channels-communities.md)）

| 管道 | 訊號品質 | 取得方式 | 主要限制 | 工時 | 建議 |
|---|---|---|---|---|---|
| **Hacker News Show HN** | **高** | 官方 Firebase API、Algolia（都免金鑰） | YC 條款禁止爬網站 → 只走 API、只存連結與 metadata；`/v0/showstories` 只是排序過的子集，要用 Algolia 按天切或輪詢 `/v0/newstories` | 2–4 h | **接** |
| Bluesky | 中 | Jetstream（免認證、不計量） | 未登入搜尋只拿得到第一頁；要處理刪除；不要自動回覆每個 mention | 3–4 h | 可選（@mention 提交） |
| dev.to `#showdev` | 中（約 887 篇／週，73% 零反應） | Forem API（免金鑰） | 網站條款只允許「personal, non-commercial transitory viewing」 | 2–3 h | 之後（先取得 DEV 書面同意） |
| Mastodon／fediverse | 低–中 | hashtag timeline API | 約一半帳號 `indexable=false` | 3 h | 之後（只做 @mention 提交） |
| X | 中 | API v2（按則計費） | 讀一則 $0.005，沒有免費讀取層 | 3–4 h＋費用 | 之後 |
| Reddit | 中 | Data API | 任何 API 存取都要先核准；禁止商用與訓練 | — | **避開** |
| Product Hunt | 中（SaaS 為主） | GraphQL API v2 | 「must not be used for commercial purposes」 | — | **避開** |
| Lobsters | 高但量極少 | JSON、RSS | robots.txt `Disallow: /`、`ai-input=no` | — | **避開**（提交的 Lobsters 連結也不抓，請提交者給 GitHub 連結） |
| Indie Hackers、LinkedIn | 低 | 無公開 API／讀取要核准 | — | — | **避開** |
| Discord | 中高（限 bot 被邀請的伺服器） | Bot＋Gateway | Developer Policy 禁止 mine／scrape、禁止拿訊息訓練 AI | — | **避開**（之後可做「作者邀 bot」） |

### 1.5 Meta 平台（[notes/channels-meta-platforms.md](notes/channels-meta-platforms.md)）

| 管道 | 能做什麼 | 主要限制 | 建議 |
|---|---|---|---|
| Threads oEmbed（免 token） | 嵌入原貼文 | 回傳的 html **沒有貼文文字**；條款禁止抽取、保存內容 | **接**（只嵌入） |
| Threads Web Intents（分享按鈕） | 被收錄的作者一鍵分享 | 無審核；不計入 Most Viral（只算 X） | **接** |
| Threads 自家帳號發文 | 發「今日寶藏」 | 讀別人的回覆再收錄：允許用途未驗證、風險高 | 可選（只發文） |
| Threads 登入讀作者貼文交給模型 | — | `threads_basic` 允許用途只限「把貼文顯示給作者本人」；Development mode 不豁免 | **避開** |
| Threads keyword／topic search | — | 未審核只搜得到自己的貼文；允許用途是「管理社群形象」，消費者 app 嚴格禁止 | **避開** |
| Threads mentions、profile discovery | — | 未審核只回 tester／4 個 Meta 官方帳號 | 之後（mentions）／避開 |
| Facebook Groups API | — | 2024-04-22 已移除 | **避開** |
| Facebook 粉專（PPCA）、Instagram hashtag | — | App Review＋商家驗證；用途不符 | **避開** |
| Meta Content Library | — | 只開放學術或非營利研究機構 | **避開** |
| 爬 threads.com／facebook.com／instagram.com | — | robots.txt 與 Automated Data Collection Terms 禁止 | **避開** |

實測：HN 一年內只有 33 則 story 連到 Threads 貼文（Show HN 1 則），連到 X 的至少 1,110 則。Threads 在英文開發者圈不是主要發表管道。

### 1.6 各地區開發者社群（[notes/channels-regional.md](notes/channels-regional.md)）

| 管道 | 訊號品質 | 量 | 取得方式 | 主要限制 | 工時 | 建議 |
|---|---|---|---|---|---|---|
| V2EX「分享创造」 | 高（節點就是發表作品） | 約 270 篇／週，40% 連 repo | Atom（免金鑰，含全文） | 沒有一般條款，只有 API 公平使用規則（反對拿輸出填充網站內容）→ 只存連結、標題、日期 | 1–1.5 h | 時間夠再接 |
| Qiita `tag:個人開発` | 中高（likes 中位數 1） | 約 200 篇／週，29% 連 repo | API v2（免金鑰 60 次／時） | 利用規約：不可轉貼 | 1–1.5 h | 時間夠再接 |
| 阮一峰周刊「工具」 | 中高（人工精選，混有爆紅大專案） | 12–18 個／週 | GitHub raw 檔 | CC BY-NC-ND 3.0 → 只取連結；只取標「投稿」的 | 0.5–1 h | 時間夠再接 |
| GeekNews Show GN（韓） | 高 | 約 70 篇／週 | RSS（不含原始連結） | robots 擋 Meta 的爬蟲 UA，絕不用 | 2 h | 可選 |
| Zenn、HelloGitHub、Gitee | 中／低 | — | RSS／raw／API | Zenn 禁止轉載；HelloGitHub CC BY-NC-ND | — | 之後 |
| Hatena Bookmark | 中 | 約 45 repo／週 | RSS | 規約禁止把資訊提供給第三方 | — | 之後（先取得書面同意） |
| 掘金、PTT、Dcard、velog、Habr、OSChina、iThome | 低 | — | 無官方 API 或條款不允許 | 掘金條款禁止機器人；PTT 擋 AI agent；Habr 禁止商用；velog 垃圾內容多 | — | **避開** |

---

## 2. 為什麼是這 5 條

| 評估角度 | GitHub search | 提交 | Show HN | Homebrew tap | PyPI |
|---|---|---|---|---|---|
| 新作品多 | 極多 | 靠作者與使用者 | 每週約 990 | 每月數千 | 每小時約 40 |
| 默默無聞 | 可用星數篩 | 自選 | 86% ≤3 分 | 星數中位數 1 | 用下載量篩 |
| 有使用訊號 | 星數、星數曲線 | 無 | 分數、留言 | 安裝數（含 CI） | 下載量 |
| 兩個 demo 類別 | 兩類都多 | 兩類 | 兩類約 75 篇／週 | CLI 為主 | 本地 AI 多 |
| 條款風險 | 低（只走 API，用途有解讀空間） | 低 | 低（只走 API） | 低（官方 JSON） | 低（RSS） |
| 一個人接上（最低版本） | 4 h | 2 h | 1.5 h | 2 h | 3 h |

前 3 條約 7.5 h：10/29 接 GitHub，10/30 接 Show HN，11/1 接提交入口（見 architecture.md H.2）。

---

## 3. 本 session 的限制（要在本機跑）

這個雲端 session 的 proxy 把 GitHub API 綁在 `ncchen99/pickfit`：`/search/repositories` 與其他 repo 的 `/repos/...` 回 403，GraphQL、codeload 也被擋（raw.githubusercontent.com 可用）。所以：
- 兩個類別在 GitHub 上的 7／14 天筆數**沒量到**；改名 repo 的 301 也沒實測。腳本 `spikes/ch_hosting_github.py` 已寫好，念誠用自己的 fine-grained PAT（不勾任何權限就能讀公開 repo）在本機跑約 3 分鐘。
- 發現管線要在本機或 Modal 跑。

---

## 4. 要避開的管道與原因

| 管道 | 原因 | 細節 |
|---|---|---|
| 爬 threads.com、facebook.com、instagram.com | robots.txt 與 [Automated Data Collection Terms](https://www.facebook.com/legal/automated_data_collection_terms) 要求書面許可 | [meta-platforms](notes/channels-meta-platforms.md) |
| Threads keyword search、Threads 登入讀貼文交給模型 | [允許用途](https://developers.facebook.com/documentation/development/permissions)不符；消費者 app 嚴格禁止 | 同上 |
| Reddit、Product Hunt、X、LinkedIn、Indie Hackers、Discord 抓取 | 要先核准／禁止商用／沒有免費讀取／沒有讀取權限／條款禁止 | [communities](notes/channels-communities.md) |
| Lobsters 自動抓取 | robots.txt 全擋、`ai-input=no` | 同上 |
| GitHub trending 頁、GitHub HTML | 沒有 API；屬 scraping | [hosting](notes/channels-hosting.md) |
| GH Archive、BigQuery、ClickHouse playground、OSS Insight、Changelog Nightly | 資料已失準或停更 | [curation](notes/channels-curation.md) |
| RSSHub | GitHub trending／search、Threads、HN、Product Hunt 路由都抓 HTML（讀過原始碼） | [integration](notes/channels-integration.md) |
| GitLab 大量輪詢、SourceHut、Gitee | 禁止大量收集／營利收集；未登入拿不到 | [hosting](notes/channels-hosting.md) |
| PyPI XML-RPC 新整合、pypistats 大量抓取、libraries.io | 官方說不要用；資料過舊 | [packages](notes/channels-packages.md) |
| ecosyste.ms（取得書面同意前） | Terms §9、§11(c) | 同上 |
| 掘金、PTT、Dcard、Habr、velog | 條款禁止機器人或商用；擋 AI agent；垃圾內容多 | [regional](notes/channels-regional.md) |
| Hatena（取得書面同意前） | 規約禁止把資訊提供給第三方 | 同上 |
| 在 GitHub Actions 裡跑爬取或處理提交 | hosted runner 只能做和本 repo 軟體專案相關的事 | [integration](notes/channels-integration.md) |
| 任何 Meta 爬蟲 User-Agent（`meta-externalagent` 等） | 很多網站專門擋 | — |

---

## 5. 怎麼有效率地大量整合（[notes/channels-integration.md](notes/channels-integration.md)）

### 5.1 主鍵與去重

| 層 | 例子 | 用途 |
|---|---|---|
| **GitHub 數字 repo ID**（最終主鍵） | `gh:523043277` | 改名、轉移都不變。實測 Show HN 7 天 271 個 repo 有 39 個（14%）改過名；ecosyste.ms、deps.dev 都不會把舊名導到新名，只有 GitHub API 的 301 可靠 |
| canonical key | `github.com/astral-sh/ruff`（全小寫，去 `.git`、`www`、尾斜線） | 解析出 ID 前的暫時 key；改名後舊值放進 `aliases` |
| 次要 key | `pkg:pypi/ruff`、`hn:50258513`、`threads:C8abc`、`web:docs.astral.sh/ruff` | 把套件、貼文、官網併到同一個候選 |
| slug | `ruff` | 收錄時給一次，永不改 |

- 合併用 union-find：任兩個 key 被同一筆證據連起來就併成同一個候選；同一專案同時出現在 Threads、HN、GitHub 時，每個來源留一筆 `sources`（出處、首次看見時間）。
- 套件 → repo：先看發布簽章 provenance（PyPI Trusted Publishing、npm `dist.attestations`），再看自填欄位（`project_urls`、`repository`、Homebrew `urls.head`）。PyPI 新專案 27／39 有 provenance，和自填欄位 0 衝突。
- fork、mirror、template 直接排除；monorepo 子目錄用 `repo#path`；共用主機的官網（`*.github.io`、`*.vercel.app`）要比到路徑才合併。
- spike：`spikes/ch_integration_normalize.py`（正規化 25／25 通過）、`spikes/ch_integration_merge.py`（冪等：重跑時 Show HN 新增 0、PyPI 只多 1 筆）。

### 5.2 增量抓取與排程

| 來源 | cursor | 頻率 |
|---|---|---|
| GitHub search | `created:`／`pushed:` 時段切片（每段 ≤1,000 筆）＋ `Link` 翻頁；請求序列化 | 每天 1–2 次 |
| Show HN | Algolia `created_at_i` | 每 1–3 小時 |
| PyPI RSS | ETag（實測回 304） | **每 20–30 分鐘**（RSS 只涵蓋約 1 小時） |
| Homebrew analytics | 和昨天的名單做差集；ETag | 每天 1 次 |

- 每個來源一個 cursor（`source`、`cursor`、`etag`、`last_success_at`），**整批成功寫入後才前進**。
- 排程：**黑客松期間用念誠本機 cron 跑發現**（GitHub API 在本機沒有本 session 的限制）；提交走事件觸發 Modal（`.spawn()`），不等排程，才做得到「幾分鐘內可被推薦」。之後要無人值守再搬到 Modal cron（Starter 有 5 個 cron）。GitHub Actions 只做「收錄檔有變 → 重建 MCP 索引」。Cloudflare Workers Free 每次只能發 50 個子請求，跑不動抓取。

### 5.3 統一候選格式與狀態機

```
discovered ─規則─► rejected（fork、archived、template、沒 README、不是可執行檔…）
    ├─只有官網或 Threads、沒 repo─► needs_info
    ▼
 triaged ─開放權重模型（不是軟體、不在兩個類別）─► rejected
    ▼
extracted（Muse Spark 抽出檔案草稿）
    ├─沙盒驗證成功─► verified ─► 給 slug、寫入 git 正本
    └─沙盒驗證失敗─► failed（可重試 1 次；仍失敗不收錄，原因回給提交者）
任何狀態 ─重複─► merged
```

候選放本機 SQLite，只有 `verified` 的寫成 JSON 進 git。每次轉換記一筆 `status_history`（時間、誰、原因），也是 demo 的 trace。JSON Schema 草案見筆記第 5 節；建議 brief 第 11 節補 `repo_id`、`aliases`、`packages`（purl）、`first_seen_at`。

### 5.4 先便宜、後昂貴的漏斗

以每天 3,000 筆候選估（GitHub、Show HN、PyPI、Homebrew）：

| 層 | 數量 | 做什麼 | 成本／天（估） |
|---|---|---|---|
| 0 收集、正規化、去重 | 3,000 → 2,600 | 程式；GitHub `/repos` 解析 | $0 |
| 1 規則初篩 | 2,600 → 約 500 | 沒 repo、fork、archived、template、不是可執行檔、不在兩個類別 | $0 |
| 2 開放權重初篩 | 500 → 約 150 | Muse Spark Open @ Baseten：是不是可用軟體、哪一類 | 約 $2（Baseten credits） |
| 3 抽取 | 150 → 約 140 | `muse-spark-1.3` 讀 README 等，填欄位 | $3.3–3.8 |
| 4 沙盒驗證 | **每天上限 30–50** | 驗證 agent＋Modal Sandbox；優先順序：提交的 > 兩類別高信心 > 其他 | $3.6–8.7 |

- 合計每天約 $9–15，6 天 Meta 部分約 $38–72，在 $150 credits 內。全部驗證會超支，所以**驗證一定要設每日上限**。
- 每層有每日上限與累計花費，由程式自己停（Meta 的 Spend Limit 只寄 email）。
- 所有成本都是估算（推理 token 未實測，兩類別篩選比例未量測）。

### 5.5 可以直接用的現成工具

| 工具 | 用不用 | 理由 |
|---|---|---|
| `gh` CLI、GitHub REST API | 用 | 官方 |
| `feedparser` 等 feed 函式庫 | 用 | PyPI、crates RSS |
| Scorecard CLI `--local` | 用（沙盒裡） | 不需 token |
| deps.dev API | 用（補資料） | 套件 ↔ repo provenance |
| ecosyste.ms | 寄信同意後 | 條款 |
| RSSHub、Huginn、changedetection.io | 不用 | RSSHub 多數相關路由抓 HTML；另兩個是網頁變更偵測，不適合 |
| GH Archive | 不用 | 資料已失準 |

### 5.6 提交入口

- **一條路、一個佇列**：MCP `submit_software` 與 GitHub Issue Form 共用。Issue Form 由 webhook 轉給 Modal 處理，不在 Actions 裡跑。
- 收什麼：GitHub repo、套件頁、HN 貼文、官網。Threads／X 貼文連結**選填、只用來嵌入**；只有 Threads 連結時回 `needs_info`，請補 repo 或官網。
- 怎麼確認是可用的軟體：連結能解析且存在 → 不是 fork／archived／template → 有安裝路徑 → 開放權重模型判斷 → 沙盒驗證成功。**驗證失敗不收錄**，原因回給提交者。
- 防灌水：同 repo 重複提交只多一筆 source、不加分；驗證佇列每日上限；MCP 限流；內容規則（排除違反第三方 ToS 的工具、醫療／政治／戰爭類）；每天人工看 failed 原因與 10% 的 verified；「作者提交」標記之後再做（例如請作者加一個 topic 證明身分）。
