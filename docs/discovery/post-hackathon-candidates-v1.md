# 賽後擴大收錄候選清單與類別擴增建議（`post-hackathon-candidates.v1`）

2026-11-15（台北）整理 · 賽後階段第一批研究清單。

## 1. 策略與範圍

- **API 與沙盒**：Meta 黑客松已結束，解除賽期凍結時程與硬性 credit 上限；模型 API 規劃切換至 **Anthropic API**，驗證沙盒持續使用 **Modal**（`ModalBox`）。
- **優先驗證領域**：優先收錄 **Linux / CLI / TUI**、**MCP Server**、**網頁應用與輕量自架 Web 工具**。CLI 與 MCP 在 Linux 沙盒驗證的結果與 macOS / Windows 高度一致，可在無需維護大量 Mac / Windows 實機的前提下維持高驗證覆蓋率。
- **去重檢查**：以下清單已逐一比對目前 `data/software/` 現有 **1,058 筆** 紀錄，排除已收錄項目（如 `k9s`, `lazygit`, `dive`, `harlequin`, `visidata`, `miller`, `glow`, `yq`, `jq`, `xh`, `hurl`, `delta`, `difftastic`, `just`, `hyperfine`, `eza`, `bat`, `fd`, `ripgrep`, `zoxide`, `fzf`, `btop`, `bottom`, `bandwhich`, `dog`, `atuin`, `zellij`, `yazi`, `mise`, `direnv`, `jj`, `nushell`, `starship`, `playwright-mcp`, `chrome-devtools-mcp`, `github-mcp-server`, `gitlab-mcp-server`, `serena`, `it-tools`, `memos`, `stirling-pdf`, `localsend` 等）。

---

## 2. 軟體類別（`category`）擴增建議

目前 `schema/software.v1.json` 僅有 4 個類別：`dev_cli`（318）、`local_ai`（292）、`mcp_server`（202）、`other`（246）。
`other` 已累積 **246 筆**（含 93 筆網頁應用與 149 筆桌面應用），過於龐雜。建議在保留既有 `dev_cli`、`local_ai`、`mcp_server`、`other` 的基礎上，先擴增 **4–5 個語意清楚的新類別**（不需一次塞滿，可先建好 schema 與 UI 標籤，再逐步把 `other` 與新收錄工具歸類）：

| 建議新類別 ID | 英文 / 中文名稱 | 涵蓋範圍與代表工具 |
| :--- | :--- | :--- |
| `infra_devops` | **Infra & DevOps / 維運與容器** | 容器、Kubernetes、CI/CD、IaC、系統監控與備份 CLI／自架面板（如 `lazydocker`, `stern`, `trivy`, `act`, `opentofu`, `uptime-kuma`, `dozzle`, `beszel`） |
| `security_net` | **Security & Networking / 資安與網路** | 網路診斷、封包分析、TLS/PKI、加密與金鑰掃描工具（如 `trippy`, `termshark`, `doggo`, `age`, `sops`, `gitleaks`, `trufflehog`, `mitmproxy`, `step-cli`） |
| `data_db` | **Data & Databases / 資料與資料庫** | 本機 SQL 引擎、資料庫 TUI/CLI、JSON/CSV/日誌處理工具（如 `duckdb`, `usql`, `rainfrog`, `fx`, `gron`, `jless`, `dasel`, `qsv`, `lnav`） |
| `productivity_docs` | **Productivity & Docs / 生產力與文件** | 筆記、知識庫、白板圖表、文件轉換與簡報工具（如 `excalidraw`, `diagrams.net`, `mermaid-live`, `hedgedoc`, `pandoc`, `presenterm`, `AppFlowy`, `logseq`, `anki`） |
| `media_files` | **Media & Files / 影音與檔案工具** | 影音下載轉檔、圖片壓縮、PDF 處理、傳檔工具（如 `yt-dlp`, `vhs`, `bentopdf`, `omni-tools`, `pairdrop`, `vert.sh`, `squoosh`, `HandBrake`, `lossless-cut`） |

