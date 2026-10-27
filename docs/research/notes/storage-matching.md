# 儲存與配對調研筆記（F 節）

2026-10-28（台北）· 查證日一律 2026-10-28。資料來自 Cloudflare、Neon、Supabase、GitHub、Meta（dev.meta.ai）官方文件與 npm／PyPI。
實測：`spikes/sm_index_bench.mjs`、`spikes/sm_worker_startup.sh`、`spikes/sm_schema_events.py`（第 5 節）。沒親自確認的標「未驗證」。
相關筆記：配對的模型呼叫與 prompt 見 [meta-usage-design.md](meta-usage-design.md) 4.5；MCP 工具與 `rec_id` 見 [mcp-server.md](mcp-server.md) 5 節。

---

## 0. 結論（照做清單）

| # | 決定 | 理由（細節見後） |
|---|---|---|
| 1 | **正本：git 裡每款一份 JSON**（`data/software/<slug>.json`），不用 YAML | diff 就是審計紀錄，也是「比賽期間做的」證據；JSON 不必處理 YAML 的隱式型別；Python、JS、JSON Schema 都原生支援 |
| 2 | **MCP 讀的是建置產物**：`build_index` 把全部檔案轉成一個 `index.json`（候選卡＋BM25 倒排），**打包進 Worker**（JSON import） | 幾千筆約 1 MB；本機 `wrangler check startup` 量到啟動遠低於 1 秒上限；不用 KV／R2／D1 讀取，沒有額度問題 |
| 3 | 完整檔案（安裝步驟、驗證細節）：1,000 筆以內一起打包；超過就放 **Workers Static Assets**（`/p/<slug>.json`） | 靜態資產請求免費、不限量，每版 20,000 個檔、單檔 25 MiB；順便當展示頁 |
| 4 | **事件寫 D1**：`events`（查詢、安裝指南、回報、提交）、`reverify_queue`、`meta_budget` 三張表 | 需要 SQL 彙總與去重；KV 免費版每天只能寫 1,000 個 key、最終一致，不適合計數 |
| 5 | **更新路徑**：管線寫 JSON → commit／push → Workers Builds 自動 `validate → build_index → deploy` | 不用自己寫同步程式；建置失敗就不部署，壞資料進不了線上 |
| 6 | **回報回流到正本**：`sync_outcomes` 把 D1 的彙總寫回每份 JSON 的 `outcomes`；失敗回報進 `reverify_queue`，驗證 agent 重跑後 commit | 「回報 → 重驗 → 安裝步驟被修正」會留下一個 git diff，是 demo 中「不是 RAG」最直接的證據 |
| 7 | **配對：條件篩選 → BM25 取 25 張候選卡 → Muse Spark 取捨** | 程式管硬條件與證據，模型管語意與取捨（第 2 節） |
| 8 | **不用向量搜尋** | Meta 沒有 embedding 模型；spike：模型改寫查詢後，8,198 筆裡 10/10 題的好答案都進前 25 名（第 3 節） |
| 9 | 不用 Postgres（Neon／Supabase）、不在 Worker 裡用 SQLite 檔 | 幾千筆不需要；多一個服務、多一條連線，換不到東西 |

估計工時（單人）：schema＋驗證 1 h、`build_index` 1.5 h、D1 表＋`report_outcome` 寫入 1.5 h、Workers Builds 0.5 h、`sync_outcomes` 1 h。配對本身算在 MCP 工作裡。

---

## 1. 儲存

### 1.1 正本放哪

| | git 中的 JSON（每款一檔） | SQLite 檔 | Cloudflare D1 | Postgres（Neon／Supabase） |
|---|---|---|---|---|
| 開發時間 | 最短：寫檔＋commit | 短，但要 schema 遷移 | 中：建表、遷移、管線要走 REST 或 wrangler | 最長：多一個服務、連線、遷移 |
| MCP（Worker）怎麼讀 | 建置時轉索引，打包或當靜態資產 | Worker 不能直接開 SQLite 檔；要 sql.js（WASM，npm 解壓約 31 MB）或先轉 JSON | binding 直接查；每次呼叫最多 50 個查詢（Free） | 要走 HTTP driver 或 Hyperdrive（未查） |
| 管線（Python，本機或 Modal）怎麼寫 | 寫檔；遠端（Modal）用 GitHub Contents API `PUT /repos/{owner}/{repo}/contents/{path}` | 寫本機檔，再轉出 | REST `POST …/d1/database/{id}/query` 或 `wrangler d1 execute --remote --json`；REST 全域限 1,200 次／5 分鐘 | psycopg |
| 可審計性與 diff | **最好**：每次改動一個 commit，`git log -p` 看得到誰、何時、改了哪個欄位 | 二進位，diff 看不懂 | Time Travel 只能還原（Free 7 天），看不到逐欄位變更 | 要自己做 audit 表 |
| 人工抽查、修正 | 開檔改、PR review | 要 SQL | 要 SQL | 要 SQL |
| 免費額度 | GitHub：單檔 >50 MiB 警告、>100 MiB 擋；建議 repo <1 GB | — | 見 1.5 | Neon：每專案 1 GB、100 CU-hours／月，閒置 5 分鐘縮到 0；Supabase：500 MB，閒置 1 週暫停 |

**結論**：正本用 git JSON。D1 只放「使用者產生的事件」，這些不需要人審、量會變大、要 SQL 彙總。

**檔案格式約定**（讓 diff 乾淨）：`json.dumps(obj, indent=2, ensure_ascii=False)`＋結尾換行；key 順序照 schema；陣列順序固定（例如 `sources` 依 `id` 排序）。管線每次寫入前用 JSON Schema 驗證，失敗就不寫。

**截圖與 log**：終端機截圖（PNG 或 WebP）放 `data/evidence/<slug>/<run-id>/`，數百款約數十 MB，在 GitHub 建議範圍內（估算）。完整的模型 trace 與指令輸出**不進 git**：可能含 README 全文與第三方輸出。放本機或 R2（免費 10 GB），profile 只存 `log_url` 與摘要。

### 1.2 MCP server（Workers）怎麼讀

