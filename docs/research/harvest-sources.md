# 大量收集軟體資料：來源盤點與自動收集（harvest）

2026-11-19（台北）· 賽後階段。延續 [channels.md](channels.md) 的盤點（10 月底），這次的問題是：驗證管線已經全自動，但候選庫只有約 1,150 筆，而且幾乎都已經變成紀錄，watch 每小時能處理 20 筆，卻沒有東西可以餵。這份記錄新加的來源、各社群平台能不能用、以及 `pickfit harvest` 怎麼運作。

## 結論

| 來源 | 平台／類型 | 怎麼取 | 條款 | 狀態 |
|---|---|---|---|---|
| 官方 MCP Registry | MCP | `registry.modelcontextprotocol.io/v0.1/servers`，第一次全抓，之後用 `updated_since` | 官方文件明寫這個 API 就是給 aggregator 用的，建議約每小時同步一次 | **已接**（`mcp_registry`） |
| npm registry search | MCP、CLI、TUI | `registry.npmjs.org/-/v1/search`（`npm search` 用的同一支），依 keyword | 走 registry API，不碰 npmjs.com 網站 | **已接**（`npm`） |
| crates.io | CLI、TUI、MCP（Rust） | `/api/v1/crates`，依分類 `command-line-utilities` 與 keyword | 每秒最多一個請求、要帶 User-Agent | **已接**（`crates`） |
| Homebrew formulae | CLI（macOS、Linux） | `formulae.brew.sh/api/formula.json` 與 30 天安裝數 | BSD-2-Clause，安裝數只拿來排序 | **已接**（`homebrew`） |
| winget-pkgs | Windows | GitHub API 搜「New package」commit，再讀該套件的 locale manifest | MIT，另守 GitHub API 條款 | **已接**（`winget`），只收有 GitHub repo 的 |
| Awesome lists | MCP、CLI、TUI、自架、Linux／Mac／Windows 桌面、開源替代品、本地 AI | GitHub API 讀 README，只取 GitHub 連結 | 只取連結（事實），不取清單的說明文字 | **已接**（`awesome`，16 份清單） |
| GitHub 新進且漲得快的 repo | 全部 | search API：近 45 天建立、50 星以上，依星數排序，25 個 topic | 同既有 GitHub 管道 | **已接**（`github_rising`），取代被封鎖的 trending 頁 |
| Hacker News 全部 story | 全部 | Algolia API，連到 GitHub、20 分以上的 story。Show HN 連到網站的也收（交給 web lane） | 同既有 Show HN 管道 | **已接**（`hn`） |
| Bluesky | 社群 | 用帳號登入後呼叫 `app.bsky.feed.searchPosts`，只留附 GitHub 連結的貼文 | 開放的協定與 API。只存貼文 URI、連結、按讚數，不存文字 | **已寫好，要帳號**（`bluesky`） |
| X | 社群 | API v2 recent search（近 7 天），本地端再依按讚數篩 | 按次付費，每讀一則 US$0.005。只存貼文 id、連結、按讚數 | **已寫好，要開發者帳號與儲值**（`x`） |
| Product Hunt | 社群（SaaS 為主） | GraphQL API v2 | 「預設不可商用」，商用要寫信給 hello@producthunt.com | **先寫信取得同意**，同意前不接 |
| Reddit | 社群 | Data API | 任何存取都要先申請核准，商用另簽約 | **先申請**，核准前不接 |
| Instagram、Threads、Facebook | 社群 | 無 | Meta 的 Automated Data Collection Terms 禁止自動收集。hashtag API 要商家驗證、用途不符 | **不做** |
| PyPI 新專案 RSS | 本地 AI、CLI（Python） | RSS 只涵蓋約一小時，要每 20–30 分鐘輪詢 | 官方 RSS | 之後（要常駐排程） |
| V2EX、Qiita、阮一峰周刊 | 各地區社群 | 見 channels.md 1.6 節 | 只存連結 | 之後 |

第一次全量執行的結果在本文最後一節。

## 社群平台：為什麼 X、IG、Product Hunt 不能用「開個小帳號讓 agent 去逛」

最直覺的做法是註冊一個專用帳號，讓瀏覽器 agent 每天去刷動態、搜 hashtag、看留言區。這在三個平台上都違反條款，而且 pickfit 是要公開、要長期經營的服務，不能拿帳號被封、資料要下架的風險去換：

- **Instagram／Threads**：Meta 的 Automated Data Collection Terms 禁止未經書面同意用自動方式收集資料，用不用帳號都一樣，robots.txt 也擋。官方 API 的 hashtag 搜尋只給通過 App Review 的商家帳號，用途也限管理自己的品牌。另外，IG 上「留言 TOOL 私訊給你連結」這類貼文，工具本身通常也發在 GitHub、HN 或 X，從那些來源收就好。
- **X**：開發者條款禁止不透過 API 爬取。合法的路是 API。2026 年 2 月起新帳號沒有免費層，改按次付費，讀一則貼文 US$0.005，每月上限 300 萬則。`x` 來源每次執行預設最多讀 100 則（約 US$0.5），每天跑一次一個月約 US$15。X 網頁版的 `min_faves:200` 在 API 不能用，所以改成取回後依 `like_count` 篩（預設 20 以上）。
- **Product Hunt**：API 文件寫明預設不可商用，要用在商業服務得寫信取得同意。pickfit 不放廣告，但仍是對外的服務，所以照 [source-terms.md](../source-terms.md) 對 Flathub 安裝數的做法，由念誠寫信，拿到書面同意再接。