*(註：若想維持更精簡，也可將 `web_app` 相關的純開發輔助工具如 `CyberChef`, `Hoppscotch`, `Regex101` 歸入 `dev_cli` 改名或另設 `dev_tools` / `web_utility`，或配合現有的 `kind: web_app` 篩選使用。)*

---

## 3. Linux & 跨平台 CLI / TUI 候選清單（42+ 款）

### A. 容器、Kubernetes 與 DevOps
| 名稱 | GitHub Repo | 授權 | Linux 安裝方式 | 定位與社群推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **lazydocker** | `jesseduffield/lazydocker` | MIT | Binary / `go install` / `brew` | 最受歡迎的 Docker / Compose 互動式 TUI 面板 |
| **oxker** | `mrjackwills/oxker` | MIT | Binary / `cargo install` | Rust 編寫的輕量高速 Docker 容器監控 TUI |
| **stern** | `stern/stern` | Apache-2.0 | Binary / `brew` / `go install` | Kubernetes 多 Pod / 多容器彩色即時日誌追蹤 |
| **kubectx** | `ahmetb/kubectx` | Apache-2.0 | `apt` / Binary / `brew` | 搭配 `fzf` 極速切換 K8s 叢集與 Namespace（含 `kubens`） |
| **helmfile** | `helmfile/helmfile` | MIT | Binary / `brew` / `pacman` | 宣告式管理多環境 Helm Chart 部署與 Diff |
| **crane** | `google/go-containerregistry` | Apache-2.0 | Binary / `go install` | 免 Docker Daemon 直接檢視、複製與推送 OCI 映像檔 |
| **trivy** | `aquasecurity/trivy` | Apache-2.0 | `apt` / Binary / `brew` | 容器、檔案系統與 IaC 全方位漏洞與機密掃描器 |
| **syft** | `anchore/syft` | Apache-2.0 | Install script / Binary | 從容器映像或專案產生 CycloneDX / SPDX SBOM 清單 |
| **act** | `nektos/act` | MIT | Binary / Install script | 在本機用 Docker 直接執行 GitHub Actions 工作流 |
| **tilt** | `tilt-dev/tilt` | Apache-2.0 | Install script / Binary | 本機 K8s 微服務熱重載開發與統一狀態儀表板 |
| **opentofu** | `opentofu/opentofu` | MPL-2.0 | `.deb`/`.rpm` / Binary | 完全開源、社群維護的 Terraform 相容 IaC 工具 |

### B. 網路診斷、資安與加密
| 名稱 | GitHub Repo | 授權 | Linux 安裝方式 | 定位與社群推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **trippy** | `fujiapple852/trippy` | Apache-2.0 | Binary / `cargo install` | Rust 網路診斷 TUI（結合 traceroute + ping + GeoIP） |
| **termshark** | `gcla/termshark` | MIT | `apt` / Binary / `go install` | 終端機版 Wireshark TUI，適合 SSH 遠端檢視 `.pcap` 封包 |
| **doggo** | `mr-karan/doggo` | GPL-3.0 | Binary / `go install` | 支援 DoH/DoT/DoQ 與 JSON 的現代 DNS 查詢工具（`dog` 活躍繼任者） |
| **gping** | `orf/gping` | MIT | `cargo install` / Binary | 在終端機繪製多主機即時 Ping 延遲折線圖 |
| **oha** | `hatoo/oha` | MIT | `cargo install` / Binary | 附帶即時延遲直方圖 TUI 的高效能 HTTP 壓測工具 |
| **step-cli** | `smallstep/cli` | Apache-2.0 | `.deb`/`.rpm` / Binary | 憑證、JWT、OAuth、SSH 憑證與本機 PKI 瑞士刀 |
| **mkcert** | `FiloSottile/mkcert` | BSD-3-Clause | Binary / `brew` | 零設定產生本機開發受信任的 HTTPS 憑證 |
| **age** | `FiloSottile/age` | BSD-3-Clause | `apt` / Binary / `brew` | 現代簡潔、可稽核的檔案加密工具（取代 GPG 日常加密） |
| **sops** | `getsops/sops` | MPL-2.0 | `.deb`/`.rpm` / Binary | 原地加密 YAML/JSON/ENV 機密欄位以便安全存入 Git |
| **gitleaks** | `gitleaks/gitleaks` | MIT | Binary / `brew` | 快速掃描 Git 歷史與 pre-commit 中的外洩 API Key |
| **trufflehog** | `trufflesecurity/trufflehog` | AGPL-3.0 | Install script / Binary | 掃描程式庫與儲存桶外洩憑證並驗證金鑰是否仍有效 |
| **mitmproxy** | `mitmproxy/mitmproxy` | MIT | `uv tool install` / Binary | 可編寫腳本的互動式 HTTP/HTTPS TLS 代理與封包重放 TUI |