| 做法 | 讀取成本 | 更新方式 | 限制（Free） | 適合 |
|---|---|---|---|---|
| **打包進 Worker**（`import ix from "./index.json"`） | 0（在記憶體） | 重新部署 | Worker 64 MiB（未壓縮）、啟動 1 秒、記憶體 128 MB | **索引（推薦）** |
| **Workers Static Assets** | 請求免費、不限量 | 重新部署 | 每版 20,000 檔、單檔 25 MiB | 完整檔案、展示頁 |
| KV | 每次讀算 1 次，Free 10 萬次／天 | 不用部署；寫入後其他地點最多約 60 秒才看得到 | 寫入 1,000 key／天；同 key 每秒 1 次 | 不需要 |
| R2 | Class B 每月 1,000 萬次免費 | 不用部署 | 10 GB-month | 大型 log、截圖（選用） |
| D1 | 依掃描列數計，Free 500 萬列／天 | 不用部署 | 每 DB 500 MB；每次呼叫 50 個查詢 | 事件表 |

為什麼打包就夠：
- spike（`sm_worker_startup.sh`，wrangler 4.153.0 本機）：3,000 筆的索引 bundle 1,017 KiB（gzip 187 KiB）；8,198 筆 2,740 KiB。`wrangler check startup` 的 profile 中，非 idle 時間約 10–25 ms，離 1 秒上限很遠（本機 CPU，非線上數字）。
- Node 量 `JSON.parse`：3,000 筆 6 ms、8,198 筆 16.5 ms；查詢（篩選＋BM25＋top 25）中位數 0.3–0.6 ms。
- **倒排索引要在建置時算好**：啟動時才建，3,000 筆要 36 ms，8,198 筆要 117 ms。
- **未驗證**：Free 方案在冷啟動時，global scope 的解析是否算進該次請求的 10 ms CPU。文件只寫「啟動 1 秒」。若線上出現 Error 1102，改開 Paid（每月 5 美元，mcp-server.md 也建議 demo 週開）。

### 1.3 推薦架構與更新路徑

```
管線（Python；本機或 Modal）
  發現 → Muse Spark 抽取 → 沙盒驗證 → 計分
  └─ 寫 data/software/<slug>.json（先過 JSON Schema）→ git commit／push
                                      │（遠端管線用 GitHub Contents API commit）
                                      ▼
Workers Builds（push 觸發；Free 每月 3,000 建置分鐘、同時 1 個）
  validate（ajv）→ build_index（候選卡＋BM25 倒排，gitignore）→ wrangler deploy
                                      ▼
MCP Worker
  find_* ：記憶體內索引 → 篩選、BM25 → Muse Spark → 回應＋rec_id
  get_install_guide：完整檔案（打包或 Static Assets）
  report_outcome／submit_software：寫 D1
                                      ▼
D1（events、reverify_queue、meta_budget）
  sync_outcomes（本機，手動或每天一次）：wrangler d1 execute --remote --json
  → 寫回各檔 outcomes；reverify_queue → 驗證 agent 重跑 → commit
```

| 項目 | 內容 |
|---|---|
| repo 目錄 | `schema/software.v1.json`、`data/software/*.json`、`data/evidence/**`、`scripts/build_index.mjs`、`worker/` |
| 建置產物 | `worker/src/generated/index.json`（加進 `.gitignore`） |
| 候選卡欄位 | `slug, name, summary, why_worth_it, category, kind, tags, use_cases, alternatives_to, platforms, install.<os>.status／method／steps 數／manual_steps 數, pricing, open_source, license, processing, requirements.gpu／network／api_keys, verification.status／verified_at／reproducible, scores.quality.total, scores.popularity.percentile, scores.treasure, outcomes` |
| 提交到上線 | push → 建置 → 部署，估 1–3 分鐘（**未驗證**，Workers Builds 實際建置時間要量） |
| commit 慣例 | 管線產生的 commit 用 `data: <slug> <動作> (run <id>, <model id>)`，用念誠自己的 token，不另開 bot 帳號 |

### 1.4 事件表（D1）

不記 IP、不存使用者需求原文（brief 第 11 節）。`need` 只存 Muse Spark 解析後的條件。

<!-- sm:events-ddl -->
```sql
CREATE TABLE IF NOT EXISTS events (
  id            TEXT PRIMARY KEY,                -- ULID
  ts            TEXT NOT NULL,                   -- ISO 8601 UTC
  type          TEXT NOT NULL CHECK (type IN ('find','alternatives','install_guide','outcome','submit')),
  rec_id        TEXT,                            -- find_* 簽發的 handle；outcome 必填
  slug          TEXT,
  os            TEXT CHECK (os IN ('macos','linux','windows') OR os IS NULL),
  category      TEXT,
  need          TEXT CHECK (need IS NULL OR json_valid(need)),        -- 解析後的條件，不含原文
  results       TEXT CHECK (results IS NULL OR json_valid(results)),  -- 回傳的 slug 陣列
  stage         TEXT CHECK (stage IN ('installed','first_run','still_using') OR stage IS NULL),
  success       INTEGER CHECK (success IN (0,1) OR success IS NULL),
  satisfied     INTEGER CHECK (satisfied IN (-1,0,1) OR satisfied IS NULL),
  error_excerpt TEXT CHECK (error_excerpt IS NULL OR length(error_excerpt) <= 500),
  client        TEXT,                            -- MCP clientInfo.name
  generated_by  TEXT CHECK (generated_by IN ('model','rules') OR generated_by IS NULL),
  meta_cost_usd REAL,
  latency_ms    INTEGER,
  CHECK (type <> 'outcome' OR (rec_id IS NOT NULL AND slug IS NOT NULL AND stage IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS events_slug_type ON events(slug, type);
CREATE UNIQUE INDEX IF NOT EXISTS events_outcome_once ON events(rec_id, slug, stage) WHERE type = 'outcome';

CREATE TABLE IF NOT EXISTS reverify_queue (
  slug           TEXT NOT NULL,
  os             TEXT NOT NULL,
  reason         TEXT NOT NULL,
  first_event_id TEXT NOT NULL,
  queued_at      TEXT NOT NULL,
  done_at        TEXT,
  PRIMARY KEY (slug, os)
);

CREATE TABLE IF NOT EXISTS meta_budget (
  day      TEXT PRIMARY KEY,                     -- UTC 日期
  calls    INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0
);
```

| 操作 | SQL 重點 | 每次寫入列數（估算） |
|---|---|---|
| `find_*` | `INSERT INTO events`；`INSERT INTO meta_budget … ON CONFLICT(day) DO UPDATE SET calls = calls + 1, cost_usd = cost_usd + ? RETURNING cost_usd`，超過門檻就走規則排序 | 約 4（表 1＋索引 2＋budget 1） |
| `report_outcome` | `INSERT OR IGNORE`（同一 `rec_id`＋`slug`＋`stage` 只記一次）；`success = 0` 且有 `error_excerpt` → `INSERT INTO reverify_queue … ON CONFLICT DO UPDATE SET done_at = NULL …` | 約 4–6 |
| `sync_outcomes` | `GROUP BY slug, os` 彙總成功率 | 讀取 |

