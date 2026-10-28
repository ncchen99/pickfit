# spikes

調研用的小實驗腳本，用來確認 API、資料集或工具真的能用。**不是產品程式碼。**

- 每個腳本都要短、可重跑；需要金鑰的從環境變數讀，不寫進 repo。
- Python 腳本大多只用標準函式庫；開頭有 `# /// script` 的用 `uv run <檔名>` 執行。
- 詳細結果與數字在各腳本對應的 [docs/research/notes/](../docs/research/notes/) 筆記的「實測」小節。實測日 2026-10-28（台北）。
- 這個雲端 session 的 GitHub API 只開放本 repo，所以打 GitHub search 或別人 repo 的腳本要在本機用自己的 `GITHUB_TOKEN` 跑。
- 金鑰放 `.env`（已在 `.gitignore`），跑 spike 前先 `set -a; source .env; set +a`；腳本不會自己讀 `.env`。
- **ecosyste.ms 警告**：它的 [Terms](https://ecosyste.ms/terms) §9 禁止未經事先書面同意、用腳本擷取資料。調研時在讀到這條之前已經跑過下列腳本；**取得書面同意前不要再執行，或先拿掉那段**（`--enrich 0`）：`quality_signals.py`（不論有沒有 token，每次都會打 repos、issues、commits、packages）、`ch_packages_brew_taps.py`、`ch_packages_registries.py`、`ch_curation_lists.py --enrich`、`ch_curation_verify.py ollama`、`ch_integration_normalize.py`（沒有 `GITHUB_TOKEN` 時）、`ch_integration_merge.py`（預設 `--enrich 1000`）。移植進產品時一律改用 GitHub REST API 與各套件庫的官方 API。

## 管道（A 節）

| 腳本 | 驗證什麼 | 怎麼跑 | 需要 | 結果（摘要） | 筆記 |
|---|---|---|---|---|---|
| `ch_hosting_github.py` | GitHub search 兩個類別最近 7／14 天的量、抽樣；`created:` 分片 | `python3 spikes/ch_hosting_github.py counts`／`sample`／`slice` | `GITHUB_TOKEN`（本機） | 本 session 被擋，**未實測** | [channels-hosting](../docs/research/notes/channels-hosting.md) |
| `ch_hosting_hf_forges.py` | HF Spaces、Codeberg、GitLab 的新作品量 | `python3 spikes/ch_hosting_hf_forges.py` | 無 | HF 本地 AI 關鍵字 7 天 20 筆；README 連回作者自己 repo 的 3 筆中至少 1 筆可安裝（ollama-hud，未實裝）；Codeberg `topic:cli` 15–16 筆；GitLab 11 筆（2026-10-19 起未登入每 IP 60 次／時，可設 `GITLAB_TOKEN`） | 同上 |
| `ch_packages_brew_taps.py` | Homebrew analytics 裡最近 30 天才出現的第三方 tap formula | `python3 spikes/ch_packages_brew_taps.py` | 無；**會呼叫 ecosyste.ms**（見上方警告） | 4,066 個新出現、437 個安裝 10–1000 次；抽 40 個，36 個今年建、星數中位數 1 | [channels-packages](../docs/research/notes/channels-packages.md) |
| `ch_packages_registries.py` | PyPI、npm、crates、Go 等的新作品量與「是不是 CLI」訊號 | `python3 spikes/ch_packages_registries.py` | 無；**會呼叫 ecosyste.ms** | PyPI 約 40 個／小時，抽 30 個有 12 個有 `console_scripts` | 同上 |
| `ch_comm_hn_showhn.py` | Show HN 近 N 天的量、連 GitHub 比例、類別 | `python3 spikes/ch_comm_hn_showhn.py` | 無 | 7 天約 990 筆、35% 連 GitHub、兩類別且連 GitHub 約 75 筆 | [channels-communities](../docs/research/notes/channels-communities.md) |
| `ch_comm_feeds.py` | dev.to、Mastodon、Bluesky 的作者自發貼文 | `uv run spikes/ch_comm_feeds.py` | 無 | dev.to `#showdev` 7 天約 887 篇；Mastodon 66 則含 repo | 同上 |
| `ch_meta_probe.py` | Threads／FB／IG 官方端點不帶 token 的回應 | `python3 spikes/ch_meta_probe.py` | 無 | oEmbed 免 token 回 200，但沒有貼文文字 | [channels-meta-platforms](../docs/research/notes/channels-meta-platforms.md) |
| `ch_meta_threads_hn.py` | 作者多常用 Threads 貼文當主連結 | `python3 spikes/ch_meta_threads_hn.py` | 無 | HN 一年內連到 Threads 33 則、X 至少 1,110 則 | 同上 |
| `ch_regional_authors.py` | V2EX、Qiita、GeekNews 等作品專區的量 | `python3 spikes/ch_regional_authors.py` | 無 | V2EX 約 270 篇／週、Qiita 約 200 篇／週 | [channels-regional](../docs/research/notes/channels-regional.md) |
| `ch_regional_curated.py` | 阮一峰周刊、HelloGitHub 等策展的 repo 量 | `python3 spikes/ch_regional_curated.py` | 無 | 阮一峰近 3 期 45 個工具、40 個 GitHub | 同上 |
| `ch_curation_gharchive.py` | GH Archive 還能不能找新 repo | `python3 spikes/ch_curation_gharchive.py` | 無（會下載一小時的 dump） | 新 repo 事件 2025-10-09 起歸零；加星事件約剩 2024 年的 2% → 避開 | [channels-curation](../docs/research/notes/channels-curation.md) |
| `ch_curation_lists.py` | awesome 清單的新增項目、週報 RSS 的 GitHub 連結 | `python3 spikes/ch_curation_lists.py awesome --days 90`；`… feeds --days 7` | 需要 git；`--enrich` 會呼叫 ecosyste.ms，不要加 | awesome-tuis 近 90 天 +51（星數中位數 42）；awesome-cli-apps 已封存 | 同上 |
| `ch_integration_normalize.py` | URL 正規化、GitHub 改名偵測、套件 → repo 映射 | `python3 spikes/ch_integration_normalize.py`（`selftest` 子命令） | 可選 `GITHUB_TOKEN` | 正規化 25／25；PyPI 新專案 27／39 有 provenance、0 衝突；沒有 `GITHUB_TOKEN` 時會改用 ecosyste.ms 查舊名 | [channels-integration](../docs/research/notes/channels-integration.md) |
| `ch_curation_verify.py` | 查核用：awesome-ollama 名稱＋URL diff、ClickHouse 逐日 CreateEvent、Golang Weekly 轉址 | `python3 spikes/ch_curation_verify.py [ollama\|clickhouse\|golang]` | 需要 git；`ollama` 子命令會呼叫 ecosyste.ms | awesome-ollama 新增 43 筆（不是 54）、星數中位數 12 | [channels-curation](../docs/research/notes/channels-curation.md) |
| `ch_integration_merge.py` | 多管道 → 統一候選格式 → 去重 → 規則初篩 | `python3 spikes/ch_integration_merge.py --enrich 0` | 無 | 冪等：重跑時 Show HN 新增 0、PyPI 只多 1 筆。Show HN 7 天 271 個 repo 有 39 個（14%）改過名，這個數字靠 ecosyste.ms 的 `previous_names`，`--enrich 0` 時算不出來 | 同上 |

## 品質（B 節）

| 腳本 | 驗證什麼 | 怎麼跑 | 需要 | 結果 | 筆記 |
|---|---|---|---|---|---|
| `quality_signals.py` | 對 repo 拉 GitHub、Scorecard、ecosyste.ms 訊號，算品質與知名度草案分數 | `python3 spikes/quality_signals.py`（預設 8 個 repo）；`--from-file repos.txt --classify-only` | `GITHUB_TOKEN`；**每次都會呼叫 ecosyste.ms**（repos、issues、commits、packages），取得同意前只當調研紀錄、不要重跑。227 筆的樣本 `repos.txt` 不在 repo 裡，要先用 HN Algolia（`tags=show_hn`，關鍵字 cli、terminal、local llm、ollama、offline、command line、llama.cpp，各取最新 80 筆、只留 GitHub repo）產生 | 227 個 Show HN repo：工具 142、交給模型 34、函式庫 1、沒資料 50；Scorecard 只有 7 個（3.1%）有資料；規則品質會飽和（小工具 80–100、bat 90） | [quality-scoring](../docs/research/notes/quality-scoring.md) |

## 沙盒（C 節）

| 腳本 | 驗證什麼 | 怎麼跑 | 需要 | 結果 | 筆記 |
|---|---|---|---|---|---|
| `sandbox_docker_install.py` | 在全新、受限的 Docker 容器裡照 README 安裝真實工具並跑 smoke test；`--limits-test` 測防護 | 先起 `dockerd`，再 `python3 spikes/sandbox_docker_install.py --with-llm`（不加 `--with-llm` 只跑 3 款 CLI）；防護檢查用 `--limits-test` | Docker | 4 款都通過（每款 2–29 秒），2 款要先修正；llama.cpp＋1.2 MB 模型做到推論驗證；OOM／磁碟／fork bomb 防護有效 | [sandbox-verify-design](../docs/research/notes/sandbox-verify-design.md) |
| `sb_local_timing.sh` | 本機 runc 與 gVisor 的啟動時間 | `bash spikes/sb_local_timing.sh` | Docker（可選 runsc） | docker run 0.3–0.5 秒；runsc 0.08–0.16 秒 | [sandbox-compare](../docs/research/notes/sandbox-compare.md) |
| `sb_modal_verify.py` | Modal Sandbox（`runtime="gvisor"`）：開網路安裝，斷網跑 smoke test，量各階段秒數 | `pip install modal && modal token new`，再 `python3 spikes/sb_modal_verify.py --install "pip install httpie" --smoke "http --version"` | `modal` 套件；`MODAL_TOKEN_ID`、`MODAL_TOKEN_SECRET` | **未實測**（沒有 token） | 同上 |
| `sb_gha_macos_brew.yml` | GitHub Actions macOS runner 上 brew 安裝與 smoke test | 只能放在 pickfit 自己 repo 的 `.github/workflows/`，手動觸發；**不要另開 repo**；只跑 demo 那 2–5 筆；`permissions: {}`、不放 secrets。repo 轉 public 前，macOS 每分鐘 $0.062。條款是灰色地帶，有 Apple silicon Mac 就不用（architecture.md K） | GitHub | **未實測**；條款限制見筆記 | 同上 |

## Meta 模型（D 節）

| 腳本 | 驗證什麼 | 怎麼跑 | 需要 | 結果 | 筆記 |
|---|---|---|---|---|---|
| `meta_api_hello.py` | Meta Model API：文字、JSON schema、tool calling、圖片輸入 | `MODEL_API_KEY=… python3 spikes/meta_api_hello.py` | `MODEL_API_KEY` | **未實測**；無效 key 回 401（端點與認證方式正確） | [meta-model-api](../docs/research/notes/meta-model-api.md) |
| `meta_responses_agent_probe.py` | Responses API 多輪工具迴圈、截圖放哪、schema＋tools、`web_search` | `MODEL_API_KEY=… python3 spikes/meta_responses_agent_probe.py` | `MODEL_API_KEY` | **未實測** | [meta-usage-design](../docs/research/notes/meta-usage-design.md) |
| `meta_baseten_hello.py` | Baseten 上的 Muse Spark Open（含比賽 model ID） | `BASETEN_API_KEY=… python3 spikes/meta_baseten_hello.py` | `BASETEN_API_KEY` | **未實測**；無效 key 回 403 | [meta-open-weights](../docs/research/notes/meta-open-weights.md) |

拿到 key 後的順序：`meta_api_hello.py` → `meta_responses_agent_probe.py` → `meta_baseten_hello.py`。

## MCP 與儲存（E、F 節）

| 腳本 | 驗證什麼 | 怎麼跑 | 需要 | 結果 | 筆記 |
|---|---|---|---|---|---|
| `mcp_stateless/` | 最小無狀態 Streamable HTTP MCP server（TS SDK v2）、Workers 設定、client 測試 | 見 [mcp_stateless/README.md](mcp_stateless/README.md) | Node 22 | Node 與 `wrangler dev` 都通過新舊兩代共 9 項檢查；TS client 3 種模式、Python client 2 種模式可呼叫；**未部署、未用 Claude Code／Codex 實連** | [mcp-server](../docs/research/notes/mcp-server.md) |
| `sm_index_bench.mjs` | 幾千筆時「條件篩選＋BM25」夠不夠；索引大小與查詢時間 | `node spikes/sm_index_bench.mjs` | Node | 8,198 筆 Homebrew 描述：原話 5／10 進前 25，改寫關鍵字後 10／10；查詢 <1 ms | [storage-matching](../docs/research/notes/storage-matching.md) |
| `sm_worker_startup.sh` | 索引打包進 Worker 的 bundle 大小與啟動 CPU | `bash spikes/sm_worker_startup.sh 3000` | Node、wrangler（本機，不部署） | 3,000 筆約 1 MB，啟動遠低於 1 秒上限 | 同上 |
| `sm_schema_events.py` | 檔案 JSON Schema 與 D1 事件表 DDL（在本機 SQLite 跑） | `uv run --with jsonschema python spikes/sm_schema_events.py` | `jsonschema` | DDL 在 SQLite 3.45 跑過；D1 未實測 | 同上 |