### C. 資料、資料庫、API、日誌與文件
| 名稱 | GitHub Repo | 授權 | Linux 安裝方式 | 定位與社群推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **duckdb** | `duckdb/duckdb` | MIT | Install script / Binary | 零設定本機分析型 SQL CLI，直接查詢 CSV/Parquet/JSON/S3 |
| **usql** | `xo/usql` | MIT | Binary / `go install` | 通用 SQL CLI，統一介面連接 Postgres/MySQL/SQLite/DuckDB |
| **rainfrog** | `achristmascarl/rainfrog` | MIT | Binary / `cargo install` | Rust 編寫、支援 Vim 快捷鍵的 Postgres/MySQL/SQLite TUI |
| **fx** | `antonmedv/fx` | MIT | Install script / Binary | 互動式終端 JSON 檢視器，支援摺疊與 JS/表達式過濾 |
| **gron** | `tomnomnom/gron` | MIT | Binary / `go install` | 將複雜 JSON 攤平為可 `grep` 的賦值行並可還原 |
| **jless** | `PaulJuliusMartinez/jless` | MIT | Binary / `cargo install` | 類 Vim 操作的高速大型 JSON 分頁瀏覽器 |
| **dasel** | `TomWright/dasel` | MIT | Binary / `go install` | 用統一語法查詢、修改與互轉 JSON/YAML/TOML/XML/CSV |
| **qsv** | `dathere/qsv` | MIT / Unlicense | Binary / `brew` | Rust 極速大型 CSV/TSV 切片、索引、合併與剖析工具組 |
| **posting** | `darrenburns/posting` | Apache-2.0 | `uv tool install` / `pipx` | 現代 Textual 終端 HTTP/API 客戶端（終端機版 Postman） |
| **lnav** | `tstack/lnav` | BSD-2-Clause | Static binary / `apt` | 自動合併索引日誌並支援用 SQL 查詢 log 的終端瀏覽器 |
| **tailspin** | `bensadeh/tailspin` | MIT | Binary / `cargo install` | 零設定日誌自動高亮檢視器（`tspin`），凸顯日期/IP/UUID |
| **presenterm** | `mfontanini/presenterm` | BSD-2-Clause | Binary / `cargo install` | 用 Markdown 直接在終端機播放含程式碼執行與圖片的簡報 |
| **pandoc** | `jgm/pandoc` | GPL-2.0+ | `.deb` / `apt` / Binary | 通用文件格式轉檔標準（Markdown/HTML/PDF/DOCX/LaTeX） |
| **tealdeer** | `tealdeer-rs/tealdeer` | MIT / Apache-2.0 | Binary / `cargo install` | 極速離線 Rust 版 `tldr` 指令範例速查工具 |