- Free 每天 10 萬列寫入 → 約 2 萬次查詢／天，demo 用不完。超過時 D1 回錯誤，要在 Worker 裡 catch，不要讓推薦失敗。
- `rec_id` 驗證不用查表（HMAC，見 mcp-server.md 5.2）。
- D1 是 SQLite 語法；上面的 DDL（含 partial unique index、`json_valid`、`RETURNING`）在本機 SQLite 3.45 跑過（spike），**在 D1 上未實測**。

### 1.5 免費額度（Workers Free 方案）

| 服務 | 額度 | 來源 |
|---|---|---|
| Workers | 10 萬請求／天；CPU 10 ms／請求；Worker 64 MiB（未壓縮，Free／Paid 相同）；啟動 1 秒；記憶體 128 MB | [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) |
| Static Assets | 請求免費、不限量；每版 20,000 檔；單檔 25 MiB | [Static assets billing](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/) |
| D1 | 10 個 DB；每 DB 500 MB；帳號 5 GB；讀 500 萬列／天；寫 10 萬列／天；每次呼叫 50 個查詢；Time Travel 7 天；支援 FTS5 與 JSON 函式 | [D1 limits](https://developers.cloudflare.com/d1/platform/limits/)、[D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/)、[SQL statements](https://developers.cloudflare.com/d1/sql-api/sql-statements/) |
| KV | 讀 10 萬次／天；寫 1,000 次／天（不同 key）；同 key 每秒 1 次；1 GB；值最大 25 MiB；最終一致（其他地點最多約 60 秒） | [KV limits](https://developers.cloudflare.com/kv/platform/limits/)、[How KV works](https://developers.cloudflare.com/kv/concepts/how-kv-works/) |
| R2 | 每月 10 GB-month、Class A 100 萬次、Class B 1,000 萬次；egress 免費 | [R2 pricing](https://developers.cloudflare.com/r2/pricing/) |
| Workers Builds | 每月 3,000 建置分鐘；同時 1 個；單次 20 分鐘 | [Builds limits](https://developers.cloudflare.com/workers/ci-cd/builds/limits-and-pricing/) |
| Cloudflare REST API | 1,200 次／5 分鐘（每使用者） | [API rate limits](https://developers.cloudflare.com/fundamentals/api/reference/limits/) |
| GitHub | 單檔 >50 MiB 警告、>100 MiB 擋；建議 repo <1 GB；public repo 的 Actions 免費 | [Large files](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)、[Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) |

---

## 2. 配對：怎麼做才不是「基本 RAG」

### 2.1 流程

模型呼叫的 schema 與 prompt 見 meta-usage-design.md 4.5（A 解析、C 比較）。這裡補「程式那一半」：候選怎麼來、什麼時候問問題、回報怎麼回流。

| 步 | 誰 | 做什麼 | 輸出 |
|---|---|---|---|
| A 解析需求 | **Muse Spark 1.3** | 自然語言 → 條件（`os`、`budget`、`privacy`、`category`、`must_have`…）＋ **`search_terms`**（英文關鍵字，把「會議錄音轉文字」改寫成 `speech recognition transcription whisper`）＋ `current_tool` | `need` |
| B 硬條件篩選 | 程式 | `status = listed`；`install.<os>.status ∈ {verified, partial, needs_manual_step}`（使用者 OS 未知時看任一 OS）；`privacy=local_only` → `processing = local` 且 `requirements.network ≠ required`；`budget=free_only` → `pricing.model = free`；有 `current_tool` 時加 `alternatives_to` 比對 | 合格清單 |
| C 取候選 | 程式 | 在合格清單上用 BM25 查 `search_terms`（欄位：name×3、tags×2、summary、use_cases、alternatives_to），取前 25；命中少於 5 筆且該類別合格數 ≤ 60 時，改成整個類別依寶藏分數排序送出 | ≤25 張候選卡（每張約 350 tokens） |
| D 該不該問 | 程式＋**Muse Spark** | 程式先算「分歧屬性」：`need` 裡未知、而前 5 名在這個屬性上值不同（例如 OS 未知、前 5 名有的只驗證過 Linux）。沒有分歧屬性就**不准問**。有的話交給 C 步的模型判斷問了會不會改變第一名、並寫成一題附選項 | `clarifying_question` 或 null |
| E 比較取捨 | **Muse Spark 1.3** | 選 1–3 個、每個理由附 `field_ref`、寫和知名工具的取捨、`best_free_option`、`no_new_software_needed` | `compare` |
| F 守門 | 程式 | slug 在候選裡；`field_ref` 存在且值對得上；違反硬條件的剔除；E 失敗 → 寶藏分數排序＋模板理由，標 `generated_by: rules` | MCP 回應（含 `verification` 證據、`rec_id`） |
| G 安裝 | 程式（不呼叫模型） | `get_install_guide` 只回傳 `install.<os>` 中重播過的步驟；使用者 OS 沒驗證過就明說，給最接近的已驗證 OS | 步驟、手動步驟、`check`、`first_task` |
| H 回報 | 程式 | `report_outcome` 寫 D1；失敗＋錯誤訊息 → `reverify_queue` → 驗證 agent（Muse Spark）重跑 → 新步驟 commit 進 git | 資料自己修正 |

每次 `find_software` 約 2 次 Muse Spark 呼叫，約 $0.024（meta-usage-design.md 的估算，未實測）。

### 2.2 跟「檢索文件再生成回答」的差別

| | 基本 RAG | pickfit |
|---|---|---|
| 知識從哪來 | 現成文件切塊 | 自己產生：Muse Spark 讀懂、沙盒實際安裝、程式重播後寫成結構化檔案 |
| 候選怎麼來 | 向量相似度取段落 | 硬條件篩選（OS、本機執行、價格、授權、驗證狀態）＋關鍵字；模型負責改寫需求 |
| 模型做什麼 | 摘要檢索到的段落 | 把需求轉成條件、決定要不要問、比較取捨、找免費選項；每個理由都要對得上欄位 |
| 輸出 | 一段文字 | 可執行的東西：重播過的安裝步驟、驗證指令、第一個任務 |
| 之後 | 結束 | 回報 → 失敗就重驗 → git 裡的步驟被改掉 |

### 2.3 demo 與 README 怎麼呈現

| 放哪 | 呈現什麼 |
|---|---|
| demo 第 3 幕 | 推薦結果旁邊直接秀證據：在哪個沙盒、哪天、幾步裝好、截圖（judge 框出的那一行） |
| demo 畫面一角 | trace 面板：A 解析 → B 篩選剩幾筆 → C 25 張卡 → E 取捨，每步標 model ID、token、花費；讓人看到模型拿到的是「候選卡」不是文件段落 |
| demo 第 4 幕後 | 故意回報一次失敗 → 驗證 agent 重跑 → 秀 git diff（安裝步驟多了一行）。這是 RAG 做不到的事 |
| README「Why this is not RAG」 | 2.2 的表＋一張流程圖；連到一個真的「回報後修正」的 commit |
| README 評測 | 對照組、實驗組之外加一列「關掉模型（規則排序）」，量出 Muse Spark 在配對的貢獻（brief 第 10 節的題組可共用） |
| 用詞 | 不用「knowledge base」「retrieval」描述產品；用 verified catalog、sandbox evidence、matching |

---

## 3. 需要向量搜尋嗎

### 3.1 查到的事實

| 項目 | 事實 | 來源 |
|---|---|---|
| Meta embedding 模型 | Meta Model API 的 API reference 只列 Responses、Chat Completions、Messages、Files、Models、Status（另有 Images、Voice 頁）；`llms.txt`、Models 頁、Open-weight 頁都**沒有 embedding 模型或 `/v1/embeddings`**。比賽可用模型清單也沒有。沒有 key，無法用 `GET /v1/models` 確認（未登入時 `/v1/embeddings` 和不存在的路徑都回 401），所以「確定沒有」標**未驗證** | [API reference](https://dev.meta.ai/docs/api-reference.md)、[llms.txt](https://dev.meta.ai/llms.txt)、[Models](https://dev.meta.ai/docs/models.md) |
| Workers AI 的 embedding | bge-small／base／large-en-v1.5、bge-m3、embeddinggemma-300m、qwen3-embedding-0.6b、plamo-embedding-1b；**沒有 Meta 的**。Free 每天 10,000 neurons | [Workers AI models](https://developers.cloudflare.com/workers-ai/models/)、[pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) |
| Vectorize（Free） | 100 個 index；最多 1,536 維；每 index 2,000 萬向量；每向量 metadata 10 KiB；帶 metadata 時 topK ≤ 50；metadata index ≤ 10 個、每個只索引前 64 bytes。存 500 萬維、每月查 3,000 萬維（查詢量＝(已存向量數＋查詢數)×維度） | [Vectorize limits](https://developers.cloudflare.com/vectorize/platform/limits/)、[pricing](https://developers.cloudflare.com/vectorize/platform/pricing/) |
| 換算 | 3,000 筆 × 768 維＝230 萬維（在免費內）；每月可查約 (30M ÷ 768) − 3,000 ≈ 3.6 萬次 | 由上式計算 |

### 3.2 spike：BM25 夠不夠

`sm_index_bench.mjs` 用 Homebrew formula（8,198 筆有描述的 CLI 套件）當語料，10 題。「原話」是使用者會說的話；「改寫」是手寫的模擬，代表 A 步 Muse Spark 會產生的 `search_terms`（**不是模型輸出**）。驗證狀態是假資料，只用來篩掉約 4 成。

| 語料大小 | 原話：好答案進前 25 | 改寫後：好答案進前 25 |
|---|---:|---:|
| 500 | 8／10 | 10／10 |
| 3,000 | 7／10 | 10／10 |
| 8,198 | 5／10 | 10／10 |

- 原話失敗的典型：「turn my meeting recording into text offline」對不到 whisper 類（描述裡沒有 recording、text）；「talk to chatgpt-like models from my shell」對不到 `aichat`。
- 改寫後最差的一題，好答案排第 6 名；C 步把前 25 名都交給模型，所以不影響。
- Homebrew 描述只有一行、沒有 tags／use_cases，這是**下限**。pickfit 的檔案會由 Muse Spark 抽出 `tags`、`use_cases`、`alternatives_to`（文件端的改寫），召回只會更好（推論，未實測）。

### 3.3 建議

- **黑客松不用向量搜尋。** 語意落差交給 Muse Spark 在兩端處理：抽取時寫 `use_cases`、`alternatives_to`；查詢時寫 `search_terms`。這樣語意理解也算在 Meta 模型身上。
- 用 embedding 等於在配對的核心路徑放一個非 Meta 模型，而且「向量庫＋LLM」正是基本 RAG 的樣子，兩邊都扣分。
- **什麼時候重新考慮**：評測題組（brief 第 10 節）裡有 2 題以上是「好答案在檔案裡，但不在 C 步的 25 張卡裡」；或收錄超過 1 萬筆。到時先試「把整個類別送進模型」（候選卡放在固定前綴，吃 prompt cache，命中率未驗證），再考慮 bge-m3＋Vectorize。

---

## 4. 檔案 schema（`software.v1`）

### 4.1 對照 brief 第 11 節

| brief 欄位 | schema 欄位 | 誰寫 |
|---|---|---|
| `slug`（永不改） | `slug`（改名放 `aliases`） | 程式：repo 名小寫，撞名加 `-<owner>` |
| `name`、`summary` | 同名 | Muse Spark 抽取 |
| `homepage`、`repo` | 同名；`repo` 是物件 | GitHub API |
| `platforms` | `platforms`＝來源宣稱；實際結果在 `install.<os>.status` | 抽取＋驗證 |
| `install` | `install.{macos,linux,windows}`：狀態、方式、步驟（`run_by: agent／user`）、手動步驟、`check`、`first_task` | 驗證 agent；`claimed` 是 README 寫的 |
| `pricing` | `pricing.model`＋`note` | 抽取 |
| `open_source`、`license` | 同名；license 用 SPDX，API 優先 | GitHub API |
| `processing` | `local／cloud／hybrid／unknown` | 抽取 |
| `last_release` | `{tag, published_at, url}` | GitHub API |
| `verification` | `status`、`verified_at`、`runs[]`（沙盒、步數、時間、smoke test、與 README 的差異、judge、截圖、花費） | 驗證 agent＋程式重播 |
| `scores` | `quality`（總分與 6 個分項）、`popularity`（百分位與訊號）、`treasure`、`formula_version` | 規則＋模型評分 |
| `sources` | `sources[]`（id、種類、URL、抓取時間）＋`evidence[]`（哪個欄位、哪個來源、引用、方法、查證時間） | 程式 |
| （新增） | `status`（只有 `listed` 會被推薦）、`category`、`kind`、`tags`、`use_cases`、`alternatives_to`、`requirements`、`outcomes`、`unknown_fields`、`review`、`provenance`、`first_seen_at`、`updated_at` | 見各欄 |

程式端規則（JSON Schema 表達不了的，spike 有實作）：
1. `evidence[].source_id` 都要在 `sources` 裡；`evidence[].field` 要指到存在的欄位。
2. 事實欄位（`summary`、`platforms`、`pricing`、`license`、`processing`、`last_release`、每個 `install.<os>`）要嘛有 evidence，要嘛列在 `unknown_fields`。
3. `install.<os>.status = verified` 時，`sandbox_ref` 指到的那次 run 必須 `reproducible = true`。

### 4.2 JSON Schema 草案（2020-12）

<!-- sm:profile-schema -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://pickfit.dev/schema/software.v1.json",
  "title": "pickfit software profile v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "slug", "name", "summary", "status", "category", "kind", "homepage", "repo",
               "platforms", "install", "pricing", "open_source", "license", "processing", "last_release",
               "verification", "scores", "sources", "evidence", "unknown_fields", "first_seen_at", "updated_at"],
  "properties": {
    "schema_version": {"const": 1},
    "slug": {"type": "string", "pattern": "^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$", "description": "永不改；檔名 data/software/<slug>.json"},
    "aliases": {"type": "array", "maxItems": 10, "items": {"type": "string"}},
    "name": {"type": "string", "minLength": 1, "maxLength": 80},
    "summary": {"type": "string", "minLength": 1, "maxLength": 160},
    "why_worth_it": {"type": ["string", "null"], "maxLength": 200},
    "status": {"enum": ["candidate", "listed", "hidden", "removed"], "description": "只有 listed 會被 MCP 回傳"},
    "status_reason": {"type": ["string", "null"], "maxLength": 200},
    "category": {"enum": ["dev_cli", "local_ai", "other"]},
    "kind": {"enum": ["cli_tool", "tui_app", "local_server", "desktop_app", "web_app", "other"]},
    "tags": {"type": "array", "maxItems": 12, "uniqueItems": true, "items": {"type": "string", "pattern": "^[a-z0-9][a-z0-9+.-]{0,30}$"}},
    "use_cases": {"type": "array", "maxItems": 5, "items": {"type": "string", "maxLength": 120}},
    "alternatives_to": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 60}, "description": "可取代的知名軟體，給 find_alternatives"},
    "homepage": {"type": ["string", "null"], "format": "uri"},
    "repo": {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/repo"}]},
    "platforms": {"type": "array", "uniqueItems": true, "items": {"$ref": "#/$defs/os"}, "description": "來源宣稱支援；實測看 install"},
    "install": {
      "type": "object", "additionalProperties": false,
      "properties": {"macos": {"$ref": "#/$defs/install_os"}, "linux": {"$ref": "#/$defs/install_os"}, "windows": {"$ref": "#/$defs/install_os"}}
    },
    "requirements": {"$ref": "#/$defs/requirements"},
    "pricing": {
      "type": "object", "additionalProperties": false, "required": ["model"],
      "properties": {"model": {"enum": ["free", "freemium", "paid", "unknown"]}, "note": {"type": ["string", "null"], "maxLength": 200}}
    },
    "open_source": {"type": ["boolean", "null"]},
    "license": {"type": ["string", "null"], "description": "SPDX；GitHub 回 NOASSERTION 時為 null"},
    "processing": {"enum": ["local", "cloud", "hybrid", "unknown"]},
    "ui_languages": {"type": "array", "items": {"type": "string"}},
    "last_release": {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/release"}]},
    "verification": {"$ref": "#/$defs/verification"},
    "scores": {"$ref": "#/$defs/scores"},
    "outcomes": {"$ref": "#/$defs/outcomes"},
    "sources": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/source"}},
    "evidence": {"type": "array", "items": {"$ref": "#/$defs/evidence"}},
    "unknown_fields": {"type": "array", "items": {"type": "string", "pattern": "^/"}},
    "review": {
      "type": "object", "additionalProperties": false, "required": ["human_checked"],
      "properties": {"human_checked": {"type": "boolean"}, "checked_at": {"$ref": "#/$defs/ts_or_null"}, "note": {"type": ["string", "null"]}}
    },
    "provenance": {
      "type": "object", "additionalProperties": false,
      "properties": {"pipeline_version": {"type": "string"}, "extract_model": {"type": "string"}, "extracted_at": {"$ref": "#/$defs/ts"}}
    },
    "first_seen_at": {"$ref": "#/$defs/ts"},
    "updated_at": {"$ref": "#/$defs/ts"}
  },
  "$defs": {
    "os": {"enum": ["macos", "linux", "windows"]},
    "ts": {"type": "string", "format": "date-time"},
    "ts_or_null": {"type": ["string", "null"], "format": "date-time"},
    "num_or_null": {"type": ["number", "null"]},
    "repo": {
      "type": "object", "additionalProperties": false, "required": ["url", "host", "full_name"],
      "properties": {
        "url": {"type": "string", "format": "uri"},
        "host": {"enum": ["github", "gitlab", "codeberg", "other"]},
        "full_name": {"type": "string"},
        "created_at": {"$ref": "#/$defs/ts_or_null"}
      }
    },
    "step": {
      "type": "object", "additionalProperties": false, "required": ["command", "purpose", "run_by"],
      "properties": {
        "command": {"type": "string", "minLength": 1, "maxLength": 500},
        "purpose": {"type": "string", "maxLength": 120},
        "run_by": {"enum": ["agent", "user"]},
        "optional": {"type": "boolean"}
      }
    },
    "check": {
      "type": "object", "additionalProperties": false, "required": ["command", "expected_signal"],
      "properties": {"command": {"type": "string"}, "expected_signal": {"type": "string"}}
    },
    "install_os": {
      "type": "object", "additionalProperties": false, "required": ["status", "method", "steps"],
      "properties": {
        "status": {"enum": ["verified", "partial", "needs_manual_step", "failed", "claimed", "unsupported_env"], "description": "verified＝重播通過；claimed＝README 寫的、沒跑過"},
        "method": {"enum": ["brew", "cargo", "pip", "pipx", "uv", "npm", "go", "binary", "docker", "script", "source", "other"]},
        "steps": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/step"}},
        "manual_steps": {"type": "array", "items": {"type": "string", "maxLength": 200}},
        "check": {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/check"}]},
        "first_task": {"type": ["string", "null"], "maxLength": 300, "description": "裝好後第一個有用的指令"},
        "verified_at": {"$ref": "#/$defs/ts_or_null"},
        "sandbox_ref": {"type": ["string", "null"], "description": "verification.runs[].id"}
      },
      "if": {"properties": {"status": {"const": "verified"}}},
      "then": {
        "required": ["verified_at", "check", "sandbox_ref"],
        "properties": {"verified_at": {"type": "string"}, "check": {"type": "object"}, "sandbox_ref": {"type": "string"}}
      }
    },
    "requirements": {
      "type": "object", "additionalProperties": false, "required": ["gpu", "network", "api_keys"],
      "properties": {
        "runtimes": {"type": "array", "items": {"type": "string"}},
        "gpu": {"enum": ["required", "optional", "none", "unknown"]},
        "min_ram_gb": {"$ref": "#/$defs/num_or_null"},
        "disk_gb": {"$ref": "#/$defs/num_or_null"},
        "network": {"enum": ["required", "optional", "none", "unknown"]},
        "api_keys": {"type": "array", "items": {"type": "string"}}
      }
    },
    "release": {
      "type": "object", "additionalProperties": false, "required": ["tag", "published_at"],
      "properties": {"tag": {"type": "string"}, "published_at": {"$ref": "#/$defs/ts"}, "url": {"type": ["string", "null"], "format": "uri"}}
    },
    "run": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "os", "arch", "sandbox", "started_at", "outcome", "reproducible", "steps_count", "smoke_tests", "screenshots", "models"],
      "properties": {
        "id": {"type": "string", "pattern": "^[a-z0-9-]+$"},
        "os": {"$ref": "#/$defs/os"},
        "arch": {"enum": ["x86_64", "arm64"]},
        "sandbox": {
          "type": "object", "additionalProperties": false, "required": ["provider", "image", "network"],
          "properties": {
            "provider": {"enum": ["modal", "docker_local", "gha_macos", "other"]},
            "image": {"type": "string"},
            "network": {"enum": ["open", "allowlist", "none"]},
            "cpu": {"$ref": "#/$defs/num_or_null"},
            "memory_gb": {"$ref": "#/$defs/num_or_null"},
            "timeout_min": {"$ref": "#/$defs/num_or_null"}
          }
        },
        "started_at": {"$ref": "#/$defs/ts"},
        "duration_s": {"$ref": "#/$defs/num_or_null"},
        "outcome": {"enum": ["verified", "partial", "needs_manual_step", "failed", "unsupported_env"]},
        "reproducible": {"type": ["boolean", "null"], "description": "乾淨沙盒重播是否通過；null＝沒重播"},
        "steps_count": {"type": "integer", "minimum": 0},
        "smoke_tests": {
          "type": "array",
          "items": {
            "type": "object", "additionalProperties": false, "required": ["command", "expected_signal", "passed"],
            "properties": {
              "command": {"type": "string"}, "expected_signal": {"type": "string"},
              "observed_excerpt": {"type": ["string", "null"], "maxLength": 300}, "passed": {"type": "boolean"}
            }
          }
        },
        "deviations_from_readme": {
          "type": "array",
          "items": {
            "type": "object", "additionalProperties": false, "required": ["readme_said", "actually_needed"],
            "properties": {"readme_said": {"type": "string"}, "actually_needed": {"type": "string"}}
          }
        },
        "blocking_error": {"type": ["string", "null"], "maxLength": 500},
        "judge": {
          "anyOf": [{"type": "null"}, {
            "type": "object", "additionalProperties": false, "required": ["verdict", "model"],
            "properties": {"verdict": {"enum": ["working", "error_visible", "inconclusive"]}, "observed": {"type": "string"}, "model": {"type": "string"}}
          }]
        },
        "screenshots": {
          "type": "array",
          "items": {
            "type": "object", "additionalProperties": false, "required": ["path", "sha256"],
            "properties": {"path": {"type": "string"}, "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}, "caption": {"type": "string"}}
          }
        },
        "log_url": {"type": ["string", "null"], "format": "uri"},
        "models": {
          "type": "object", "additionalProperties": false, "required": ["actor"],
          "properties": {"actor": {"type": "string"}, "judge": {"type": ["string", "null"]}}
        },
        "cost_usd": {"$ref": "#/$defs/num_or_null"}
      }
    },
    "verification": {
      "type": "object", "additionalProperties": false, "required": ["status", "verified_at", "runs"],
      "properties": {
        "status": {"enum": ["verified", "partial", "needs_manual_step", "failed", "unsupported_env", "not_run"]},
        "verified_at": {"$ref": "#/$defs/ts_or_null"},
        "runs": {"type": "array", "items": {"$ref": "#/$defs/run"}, "description": "每個 OS 只留最新一次；歷史看 git"}
      }
    },
    "scores": {
      "type": "object", "additionalProperties": false, "required": ["formula_version", "computed_at", "quality", "popularity", "treasure"],
      "properties": {
        "formula_version": {"type": "string"},
        "computed_at": {"$ref": "#/$defs/ts"},
        "quality": {
          "type": "object", "additionalProperties": false, "required": ["total", "components"],
          "properties": {
            "total": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
            "components": {
              "type": "object", "additionalProperties": false,
              "properties": {
                "verification": {"$ref": "#/$defs/num_or_null"}, "install_doc_accuracy": {"$ref": "#/$defs/num_or_null"},
                "docs": {"$ref": "#/$defs/num_or_null"}, "first_run": {"$ref": "#/$defs/num_or_null"},
                "maintenance": {"$ref": "#/$defs/num_or_null"}, "outcomes": {"$ref": "#/$defs/num_or_null"}
              }
            }
          }
        },
        "popularity": {
          "type": "object", "additionalProperties": false, "required": ["percentile", "signals"],
          "properties": {
            "percentile": {"type": ["number", "null"], "minimum": 0, "maximum": 100, "description": "類別內百分位"},
            "signals": {
              "type": "object", "additionalProperties": false,
              "properties": {
                "stars": {"type": ["integer", "null"]}, "forks": {"type": ["integer", "null"]},
                "downloads_30d": {"type": ["integer", "null"]}, "hn_points": {"type": ["integer", "null"]},
                "search_visible": {"type": ["boolean", "null"]}, "age_days": {"type": ["integer", "null"]}
              }
            }
          }
        },
        "treasure": {"type": ["number", "null"], "description": "quality.total × (1 − percentile/100)"}
      }
    },
    "outcomes": {
      "type": "object", "additionalProperties": false, "required": ["reports", "synced_at"],
      "properties": {
        "reports": {"type": "integer", "minimum": 0}, "install_ok": {"type": "integer", "minimum": 0},
        "first_run_ok": {"type": "integer", "minimum": 0}, "satisfied": {"type": "integer", "minimum": 0},
        "last_report_at": {"$ref": "#/$defs/ts_or_null"}, "synced_at": {"$ref": "#/$defs/ts_or_null"}
      }
    },
    "source": {
      "type": "object", "additionalProperties": false, "required": ["id", "kind", "url", "fetched_at"],
      "properties": {
        "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9:._-]*$"},
        "kind": {"enum": ["github_api", "readme", "release", "manifest", "package_registry", "hn", "submission", "sandbox", "web"]},
        "url": {"type": ["string", "null"], "format": "uri"},
        "fetched_at": {"$ref": "#/$defs/ts"}
      }
    },
    "evidence": {
      "type": "object", "additionalProperties": false, "required": ["field", "source_id", "method", "checked_at"],
      "properties": {
        "field": {"type": "string", "pattern": "^/", "description": "JSON Pointer，例如 /license"},
        "source_id": {"type": "string"},
        "quote": {"type": ["string", "null"], "maxLength": 200, "description": "逐字引用；API 值與沙盒結果為 null"},
        "method": {"enum": ["api", "model", "sandbox", "rule", "human"]},
        "checked_at": {"$ref": "#/$defs/ts"}
      }
    }
  }
}
```

### 4.3 範例（虛構的軟體，只用來測 schema）

<!-- sm:profile-example -->
```json
{
  "schema_version": 1,
  "slug": "example-whisper-cli",
  "aliases": [],
  "name": "example-whisper-cli",
  "summary": "（虛構範例）在本機把音訊檔轉成文字的命令列工具",
  "why_worth_it": "（虛構）Linux 沙盒 3 步裝好，第一次執行就轉出逐字稿；README 漏寫要先裝 ffmpeg",
  "status": "listed",
  "status_reason": null,
  "category": "local_ai",
  "kind": "cli_tool",
  "tags": ["speech-to-text", "whisper", "offline", "cli"],
  "use_cases": ["transcribe a wav file offline", "generate srt subtitles from a recording"],
  "alternatives_to": ["openai-whisper"],
  "homepage": null,
  "repo": {"url": "https://github.com/example/example-whisper-cli", "host": "github", "full_name": "example/example-whisper-cli", "created_at": "2026-08-14T09:12:00Z"},
  "platforms": ["linux", "macos"],
  "install": {
    "linux": {
      "status": "verified",
      "method": "pipx",
      "steps": [
        {"command": "sudo apt-get install -y ffmpeg", "purpose": "解碼音訊（README 沒寫）", "run_by": "agent"},
        {"command": "pipx install example-whisper-cli", "purpose": "安裝", "run_by": "agent"},
        {"command": "example-whisper download tiny", "purpose": "下載最小的模型", "run_by": "agent"}
      ],
      "manual_steps": [],
      "check": {"command": "example-whisper transcribe sample.wav", "expected_signal": "[00:00.000 -->"},
      "first_task": "example-whisper transcribe meeting.wav --srt",
      "verified_at": "2026-10-31T08:20:00Z",
      "sandbox_ref": "run-20261031-linux-1"
    },
    "macos": {
      "status": "claimed",
      "method": "brew",
      "steps": [{"command": "brew install example/tap/example-whisper-cli", "purpose": "README 寫的方式（沒驗證）", "run_by": "agent"}],
      "manual_steps": ["第一次錄音時在系統設定允許麥克風"],
      "check": null,
      "first_task": null,
      "verified_at": null,
      "sandbox_ref": null
    }
  },
  "requirements": {"runtimes": ["python>=3.10"], "gpu": "optional", "min_ram_gb": 2, "disk_gb": 1, "network": "optional", "api_keys": []},
  "pricing": {"model": "free", "note": null},
  "open_source": true,
  "license": "MIT",
  "processing": "local",
  "ui_languages": ["en"],
  "last_release": {"tag": "v0.4.1", "published_at": "2026-10-20T12:00:00Z", "url": "https://github.com/example/example-whisper-cli/releases/tag/v0.4.1"},
  "verification": {
    "status": "verified",
    "verified_at": "2026-10-31T08:20:00Z",
    "runs": [{
      "id": "run-20261031-linux-1",
      "os": "linux",
      "arch": "x86_64",
      "sandbox": {"provider": "modal", "image": "ubuntu-24.04 python3.12 pipx node22", "network": "open", "cpu": 2, "memory_gb": 4, "timeout_min": 20},
      "started_at": "2026-10-31T08:05:00Z",
      "duration_s": 512,
      "outcome": "verified",
      "reproducible": true,
      "steps_count": 3,
      "smoke_tests": [{"command": "example-whisper transcribe sample.wav", "expected_signal": "[00:00.000 -->", "observed_excerpt": "[00:00.000 --> 00:03.200] hello world", "passed": true}],
      "deviations_from_readme": [{"readme_said": "pipx install example-whisper-cli", "actually_needed": "先 apt-get install ffmpeg"}],
      "blocking_error": null,
      "judge": {"verdict": "working", "observed": "終端機顯示時間戳與逐字稿", "model": "muse-spark-1.3"},
      "screenshots": [{"path": "data/evidence/example-whisper-cli/run-20261031-linux-1/terminal.png", "sha256": "0000000000000000000000000000000000000000000000000000000000000000", "caption": "smoke test 輸出"}],
      "log_url": null,
      "models": {"actor": "muse-spark-1.3", "judge": "muse-spark-1.3"},
      "cost_usd": 0.19
    }]
  },
  "scores": {
    "formula_version": "q1-n1",
    "computed_at": "2026-10-31T09:00:00Z",
    "quality": {"total": 78.5, "components": {"verification": 40, "install_doc_accuracy": 9, "docs": 10, "first_run": 4, "maintenance": 13, "outcomes": 2.5}},
    "popularity": {"percentile": 12, "signals": {"stars": 41, "forks": 3, "downloads_30d": null, "hn_points": null, "search_visible": false, "age_days": 78}},
    "treasure": 69.1
  },
  "outcomes": {"reports": 0, "install_ok": 0, "first_run_ok": 0, "satisfied": 0, "last_report_at": null, "synced_at": null},
  "sources": [
    {"id": "meta", "kind": "github_api", "url": "https://api.github.com/repos/example/example-whisper-cli", "fetched_at": "2026-10-30T02:00:00Z"},
    {"id": "readme", "kind": "readme", "url": "https://github.com/example/example-whisper-cli#readme", "fetched_at": "2026-10-30T02:00:00Z"},
    {"id": "release:v0.4.1", "kind": "release", "url": "https://github.com/example/example-whisper-cli/releases/tag/v0.4.1", "fetched_at": "2026-10-30T02:00:00Z"},
    {"id": "sandbox:run-20261031-linux-1", "kind": "sandbox", "url": null, "fetched_at": "2026-10-31T08:20:00Z"}
  ],
  "evidence": [
    {"field": "/summary", "source_id": "readme", "quote": "Transcribe audio files on your machine.", "method": "model", "checked_at": "2026-10-30T02:01:00Z"},
    {"field": "/platforms", "source_id": "readme", "quote": "Works on Linux and macOS.", "method": "model", "checked_at": "2026-10-30T02:01:00Z"},
    {"field": "/pricing", "source_id": "readme", "quote": "Free and open source.", "method": "model", "checked_at": "2026-10-30T02:01:00Z"},
    {"field": "/license", "source_id": "meta", "quote": null, "method": "api", "checked_at": "2026-10-30T02:00:00Z"},
    {"field": "/processing", "source_id": "readme", "quote": "Runs fully offline after the model download.", "method": "model", "checked_at": "2026-10-30T02:01:00Z"},
    {"field": "/last_release", "source_id": "release:v0.4.1", "quote": null, "method": "api", "checked_at": "2026-10-30T02:00:00Z"},
    {"field": "/install/linux", "source_id": "sandbox:run-20261031-linux-1", "quote": null, "method": "sandbox", "checked_at": "2026-10-31T08:20:00Z"},
    {"field": "/install/macos", "source_id": "readme", "quote": "brew install example/tap/example-whisper-cli", "method": "model", "checked_at": "2026-10-30T02:01:00Z"}
  ],
  "unknown_fields": ["/homepage"],
  "review": {"human_checked": false, "checked_at": null, "note": null},
  "provenance": {"pipeline_version": "0.1.0", "extract_model": "muse-spark-1.3", "extracted_at": "2026-10-30T02:01:00Z"},
  "first_seen_at": "2026-10-30T01:58:00Z",
  "updated_at": "2026-10-31T09:00:00Z"
}
```

---

## 5. Spike

| 腳本 | 驗證什麼 | 怎麼跑 | 結果 |
|---|---|---|---|
| `spikes/sm_index_bench.mjs` | JSON 索引的大小、parse 與查詢時間；條件篩選；BM25 原話 vs 改寫的召回 | `node spikes/sm_index_bench.mjs`（約 5 秒；第一次會下載 Homebrew formula API 約 32 MB 到暫存目錄） | 見 1.2、3.2 |
| `spikes/sm_worker_startup.sh` | 索引打包進 Worker 後的 bundle 大小與啟動 CPU（wrangler 本機，不登入） | `bash spikes/sm_worker_startup.sh 3000` | 見 1.2 |
| `spikes/sm_schema_events.py` | 從本文抽出 schema、範例、DDL：範例過 schema、壞資料被擋、程式端規則、D1 表在 SQLite 上的去重與彙總；SQLite＋FTS5 當索引的大小 | `python3 spikes/sm_schema_events.py` | 見下 |

`sm_schema_events.py` 結果：（待填）

---

## 6. 未驗證

| # | 項目 | 怎麼確認 |
|---|---|---|
| 1 | Free 方案冷啟動時，global scope 解析是否算進請求的 10 ms CPU | 部署後看 Invocation Statuses；出現 1102 就開 Paid |
| 2 | Workers Builds 從 push 到上線實際幾分鐘 | 第一次接上時量 |
| 3 | DDL 的 partial unique index、`json_valid`、`RETURNING` 在 D1 上可用 | `wrangler d1 execute --local` 再 `--remote` 跑一次 |
| 4 | Meta Model API 確實沒有 embedding 端點 | 拿到 key 後 `GET /v1/models` |
| 5 | 抽取產生的 `tags`／`use_cases` 讓 BM25 召回更好 | 10/29 抽完第一批後，用評測題組重跑 C 步 |
| 6 | 「整個類別放固定前綴」的 prompt cache 命中率 | 只有 3.3 的後備方案需要 |

---

## 7. 來源（查證日 2026-10-28）

- Workers limits：https://developers.cloudflare.com/workers/platform/limits/
- Static assets billing：https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/
- Wrangler bundling：https://developers.cloudflare.com/workers/wrangler/bundling/
- Workers Builds limits：https://developers.cloudflare.com/workers/ci-cd/builds/limits-and-pricing/
- GitHub Actions 部署 Workers：https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/
- D1 limits：https://developers.cloudflare.com/d1/platform/limits/
- D1 pricing：https://developers.cloudflare.com/d1/platform/pricing/
- D1 SQL statements（FTS5、JSON）：https://developers.cloudflare.com/d1/sql-api/sql-statements/
- D1 query（REST 主要是 control plane）：https://developers.cloudflare.com/d1/best-practices/query-d1/
- D1 REST query：https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/
- D1 wrangler commands：https://developers.cloudflare.com/d1/wrangler-commands/
- KV limits／pricing／consistency：https://developers.cloudflare.com/kv/platform/limits/、https://developers.cloudflare.com/kv/platform/pricing/、https://developers.cloudflare.com/kv/concepts/how-kv-works/
- R2 pricing：https://developers.cloudflare.com/r2/pricing/
- Vectorize limits／pricing：https://developers.cloudflare.com/vectorize/platform/limits/、https://developers.cloudflare.com/vectorize/platform/pricing/
- Workers AI models／pricing：https://developers.cloudflare.com/workers-ai/models/、https://developers.cloudflare.com/workers-ai/platform/pricing/
- Cloudflare API rate limits：https://developers.cloudflare.com/fundamentals/api/reference/limits/
- Neon plans：https://neon.com/docs/introduction/plans
- Supabase billing／pricing：https://supabase.com/docs/guides/platform/billing-on-supabase、https://supabase.com/pricing
- GitHub large files：https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
- GitHub Contents API：https://docs.github.com/en/rest/repos/contents
- GitHub Actions billing：https://docs.github.com/en/billing/concepts/product-billing/github-actions
- Meta Model API reference／llms.txt／Models：https://dev.meta.ai/docs/api-reference.md、https://dev.meta.ai/llms.txt、https://dev.meta.ai/docs/models.md
- npm：minisearch 7.2.0（MIT，BM25+）、@orama/orama 3.1.18（Apache-2.0）、ajv 8.20.0（MIT）、sql.js 1.15.2（MIT）；PyPI：jsonschema 4.26.0（MIT）
- Homebrew formula API（spike 語料，執行時下載，不進 repo）：https://formulae.brew.sh/api/formula.json
