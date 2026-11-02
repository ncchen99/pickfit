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