### D. 影音、檔案、系統與開發任務
| 名稱 | GitHub Repo | 授權 | Linux 安裝方式 | 定位與社群推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **yt-dlp** | `yt-dlp/yt-dlp` | Unlicense | Standalone binary / `pipx` | 最強大的跨平台影音與字幕下載 CLI |
| **vhs** | `charmbracelet/vhs` | MIT | Charm `apt` / Binary | 用 `.tape` 腳本自動錄製可重現的終端機 GIF/MP4 演示 |
| **rclone** | `rclone/rclone` | MIT | Install script / `apt` | 「雲端儲存的 rsync」，支援 S3/GCS/Drive 同步與加密掛載 |
| **restic** | `restic/restic` | BSD-2-Clause | `apt` / Binary | 快速、去重、端對端加密的跨平台備份 CLI |
| **chezmoi** | `twpayne/chezmoi` | MIT | Install script / Binary | 支援範本與密碼管理器整合的跨平台 Dotfiles 管理工具 |
| **dust** / **duf** | `bootandy/dust` / `muesli/duf` | Apache-2.0 / MIT | Binary / `cargo` / `apt` | 視覺化取代 `du`（`dust`）與 `df`（`duf`）的磁碟空間工具 |
| **procs** | `dalance/procs` | MIT | Binary / `cargo install` | Rust 彩色樹狀進程檢視器（取代 `ps`） |
| **watchexec** | `watchexec/watchexec` | Apache-2.0 | Binary / `cargo install` | 尊重 `.gitignore` 的跨平台檔案變動自動重跑工具 |
| **go-task (`task`)** | `go-task/task` | MIT | Install script / Binary | YAML 撰寫、支援跨平台 Shell 與快取的現代 `Make` 替代品 |
| **pueue** | `Nukesor/pueue` | MIT | Binary / `cargo install` | 背景長任務佇列管理守護進程與 CLI（支援暫停/重試） |
| **gh-dash** | `dlvhdr/gh-dash` | MIT | `gh extension install` | GitHub PR 與 Issue 的終端機互動式管理儀表板 |
| **git-cliff** | `orhun/git-cliff` | MIT / Apache-2.0 | Binary / `cargo install` | 依據 Conventional Commits 高速產生客製化 Changelog |
| **tokei** / **scc** | `XAMPPRocky/tokei` / `boyter/scc` | MIT/Apache-2.0 / MIT | Binary / `cargo` / `go` | 極速多語言程式碼行數統計與複雜度估算工具 |

---

## 4. MCP Server 候選清單（34 款）

### A. 程式庫、文件、知識庫與搜尋（11 款）
| 名稱 | Repo / Package | 啟動方式 | 離線 / 金鑰需求 | 定位與社群推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **Context7** | `upstash/context7` (`@upstash/context7-mcp`) | `npx -y @upstash/context7-mcp` | 需連網抓文件；免 API Key（可選 Key 提限） | 即時注入各函式庫最新版本的正確文件與範例，大幅減少幻覺 |
| **Repomix (MCP)** | `yamadashy/repomix` | `npx -y repomix --mcp` | **100% 離線**，免 Key | 將整個程式庫打包成對 LLM 友善的 XML/Markdown 並支援 tree-sitter 壓縮 |
| **DeepWiki MCP** | `regenrek/deepwiki-mcp` (`mcp-deepwiki`) | `npx -y mcp-deepwiki` | 需連網查 `deepwiki.com`；免 API Key | 直接存取公開 GitHub Repo 的架構摘要與文件 |
| **MCP Server Fetch** | `modelcontextprotocol/servers` (`mcp-server-fetch`) | `uvx mcp-server-fetch` | 抓外網需連網（`localhost` 可離線）；免 Key | 官方參考實作，將網頁 HTML 轉為乾淨省 Token 的 Markdown |
| **ast-grep MCP** | `ast-grep/ast-grep-mcp` | `npx -y ast-grep-mcp` | **100% 離線**，免 Key | 跨 20+ 語言的 AST 語法樹結構搜尋與比對，比 regex 精準 |
| **MarkItDown MCP** | `microsoft/markitdown` (`markitdown-mcp`) | `uvx markitdown-mcp` | **本機檔案 100% 離線**，免 Key | 微軟官方文件轉換器，將 PDF/Office/HTML 轉為 Markdown |
| **Tree-sitter MCP** | `wrale/mcp-server-tree-sitter` | `uvx mcp-server-tree-sitter` | **100% 離線**，免 Key | 解析 AST、抽取符號定義與呼叫圖，低 Token 瀏覽大型專案 |
| **Code Index MCP** | `johnhuang316/code-index-mcp` | `uvx code-index-mcp` | **100% 離線**，免 Key | 提供大型多檔案專案的快速索引、符號搜尋與結構分析 |
| **YouTube Transcript MCP** | `jkawamoto/mcp-youtube-transcript` | `uvx --from git+...` | 需連網抓字幕；免 API Key | 直接抓取 YouTube 影片含時間軸的逐字稿供總結或學習 |
| **Brave Search MCP** | `brave/brave-search-mcp-server` | `npx -y @modelcontextprotocol/server-brave-search` | 需連網 + `BRAVE_API_KEY`（交握免 Key） | 最普及的隱私導向即時網頁與本地搜尋 MCP |
| **Exa MCP Server** | `exa-labs/exa-mcp-server` | `npx -y exa-mcp-server` | 需連網 + `EXA_API_KEY`（交握免 Key） | `r/ClaudeAI` 熱門語義網頁搜尋與 Markdown 內容擷取 |

