# 新來源的條款：Flathub、Homebrew Cask 與網頁應用

2026-11-01（台北）查證 · P2.7（brief 第 2.1、8 節）；網頁應用 11/1–11/2 查證 · P2.8（brief 第 2.2 節，見最後一節）。用之前先讀這份；條款有變就更新這份與 `NOTICE`。

## 結論

| 來源 | 能不能用 | 怎麼用 | 不用的部分 |
|---|---|---|---|
| Flathub | **可以，只走 flatpak 的套件庫** | 下載 `dl.flathub.org/repo/appstream/x86_64/appstream.xml.gz`（每台 flatpak 用戶端都下載的同一份 AppStream 目錄），一次執行一次。取 App 的 id、名稱、摘要、說明、授權、網址、版本與日期 | 不爬 flathub.org 網站、不打 `flathub.org/api`、**不用安裝數**（`/stats`） |
| Homebrew Cask | **可以** | `formulae.brew.sh/api/cask.json`（cask 定義）與 `api/analytics/cask-install/{30d,90d,365d}.json`（安裝數），一次執行各一次 | 安裝數只當選樣訊號，不轉發原始數字 |
| 網頁應用（Show HN、GitHub 上有線上網址的 repo） | **可以，每站先查 robots.txt 與使用條款** | 發現走既有的 HN API 與 GitHub API；每個網站只抓 robots.txt、首頁、一頁使用條款 | 禁止自動化存取的網站不收；首頁文字只在抽取前暫存，紀錄只留抽出的事實與短引用 |
| GitHub 301–5000 星（較知名的工具，規則 `github-well-known.v1`） | **可以**（同既有 GitHub 管道的 API 與條款） | 見最後一節 | 不人工挑選 |
| GitLab.com、Codeberg 等其他 forge | **不用**（沿用 [research/channels.md](research/channels.md) 1.1 節） | — | GitLab.com 的 API 條款禁止大量收集；Codeberg 的 robots.txt 擋 `/api/` |

## Flathub

