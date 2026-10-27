2026-10-28 · B 節：怎麼判斷「可用的軟體」與「品質好不好」 · 由調研 agent 撰寫，待主控者整合

# 調研：可用軟體的判斷、品質與知名度計分

需求來源：[brief.md](../../brief.md) 第 4、7、10、11 節；[hackathon-rules.md](../../hackathon-rules.md)。查證日期一律是 2026-10-28（台北），也就是 2026-10-27 UTC 晚間。實測腳本：[spikes/quality_signals.py](../../../spikes/quality_signals.py)。

## 一句話結論

- **規則只能做第一層篩選。** 在 227 個最近一年的 Show HN repo 上，規則判定 142 個是工具、34 個要交給模型、1 個是函式庫。「函式庫還是工具」用規則很難分，要交給 Muse Spark。
- **用規則算品質會飽和。** 今年的小專案多半有 CI、測試、changelog、release，這些用 AI 很容易做出來。實測 5 個小工具「若驗證通過」的品質是 80–100，知名的 bat 是 90，分不開。**品質排序要靠沙盒驗證，再加上模型依 rubric 讀文件；規則只當門檻。**
- **OpenSSF Scorecard 幾乎不涵蓋長尾。** 227 個 Show HN repo 只有 7 個（3%）在 REST API 查得到，連 ollama/ollama 都是 404。可以自己跑 CLI：`--local` 模式不需要 token，不到 1 秒就跑完 11 個 check。適合在沙盒 clone 後順便跑。
- **ecosyste.ms 一個來源就涵蓋大部分欄位**：repo、release（含下載數）、issue 關閉時間、committer、各套件庫的下載量、檔案列表。227 個 repo 中涵蓋 177 個（78%）。授權是 CC-BY-SA-4.0。
- **寶藏的定義**：必須是工具、沙盒驗證通過、品質 ≥ 70、知名度 ≤ 45，排序看「品質 − 知名度」。防灌水的原則是不獎勵數量，README 一律當成不可信的輸入。

---

## 0. 本次實測的環境限制

| 端點 | 結果 | 影響 |
|---|---|---|
| `api.github.com` REST（帶 GH_TOKEN） | 只有本 session 的 repo（ncchen99/pickfit）回 200，其他 repo 都回 403：「GitHub access to this repository is not enabled for this session」 | spike 改用 ecosyste.ms 的鏡像資料。正式環境用自己的 PAT（5,000 req/h，[GitHub 文件](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)）就沒有這個問題 |
| `api.github.com/graphql` | 403：「GitHub GraphQL is not available from Claude Code sessions」 | Scorecard CLI 的 `--repo` 模式跑不起來 |
| `codeload.github.com`（tarball） | 403 | 改用 archives.ecosyste.ms 列出檔案 |
| `raw.githubusercontent.com` | 200 | README、manifest 照常讀 |

spike 會先試 GitHub API，失敗才改用 ecosyste.ms，所以正式環境可以沿用同一支程式。

---

## 1. 「可用的軟體」和其他東西怎麼分

### 1.1 用規則判斷的訊號

**正向（P，像是可安裝的工具）**