### B. 瀏覽器、爬蟲與自動化測試（3 款）
| 名稱 | Repo / Package | 啟動方式 | 離線 / 金鑰需求 | 定位與社群推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **Puppeteer MCP** | `@modelcontextprotocol/server-puppeteer` | `npx -y @modelcontextprotocol/server-puppeteer` | **對 `localhost` 可離線**，免 Key | 經典官方瀏覽器自動化參考實作，支援截圖與表單操作 |
| **Firecrawl MCP** | `firecrawl/firecrawl-mcp-server` (`firecrawl-mcp`) | `npx -y firecrawl-mcp` | 需 `FIRECRAWL_API_KEY` 或自架 Docker | JS 渲染網頁抓取、全站地圖與文件站轉 Markdown 標準工具 |
| **Browser-Use MCP** | `browser-use/browser-use` | `uvx browser-use[cli] --mcp` | 瀏覽器控制本機運作；自主子任務需 LLM Key | 連接爆紅的 `browser-use` 框架執行多步網頁操作 |

### C. 資料庫與資料（9 款）
| 名稱 | Repo / Package | 啟動方式 | 離線 / 金鑰需求 | 定位與社群推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **SQLite MCP** | `modelcontextprotocol/servers` (`mcp-server-sqlite`) | `npx`/`uvx` | **100% 離線**，免 Key | 零設定本機 SQLite 查詢與 Schema 檢視官方實作 |
| **Postgres MCP Pro** | `crystaldba/postgres-mcp` | `uvx postgres-mcp` | **本機 Postgres 可離線** | 除 SQL 查詢外，支援索引調優、`EXPLAIN` 分析與健康診斷 |
| **DuckDB MCP** | `boettiger-lab/mcp-server-duckdb` | `uvx mcp-server-duckdb` | **100% 離線**，免 Key | 直接對本機 CSV/Parquet/JSON 執行高速分析 SQL，免架 DB |
| **Qdrant MCP** | `qdrant/mcp-server-qdrant` | `uvx mcp-server-qdrant` | **100% 離線**（本機 `:memory:` + FastEmbed） | Qdrant 官方語義記憶與向量 RAG MCP |
| **Redis MCP** | `redis/mcp-redis` (`redis-mcp-server`) | `uvx redis-mcp-server` | **本機 Redis 可離線** | Redis 官方自然語言操作鍵值、Stream、Pub/Sub 與向量索引 |
| **MongoDB MCP** | `mongodb-js/mongodb-mcp-server` | `npx -y mongodb-mcp-server` | **本機 Mongo 可離線** | MongoDB 官方 Schema 檢視、Aggregation Pipeline 與 CRUD |
| **Neo4j Cypher MCP** | `neo4j-contrib/mcp-neo4j` (`mcp-neo4j-cypher`) | `uvx mcp-neo4j-cypher` | **本機 Neo4j 可離線** | Neo4j 官方自然語言轉 Cypher 與知識圖譜探索 |
| **ClickHouse MCP** | `ClickHouse/mcp-clickhouse` | `uvx mcp-clickhouse` | **本機 ClickHouse 可離線** | ClickHouse 官方唯讀 OLAP 查詢與 Schema 檢視 |
| **Supabase MCP** | `supabase/mcp` (`@supabase/mcp-server-supabase`) | `npx -y @supabase/mcp-server-supabase` | 雲端需 `SUPABASE_ACCESS_TOKEN`（或本機 CLI） | `r/ClaudeAI` 高票資料庫/後端管理、Migration 與日誌除錯 |