能用的社群來源是 **Bluesky**：協定與 API 開放，開發者大量在上面分享 GitHub 作品。用一個帳號的 app password 就能呼叫搜尋，免費。

## 需要念誠協助的帳號

| 帳號 | 用途 | 要放進 `.env` 的名稱 | 費用 |
|---|---|---|---|
| Bluesky 帳號＋ app password（設定 → Privacy and security → App passwords） | `bluesky` 來源搜尋貼文 | `BSKY_HANDLE`、`BSKY_APP_PASSWORD` | 免費 |
| X 開發者帳號（developer.x.com），建一個 App、儲值、拿 Bearer token | `x` 來源 | `X_BEARER_TOKEN` | 每讀一則 US$0.005。建議先儲值 US$10–20，並在後台設花費上限 |
| （選）寫信給 Product Hunt | 取得商用同意 | 之後放 `PRODUCTHUNT_TOKEN` | 免費 |

不需要 Instagram 或 Threads 帳號。

## `pickfit harvest` 怎麼運作

程式在 `pickfit/harvest/`，資料存在 `runs/harvest.db`（不進 repo）。

1. `pickfit harvest run`：依序執行各來源。每個來源產生「hit」（某個來源提到某個軟體），整理成「lead」，也就是一個 GitHub repo（`gh:owner/name`）或一個網站（`web:https://…`）一筆，同一個軟體被幾個來源提到，就有幾筆來源紀錄。只存事實，包括來源裡的 id、回到來源的連結、短標題、一個熱度數字（星數、分數、下載數、安裝數、按讚數），不存貼文內容。某個來源出錯時記下錯誤，繼續跑下一個。
2. 跑完後，已經有紀錄（`data/software`）或已在候選庫（`runs/pipeline.db`）的 lead 標成 `known`。
3. 排序：先看類型（MCP、CLI、TUI、網頁優先，對應 11/15 的方針），再加上 Linux／網頁加分、熱度取 log、每多一個來源加一分。
4. `pickfit harvest top`／`export`：看排序最前面的新 lead，或匯出成 JSON lines。
5. `pickfit harvest feed -n N --apply`：把最前面的 N 筆寫進 D1 的 `submissions`（`status = 'queued'`，note 寫 `harvest: <來源>`），之後由 watch 照一般投稿的流程讀取、驗證、寫紀錄。每小時最多用到 `SUBMIT_HOURLY_CAP` 減 5，留 5 筆給真人投稿。不加 `--apply` 只列出會送哪些，不寫任何東西。

feed 會花錢：每一筆進 watch 都要跑抽取與沙盒驗證（Anthropic API 與 Modal）。所以 feed 是分開的指令，要明確加 `--apply` 才會寫入。

## 第一次全量執行（2026-11-19）

在這台 Mac 跑 `pickfit harvest run --limit 20000`，約 20 分鐘，沒有任何模型呼叫，也沒有寫 D1。

| 來源 | 提到的軟體（hit） | lead | 其中新的 | 請求數 |
|---|---:|---:|---:|---:|
| MCP Registry | 6,397 | 5,445 | 5,432 | 203 |
| npm | 17,688 | 14,388 | 14,286 | 104 |
| crates.io | 3,937 | 2,531 | 2,492 | 41 |
| Homebrew formulae | 6,012 | 5,891 | 5,786 | 2 |
| winget（近 7 天新套件） | 168 | 167 | 166 | 294 |
| Awesome lists（15 份讀得到） | 9,377 | 7,985 | 7,792 | 16 |
| GitHub 新進且漲得快 | 1,619 | 1,036 | 1,005 | 25 |
| HN（近 7 天、20 分以上） | 64 | 64 | 63 | 7 |

合併後共 35,612 個 lead，370 個已經有紀錄或在候選庫，**新的 35,242 個**（候選庫原本約 1,150 筆）。依類型：MCP 16,564、CLI 9,799、TUI 4,641、桌面 App 2,270、自架網頁 1,097、網頁 37、本地 AI 136、未知 698。`Awesome-Windows/Awesome` 讀不到 README，下次換別份 Windows 清單。

排序一開始直接比原始數字，npm 和 crates 的下載數上百萬，結果前幾名都是函式庫（`typescript-sdk`、`crossterm`）。改成每個來源各自算百分位，再看有幾個來源都提到、只出現在套件 registry 的扣分之後，前面變成 `ast-grep`、`broot`、`csvlens`、`television`、Notion／Slack／Kubernetes 的 MCP server 這類真正的工具。

注意：lead 沒有經過任何篩選，函式庫、需要帳號的服務、內容有疑慮的專案都還在裡面。feed 送進 watch 之後才會照既有的規則、Haiku 初篩與沙盒驗證處理，所以每筆 feed 都會花一點錢。

## 排程

`deploy/watch/` 多了兩組 systemd unit，裝在跑 watch 的那台機器上：

- `pickfit-harvest.timer`：每天 03:30 UTC 跑一次 `pickfit harvest run`，結果寫在 `runs/harvest/last-run.json`。
- `pickfit-harvest-feed.timer`：每小時跑一次 `pickfit harvest feed -n $HARVEST_FEED_PER_HOUR --apply`（預設 10 筆）。

`bootstrap.sh` 會安裝這些 unit，但不會啟用。要啟用時在機器上執行 `systemctl enable --now pickfit-harvest.timer`，確定要開始花錢時再啟用 `pickfit-harvest-feed.timer`。花費仍受 `PICKFIT_PIPELINE_DAILY_CAP_USD` 管。
