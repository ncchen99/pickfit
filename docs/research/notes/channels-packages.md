2026-10-28 · 套件生態與跨生態系開放資料（Homebrew、winget、Scoop、PyPI、npm、crates.io、Go、Docker Hub、AUR、Nixpkgs、conda-forge、ecosyste.ms、deps.dev、libraries.io） · 由調研 agent 撰寫，待主控者整合

# 管道調研：套件生態與跨生態系開放資料

實測時間：2026-10-27 19:45–20:20 UTC（台北 10/28 03:45–04:20）。下文「查證日期」一律記 2026-10-28（台北）。

**一句話**：最值得接的是 **Homebrew 官方 analytics 裡的第三方 tap**。它同時給出「新」（安裝幾乎都在最近 30 天）、「可執行」（tap 幾乎都是 CLI，多半附 release 預編譯檔）、「還沒紅」（中位數 1 顆星）、「有安裝紀錄」（官方安裝數；**公開數字沒有排除 CI 安裝**，見 2.1）。其次是 PyPI（本地 AI 工具多）和 deps.dev（補 repo 對應）。ecosyste.ms 的服務條款要求自動化存取先取得書面同意，取得前不放進管線（見 2.12，查核時修正）。

---

## 1. 比較表

| 管道 | 訊號品質 | 新作品多寡 | 雜訊 | 取得方式 | 限制 | 整合成本 | 建議 |
|---|---|---|---|---|---|---|---|
| **Homebrew 第三方 tap**（analytics） | **高**：作者自建 tap＝有 release、可執行；官方給真實安裝數 | 30 天內新出現 4,066 個 formula；安裝 10–1000 的 437 個 | 中：1–5 次安裝的多是作者自測（3,310 個）；公開數字含 CI 安裝 | API（formulae.brew.sh analytics JSON）＋讀 tap repo 的 `.rb` | 無 rate limit／條款說明；資料授權未明示 | 3–4 h | **黑客松接** |
| Homebrew core | 中：品質高，但新作品進不去（notability 門檻） | 7 天 13 個新 formula | 低 | API（formula.json、analytics） | 同上；收錄門檻 75 星／自薦 225 星、repo 未滿 30 天通常不收 | 1–2 h | 黑客松接（當知名度基準與 `executables`） |
| winget-pkgs | 中：自助提交、有自動驗證，但無安裝數、GUI 多 | 7 天 87 個 New package | 中：含大廠與商用軟體 | Git repo（manifest YAML）；PR 流 | MIT；無 notability 門檻 | 2–3 h | 之後擴充 |
| Scoop buckets | 低：Main/Extras 有星數門檻；第三方 bucket 分散 | 少 | 低 | Git repo（JSON manifest）；GitHub topic `scoop-bucket` | Main 500 星＋150 forks；Extras 100 星／50 forks | 3 h | 避開（黑客松期間） |
| PyPI | 中：量大，但 `console_scripts` 可篩出 CLI；本地 AI 工具多在這 | 約 40 個新專案／小時（≈6,700／週） | 高：spam、作業、SDK、內部套件 | RSS、JSON API、BigQuery（XML-RPC `changelog_since_serial` 只當一次性回補） | ToS：過度請求可停權；無 edge rate limit；官方：新整合不要用 XML-RPC，追新套件用 RSS | 3–4 h | **黑客松接** |
| npm | 低～中：量最大，`bin` 可篩 CLI | 7 天約 27,000 個 | 很高：72% scoped、placeholder、spam | replicate `_changes`（只有 id）、registry、downloads API、search | ToS：每月 500 萬請求不合理；不准自動化存取網站（要走 Public APIs） | 3 h | 之後擴充（或黑客松選做） |
| crates.io | 中：91% 連 GitHub；`bin_names` 直接判斷 CLI | 7 天 5,947 個 | 中：大量函式庫、名稱保留 | RSS、API、sparse index、每日 db dump | API 1 req/s、必須帶可識別的 User-Agent | 2 h | 之後擴充 |
| Go（index＋pkg.go.dev） | 低：量極大；`name == "main"` 可篩 CLI | 6 小時 35,583 個版本事件、9,795 個 module | 很高：pseudo-version、SDK、monorepo | index.golang.org feed、pkg.go.dev v1 API | pkg.go.dev 45 QPS／IP block；index 單次最多 2000 筆 | 3–4 h | 之後擴充 |
| Docker Hub | 低：新作品少放這 | 未量測 | 中 | API（v2 repositories） | 觀察到 180 次／視窗的 rate limit；條款未查證 | 1 h | 避開（只當知名度補充） |
| AUR | 中：新作品多、80% 連 GitHub | 7 天 831 個 | 中：只限 Arch、無審查、`-bin` 安全風險 | 每 5 分鐘更新的 metadata dump、RPC | RPC 預設 4,000 次／日／IP（正式站未驗證）；Anubis 未驗證 | 1–2 h | 之後擴充 |
| Nixpkgs | 低（發現用）：無上架日期、無安裝數 | 未量測 | 低 | channel 的 packages.json | MIT | 2 h | 避開（黑客松期間） |
| conda-forge | 低：人工審核慢，偏科學函式庫 | 少 | 低 | anaconda.org API、staged-recipes PR | 未查證 | 2 h | 避開 |
| **ecosyste.ms** | 中～高（補資料用）：跨 100 個 registry、repo metadata、release 檔案清單 | 依 registry；PyPI 延遲約 34 小時 | 中：dependents 數字不一定準 | API（packages、repos、timeline、advisories）、Postgres dump | 匿名 5,000／小時、帶 email 15,000／小時；資料 **CC BY-SA 4.0**；**ToS 禁止未經書面同意的腳本擷取資料**（§9、§11(c)） | 2 h | **條件式**：寄信取得書面同意後才接；同意前不放進管線（查核時修正） |
| **deps.dev** | 中（補資料用）：**有驗證的 repo 對應**（attestation）、星數、Scorecard | 新套件有、Scorecard 多半沒有 | 低 | API v3、BigQuery `deps_dev_v1` | Google API ToS；只有 deps.dev 自己產生的資料（關聯、解析後依賴等）是 CC-BY 4.0，星數等依原始來源條款；不支援 Homebrew | 1 h | **黑客松接**（補資料） |
| libraries.io | 低：與 ecosyste.ms 重複 | — | — | API（需 key） | 60 req/min；CC-BY-SA；公開 dump 停在 2020 | 1 h | 避開 |

整合成本是「讀到資料、轉成候選清單」的人時，不含 Meta 模型判讀。

---

## 2. 各管道細節

### 2.1 Homebrew 第三方 tap（透過官方 analytics）——本組最佳