### D. DevOps、Git、容器與可觀測性（5 款）
| 名稱 | Repo / Package | 啟動方式 | 離線 / 金鑰需求 | 定位與社群推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **Git MCP** | `modelcontextprotocol/servers` (`mcp-server-git`) | `uvx mcp-server-git` | **100% 離線**，免 Key | 官方 Git 參考實作：讀取 status、diff、log、branch 與提交 |
| **Docker MCP** | `ckreiling/mcp-server-docker` | `uvx mcp-server-docker` | **100% 離線**（本機 Docker socket） | 檢視運行中容器、追蹤 log、管理 Compose 堆疊 |
| **Kubernetes MCP** | `containers/kubernetes-mcp-server` | `npx` / `uvx` | **本機 kind/k3s 可離線** | 原生 K8s 除錯 CrashLoopBackOff Pod、事件與資源管理 |
| **Terraform MCP** | `hashicorp/terraform-mcp-server` | Go Binary / Docker | 查 Registry 需連網（免 Key） | HashiCorp 官方查詢即時 Provider/Module 文件減少 IaC 幻覺 |
| **Grafana MCP** | `grafana/mcp-grafana` | Go Binary / `uvx` / Docker | **本機 Grafana 可離線** | Grafana 官方查詢 Prometheus 指標、Loki 日誌與告警排查 |

### E. 思考、記憶、規劃與系統工具（6 款）
| 名稱 | Repo / Package | 啟動方式 | 離線 / 金鑰需求 | 定位與社群推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **Sequential Thinking** | `modelcontextprotocol/servers` | `npx -y @modelcontextprotocol/server-sequential-thinking` | **100% 離線**，免 Key | 社群公認必裝 #1：結構化多步推理、假設修正與架構規劃草稿板 |
| **Filesystem MCP** | `modelcontextprotocol/servers` | `npx -y @modelcontextprotocol/server-filesystem` | **100% 離線**，免 Key | 官方基礎沙盒限制路徑的本機檔案讀寫與搜尋工具 |
| **Desktop Commander** | `wonderwhy-er/DesktopCommanderMCP` | `npx -y @wonderwhy-er/desktop-commander@latest` | **100% 離線**，免 Key | 賦予 Agent 完整本機終端機、進程管理與精準檔案 Diff 編輯 |
| **Memory MCP** | `modelcontextprotocol/servers` | `npx -y @modelcontextprotocol/server-memory` | **100% 離線**（本機 JSONL） | 官方跨工作階段知識圖譜記憶伺服器 |
| **Time MCP** | `modelcontextprotocol/servers` (`mcp-server-time`) | `uvx mcp-server-time` | **100% 離線**，免 Key | 輕量取得準確系統時間與 IANA 時區轉換 |
| **Claude Task Master** | `eyaltoledano/claude-task-master` (`task-master-ai`) | `npx -y task-master-ai` | 交握與任務狀態離線；PRD 解析需 LLM Key | GitHub 高星 Agent 任務規劃器，拆解 PRD 與追蹤相依子任務 |

---

## 5. 網頁應用與輕量自架 Web 工具候選清單（32 款）

