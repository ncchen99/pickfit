# 安全審查

> 提案（2026-11-19）。總覽和共同規則在 [README.md](README.md)。之前的試點在 [docs/security-pilot.md](../security-pilot.md)，封頂造成的分數變化在 [docs/security-score-changes.md](../security-score-changes.md)。

## 現況

1,150 筆上架的紀錄裡，vulnerable 335 筆（29%）、clean 508 筆、unchecked 307 筆。MCP 的指示是遇到 vulnerable 先警告使用者（[server.ts:24](../../worker/src/server.ts)）。

unchecked 的原因：沒有 lockfile 182、解析失敗 61、沒有原始碼 50、不支援的格式 14。有 700 筆是 11/3 掃的，11/16 之後只掃了 4 筆，沒有定期重掃。

掃的方式太粗：

- **掃的不是使用者裝到的東西。** 335 筆 vulnerable 裡有 291 筆，是看預設分支最新的 lockfile 判的。OpenPets 掃的是 10/30 的 commit，驗證時裝的卻是 10/18 的 DMG v4.1.0。
- 只算 HIGH 和 CRITICAL（[security.py:52](../../pickfit/security.py)），最多存 60 筆（:59）。finding 沒有依賴路徑、沒標是不是 dev 依賴、沒有 CVSS vector（:548-552）。
- Cargo.lock 和 go.mod 整份讀（:367-373），dev、build、其他平台的依賴，還有鎖了但沒編進去的 optional 依賴都算進去。pnpm 掃所有 workspace（:298-307）。yarn.lock、bun.lock 不支援。

OpenPets 拆開來看，排最前面的兩條 CRITICAL 反而最不相關：

- proxy-addr、MCP SDK、hono 來自 `packages/mcp`，那邊只用 `StdioServerTransport`，HTTP server 的程式碼不會跑。
- tar 來自 node-gyp，是編譯工具。pi-coding-agent 和 openclaw 是 peerDependency。
- 真正跑得到的是 electron、sharp、undici。

finding 列全的 225 筆 vulnerable 裡，有 40 筆（18%）只是因為五種多半碰不到的情況被判 vulnerable：quinn-proto 鎖了但多半沒編進去、x/crypto 的漏洞都在 ssh 而專案沒 import ssh、pulldown-cmark 的 wikilinks、dompurify 的特定選項、Next.js 靜態輸出卻被算了 server 端的 RCE。其中 21 筆因此被壓在 79 分，包括 just、github-mcp-server、mcp-grafana。

也有真的相關的：privateer-agent 的 undici TLS 繞過、圖片工具的 Pillow 解碼器、certifi。所以不能整批放掉。

## 提案

### S1 observation 和 assessment 分開存（收錄前）

紀錄的 `security` 拆成兩塊：

- **observation**（看到什麼，不含判斷）：掃描器和版本、掃描對象（`repo_lockfile` 或 `installed_artifact`，附 commit sha、tool_version、artifact 的 sha256）、各生態系的套件數、advisory 抓取時間、全部等級的 finding。
- **assessment**（怎麼判）：`level`、理由、各等級的計數、`policy_version`（例如 `sec.v2`）、判定時間。

`security.status` 保留，由 assessment 推出來，讓舊的程式和頁面不會壞。

finding 全部存可能讓紀錄變很大。先量 OpenPets 這種大專案存全部會多大，太大的話完整 observation 放 `data/security/<slug>.json`，紀錄裡只留摘要和前幾筆。決定和量到的數字寫在回報裡。

### S2 每筆 finding 的欄位（收錄前）

- ids 和 aliases、published、modified、purl
- CVSS vector（v3 和 v4 都存原字串）、attack vector、CWE、是不是只有 DoS
- `fixed_in`、`fix_published_at`
- `scope`（runtime、dev、build、test、peer、optional）、依賴路徑、workspace、platform
- `found_in`（哪個 lockfile 或哪個 SBOM）、`in_artifact`（有沒有出現在裝好的東西裡）
- `kev`、`epss` 和查詢日期
- `preconditions`（漏洞要成立的前提）
- `reachability`：`method`、`result`、`evidence`
- `vex`（OpenVEX 格式的判斷，之後要給外部看時用）
- `triage`：模型、prompt 版本、輸入 sha、判定。沒有用模型時留空。
- `level` 和 `policy_version`

### S3 掃使用者實際裝到的東西（收錄前，最重要）

新增 `pickfit/sbom.py`，在 replay 箱裝完之後、箱子關掉之前收 SBOM：

- 一般情況用 syft 掃安裝目錄或 binary。
- Go binary 用 `govulncheck -mode=binary`，可以查到函式層級。
- Rust binary 用 `cargo audit bin`（binary 用 cargo-auditable 編的才有依賴資訊，沒有就退回 syft）。
- npm 全域安裝用 `npm ls --all --omit=dev --json`。
- 結果綁 tool_version 和 artifact 的 sha256，寫進 run 的 report.json，之後成為 `target: installed_artifact` 的 observation。