- **發現方式**：`https://formulae.brew.sh/api/analytics/install-on-request/{30d,90d,365d}.json` 也收第三方 tap，名稱是 `user/tap/formula`。實測 30 天有 12,264 個第三方 tap formula、來自 7,858 個 tap（cask 也有 7,523 個第三方項目）。
- **「最近才出現」**：365 天與 90 天安裝數都 ≤ 30 天安裝數的 1.15 倍＝幾乎是這 30 天才開始有人裝（腳本兩個條件都檢查；只看 365 天結果也是 4,066）。共 4,066 個；30 天安裝 10–1000 的有 437 個。
- **安裝數含 CI（查核時補）**：brew 的公開 analytics 查詢只篩 `on_request = 'true'`，沒有排除 `ci`／`developer` 標記的事件（[influx.rb](https://github.com/Homebrew/brew/blob/main/Library/Homebrew/utils/analytics/influx.rb) 的 `query`）；brew 在 CI 裡只要顯示過 analytics 訊息、沒設 `HOMEBREW_NO_ANALYTICS` 就會送事件（[analytics.rb](https://github.com/Homebrew/brew/blob/main/Library/Homebrew/utils/analytics.rb)、[analytics.sh](https://github.com/Homebrew/brew/blob/main/Library/Homebrew/utils/analytics.sh)）。所以 10–1000 次裡可能有作者 release workflow 或使用者 CI 的安裝。CI 占比多少：**未驗證**。安裝數只能當「有人在用」的弱訊號，不能當使用者數。
- **對到 repo**：tap 依慣例是 `github.com/<user>/homebrew-<tap>`；formula 檔裡的 `homepage`／`url` 再對到原始 repo。抽樣 40 筆：39 找到 formula 檔、36 對到 GitHub repo、29 用 `releases/download` 預編譯檔、36 個 repo 今年才建立；星數中位數 **1**，32/36 不到 100 星。
- **兩個 demo 類別**：開發者 CLI 很好用（tap 本來就幾乎都是 CLI）。抽樣 40 筆中約 15–16 筆和 AI／agent／LLM 有關（查核時人工重數 16 筆；分類是主觀判斷），但**多數是 coding agent 周邊工具**（agent 編排、Claude Code 用量統計、終端 coding agent）。真正屬於「本地 AI／LLM 工具」的只有約 3 筆：`beamivalice/tap/sushi`（Apple Silicon 的 LLM 推論伺服器，296 星）、`shashankswe2020-ux/tap/rigspark`（依硬體挑選並執行本地 LLM，19 星）、`ipsupport-llc/tap/ipsupport-code`（本地／雲端模型的終端 coding agent，4 星）；`topogamer0/tap/ollama-c` 是函式庫。本地 AI 類別要靠 PyPI 補（查核時修正）。
- **安全（查核時補）**：官方明講「Distribution through a third-party tap does not imply Homebrew endorsement or support」（[Package Acceptance Policy](https://docs.brew.sh/Package-Acceptance-Policy)）。tap formula 沒經過 Homebrew 審查，驗證一律在沙盒裡跑。
- **雜訊**：1–5 次安裝的 3,310 個多半是作者自測；設下限（例如 ≥10）就好。也有大公司 tap（victoriametrics、hashicorp），用 repo 星數或 org 過濾。
- **條款**：analytics 文件只說資料是匿名彙總、公開在 formulae.brew.sh：「Homebrew collects aggregate, anonymous usage analytics」；只會收「non-private GitHub tap names」（[Analytics](https://docs.brew.sh/Analytics)）。API 文件沒有 rate limit、條款或資料授權的說明（[API docs](https://formulae.brew.sh/docs/api/)）。homebrew-core 程式碼是 BSD-2-Clause；**analytics 資料授權未明示**，用時註明出處。API 由 GitHub Pages 提供（回應頭 `server: GitHub.com`、`cache-control: max-age=600`），一天抓幾次就夠。
- **注意**：讀 tap 的 `.rb` 我用 raw.githubusercontent.com。GitHub AUP 把自動化擷取定義為 scraping，只對研究與封存開放；正式產品改走 GitHub REST API（contents），適用 API 條款（[GitHub AUP 第 7 節](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)）。

### 2.2 Homebrew core（formula.json＋analytics）

- `formula.json` 8,679 個 formula、`cask.json` 7,816 個（實測）。每筆有 `homepage`、`urls.stable.url`、`license`、`desc`，以及 API 文件沒寫、但實測存在的 **`executables`**（例：ripgrep → `["rg"]`；函式庫 ng-log → `[]`）。7,307／8,679 有 executables。
- 單一 formula JSON 會附 30／90／365 天安裝數（ripgrep 30 天 `install` 48,775 次，含被當依賴安裝；`install_on_request` 37,725 次）。
- **收錄門檻（新作品進不去的原因）**：「at least 30 forks, 30 watchers or 75 stars」；自薦要「at least 90 forks, 90 watchers or 225 stars」；「A code repository less than 30 days old is normally not eligible.」；不符合的「can generally be maintained in a third-party tap」（[Package Acceptance Policy](https://docs.brew.sh/Package-Acceptance-Policy)）。
- 實測 7 天只有 13 個 `(new formula)` commit（shallow clone homebrew-core 後 `git log`；查核時重跑也是 13 個）。其中幾個看起來是作者自薦：xfr（commit 作者 lance／repo `lance0/xfr`）、ascelerate（Kerem Erkan／`keremerkan/ascelerate`）。只比對 commit 作者與 repo owner，沒看 PR，**未逐一確認**；原文舉的 zvec-grep 對不上（commit 作者與 `zvec-ai` 看不出關係）。
- 用途：當知名度基準（已進 core＝已有一定知名度），以及驗證時的「官方安裝方式」。

### 2.3 winget-pkgs

- manifest 在 `microsoft/winget-pkgs`（MIT）。新套件以 PR 進來，標題 `New package: <Id> version <v>`。實測 7 天 87 個 New package commit；解析 84 個：65 個連到 GitHub、28 個有 portable／`Commands` 等 CLI 訊號、10 個帶 AI 相關 tag、54 個是 OSI 類授權。
- 例：`kanywst.y509`（X.509 憑證鏈 TUI，37 星）、`CastAI.Kimchi`（終端 coding agent）、`ChenZibo.NewbeeOCRCLI`（PaddleOCR 命令列）。
- **沒有安裝數**，沒有官方 notability 門檻。政策只要求「Offer unique and distinct value」與「The InstallerUrl must be the ISV's release location」（[winget 政策](https://learn.microsoft.com/en-us/windows/package-manager/package/windows-package-manager-policies)）。
- `portable` 也包含 GUI 小工具，CLI 判斷要再看 `Commands`／`PortableCommandAlias`。
- 只對 Windows 有意義；沙盒驗證要 Windows 環境，黑客松期間不划算。

### 2.4 Scoop buckets

- Main：「at least 500 stars and 150 forks」、而且是「a non-GUI tool」（[Scoop wiki](https://github.com/ScoopInstaller/Scoop/wiki/Criteria-for-including-apps-in-the-main-bucket)）。
- Extras：package request 模板寫「at least 100 stars and/or 50 forks」（ScoopInstaller/Extras `.github/ISSUE_TEMPLATE/package-request.yml`）。Extras 授權是 Unlicense。
- 第三方 bucket 要靠 GitHub topic `scoop-bucket`（Scoop Directory），沒有安裝數。對「默默無聞」幫助小。

### 2.5 PyPI

- **新專案**：RSS `https://pypi.org/rss/packages.xml` 約 40 筆，實測只涵蓋最近約 1 小時（調研時 40 筆／64 分；查核時 39 筆／74 分）。官方建議：「For periodically checking for new packages or updates to existing packages, use our RSS feeds. No new integrations should use the XML-RPC APIs as they are planned for deprecation.」（[API docs](https://docs.pypi.org/api/) 的 API Preference）。所以**主路徑是每 30 分鐘左右輪詢 RSS**，不要把 XML-RPC 做進管線（查核時修正）。
- **回補**：XML-RPC `changelog_since_serial` 仍可用，但只適合一次性回補，而且違反上面的官方建議，要自己承擔停用風險。實測 22.4 小時內 901 個 `create` 事件（約 40／小時；查核時 22.8 小時 909 個）。**單次呼叫最多回 50,000 筆、從 serial 往後取**：`since=last-60000` 只拿到較舊的 50,000 筆，最近約 4 小時沒回來，要用回傳的最後 serial 再呼叫。舊的 `changelog(since)` 已停用，回傳「The changelog method has been deprecated, use changelog_since_serial instead.」（實測）。替代：BigQuery `distribution_metadata`（每個 release 的 metadata，含上傳時間欄位與否**未驗證**），資料授權 CC BY 4.0（[BigQuery docs](https://docs.pypi.org/api/bigquery/)）。
- **JSON API**：`/pypi/<name>/json` 有 `project_urls`、`classifiers`、`requires_dist`；`downloads` 欄位「is always -1」（[JSON API](https://docs.pypi.org/api/json/)）。**沒有 entry points**。
- **可執行判斷**：wheel 裡的 `*.dist-info/entry_points.txt`。用 HTTP Range 只讀 zip 中央目錄即可（files.pythonhosted.org 回 206，實測）。抽樣 30 筆新套件中 12 筆有 `console_scripts`。只有 sdist 的要讀 `pyproject.toml` 的 `[project.scripts]`。
- **知名度**：pypistats API（實測 `x-ratelimit-limit: 60`；只留 180 天；官方明講大量抓「DON'T」，改用 BigQuery）。BigQuery `bigquery-public-data.pypi.file_downloads`、`distribution_metadata`（[BigQuery docs](https://docs.pypi.org/api/bigquery/)，資料 CC BY 4.0），要 GCP 專案；本環境 `bq` 未登入，未實測。BigQuery 查詢每月前 1 TiB 免費、儲存前 10 GiB 免費（[BigQuery pricing](https://cloud.google.com/bigquery/pricing)，查核時補）。
- **條款**：「Abuse or excessively frequent requests to PyPI via the API may result in the temporary or permanent suspension」；不得「download data or Content from PyPI for spamming purposes」（[PyPI ToS](https://policies.python.org/pypi.org/Terms-of-Service/)）。API 文件：「there is currently no rate limiting of PyPI APIs at the edge」，但「Try not to make a lot of requests (thousands) in a short amount of time (minutes)」，User-Agent 要能識別（[API docs](https://docs.pypi.org/api/)）。
- **兩個 demo 類別**：本地 AI／LLM 工具很多在 PyPI（含 MLX、Ollama 周邊）；CLI 也不少。雜訊高，要先用 `console_scripts`＋有 GitHub repo＋README 長度篩。

### 2.6 npm

- **changes feed**：`replicate.npmjs.com/_changes` 仍可用（engine `npm-replicate`），但只回 id 與 rev；`include_docs=true` 回 400（實測）。2025-05-29 起舊端點已全面換新（[GitHub changelog](https://github.blog/changelog/2025-02-26-changes-and-deprecation-notice-for-npm-replication-apis/)）。分不出新建或更新，要再抓 packument 看 `time.created`。
- **新套件數**：用 ecosyste.ms（延遲約 2 小時），7 天 27,393 個、64% 連 GitHub。最新 1,000 筆裡 72% 是 scoped、約 2% 的描述是「Temporary package placeholder for staged publishing」（推測與 npm staged publishing 2026-10-02 起可建立新套件有關，未驗證）。
- **可執行判斷**：最新版的 `bin`（abbreviated packument `application/vnd.npm.install-v1+json` 就有）。抽樣 30 筆有 7 筆。
- **知名度**：downloads API；bulk 最多 128 個、最多 365 天，scoped 不支援 bulk；非 bulk 查詢最多 18 個月（[download-counts](https://github.com/npm/registry/blob/main/docs/download-counts.md) 的 Limits；查核時修正，原文把 18 個月寫成 bulk 的上限）。search API 回應現在直接帶 `downloads`（週／月）與 `dependents`（實測）。
- **條款**：「You will not automate access to, use, or monitor the Website, such as with a web crawler」；但「You may replicate data from the Public Registry using the Public APIs」；「under no circumstances are five million requests to npm Services in a single month-long period」合理；安全資料只能「for your own personal or internal business purposes」（[Open-Source Terms](https://docs.npmjs.com/policies/open-source-terms)）。原文列的「Using the Public Registry as a general purpose database is not allowed」在 Acceptable Content 段，指的是**上傳什麼內容**，不是限制讀取資料（查核時修正）。另有 [Replication and web crawler policy](https://docs.npmjs.com/policies/crawlers)：網站「At our discretion」允許每秒 ≤1 次的實驗性爬蟲，但與 Open-Source Terms 的禁止條款並存，仍以走 Public APIs 為準。

### 2.7 crates.io

- **新 crate**：RSS `static.crates.io/rss/crates.xml`（「the past 60 minutes, but at least 50 new crates」）；API `?sort=new` 用 seek 分頁。實測 7 天 5,947 個、24 小時 808 個、91% 的 repository 是 GitHub。
- **可執行判斷**：版本的 `bin_names`（ripgrep → `["rg"]`）與 `has_lib`。db dump 的 `versions.bin_names` 是 public 欄位。抽樣 30 筆新 crate 只有 3 筆是 CLI（多為函式庫與名稱保留；查核重跑 6／29，CLI 約 10–20%）。用 category `command-line-utilities` 可先縮小。
- **條款**：「A maximum of 1 request per second」＋「A user-agent header that identifies your application」；sparse index「No rate limits」；db dump「updated every 24 hours」（crates.io Data Access 頁，原始碼 `svelte/src/routes/data-access/+page.svelte`）。不帶 UA 實測直接被拒（查核時重測：HTTP 403，訊息「We require that all requests include a `User-Agent` header」）。同頁要求「Please try them in the order below」：先 sparse index → db dump → API 最後。[Policies](https://crates.io/policies) 另禁止「excessive automated bulk activity」。資料授權未明示。查核時以原生 API 重數：7 天 5,961 個、24 h 834 個、GitHub 90.5%（與原文一致）。`trustpub_data` 在 db dump 是 private，只能從 API 拿。
- 適合「Rust 寫的 CLI」，對本地 AI 類別普通。

### 2.8 Go（index.golang.org、pkg.go.dev）

- index：「Default = 2000, Max = 2000」；`include=all` 會含所有出現過的版本（[index.golang.org](https://index.golang.org/)）。實測 6 小時 35,583 個版本事件、9,795 個 module、5,154 個有正式 tag。量太大，雜訊（AWS SDK、monorepo 子模組）很多。
- pkg.go.dev 在 2026 年推出官方 API，現在路徑是 `/v1/...`（[API 參考](https://pkg.go.dev/v1/api)；[Go blog 2026-05-21](https://go.dev/blog/pkgsite-api) 當時還是 `/v1beta`）。`/v1/packages/{module}?filter=name == "main"` 可直接判斷有沒有 CLI（fzf → 1 個 main）。`imported-by-counts=true` 給 importer 數（cobra 99,323 個 module），新套件常是 -1。
- 限制：「rate-limited to 45 queries per second (QPS) per IP block」。剛發布的 module 常常還查不到（抽樣 30 筆有 5 筆 404）。
- module path 本身就是 repo（`github.com/owner/repo`），proxy `@latest` 的 `Origin.URL` 可再確認。

### 2.9 Docker Hub（簡要）

- `hub.docker.com/v2/repositories/<ns>/<repo>` 有 `pull_count`、`star_count`（ollama/ollama 1.9 億次 pull）。回應頭 `x-ratelimit-limit: 180`。
- 新的個人作品很少先上 Docker Hub；只適合當本地 AI 伺服器類的知名度補充。條款未查證。

### 2.10 AUR（簡要）

- `aur.archlinux.org/packages-meta-v1.json.gz`（10.6 MB，`cache-control: max-age=300`）含 `FirstSubmitted`、`NumVotes`、`Popularity`、`URL`。實測 7 天新增 831 個、80% 連 GitHub；`-bin` 240 個、`-git` 122 個。
- RPC 預設「request_limit = 4000」「window_length = 86400」（aurweb `conf/config.defaults`；正式站設定**未驗證**，查核時 RPC 回應頭也沒有 rate limit 資訊）。「wiki 與網站有 Anubis 防機器人」：**未驗證**（查核時 `aur.archlinux.org/packages/yay` 與 ArchWiki 都直接回 200，沒出現挑戰頁）。不論有沒有，都不要爬頁面，用 metadata dump 與 RPC。
- 很多是別人幫上游打包；只能代表 Linux。AUR 沒有審查，`-bin` 套件曾出過惡意程式（未在本次查證），驗證時要更嚴。

### 2.11 Nixpkgs、conda-forge（簡要）

- Nixpkgs：`channels.nixos.org/nixos-unstable/packages.json.br` 有 150,656 個套件、26,969 個有 `meta.mainProgram`（CLI 訊號）、55,067 個 homepage 在 GitHub。沒有上架日期與安裝數；新套件要追 nixpkgs 的「init at」PR。MIT 授權。
- conda-forge：新套件要經 staged-recipes 人工審核，偏科學函式庫。anaconda.org API 有每個檔案的 `ndownloads`（llm 合計 77,950）。黑客松期間不值得。

### 2.12 ecosyste.ms

- 服務：packages、repos、advisories、timeline（GH Archive 事件流）、awesome 等；「Code: AGPL-3」「Data: CC BY-SA 4.0」（[API 頁](https://ecosyste.ms/api)）。
- **服務條款衝突（查核時補，最影響決策）**：[ecosyste.ms Terms](https://ecosyste.ms/terms) §9 列為禁止：「Develop or use any third-party applications that interact with our Platform without our prior written consent, including any scripts designed to scrape or extract data from our Platform」；§11(c) 的授權只限「your own personal use」，不含「commercially use」與「use any data mining, robots or similar data gathering or extraction methods」。但 [API 頁](https://ecosyste.ms/api) 又公開提供 API、rate limit 與 polite pool，[commercial 頁](https://ecosyste.ms/commercial) 說社群可在 AGPL／CC-BY-SA 下免費使用。兩邊文字衝突。**判定**：取得書面同意前，不把 ecosyste.ms 放進自動化管線；要用就先寄信 support@ecosyste.ms 說明用途（黑客松、非商用、資料以 CC BY-SA 標示出處）並保留回信。替代：repo metadata 與 release assets 改用 GitHub REST API（自己的 token）；新套件數改用各 registry 原生來源。
- rate limit（回應頭實測）：匿名 `x-ratelimit-limit: 5000`（每小時、**依 IP**，本環境出口 IP 是共用的，第一次呼叫剩 4,050）；User-Agent 帶 mailto 進 polite pool，`15000`。查核時：`x-ratelimit-reset` 落在整點，符合每小時視窗；同一 IP 帶過一次 mailto 後，不帶 mailto 的請求也回 `tier: polite`，可見 tier 是依 IP 記，不是逐請求判斷。
- packages API：`created_after`、`per_page=1000`、`sort=created_at`；欄位有 `repository_url`、`downloads`、`dependent_packages_count`、`dependent_repos_count`、`repo_metadata`（星數、topics）。
- **延遲**（新套件首次發布到被收錄的中位數）：crates 0.4 h、npm 2.1 h、PyPI **34 h**（查核時以最新 500 筆重算：0.3／2.6／32.9 h，一致）。抽 25 個 20 小時前在 PyPI 建立的專案，ecosyste.ms 一個都還沒有。**不能當 PyPI 的即時來源。**
- repos API 免 GitHub token 就能拿到 repo metadata 與 **release assets 清單**（y509 v1.11.0 有 18 個檔，含 darwin／linux／windows 壓縮檔）。可判斷「有沒有預編譯二進位檔」。
- dump：Postgres tarball，最新 2026-02-05（約 1,311 萬個套件），[open-data](https://packages.ecosyste.ms/open-data)。商用有付費授權。
- **授權風險**：CC BY-SA 有 share-alike。若把 ecosyste.ms 來的欄位存進公開的 YAML 正本，整份衍生資料可能要用 BY-SA 釋出。Terms §11(b) 也要求「attributing 'ecosyste.ms' as the source of data」。需要主控者決定（見第 6 節）。

### 2.13 deps.dev

- API v3 支援「GO, RUBYGEMS, NPM, CARGO, MAVEN, PYPI, NUGET」；「Use of the deps.dev API is subject to the Google API Terms of Service」；「This generated data is available under a CC-BY 4.0 license.」；「Clients are expressly permitted to cache data」（[API v3](https://docs.deps.dev/api/v3/)）。文件沒寫 rate limit（查核時回應頭也沒有）。
- **CC-BY 4.0 的範圍（查核時修正）**：只涵蓋 deps.dev「generates」的資料（「resolved dependencies, advisory statistics, associations between entities」）。星數、forks 來自 GitHub，套件資料來自各 registry，文件寫「For details on using the data from these sources, please consult their documentation」。[Google APIs ToS](https://developers.google.com/terms) §5(e) 規定，除非內容擁有者明示允許，不得對 API 回傳內容「Scrape, build databases, or otherwise create permanent copies」或「publicly display」。所以 `relationProvenance`（關聯）可依 CC-BY 存；**從 deps.dev 拿的星數不能當成 CC-BY 存進公開 YAML**。
- **最有用的是 repo 對應的可信度**：`relatedProjects[].relationProvenance` 會區分 `UNVERIFIED_METADATA` 與 `SLSA_ATTESTATION`／`PYPI_PUBLISH_ATTESTATION`（實測 vite、llm）。後者是發布流程簽章證明的 repo，可防冒名。
- `GetProject` 給星數、forks、授權；`scorecard` 只有部分專案有（fzf 6.4、2026-08-24；llm 與新 repo 都沒有）。
- BigQuery `deps_dev_v1` 有 Projects、PackageVersions、Dependents 等表（[BigQuery](https://docs.deps.dev/bigquery/v1/)）。
- 不支援 Homebrew、AUR、winget。

### 2.14 libraries.io

- 「All API requests must include api_key」、「60 request/minute」（[API](https://libraries.io/api)）。實測 search 無 key 回 401；但單一專案端點無 key 也回了資料。申請：libraries.io 用 GitHub 等帳號登入，在帳號設定頁取得 API key。
- 網站寫「Data is available under CC-BY-SA 4.0 license」；Zenodo 上的公開 dump 停在 1.6.0（2020-01-12，標 CC-BY-4.0）（[Zenodo](https://zenodo.org/records/3626071)）。repo 仍在維護（最近 commit 2026-10-23）。
- 與 ecosyste.ms 功能重疊，黑客松期間沒理由多管一把 key。

---

## 3. 三個特別問題

### (a) 可當「知名度」的欄位

| 生態系 | 欄位與端點 | 實測例子 | 注意 |
|---|---|---|---|
| Homebrew | analytics `install`／`install-on-request` 30／90／365 天 | ripgrep 30 天 `install` 48,775（`install_on_request` 37,725） | 第三方 tap 也有；使用者可關閉 analytics；公開數字含 CI 安裝 |
| PyPI | pypistats `recent`；BigQuery `file_downloads` | llm 上週 126,822 | pypistats 不准大量抓；180 天 |
| npm | downloads API `point/last-week`；search 的 `downloads`、`dependents` | ollama 上週 728,415 | scoped 不能 bulk |
| crates.io | `downloads`、`recent_downloads`（90 天） | — | 新 crate 多為 0 |
| Go | pkg.go.dev `importedByCounts` | cobra 99,323 module | 新 module 常為 -1 |
| Docker Hub | `pull_count`、`star_count` | ollama 1.9 億 | 只適合伺服器類 |
| AUR | `NumVotes`、`Popularity` | — | 只代表 Arch 使用者 |
| 跨生態 | ecosyste.ms `downloads`、`dependent_*_count`、`rankings`；deps.dev `starsCount`；libraries.io `dependents_count` | npm ollama 的 ecosyste.ms dependents＝0，明顯偏低 | 不同來源的 dependents 數字差很多，只當參考；ecosyste.ms 要先取得書面同意；deps.dev 星數不是 CC-BY |
| repo | 星數（ecosyste.ms repos、deps.dev project） | — | brief 已決定不讓星數主導 |

### (b) 可當「這是可執行的軟體，不是函式庫」的欄位

| 生態系 | 欄位 | 怎麼拿 | 實測 |
|---|---|---|---|
| Homebrew core | formula 本身＋`executables` | formula.json | 7,307／8,679 有；函式庫為 `[]` |
| Homebrew tap | formula 的 `bin.install`、`url` 指向 `releases/download` | 讀 tap repo 的 `.rb` | 抽樣 29／40 用預編譯檔 |
| PyPI | wheel `entry_points.txt` 的 `[console_scripts]`／`[gui_scripts]` | HTTP Range 讀 wheel | 抽樣 12／30 |
| npm | 最新版 `bin` | abbreviated packument | 抽樣 7／30 |
| crates.io | `bin_names`（非空）、`has_lib` | `/api/v1/crates/{name}/{ver}` 或 db dump | 抽樣 3／30（重跑 6／29）；ripgrep `["rg"]` |
| Go | 有 `name == "main"` 的 package | pkg.go.dev `/v1/packages/{mod}?filter=...` | 抽樣 11／25（重跑 14／21） |
| winget | `InstallerType: portable`、`Commands`、`PortableCommandAlias` | installer manifest | 28／84（含 GUI portable） |
| Nixpkgs | `meta.mainProgram` | packages.json | 26,969／150,656 |
| GitHub release | release assets 有各平台壓縮檔 | ecosyste.ms repos `/releases`（免 GitHub token，但要先取得書面同意）；正式管線改用 GitHub REST API | y509 有 darwin／linux／windows |

### (c) 套件名對到 repo URL

| 生態系 | 方法 | 可信度 |
|---|---|---|
| PyPI | `info.project_urls`（Source／Repository／Homepage）、`home_page` | 自填，可能填錯或冒名 |
| PyPI | deps.dev `relationProvenance: PYPI_PUBLISH_ATTESTATION`；PyPI integrity API 的 provenance | **有簽章證明** |
| npm | packument `repository.url`（含 `directory`） | 自填 |
| npm | `dist.attestations`；deps.dev `SLSA_ATTESTATION`、`slsaProvenances[].sourceRepository` | **有簽章證明** |
| crates.io | `repository` 欄位；`trustpub_data`（Trusted Publishing） | 自填／trustpub 較可信 |
| Go | module path 本身；proxy `@latest` 的 `Origin.URL` | 高（由路徑決定） |
| Homebrew core | `homepage`、`urls.stable.url`、`urls.head` | 維護者審過 |
| Homebrew tap | `user/tap` → `github.com/user/homebrew-tap`；`.rb` 的 `homepage`／`url` | 慣例＋作者自填 |
| winget | `PackageUrl`、`InstallerUrl`（GitHub releases） | 自填，PR 有審 |
| AUR | `URL` | 打包者自填 |
| 跨生態 | ecosyste.ms `repository_url`；deps.dev `relatedProjects` | 依來源 |

---

## 4. 實測

兩個腳本都只用 Python 標準函式庫、不需金鑰。選填環境變數 `PICKFIT_CONTACT=<email>` 會放進 User-Agent（crates.io 要求可聯絡、ecosyste.ms 進 polite pool）。

### 4.1 `spikes/ch_packages_brew_taps.py`：Homebrew 第三方 tap 的新作品

```
PICKFIT_CONTACT=<email> python3 spikes/ch_packages_brew_taps.py            # 約 40 秒
python3 spikes/ch_packages_brew_taps.py --min 20 --max 500 --sample 60    # 調門檻
PICKFIT_JSON=1 python3 spikes/ch_packages_brew_taps.py                    # 多印完整 JSON
```

做法：抓 install-on-request 30／90／365 天 → 挑第三方 tap 中 365 天與 90 天都 ≤ 1.15 × 30 天的 → 安裝 10–1000 次 → 抽 40 筆讀 `.rb` → 用 ecosyste.ms repos 補星數與建立日期。

結果（2026-10-27 20:00 UTC，analytics 區間 09-27～10-27）：

| 項目 | 數字 |
|---|---|
| 30 天有安裝的 formula | 20,334（第三方 tap 12,264，來自 7,858 個 tap） |
| 第三方 tap 中「安裝幾乎都在最近 30 天」 | 4,066（1–5 次 3,310；6–20 次 564；21–100 次 159；101–1000 次 29；>1000 次 4） |
| 30 天安裝 10–1000 次 | 437 |
| 抽樣 40：找到 formula 檔 | 39 |
| 對到 GitHub repo | 36 |
| 用 release 預編譯檔 | 29 |
| repo 2026 年建立 | 36 |
| 星數中位數／<100 星 | 1／32 of 36（最大 3,510） |
| 和 AI／agent／LLM 相關 | 15 |

抽樣 5 筆（照輸出順序）：

| tap formula | 30 天安裝 | repo | 星 | 建立 | 說明 |
|---|---|---|---|---|---|
| secretli/tap/secretli | 30 | secretli/cli | 0 | 2026-10-06 | 本機加密分享祕密 |
| brendan-appstart/tap/bead-me-up-scotty | 47 | 同名 | 22 | 2026-06-17 | beads issue tracker 的本地 web UI |
| albersg/tap/dotfiles | 20 | albersg/dotfiles | 0 | 2026-03-07 | dotfiles 安裝 TUI |
| topogamer0/tap/ollama-c | 11 | Topogamer0/Ollama-C | 0 | 2026-10-21 | Ollama 的 C 客戶端函式庫（不是 CLI，要靠模型判讀剔除） |
| gitslice-io/tap/gitslice | 19 | （homepage 非 GitHub） | — | — | source graph CLI |

其他值得注意的：`beamivalice/tap/sushi`（Apple Silicon LLM 推論伺服器，296 星，30 天 194 次）、`fieldwork-ai/tap/lighter`（65 星）、`shashankswe2020-ux/tap/rigspark`（本地 LLM 選擇與執行 CLI，19 星）。品質判斷：大多是真的可用的 CLI，少數是函式庫或公司內部工具，正好交給 Meta 模型讀 README 判斷。

### 4.2 `spikes/ch_packages_registries.py`：PyPI、npm、crates.io、Go、AUR

```
PICKFIT_CONTACT=<email> python3 spikes/ch_packages_registries.py                 # 全部，約 6–8 分鐘
python3 spikes/ch_packages_registries.py --only pypi,crates --sample 20 --days 3   # 局部
```

做法：PyPI／npm／crates 的數量用 ecosyste.ms（`created_after`）；可執行判斷各用原生 API（wheel entry points、`bin`、`bin_names`、pkg.go.dev main）；Go 讀 index 最近 6 小時；AUR 讀 metadata dump。crates.io 呼叫間隔 1.05 秒。

結果（7 天窗；Go 為 6 小時；每個抽 30 筆）：

| 生態系 | 新套件 | 連 GitHub | 抽樣可執行 | 備註 |
|---|---|---|---|---|
| PyPI | 2,091（ecosyste.ms） | 71% | 12／30 有 console_scripts | 原生約 40／小時 ≈ 6,700／週；ecosyste.ms 延遲 34 h 而漏很多 |
| npm | 27,393（ecosyste.ms） | 64% | 7／30 有 bin | 5 筆抽樣中 3 筆是 staged publishing placeholder |
| crates.io | 5,041（ecosyste.ms）；原生 API 5,947 | 91% | 3／30 有 bin_names | 名稱保留的 crate 不少 |
| Go | 35,583 個版本事件、9,795 module、5,154 有 tag | 91%（tag module） | 11／25 有 main | 30 個抽樣中 5 個在 pkg.go.dev 查不到 |
| AUR | 831 | 80% | — | `-bin` 240、`-git` 122 |

查核時重跑（2026-10-27 21:10 UTC，預設參數，6 分 14 秒）：PyPI 2,091／71%／12 of 30；npm 27,484／64%／8 of 28；crates 5,067／91%／**6 of 29**；Go 36,480 事件、9,703 module、5,167 有 tag、查得到 21／30、**14 有 main**；AUR 821／80%（`-bin` 238、`-git` 121）；RSS 39 筆／64 分。數量與比例一致；抽樣比例因時間窗移動而變（crates 3→6、Go 11→14），小樣本只看量級。

另外手動量測（不在腳本裡）：

| 項目 | 數字 | 方法 |
|---|---|---|
| PyPI 原生新專案 | 22.4 h 內 901 個 create | XML-RPC `changelog_since_serial(last-60000)`；單次只回 50,000 筆，窗口止於呼叫前約 4 小時（查核時補） |
| PyPI RSS 涵蓋時間 | 40 筆＝64 分鐘 | `rss/packages.xml` |
| crates.io 原生新 crate | 7 天 5,947、24 h 808 | `/api/v1/crates?sort=new` seek 分頁 60 頁 |
| homebrew-core 新 formula | 7 天 13 個 | shallow clone 後 `git log` 找 `(new formula)` |
| winget 新套件 | 7 天 87 個（解析 84：GitHub 65、CLI 訊號 28、AI tag 10） | shallow clone 取 commit 標題，再讀 raw manifest |
| ecosyste.ms 延遲 | crates 0.4 h、npm 2.1 h、PyPI 34 h | `first_release_published_at` 到 `created_at` 的中位數 |

**沒辦法實測的**：GitHub REST／Search API。這個 session 的 GH_TOKEN 被限制在本專案 repo，打 `search/issues`、`repos/Homebrew/homebrew-core/...` 都回 403（「sessions are bound to their configured repositories」）。所以 homebrew-core 與 winget 改用 `git clone --filter --shallow-since`，tap 的 `.rb` 用 raw.githubusercontent.com。BigQuery（`bq`）未登入，PyPI／deps.dev 的 BigQuery 都沒實測；要用需 GCP 專案（`gcloud auth login` 後建專案，可用 BigQuery sandbox）。

---

## 5. 結論

### 黑客松期間值得接

| 管道 | 理由 | 工時 |
|---|---|---|
| Homebrew 第三方 tap（analytics） | 一次拿到「新、可執行、沒名氣、有安裝紀錄」四個訊號（安裝數含 CI）；開發者 CLI 類別貨多，本地 AI 類別抽樣只有約 3 筆；Mac 情境正好對上 demo 腳本「Mac 上、免費、離線」 | 3–4 h |
| Homebrew core（formula.json） | 知名度基準、`executables`、官方安裝方式；幾乎零成本 | 1 h |
| PyPI（RSS 輪詢＋JSON＋wheel entry points） | 本地 AI／LLM 工具的主要來源；`console_scripts` 篩 CLI。官方要新整合用 RSS，不用 XML-RPC | 3–4 h |
| deps.dev（GetVersion／GetProject） | 有簽章證明的 repo 對應（防冒名）；關聯資料 CC-BY 4.0（星數不是） | 1 h |

合計約 8–10 h。建議順序：Homebrew tap → Homebrew core → deps.dev 補資料 → PyPI。

**條件式**：ecosyste.ms（repos＋packages lookup，原估 2 h）。功能好用（免 GitHub token 拿 repo metadata、release assets），但 Terms §9 要求腳本存取先取得書面同意（見 2.12）。今天寄信；拿到同意再接，沒拿到就用 GitHub REST API 補 repo metadata。（查核時修正：原文列為黑客松直接接）

### 之後擴充

- **crates.io**：資料乾淨、`bin_names` 直接可用，但 CLI 比例低；1 req/s 要排程。
- **npm**：量最大、雜訊最高；等有更好的過濾（bin＋非 scoped＋有 README）再接。
- **winget**：Windows 情境、無安裝數；沙盒驗證要 Windows。
- **Go**：pkg.go.dev v1 API 很好用，但 index 量太大；之後可只追「新 module 第一個 tag」。
- **AUR**：新作品多，但只限 Arch 且無審查；之後可當 Linux 補充。

### 避開

| 管道 | 原因 |
|---|---|
| libraries.io | 要 API key、60 req/min，功能和 ecosyste.ms 重疊（後者也要先處理條款）；dump 停在 2020 |
| pypistats 大量抓取 | 官方明寫大量抓「DON'T」，改用 BigQuery |
| 爬 npmjs.com、aur.archlinux.org、pkg.go.dev 的網頁 | npm 條款禁止自動化存取網站；AUR 的 Anubis 查核時未出現（未驗證）；都有官方 API 或 dump 可用 |
| Scoop Main／Extras、Nixpkgs、conda-forge、Docker Hub 當發現來源 | 有星數門檻或無日期、無安裝數；新作品少 |
| 拿 ecosyste.ms 當 PyPI 即時來源 | 延遲約 34 小時 |

---

## 6. 給主控者：需要決定或修正的地方

1. **ecosyste.ms 條款與 CC BY-SA**：先決問題是 Terms §9 要求腳本存取前取得書面同意（見 2.12），要不要寄信由主控者決定。拿到同意後才談授權：資料是 CC BY-SA 4.0，若把它的欄位（下載數、dependents、repo metadata）寫進公開的軟體 YAML，衍生資料可能要用 BY-SA 釋出。選項：(a) 只在計分時即時查、不存；(b) 存，但整份資料集標 CC BY-SA 並註明出處；(c) 改用原生 registry 或 GitHub API 的欄位。**原文的 (c)「改用 deps.dev（CC-BY 4.0）」不成立**：deps.dev 只有自己產生的關聯資料是 CC-BY 4.0，星數來自 GitHub、下載數它沒有（查核時修正）。
2. **brief 第 8 節可能要修正**：「Homebrew、winget-pkgs、Flathub 可以（授權寬鬆），有安裝數等資料」。實測：winget **沒有**公開安裝數；homebrew-core 是 BSD-2-Clause、winget-pkgs 是 MIT，但 Homebrew analytics 的**資料授權沒有明示**。Flathub 不在本次範圍，未查證。
3. **GitHub API 在調研 session 被限制**：只能打本專案 repo。正式管線需要自己的 GitHub token（github.com → Settings → Developer settings → Fine-grained token，只要 public repo 唯讀）。
4. **BigQuery**：要用 PyPI 下載量或 deps.dev 資料集，需要 GCP 專案。免費額度：查詢每月前 1 TiB、儲存前 10 GiB（[BigQuery pricing](https://cloud.google.com/bigquery/pricing)，查核時補）。`file_downloads` 很大，查詢要限定日期分區，否則一次就可能用掉大半額度（未實測）。
5. **Homebrew 安裝數含 CI**（查核時補）：計分時不要把 tap 的安裝數當使用者數；最多當「有人在用」的弱訊號。

---

## 7. 來源（查證日期皆為 2026-10-28）

| 主題 | 連結 | 狀態 |
|---|---|---|
| Homebrew API 文件 | https://formulae.brew.sh/docs/api/ | 已讀 |
| Homebrew formula／cask／analytics JSON | https://formulae.brew.sh/api/formula.json 、 https://formulae.brew.sh/api/analytics/install-on-request/30d.json | 實測 |
| Homebrew 收錄政策 | https://docs.brew.sh/Package-Acceptance-Policy 、 https://docs.brew.sh/Acceptable-Formulae | 已讀 |
| Homebrew analytics 說明 | https://docs.brew.sh/Analytics | 已讀 |
| homebrew-core 歷史 | https://github.com/Homebrew/homebrew-core （shallow clone） | 實測 |
| winget-pkgs | https://github.com/microsoft/winget-pkgs （shallow clone、raw manifest） | 實測 |
| winget 政策 | https://learn.microsoft.com/en-us/windows/package-manager/package/windows-package-manager-policies | 已讀 |
| Scoop Main 條件 | https://github.com/ScoopInstaller/Scoop/wiki/Criteria-for-including-apps-in-the-main-bucket | 已讀 |
| Scoop Extras 條件 | https://github.com/ScoopInstaller/Extras/blob/master/.github/ISSUE_TEMPLATE/package-request.yml | 已讀 |
| PyPI API、RSS、JSON、BigQuery | https://docs.pypi.org/api/ 、 https://docs.pypi.org/api/feeds/ 、 https://docs.pypi.org/api/json/ 、 https://docs.pypi.org/api/bigquery/ | 已讀＋實測 |
| PyPI ToS | https://policies.python.org/pypi.org/Terms-of-Service/ | 已讀 |
| PyPI XML-RPC | https://pypi.org/pypi （`changelog_since_serial`） | 實測 |
| pypistats API | https://pypistats.org/api/ | 已讀＋實測 |
| npm replication 變更 | https://github.blog/changelog/2025-02-26-changes-and-deprecation-notice-for-npm-replication-apis/ | 已讀 |
| npm replicate | https://replicate.npmjs.com/_changes | 實測 |
| npm downloads API | https://github.com/npm/registry/blob/main/docs/download-counts.md 、 https://api.npmjs.org/downloads/point/last-week/ollama | 已讀＋實測 |
| npm 條款 | https://docs.npmjs.com/policies/open-source-terms | 已讀 |
| npm staged publishing | https://github.blog/changelog/2026-10-02-npm-staged-publishing-now-supports-creating-new-packages | 查核時已讀（頁面存在；與 placeholder 的關係仍是推測） |
| npm 爬蟲政策 | https://docs.npmjs.com/policies/crawlers | 查核時已讀 |
| crates.io Data Access | https://crates.io/data-access （原始碼 https://github.com/rust-lang/crates.io/blob/main/svelte/src/routes/data-access/+page.svelte ） | 已讀＋實測 |
| crates.io db dump 欄位 | https://github.com/rust-lang/crates.io/blob/main/crates/crates_io_database_dump/src/dump-db.toml | 已讀 |
| crates.io RSS／API | https://static.crates.io/rss/crates.xml 、 https://crates.io/api/v1/crates?sort=new | 實測 |
| Go index | https://index.golang.org/ | 已讀＋實測 |
| pkg.go.dev API | https://pkg.go.dev/v1/api 、 https://go.dev/blog/pkgsite-api | 已讀＋實測 |
| Docker Hub API | https://hub.docker.com/v2/repositories/ollama/ollama | 實測 |
| AUR metadata dump | https://aur.archlinux.org/packages-meta-v1.json.gz | 實測 |
| aurweb 原始碼（rate limit、RPC） | https://gitlab.archlinux.org/archlinux/aurweb （`conf/config.defaults`、`doc/rpc.txt`） | 已讀 |
| Nixpkgs channel | https://channels.nixos.org/nixos-unstable/packages.json.br 、 https://github.com/NixOS/nixpkgs/blob/master/COPYING | 實測 |
| anaconda.org API | https://api.anaconda.org/package/conda-forge/llm | 實測 |
| ecosyste.ms | https://ecosyste.ms/api 、 https://ecosyste.ms/commercial 、 https://packages.ecosyste.ms/open-data 、 https://packages.ecosyste.ms/docs/api/v1/openapi.yaml | 已讀＋實測 |
| deps.dev | https://docs.deps.dev/api/v3/ 、 https://docs.deps.dev/faq/ 、 https://docs.deps.dev/bigquery/v1/ | 已讀＋實測 |
| libraries.io | https://libraries.io/api 、 https://libraries.io/data 、 https://zenodo.org/records/3626071 | 已讀＋實測 |
| GitHub AUP | https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies | 已讀 |
| Homebrew analytics 產生方式 | https://github.com/Homebrew/brew/blob/main/Library/Homebrew/utils/analytics/influx.rb 、 https://github.com/Homebrew/brew/blob/main/Library/Homebrew/utils/analytics.rb 、 https://github.com/Homebrew/brew/blob/main/Library/Homebrew/utils/analytics.sh | 查核時已讀（raw） |
| ecosyste.ms 服務條款 | https://ecosyste.ms/terms | 查核時已讀 |
| Google APIs ToS | https://developers.google.com/terms （Last modified 2021-11-09） | 查核時已讀 |
| BigQuery 價格 | https://cloud.google.com/bigquery/pricing | 查核時已讀 |
| crates.io Policies | https://crates.io/policies （原始碼 `svelte/src/routes/policies/+page.svelte`） | 查核時已讀 |

---

## 查核紀錄（2026-10-28）

查核者：另一個 agent，預設懷疑。實測時間 2026-10-27 20:50–21:16 UTC（台北 10/28 04:50–05:16）。一律直接打官方 API 或讀官方文件；GitHub 檔案用 raw 或 shallow clone（本 session 的 GitHub API 只能打本 repo，查核時重測仍回 403，屬實）。沒執行任何 git commit／push／checkout。

### 關鍵主張逐條

| # | 主張 | 判定 | 依據／改了什麼 |
|---|---|---|---|
| 1 | Homebrew analytics 收第三方 tap；12,264 個、7,858 個 tap、4,066 個近 30 天新 | **成立，補但書** | 重抓 30／90／365d JSON，數字完全一致；清單 `sum(count)`＝`total_count`，沒有截斷。補：公開查詢沒排除 CI（brew 原始碼），「真的有人裝」改成「有安裝紀錄」 |
| 2 | API 文件無 rate limit／條款／授權；analytics 匿名彙總、收 non-private tap 名 | 成立 | formulae.brew.sh/docs/api/ 全文沒有相關字；docs.brew.sh/Analytics 原文相符。formulae.brew.sh repo 是 BSD-2-Clause，但 analytics JSON 不在 repo 裡（建置時產生），資料授權仍未明示 |
| 3 | homebrew-core 門檻 30/30/75、自薦 90/90/225、未滿 30 天不收、建議第三方 tap | 成立 | Package Acceptance Policy 原文相符。補：官方明講第三方 tap 不代表 Homebrew 背書 |
| 4 | crates.io API 1 req/s、必須帶 UA；sparse index／static 無 rate limit；dump 每 24h；`bin_names` public | 成立 | data-access 原始碼相符；不帶 UA 回 403；dump-db.toml `bin_names = "public"`。補：官方要求先用 index、dump，API 最後 |
| 5 | PyPI ToS 停權與 spam 條款；edge 無 rate limit、不要幾分鐘上千次、UA 可識別 | 成立，**但漏了關鍵一句** | 原文都相符。漏掉 API Preference：「No new integrations should use the XML-RPC APIs」。原文建議用 XML-RPC 回補，已改成 RSS 為主、XML-RPC 只當一次性回補 |
| 6 | RSS 40 筆約 64 分；`changelog` 停用；22.4h 901 create；JSON 無 entry points、downloads −1 | 成立，補細節 | 查核時 RSS 39 筆／74 分；`changelog` 回「deprecated, use changelog_since_serial」；`changelog_since_serial` 22.8h 909 create。補：單次上限 50,000 筆，原文窗口其實止於呼叫前約 4 小時 |
| 7 | pypistats 依 IP 限速 60、留 180 天、大量抓「DON'T」改用 BigQuery | 成立 | 回應頭 `x-ratelimit-limit: 60`；/api 頁原文相符 |
| 8 | npm 條款：不准自動化存取網站、可用 Public APIs 複製、500 萬次不合理、不得當通用資料庫、安全資料只能自用 | **部分錯** | 前三項與最後一項相符。「不得當通用資料庫」在 Acceptable Content，是限制上傳內容，不是讀取；已改。補：crawlers 政策允許 ≤1 req/s 實驗性爬蟲（由 npm 裁量） |
| 9 | replicate `_changes` 只回 id／rev、`include_docs` 回 400；bulk 128、不支援 scoped、最多 365 天 | 成立（主張清單正確，**檔案內文寫錯**） | 實測相符。檔案原寫「bulk…最多 18 個月」，官方是 bulk 365 天、非 bulk 18 個月；已改 |
| 10 | pkg.go.dev `/v1` 能用 `name == "main"` 篩、45 QPS／IP block；index 單次最多 2000 | 成立 | fzf 回 1 個 main；cobra `importedByCounts.modules` 99,323；`limit=5000` 回 400；index 頁「Default = 2000, Max = 2000」 |
| 11 | ecosyste.ms CC BY-SA 4.0、AGPL-3；匿名 5,000、polite 15,000；延遲 34／2.1／0.4 h | 數字成立，**建議與條款衝突** | 回應頭與延遲重測一致（32.9／2.6／0.3 h）。但 Terms §9 禁止未經書面同意的腳本擷取資料，§11(c) 只授權個人使用、不含資料探勘。原文建議「黑客松接」，已改成「取得書面同意後才接」 |
| 12 | deps.dev 受 Google API ToS、CC-BY 4.0、可快取、無 rate limit、7 個生態系、provenance 分類 | 成立，**授權範圍寫太寬** | vite 有 `SLSA_ATTESTATION`、llm 有 `PYPI_PUBLISH_ATTESTATION`；Homebrew 回 404。但 CC-BY 4.0 只涵蓋 deps.dev 產生的資料，星數來自 GitHub；Google APIs ToS §5(e) 禁止用 API 內容建資料庫或公開展示。第 6 節「改用 deps.dev（CC-BY）」已改 |
| 13 | libraries.io 要 key、60/min、search 無 key 401；CC-BY-SA 4.0；dump 1.6.0（2020-01-12） | 成立 | search 401、單一專案 200；首頁頁尾原文相符；Zenodo API 1.6.0／2020-01-12／cc-by-4.0 |
| 14 | winget MIT、無 notability 門檻、無安裝數、7 天 87 個；Scoop Main 500+150、Extras 100 和/或 50 | 成立 | LICENSE、政策原文、wiki、issue template 相符；shallow clone 重數 87。「winget 沒有公開安裝數」是查不到官方來源，不是官方明文 |
| 15 | AUR RPC 預設 4,000／日／IP；正式站未驗證 | 成立（維持未驗證） | `conf/config.defaults` 相符；正式站 RPC 回應頭沒有 rate limit 資訊，仍未驗證 |

### 其他影響決策的事實

| 項目 | 判定 | 說明 |
|---|---|---|
| Homebrew 抽樣「15 筆和 AI 相關」 | 數字約略成立，**解讀過頭** | 人工重數 16 筆，多數是 coding agent 周邊工具；真的屬於本地 AI／LLM 工具的約 3 筆。已改 2.1 與結論 |
| homebrew-core 7 天 13 個新 formula | 成立 | shallow clone 重數 13。「不少是作者自薦」只部分可信，zvec-grep 對不上；已改為未逐一確認 |
| ripgrep 30 天 48,775 | 成立，補欄位 | 那是 `install`（含依賴）；`install_on_request` 是 37,725 |
| crates.io 原生 7 天 5,947、91% GitHub | 成立 | 以 1 req/s 重數 5,961、90.5% |
| AUR／ArchWiki 有 Anubis | **未驗證** | 查核時兩邊都直接 200，沒出現挑戰頁；已標未驗證 |
| GitHub AUP 第 7 節 | 成立 | 原文：Scraping＝自動化擷取，不含 API；研究（需開放取用）與封存可用 |
| BigQuery 免費額度（原文未查證） | 已補 | 查詢每月 1 TiB、儲存 10 GiB 免費 |
| PyPI BigQuery 資料授權 | 已補 | docs 連到 CC BY 4.0 |
| Docker Hub `x-ratelimit-limit: 180`、ollama pull 數 | 成立 | 重測 180；pull_count 192,697,916 |
| npm staged publishing 2026-10-02 | 頁面存在 | 與 placeholder 的關係仍是推測 |

### 腳本重跑

| 腳本 | 結果 | 金鑰 |
|---|---|---|
| `spikes/ch_packages_brew_taps.py`（預設參數） | 18.5 秒跑完；所有數字與第 4.1 節完全一致（20,334／12,264／7,858／4,066／437；39／36／29／36；中位數 1、32／36、最大 3,510）；前 5 筆相同 | 無；只讀 `PICKFIT_CONTACT`、`PICKFIT_JSON` |
| `spikes/ch_packages_registries.py`（預設參數） | 6 分 14 秒跑完；數量與比例一致，小樣本比例有變動（見 4.2 下方） | 無；只讀 `PICKFIT_CONTACT` |

腳本的小問題（不影響本次結果）：analytics、RSS、Go index 抓取失敗時 `get()` 回 `None`，後面直接取值會丟例外；兩支腳本都呼叫 ecosyste.ms，若主控者決定在取得同意前不用它，正式管線不要沿用這兩支腳本的做法。查核重跑沒有帶 `PICKFIT_CONTACT`。

### 改了什麼（摘要）

1. ecosyste.ms 從「黑客松接」改成「取得書面同意後才接」；工時合計從 10–12 h 改成 8–10 h（不含 ecosyste.ms）。
2. PyPI 改成 RSS 輪詢為主；XML-RPC 只當一次性回補，並註明 50,000 筆上限。
3. deps.dev 的 CC-BY 4.0 範圍縮到它自己產生的資料；第 6 節選項 (c) 改正。
4. Homebrew 安裝數補「含 CI」；本地 AI 類別在 tap 裡只有約 3 筆。
5. npm 條款「通用資料庫」誤用改正；downloads API 期間上限改正。
6. AUR Anubis 改標未驗證；BigQuery 免費額度補上；crates／Go 重跑數字補上。