### A. 開發者與資安純前端／網頁工具（10 款）
| 名稱 | 網址 / Repo | 類型 | 沙盒瀏覽器驗證可行性 | 定位與推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **CyberChef** | `https://gchq.github.io/CyberChef/` (`gchq/CyberChef`) | `web_app` | 免登入、100% 純前端 | 加解密、編碼、壓縮、Hex/二進位解析「網路瑞士刀」 |
| **Hoppscotch** | `https://hoppscotch.io` (`hoppscotch/hoppscotch`) | `web_app` | 核心 REST/WS 測試免登入 | 開源輕量網頁版 Postman 替代品 |
| **JSON Crack** | `https://jsoncrack.com` (`AykutSarac/jsoncrack.com`) | `web_app` | 免登入即用 | 將巢狀 JSON/YAML/CSV 視覺化為可搜尋節點圖 |
| **Regex101** | `https://regex101.com` | `web_app` | 免登入即用 | 跨多語言正規表達式測試與逐步解釋標竿 |
| **Crontab.guru** | `https://crontab.guru` | `web_app` | 免登入、純前端 | Cron 排程表達式即時白話翻譯與下次執行驗證 |
| **Transform.tools** | `https://transform.tools` (`ritz078/transform`) | `web_app` | 免登入即用 | 多語言資料結構／語法轉換（JSON→TS/Go/Rust、HTML→JSX 等） |
| **Compiler Explorer** | `https://godbolt.org` (`compiler-explorer/compiler-explorer`) | `web_app` | 免登入即用 | 多語言線上編譯器與組合語言對照除錯器 |
| **DuckDB-Wasm Shell** | `https://shell.duckdb.org` (`duckdb/duckdb-wasm`) | `web_app` | 免登入、純 WASM | 瀏覽器內直接對本機 Parquet/CSV/JSON 跑分析 SQL |
| **Webhook.site** | `https://webhook.site` (`webhooksite/webhook.site`) | `web_app` | 免登入即自動產生測試 URL | 即時 HTTP / Webhook 請求內容與標頭檢視器 |
| **JWT.io** | `https://jwt.io` | `web_app` | 免登入、純前端 | JSON Web Token 解碼與簽章驗證標準工具 |

### B. 圖表繪製、白板與協作文件（7 款）
| 名稱 | 網址 / Repo | 類型 | 沙盒瀏覽器驗證可行性 | 定位與推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **Excalidraw** | `https://excalidraw.com` (`excalidraw/excalidraw`) | `web_app` | 免登入即畫即匯出 | 工程師最愛的手繪風系統架構白板（目前僅收錄 `excalidraw-cli`） |
| **diagrams.net (Draw.io)** | `https://app.diagrams.net` (`jgraph/drawio`) | `web_app` | 選「Decide later」即可免登入 | 全功能開源架構圖／UML／雲端拓樸繪圖工具 |
| **Mermaid Live Editor** | `https://mermaid.live` (`mermaid-js/mermaid-live-editor`) | `web_app` | 免登入即用 | 官方 Mermaid 程式碼繪圖即時預覽與 SVG/PNG 匯出 |
| **tldraw** | `https://www.tldraw.com` (`tldraw/tldraw`) | `web_app` | 免登入即用 | 極度流暢的無限畫布向量白板 |
| **D2 Playground** | `https://play.d2lang.com` (`d2lang/d2-playground`) | `web_app` | 免登入即用 | 現代宣告式架構圖語言 D2 的官方互動測試區 |
| **Kroki** | `https://kroki.io` (`yuzutech/kroki`) | `self_hosted_web_app` | 單一 Docker 容器免登入 | 統一 API 渲染 PlantUML/Mermaid/D2/Graphviz 等多種圖表 |
| **HedgeDoc** | `https://hedgedoc.org` (`hedgedoc/hedgedoc`) | `self_hosted_web_app` | Docker Compose 可開訪客免登入 | 即時協作 Markdown 筆記與簡報平台 |

