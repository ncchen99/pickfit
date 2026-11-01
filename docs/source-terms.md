# 新來源的條款：Flathub、Homebrew Cask 與網頁應用

2026-11-01（台北）查證 · P2.7（brief 第 2.1、8 節）；網頁應用 11/1–11/2 查證 · P2.8（brief 第 2.2 節，見最後一節）。用之前先讀這份；條款有變就更新這份與 `NOTICE`。

## 結論

| 來源 | 能不能用 | 怎麼用 | 不用的部分 |
|---|---|---|---|
| Flathub | **可以，只走 flatpak 的套件庫** | 下載 `dl.flathub.org/repo/appstream/x86_64/appstream.xml.gz`（每台 flatpak 用戶端都下載的同一份 AppStream 目錄），一次執行一次。取 App 的 id、名稱、摘要、說明、授權、網址、版本與日期 | 不爬 flathub.org 網站、不打 `flathub.org/api`、**不用安裝數**（`/stats`） |
| Homebrew Cask | **可以** | `formulae.brew.sh/api/cask.json`（cask 定義）與 `api/analytics/cask-install/{30d,90d,365d}.json`（安裝數），一次執行各一次 | 安裝數只當選樣訊號，不轉發原始數字 |
| 網頁應用（Show HN、GitHub 上有線上網址的 repo） | **可以，每站先查 robots.txt 與使用條款** | 發現走既有的 HN API 與 GitHub API；每個網站只抓 robots.txt、首頁、一頁使用條款 | 禁止自動化存取的網站不收；首頁文字只在抽取前暫存，紀錄只留抽出的事實與短引用 |
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
2. **首頁**：pickfit 自己的 User-Agent（`pickfit/0.1 (+https://github.com/ncchen99/pickfit)`）GET 一次，跟隨轉址，最多 3 MB。不是 200（`site_down`）、不是 HTML（`not_html`）、轉到平台（`redirect_platform`）都不收。
3. **使用條款**：首頁連到的 terms／ToS／conditions／legal 頁（同網站、terms 優先，只有 privacy 或 cookie 的不算）；首頁沒有連結（多半是用 script 畫出來的單頁應用）就試一次 `/terms`，內容讀起來是條款才算。條款裡有一句同時出現「robot、spider、scraper、crawler、bot、automated means／access／tools…、data mining、harvest」和「不得、禁止、未經同意」之類的字 → 不收（`terms_disallow`），那句話（最多 300 字）存在檢查紀錄裡。寧可多擋：有些只禁止「用自動化工具註冊帳號」的也會被擋。讀不到條款頁照收，並記 `unreadable`。

每個網站只抓這三樣（robots.txt、首頁、一頁條款），每次請求間隔 1 秒；GitHub repo 的 README 走 GitHub API。

### 存什麼

- `runs/pipeline.db`（不進 git）的 `web_sites` 表：每篇貼文或每個 repo 一列，含篩選結果、robots 與條款的判讀、首頁標題與 meta 描述。首頁的可見文字（最多 4 萬字）只為了抽取暫存，抽取完用 `pickfit webapps purge` 刪掉。
- 紀錄（`data/software/`）：只有抽出的事實與每個欄位的短引用（≤300 字），來源列出網站首頁（`website`）、Show HN 貼文（`hn`，不當任何欄位的證據）、有 repo 的再列 GitHub API 與 README。
