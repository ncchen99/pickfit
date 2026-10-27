2026-10-28 · 多管道整合工程（增量抓取、排程、去重正規化、統一候選格式、漏斗成本、現成工具）與「作者／使用者主動提交連結」管道 · 由調研 agent 撰寫，待主控者整合

# 管道調研：多管道整合工程與提交入口

需求來源：[brief.md](../../brief.md) 第 4、8、11、13 節；[hackathon-rules.md](../../hackathon-rules.md)。查證日期一律是 2026-10-28（台北），也就是 2026-10-27 UTC 晚間。條款引用是原文摘錄，解讀只供產品決策參考，不是法律意見。

標記：**已驗證**＝親自讀了官方文件原文，或親自打了 API 看到回應。**未驗證**＝沒親自確認。

> **環境限制（影響實測）**：這個雲端 session 的代理只放行 `api.github.com` 上的本專案 repo，打別人的 `/repos/...` 回 403（「GitHub access to this repository is not enabled for this session」）。所以 **GitHub API 對改名 repo 回 301 這件事本 session 沒辦法親眼看到**。腳本已寫好 API 路徑（不自動 follow redirect，直接印出 301 與 `Location`），在念誠自己的電腦設 `GH_TOKEN` 跑即可。本 session 改用 `git ls-remote`、ecosyste.ms、deps.dev 做旁證。〔查核 2026-10-28 重測：`/repos/{別人}` 仍 403；`/repositories/{id}` 回「Numeric-ID repository paths … are not supported through this proxy」；`/search/*`、`/users/*` 也 403；只有 `/rate_limit` 回 200。〕

---

## 一句話結論