### C. 檔案、PDF 與媒體工具（7 款）
| 名稱 | 網址 / Repo | 類型 | 沙盒瀏覽器驗證可行性 | 定位與推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **BentoPDF** | `https://bentopdf.com` (`alam00000/bentopdf`) | `self_hosted_web_app` | 9MB 輕量 Docker / 網頁免登入 WASM | 隱私優先、免上傳伺服器的輕量 PDF 工具箱（Stirling-PDF 輕量替代） |
| **Omni-Tools** | `iib0011/omni-tools` | `self_hosted_web_app` | 單一 Docker 容器免登入 | 自架全能影音/圖片/PDF/文字網頁工具箱（與 IT-Tools 互補） |
| **PairDrop** | `https://pairdrop.net` (`schlagmichdoch/PairDrop`) | `self_hosted_web_app` | 單一 Docker / 網頁免登入 | 瀏覽器跨裝置局域網／WebRTC AirDrop 傳檔工具 |
| **VERT.sh** | `https://vert.sh` (`VERT-sh/VERT`) | `web_app` | 網頁與 Docker 皆免登入（WASM） | 無廣告開源通用檔案格式轉換器 |
| **Squoosh** | `https://squoosh.app` (`GoogleChromeLabs/squoosh`) | `web_app` | 免登入、純 WASM | 雙欄對比視覺化圖片壓縮與 WebP/AVIF 轉檔 |
| **SVGOMG** | `https://svgomg.net` (`jakearchibald/svgomg`) | `web_app` | 免登入、純前端 | SVGO 互動式 SVG 精簡與即時預覽介面 |
| **Cobalt** | `https://cobalt.tools` (`imputnet/cobalt`) | `self_hosted_web_app` | Docker / 網頁免登入 | 乾淨無廣告追蹤的公開網路影音下載工具 |

### D. 自架監控、儀表板與自動化（8 款）
| 名稱 | 網址 / Repo | 類型 | 沙盒瀏覽器驗證可行性 | 定位與推薦理由 |
| :--- | :--- | :--- | :--- | :--- |
| **Uptime Kuma** | `https://uptime.kuma.pet` (`louislam/uptime-kuma`) | `self_hosted_web_app` | 單一 Docker（首次需建管理員帳號） | 自架服務可用性監控與狀態頁標竿（支援 90+ 通知） |
| **Glance** | `glanceapp/glance` | `self_hosted_web_app` | 單一 Docker，預設**免登入** | 超輕量 YAML 驅動 Homelab 與 RSS/Docker 儀表板 |
| **Dozzle** | `https://dozzle.dev` (`amir20/dozzle`) | `self_hosted_web_app` | 單一 Docker，預設**免登入** | 即時串流與搜尋多主機 Docker 容器日誌網頁 UI |
| **Changedetection.io** | `https://changedetection.io` (`dgtlmoon/changedetection.io`) | `self_hosted_web_app` | 單一 Docker，預設**免登入** | 網頁內容與視覺 Diff 自動監測通知工具 |
| **Homepage** | `https://gethomepage.dev` (`gethomepage/homepage`) | `self_hosted_web_app` | 單一 Docker，**免登入** | 支援 100+ 服務 Widget 的高速靜態 Homelab 首頁 |
| **Homarr** | `https://homarr.dev` (`homarr-labs/homarr`) | `self_hosted_web_app` | 單一 Docker（首次需設定帳號） | 拖放式互動 Homelab 儀表板與容器控制面板 |
| **Beszel** | `https://beszel.dev` (`henrygd/beszel`) | `self_hosted_web_app` | 單一 Docker（首次需建帳號） | 輕量伺服器與 Docker 資源監控中心（取代繁重 Prometheus） |
| **n8n** | `https://n8n.io` (`n8n-io/n8n`) | `self_hosted_web_app` | 單一 Docker（首次需建帳號） | 視覺化節點工作流自動化平台（自架 Zapier/Make 替代） |