工具要裝進沙盒映像（`pickfit/verify/sandbox.Dockerfile`），先確認授權（syft Apache-2.0、govulncheck BSD-3、cargo-audit Apache-2.0/MIT），寫在回報裡。Windows 和 macOS 先做 Linux 版，其他平台列為之後。

`pipeline.py` 只加呼叫 `sbom.py` 的那一步。machines-cost 提案會改 replay 箱開啟的時間點，兩邊都盡量只動幾行。

這件事拖到以後才補，就得把每個沙盒重跑一次。

### S4 用程式判斷「有沒有裝到」「有沒有用到」（欄位收錄前，邏輯可以之後補）

全部用程式判斷，不用模型：

- npm：lockfile 的 `dev` 標記、`npm ls --omit=dev`、peerDependencies、只在 build 用的工具（node-gyp 一類）。
- pnpm：只看會被打包的 importer，不要所有 workspace 一起算。
- Cargo：解析 Cargo.toml 的 features 和 target，只算 normal 依賴、目標平台、有開的 optional 依賴。沙盒裡有 cargo 時可以用 `cargo tree -e normal`。
- Go：govulncheck 的 symbol 層級結果。沒有 binary 時用原始碼模式。
- OSV advisory 的 `ecosystem_specific` 列出受影響的函式時，在原始碼裡 grep。
- Next.js：`next.config` 有 `output: 'export'` 的，server 端漏洞標成 not_shipped。

判斷結果寫進每筆 finding 的 `scope`、`in_artifact`、`reachability`。

### S5 分級（收錄前定欄位，政策可以之後調）

| 等級 | 意思 | 效果 |
|---|---|---|
| blocked | 惡意套件，或碰得到的 runtime 元件在 CISA KEV 清單上 | 隱藏 |
| exposed | 預設就會跑到的 runtime 元件，有呼叫證據，而且會碰到網路或不受信任的輸入 | 安裝前警告，不能當 treasure |
| conditional | 特定情況下才碰得到（例如「打開來路不明的 EPUB」）。判不出來的也歸這一級 | 一行說明 |
| present_unreachable | 有裝，但沒用到那個函式或選項 | 列在詳細資料，不扣分 |
| not_shipped | dev、build、test、peer、其他平台的依賴 | 只計數 |
| clean／partial／unchecked | 附上理由 | partial 和 unchecked 只說「沒驗證」，不說安全 |

- 一筆紀錄的等級取所有 finding 裡最嚴重的那一級。
- KEV 用 CISA 的 JSON catalog，EPSS 用 FIRST 的 API。抓的時候有快取和日期。
- 「修好的版本已經出了 90 天，最新版還沒跟上」不在這裡封頂，改成給 scoring 用的 maintenance 訊號（存 `fix_published_at` 就夠了）。

### S6 模型 triage 的設計（之後再做，這次只留欄位）

- 每個 advisory 只問一次，讓模型抽出程式能檢查的前提：哪個函式、哪個選項、server 端還是 parser、是不是只有 DoS。用 advisory id 加 modified 時間快取。
- 再由程式到每個專案裡 grep。
- 剩下判不出來的才逐個專案問。答案必須附 file:line 引文，由程式重新 grep 核對，沒有證據就算 conditional。11/3 的試點有一筆模型結論對了、理由卻是錯的，所以一定要有證據。
- exposed 和 KEV 的進人工審查佇列。

### S7 MCP 和頁面的說法（收錄前）

- [server.ts:24](../../worker/src/server.ts) 的指示改成依等級：blocked 不推薦、exposed 先警告、conditional 提一句條件、partial 和 unchecked 不說安全。
- 頁面（`tool.ts` 的安全區，video 提案只改影片區）照等級顯示。新的英文句子要能被翻譯流程抓到。

### S8 定期重掃（可以並行做）

加一個重掃過期紀錄的指令（例如 `pickfit security --stale-days 14`）。advisory 會一直更新，11/3 掃的結果已經過時。排程之後再接到 watch 或 timer。

## 遷移

- 舊紀錄沒有 `assessment` 時，照現在的規則處理（scoring 那邊會繼續封頂 79）。
- 協調 session 合併後跑一次重掃（`pickfit security --all --write` 或新的指令），寫回紀錄，附一份像 [security-score-changes.md](../security-score-changes.md) 的前後比較。實作時不要寫 `data/software/`。

## 驗收

- 用 fixture 測：OpenPets 的 pnpm workspace、Cargo optional 依賴、Go 沒 import ssh、Next.js 靜態輸出、npm dev 依賴、peer 依賴。每一種都要分到預期的等級。
- `sbom.py` 用假的箱子測指令和解析。
- 回報附上：拿 `data/software/` 裡現有的 vulnerable 紀錄（只讀），在本機用新規則重算，有多少筆會換等級（不寫回）。