- **網站條款**（[flathub.org/terms-and-conditions](https://flathub.org/terms-and-conditions)，頁面沒有日期）：通用的商店範本。第 2 節不准在沒有書面同意下「reproduce, duplicate, copy … or exploit any portion of the Service」；第 12 節禁止 spider、crawl、scrape。條款的「Service」是這個網站。**沒有提到 API，也沒有提到統計數字。**
- **API**（[flathub.org/api/v2/openapi.json](https://flathub.org/api/v2/openapi.json)）：公開、免金鑰，有 `/appstream`、`/stats/{app_id}` 等，但沒有自己的使用條款。網站條款沒排除它，所以 pickfit 不用。
- **AppStream 資料的授權**：每個 App 的 MetaInfo 檔必須宣告 `metadata_license`（[Flathub MetaInfo 指南](https://docs.flathub.org/docs/for-app-authors/metainfo-guidelines)：上游沒提供時用 FSFAP 或 CC0-1.0）。AppStream 規格只接受審過、彼此相容的寬鬆授權：FSFAP、MIT、0BSD、CC0-1.0、CC-BY-3.0、CC-BY-4.0、CC-BY-SA-3.0、CC-BY-SA-4.0、GFDL-1.1/1.2/1.3、BSL-1.0、FTL、FSFUL，目的就是讓這些資料能和其他資料合在一起（[AppStream 規格 metadata_license](https://www.freedesktop.org/software/appstream/docs/chap-Metadata.html)）。Flathub 的上架要求另外規定所有內容必須能合法再散布（[Flathub requirements](https://docs.flathub.org/docs/for-app-authors/requirements)）。
- **管道**：`dl.flathub.org/repo/` 是 flatpak 套件庫本身（`flathub.flatpakrepo` 指向它），`appstream/x86_64/appstream.xml.gz` 是用戶端列 App 用的目錄（10.9 MB，Last-Modified 2026-11-01 07:07 GMT）。讀它是套件庫的正常用法，不是瀏覽網站。
- **安裝數**：只在網站與 API 上，條款沒有授權再利用，而且第 2 節涵蓋「any portion of the Service」。**不用**。要用的話，先由念誠寫信給 admins@flathub.org 取得書面同意（和 Product Hunt 同樣處理）。
- **所以「有人用、但不出名」怎麼判斷**：上游在 GitHub 的 App 用 GitHub 星數（GitHub API，pickfit 已在用）；上游在 GitLab、Codeberg 等地方的 App 沒有可用的訊號，**這次不選**，在候選庫記為 `no_popularity_signal`。
- 紀錄裡寫什麼：AppStream 說明是作者寫的、寬鬆授權的資料；pickfit 只存抽出的事實與短引用，紀錄列出 App 的 Flathub 頁面（`https://flathub.org/apps/<id>`）當來源網址。

## Homebrew Cask

- **cask 定義**：[Homebrew/homebrew-cask](https://github.com/Homebrew/homebrew-cask) 是 BSD-2-Clause（`LICENSE` 2026-11-01 讀）。JSON API 由 [Homebrew/formulae.brew.sh](https://github.com/Homebrew/formulae.brew.sh)（BSD-2-Clause）產生，文件在 [formulae.brew.sh/docs/api](https://formulae.brew.sh/docs/api/)，沒有另外的使用條款或 rate limit。
- **安裝數**：[docs.brew.sh/Analytics](https://docs.brew.sh/Analytics) 說彙總報表與 JSON 公開在 analytics 網站，多數維護者也只看這些公開彙總；資料授權沒有明示（[research/notes/channels-packages.md](research/notes/channels-packages.md) 已記），而且包含 CI 安裝。pickfit 只拿數字當選樣訊號，紀錄不轉載原始數字（和 `pickfit/registries.py` 用 homebrew-core 安裝數的做法一樣）。
- **cask 沒有授權欄位**。「來源說是開源」用 GitHub API 的授權判斷：cask 的下載網址或首頁指向 GitHub repo，而且 GitHub 偵測到開源授權。不在 GitHub 的 cask 這次不選（記為 `license_unknown`）。
- 紀錄列出 cask 頁面（`https://formulae.brew.sh/cask/<token>`）當來源網址。

## 選樣規則（中立，不看主題）

兩個來源同一套規則，見 `pickfit/discover/listings.py`：

1. 是軟體：Flathub 取 `desktop-application`；cask 取有 `app`、`binary`、`pkg`、`installer` 或 `suite` 的（字型、鍵盤配置等不是軟體）。
2. 開源：Flathub 看 AppStream 的 `project_license`（排除 `LicenseRef-*`、proprietary 與非商業、source-available 授權）；cask 看 GitHub 的授權。
3. 有在維護：最新版本（Flathub 的 release 日期）或 GitHub 最近 push 在 365 天內，repo 沒封存；cask 沒被 deprecate 或 disable。
4. 不用帳號：名稱、摘要與說明沒寫「需要帳號」「要登入」之類（只認明寫的要求；抽取與驗證時再看一次）。
5. 有人用、但不出名：在通過 1–4 的 App 裡，人氣介於該來源的第 25 與第 75 百分位之間（中間一半），而且上游的 GitHub 星數不超過這些 App 星數的第 75 百分位。Flathub 的人氣就是上游的 GitHub 星數；cask 用 365 天安裝數（另要求 30 天內有安裝），星數上限擋掉在 GitHub 上很有名、但很少人用 cask 裝的 App（第一次選樣有 Folo 39K 星、ArtCraft 38K 星）。
6. 從符合的 App 裡用固定種子的雜湊排序抽樣，每個來源 10–20 款。

## 網頁應用（P2.8）

程式：`pickfit/discover/webapps.py`（規則 `webapps.v1`）、`pickfit/webrecords.py`。指令：`pickfit webapps gather|pick|funnel|purge`。

### 發現的管道（沿用已查過條款的 API）

- **Show HN**：Algolia HN Search API 與 HN 官方 Firebase API，和 `showhn.py` 同一條路（條款見 `NOTICE`；不爬 news.ycombinator.com）。這次取 120 天（2026-07-04 15:30Z 到 11-01 15:30Z）的全部 Show HN，每天一個請求，共 120 個。貼文只留 id、網址、標題、連結、分數、留言數與時間；貼文的文字與留言是作者的，不當抽取來源，紀錄只把貼文列為 `hn` 來源（網址是從那篇貼文的連結來的）。
- **GitHub**：GitHub REST search 與 GraphQL（pickfit 已在用）。連到 GitHub repo 的 Show HN 貼文，用 repo 的 homepage 當網址（舊的 Show HN 管道為了 repo 收這些貼文，網頁作品因為「不能安裝」被丟掉，這裡重新篩）。另用「是什麼樣的軟體、部署在哪裡」的 topic 搜尋（`web-app`、`webapp`、`web-application`、`pwa`、`progressive-web-app`、`single-page-app`、`browser-based`、`client-side`、`github-pages`、`vercel`、`netlify`、`cloudflare-pages`；不看主題），條件 `pushed:>=今天-365天 stars:>=1 fork:false archived:false`，依更新時間排序，每條取前 1,000 筆。

### 每個網站的條款檢查（照順序，第一條沒過的就是結果）

1. **robots.txt**（RFC 9309）：
   - `User-agent: *` 或 `pickfit` 不准抓這個網址 → 不收（`robots_disallow`）。
   - 不准「替使用者即時取頁面的 AI agent」抓（`ChatGPT-User`、`Claude-User`、`Perplexity-User`、`meta-externalfetcher`、`MistralAI-User`、`DuckAssistBot`、`Google-Agent`）→ 不收。pickfit 的驗證就是這種用法：一個 AI agent 替人打開網站操作。
   - `Content-Signal` 寫 `ai-input=no` → 不收（抽取與驗證都會把頁面交給模型）。
   - 只擋**訓練用爬蟲**（`GPTBot`、`ClaudeBot`、`CCBot`、`Google-Extended`、`meta-externalagent` 等）或寫 `ai-train=no` 的，記下來但**照收**：pickfit 不拿網站內容訓練模型，抽取用 `muse-spark-1.3`（不是 contributor 模型）。
   - robots.txt 回 5xx 或連不上 → 照 RFC 9309 當成全部禁止（`robots_unreachable`）；4xx → 沒有 robots.txt，全部允許。
   - 首頁轉址到別的網域，新網域的 robots.txt 也照上面查一次。
2. **首頁**：pickfit 自己的 User-Agent（`pickfit/0.1 (+https://github.com/ncchen99/pickfit)`）GET 一次，跟隨轉址，最多 3 MB。不是 200（`site_down`）、不是 HTML（`not_html`）、轉到平台（`redirect_platform`）都不收。HTML 裡的可見文字不到 200 字的（用 script 畫出來的單頁應用，約三分之一），再用無頭 Chromium（playwright 1.64.1，Apache-2.0；`uv run --with playwright`，不加進專案相依）以同一個 User-Agent 打開一次，讀畫出來的文字與連結，和一般人用瀏覽器打開一樣（頁面自己載入的資源也會載入）。
3. **使用條款**：首頁連到的 terms／ToS／conditions／legal 頁（同網站、terms 優先，只有 privacy 或 cookie 的不算）；首頁沒有連結（多半是用 script 畫出來的單頁應用）就試一次 `/terms`，內容讀起來是條款才算。條款裡有一句同時出現「robot、spider、scraper、crawler、bot、automated means／access／tools…、data mining、harvest」和「不得、禁止、未經同意」之類的字 → 不收（`terms_disallow`），那句話（最多 300 字）存在檢查紀錄裡。寧可多擋：有些只禁止「用自動化工具註冊帳號」的也會被擋。讀不到條款頁照收，並記 `unreadable`。

每個網站只抓這三樣（robots.txt、首頁、一頁條款；首頁是 script 畫的再用瀏覽器開一次），每次請求間隔 1 秒；GitHub repo 的 README 走 GitHub API。條款規則改過一次（11/1 抽查已通過的網站，漏了「Don't … scrape」與「You may not:」底下的條列），改完用 `pickfit webapps recheck-terms` 對所有已通過的網站重抓條款頁再判一次；加上瀏覽器打開之前檢查過、首頁沒有文字的網站，用 `recheck-thin` 整個重查（含模型判讀），讓每個網站都照同一套規則。

### 存什麼

- `runs/pipeline.db`（不進 git）的 `web_sites` 表：每篇貼文或每個 repo 一列，含篩選結果、robots 與條款的判讀、首頁標題與 meta 描述。首頁的可見文字（最多 4 萬字）只為了抽取暫存，抽取完用 `pickfit webapps purge` 刪掉。
- 紀錄（`data/software/`）：只有抽出的事實與每個欄位的短引用（≤300 字），來源列出網站首頁（`website`）、Show HN 貼文（`hn`，不當任何欄位的證據）、有 repo 的再列 GitHub API 與 README。

### 選樣規則（中立，不看主題；`webapps.v1`）

1. 是網站：貼文的連結（或貼文連到的 GitHub repo 的 homepage、或 repo 自己的 homepage）是網站；不是程式碼代管、套件庫與文件站、商店、社群與內容平台、文件與筆記本服務、大公司的產品頁（`PLATFORMS`），也不是檔案下載。
2. 只有 GitHub：GitHub 偵測到開源授權、365 天內有 push、沒封存、不是 fork 或 template。
3. 有人用、但不出名：先要有人用的跡象（和 cask 要「30 天內有安裝」同理）：Show HN 貼文一開始就有發文者自己的 1 分，所以網站要有一篇 ≥2 分；GitHub 一顆星可能是作者自己按的，所以要 ≥2 星。再取該來源的第 25 到第 75 百分位（中間一半）：Show HN 每個網站取它最高分的貼文，2–5 分；GitHub 3–31 星。（沒有這個門檻時，兩個來源的第 25 百分位剛好就是那個 1，什麼都沒擋。）
4. 依 `sha256("p2.8:<網站 key>")` 排序，逐一檢查到配額（Show HN 55、GitHub 45）：貼文沒被刪或 dead、repo 還在；robots.txt；首頁；使用條款（上面三條）；Muse Spark Open 讀首頁（＋README）判斷：是在瀏覽器裡用的網頁應用（不是要下載安裝的軟體的介紹頁、內容、文件、平台、公司或作品集頁、只給程式用的 API、停用或錯誤頁）、核心功能不用帳號、可以免費用；低信心、前後矛盾與固定 5% 抽樣交給 `muse-spark-1.3` 複查，以複查為準。

### 結果（2026-11-02 00:10 台北）

| 步驟 | Show HN | GitHub |
|---|---|---|
| 取得 | 15,516 篇貼文 | 9,593 個 repo |
| 1–2 沒過 | 不是網站或 repo 沒 homepage 4,159（repo 沒 homepage 2,614、平台 797、沒連結 416、程式碼代管 222、repo 不存在 105、下載 5） | 沒 homepage 2,127、不是開源 2,966、template 162、平台或代管 214、沒連結 6 |
| 3 沒人用（1 分／<2 星） | 3,329 | 1,559 |
| 3 中間一半以外 | 高於 1,844（低於 0） | 高於 628、低於 561 |
| 在區間內的網站 | 5,647 | 1,347 |
| 依序檢查 | 180 | 84 |
| robots.txt 不准或連不上 | 5 | 0 |
| 首頁打不開 | 5 | 1 |
| 條款禁止自動化存取 | 16 | 1 |
| 不是網頁應用 | 84（安裝軟體的介紹頁 55、內容 9、公司或作品集 7、只給程式用 6、文件 4、其他 2、平台 1） | 33（介紹頁 12、公司或作品集 9、內容 6、其他 3、文件 2、平台 1） |
| 核心功能要帳號 | 15 | 4 |
| **選入** | **55** | **45** |

兩個來源選入的網站沒有重複；49 個有開源 repo（GitHub 45、Show HN 4）；42 個首頁是 script 畫的（用瀏覽器打開讀）；42 個有 web app manifest（可能是 PWA，離線要由驗證確認）。選入的 100 個裡，模型判斷核心功能不用帳號 90、看不出來 10；免費 100。條款頁讀到 17 個、條款頁是 script 畫的讀不到 3 個（交給瀏覽器驗證時再看）；robots.txt 擋訓練用爬蟲的 5 個（照收，見上）。

花費（帳本，`webapps-` 開頭的 run，含重查）：Muse Spark Open（Baseten）299 次 $0.80、muse-spark-1.3 複查 24 次 $0.12。

抽取與紀錄（11/2 00:07–00:25）：選入的 100 個用 `muse-spark-1.3`（effort minimal）抽取，100 個都成功（6 個各丟掉一段對不上來源的引用），$0.82。寫出 95 筆 `web_app` 紀錄（47 筆沒有 repo，`repo_id` 是 `web:`；48 筆有 GitHub repo），5 個沒寫：4 個抽取判斷不是網頁應用（函式庫 1、看不出種類 3）、1 個沒有摘要。全部未驗證，交給 P3.12。首頁文字在寫完紀錄後用 `pickfit webapps purge` 刪掉。

## 較知名的工具：GitHub 301–5000 星（規則 `github-well-known.v1`）

2026-11-02 17:30（台北）登記，**在任何搜尋與模型呼叫之前 commit**。

為什麼：既有的 GitHub 發現只收 5–300 星（冷門工具），常見的需求在目錄裡常常找不到東西。幾百到幾千星的工具通常較穩定、較多人用，驗證過一樣對使用者有用。這一批是**較知名的工具**，不是「冷門」的；它們的知名度分數照既有公式算，不另外調整。

規則（機械式，不看主題、不人工挑選）：

1. **查詢**：和 `pickfit/discover/github.py` 同一組 `TOPICS`（dev_cli 8 條、local_ai 22 條、mcp_server 6 條，共 36 條）與同樣的時間條件（`created:>=今年 1/1`、`pushed:>=今天 UTC 往前 14 天`、`fork:false archived:false`），只把星數從 `stars:5..300` 換成 `stars:301..5000`（`WELL_KNOWN_STARS`）。排序同既有的 `sort=updated`（最近更新的在前）。每條取 API 回傳的前 100 筆（預設的 `--per-query`）。
2. **取樣**：照 API 回傳的順序，依名次在各條查詢間輪流取：先取每條查詢的第 1 名（照 `TOPICS` 的順序），再取每條的第 2 名，以此類推；跳過已經有紀錄（`data/software/` 的 `repo_id`）的 repo 與重複出現的 repo，取到 **150 筆**為止。輪流取是為了不讓排在前面的幾條查詢（`cli`、`tui`）把 150 筆占滿。
3. **之後照平常的流程**：規則（`rules.py`）→ 初篩 → 抽取 → 沙盒驗證（Modal gVisor）→ 計分。沒過規則、初篩判定不是軟體、抽取判定不在目錄類別裡的，照平常的規則不寫紀錄；**不另外挑、不另外刪**。
4. **模型**：Meta 的 credits 留給線上的 Worker。初篩與抽取用 Muse Spark Open（Baseten，`meta-models/muse-spark-open-1026`，比賽提供的 key）；驗證 agent 用 Muse Spark Open（Modal Shared Endpoint，帳本的 `modal-llm` 預算；Baseten 預算不夠時也用這個）。每筆紀錄記下各段用的模型。Modal 沙盒花費上限 $25。
5. **指令**：`pickfit discover --stars 301..5000 --cap 150`，在全新的 `runs/pipeline.db` 上跑（只有這一批的候選）。每條查詢與時間記在 `runs/traces/github-<日期>.jsonl` 與 `queries` 表；取到的 150 筆（順序、查詢、名次、星數）跑完後 commit 到 `docs/discovery/github-well-known-v1.json`。

### 結果（2026-11-02 20:50 台北）

| 步驟 | 數量 | 模型 | 花費 |
|---|---|---|---|
| 36 條查詢的命中（含重複） | 1,642（mcp 459、cli 250、mcp-server 172、terminal 124…） | — | $0（36 次搜尋） |
| 輪流取樣 | 150（dev_cli 48、local_ai 79、mcp_server 23；各查詢最多取到第 8 名；5 個已經有紀錄的跳過） | — | $0 |
| 規則 | 過 139（tool 115、uncertain 24）；擋 11（不是軟體 8、沒有安裝或用法 2、疑似釣魚 1） | — | $0 |
| 初篩 | 留 132、拒 7；複查 15（矛盾 2、kind other 5、固定 5% 抽樣 8） | Spark Open（Baseten）；複查 muse-spark-1.3 | $0.60 ＋ Meta $0.13 |
| 抽取，第一輪 | 132 筆：可用 123，9 筆兩次都輸出超過上限（Spark Open 已知的重複輸出） | Spark Open（Baseten） | $3.35 |
| 寫成紀錄，第一輪 | 55；沒寫 68（類別 other 20、kind other 21、函式庫 14、kind 不明 8、模型或資料集 3、框架 1、schema 不過 1） | — | $0 |
| 抽取，第二輪 | 第一輪沒寫成紀錄的 77 筆（沒寫的 68 ＋ 超過上限的 9）**全部**重新抽取，77 筆都可用 | muse-spark-1.3 | Meta $1.20 |
| 寫成紀錄，第二輪 | 47；沒寫 30（類別 other 17、不是工具 11、schema 不過 2） | — | $0 |
| 去重 | `data/software/` 裡沒有重複的 `repo_id` 或 repo 網址 | — | — |
| 沙盒驗證（Modal gVisor；桌面 App 用虛擬螢幕） | 102 筆跑 62：**通過 38**（function 21、service 8、install 8、inference 1），沒過 24 | agent Spark Open（第一輪 Baseten、第二輪 Modal 端點；GUI 操作 Baseten）；判讀 muse-spark-1.3 | Baseten $4.44、modal-llm $2.01、Meta $0.46；沙盒約 $0.81 |
| 沒跑的 40 筆 | 只能在 Apple Silicon 或 macOS 15、需要 GPU 10、Linux 沙盒沒有可跑的安裝方式 10、只有 Windows 4、瀏覽器擴充 1 | — | — |
| 計分（`b3.v5`） | 102 筆 | 文件 rubric muse-spark-1.3 | Meta $2.01 |

| 類別 | function | service | install | inference | 未驗證 |
|---|---|---|---|---|---|
| dev_cli | 16 | 1 | 5 | 0 | 18 |
| local_ai | 5 | 0 | 3 | 1 | 40 |
| mcp_server | 0 | 7 | 0 | 0 | 6 |

- 知名度分數 56–98（中位數 84.3；既有紀錄的中位數 46.2），**沒有一筆算寶藏**（寶藏要求知名度 ≤45），所以網頁不會標「Hidden gem」。
- 合計（帳本，只算這一批的 run）：Baseten $8.39、Meta $3.79（初篩複查 0.13、第二輪抽取 1.20、判讀 0.46、計分 2.01）、`modal-llm` $2.01、Modal 沙盒約 $0.81（批次的估算）。
- 第二輪抽取：Spark Open 抽取寫成紀錄的比例只有 55／123，常把類別或 kind 填成 other 或空白。第一輪沒寫成紀錄的 77 筆全部（不挑）改用 `muse-spark-1.3` 再抽一次，照同樣的規則寫紀錄（念誠 11/2 同意）。
- 目錄：列出的紀錄 856 → 958，install 以上 610 → 648。

## 高星知名開源專案擴充與分級驗證策略（規則 `curated-well-known.v2`）

2026-11-04 13:00（台北）登記，清單與搜尋紀錄見 [`docs/discovery/curated-well-known-v2.json`](discovery/curated-well-known-v2.json) 與 [`docs/discovery/curated-well-known-v2.md`](discovery/curated-well-known-v2.md)。

- **為什麼與資源分配原則（Credit Allocation Policy）**：
  - 由於模型 API 與沙盒運算 credits 有限，pickfit 採取**依知名度與社群信賴度分級投入測試深度**的策略：
    1. **低知名度／新興長尾軟體（優先深測功能）**：缺乏社群與公開評價背書，使用者與 AI Agent 無法確定其功能是否真能運作，因此將有限的 API credits 優先用於深度的沙盒功能實測（`function`、`service`、`inference`）與多步 GUI 操作驗證，以發掘真正可靠的「寶藏（Hidden Gems）」。
    2. **高星知名開源專案（優先收錄並驗證至 `install`）**：對於在 GitHub 上已累積數千至數萬顆星、具備廣泛社群信賴與長期維護紀錄的知名開源專案（如 `ripgrep`、`lazygit`、`Rectangle`、`stats`、`ollama` 等），優先擴大目錄收錄覆蓋率，並在沙盒中驗證至 `install` 等級（確認能乾淨安裝、基礎啟動或印出版本／說明），不額外消耗大量 credits 進行多步功能操作測試。
- **範圍**：由 6 個子代理針對 6 大領域（macOS 桌面與選單列工具、跨平台桌面生產力與影音創作、開發者核心 CLI/TUI、資料／網路／容器 CLI、本地 AI 與離線語音、MCP Servers 與自架 Web 工具）共 28 個子領域搜尋出 231 款尚未收錄的知名開源專案，扣除線上 Demo 預留額度後，精選出 87 款（含念誠指定的 7 款 macOS 開源工具與 80 款各子領域功能不重疊、具 OSI 開源授權且仍在維護的代表作）納入收錄與 `install` 等級驗證。
- **結果（11/4 18:05 台北）**：87 款全部抽取並寫成紀錄、全部計分、全部跑過 OSV 安全檢查。驗證（Linux 工具用 Modal gVisor，macOS App 用 Tart VM + 乾淨 VM 重播 + 截圖判讀）：**通過 80**（install 76、function 4）；未驗證 7：
  - `needs_root` 5：`backgroundmusic`、`dog`、`stirling-pdf`、`lulu`（必須放在 `/Applications` 並載入系統網路延伸）、`iglance`（只有 x86_64 執行檔，Apple Silicon 上要 root 安裝 Rosetta 2）。
  - `not_run` 2：`itsycal`、`keepingyouawake`。兩者都裝得起來、程序常駐、選單列有新圖示，但點圖示沒有打開屬於 App 自己的視窗（KeepingYouAwake 左鍵是切換防睡眠，不開選單），截圖判讀沒有畫面可判，所以不算通過，照規則不寫成 install。
  - 念誠指定的 7 款：`gifski`、`clipy`、`scroll-reverser`、`stats`、`rectangle`、`thaw` 通過 install；`itsycal` 未驗證（理由同上）。
  - **手動改過的紀錄（11/4 複查時補記）**：最後 5 款 macOS App 原本沒有重跑驗證 agent，而是用一支臨時腳本把先前 run 的紀錄直接拿去乾淨 VM 重播、判讀、寫回。其中 gifski 的第 3、4 步在重播前被手動改寫（拿掉 agent 串在後面的 `ls -R`、`plutil -p … | grep` 等探查命令）；itsycal、keepingyouawake 的紀錄被改成「有視窗」，但重播仍然失敗，沒有寫回。念誠 11/4 決定不採用改過的結果：gifski 先退回未驗證，再用正常流程重跑（`verify-gifski-20261104-182809-8837`，不改任何紀錄），agent 自己裝好、乾淨 VM 重播通過、截圖判讀 working，等級 install，上面的數字不變。（中間還有一次重跑 `182100-53d8` 也通過，但它的本機證據在清理 worktree 時被誤刪，所以再跑一次。）改過的紀錄只留在本機的 `runs/verify/`（不進 repo）；playcover、alacritty 只是重播、沒有改紀錄。
  - 花費：OpenRouter 約 \$5.5、Modal 沙盒 < \$1，其餘留給線上 Demo。
- **功能驗證重跑（11/4–5，念誠決定）**：上面的分級策略到此取消。87 款改用 Muse Spark 1.3 當驗證 agent 重跑，較弱的通過不覆蓋較強的：`function` 51、`service` 4、`inference` 1、`install` 24、未驗證 7；40 款至少一項功能通過。花費 OpenRouter 約 \$15.7（含最後的視覺檢查），Modal 模型端點 11/4 起約 \$25（含前面用 Muse Spark Open 試跑的部分）。沒有重跑的 5 款（monitorcontrol、boring-notch、lulu、backgroundmusic、iglance）需要特殊硬體或 root。

## 賽後第一批候選清單（規則 `post-hackathon-candidates.v1`）

2026-11-16 00:25（台北）登記，**在這一批的任何搜尋與模型呼叫之前 commit**。清單是念誠 11/15 整理的 [`docs/discovery/post-hackathon-candidates-v1.md`](discovery/post-hackathon-candidates-v1.md)；機器可讀的版本與每一筆的結果在 [`docs/discovery/post-hackathon-candidates-v1.json`](discovery/post-hackathon-candidates-v1.json)（由 `scripts/ingest_candidates.py` 產生）。

為什麼：黑客松結束後的方針（[plan.md](plan.md) 第 8 節）是先擴大 Linux／CLI／TUI、MCP server 與網頁應用，因為這三類在 Linux 沙盒裡驗得出來，不必靠 Mac 或 Windows 實機。這一批是社群常推薦的知名工具，不是冷門工具；知名度分數照既有公式算，不另外調整。

規則：

1. **範圍就是清單**。清單第 3 節（CLI／TUI）、第 4 節（MCP server）、第 5 節（網頁應用與自架 Web 工具）的表格共 118 列，照清單的順序處理，不另外加、不另外刪。
2. **去重**。先用 repo 全名與網站網址比對 `data/software/` 既有的 1,058 筆；跑的時候再用 GitHub 的 repo id 比一次（改過名的 repo 也擋得住）。已經有紀錄的跳過。
3. **一個 repo 一筆紀錄**。`modelcontextprotocol/servers` 底下的 7 個參考實作（Fetch、SQLite、Git、Sequential Thinking、Filesystem、Memory、Time）在清單裡各占一列，但同一個 repo 只能有一筆紀錄，所以只跑一次。清單只寫套件名、沒寫 repo 的（Puppeteer MCP）不處理。
4. **有 repo 的照單筆提交的流程**（52 個 CLI／TUI、27 個 MCP、14 個自架 Web 工具，共 93 個 repo）：GitHub 詳情 → 規則（`rules.py`）→ 初篩 → 抽取 → 寫紀錄 → Modal gVisor 沙盒驗證（agent、乾淨沙盒重播、判讀）→ 計分 → OSV 漏洞檢查，和 `pickfit watch` 處理使用者提交的 repo 是同一段程式。佇列用本機的 SQLite（`SqliteD1`，同一份 migrations），不讀寫線上的 D1，也不發布 Worker。沒過規則、初篩判定不是軟體的，照平常的規則不寫紀錄。
5. **只有網址的網頁應用照網頁應用的規則**（18 個）：每站只抓 robots.txt、首頁、一頁使用條款；robots.txt 不讓 pickfit 抓、或條款禁止自動化存取的不收（上面「網頁應用（P2.8）」一節的規則 4–8）。通過後由模型初篩、抽取、寫紀錄，再由 `web_verify` 在 Modal microVM 裡開瀏覽器實測，每站只造訪一次。唯一不套用的是規則 3 的人氣區間（中間一半）：那是為了從一大批站裡取樣，這一批是念誠指定的知名網站。
6. **模型**：初篩 `claude-haiku-5-5`；初篩複查、抽取、驗證 agent、判讀、計分、網頁操作 `claude-opus-5-5`（Anthropic API）。每筆紀錄記下各段用的模型，花費記在帳本的 `pipeline` 預算。
7. **指令**：`uv run python scripts/ingest_candidates.py list`（解析與去重）、`repos`（有 repo 的）、`web`（網站的規則與初篩）、`results`（把每一筆的結果寫回 JSON）。

### 結果（2026-11-16 02:20 台北）

| | CLI／TUI | MCP server | 自架 Web 工具 | 網站 | 合計 |
|---|---|---|---|---|---|
| 清單列數 | 52 | 34 | 14 | 18 | 118 |
| 要跑的 repo 或網站 | 52 | 27 | 14 | 18 | 111 |
| 寫成紀錄 | 48 | 22 | 12 | 13 | 95 |
| 其中 function | 29 | 7 | 1 | 0 | 37 |
| 其中 service | 0 | 10 | 2 | 0 | 12 |
| 其中 install | 3 | 0 | 0 | 13 | 16 |
| 其中未驗證 | 16 | 5 | 9 | 0 | 30 |
| 沒寫紀錄 | 4 | 5 | 2 | 5 | 16 |

MCP 的 34 列裡有 6 列和別列同一個 repo（`modelcontextprotocol/servers`，合成一筆，驗到 service），1 列沒寫 repo（Puppeteer MCP）。每一筆的結果在 `docs/discovery/post-hackathon-candidates-v1.json`。

- **目錄**：1,058 → 1,153 筆，列出的 1,145 筆。新紀錄的類別：mcp_server 20、infra_devops 15、security_net 15、dev_cli 15、productivity_docs 11、data_db 9、media_files 6、other 4。知名度都高，沒有一筆算寶藏。漏洞檢查：clean 44、vulnerable 38、unchecked 13。
- **沒寫紀錄的 16 筆**，都是流程自己擋下的，沒有重抽：
  - 規則擋下 5：repo 已封存（Tree-sitter MCP、DuckDB MCP）、README 沒有安裝或用法的段落（Neo4j Cypher MCP、PairDrop、Cobalt）。
  - 讀起來不是「人會安裝來用的軟體」6：crane（`google/go-containerregistry` 主要是函式庫）、duckdb（README 寫它跑在應用程式的行程裡）、Browser-Use MCP（函式庫）、git-cliff 與 opentofu（README 裡找不到能引用的句子說它是哪一種軟體）、DeepWiki MCP（初篩複查判定不是可用的軟體）。
  - 網站 5：使用條款禁止自動化存取（JSON Crack、Webhook.site）、robots.txt 不允許（tldraw）、首頁文字太少，抽取引不出「這是網頁應用」的原文（Squoosh、Crontab.guru）。
- **未驗證的 30 筆**：20 筆是 README 沒有 Linux 沙盒能跑的安裝指令。知名工具的 README 常常只寫「安裝請看官網文件」（rclone、restic、chezmoi、pandoc、mitmproxy、fx…），或只給 Docker、Homebrew（trivy、多數自架 Web 工具）；pickfit 只讀 README 與 release，所以沒有指令可跑。其餘 10 筆沙盒跑了但沒通過：
  - 5 筆是 agent 說裝好也測過了，但它記下的安裝步驟不合 pickfit 的紀錄規則，程式不採信：一步超過 500 字元（act、vhs、homepage），或用 `for` 迴圈包住下載、看不出每一步有沒有成功（termshark、jless）。這是 Claude 當 agent 時的寫法問題，不是工具的問題，之後調整提示再重驗應該會過。
  - 2 筆是 MCP server 少了它要連的服務，交握不成功：Postgres MCP Pro（要資料庫）、kubernetes-mcp-server（要叢集）。
  - 3 筆 agent 自己回報原因：mcp-server-docker 要 Docker、Brave Search MCP 要金鑰、n8n 資源不夠。
- **網站 13 筆只到 install**：每站造訪了一次，頁面開得起來、判讀是主畫面，但操作 agent 一步都沒動。原因在 pickfit 這邊：browser-use 會要求模型把推理寫進回覆的 `thinking` 欄位，Anthropic API 把這種請求判成擷取模型推理而拒答（`stop_reason: refusal`，類別 `reasoning_extraction`），52 次操作呼叫全部沒有內容。已修正（Claude 當操作者時不要求那個欄位；被拒答會換模型並把原因回報給 harness）。要補功能實測就得再造訪一次，和上面第 5 點「每站只造訪一次」衝突，所以還沒做，等念誠決定。
- **途中修掉的兩個抽取問題，以及重跑了哪幾筆**（都是 pickfit 這邊的錯，不是挑結果）：
  - 抽取的 schema 有 49 個可為 null 的欄位，超過 Claude 結構化輸出的上限 16，所以 schema 改放在提示詞裡，沒有強制力。Claude 把不知道的欄位寫成單純的 `null`，驗證不過；前後 41 次抽取因此白做（約 $1.2）。修正後重跑三次都失敗的 3 筆：pandoc、trippy、go-task（`--retry`）。
  - `platforms` 被讀成「句子裡提到的那個系統」（例如 "Release v0.3.0 adds windows support" 被讀成只支援 Windows），3 筆因此沒進沙盒：oxker、mcp-server-docker、postgres-mcp。把欄位說明寫清楚後重抽（三筆都變成「沒寫」），第一次產生的未驗證紀錄還沒 commit，移到 `runs/candidates-v1/superseded/`，再照同一段流程重跑：oxker 通過，另外兩筆進了沙盒但沒過（要 Docker、要資料庫）。
- **花費**（帳本 `pipeline` 預算，11/16）：Claude 約 $27.7，其中驗證 agent 12.4、抽取 8.0、文件 rubric 3.1、判讀 1.4、網頁操作 1.4（全部被拒答）、使用說明 0.9、初篩 0.2、連線測試 0.2；Modal 沙盒約 $0.55。每個有 repo 的候選平均約 $0.25，從送進流程到寫成紀錄 2–6 分鐘。
- **11/16 03:20 補跑之後的數字在下一節**；這一節維持 02:20 當時的樣子。
- **帳本裡有 43 列不是實際花費**：11/15–11/16 的 `verify-gui-operator`、沒有 run id、共約 $0.49，是跑測試時測試替身寫進共用帳本的（`tests/test_verify_gui_operate.py` 沒有隔離帳本，賽期就有，當時算在 Baseten 的價格上）。現在 `tests/conftest.py` 讓每個測試用自己的帳本與 runs 資料夾；已經寫進去的列沒有刪。

## 安裝文件：README 只寫「請看官網」時，讀專案自己的安裝頁（規則 `install-docs.v1`）

2026-11-16 03:20（台北）登記，念誠 11/16 要求（「很多說安裝請看官網的，agent 要有辦法去看官網的文件」）。登記比第一次抓取晚：02:58–03:01 已經替 20 個候選抓過頁面，程式（`pickfit/installdocs.py`）、測試和這一節在同一批 commit 裡（分支 `worktree-post-hackathon-anthropic`）。

為什麼：知名工具的 README 常常沒有安裝指令，只連到官網的安裝頁。抽取只讀 pickfit 抓下來的東西，所以這些工具沒有沙盒能跑的安裝方式，從來沒進過沙盒就列成未驗證。

規則：

1. **只在需要時讀**。候選的抽取結果是工具、而且沒有 Linux 沙盒能跑的安裝方式，才去讀；README 自己有安裝指令的不抓任何頁面。每個候選只讀**一頁**，找過一次就不再找（`--force` 例外）。
2. **只讀專案自己的**，照這個順序，讀到一頁就停：
   1. repo 裡的文件（`INSTALL.md`、`docs/install*.md`、`docs/getting-started.md` 這類，README 有連過去的，或檔案樹裡看得到的）。走 GitHub API，和讀 README 一樣。
   2. README 連出去的頁面，連結文字或網址寫著 install、getting started、quick start、download、setup。
   3. 前兩種都沒有時，看專案稱為首頁的頁面（GitHub 上登記的 homepage、README 裡寫「Documentation」的連結），再讀那一頁在同一個網站上連到的安裝頁；首頁自己就寫了安裝方式的，讀首頁。
3. **「專案自己的網站」怎麼認**：和 GitHub 登記的 homepage 同一個網站（含子網域，例如 `docs.mitmproxy.org`），或主機名稱裡有 repo 或擁有者的名字（`restic.readthedocs.io`、`smallstep.com`）。README 也會連到它依賴的東西的安裝頁（Rust、Docker、Go），那些不讀。不搜尋。徽章圖片、社群、商店、套件倉庫的網址都不算。
4. **照網頁應用的規矩抓**：用 pickfit 自己的 User-Agent，同站每秒一個請求，每個候選最多 8 個請求（robots.txt、首頁、安裝頁都算）。robots.txt 不讓 pickfit 抓、或表示內容不給模型讀的，不抓（`robots_verdict`，和上面「網頁應用」一節同一段程式）。轉到別的網站的不讀；只會轉址的舊網址跟一次；要 JavaScript 才有文字的頁面不渲染，記下來跳過。
5. **存什麼**：頁面網址、標題、去掉選單與頁尾的文字（最多 20,000 字元）、抓取時間，以及每個找過的位置和結果（`runs/pipeline.db` 的 `install_docs`）。不存圖片。
6. **怎麼用**：這一頁當成抽取的另一個來源（`docs1`，放在 `<source>` 區塊裡，和 README 一樣只是資料），抽出的安裝指令照舊要逐字引用原文；紀錄的 `sources` 會列出這一頁。驗證時這一頁也放進沙盒的工作目錄（`INSTALL-GUIDE-1.md`），README 的指令不夠時 agent 可以自己讀。
7. **指令**：`uv run pickfit extract --install-docs --model prod`；`pickfit watch` 處理提交的 repo 時也會做同一步。

### 結果（2026-11-16 03:20 台北）

22 個候選的抽取沒有沙盒能跑的安裝方式（20 筆未驗證的紀錄，加上當時沒寫成紀錄的 git-cliff 與 opentofu）。讀到一頁的 21 個：

- repo 裡的檔案 7：rclone（`docs/content/install.md`）、pandoc（`INSTALL.md`）、trivy、presenterm、bentopdf、dozzle、qsv。
- README 連出去的頁面 11：mitmproxy、restic、step-cli、go-task、git-cliff、opentofu、gh-dash、beszel、homarr、hedgedoc、supabase MCP（讀到的是它的 MCP 說明頁）。
- 從首頁找到安裝頁 3：chezmoi、fx、kroki。
- 沒讀到 1：omni-tools（首頁要 JavaScript 才有文字）。

重新抽取 21 筆（約 $1.36）之後，11 筆有了沙盒能跑的安裝方式，全部進沙盒，全部通過：function 8（rclone、restic、chezmoi、pandoc、trivy、go-task、step-cli、presenterm）、service 2（mitmproxy、bentopdf）、install 1（gh-dash）。git-cliff 第一次因為 README 裡引不出「它是哪一種軟體」而沒寫紀錄，這次抽取判定是 CLI 工具，寫成紀錄（未驗證）。

還是沒有安裝方式的 10 筆：只給 Docker 的自架工具 5（dozzle、kroki、hedgedoc、homarr、beszel）；安裝頁只列 Homebrew、snap、Go 的 fx；安裝頁是索引、指令在子頁的 git-cliff 與 opentofu（這條規則只讀一頁）；qsv（README 連到的是另一份入門文件）；supabase MCP（遠端服務，沒有本機安裝）。

## 第一批候選：11/16 的補跑

念誠 11/16：13 個網站重跑、agent 要能讀官網的安裝文件、查清楚 5 筆安裝步驟不合紀錄規則的原因並修正。

### 13 個網站再造訪一次

第一次造訪（規則 5 的「每站只造訪一次」）操作 agent 一步都沒動，原因在 pickfit（上一節）。念誠同意重跑，所以每站用 `--revisit` 再造訪一次，原因寫進每一筆 run。結果：**function 12、install 1**。Excalidraw 留在 install：agent 在畫布上打了字，但判讀沒看到 README 說的功能做出來。

DuckDB Web Shell 造訪了第三次。第二次操作了 6 步之後，判讀被 pickfit 自己的預算規則擋下：判讀和操作共用同一個 scope，上限卻只有 $0.50，操作已經花了 $0.69，判讀就送不出去，那次造訪等於白做。修正：判讀的上限改成整次造訪的上限（`SITE_CAP_USD`）。第三次到 function。

13 筆都補了視覺檢查（`pickfit visual`）。這次有變動的 37 筆紀錄（含下面重驗的），使用說明都照新的 run 重寫。

### 5 筆安裝步驟不合紀錄規則：原因與修正

規則本身沒有錯。紀錄裡的每個安裝步驟都要符合兩件事：指令在 500 字元以內（要顯示給人複製）、指令的結束碼真的代表成功（不能用 `; echo`、`|| true`、管線接 `grep`、迴圈等把失敗蓋掉）。5 筆都是工具其實裝好也測過了，但 agent 引用的指令不合這兩條。問題出在 pickfit 怎麼告訴 agent：

1. **一次只講一個毛病，而且只給一次重來的機會**。act 的那一步同時有兩個問題（結尾接了 `; cat`、長度 692 字元）。pickfit 只回報第一個，agent 改掉之後重跑，新的指令 752 字元，第二次就不再退回。homepage（結尾的 `; ls`，改完 758 字元）、jless（先被挑 `||`，改完剩下 `for` 迴圈）都是同一種情況。
2. **規則沒有事先講**。提示詞列了一部分會蓋掉結束碼的寫法，沒有提 500 字元，也沒有提迴圈。agent 要等到最後呼叫 finish 才知道。termshark 和 vhs 是在只能呼叫 finish 的最後一輪才被擋，連重來的機會都沒有。
3. **測試用的輸入檔被當成安裝步驟**。act 的 workflow 檔、homepage 的設定檔，是用 heredoc 寫的幾百字元。它們是某個檢查的前置（`setup_ids`，上限 4,000 字元），不是安裝步驟。finish 的欄位說明寫「包含這些指令用到的每個檔案寫入」，agent 就把它們放進 steps。

修正（`pickfit/verify/verdict.py`、`agent.py`）：

- 一個步驟的所有毛病一次列完（`masked_exits`），長度另外算，不再只報第一個。
- 提示詞事先寫明：每個安裝步驟與檢查是一條 500 字元以內的指令、不能有迴圈（改成用 `&&` 寫開，或把清單餵給 xargs）、只寫輸入檔或設定檔的指令放在該檢查的 `setup_ids`。
- 指令跑完當下就提醒：成功（exit 0）但不能引用的指令，回傳的輸出前面會加一行說明原因，agent 還有指令額度時就能重跑，不用等到 finish。
- 退回 finish 時的訊息也寫上這幾條，並說明只寫輸入檔的指令不必重跑，改放 `setup_ids` 就好。

重驗 5 筆：**vhs function、jless function、homepage service、act function（第二次；第一次 agent 自己判定要 Docker）**。termshark 修正後跑了三次都沒過。第一次是安裝步驟接了 `grep`，又剛好在只能呼叫 finish 的那一輪（所以才加上跑完當下的提醒）。後兩次 agent 的回報和紀錄一致，但在乾淨沙盒重播時失敗：它要的 tshark 是系統套件，沙盒沒有 root，agent 用下載 .deb 再解開的方式繞過，引用的步驟換到乾淨的沙盒就跑不起來（一次少了建立目錄的指令，一次第一步就失敗）。維持未驗證。

### 補跑之後（2026-11-16 03:20 台北）

| | CLI／TUI | MCP server | 自架 Web 工具 | 網站 | 合計 |
|---|---|---|---|---|---|
| 寫成紀錄 | 49 | 22 | 12 | 13 | 96 |
| 其中 function | 40 | 7 | 1 | 12 | 60 |
| 其中 service | 1 | 10 | 4 | 0 | 15 |
| 其中 install | 4 | 0 | 0 | 1 | 5 |
| 其中未驗證 | 4 | 5 | 7 | 0 | 16 |
| 沒寫紀錄 | 3 | 5 | 2 | 5 | 15 |

- **未驗證的 16 筆**：termshark（上面）；fx、qsv、git-cliff（讀了安裝頁還是沒有沙盒能跑的指令）；MCP 5（Brave Search 要金鑰、mcp-server-docker 要 Docker、Postgres MCP Pro 與 kubernetes-mcp-server 交握不成功、supabase MCP 是遠端服務）；自架 Web 工具 7（dozzle、kroki、hedgedoc、homarr、beszel 只給 Docker，omni-tools 沒讀到安裝頁，n8n 資源不夠）。
- **花費**（帳本，11/16 02:37–03:19）：Claude 約 $10.0，其中驗證 agent 3.9、網頁操作 2.4、抽取 1.4、文件 rubric 0.9、網頁判讀 0.4、使用說明 0.4、視覺檢查 0.3、判讀 0.4；Modal 約 $0.13。
- **順手修掉的兩個舊問題**：`pickfit profiles` 遇到網頁應用的抽取會當掉（那些抽取沒有 repo 候選，現在跳過，它們的紀錄由 `pickfit webapps records` 寫）；`scripts/copy_evidence.py` 遇到本身就是連到證據區的 run 資料夾會當掉（現在標成 `in_place`，不複製也不改寫）。這一批網頁 run 的截圖與紀錄已複製到 `~/.pickfit/evidence/`。