| 訊號 | 怎麼拿 | 分數 | 依據 |
|---|---|---|---|
| README 有安裝小節（Install、Getting started、Quick start、Setup、Download、安裝） | raw README，比對標題 | +2 | — |
| README 有用法小節（Usage、Examples、Commands、使用） | 同上 | +1 | — |
| README 有安裝指令（`brew install`、`cargo install`、`pipx`/`uv tool install`、`npm i -g`、`go install`、winget／scoop、`curl … \| sh`、`docker run`） | 同上 | +2 | — |
| Release 附二進位檔（檔名含 darwin、linux、windows、arm64、x86_64，或副檔名 .dmg、.exe、.msi、.deb、.rpm、.AppImage） | GitHub releases 或 ecosyste.ms releases | +3（強訊號） | — |
| 套件中繼資料有執行入口：package.json 的 `bin`；pyproject 的 `[project.scripts]`／`gui-scripts`；setup.cfg 的 `console_scripts`；Cargo 的 `src/main.rs`、`src/bin/`、`[[bin]]`；Go 根目錄的 `main.go` 或 `cmd/<名稱>/main.go`；Xcode、Tauri、Package.swift 專案 | 檔案樹＋raw manifest | +3（強訊號） | [npm bin](https://docs.npmjs.com/cli/configuring-npm/package-json#bin)、[PyPA entry points](https://packaging.python.org/en/latest/specifications/pyproject-toml/)（`[project.scripts]` 就是 console_scripts）、[Cargo targets](https://doc.rust-lang.org/cargo/reference/cargo-targets.html)、[Go module layout](https://go.dev/doc/modules/layout)（`cmd/` 是慣例，不是規定） |
| 被套件庫收錄（Homebrew、Debian、Alpine、nixpkgs、AUR、winget…） | packages.ecosyste.ms lookup | +2（強訊號） | — |
| topics 含 cli、tui、terminal、self-hosted、local-llm 等 | repo 中繼資料 | +1 | — |

Go 的 `examples/*/main.go` 不算執行入口。第一版把它算進去，結果把 okunix/gollama（Ollama 的 Go 用戶端函式庫）誤判成工具。

**負向（N，不是軟體）**：名稱或 topics 命中算 4 分，只在描述裡命中算 2 分。

| 類型 | 規則 |
|---|---|
| awesome 清單 | 名稱 `awesome-*`、「curated list」；README 有超過 40 個「`- [名稱](http…)`」清單項目，再加 3 分 |
| 作業、課程 | homework、assignment、coursework、course、exercises、leetcode、bootcamp、lab1、作業 |
| 教學 | tutorial、cheat sheet、for beginners、「30 days of」、learn-rust 等。**不要用 `learning`**：第一版把 machine-learning topic 和「Learn to sing」都判成教學 |
| 模板 | template、starter、boilerplate、skeleton（只看名稱或 topics；GitHub 的 `is_template` 為 true 時直接算 4 分）。第一版因為描述裡有 boilerplate，把一個 scaffolding CLI 判成模板 |
| dotfiles | dotfiles、vim config |
| demo | demo、proof of concept、poc、example(s)、sample（2 分） |
| 沒有程式碼檔 | 4 分 |

**函式庫（L）**

| 訊號 | 分數 |
|---|---|
| package.json 有 `main`／`exports`，但沒有 `bin` | 2 |
| 有 go.mod，但沒有根目錄或 `cmd/` 的 main | 2 |
| Cargo 只有 `src/lib.rs` | 2 |
| pyproject 沒有 scripts | 1（弱訊號：很多 Python app 是用 `python -m` 或 docker 執行） |
| README 只示範 `go get`、`import x`、`require("x")`，沒有安裝指令 | 2 |
| 描述寫 library、SDK、framework、bindings、api client | 2 |

### 1.2 判定順序

1. N ≥ 4 且 N ≥ P：**不是軟體**（清單、作業、模板等）。
2. L ≥ 4，而且沒有強訊號（執行入口、二進位檔、套件庫收錄）：**函式庫**。
3. N < 4、L < 2，而且有強訊號或 P ≥ 4：**工具**。
4. 其他：**交給模型**。

### 1.3 實測：227 個 Show HN repo

樣本：用 HN Algolia API 查 2025-10-01 之後、`tags=show_hn` 的貼文，關鍵字為 cli、terminal、local llm、ollama、offline、command line、llama.cpp，取網址是 GitHub repo 的貼文，去重後 227 個。指令：`python3 spikes/quality_signals.py --from-file repos.txt --classify-only`，約 60 秒。

| 結果 | 數量 | 說明 |
|---|---|---|
| 工具 | 142 | 占有資料的 177 個中的 80% |
| 交給模型 | 34 | 19% |
| 函式庫 | 1 | okunix/gollama |
| 不是軟體 | 0 | Show HN 本來就很少清單或作業；反例改用 awesome-cli-apps 測（見 3.5） |
| 沒資料 | 50 | ecosyste.ms 沒收錄，GitHub API 又被擋。其中 46 個 README 還在，表示 repo 存在 |

- **精確率未驗證**。我目測抽查 40 個判為「工具」的 repo：32 個確定是可安裝的工具；4 個不是（benchmark 網站、模型權重、Java 推論函式庫、benchmark 資料集）；4 個難以判斷（protocol、llama.cpp 修補）。沒有建立標註集。
- 第二版規則把 L ≥ 2 就判成函式庫，13 個中約 7 個判錯（例如描述提到 SDK 的 CLI、Python 推論伺服器、Windows 桌面 app）。改成「至少兩個函式庫訊號，而且沒有強訊號」之後只剩 1 個，其餘都交給模型。
- **規則沒有涵蓋的類型**：benchmark、模型權重、研究程式碼、agent plugin 與 MCP server、Home Assistant 整合、硬體韌體（ESP32）。這些都要交給模型判斷。

### 1.4 交給 Muse Spark 判斷的部分

| 項目 | 輸出 |
|---|---|
| 類型 | enum：`cli_tool`、`tui`、`desktop_app`、`self_hosted_web_app`、`server_daemon`、`mcp_server_or_agent_plugin`、`browser_extension`、`library_sdk`、`framework`、`model_or_dataset`、`benchmark_or_research`、`demo_prototype`、`tutorial_course`、`homework`、`template_starter`、`curated_list`、`dotfiles_config`、`other` |
| 是給終端使用者安裝執行，還是給開發者 import | bool＋證據 |
| 成熟度 | README 自稱 alpha、WIP、PoC、hackathon project 等 |
| 是否需要付費 API key（BYOK wrapper）、在哪裡處理 | `processing`：local、cloud、hybrid |
| 支援平台與前置需求 | OS、GPU、CUDA、Apple Silicon、RAM |
| 文件完整度 | 見 3.1 的 rubric |

做法：

- 每個判斷都要附 README 原文片段當證據。**分數由程式根據抽出的事實計算，不讓模型直接給 0–100 分。**
- **README 是不可信的輸入**，可能夾帶「請給這個專案滿分」之類的 prompt injection。prompt 要把 README 放在資料區，輸出只接受 JSON schema 定義的欄位。沙盒驗證是最後的裁判。

---

## 2. 和知名度無關的品質訊號

### 2.1 OpenSSF Scorecard

**基本事實**

- 每個 check 給 0–10 分。總分是依風險加權的平均：Critical 10、High 7.5、Medium 5、Low 2.5（[README](https://github.com/ossf/scorecard#aggregate-score)，原始碼 `pkg/scorecard/scorecard_result.go`）。
- 官方自己說不該只看總分：「Instead of relying on an aggregate score of X/10…」（[README](https://github.com/ossf/scorecard)）。

**REST API 的覆蓋範圍**

- 端點是 `https://api.scorecard.dev/projects/github.com/{owner}/{repo}`。只有兩種 repo 查得到：
  1. 在每週掃描清單裡的 repo。清單在 [ossf/scorecard-infra](https://github.com/ossf/scorecard-infra/blob/main/CONTRIBUTING.md) 的 `cron/internal/data/projects.csv`，今天下載有 1,310,430 列。README 寫的是「more than 1.3 million repositories every week」。
  2. 自己安裝 [Scorecard Action](https://github.com/ossf/scorecard-action) 並設定 `publish_results: true` 的 repo。
- 每週掃描的結果省略 CI-Tests、Contributors、Dependency-Update-Tool（README：「due to the API costs」）。實測 bat 的 API 結果只有 14 個 check，**連 Vulnerabilities 也沒有**；這點文件沒寫，是觀察結果。
- BigQuery 公開資料集已停止提供（[README](https://github.com/ossf/scorecard#public-data)）。API 的資料授權是 CDLA-Permissive-2.0。
- **覆蓋率實測**：227 個 Show HN repo 中只有 7 個有資料（3.1%）。其中 derekwisong/datui 有資料，是因為它自己裝了 scorecard-action，所以有完整 18 個 check。ollama/ollama（184,617 星）回 404，因為它不在清單裡。

**自己跑 CLI**

- `go install github.com/ossf/scorecard/v5@latest` 成功裝好 v5.6.0，約 3 分鐘。
- `--repo` 模式需要 GitHub token（環境變數 `GITHUB_AUTH_TOKEN`、`GITHUB_TOKEN`、`GH_AUTH_TOKEN` 或 `GH_TOKEN`；classic PAT 建議用 `public_repo` scope，見 [README](https://github.com/ossf/scorecard#authentication)），而且會呼叫 GraphQL。本 session 的 GraphQL 被擋，所以跑不起來。
- `--local=<資料夾>` 模式**不需要 token**，0.9 秒跑完 11 個檔案型 check：Binary-Artifacts、Dangerous-Workflow、Dependency-Update-Tool、Fuzzing、License、Packaging、Pinned-Dependencies、SAST、Security-Policy、Token-Permissions、Vulnerabilities。其中 Vulnerabilities 會連到 OSV。
- Maintained 對建立未滿 90 天的 repo 直接給最低分。原始碼 `checks/evaluation/maintained.go`（v5.6.0）寫的是：「project was created within the last 90 days. Please review its contents carefully」。

**各 check 對小專案是否公平**（說明出自 [docs/checks.md](https://github.com/ossf/scorecard/blob/main/docs/checks.md)）

| check | 風險 | 小專案 | 理由 |
|---|---|---|---|
| Binary-Artifacts | High | 適合 | 不把執行檔放進 repo 是基本衛生 |
| Branch-Protection | High | 不公平 | 單人專案通常不設；部分設定要 admin token 才看得到 |
| CI-Tests | Low | 適合 | 看最近約 30 個 commit 的 CheckRuns；每週掃描不跑這項 |
| CII-Best-Practices | Low | 不公平 | 要另外申請徽章，小專案幾乎都是 0 分 |
| Code-Review | High | 不公平 | 單人直接 push，datui 的結果是「0/30 approved」 |
| Contributors | Low | 不公平 | 要求 3 家不同公司的貢獻者，官方文件自己也承認小專案做不到 |
| Dangerous-Workflow | Critical | 適合 | 有 workflow 才計分 |
| Dependency-Update-Tool | High | 部分 | Dependabot、Renovate 很容易設定，有設定不代表品質好 |
| Fuzzing | Medium | 不公平 | CLI 工具很少做 fuzz |
| License | Low | 適合 | — |
| Maintained | High | 對新 repo 不公平 | 未滿 90 天直接 0 分；我們自己算最近活動 |
| Packaging | Medium | 適合 | 只看 GitHub workflow 是否發布套件；用 tap 或手動上傳的會漏掉 |
| Pinned-Dependencies | Medium | 部分 | — |
| SAST | Medium | 部分 | 要 CodeQL 之類的工具，小專案很少用 |
| SBOM | Medium | 不採用 | CLI `--checks` 的預設清單沒有這項 |
| Security-Policy | Medium | 部分 | 加一個 SECURITY.md 很容易 |
| Signed-Releases | High | 部分 | 有 release 才計分 |
| Token-Permissions | High | 適合 | workflow 權限是否最小化 |
| Vulnerabilities | High | 適合 | 用 OSV 查已知漏洞（datui 有 9 個） |
| Webhooks | Critical | 不採用 | 要 admin token |

**建議**：只取「適合」與「部分」中的 10 項（見 spike 的 `SC_FAIR`）算平均，占工程衛生分數的 20%。查不到 Scorecard 就不算，不扣分。

### 2.2 CHAOSS 指標

| 指標（官方頁） | 問的問題 | pickfit 怎麼算 | 資料來源 | 是否採用 |
|---|---|---|---|---|
| [Issue Response Time](https://chaoss.community/kb/metric-issue-response-time/) | 開 issue 後，多久得到「作者以外的人」第一次回應 | 外部使用者開的 issue，維護者第一次回覆時間的中位數 | GitHub issues＋comments API（ecosyste.ms 只有關閉時間） | 採用。issue 少於 3 筆就不算。本環境**沒有實測** |
| [Time to First Response](https://chaoss.community/kb/metric-time-to-first-response/) | 同上，也包含 PR | 同上 | 同上 | 和上一項合併 |
| [Change Request Closure Ratio](https://chaoss.community/kb/metric-change-request-closure-ratio/) | 是否跟得上 PR | 合併的 PR 數 ÷ PR 總數 | issues.ecosyste.ms | 採用（PR ≥ 3 才算） |
| [Change Requests Duration](https://chaoss.community/kb/metric-change-requests-duration/) | 被接受的 PR 從開到合併要多久 | `avg_time_to_close_pull_request` | issues.ecosyste.ms | 只顯示 |
| [Release Frequency](https://chaoss.community/kb/metric-release-frequency/) | 多久發一次 release | 一年內發 ≥ 2 次就滿分 | release 列表 | 採用，但**不獎勵更多次**（防刷） |
| [Contributor Absence Factor](https://chaoss.community/kb/metric-contributor-absence-factor/)（原名 Bus Factor） | 貢獻 50% commit 的最少人數 | 排除 bot 後計算 | commits.ecosyste.ms | **不計分**。小專案一定是 1，而小專案正是我們要找的；只顯示 |
| [Issue Age](https://chaoss.community/kb/metric-issue-age/) | 開著的 issue 開了多久 | — | GitHub | 之後擴充 |
| [Libyears](https://chaoss.community/kb/metric-libyears/) | 依賴套件落後最新版多久 | — | deps.dev、ecosyste.ms manifests | 之後擴充 |
| [Documentation Usability](https://chaoss.community/kb/metric-documentation-usability/) | 文件內容與結構是否好用 | 模型依 rubric 打分 | README | 採用，對應「文件完整度」 |
| [Elephant Factor](https://chaoss.community/kb/metric-elephant-factor/) | 工作是否集中在少數公司 | — | — | 不採用 |

### 2.3 ecosyste.ms 提供的欄位

| 服務 | 端點 | 主要欄位 | 涵蓋（227 個 Show HN repo） |
|---|---|---|---|
| repos | `repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/{owner%2Frepo}` | stargazers_count、forks_count、open_issues_count、created_at、pushed_at、archived、fork、template、topics、license、language、tags_count、`metadata.files`（readme、changelog、contributing、security、codeowners 等）、commit_stats、scorecard（內嵌舊副本；gum 的是 2025-08-11） | 177（78%） |
| repos releases | `…/releases` | tag_name、published_at、prerelease、body、assets（name、size、**download_count**、digest） | 同上 |
| repos manifests | `…/manifests` | 依賴檔、GitHub Actions workflow 與用到的 action（可看出有沒有 scorecard-action、CI） | 同上 |
| issues | `issues.ecosyste.ms/api/v1/hosts/GitHub/repositories/…` | issues_count、issues_closed_count、avg_time_to_close_issue、pull_requests_count、merged_pull_requests_count、avg_time_to_close_pull_request、past_year_*、issue_author_associations_count、maintainers | 100（44%） |
| commits | `commits.ecosyste.ms/…` | total_commits、total_committers、dds、past_year_*、committers[] | 75（33%） |
| packages | `packages.ecosyste.ms/api/v1/packages/lookup?repository_url=` | ecosystem、downloads＋downloads_period（npm、PyPI、Homebrew 是 last-month，cargo 是 total）、dependent_repos_count、dependent_packages_count、rankings、first／latest_release_published_at | — |
| archives | `archives.ecosyste.ms/api/v1/archives/list?url=<tarball>` | 檔案路徑列表 | — |
| timeline | `timeline.ecosyste.ms/api/v1/events/{owner}/{repo}` | GH Archive 事件，包含 WatchEvent | datui 只回 26 筆，實際有 137 星。**資料不完整，不能用來偵測星數暴增** |

**限制**

- **同步有延遲**：convkit 的同步日是 10-12，photoc 是 10-06。很新的 repo 不一定查得到；呼叫 `repositories/lookup` 也不會立刻補上（minebender 查完仍是 404）。
- **速率限制**（看回應 header）：匿名 5,000 次／小時；在 User-Agent 或參數帶 `mailto` 會進 polite pool，15,000 次／小時（[ecosyste.ms API 頁](https://ecosyste.ms/api)）。
- **授權**：CC-BY-SA-4.0（API 頁與 OpenAPI 的 `info.license`）。存進我們的 YAML 並公開時要標示來源；衍生資料可能也要採用同樣的授權（**沒有請教法律意見**）。另有商用 API。
- **結論**：正式環境以 GitHub API 為主（即時、完整），ecosyste.ms 用來補 issue 統計、下載量與套件庫收錄。

### 2.4 deps.dev

- `GET https://api.deps.dev/v3/projects/{github.com%2Fowner%2Frepo}` 回傳 openIssuesCount、starsCount、forksCount、license、description、homepage、scorecard（又是另一份副本；datui 的是 2026-08-24 版）（[API v3 文件](https://docs.deps.dev/api/v3/)：「when known to us」）。
- 只有被 npm、PyPI、Go、Maven、Cargo、NuGet、RubyGems 套件連到的 repo 才查得到。227 個中有 64 個（28%）；photoc、mere-run 都是 404。
- `:packageversions` 會列出連到這個 repo 的套件版本，以及 SLSA provenance 和 attestations。
- 對 pickfit 的用途有限：拿來交叉核對星數，以及當作「有沒有發布到套件庫」的旁證。資料授權**未查**。

### 2.5 pickfit 自己的訊號

| 訊號 | 怎麼量 | 為什麼重要 |
|---|---|---|
| 沙盒驗證結果 | 照 README 安裝，執行 `--help` 和一個最小範例：通過、失敗、要修正才通過 | 唯一沒辦法靠 AI 便宜做出來的訊號 |
| 安裝步驟數 | 驗證 agent 實際執行的指令數（不含 `cd`） | 步驟越少越好上手 |
| README 和實際操作的差距 | agent 要修正幾處才裝得起來 | 這就是我們能提供、agent 自己最容易答錯的資訊 |
| 文件完整度 | Muse Spark 依 rubric 打分（見 3.1）。便宜的旁證：GitHub community profile 的 `health_percentage`，以及 README、LICENSE、CONTRIBUTING 等檔案是否存在（ecosyste.ms 的 `metadata.files` 也有） | 對應 CHAOSS 的 Documentation Usability |
| 最近 release、CI、測試、授權 | 檔案樹＋release 列表 | 便宜，但用 AI 容易做出來，所以權重低 |
| 使用結果 | `report_outcome` 的成功率 | brief 說「看結果，不只看評論」；黑客松初期沒有資料 |

---

## 3. 計分草案

### 3.1 quality（0–100）

| 分項 | 權重 | 怎麼算（0–1） |
|---|---|---|
| 沙盒驗證 | 35 | 通過且 ≤ 3 步：1.0；4–6 步：0.85；> 6 步：0.7；要改 README 的步驟才成功：再 × 0.8；失敗：0 |
| 安裝與文件 | 20 | 正式版：模型依 rubric 評 8 項，每項 0／1／2 分，總分 ÷ 16。8 項是：做什麼、適合誰、前置需求、各 OS 的安裝方式、第一次執行的範例與預期輸出、設定與金鑰、疑難排解與移除、授權與平台。spike 先用規則近似：安裝小節 0.25、用法小節 0.2、安裝指令 0.15、有預編譯檔或套件 0.25、README 長度 0.15 |
| 維護 | 15 | 最近 push（≤ 90 天 1、≤ 180 天 0.6、≤ 365 天 0.3）占 0.35；最近 release（≤ 180 天 1、≤ 365 天 0.6、≤ 730 天 0.3）占 0.35；一年 ≥ 2 次 release 占 0.3（建立未滿 180 天、發過 1 次就算滿分）。**不計 commit 數** |
| 工程衛生 | 10 | CI 0.25、測試 0.25、OSI 授權 0.2、changelog 或 release notes 0.15、lockfile 0.15。有 Scorecard 資料時：0.8 × 自算分數 ＋ 0.2 × 公平 check 的平均 |
| 回應 | 10 | 外部使用者開的 issue ≥ 2 筆才計算：關閉比例 0.4、平均關閉時間（≤ 7 天 1、≤ 30 天 0.6、≤ 90 天 0.3、其他 0.1）0.4、PR 合併比例 0.2（PR ≥ 3 才算）。正式版改用 CHAOSS 的 Issue Response Time |
| 使用結果 | 10 | `report_outcome` 的成功率（≥ 3 筆才算） |

**缺資料怎麼處理**：缺的分項不算 0 分，而是從分母拿掉後重新正規化。另外輸出 `confidence` = 有資料的權重 ÷ 100。沙盒驗證缺資料時，confidence 最高只有 0.55。

**上限**：

| 條件 | 品質上限 |
|---|---|
| repo 已 archived | 30 |
| 沙盒驗證失敗 | 40 |
| 分類不是工具（函式庫、不是軟體、交給模型但還沒判定） | 50 |
| 還沒驗證，或沙盒跑不了（GUI、需要權限） | 69（剛好低於寶藏門檻 70） |

### 3.2 popularity（0–100）

- 每個訊號用對數正規化：`norm = 100 × log10(1 + x) ÷ log10(1 + ref)`，超過 ref 就算 100。星數分布是長尾，從 10 星到 100 星的意義，和從 1k 到 10k 差不多。
- `absolute` = 有資料的訊號依權重平均。

| 訊號 | 權重 | ref（CLI） | ref（本地 AI） | 來源 |
|---|---|---|---|---|
| stars | 0.35 | 20,000 | 60,000 | GitHub／ecosyste.ms |
| forks | 0.10 | 1,500 | 6,000 | 同上 |
| 每月下載量（各套件庫取最大值後加總；cargo 的 total 除以發布後月數） | 0.15 | 200,000 | 500,000 | packages.ecosyste.ms。Homebrew 的值（last-month）和 formulae.brew.sh 的 30 天安裝數接近（bat：16,104 對 16,769，快照時間不同），也可以直接查官方 API |
| dependent repos | 0.10 | 2,000 | 2,000 | 同上 |
| release 資產下載總數（最近 30 個 release） | 0.10 | 200,000 | 500,000 | releases |
| HN 最高分 | 0.10 | 500 | 800 | HN Algolia |
| 被幾個套件庫收錄（Homebrew、Debian、nixpkgs…） | 0.10 | 8 | 6 | packages.ecosyste.ms |

- **依類別校正**：本地 AI 類的星數普遍比較高，所以 ref 也比較高。ref 目前是**未經校準的初始猜測**，收完每個類別約 500 個候選後，改成用類別內的 P95 當 100 分。
- **依年齡校正**：建立 ≥ 3 個月時，`popularity = 0.75 × absolute + 0.25 × velocity`，其中 `velocity = norm(每月星數, ref_stars ÷ 24)`，也就是兩年內達到 ref 算 100 分。未滿 3 個月時不算 velocity（太不穩定）。

### 3.3 寶藏判定

- **必要條件**：分類是工具；沙盒驗證通過；沒有 archived；有 OSI 授權（沒有的要明確標示）。
- **寶藏**：quality ≥ 70 且 popularity ≤ 45。
- **排序**：`gap = quality − popularity`。不過推薦時先配對條件（OS、預算、能否本機執行、語言）；寶藏只在符合條件的候選中加分，並寫進推薦理由（brief：「推薦是配對，不是排名」）。
- 門檻要等收完候選、看過分布後再調整，例如 popularity 改用類別內的 P60。

### 3.4 防灌水

| 手法 | 怎麼偵測 | 怎麼處理 |
|---|---|---|
| 買星、互刷星 | 單週新增的星數超過總數 50% 且超過 200；forks／stars < 0.5%；星數 ≥ 300 卻沒有任何 issue 或 PR；用 stargazers API 加 `Accept: application/vnd.github.star+json` 取 `starred_at` 時間分布（[GitHub 文件](https://docs.github.com/en/rest/activity/starring)） | 星數只影響知名度，不影響品質；出現旗標就人工抽查 |
| 刷 commit、刷 release | — | 不計 commit 數；release 只看一年內是否 ≥ 2 次，數量不加分 |
| 自己開 issue 自己回 | 只計 author_association 不是 OWNER、MEMBER、COLLABORATOR 的 issue | — |
| 在 README 灌關鍵字或塞 prompt injection | 模型只抽事實並附原文；分數由程式計算 | 沙盒驗證是最後的裁判 |
| 刷套件下載量 | — | 下載量只算進知名度 |
| 開放提交被洗版 | 作者登入、同一作者每天有上限、人工抽查 | brief 第 13 節 |
| 不同資料源互相矛盾 | deps.dev 和 GitHub 的星數差距超過 max(50, 20%) 才標旗標。小數字的差距多半只是同步延遲（第一版因為 convkit 的 19 星對 24 星就誤報） | — |

依據：

- StarScout 研究（[arXiv 2412.13459](https://arxiv.org/abs/2412.13459)，標題「Six Million (Suspected) Fake Stars in GitHub」）。假星活動在 2024 年暴增。參與的帳號活動模式很單薄。除了釣魚與惡意程式，假星多半被拿來推 **AI/LLM、工具與 App、教學與 demo** repo，正好是我們的兩個類別。假星只在短期（不到兩個月）有效。
- GitHub [Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies) 第 4 節禁止「inauthentic interactions, such as fake accounts and automated inauthentic activity」。可以向 GitHub 檢舉。

### 3.5 試算（spike 實測，2026-10-28）

指令：`python3 spikes/quality_signals.py`（約 23 秒）。沙盒驗證一律是「未驗證」，所以每個工具都被封頂在 69。「若驗證通過」是假設驗證分數為 1.0 時的品質。

| repo | 類別 | 建立 | 星 | 分類 | 文件 | 維護 | 衛生 | 回應 | 品質（未封頂） | 若驗證通過 | confidence | 知名度 | gap | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [derekwisong/datui](https://github.com/derekwisong/datui) | CLI | 2026-01-18 | 137 | 工具 | 0.80 | 1.00 | 0.96 | 0.91 | 90.4 | 94.1 | 0.55 | 38.4 | 55.7 | 寶藏候選 |
| [shdwfruit/convkit](https://github.com/shdwfruit/convkit) | CLI | 2026-08-29 | 19 | 工具 | 0.80 | 1.00 | 1.00 | — | 91.1 | 95.0 | 0.45 | 23.5 | 71.5 | 寶藏候選 |
| [ahmetomerv/photoc](https://github.com/ahmetomerv/photoc) | CLI | 2026-09-27 | 11 | 工具 | 1.00 | 1.00 | 0.85 | — | 96.7 | 98.1 | 0.45 | 24.8 | 73.3 | 寶藏候選 |
| [sawfwair/mere-run](https://github.com/sawfwair/mere-run) | 本地 AI | 2026-03-29 | 84 | 工具 | 1.00 | 1.00 | 1.00 | — | 100.0 | 100.0 | 0.45 | 34.2 | 65.8 | 寶藏候選 |
| [blairjordan/pasteface](https://github.com/blairjordan/pasteface) | 本地 AI | 2026-09-07 | 3 | 工具 | 0.75 | 0.35 | 0.85 | — | 63.9 | 79.7 | 0.45 | 9.3 | 70.4 | 寶藏候選 |
| [sharkdp/bat](https://github.com/sharkdp/bat)（對照） | CLI | 2018-04-21 | 60,914 | 工具 | 1.00 | 0.71 | 0.91 | 0.58 | 82.9 | 89.6 | 0.55 | 96.2 | −6.6 | 否 |
| [okunix/gollama](https://github.com/okunix/gollama)（反例） | 本地 AI | 2026-07-07 | 0 | 函式庫 | 0.64 | 0.35 | 0.45 | — | 50.3 | 50（封頂） | 0.45 | 1.0 | 49.0 | 否 |
| [agarrharr/awesome-cli-apps](https://github.com/agarrharr/awesome-cli-apps)（反例） | CLI | 2015-07-09 | 20,555 | 不是軟體 | 0.35 | 0.35 | 0.07 | 0.42 | 31.1 | 30（archived） | 0.55 | 77.7 | −47.7 | 否 |

知名度的原始值：

| repo | stars | forks | 每月下載 | dependents | release 下載 | HN 最高分 | 收錄套件庫數 | 每月星數 |
|---|---|---|---|---|---|---|---|---|
| datui | 137 | 5 | 897（cargo＋PyPI） | 0 | 3,558 | 4 | 0 | 14.8 |
| convkit | 19 | 2 | 38 | 0 | 51 | 9 | 0 | 9.8 |
| photoc | 11 | 0 | — | — | 41 | 66 | 0 | 11.0 |
| mere-run | 84 | 7 | — | — | 962 | 16 | 0 | 12.1 |
| pasteface | 3 | 0 | — | — | — | 2 | 0 | 1.8 |
| bat | 60,914 | 4,263 | 65,666 | 1,352 | 1,114,883 | 191 | 8 | 595.2 |
| awesome-cli-apps | 20,555 | 1,550 | — | — | — | 45 | 0 | 151.4 |

Scorecard API 只有 datui（7.2，自己發布的）、bat（5.5）、awesome-cli-apps（2.5）查得到。Contributor Absence Factor：datui 1、convkit 1、bat 5、awesome-cli-apps 19。

**解讀**

- **品質用規則分不開**：小工具「若驗證通過」是 80–100，bat 是 90。這 5 個小工具都有 CI、測試、授權、release notes，衛生分數 0.85–1.0。能拉開差距的只剩沙盒驗證和模型 rubric。
- **知名度分得很開**：小工具 9–38，bat 96，awesome 清單 78。門檻 45 目前合理。datui（137 星、9 個月）是 38，已經接近門檻。
- photoc 只有 11 星，但 Show HN 拿到 66 分，HN 這一項把知名度拉到 24.8。HN 是一次性的曝光，權重 0.1 算合理。
- bat 的維護分是 0.71，因為最後一次 release 是 2025-12（10 個月前）。成熟工具發版慢不代表差，所以 release 的時間窗放寬到 180／365／730 天。
- pasteface 沒有 release，維護分 0.35，「若驗證通過」只有 79.7，仍高於 70。
- 函式庫（gollama）和清單（awesome-cli-apps，已 archived）都被正確封頂，不會被當成寶藏。
- 這 5 個寶藏候選都是從 Show HN 挑出來的，已經偏向完成度高的作品。要測出鑑別度，得加入隨機抽樣的新 repo。

---

## 4. 給 10/29–11/1 的實作建議

1. **發現 agent（10/29）**：規則分類當第一層，可以省下 Muse Spark 的呼叫。只把「工具」和「交給模型」送給 Muse Spark；函式庫和不是軟體的直接丟掉，但記錄原因。
2. **資料**：GitHub API（自己的 PAT）＋ ecosyste.ms 的 issues 與 packages（帶 mailto）＋ raw README。Scorecard API 只當加分資料，不要依賴它。
3. **驗證 agent（10/31）**：沙盒 clone 之後順便跑 `scorecard --local=.`（不需要 token，不到 1 秒）。安裝步驟數和失敗原因直接寫進 `verification`。
4. **`scores` 欄位**：存各分項、confidence、notes，以及每個數字的來源與取得時間（brief 第 8 節）。
5. **評測（brief 第 10 節）**：拿「交給模型」的 34 筆和目測判錯的幾筆，當成分類器的小評測集。
6. **demo**：用 3.5 的表格示範「品質與知名度分開算」：bat 品質高但知名度 96，所以不是寶藏；convkit 驗證通過後就是寶藏。

## 5. 未驗證或待確認

| 項目 | 狀態 |
|---|---|
| 規則分類的精確率 | 只有目測，沒有標註集 |
| 知名度的 ref 值與寶藏門檻 | 初始猜測，要用分布校準 |
| 用 GitHub API 計算 issue first response | 本環境 API 被擋，沒有實測 |
| ecosyste.ms 的 CC-BY-SA 對我們資料庫的影響 | 沒有請教法律意見 |
| deps.dev 的資料授權 | 沒查 |
| 每週掃描的 Scorecard 結果為什麼沒有 Vulnerabilities | 觀察結果，文件沒寫 |
| timeline.ecosyste.ms 為什麼資料不完整 | 沒查 |
| Scorecard CLI 用 `--repo` 對長尾 repo 跑一次要多久、耗多少 API 次數 | 本環境 GraphQL 被擋，沒有實測 |

## spike

| 腳本 | 驗證什麼 | 怎麼跑 | 結果 |
|---|---|---|---|
| `spikes/quality_signals.py` | 能不能從公開 API 拉到分類與計分要的訊號，並算出草案分數 | `python3 spikes/quality_signals.py`（8 個 repo，約 23 秒）；`--from-file repos.txt --classify-only`（227 個，約 60 秒）；可選環境變數 `GH_TOKEN`、`PICKFIT_CONTACT` | 見 1.3、3.5。GitHub API 在本環境回 403，自動改用 ecosyste.ms |

## 來源（查證日 2026-10-28）

- OpenSSF Scorecard：[README](https://github.com/ossf/scorecard)、[docs/checks.md](https://github.com/ossf/scorecard/blob/main/docs/checks.md)、[scorecard-infra CONTRIBUTING](https://github.com/ossf/scorecard-infra/blob/main/CONTRIBUTING.md)、[projects.csv](https://raw.githubusercontent.com/ossf/scorecard-infra/main/cron/internal/data/projects.csv)、REST API `https://api.scorecard.dev/projects/github.com/{owner}/{repo}`、原始碼 v5.6.0 的 `checks/evaluation/maintained.go` 與 `pkg/scorecard/scorecard_result.go`
- CHAOSS：[Issue Response Time](https://chaoss.community/kb/metric-issue-response-time/)、[Time to First Response](https://chaoss.community/kb/metric-time-to-first-response/)、[Change Request Closure Ratio](https://chaoss.community/kb/metric-change-request-closure-ratio/)、[Change Requests Duration](https://chaoss.community/kb/metric-change-requests-duration/)、[Release Frequency](https://chaoss.community/kb/metric-release-frequency/)、[Contributor Absence Factor](https://chaoss.community/kb/metric-contributor-absence-factor/)、[Issue Age](https://chaoss.community/kb/metric-issue-age/)、[Libyears](https://chaoss.community/kb/metric-libyears/)、[Documentation Usability](https://chaoss.community/kb/metric-documentation-usability/)、[Elephant Factor](https://chaoss.community/kb/metric-elephant-factor/)
- ecosyste.ms：[API 說明](https://ecosyste.ms/api)、[repos OpenAPI](https://repos.ecosyste.ms/docs/api/v1/openapi.yaml)、[timeline OpenAPI](https://timeline.ecosyste.ms/docs/api/v1/openapi.yaml)
- deps.dev：[API v3](https://docs.deps.dev/api/v3/)
- 套件慣例：[npm package.json bin](https://docs.npmjs.com/cli/configuring-npm/package-json#bin)、[pyproject.toml 規格](https://packaging.python.org/en/latest/specifications/pyproject-toml/)、[Cargo targets](https://doc.rust-lang.org/cargo/reference/cargo-targets.html)、[Go module layout](https://go.dev/doc/modules/layout)、[Homebrew formulae API](https://formulae.brew.sh/docs/api/)（`/api/formula/{name}.json` 含 30／90／365 天安裝數）
- GitHub：[REST 速率限制](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)、[Starring API](https://docs.github.com/en/rest/activity/starring)、[Community profile metrics](https://docs.github.com/en/rest/metrics/community)（`health_percentage`）、[Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)
- 假星研究：[arXiv 2412.13459](https://arxiv.org/abs/2412.13459)
- 樣本：[HN Algolia API](https://hn.algolia.com/api)