- **主鍵用 GitHub 的數字 repo ID，不是網址。** 實測 Show HN 7 天的 271 個 repo 裡有 **39 個（14%）已經改過名或轉移過**；ecosyste.ms 與 deps.dev 都**不會**把舊名導到新名（舊名查無，或當成另一個專案）。只有 GitHub API 的 301 能可靠拿到現名，所以正式管線一定要走 GitHub API。〔查核補充：這 7 天資料裡，Show HN 貼文用舊名連結的實例是 0（查得到的 271 個 repo，貼文網址全是現名）；實際會造成重複的是套件宣告舊名（4.3）。〕
- **套件 → repo 先看簽章 provenance，再看自填欄位。** PyPI 最新 39 個新專案有 27 個有 Trusted Publishing provenance，與自填欄位 0 衝突；4 個只能靠 provenance 才對得到 repo。
- **增量抓取不難，難在 PyPI RSS 只涵蓋約 1 小時**：要 20–30 分鐘輪詢一次，否則會漏。HN Algolia 用 `created_at_i` 當 cursor；有 ETag 的來源（PyPI、crates、Homebrew、npm、raw.githubusercontent）用 `If-None-Match` 省流量。
- **排程：本機 cron 或 Modal cron 跑發現；提交走事件觸發，不等排程。** GitHub Actions 用 GitHub-hosted runner 跑爬取型工作落在條款灰色地帶（「unrelated to the production … of the software project」），Cloudflare Workers Free 每次只能發 50 個子請求（轉址每一跳都算），跑不動抓取管線。
- **提交入口只做一條路**：MCP `submit_software`＋GitHub Issue Form 共用同一個佇列。Threads 連結只存 permalink 供 oEmbed 嵌入，**一定要附 GitHub 或官網連結**（Threads 貼文內容沒有合規的方法交給模型讀，見 [channels-meta-platforms.md](channels-meta-platforms.md)）。驗證失敗不收錄；提交次數不加分。
- **不要裝 RSSHub、Huginn、changedetection.io、GH Archive。** RSSHub 的 GitHub trending／topics／search、Threads、HN、Product Hunt 路由都是抓 HTML（讀過原始碼），違反各來源條款；GH Archive 從 2025-10 起每小時 0 筆新 repo 事件（本次再測一次仍是 0）。
- **〔查核新增〕ecosyste.ms 先取得書面同意才放進管線。** 它的 [Terms](https://ecosyste.ms/terms) §9 禁止「Develop or use any third-party applications that interact with our Platform without our prior written consent, including any scripts designed to scrape or extract data from our Platform」，§11(c) 的授權只限「your own personal use」。和 API 頁公開提供 API 的說法衝突。處理方式和 [channels-packages.md](channels-packages.md) 2.12 一致：寄信 support@ecosyste.ms 取得同意前，改用 GitHub API（metadata）與 deps.dev（repo → 套件反查）。

---

## 1. 比較表

這一組的「管道」分兩類：(A) 提交入口與提交的連結類型，(B) 讓多管道整合省工的資料服務與工具。整合成本是一個人、黑客松版本的人時。

| 管道 | 訊號品質 | 新作品多寡 | 雜訊 | 取得方式 | 限制（ToS／授權／費用／rate limit／權限） | 整合成本 | 建議 |
|---|---|---|---|---|---|---|---|
| **MCP `submit_software` 工具** | 高：使用者或作者主動推薦，附需求情境 | 少，靠使用者主動 | 中：會有自我推銷與重複 | MCP tool → 佇列 | 匿名；Worker rate limit binding 計數只在單一機房、最終一致；不記 IP（brief 11） | 1–2 | **黑客松接** |
| **GitHub Issue Form（提交）** | 高：有 GitHub 帳號、可追蹤、公開透明 | 少 | 中 | Issue Form＋repo webhook（`issues` 事件）→ Modal 端點；或 Actions `issues: opened` 只做轉送（〔查核修正〕見 2.2） | Issue forms 官方標示 public preview；**private repo 只有協作者能開 issue**；`GITHUB_TOKEN` 1,000 次／時／repo；要防 script injection；Actions 條款（GitHub-hosted runner 不得做與 repo 軟體專案無關的事） | 1–2 | **黑客松接**（repo 公開後，或開一個公開的 submissions repo） |
| 網頁表單（Worker＋Turnstile） | 中：匿名 | 少 | 中高 | HTTPS 表單 | Turnstile 免費、20 個 widget；要自己做頁面 | 2–3 | 之後擴充（展示頁有做才做） |
| 提交的連結：GitHub／GitLab／Codeberg repo | 高 | — | 低 | GitHub API（其他 forge 單筆 API） | GitHub API 5,000 次／時；GitLab API Terms 1.3.9 禁止 bulk collection，單筆查詢可以 | 2–3（正規化＋改名解析） | **黑客松接** |
| 提交的連結：套件頁（PyPI／npm／crates／Homebrew） | 高：provenance 可證明對應的 repo | — | 低 | 各 registry API（不爬網頁） | npm 條款禁止自動化存取網站，要走 registry API | 2 | **黑客松接**（PyPI、npm、Homebrew） |
| 提交的連結：HN item | 中高：有作者說明 | — | 低 | HN 官方 API（item） | 「There is currently no rate limit」；YC ToU 禁止爬網站 | 0.5 | **黑客松接** |
| 提交的連結：Threads 貼文 | 無（讀不到內容） | — | — | 只存 permalink；展示時 oEmbed 嵌入 | oEmbed 內容「any purpose other than providing a front-end view … is strictly prohibited」 | 0.5 | **只當附件**；必須另附 repo 或官網 |
| 提交的連結：任意官網 | 中低：可能是閉源 SaaS 或 landing page | — | 高 | 抓一次該頁（守 robots.txt）找 repo／下載連結，或交模型 | 每個網站條款不同；只抓作者提交的那一頁 | 2 | 黑客松選做（先標 `needs_info`） |
| 短網址展開 | — | — | — | HEAD 逐跳、不自動 follow | 要擋私有 IP（SSRF）；實測 tinyurl 指到裸 IP | 0.5 | **黑客松接**（放進正規化） |
| **ecosyste.ms**（repos／packages lookup） | 中高（補資料）：fork／archived／template／README／license、`previous_names`、反查「這個 repo 發了哪些套件」 | 新 repo 覆蓋 70%（271／386） | 低 | API | 程式碼 AGPL-3、**資料 CC BY-SA 4.0**；**Terms §9 禁止未經書面同意的第三方程式／腳本擷取資料，§11(c) 只授權個人使用**；rate limit 官方頁沒寫數字，回應標頭見 2.10（〔查核修正〕原寫「匿名 5,000、加 `?mailto=` 15,000」，重測不成立） | 1–2 | **條件式**：寄信取得書面同意後才接；之前改用 GitHub API＋deps.dev（〔查核修正〕原寫「黑客松接」） |
| deps.dev | 中（補資料）：有簽章的 repo 對應；`projects/{key}:packageversions` 可從 repo 反查套件（查核實測） | — | 中：**改名後舊名、新名是兩個專案** | API v3 | Google API ToS；資料 CC-BY 4.0；文件沒寫 rate limit | 1 | 之後擴充；ecosyste.ms 未取得同意前，反查套件改用它（〔查核修正〕） |
| PyPI Integrity API／npm attestations | **高**：Trusted Publishing 簽章證明的來源 repo | 新套件常有（PyPI 27／39） | 低 | API | 無金鑰 | 1 | **黑客松接** |
| GH Archive（每小時 dump） | **低**：公開事件流已看不到新 repo | 2026-10-27 17:00 UTC 一小時 3,251 筆事件、**新 repo 0** | — | 每小時 `.json.gz`、BigQuery | 程式碼 MIT、網站 CC-BY-4.0；BigQuery 每月 1 TB 免費查詢 | — | **避開** |
| OpenSSF Scorecard（API／CLI） | 高（品質訊號）但**新 repo 沒有資料** | API 抽 40 個 Show HN repo：**0 個有分數**（查核重抽 40 個、用原始大小寫：仍 0） | 低 | REST API（**路徑區分大小寫**，要用 API 回的 `full_name`）；CLI 自己跑 | Apache-2.0；API 資料 CDLA-Permissive-2.0；BigQuery 資料集已停；CLI 要 GitHub token、吃 API 額度 | 1–2（CLI） | 之後擴充（驗證通過後才跑 CLI） |
| RSSHub | 低：多數相關路由是爬網頁 | — | — | 自架 feed 轉換器 | AGPL-3.0；github trending／topic／search、threads、hackernews、producthunt 路由都抓 HTML | — | **避開** |
| changedetection.io | 低（對本專案） | — | — | 自架網頁監看 | Apache-2.0；本質是定期抓網頁 | — | 避開（我們的來源都有 API／RSS） |
| Huginn | 低（對本專案） | — | — | 自架 agent 平台（Rails） | MIT；維運重 | — | 避開 |
| `gh` CLI | —（工具） | — | — | CLI | MIT；`gh api --paginate --cache 1h` | 0.5 | **黑客松接**（手動探查、一次性回補） |
| feedparser 與正規化函式庫 | —（工具） | — | — | Python／npm 套件 | feedparser BSD-2；packageurl-python MIT；hosted-git-info ISC（npm 自己用的） | 0.5 | 選用（spike 證明標準函式庫也夠） |

---

## 2. 各管道細節

### 2.1 MCP `submit_software` 工具

- **能不能拿到最近才出現、沒人知道的**：能，這正是它的用途。作者本人或使用者的 agent 把剛看到的作品交上來。
- **做法**：輸入 `url`（必填）、`repo_url`（選填，提交 Threads 或官網時必填）、`note`、`i_am_the_author`。回傳 `submission_id` 與目前狀態；處理是非同步的。另加一個查狀態的方式（第 5 個工具，或在 `report_outcome` 裡帶 `submission_id`）。
- **兩個類別**：開發者 CLI 工具、本地 AI 工具都一樣適用；agent 使用者本來就在終端機裡。
- **限制**：MCP server 是無狀態 Worker（brief 11），提交要寫進外部佇列（GitHub issue、D1 或 KV）。Cloudflare Rate Limiting binding：「Counts are eventually consistent: each check uses a local count」「These counts do not combine into one worldwide limit」，期間只能是 10 或 60 秒（[Rate Limiting](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/)，已驗證）。所以它只能擋短時間洗版，**每日總量要另外在佇列端設上限**。
- **demo 價值**：brief 第 5 節第 5 幕「作者貼連結 → 幾分鐘後出現在推薦裡」可以直接用 agent 呼叫這個工具錄。

### 2.2 GitHub Issue Form

- 官方：「Issue forms are currently in public preview and subject to change.」回答會「converted to markdown and added to the body of an issue」（[Syntax for issue forms](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms)，已驗證）。所以表單**不保證格式**，處理端仍要從 markdown 解析、重新驗證。
- **便宜**：零後端。一個 `.github/ISSUE_TEMPLATE/submit.yml`＋一個 `on: issues: types: [opened]` 的 workflow，用 label 當狀態（`submitted` → `processing` → `verified`／`failed`／`needs-info`）。public repo 用標準 runner 免費（已驗證，見 3.2）。
- **身分與防灌水**：一定要有 GitHub 帳號。可用 interaction limits：「Limits activity for users with accounts that are less than 24 hours old」「Limits activity for users who have not previously contributed」，期間「24 hours, 3 days, 1 week, 1 month, or 6 months」（[Limiting interactions](https://docs.github.com/en/communities/moderating-comments-and-conversations/limiting-interactions-in-your-repository)，已驗證）。
- **資安**：issue 標題與內文是不可信輸入。官方把 `github.event.issue.title`、`…body` 列為會造成 script injection 的 context（[Script injections](https://docs.github.com/en/actions/concepts/security/script-injections)，已驗證）。workflow 只能透過環境變數把內容交給腳本，不能直接寫進 `run:`；處理提交的 job 不要拿得到 Meta API key 以外的祕密。
- **〔查核修正〕不要在 Actions 裡處理提交。** Actions 條款原文：用 GitHub-hosted runner 時不得做「any other activity unrelated to the production, testing, deployment, or publication of the software project associated with the repository」，並以「don't use Actions as a content delivery network or as part of a serverless application」為例（[Additional Products Terms](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features)，查核已讀）。在 Actions 裡呼叫 Meta 模型、跑驗證，等於把 Actions 當成服務後端。建議改用 repo webhook（`issues` 事件）直接打 Modal 的 web 端點；或 workflow 只做「加 label＋轉送 issue 編號」，不放 Meta API key。
- **卡點**：pickfit repo 目前 private，外人開不了 issue。黑客松期間要嘛等 11/4 轉 public，要嘛在開發期間另開一個公開的 `pickfit-submissions` repo（10/26 之後建立，符合規則）。
- `GITHUB_TOKEN`：「The rate limit for GITHUB_TOKEN is 1,000 requests per hour per repository」（[REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)，已驗證）。處理提交夠用。

### 2.3 網頁表單（Worker＋Turnstile）

- Turnstile Free：「Up to 20 widgets」、「Unlimited challenges」，價格 Free（[Turnstile plans](https://developers.cloudflare.com/turnstile/plans/)，已驗證）。
- 匿名、門檻最低，所以灌水風險最高。只有在做了公開展示頁（brief 4.5，第一個被砍的項目）時才值得做。
- 收進來的東西和 MCP、Issue Form 走同一個佇列與同一套驗證。

### 2.4 提交的連結：程式碼託管 repo

- 走正規化（第 4 節）→ GitHub API 解析 → 拿數字 ID、現名、fork、archived、template。
- GitHub 以外的 forge：GitLab API Terms 1.3.9「Not to use the GitLab APIs for the bulk collection or scraping of information」；Codeberg robots.txt `Disallow: /api/`（兩者見 [channels-hosting.md](channels-hosting.md)）。**單筆、使用者觸發的查詢**和這些限制不衝突，定期掃描才會。
- 兩個類別：CLI 工具的 repo 最好處理（有 release 就能驗證）；本地 AI 工具常要下載模型，驗證要用最小模型（見 [sandbox-compare.md](sandbox-compare.md)）。

### 2.5 提交的連結：套件頁

- `pypi.org/project/<name>`、`www.npmjs.com/package/<name>`、`crates.io/crates/<name>`、`formulae.brew.sh/formula/<name>`：只從網址取套件名，資料一律走 API（npm 條款：「You will not automate access to, use, or monitor the Website, such as with a web crawler」，見 [channels-packages.md](channels-packages.md)）。
- 對應方法與實測結果見 4.5、8.1。

### 2.6 提交的連結：HN item

- `news.ycombinator.com/item?id=N` → `https://hacker-news.firebaseio.com/v0/item/N.json` 拿 `url` 與 `text`，再抽網址。官方 README：「There is currently no rate limit.」（[HackerNews/API](https://github.com/HackerNews/API)，已驗證）。
- 只存 item ID、標題、時間、points；軟體事實從 repo 取，不轉載貼文全文（YC ToU 的解讀見 [channels-communities.md](channels-communities.md)）。

### 2.7 提交的連結：Threads 貼文

- 只存 permalink（`threads:<code>`），展示時用 oEmbed 嵌入。oEmbed 條款原文：「Using metadata and post content (or their derivations) from the endpoint for any purpose other than providing a front-end view of the post is strictly prohibited.」，而且回傳的 html 沒有貼文文字（[channels-meta-platforms.md](channels-meta-platforms.md) 2.2，已由該組驗證）。〔查核 2026-10-28：條款原文在 [Embed a Threads Post](https://developers.facebook.com/documentation/threads/tools-and-resources/embed-a-threads-post)（Updated Mar 3, 2026）親自讀過，一致；同頁寫「You can make up to 1,000 requests every hour」，私人、停用、年齡限制、地區限定的貼文不支援。重跑 `spikes/ch_meta_probe.py`：免 token 回 200，html 3,094 bytes，可見文字只有「View on Threads」。只驗了官方範例貼文 1 則。〕
- **所以 brief 4.1「貼一個 GitHub 或 Threads 連結」要改成「貼 GitHub（或官網）連結，可另附 Threads 貼文」**。只有 Threads 連結的提交，狀態設 `needs_info`，回覆提交者補 repo。
- 實測：Show HN 最近 24 小時就有 1 則附 Threads 連結（`threads_post` 1 筆），作者確實會跨平台貼。

### 2.8 提交的連結：任意官網

- Show HN 7 天 986 則有網址的貼文裡，**只有 385 則（39%）連到 repo**，698 個網址是官網或其他網頁。很多「默默無聞的好軟體」是閉源的 Mac App 或 SaaS。
- 做法：抓提交的那一頁一次（守 robots.txt），找 `github.com/...`、`releases`、`brew install`、`pip install` 等線索；找到 repo 就併回 repo 流程。找不到就保留為 `kind: web` 候選，交給 Muse Spark 判斷是不是可安裝的軟體；沙盒驗證不了的標「未驗證」（brief 13）。
- GitHub Pages（`user.github.io/repo`）可推回 `github.com/user/repo`，但只是提示，要用 API 確認存在（7 天有 39 個這種網址）。

### 2.9 短網址展開

- 實測 5 個從 HN 撈到的真實短網址全部展開成功：`git.io/JvoOi` → `github.com/tryamid/reekpie`；`t.co`、`lnkd.in`、`buff.ly` 都正常；`tinyurl.com/snakesonahyperplane` → **`http://104.131.141.204/`（裸 IP）**。
- 做法：手動逐跳（HEAD，不行再 GET），最多 5 跳，每跳檢查目標：只允許 http(s)、擋私有與保留 IP，避免 SSRF。只對已知短網址網域展開；Meta 的連結殼（`l.threads.com/?u=`、`l.facebook.com/l.php?u=`）直接解 query，不必發請求。
- Show HN 7 天 0 個短網址；這個問題主要出現在社群貼文與使用者提交。

### 2.10 ecosyste.ms

- **〔查核新增〕條款先決**：[ecosyste.ms Terms](https://ecosyste.ms/terms) §9 列為禁止：「Develop or use any third-party applications that interact with our Platform without our prior written consent, including any scripts designed to scrape or extract data from our Platform」；§11(c)：授權只限「your own personal use」，不含「commercially use」與「use any data mining, robots or similar data gathering or extraction methods」；§11(b)：資料 CC BY-SA，要「attributing 'ecosyste.ms' as the source of data」。[commercial 頁](https://ecosyste.ms/commercial) 又說社群可在 AGPL／CC-BY-SA 下免費使用。文字互相衝突，以較嚴的 Terms 為準。**寄信取得書面同意前，不放進自動化管線**；下面「為什麼要接」是取得同意後的理由。替代：metadata 用 GitHub API；repo → 套件反查用 deps.dev `GET /v3/projects/{key}:packageversions`（查核實測：`sturnus-dev/sturnus` 回 cargo `sturnus`；`astral-sh/ruff` 回 1,500 筆就截斷、沒有 `nextPageToken`，PyPI 的 `ruff` 不在裡面，大 repo 會漏）。
- **為什麼黑客松要接**（取得同意後）：(1) 本調研環境打不到 GitHub API 時的備援；(2) `previous_names`（改名歷史）；(3) packages lookup 可以**從 repo 反查它發了哪些套件**，這是「同一專案出現在 GitHub、PyPI、npm」合併的關鍵。
- 實測 Show HN 7 天 386 個 GitHub repo：查得到 271（70%）。查不到的多是剛建立的 repo，正式管線要以 GitHub API 為主。〔查核補充：舊名查詢也會 404，所以 115 個查不到的裡面可能混有用舊名連結的 repo，比例未驗證。〕反查到套件的 repo 78 個（扣掉 Go module 後 66 個）：有 npm 套件 48、Go 17、cargo 15、PyPI 9、Homebrew 1。
- **改名**：對 5 組已知改名的 repo，舊名 lookup 全部 404；現名的 `previous_names` 有 4 組包含舊名（whisper.cpp 沒有）。所以它**只能「從現名查到舊名」，不能「從舊名找現名」**。
- `uuid` 欄位就是 GitHub REST 的數字 `id`。〔查核修正：原標未驗證。原始碼 [ecosyste-ms/repos](https://github.com/ecosyste-ms/repos) `app/models/hosts/github.rb`（commit `5f869a7`）寫 `hash[:uuid] = hash[:id]`，資料來自 GitHub API 的 repo 回應。〕
- 授權：「Code: AGPL-3」「Data: CC BY-SA 4.0」。rate limit：官方「To access the polite pool … Add mailto=you@example.com as a parameter to your API request, or Add mailto:you@exmaple.com somewhere in your user-agent request header, or Configure your from request header」，另有 common pool（[API 頁](https://ecosyste.ms/api)，已驗證）。**官方頁沒寫 5,000、15,000 這些數字，只能看回應標頭。** 〔查核修正：原寫「實測 UA 帶 mailto 仍是 anonymous 5,000 次／時，加 `?mailto=` 參數才變成 polite 15,000 次／時」。2026-10-28 重測：repos 服務**不帶任何 mailto** 也回 `x-ratelimit-tier: polite`、`x-ratelimit-limit: 15000`、`x-ratelimit-consumer: anonymous`；packages 服務回 `tier: parlay`、15000。pool 怎麼判定（可能依 IP 記住）**未驗證**，不要依賴「加參數才升級」的說法。另外 Cloudflare 會擋 Python 預設 UA（`Python-urllib/3.x` 回 403、error code 1010），一定要自訂 UA。〕
- CC BY-SA 的 share-alike 影響見第 10 節第 2 點。

### 2.11 deps.dev

- 實測 4 組改名的 repo：**舊名、新名各自是一個 project**，星數還不一樣（`charliermarsh/ruff` 50,179、`astral-sh/ruff` 50,207）。拿 deps.dev 當主鍵會重複收錄。
- 會把 key 轉成小寫（`github.com/Astral-SH/ruff` → `github.com/astral-sh/ruff`），旁證 GitHub 名稱大小寫不敏感。
- 它的強項（`relationProvenance` 區分自填與簽章）在 PyPI、npm 可以直接打原生 API 拿到（2.12），黑客松不必多接。

### 2.12 PyPI Integrity API、npm attestations（簽章 provenance）

- PyPI：`/integrity/<project>/<version>/<file>/provenance` 回 `publisher: {kind: "GitHub", repository: "pypa/pip", workflow: "release.yml"}`（實測）。PyPI 文件：「Trusted Publishing allows PyPI to attest that the publishing workflow for a package is coming from a verified source」；但「Verification isn't repeated after upload」（[Project metadata](https://docs.pypi.org/project_metadata/)，已驗證）。JSON API 的 `project_urls` **不帶**「已驗證」標記（實測欄位清單）。
- npm：最新版 `dist.attestations.url` → SLSA provenance → `predicate.buildDefinition.externalParameters.workflow.repository`（實測 `vite` → `https://github.com/vitejs/vite`）。
- 對兩個類別：本地 AI 的 Python 工具、CLI 的 npm 工具都常用 GitHub Actions 發布，覆蓋率不錯（PyPI 新專案 27／39）。

### 2.13 GH Archive

- 官方：「These events are aggregated into hourly archives」、BigQuery「automatically updated every hour」「1 TB of data processed per month free of charge」（[gharchive.org](https://www.gharchive.org/)，已驗證）。授權：程式碼 MIT、網站內容 CC-BY-4.0（[README](https://github.com/igrigorik/gharchive.org)，已驗證）；事件內容本身來自 GitHub API。
- **實測 2026-10-27 17:00 UTC 的小時檔**：3,251 筆事件（PullRequestEvent 1,334、ReleaseEvent 116、WatchEvent 231），**新 repo（CreateEvent, ref_type=repository）0 筆**。和 [channels-hosting.md](channels-hosting.md) 的結論一致：2025-10 起事件流看不到新 repo。
- 每小時 dump 的增量做法很簡單（cursor＝最後處理的小時；檔案有 ETag 與 Last-Modified，實測 304），但資料已經沒用。

### 2.14 OpenSSF Scorecard

- 官方 README：「Scorecard scans more than 1.3 million repositories every week」；「The BigQuery public dataset is no longer available」；「Data provided by the REST API is licensed under the CDLA Permissive 2.0」（[ossf/scorecard README](https://github.com/ossf/scorecard)，已驗證）。
- **實測覆蓋率**：Show HN 7 天的 repo 隨機抽 40 個，`api.scorecard.dev` **0 個有資料**；`junegunn/fzf` 有（6.5 分，2026-10-26）。連 `astral-sh/ruff` 都 404。〔查核補充：API 路徑**區分大小寫**：`BurntSushi/ripgrep` 200、`burntsushi/ripgrep` 404；`junegunn/fzf` 200、`JUNEGUNN/FZF` 404。用我們的小寫 key 查會誤判成「沒資料」。查核用 ecosyste.ms 回的 `full_name`（原始大小寫）重抽 40 個，仍是 0／40。〕
- 結論：對「默默無聞」的新 repo 沒有現成分數。要用就得自己跑 CLI（要 `GITHUB_AUTH_TOKEN`、每個 repo 吃一批 API 額度），只對驗證通過的少數 repo 跑。品質分數主要靠我們自己的沙盒驗證。

### 2.15 RSSHub

- 授權 AGPL-3.0（LICENSE 檔，已驗證）。
- **讀了路由原始碼（commit `1d73c7c`，2026-10-27）**：`github/trending.tsx` 抓 `https://github.com/trending/...` 並用 cheerio 解析；`github/topic.ts` 抓 `github.com/topics/...`；`github/search.ts` 打 `github.com` 網頁搜尋的內部 JSON；`threads/index.ts`、`threads/search.ts` 抓 `www.threads.com/@user`、`/search?q=`；`hackernews/index.ts` 抓 `news.ycombinator.com` HTML；`producthunt/today.tsx` 抓 `www.producthunt.com`。這些都是爬網頁，分別違反 GitHub AUP（只開放研究與封存用途）、Meta 的自動化資料收集條款、YC ToU、Product Hunt 條款。〔查核 2026-10-28：sparse clone 同一個 commit `1d73c7c`（2026-10-27T15:18:49Z）逐檔確認上述抓取目標屬實；`github/trending.tsx` 抓 HTML 後再打 `api.github.com/graphql`。Product Hunt 條款本次沒有重讀，**未驗證**。GitHub AUP §7 的用途清單連 API 取得的資料也適用，見 [channels-hosting.md](channels-hosting.md) 2.1。〕
- 走官方 API 的路由（例如 `npm/package.tsx` 打 `registry.npmjs.org`、`github/repos.ts` 打 `api.github.com`）我們自己寫也只要幾行。**沒有理由裝。**

### 2.16 changedetection.io、Huginn

- changedetection.io：Apache-2.0。定位是「網頁變更監看」，本質是定期抓網頁；我們要的來源都有 API、RSS 或 ETag，自己寫輪詢比較簡單也比較合規。
- Huginn：MIT。Rails 應用，要資料庫與背景 worker。一個人六天，維運成本不值得。

### 2.17 `gh` CLI 與函式庫

- `gh api`：「`--cache <duration>` Cache the response, e.g. "3600s", "60m", "1h"」、「`--paginate` Make additional HTTP requests to fetch all pages of results」、「`--slurp` … return an array of all pages」（[gh api manual](https://cli.github.com/manual/gh_api)，已驗證）。MIT。適合手動探查與一次性回補，管線本身用 Python 直接打 API。
- feedparser（BSD-2-Clause）：`feedparser.parse(url, etag=d.etag)` 沒變時回 `status 304`、`entries` 空（[ETag 文件](https://feedparser.readthedocs.io/en/latest/http-etag/)，已驗證）。RSS 來源只有 PyPI、crates 兩個，標準函式庫 `xml.etree` 也夠（spike 就是這樣做）。
- URL 與套件識別：`packageurl-python`（MIT，purl 標準）、`hosted-git-info`（ISC，npm 自己解析 `repository` 用的）、`giturlparse`（Apache-2.0）、`url-normalize`（MIT）、`w3lib`（BSD-3）、`courlan`（Apache-2.0）。授權都寬鬆。**建議只用 purl 當跨生態系的套件 ID 格式**，正規化規則自己寫（需要 GitHub 專屬規則，見第 4 節）。

---

## 3. 增量抓取與排程

### 3.1 各來源的 cursor／since／ETag

「ETag 實測」欄是本次對每個端點先 GET 拿 ETag／Last-Modified，再帶 `If-None-Match`／`If-Modified-Since` 重打一次的結果。

| 來源 | 形式 | cursor／since | ETag 實測 | 建議頻率 | 備註 |
|---|---|---|---|---|---|
| GitHub search API | API 分頁 | `created:>=T`／`pushed:>=T`，切時段讓每段 ≤1,000 筆；用 `Link` 標頭翻頁 | 本 session 測不到 | 每天 1–2 次，時段重疊 2 小時（索引延遲，未驗證） | 官方：「you should not try to manually construct pagination queries」「use the link headers」「If you page through a list, use a stable sort order」（[Best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)，已驗證）。repo 搜尋不能依建立時間排序，只能切時段 |
| GitHub `/repos/{o}/{r}`、releases | API | ETag | 本 session 測不到 | 每個候選每天最多 1 次 | 官方：「Making a conditional request does not count against your primary rate limit」，條件是回 304 且帶 `Authorization`（同上，已驗證） |
| HN（Algolia） | API | `numericFilters=created_at_i>{cursor}`，按天切片（單次最多 1,000 筆） | 沒有 ETag／LM | 每 1–3 小時 | 每 IP 10,000 次／時（[channels-communities.md](channels-communities.md)）；spike 已實作 |
| HN（Firebase） | API | `/v0/newstories`（最新 500 筆，約 6.6 小時）；`/v0/maxitem` 往回走 | 沒有（`cache-control: no-cache`） | 每 1–3 小時 | 官方：「The current largest item id is at /v0/maxitem. You can walk backward from here」（已驗證） |
| PyPI 新專案 | RSS | ETag | **304** | **每 20–30 分鐘** | 40 筆只涵蓋約 1 小時（[channels-packages.md](channels-packages.md)）；spike 兩次相隔 2 分鐘就換了 ETag。官方：「For periodically checking for new packages … use our RSS feeds. No new integrations should use the XML-RPC APIs as they are planned for deprecation」（[PyPI API](https://docs.pypi.org/api/)，已驗證）。漏掉的用 ecosyste.ms 每天回補（PyPI 延遲約 34 小時；〔查核〕要先取得 ecosyste.ms 書面同意，見 2.10）。查核重測：40 筆涵蓋 49 分鐘（20:28–21:17 UTC），ETag 重打回 304 |
| PyPI JSON | API | ETag | **304**（`max-age=900`） | 依需要 | — |
| crates.io 新 crate | RSS | ETag／Last-Modified | **304／304** | 每 30 分鐘 | RSS「past 60 minutes, but at least 50」〔查核：feed 本身只寫「Newest crates registered on the crates.io package registry」，這句引文出處不明；原始碼證實行為相同：60 分鐘內的全收、至少 50 筆（查核時 79 筆）〕 |
| npm | changes feed | `_changes?since=<seq>`（只回 id） | packument：INM **304**、IMS 200 | 每 30–60 分鐘 | 量太大，黑客松選做 |
| Homebrew analytics | 每日 JSON | 和昨天的 formula 名單做差集 | **304／304**（`max-age=600`） | 每天 1 次 | — |
| dev.to | API | 依 `published_at` | 弱 ETag **304** | 每天 | 黑客松選做 |
| raw.githubusercontent.com | 檔案 | ETag | **304** | — | AUP 的爬取疑慮見 [channels-packages.md](channels-packages.md) 2.1；正式版走 contents API |
| ecosyste.ms | API | `created_after` | 弱 ETag 回 200（**沒生效**）；IMS **304**（`max-age=86400`） | 每天 | 〔查核〕取得書面同意前不排程（2.10） |
| deps.dev | API | — | 沒有 ETag（`max-age=3600`） | — | — |
| GH Archive | 每小時 dump | 最後處理的小時 | **304／304** | — | 資料已沒用（2.13） |

設計重點：

- 每個來源一個 cursor，存在 `state` 表（`source`, `cursor`, `etag`, `last_success_at`）。**cursor 只在整批成功寫入後才前進**，失敗就從舊 cursor 重來；重抓的重複資料由 `(channel, ref)` 去重吸收。spike 第二次跑 Show HN 回 0 則、PyPI 39 筆只新增 1 個候選，證明這樣做是冪等的。
- GitHub 要序列化請求：「you should make requests serially instead of concurrently」（Best practices，已驗證）。

### 3.2 排程放哪裡

| 方案 | 限制（官方） | 費用（官方） | 適合 pickfit 的什麼 |
|---|---|---|---|
| **GitHub Actions cron** | 「The shortest interval you can run scheduled workflows is once every 5 minutes」；「can be delayed during periods of high loads」，「some queued jobs may be dropped」（查核補）；「will only run on the default branch」；public repo「automatically disabled when no repository activity has occurred in 60 days」；job 6 小時 | public repo 標準 runner 免費；private repo Free 方案每月 2,000 分鐘，Linux 2 核 $0.006／分 | 只適合「重建索引、commit 收錄檔」這類輕工作。**條款**：用 GitHub-hosted runner 時，Actions 不得用於「any other activity unrelated to the production, testing, deployment, or publication of the software project associated with the repository」；另一條禁止「disproportionate」負擔的活動，舉例「don't use Actions as a content delivery network or as part of a serverless application, but a low benefit Action could be ok if it's also low burden」（[Additional Products Terms](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features)，已驗證；〔查核補〕原文前者限定 GitHub-hosted runner，後者是「負擔不成比例」的舉例，不是無條件禁止）。定期爬外部來源是灰色地帶 |
| **Modal cron** | `modal.Period`、`modal.Cron`（可設 timezone）；「To activate the schedule, deploy your App」；Period 在重新部署時重算；function 預設 timeout 300 秒、最長 24 小時 | Starter 每月 $30 credits、「5 deployed crons」；CPU $0.0000131／core／秒、記憶體 $0.00000222／GiB／秒；比賽另有 $100 | **發現管線＋事件觸發的驗證**。和 Modal Sandbox 同一個帳號，Python 直接寫 |
| **Cloudflare Cron Triggers** | Free：每帳號 5 個、CPU 10 ms（「Waiting on network requests … does not count toward CPU time」）、子請求 **50**／次（「Each subrequest in a redirect chain counts」）、wall clock 15 分；Paid：250 個、CPU 30 秒（間隔 <1 小時）或 15 分（≥1 小時）、子請求 10,000；「Cron Triggers execute on UTC time」；變更「up to 15 minutes to propagate」 | Free；Paid 每月最低 $5 | 只適合在 MCP Worker 裡做小事（例如每小時清過期資料）。**Free 方案一次只能發 50 個請求，跑不動抓取管線** |
| **本機 cron／launchd** | 電腦要開著、有網路 | $0 | **黑客松最省事**：發現每 30 分鐘一次，跑在念誠的電腦上；GitHub API 在本機沒有本 session 的代理限制 |

**建議**：

1. 黑客松期間：**本機 cron 跑發現**（每 30 分鐘：PyPI RSS、crates RSS；每 2 小時：Show HN；每天 2 次：GitHub search、Homebrew analytics）。錄 demo 前手動跑一次全量。
2. **提交不靠排程**：MCP／Issue Form 收到後直接觸發 Modal function（`.spawn()`）處理，這樣才做得到「幾分鐘內可被推薦」。
3. 之後要 24 小時無人值守，再把發現搬到 Modal cron（Starter 有 5 個 cron 額度，夠用）。
4. GitHub Actions 只做「收錄檔有變 → 重建 MCP 索引」這類跟 repo 本身產出有關的工作。

---

## 4. 去重與正規化

### 4.1 主鍵設計

| 層 | 例子 | 用途 | 穩定性 |
|---|---|---|---|
| **repo ID**（最終主鍵） | `gh:523043277` | 合併、判斷是不是同一個 repo | 改名、轉移都不變（GitHub 的數字 ID） |
| canonical key | `github.com/astral-sh/ruff`（全小寫） | 還沒解析出 ID 前的合併、索引 | 改名會變；變了就把舊值放進 `aliases` |
| 次要 key | `pkg:pypi/ruff`、`pkg:npm/vite`、`web:docs.astral.sh/ruff`、`hn:50258513`、`threads:C8abc` | 把套件、官網、貼文併到同一個候選 | — |
| slug | `ruff` | brief 11 的永久識別 | 只在收錄時給一次，永不改 |

合併用 union-find：任何兩個 key 被同一筆證據連起來（例如 PyPI provenance 指向某 repo、repo 的 `homepage` 指向某官網），就併成同一個候選。**官網 key 只在網域不是共用主機時才拿來合併**（`*.github.io`、`*.vercel.app`、`*.netlify.app` 這類要比到路徑）。

### 4.2 正規化規則（spike `selftest` 25／25 通過）

| 情況 | 輸入 → 輸出 | 依據 |
|---|---|---|
| 大小寫 | `BURNTSUSHI/RIPGREP` → `github.com/burntsushi/ripgrep` | 實測：`git ls-remote` 對大寫、原樣、`.git`、尾斜線 4 種寫法回同一個 HEAD；deps.dev 也轉小寫。**key 用小寫，顯示用 API 回的 `full_name`** |
| `.git` 結尾 | `…/ripgrep.git` → 去掉 | 同上 |
| `www`、`http` | `http://www.github.com/x/y/` → `https://github.com/x/y` | 慣例；本 session 打不到 github.com 網頁，轉址行為未實測 |
| 尾斜線、`#readme`、`?utm_*` | 去掉 | — |
| 子頁 | `/tree/main/packages/vite`、`/releases/download/...`、`/issues` → repo；`tree`／`blob` 後的路徑存成 `subpath` | — |
| git 協定 | `git+https://`、`git+ssh://git@`、`git@github.com:x/y.git`、`git://` → https | npm `repository.url` 常見寫法（實測 npm 9／9 都要套 `git+` 與 `.git` 規則） |
| npm 簡寫 | `github:user/repo`、`user/repo`（只在 npm `repository` 欄位內成立） | npm 文件：「"npm/example", "github:npm/example", "gist:11081aaa281", "bitbucket:user/repo", "gitlab:user/repo"」；「When you publish a package, npm normalizes the repository field to the full object format」（[package.json](https://docs.npmjs.com/cli/v11/configuring-npm/package-json)，已驗證） |
| pip 子目錄 | `https://github.com/charliermarsh/ruff#subdirectory=crates/flake8_to_ruff` | 實測 PyPI `flake8-to-ruff` 就這樣寫 |
| 其他 GitHub 網域 | `raw.githubusercontent.com`、`codeload.github.com`、`api.github.com/repos/x/y` → repo | — |
| GitHub 非 repo 路徑 | `github.com/topics/cli`、`github.com/user`、`/orgs/`、`/sponsors/` → 不是 repo | 保留字清單 |
| GitHub Pages | `user.github.io/repo` → `github.com/user/repo`（提示，要 API 確認） | 7 天 Show HN 有 39 個 |
| GitLab 巢狀 group | `gitlab.com/g/sub/proj/-/tree/main/cli` → `gitlab.com/g/sub/proj` | 以 `/-/` 為界 |
| 連結殼 | `l.threads.com/?u=…`、`l.facebook.com/l.php?u=…` → 解出 `u` | 不發請求 |
| 貼文裡的網址 | 去掉句尾標點與不成對的右括號 | `extract_urls()` |
| 短網址 | 逐跳展開（2.9） | 實測 5／5 |

Show HN 7 天實際觸發的規則（去重前 1,202 個網址）：大小寫 128、`www` 84、GitHub Pages 39、子頁 17、尾斜線 7、補 scheme 2、http→https 1、追蹤參數 1。

### 4.3 改名與轉移

**官方行為（已驗證的部分）**：

- 改名：「all existing information, with the exception of project site URLs, is automatically redirected to the new name」；git「operations targeting the previous location will continue to function as if made on the new location」；**若有人在舊名建新 repo，「redirects to the renamed repository will no longer work」**（[Renaming a repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)）。〔查核補：原文是「If you create a new repository under your account in the future, do not reuse the original name」，指同一帳號重用舊名；同頁另寫「GitHub will not redirect calls to an action hosted by a renamed repository」，Pages 的 project site 網址也不轉。〕
- 轉移：「All links to the previous repository location are automatically redirected」；在舊位置建新 repo 或 fork 時「the redirects to the transferred repository will be permanently deleted」（[Transferring a repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository)）。〔查核補：同頁「we don't redirect GitHub Pages associated with the repository」；轉移前一週超過 100 次 clone 或 Actions 使用、或含 Marketplace action 的 repo，舊的 `OWNER/REPOSITORY-NAME` 會被永久保留不能再用。對「默默無聞」的新 repo 通常不適用，所以舊名被別人佔走、redirect 消失是真實風險。轉移頁沒有提到 Actions 不轉址。〕
- API：「Get a repository」的狀態碼表列了 **301「Moved permanently」**（[Repos API](https://docs.github.com/en/rest/repos/repos#get-a-repository)）。2015 年的公告：用舊位置呼叫 API「receive either a 301 or 307 HTTP redirect, depending on the type of request」，適用於改 repo 名、改帳號名、轉移三種情況（[Preview repository redirects](https://developer.github.com/changes/2015-04-17-preview-repository-redirects/)、[Automatic redirects](https://developer.github.com/changes/2015-07-21-automatic-redirects-for-renamed-repositories/)）。
- 一般原則：「A 301 status code indicates permanent redirection」，要更新存下來的 URL（[Best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)）。
- 〔查核補〕「Get a repository」的路徑參數說明寫「The name is not case sensitive」（owner 與 repo 都是），這是 key 用小寫的官方依據，比 `git ls-remote` 旁證更直接。
- **未驗證**：301 的 `Location` 是不是 `https://api.github.com/repositories/{id}`（印象如此，本 session 打不到）。spike 的 `github` 子命令會印出來。〔查核：官方 REST 文件與 2015 年三篇公告（含 [changes/21](https://developer.github.com/changes/21/)）都沒寫 `Location` 的格式；仍是未驗證。設計上不要依賴它：拿到 301 後照 `Location` 再打一次，從回應的 `id`、`full_name` 取值即可。〕

**實測（本 session 能做的旁證）**：

| 舊名或變體 → 現名 | git HEAD 相同 | ecosyste.ms 舊名 | ecosyste.ms 現名的 `previous_names` 含舊名 | deps.dev |
|---|---|---|---|---|
| `charliermarsh/ruff` → `astral-sh/ruff` | 是 | 404 | 是 | 兩個專案 |
| `jmorganca/ollama` → `ollama/ollama` | 是 | 404 | 是 | 兩個專案 |
| `ggerganov/llama.cpp` → `ggml-org/llama.cpp` | 是 | 404 | 是 | 兩個專案 |
| `ggerganov/whisper.cpp` → `ggml-org/whisper.cpp` | 是 | 404 | **否** | 兩個專案 |
| `twitter/bootstrap` → `twbs/bootstrap` | 是 | 404 | 是 | — |
| `BURNTSUSHI/RIPGREP` → `BurntSushi/ripgrep` | 是 | 找得到 | — | — |

- 套件裡的舊名是真的會遇到：PyPI `flake8-to-ruff` 宣告 `charliermarsh/ruff`；npm `whisper.cpp` 宣告 `ggerganov/whisper.cpp`，而 Homebrew `whisper.cpp` 宣告 `ggml-org/whisper.cpp`。**不解析改名，同一個專案會變成兩筆。**
- 新作品改名很常見：Show HN 7 天、ecosyste.ms 查得到的 271 個 repo 中 **39 個（14%）** 的 `previous_names` 有別的名字（例：`vinhnx/vtagent` → `vinhnx/VTCode`、`byerlikaya/claude-starter-kit` → `crewforth/crewforth`）。〔查核：用 spike 上次的輸出離線重算，39／271 屬實；其中 17 個 owner 也變了（轉移或帳號改名）。注意 `previous_names` 會含現名本身（ruff 的清單是 `astral-sh/ruff`、`charliermarsh/ruff`），要排除現名再算。另外這 271 個的貼文網址全是現名，7 天內因「貼文用舊名」造成的重複是 0；14% 是「這個 repo 曾改過名」，不是「重複率」。〕
- **做法**：每個 repo 候選都打一次 `GET /repos/{o}/{r}`（不自動 follow），遇到 301 就記下 `Location`、再打一次拿現名與 ID，舊名進 `aliases`。之後的更新都用 ID 查。這一步每個 repo 1–2 次 core 請求。

### 4.4 fork、mirror、template

- API：「The parent and source objects are present when the repository is a fork」「parent is the repository this repository was forked from, source is the ultimate source for the network」（[Repos API](https://docs.github.com/en/rest/repos/repos#get-a-repository)，已驗證）。
- 規則：`fork: true` 預設丟掉；**例外**是提交者明說是「仍在維護的 fork」，而且 fork 有自己的 release。保留時記 `fork_of: <source 的 ID>`，不和上游合併。
- `is_template: true`、`mirror_url` 非空：丟掉（mirror 改收原站）。
- 實測 Show HN 7 天 271 個有資料的 repo：fork 2、template 3。fork 在作者自己發表的管道裡很少，主要出現在 GitHub search。

### 4.5 monorepo 子目錄

- npm 有 `repository.directory`（文件：「you can specify the directory in which it lives」，已驗證）；實測 `vite` → `packages/vite`、`@openai/codex` → `codex-cli`。
- PyPI 沒有標準欄位，但有人用 pip 的 `#subdirectory=`（`flake8-to-ruff`）。
- 建議：**候選以 repo 為單位**，子目錄放 `subpaths[]`。只有一個 repo 裡真的有好幾個獨立工具時，才拆成 `github.com/o/r#path` 的 key（黑客松先不做）。
- 反方向（一個 repo 發多個套件）也常見：PyPI 39 個新專案裡有 2 個 repo 各發了 3 個套件（`serp-tracing`、`serp-redis`、`serp-jwt` 都是 `avijitbhuin21/serpentine`）。合併成一筆候選，`packages[]` 列三個。

### 4.6 套件名 → repo

優先順序（高到低）：

| 順序 | 方法 | 可信度 | 實測 |
|---|---|---|---|
| 1 | 簽章 provenance：PyPI Integrity API `publisher.repository`；npm `dist.attestations` 的 SLSA `workflow.repository` | 高（發布流程證明） | PyPI 新專案 27／39 有；與自填 0 衝突。npm 範例 5／9 有 |
| 2 | 自填欄位：PyPI `project_urls`，標籤先依 PEP 753 正規化（「deleting all ASCII punctuation and whitespace, and then converting the result to lowercase」），找 `source`（別名 `repository`、`sourcecode`、`github`），再找 `homepage`；npm `repository`（含 `directory`）；Homebrew `urls.head.url` → `urls.stable.url` → `homepage` | 中（自填，可能填錯、冒名、過期） | PyPI 範例 10／11；npm 9／9；Homebrew 8／8（全部靠 `urls.head`） |
| 3 | 反查：ecosyste.ms packages lookup `?repository_url=`（〔查核〕要先取得書面同意）；替代 deps.dev `projects/{key}:packageversions` | 中 | Show HN 的 386 個 GitHub repo 有 78 個查得到套件（ecosyste.ms）；deps.dev 對大 repo 截斷在 1,500 筆（2.10） |
| 4 | 交給模型讀 README 判斷 | 低 | — |

- PEP 753 標籤與別名：[Well-known Project URLs](https://packaging.python.org/en/latest/specifications/well-known-project-urls/)（已驗證）。
- 實測例外：`open-webui` 的 `project_urls` 是空的，**只有 provenance 對得到 repo**；`llm` 的 repo 只寫在 `Homepage`。
- provenance 與自填不一致時，以 provenance 為準，並把自填值記進 `aliases`（可能是舊名）。

### 4.7 同一專案出現在 Threads、GitHub、HN：合併成一個正本

1. 每個來源先產生一筆 **source 記錄**：`channel`、`ref`（來源內穩定 ID）、`url`（原始寫法）、`seen_at`（來源自己的時間）、`fetched_at`（我們抓到的時間）、少量數字訊號。
2. 從 source 抽出所有網址 → 正規化 → 得到一組 key。
3. key 解析：repo key → GitHub API → `gh:<id>`；套件 → 4.6；官網 → 如果某個 repo 的 `homepage` 指向它就併過去。
4. union-find 合併；合併後候選的 `first_seen_at = min(seen_at)`，這就是「作者第一次發文」的時間，可以算 brief 第 10 節的「從作者發文到可被推薦花了多久」。
5. **source 只增不改**。同一個 `(channel, ref)` 重抓時只更新 `fetched_at` 與訊號，不新增。
6. 對外（收錄檔、MCP 回應）只公開「來源連結＋時間」，不轉載貼文全文；Threads 只放 permalink 給 oEmbed 嵌入。

實測（Show HN 7 天）：**19 個 repo 被 2 則以上的 Show HN 貼文提到**（例：`mvikmanners/aw1-circuit-breaker` 在 10-21 與 10-22 各發一次），合併後一筆候選、兩筆 source。同一則貼文的網址欄與內文都指向同一個 repo 的情況，由 `(channel, ref)` 去重吸收。跨管道合併（Show HN × PyPI RSS）這次是 0，因為 PyPI RSS 只有 1 小時窗；要等 GitHub search 與 Homebrew tap 也接上才會常見。

---

## 5. 統一候選格式（JSON Schema 草案）

### 5.1 Schema

候選（candidate）和收錄檔（brief 11 的軟體檔案）分開：候選量大、變動快，放 SQLite（或 D1）；只有收錄的才寫成 git 裡的 YAML。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "pickfit.candidate/v0",
  "title": "pickfit 候選（草案）",
  "type": "object",
  "required": ["schema", "candidate_id", "kind", "status", "first_seen_at", "sources"],
  "properties": {
    "schema": { "const": "pickfit.candidate/v0" },
    "candidate_id": { "type": "string", "description": "合併用 key。repo：小寫 host/owner/repo；其他：web:host/path、pkg:…" },
    "repo_id": { "type": ["string", "null"], "pattern": "^(gh|gl|cb):[0-9]+$", "description": "託管平台的數字 ID；改名轉移不變；解析出來後是最終主鍵" },
    "kind": { "enum": ["repo", "web", "package_only"] },
    "canonical_url": { "type": "string", "format": "uri", "description": "目前的正式網址（GitHub 用 API 回的 full_name）" },
    "aliases": { "type": "array", "items": { "type": "string" }, "description": "舊名、變體、原始寫法" },
    "subpaths": { "type": "array", "items": { "type": "string" } },
    "fork_of": { "type": ["string", "null"] },
    "homepage": { "type": ["string", "null"] },
    "packages": { "type": "array", "items": { "$ref": "#/$defs/package" } },
    "status": { "enum": ["discovered", "triaged", "extracted", "verified", "failed", "rejected", "needs_info", "merged"] },
    "status_history": { "type": "array", "items": { "$ref": "#/$defs/transition" } },
    "merged_into": { "type": ["string", "null"] },
    "priority": { "type": "integer", "description": "提交的候選排前面；不影響分數" },
    "first_seen_at": { "type": "string", "format": "date-time" },
    "last_seen_at": { "type": "string", "format": "date-time" },
    "sources": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/source" } },
    "repo_meta": { "$ref": "#/$defs/repo_meta" },
    "triage": { "$ref": "#/$defs/judgement" },
    "extraction_ref": { "type": ["string", "null"], "description": "抽取結果（軟體檔案草稿）的 ID" },
    "verification_ref": { "type": ["string", "null"] },
    "slug": { "type": ["string", "null"], "description": "收錄時才給；永不改" }
  },
  "$defs": {
    "source": {
      "type": "object",
      "required": ["channel", "ref", "url", "fetched_at"],
      "properties": {
        "channel": { "enum": ["github_search", "hn_show", "pypi_new", "crates_new", "npm_new", "brew_tap", "awesome_list", "submission_mcp", "submission_issue", "submission_form"] },
        "ref": { "type": "string", "description": "來源內穩定 ID：hn:50258513、pkg:pypi/llm、issue:12、threads:C8abc" },
        "url": { "type": "string", "description": "原始寫法（正規化前）" },
        "role": { "enum": ["story_url", "story_text", "package", "repo", "submitted_link", "embed_only"] },
        "seen_at": { "type": ["string", "null"], "format": "date-time", "description": "來源自己的時間" },
        "fetched_at": { "type": "string", "format": "date-time" },
        "submitter": {
          "type": ["object", "null"],
          "properties": {
            "type": { "enum": ["anonymous", "github_user", "verified_author"] },
            "github_login": { "type": ["string", "null"] }
          }
        },
        "signals": { "type": "object", "description": "只放數字與短欄位（points、downloads、title），不放全文" },
        "terms": { "type": "string", "description": "受哪份條款約束，例：hn-api、github-api、pypi-api、threads-oembed-display-only" }
      }
    },
    "package": {
      "type": "object",
      "required": ["purl", "mapping"],
      "properties": {
        "purl": { "type": "string", "description": "pkg:pypi/llm、pkg:npm/vite、pkg:brew/ripgrep" },
        "mapping": { "enum": ["provenance", "declared", "reverse_lookup", "formula", "model"] },
        "subpath": { "type": ["string", "null"] },
        "downloads": { "type": ["object", "null"] }
      }
    },
    "transition": {
      "type": "object",
      "required": ["status", "at", "by"],
      "properties": {
        "status": { "type": "string" },
        "at": { "type": "string", "format": "date-time" },
        "by": { "type": "string", "description": "rules-v0、muse-spark-open-1026、muse-spark-1.3、sandbox、human:<login>" },
        "reason": { "type": ["string", "array", "null"] }
      }
    },
    "judgement": {
      "type": ["object", "null"],
      "properties": {
        "result": { "enum": ["pass", "suspect", "drop", "unknown"] },
        "reasons": { "type": "array", "items": { "type": "string" } },
        "kind": { "type": ["string", "null"], "description": "cli_tool、local_server、library_sdk… 由初篩模型填" },
        "demo_category": { "enum": ["dev_cli", "local_ai", "other", null] },
        "confidence": { "enum": ["high", "medium", "low", null] },
        "model": { "type": ["string", "null"] },
        "at": { "type": "string", "format": "date-time" }
      }
    },
    "repo_meta": {
      "type": ["object", "null"],
      "properties": {
        "full_name": { "type": "string" },
        "fork": { "type": "boolean" }, "archived": { "type": "boolean" }, "is_template": { "type": "boolean" },
        "has_readme": { "type": "boolean" }, "license": { "type": ["string", "null"] },
        "stars": { "type": "integer" }, "created_at": { "type": "string" }, "pushed_at": { "type": "string" },
        "latest_release_at": { "type": ["string", "null"] },
        "via": { "enum": ["github_api", "ecosystems"] },
        "fetched_at": { "type": "string", "format": "date-time" }
      }
    }
  }
}
```

spike `ch_integration_merge.py` 輸出的 JSONL 就是這個格式的子集（`pickfit.candidate/v0`）。

### 5.2 狀態機

```
discovered ──規則──► rejected（fork、archived、template、沒 README、非可執行…）
    │
    ├──規則（只有官網或 Threads、沒 repo）──► needs_info
    ▼
 triaged ──開放權重模型（不是軟體、不在兩個類別）──► rejected
    │
    ▼
extracted（Muse Spark 抽出軟體檔案草稿）
    │
    ├──沙盒驗證成功──► verified ──► 給 slug、寫入 YAML 收錄檔
    └──沙盒驗證失敗──► failed（可重試 1 次；仍失敗就不收錄，原因回給提交者）

任何狀態 ──發現是重複──► merged（merged_into 指向正本）
verified ──30 天後或有新 release──► 重新驗證（brief 13：維護訊號）
```

- 每次轉換寫一筆 `status_history`（`at`、`by`、`reason`），這就是 demo 和 README 要的 trace。
- GUI、需要權限、特定 OS 的軟體：沙盒驗證不了就停在 `extracted`，標「未驗證」，不假裝通過（brief 13）。

### 5.3 對照 brief 第 11 節的檔案欄位

| brief 11 欄位 | 從候選的哪裡來 | 哪一層填 |
|---|---|---|
| `slug` | 收錄時從 repo 名產生、檢查唯一；之後改名只動 `aliases` | verified → 收錄 |
| `name` | 抽取（模型）＋ repo 名 | extracted |
| `summary` | 抽取 | extracted |
| `homepage` | `homepage`（GitHub API 的 `homepage`、PyPI `project_urls.homepage`、提交者給的） | discovered／extracted |
| `repo` | `canonical_url`（現名）；**建議加 `repo_id`** | discovered |
| `platforms` | 抽取＋release assets＋驗證結果 | extracted／verified |
| `install` | 抽取的草稿，驗證後換成實際成功的步驟 | verified |
| `pricing` | 抽取 | extracted |
| `open_source` | `repo_meta.license` 非空 | discovered |
| `license` | `repo_meta.license`（API 值，不用模型） | discovered |
| `processing` | 抽取 | extracted |
| `last_release` | GitHub releases API | discovered／定期更新 |
| `verification` | `verification_ref` | verified／failed |
| `scores` | 品質：驗證＋文件＋維護；知名度：`repo_meta.stars`、`packages[].downloads` | 收錄時計算 |
| `sources` | `sources[]` 的 `channel`、`url`、`seen_at`（只放連結與時間） | 全程累積 |

**建議 brief 11 補四個欄位**：`repo_id`（去重）、`aliases`（改名歷史）、`packages`（purl 清單，給 `get_install_guide` 用）、`first_seen_at`（算「發文到可被推薦」）。

---

## 6. 漏斗與成本控制

### 6.1 每天幾千筆從哪來

| 來源 | 每天新項目（量測值） | 出處 |
|---|---|---|
| npm 新套件 | 約 3,900（7 天 27,393） | [channels-packages.md](channels-packages.md) |
| PyPI 新專案 | 約 900（22.4 小時 901 個） | 同上 |
| crates.io 新 crate | 約 850 | 同上 |
| Homebrew 第三方 tap 新 formula | 約 135（30 天 4,066） | 同上 |
| Show HN | 約 142（7 天 991，本次實測） | 本筆記第 8 節 |
| GitHub search（兩個類別的 16 條 query） | 未實測（本 session 打不到） | [channels-hosting.md](channels-hosting.md) |

全接約 6,000／天；黑客松實際只接 Show HN、PyPI、Homebrew tap、GitHub search，估 1,500–3,000／天。下表以 **3,000／天** 估算。

### 6.2 每一層

| 層 | 每天數量（估） | 做什麼 | 時間（估） | 成本（估） | 依據 |
|---|---|---|---|---|---|
| 0 收集＋正規化＋去重 | 3,000 → 約 2,600 | 程式；GitHub `/repos` 解析（含 301） | GitHub 約 2,600 次 core 請求（上限 5,000／時），序列約 15–25 分鐘 | $0 | 去重率：Show HN 同 repo 重複 19／389；PyPI 一 repo 多套件 33 → 29 |
| 1 規則初篩 | 2,600 → 約 500 | 沒 repo（PyPI 15%）、fork、archived、template、沒 README、**不是可執行檔**（沒 `bin`／`console_scripts`／`bin_names`／release asset）、不在兩個類別的 topic 與關鍵字 | 秒級 | $0 | Show HN 有 metadata 的 repo：drop 13%、suspect 11%。套件可執行比例 PyPI 12／30、npm 7／30、crates 3／30（[channels-packages.md](channels-packages.md)）。兩類別篩選比例**未量測**，假設留一半 |
| 2 開放權重初篩 | 500 → 約 150 | Muse Spark Open @ Baseten：是不是可用軟體、哪一類 | 500 次；Baseten 15 或 120 RPM → 4–35 分鐘 | 500 × $0.0042 ≈ **$2.1／天**（Baseten credits） | 單價與通過率 30%：[meta-usage-design.md](meta-usage-design.md) 4.1 |
| 3 抽取 | 150 → 約 140 | `muse-spark-1.3` 讀 README 等，填欄位 | 3,000 RPM 不是瓶頸；並行 10 約 10–20 分鐘 | 150 × $0.022–0.025 ≈ **$3.3–3.8／天** | 同上 4.2 |
| 4 沙盒驗證 | **每天上限 30–50**（依優先順序） | 驗證 agent＋Modal Sandbox | 每筆 4–8 分鐘；10 並行，30 筆約 15–25 分鐘 | 每筆 agent $0.10–0.27＋沙盒約 $0.02 → 30 筆 **$3.6–8.7／天** | [meta-usage-design.md](meta-usage-design.md)、[sandbox-compare.md](sandbox-compare.md) |

- **合計約 $9–15／天**（Meta 約 $6–12＋Baseten 約 $2＋Modal 沙盒約 $0.6）。6 天約 $55–90；其中 Meta 部分 6 天約 $38–72，在 Meta $150 credits 內。〔查核修正：原寫「Meta $7–13」，把沙盒費算進 Meta。逐項：抽取 $3.3–3.8＋驗證 agent 30 × $0.10–0.27 = $3.0–8.1。〕
- 如果 140 筆全驗證：光驗證每天 $17–41（agent＋沙盒）；Meta 部分每天約 $17–42，6 天約 $104–250。**估算低端仍在 $150 內，中段以上就超過**。〔查核修正：原寫「6 天會超過 $150」，只在估算中高段成立。〕**所以驗證要設每日上限**，優先順序：提交的 > 兩個類別且初篩高信心 > 其他。
- 所有成本是估算：Meta 模型推理 token 未實測（沒有 key），兩類別篩選比例未量測。
- 成本控制在程式端：每層一個每日上限與累計花費（Meta 的 Spend Limit「只是通知，不會自動停止扣款」，見 [hackathon-rules.md](../../hackathon-rules.md) 第 6 節）。

---

## 7. 提交入口設計

### 7.1 流程

```
MCP submit_software ─┐
GitHub Issue Form ───┼─► 佇列（GitHub issue 或 D1）─► 正規化＋短網址展開 ─► 解析
網頁表單（之後） ────┘                                            │
                                         ┌─────────────────────────┼──────────────────────────┐
                                     repo／套件頁／HN item         只有官網                  只有 Threads
                                         │                          │                          │
                                     GitHub API 解析              抓該頁找 repo              needs_info：
                                     （ID、現名、fork…）          找不到 → 交模型判斷        請補 repo 或官網
                                         ▼
                              合併進既有候選（重複提交不加分）
                                         ▼
                     規則初篩 → 開放權重初篩 → 抽取 → 沙盒驗證（優先佇列）
                                         ▼
                         verified：收錄、通知提交者；failed：不收錄，附原因
```

### 7.2 怎麼確認連結指向「可用的軟體」

依序，任何一步失敗就停：

1. 網址能解析成 repo、套件或官網，而且存在（GitHub API 200／301；不存在回 404）。
2. 不是 fork、archived、template；有 README（4.4）。
3. 有安裝路徑：release assets、`bin`／`console_scripts`／`bin_names`、Homebrew formula，或 README 裡的安裝段（交模型判斷）。
4. 開放權重模型判斷是軟體、屬於哪一類。
5. 沙盒照 README 裝起來並執行成功。**驗證失敗不收錄**。
6. 收錄後由同一套規則計分；提交本身不給分。

### 7.3 防灌水

| 手段 | 做法 | 成本 | 黑客松 |
|---|---|---|---|
| 同 repo 合併 | 重複提交只多一筆 source，不重跑驗證、不加分 | 已在合併邏輯裡 | 做 |
| 每日總量上限 | 驗證佇列每天最多 N 筆（例：提交 20、主動發現 30） | 一個計數器 | 做 |
| 短時間限流 | MCP：Worker rate limit binding（key 用 MCP session 雜湊，60 秒窗，不存 IP）；Issue Form：GitHub 帳號＋必要時 interaction limits | 0.5 h | 做 |
| 機器人 | 網頁表單加 Turnstile（免費） | 0.5 h | 有表單才做 |
| 驗證作者身分（選用，給「作者提交」標記） | (a) GitHub OAuth 登入（不用要任何 scope：「(no scope) Grants read-only access to public information」，[OAuth scopes](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)，已驗證），比對登入帳號＝repo owner 或 org 公開成員；(b) 請作者在 repo 加一個 topic 或檔案（例：topic `pickfit-verify-<code>`），用 API 確認；(c) PyPI／npm provenance 證明套件與 repo 是同一人發布 | (b) 1 h；(a) 2–3 h | 之後擴充；黑客松最多做 (b) |
| 內容規則 | 丟掉明顯違反第三方 ToS 的工具（Codeberg 實測有一週 9 個「Bulk-create … accounts, harvest tokens & cookies」repo，見 [channels-hosting.md](channels-hosting.md)）、醫療／政治／戰爭類（比賽禁止） | 關鍵字＋模型 | 做 |
| 人工抽查 | 每天看全部提交的 failed 原因＋隨機 10% 的 verified；README 寫明「黑客松期間由驗證結果與人工抽查把關」（brief 13） | 每天 15 分鐘 | 做 |
| 沙盒隔離 | 驗證時網路只在安裝階段開；不放任何金鑰 | 見 [sandbox-compare.md](sandbox-compare.md) | 做 |

### 7.4 GitHub Issue Form 草稿（只示範欄位）

```yaml
name: 推薦一個軟體
description: 貼 GitHub repo、套件頁或官網；pickfit 會讀懂、在沙盒裝起來驗證，通過才收錄
labels: [submitted]
body:
  - type: input
    id: url
    attributes: { label: 連結（GitHub repo、PyPI／npm／Homebrew 頁、官網、HN 貼文） }
    validations: { required: true }
  - type: input
    id: social
    attributes: { label: Threads／X 貼文連結（選填，只用來嵌入展示） }
  - type: dropdown
    id: role
    attributes: { label: 你是作者嗎？, options: [是, 不是] }
  - type: textarea
    id: note
    attributes: { label: 它解決什麼問題、適合誰（選填） }
```

處理的 workflow 只用環境變數把 `github.event.issue.body` 交給 Python 腳本（2.2 的 script injection）。〔查核：workflow 只做轉送，模型呼叫與驗證放在 Modal，理由見 2.2 的 Actions 條款。〕

---

## 8. 實測

兩個腳本都在 `spikes/`，只用 Python 標準函式庫、不含金鑰。執行時間 2026-10-27 20:20–20:50 UTC（台北 10-28 04:20–04:50）。選填環境變數：`GH_TOKEN`（GitHub API）、`PICKFIT_CONTACT=<email>`（放進 User-Agent，ecosyste.ms 以 `?mailto=` 進 polite pool）。

### 8.1 `spikes/ch_integration_normalize.py`：URL 正規化、改名偵測、套件 → repo

```bash
python3 spikes/ch_integration_normalize.py selftest   # 離線，25 個 URL 寫法
python3 spikes/ch_integration_normalize.py github     # 7 組改名／大小寫；有 GH_TOKEN 且 API 打得通時印 301 與 Location
python3 spikes/ch_integration_normalize.py packages   # PyPI 11、npm 9、Homebrew 8 個套件
python3 spikes/ch_integration_normalize.py short      # 5 個真實短網址
python3 spikes/ch_integration_normalize.py recent     # PyPI 最新 40 個專案
python3 spikes/ch_integration_normalize.py all        # 全部，約 1 分鐘
```

結果：

| 項目 | 數字 |
|---|---|
| selftest | 25／25 通過（另加 `extract_urls` 斷言） |
| GitHub API（本 session） | 全部 403（代理限制），自動改走 git＋ecosyste.ms |
| 舊名與現名 git HEAD 相同 | 7／7（含大小寫變體） |
| ecosyste.ms 舊名 lookup | 5 組改名全部 404；現名 `previous_names` 含舊名 4／5 |
| deps.dev | 4 組改名都是兩個獨立專案 |
| 不存在的 repo | git 要求帳密（GitHub 對不存在與私有 repo 都不洩漏存在與否） |
| PyPI 範例 11 個 | 自填對到 repo 10（`project_urls` 6、退回 homepage 4）；provenance 5，一致 4，另 1 個（`open-webui`）只有 provenance |
| npm 範例 9 個 | `repository` 9／9（全部要套 `git+`、`.git` 規則）；provenance 5，一致 5；`directory` 2 個 |
| Homebrew 範例 8 個 | `urls.head` 8／8 |
| 宣告舊名的套件 | PyPI `flake8-to-ruff`、npm `whisper.cpp`：本 session 判定不出現名（需要 API 301） |
| 短網址 | 5／5 展開（git.io → GitHub repo；tinyurl → 裸 IP） |
| PyPI 最新 39 個專案 | 自填 repo 29（全是 GitHub）；provenance 27，與自填一致 23、只有 provenance 4、衝突 0；任一方式對到 repo 33／39；去重後 29 個 repo（2 個 repo 各 3 個套件） |

PyPI 新專案抽樣 5 筆（看品質，描述取自 PyPI `summary`）：`staal`（staalc 編譯器與 Python 介面）、`dbt-atlatl`（dbt-duckdb 外掛）、`macos-photos-cleanup`（在本機瀏覽器介面整理 macOS 照片庫）、`serp-tracing`／`serp-redis`／`serp-jwt`（同一個 monorepo 的三個套件）、`own-computer-use-mcp`（Windows 上自架的 computer-use MCP server）。可直接拿來用的工具約 2／5，其餘是外掛或函式庫，和 [channels-packages.md](channels-packages.md) 的 12／30 有 console_scripts 一致。

### 8.2 `spikes/ch_integration_merge.py`：增量抓取 → 統一候選 → 合併 → 規則初篩

```bash
PICKFIT_CONTACT=<email> python3 spikes/ch_integration_merge.py --reset      # 首次：Show HN 7 天＋PyPI RSS，約 50 秒
PICKFIT_CONTACT=<email> python3 spikes/ch_integration_merge.py              # 增量：只抓 cursor 之後的
python3 spikes/ch_integration_merge.py --days 1 --out /tmp/x.jsonl --state /tmp/s.json
```

輸出候選 JSONL 與狀態檔都在系統暫存目錄（`/tmp/pickfit_ch_integration_*`），不寫進 repo。

首次（7 天）：

| 項目 | 數字 |
|---|---|
| Show HN 貼文 | 991（沒有網址 5） |
| 有連到 repo 的貼文 | 385（39%）；連結在網址欄 347、在內文 50 |
| 去重後 repo | 389（GitHub 386、GitLab 1、自架 GitLab 1、Codeberg 1） |
| 只有官網等網頁 | 698 個 key；GitHub Pages 26；HN item 5；Threads 1 |
| 同一 repo 被多則貼文提到 | 19 |
| 觸發的正規化規則 | 大小寫 128、`www` 84、Pages 39、子頁 17、尾斜線 7、補 scheme 2、http 1、追蹤參數 1 |
| 短網址 | 0 |
| PyPI RSS | 39 個專案 |
| 合併後候選 | 1,148 |
| ecosyste.ms 查得到（GitHub repo） | 278／415（Show HN 部分 271／386 = 70%） |
| 反查到套件（Show HN 的 GitHub repo） | 78／386（npm 48、Go 17、cargo 15、PyPI 9、Homebrew 1；扣掉 Go 66） |
| Show HN repo 的星數（271 個有資料） | 中位數 **2**；<100 星 238；≥1,000 星 11；2026 年建立 237 |
| 已改名或轉移過 | 39／271（14%） |
| 規則初篩（Show HN 的 386 個 GitHub repo） | pass 205、suspect 30、drop 36、unknown 115（ecosyste.ms 查無） |
| drop 原因（全部候選） | 沒 README 34、template 3、fork 2 |
| Scorecard API 覆蓋 | 隨機 40 個：0 |

第二次（增量，相隔約 1 分鐘）：Show HN cursor 之後 0 則；PyPI RSS ETag 已變（回 200），39 個專案只新增 1 個候選，其餘被 `(channel, ref)` 去重。候選庫 1,148 → 1,149。

抽樣 5 筆（通過或疑似的 GitHub repo，依字母等距抽）：

| repo | 結果 | 星 | 建立 | 授權 | 套件 | HN points | 標題 |
|---|---|---|---|---|---|---|---|
| `0xarx/hashling` | pass | 0 | 2026-10-19 | MIT | — | 1 | open-source Mac security agent |
| `codyhxyz/playlist-search-extension` | pass | 0 | 2026-03-08 | AGPL-3.0 | — | 3 | YouTube 播放清單過濾（瀏覽器擴充） |
| `jp-um/university_of_malta_latex_dissertation_template` | suspect（`template`） | 80 | 2018-05-07 | GPL-3.0 | — | 2 | LaTeX 論文範本 |
| `pagel-s/termcraft` | pass | 252 | 2026-03-21 | AGPL-3.0 | `pkg:cargo/termcraft` | 7 | 終端機 2D 生存遊戲 |
| `sturnus-dev/sturnus` | pass | 6 | 2026-03-29 | MIT | `pkg:cargo/sturnus` | 1 | 依延遲分流的 LLM load balancer |

品質判斷：5 筆裡 `hashling`、`termcraft`、`sturnus` 是真的可裝的工具（後兩個有 cargo 套件）；論文範本被名稱規則標成 suspect，正確；瀏覽器擴充不在兩個類別，要靠模型初篩剔除。**規則只能刷掉明顯的雜訊，「是不是兩個類別的可用軟體」仍要模型判斷。**

**沒辦法實測的**：GitHub API（含 301）、GitHub search、GraphQL 批次查詢（本 session 代理限制）；github.com 網頁的 http／www 轉址（代理 403）。

---

## 9. 結論

### 9.1 黑客松期間值得接

| 項目 | 理由 | 預估工時 |
|---|---|---|
| 正規化＋GitHub 解析（`repo_id`、301、fork／archived／template） | 所有管道的共同入口；新作品 14% 改過名，不做就會重複收錄 | 3–4 h（spike 的規則可直接參考重寫） |
| 套件 → repo（provenance 優先、PEP 753 標籤、npm `repository`／`directory`、Homebrew `urls.head`） | Homebrew tap 與 PyPI 是本地 AI、CLI 兩類的主要來源（[channels-packages.md](channels-packages.md)） | 2 h |
| 候選庫（SQLite）＋狀態機＋`sources[]` | 增量、冪等、可追溯；demo 的 trace 與「發文到可被推薦」時間都從這裡算 | 2–3 h |
| 增量 cursor 與 ETag（Show HN Algolia、PyPI RSS、crates RSS、Homebrew 差集、GitHub search 切時段） | 每個來源 0.5–1 h | 3–4 h |
| 規則初篩 | 免費刷掉 13–25% 的明顯雜訊，省模型錢 | 1–2 h |
| 排程：本機 cron＋提交事件觸發 Modal | 最省事；提交要「幾分鐘內」 | 1 h |
| 提交：MCP `submit_software`＋GitHub Issue Form（同一佇列） | demo 第 5 幕；Issue Form 幾乎零成本、有身分 | 3–4 h |
| ~~ecosyste.ms（備援、`previous_names`、反查套件）~~ → 〔查核修正〕repo → 套件反查改用 deps.dev `:packageversions`；ecosyste.ms 取得書面同意後才接 | 跨管道合併的關鍵；ecosyste.ms Terms §9 要求書面同意（2.10） | 1–2 h |

合計約 16–22 h（〔查核〕數字不變，只是第 8 列換成 deps.dev）。若時間不夠，依序砍：Issue Form（只留 MCP）→ crates RSS → 套件反查。

### 9.2 之後擴充

| 項目 | 條件 |
|---|---|
| 網頁表單＋Turnstile | 公開展示頁做了才做 |
| 作者身分驗證（OAuth 或 topic 驗證碼）、GitHub App 安裝（同時證明控制權並收 release webhook） | 開放提交後有灌水再做 |
| Modal cron 無人值守 | 黑客松後要持續更新時 |
| OpenSSF Scorecard CLI | 只對 verified 的 repo 跑，當品質分數的一部分 |
| deps.dev | 要支援 Go、Maven、NuGet 的 provenance 時 |
| 官網 → repo 自動找連結 | `kind: web` 候選累積多了再做 |

### 9.3 要避開

| 項目 | 原因 |
|---|---|
| RSSHub | 相關路由（GitHub trending／topic／search、Threads、HN、Product Hunt）都是爬網頁（讀過原始碼），違反各來源條款；AGPL-3.0 |
| GH Archive／GitHub events | 實測 2026-10-27 一小時 0 筆新 repo 事件 |
| changedetection.io、Huginn | 本質是爬網頁或維運太重；我們的來源都有 API／RSS |
| 用 GitHub Actions 定期爬外部來源，或在 Actions 裡處理提交 | Actions 條款：用 GitHub-hosted runner 時，限定與該 repo 軟體專案的產出、測試、部署、發布有關的活動；造成不成比例負擔的用法（例如當 serverless 應用的一部分）也不行（〔查核〕補上原文的限定條件） |
| 未取得書面同意就用 ecosyste.ms API | 〔查核新增〕Terms §9 禁止未經書面同意的腳本擷取，§11(c) 只授權個人使用 |
| Cloudflare Workers Free 跑抓取管線 | 每次最多 50 個子請求（轉址每跳都算）；Paid（$5／月）才有 10,000 |
| 用 deps.dev 或 ecosyste.ms 的 key 當主鍵 | 舊名、新名會變成兩筆 |
| 只靠 Threads 連結收錄 | 讀不到內容，oEmbed 條款禁止拿來做顯示以外的事 |
| 把提交次數或「作者自薦」當品質訊號 | 會被刷；分數只看驗證與規則 |

---

## 10. 給主控者：需要決定或修正的地方

1. **brief 4.1 與 5 的「貼 Threads 連結」**：改成「貼 GitHub（或官網）連結，可另附 Threads 貼文」。和 [channels-meta-platforms.md](channels-meta-platforms.md) 的結論一致。
2. **ecosyste.ms 的條款與 CC BY-SA**：〔查核新增〕先決問題是 Terms §9 要求腳本存取前取得書面同意，要不要寄信由主控者決定（同 [channels-packages.md](channels-packages.md) 2.12）。拿到同意後才談授權：若把它的欄位（星數、`previous_names`、套件清單）寫進公開的 YAML，衍生資料可能要 BY-SA。建議 GitHub API 為主、ecosyste.ms 只做查詢不存值（[channels-packages.md](channels-packages.md) 第 6 節同一問題）。
3. **brief 11 補欄位**：`repo_id`、`aliases`、`packages`、`first_seen_at`（5.3）。
4. **候選與收錄檔分開存**：候選（每天上千筆、狀態常變）放 SQLite；只有 verified 寫 YAML 進 git。否則 commit 歷史會被候選淹沒。
5. **提交用的公開 repo**：pickfit repo 11/4 前是 private，外人開不了 issue。要不要另開一個公開的 submissions repo？
6. **驗證每日上限**：建議提交 20、主動發現 30，讓 6 天總花費落在 $55–90。
7. **GitHub token**：正式管線需要 fine-grained token（只要公開 repo 唯讀）。這個雲端 session 打不到 GitHub API，發現管線要在本機或 Modal 跑。

---

## 11. 來源

查證日期一律 2026-10-28（台北）。「實測」＝本次親自打 API 或下載。

**GitHub**
- REST best practices（redirect、conditional request、pagination、序列化）：<https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api>（已驗證）
- REST rate limits（60／5,000／GITHUB_TOKEN 1,000／secondary）：<https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api>（已驗證）
- Troubleshooting（404 代替 403）：<https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api>（已驗證）
- Get a repository（fork 的 parent／source、301）：<https://docs.github.com/en/rest/repos/repos#get-a-repository>（已驗證）
- Renaming a repository：<https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository>（已驗證）
- Transferring a repository：<https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository>（已驗證）
- API redirects 公告（2015）：<https://developer.github.com/changes/2015-04-17-preview-repository-redirects/>、<https://developer.github.com/changes/2015-07-21-automatic-redirects-for-renamed-repositories/>（已驗證）
- Events that trigger workflows（schedule）：<https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows>（已驗證）
- Actions billing：<https://docs.github.com/en/billing/concepts/product-billing/github-actions>（已驗證）
- Terms for Additional Products and Features（Actions）：<https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features>（已驗證）
- Issue forms syntax：<https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms>（已驗證）
- Limiting interactions：<https://docs.github.com/en/communities/moderating-comments-and-conversations/limiting-interactions-in-your-repository>（已驗證）
- Script injections：<https://docs.github.com/en/actions/concepts/security/script-injections>（已驗證）
- OAuth scopes：<https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps>（已驗證）
- gh api manual：<https://cli.github.com/manual/gh_api>（已驗證）；gh 授權 MIT：<https://github.com/cli/cli/blob/trunk/LICENSE>（實測）
- `git ls-remote` 對舊名、大小寫、`.git`、尾斜線（實測）

**排程平台**
- Modal cron：<https://modal.com/docs/guide/cron>（已驗證）；timeouts：<https://modal.com/docs/guide/timeouts>（已驗證）；pricing：<https://modal.com/pricing>（已驗證）
- Cloudflare Workers limits：<https://developers.cloudflare.com/workers/platform/limits/>（已驗證）；pricing：<https://developers.cloudflare.com/workers/platform/pricing/>（已驗證）；Cron Triggers：<https://developers.cloudflare.com/workers/configuration/cron-triggers/>（已驗證）
- Workers Rate Limiting binding：<https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/>（已驗證）
- Turnstile plans：<https://developers.cloudflare.com/turnstile/plans/>（已驗證）

**套件與資料服務**
- PyPI API（RSS 優先、XML-RPC 將棄用、rate limit）：<https://docs.pypi.org/api/>（已驗證）
- PyPI project metadata（verified URLs）：<https://docs.pypi.org/project_metadata/>（已驗證）
- PyPI JSON、Integrity API provenance：`https://pypi.org/pypi/<name>/json`、`https://pypi.org/integrity/<name>/<ver>/<file>/provenance`（實測）
- PyPI RSS：<https://pypi.org/rss/packages.xml>（實測 ETag／304）
- Well-known Project URLs（PEP 753）：<https://packaging.python.org/en/latest/specifications/well-known-project-urls/>（已驗證）
- npm package.json（repository、directory）：<https://docs.npmjs.com/cli/v11/configuring-npm/package-json>（已驗證）
- npm registry／attestations：`https://registry.npmjs.org/<name>/latest`、`https://registry.npmjs.org/-/npm/v1/attestations/<name>@<ver>`（實測）
- Homebrew formula API：`https://formulae.brew.sh/api/formula/<name>.json`（實測）
- crates.io RSS：<https://static.crates.io/rss/crates.xml>（實測 ETag／304）
- ecosyste.ms API 與 polite pool：<https://ecosyste.ms/api>（已驗證＋實測）；repos／packages lookup（實測）
- ecosyste.ms Terms §9、§11：<https://ecosyste.ms/terms>；commercial：<https://ecosyste.ms/commercial>（查核已讀）
- ecosyste.ms `uuid` 對應：<https://github.com/ecosyste-ms/repos> `app/models/hosts/github.rb`，commit `5f869a7`（查核讀原始碼）
- deps.dev 反查：`https://api.deps.dev/v3/projects/<key>:packageversions`（查核實測）
- crates.io RSS 規則：<https://github.com/rust-lang/crates.io> `src/worker/jobs/rss/sync_crates_feed.rs`（`ALWAYS_INCLUDE_AGE` 60 分、`NUM_ITEMS` 50，commit `d21c1ec`，查核讀原始碼）
- deps.dev API v3：`https://api.deps.dev/v3/projects/<key>`（實測）
- OpenSSF Scorecard README：<https://github.com/ossf/scorecard>（已驗證）；API：`https://api.scorecard.dev/projects/github.com/<o>/<r>`（實測）
- GH Archive：<https://www.gharchive.org/>（已驗證）；README 授權：<https://github.com/igrigorik/gharchive.org>（已驗證）；`https://data.gharchive.org/2026-10-27-17.json.gz`（實測）

**HN**
- HackerNews/API README：<https://github.com/HackerNews/API>（已驗證）
- Algolia：`https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&numericFilters=...`（實測）

**工具與函式庫**
- RSSHub：<https://github.com/DIYgod/RSSHub>（LICENSE AGPL-3.0；路由原始碼 `lib/routes/{github,threads,hackernews,producthunt,npm}/`，commit `1d73c7c`，實測）
- changedetection.io LICENSE（Apache-2.0）：<https://github.com/dgtlmoon/changedetection.io>（實測）
- Huginn LICENSE（MIT）：<https://github.com/huginn/huginn>（實測）
- feedparser ETag 文件：<https://feedparser.readthedocs.io/en/latest/http-etag/>（已驗證）
- 函式庫授權（feedparser、packageurl-python、giturlparse、url-normalize、w3lib、courlan、hosted-git-info、normalize-package-data）：PyPI JSON 與 npm registry 的 license 欄位（實測）

**本 repo 其他調研筆記（交叉引用）**
- [channels-packages.md](channels-packages.md)：各套件庫的量、可執行判斷、條款
- [channels-hosting.md](channels-hosting.md)：GitHub search query、GH Archive 量測、GitLab／Codeberg 條款
- [channels-communities.md](channels-communities.md)：HN 條款與 Algolia 限制
- [channels-meta-platforms.md](channels-meta-platforms.md)：Threads oEmbed 與權限
- [meta-usage-design.md](meta-usage-design.md)：模型單價與每層 token 估算
- [sandbox-compare.md](sandbox-compare.md)：沙盒單價與時間

---

## 查核紀錄（2026-10-28）

查核者：另一個調研 agent，預設懷疑。方法：讀官方文件原文（GitHub docs 用 `docs.github.com/api/article/body` 取 markdown；Cloudflare 用 `index.md`）、實際打 API、讀原始碼、重跑 spike。時間 2026-10-27 21:00–21:30 UTC（台北 10-28 05:00–05:30）。

### 逐條結果

| # | 主張 | 判定 | 依據與修改 |
|---|---|---|---|
| 1 | Get a repository 狀態碼表有 301；2015 公告舊位置回 301／307；Location 格式未實測 | **成立** | 文件表列「301 - Moved permanently」；兩篇公告原文一致。Location 格式在官方文件與 [changes/21](https://developer.github.com/changes/21/) 都查不到，維持未驗證。本 session 重打 `/repos/charliermarsh/ruff` 仍 403，`/repositories/{id}` 代理明確不支援。補上官方「The name is not case sensitive」 |
| 2 | 舊位置建新 repo／fork 後 redirect 失效；Pages、被呼叫的 Actions 不轉 | **大致成立，補精確度** | 改名頁：同一帳號重用舊名才失效；Actions 不轉只寫在改名頁；轉移頁寫 fork 也會讓 redirect 永久刪除、Pages 不轉，另有「熱門 repo 舊名永久保留」規則。已在 4.3 補 |
| 3 | 271 個中 39 個（14%）改過名；5 組舊名 ecosyste.ms 404；4 組 deps.dev 兩個專案 | **成立，補解讀** | 離線重算上次輸出：39／271；重跑 `github` 子命令：5 組舊名 404、deps.dev 4 組各自 200。補：`previous_names` 含現名要排除；271 個的貼文網址全是現名，「14%」不是重複率 |
| 4 | GitHub rate limit 60／5,000／1,000；304＋Authorization 不計；序列化、Link 分頁 | **成立** | 原文逐字對到。「要求」原文是「should」（建議） |
| 5 | Actions 條款「unrelated…」與「serverless」 | **成立，補限定條件** | 「unrelated」那條只適用 GitHub-hosted runner；serverless 是「不成比例負擔」的舉例，附「low burden 可以」。另發現 2.2 建議在 Actions 裡處理提交（帶 Meta key）與這條衝突，改成 webhook → Modal 或 Actions 只轉送 |
| 6 | schedule 5 分鐘、延遲、預設分支、60 天停用；public 免費、private 2,000 分 | **成立** | 另補「some queued jobs may be dropped」。job 上限 6 小時也對（[Actions limits](https://docs.github.com/en/actions/reference/limits)） |
| 7 | Workers Free 5 個 Cron、10 ms、50 子請求（轉址每跳算）；Paid $5、10,000、250 | **成立** | limits／pricing 的 markdown 原文一致；Paid 子請求可調到 10M |
| 8 | Modal Starter $30、5 個 cron；timeout 預設 300 秒、最長 24 小時；Period 重部署重算 | **成立** | pricing 頁「Cron jobs 5 deployed crons」；cron、timeouts 頁原文一致 |
| 9 | PyPI 建議 RSS、XML-RPC 將棄用；packages.xml ETag／304；約 1 小時 | **成立** | 原文一致。重測 40 筆涵蓋 49 分鐘、重打 304；JSON `max-age=900`、304。官方另寫「no rate limiting of PyPI APIs at the edge」，但要設可識別的 UA、避免短時間上千次 |
| 10 | PyPI provenance 27／39、0 衝突、4 個只能靠 provenance；JSON 無 verified 標記 | **成立（數字會隨時間變）** | `pip` 的 Integrity API 回 `{kind: GitHub, repository: pypa/pip, workflow: release.yml}`；JSON `info` 欄位沒有 verified 標記。重跑 `recent`：40 個，provenance 24、只有 provenance 5、衝突 0 |
| 11 | ecosyste.ms CC BY-SA 4.0、AGPL-3；polite 15,000；UA 帶 mailto 仍 anonymous 5,000 | **部分不成立＋條款衝突** | 授權成立。rate limit：官方頁沒寫數字；重測不帶 mailto 也回 polite 15,000，原主張無法重現，已改。**Terms §9／§11(c) 禁止未經書面同意的腳本擷取**，原文建議「黑客松接」與條款衝突，已改成「取得同意後才接」，反查改用 deps.dev |
| 12 | Scorecard 130 萬、BigQuery 停、CDLA-Permissive-2.0；40 個 0 有分數 | **成立，補一個坑** | README 原文一致。API 路徑**區分大小寫**，小寫 key 會誤判；用原始大小寫重抽 40 個仍 0 |
| 13 | RSSHub 那些路由抓 HTML（commit `1d73c7c`） | **成立** | sparse clone 同一 commit 逐檔看過；LICENSE 是 AGPL-3.0。Product Hunt 條款本次沒讀，標未驗證 |
| 14 | GH Archive 2026-10-27-17 有 3,251 筆、新 repo 0 | **成立** | 重新下載：3,251 筆，CreateEvent 0（連 branch 都沒有）、PushEvent 0；ETag 重打 304 |
| 15 | Threads oEmbed 不含文字、條款禁止顯示以外用途（原標未驗證） | **成立（改為已驗證）** | 官方頁原文親自讀過；重跑 `spikes/ch_meta_probe.py`：html 可見文字只有「View on Threads」 |

### 其他自行抽查的事實

| 項目 | 結果 |
|---|---|
| ecosyste.ms `uuid` 是否等於 GitHub repo ID | 成立：原始碼 `hash[:uuid] = hash[:id]`。原標未驗證，已改 |
| crates.io RSS「60 分鐘、至少 50 筆」 | 行為成立（原始碼常數），但引號內的英文句子出處不明，已註記 |
| 成本 6.2 | 算術有兩處錯：Meta 每天應是 $6–12（原 $7–13，沙盒費被算進 Meta）；「全驗證 6 天超過 $150」只在估算中高段成立。已改 |
| Issue forms public preview、interaction limits、OAuth no scope、script injection、Turnstile 20 widgets、HN「no rate limit」、PEP 753 正規化、npm `repository` 正規化與 `directory` | 原文都對得上 |
| Codeberg robots.txt `Disallow: /api/` | 成立 |
| GitHub AUP §7 | 現行原文的用途清單寫「regardless of whether the information was scraped, collected through our API」，API 取得的資料也受限；本檔 2.15 已加指向 [channels-hosting.md](channels-hosting.md) 2.1 |

### spike 重跑

| 腳本 | 指令 | 結果 | 與本檔是否一致 |
|---|---|---|---|
| `ch_integration_normalize.py` | `all` | 59 秒跑完，exit 0。selftest 25／25；GitHub API 403 → 自動走 git＋ecosyste.ms；7 組 git HEAD 相同；短網址 5／5 | 一致。`recent` 數字隨 RSS 視窗變動（見上表第 10 條） |
| `ch_integration_merge.py` | 以上次的狀態檔增量、`--enrich 0`（不打 ecosyste.ms，避開條款問題） | Show HN cursor 後 3 則；PyPI 200、40 個；候選 1,149 → 1,172 | 可重跑、增量正確 |
| 同上，再跑一次 | 同上 | Show HN 0 則；PyPI **304**；候選 1,172 → 1,172 | 冪等成立 |
| 同上，`--reset --days 1 --enrich 0` | 首次路徑 | 5 秒；Show HN 24 小時 189 則、候選 251 | 首次路徑可跑 |

- 兩支腳本都不含金鑰；`GH_TOKEN`、`PICKFIT_CONTACT` 都從環境變數讀。輸出寫在系統暫存目錄，不進 repo。
- 已知限制：merge 腳本的 `--enrich` 預設 1,000，會對 ecosyste.ms 發約 800 次請求。條款問題解決前，重跑請加 `--enrich 0`。`--enrich 0` 時初篩原因會顯示「ecosyste.ms 查無」，這是腳本文字，不代表真的查過。

### 本次修改清單

1. 一句話結論：補「14% 不是重複率」、Actions 限定 GitHub-hosted runner、新增 ecosyste.ms 條款一條。
2. 比較表：Issue Form 取得方式、ecosyste.ms（條款、rate limit、建議改為條件式）、deps.dev（反查）、Scorecard（大小寫）。
3. 2.2 新增「不要在 Actions 裡處理提交」；7.4 加註。
4. 2.7 Threads：改為親自驗證，補 rate limit 與不支援的貼文類型。
5. 2.10 ecosyste.ms：新增條款段、deps.dev 替代與實測、`uuid` 改為已驗證、rate limit 主張改寫、查無 115 個的解讀。
6. 2.14、2.15、3.1、3.2、4.3、4.6、6.2、9.1、9.3、10、11：見各處〔查核〕標記。
7. 沒有動 brief.md、hackathon-rules.md、architecture.md、spikes/README.md 與任何 spike 腳本。
