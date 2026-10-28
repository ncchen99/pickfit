# pickfit MCP server（Cloudflare Worker）

無狀態的 Streamable HTTP MCP server（官方 TypeScript SDK v2 的 `createMcpHandler`，新舊兩代協定都收）。5 個工具：`find_software`、`find_alternatives`、`get_install_guide`、`report_outcome`、`submit_software`（`TOOLS=readonly` 時只有前 3 個，見「評測部署」）。**還沒部署**，只在本機跑；部署步驟見文末的檢查清單。

## 怎麼跑

```bash
cd worker
npm install
npm run build:index -- --data test/fixtures/software   # 還沒有真資料：先用 5 筆假 profile
npm run db:migrate:local                                # 本機 D1 建表（套用 migrations/ 全部）
grep -E '^MODEL_API_KEY=' ../.env > .dev.vars           # 只取這一個變數；.dev.vars 已 gitignore
npm run dev                                             # http://127.0.0.1:8787/mcp
```

- 關掉模型：`npx wrangler dev --var MATCH_MODE:off`（或不放 `MODEL_API_KEY`）。
- 測試：`npm test`（先用 `scripts/build_index.py` 從 fixture 建索引；D1 用 `node:sqlite` 跑同一份 migration；Meta 回應是假的，不打 API）。型別：`npm run typecheck`。
- 真資料：`npm run build:index`（讀 `data/software/*.json`，任何一筆不合 `software.v1` 就失敗、不寫索引）。部署用 `uv run pickfit publish`（見文末）。

Claude Code 連本機（桌面 app 的 shell 要用 `env -i`，否則會繼承 `ANTHROPIC_BASE_URL`）：

```bash
echo '{"mcpServers":{"pickfit":{"type":"http","url":"http://127.0.0.1:8787/mcp","headers":{"X-Pickfit-Reporter":"dev"}}}}' > /tmp/pickfit-mcp.json
env -i HOME="$HOME" PATH="$PATH" ANTHROPIC_API_KEY=… claude -p "…" \
  --strict-mcp-config --mcp-config /tmp/pickfit-mcp.json \
  --allowedTools "mcp__pickfit__find_software,mcp__pickfit__find_alternatives,mcp__pickfit__get_install_guide,mcp__pickfit__report_outcome,mcp__pickfit__submit_software"
```

`X-Pickfit-Reporter`（`dev`、`eval`、`demo`）只是標記：`report_outcome` 存進 `events.reporter`，讓自己的測試、評測、錄影和外部回報分得開；沒帶就是 `external`。

## 工具

| 工具 | 呼叫模型 | 寫 D1 | 重點 |
|---|---|---|---|
| `find_software` | `muse-spark-1.3` 一次（超預算或失敗退回規則） | `events`（find） | 見下節 |
| `find_alternatives` | 同上，同一條路徑 | `events`（alternatives） | 多送 `current_software`、`pain_points`、`must_keep`；回 `current`、`keep_current` |
| `get_install_guide` | 不呼叫 | `events`（install_guide） | 只回實跑過的步驟；沿用或新發 `rec_id` |
| `report_outcome` | 不呼叫 | `events`（outcome）、`reverify_queue` | 帶有效 `rec_id` 才計分；同一回報只記一次 |
| `submit_software` | 不呼叫（Worker 不抓網址） | `submissions`、`events`（submit） | 只收 GitHub repo；重送就是查進度 |

每個推薦與安裝指南都帶 `rec_id`、`matched_by`、`how_we_know`、`evidence_url`（`find_*` 在每個 pick 上；`get_install_guide` 在頂層，`matched_by` 固定是 `rules`，因為步驟是錄下來的實跑紀錄，沒經過模型）。這些欄位都由程式從資料產生。

### `find_software`、`find_alternatives` 怎麼配對（architecture F.2）

1. **硬條件（程式）**：只留有實跑過安裝步驟的（`install.<os>` 的 basis 是 `replayed` 或 `human`）；類別、`budget: free_only` → `pricing = free`、`must_run_locally` → `processing = local`、不需網路、不需 API key；作業系統要在 `platforms` 或已驗證過。只在別的 OS 驗證過的留下，但卡片與回應都會標明。`find_alternatives` 另外把使用者目前的工具（依 slug 或名稱比對到目錄裡的那筆）排除。
2. **候選卡**：全部合格的卡（≤60 張，依 slug 排，不給模型看熱門度順序）。超過 60 張先取寶藏分數前 60（之後換 BM25）。
3. **一次 `muse-spark-1.3`**（Responses API、`store: false`、`reasoning.effort: low`、strict JSON schema；slug 欄位的 enum 就是這次的候選）：解析需求成條件、選 1–3 個、每個理由引用一個卡片欄位與原值、取捨、和知名工具比、最好的免費選項、「內建就夠」、最多 1 個追問。模型固定在程式裡，不能換成 `-contributor`（使用者需求是私人資料）。`find_alternatives` 用同一份 prompt，**後面加 4 條規則**（`ALTERNATIVES_RULES`：只選做同一件事、至少解決一個痛點、保留 `must_keep` 的；和目前的工具比較；`keep_current`；解析出的痛點）；`find_software` 的 prompt 與 schema 不變。
4. **守門（程式）**：slug 必須在候選裡；理由引用的值要真的出現在該欄位；理由不能和卡片矛盾（離線、免費、開源、在某 OS 驗證過、不需 key、不需 GPU）。不合的理由丟掉，沒有理由的推薦丟掉。
5. **退回規則**：模型關掉、沒有 key、超出預算、逾時、HTTP 錯誤、輸出壞掉、或推薦全被守門擋掉 → 依「（`find_alternatives`）卡片的 `alternatives_to` 提到目前的工具 → 需求關鍵字命中 → 在使用者 OS 驗證過 → 寶藏分數」排序，理由用模板（只從欄位產生），標 `matched_by: "rules"`、`degraded: true`、`degraded_reason`。規則模式不判斷 `keep_current`（回 `null`）。

`find_alternatives` 的 `current`：`matched_slug` 是目錄裡的那筆（有的話，且不會出現在 picks）；`known` 是「目錄有它，或某張卡的 `alternatives_to` 提到它」。`keep_current.recommended: true` 表示沒有一個候選明顯比較好，這時 picks 可能是空的。

### `report_outcome`

- 7 個 stage 存成 `(stage, success)`，對照寫在 `migrations/0001_init.sql` 開頭；`satisfaction` 存成 1／0／-1。
- **計分**：`rec_id` 必須是 pickfit 7 天內發給這個 slug 的（`find_*` 推薦過它，或 `get_install_guide` 給過它的指南）。合格的回報保留 `rec_id`，不合格的存成 `rec_id = NULL`，所以「`rec_id IS NOT NULL` ＝ 計分」。回 `counted_in_score` 與 `not_counted_reason`。
- **去重**：同一個 `(rec_id, slug, stage, success)` 只記一次，重送回 `deduplicated: true`、同一個 `report_id`（`0002` 把 `success` 加進唯一索引，否則「先失敗、修好後成功」的第二筆會被當成重複）。
- **重驗**：`install_failed`／`first_run_failed`＋有效 `rec_id`＋知道 OS（參數或推薦時的 OS）＋有 `error_excerpt` → 寫進 `reverify_queue`；同一 `(slug, os)` 還在排隊就回 `already_queued`，做完（`done_at` 有值）後再失敗會重新排。
- **個資**：`error_excerpt` 與 `note` 存之前先過 `src/scrub.ts`（家目錄的使用者名稱、email、`token=`／`Bearer` 之類的值、長串像金鑰的字元），`error_excerpt` 留最後 500 字元、`note` 最多 280 字元。`note` 是不可信的輸入：只給人看，**不出現在任何回應，也不送進模型**。

### `submit_software`

- 只收 `github.com/<owner>/<repo>`（`.git`、大小寫、`/tree/...` 都正規化成 `https://github.com/owner/repo`）；其他網域、`/topics/...` 之類不是 repo 的路徑回工具錯誤。Threads 連結還沒做。
- 一個 repo 一列（`submissions.url` 唯一）；重送只讀狀態（`already_submitted: true`）。已在目錄裡的 repo 直接回 `listed` 與 slug，不新增一列。
- 每小時新提交上限 `SUBMIT_HOURLY_CAP`（預設 20，全體共用；不存 IP，所以沒辦法分人計）。
- Worker 只排隊，處理在管線：`pickfit watch`（P5.2）讀 `status = 'queued'` 的列，更新 `status`（`reading` → `verifying` → `listed`／`listed_unverified`／`rejected`）、`slug`、`reason`、`updated_at`。

## 花費上限與 `degraded`

Worker 自己的帳在 D1 `meta_budget`（和本機管線的 `~/.pickfit/ledger.sqlite` 分開）：每日 $3、總額 $40（`META_DAILY_CAP_USD`、`META_TOTAL_CAP_USD`）。`find_*` 呼叫前先用「這次最多花多少」檢查兩個上限，超過就不呼叫、回 `degraded: true`、`degraded_reason: "over_budget"`；呼叫後記實際花費；逾時的呼叫照上限計。查不到 D1 就不呼叫模型（`budget_unavailable`）。

本機實測（假資料 4–5 張卡，10/28）：`find_software` 約 $0.009、7 秒；`find_alternatives` 約 $0.009–0.011、6–7 秒。

## 不快取

`find_software`、`find_alternatives` 每次呼叫都重新做一次完整配對（硬條件 → 候選卡 → 一次 `muse-spark-1.3` → 守門），Worker 裡沒有任何結果快取；同樣的請求送兩次就是兩次模型呼叫、兩個不同的 `rec_id`、兩列 `events`（`test/deployments.test.ts` 有測）。其他層也不快取：

- MCP：2026-07-28 版只有 `tools/list`、`server/discover` 等清單類結果帶快取欄位（SDK 預設 `ttlMs: 0`、`private`）；`tools/call` 的結果沒有。
- HTTP：`/mcp` 的每個回應都帶 `Cache-Control: no-store`。
- Meta：請求帶 `store: false`。Meta 可能把重複的 prompt 前段算成 cached input token（計價較低），那只是重用輸入，答案每次都重新產生，所以同樣的請求可能得到不同的 picks。

## 評測部署（凍結、唯讀）

同一份程式與資料，只靠 `wrangler.jsonc` 的設定分出不同部署（不改程式碼）：

| 設定 | 作用 |
|---|---|
| `TOOLS` | 不設或 `all`：5 個工具。`readonly`：只註冊 `find_software`、`find_alternatives`、`get_install_guide`；server instructions 與工具說明不再提到另外兩個，呼叫它們回 JSON-RPC `-32602 Tool … not found`。其他任何值也當 `readonly`（打錯字不會意外打開寫入工具） |
| `MATCH_MODE` | `model` 或 `off`（規則排序，不呼叫 Meta） |
| `META_DAILY_CAP_USD`、`META_TOTAL_CAP_USD` | 這個部署自己的 Meta 上限；算的是這個部署的 D1 `meta_budget` |

`wrangler.jsonc` 已有兩個範本（`env` 區塊；wrangler 不會把頂層的 `vars`、`d1_databases` 繼承進 env，所以每個都完整列出）：

- `eval`：`TOOLS=readonly`、`MATCH_MODE=model`、每日 $3、總額 $10、自己的 D1 `pickfit-eval`。
- `eval-rules`：`TOOLS=readonly`、`MATCH_MODE=off`、上限都是 0、自己的 D1 `pickfit-eval-rules`。

**凍結**：Worker 的資料是部署時打包進去的索引，所以評測期間不要再對該 env 跑 `pickfit publish --env …`；公開的 server 照常更新不影響它。兩個 arm 要從同一個 commit 部署；`GET /` 會回 `data_sha256`、`index_built_at`、`tools`、`match_mode`，兩邊的 `data_sha256` 相同就是同一份資料。

**`rec_id` 對帳**：三個唯讀工具的每個回應都有 `rec_id`，也都寫進該部署的 `events`：`find`／`alternatives` 一個 `rec_id` 一列（唯一索引）；`get_install_guide` 若帶了推薦的 `rec_id` 就沿用（用 `rec_id`＋`slug`＋`type = 'install_guide'` 對），沒帶就新發一個。`events` 存的是條件與推薦的 slug（`results`），不是整個回應、也沒有使用者原話；要比對完整回應，客戶端那邊要自己留 transcript。寫 D1 在回應送出後（`waitUntil`），失敗不會讓回應失敗，但會在 Workers log 記 `d1_write_failed` 與 `rec_id`。

部署評測 env（在第一次公開部署的檢查清單之外另做；下面以 `eval` 為例，`eval-rules` 一樣但不用設金鑰）：

1. `npx wrangler d1 create pickfit-eval`，把 id 填進 `env.eval.d1_databases`；`npx wrangler d1 migrations apply pickfit-eval --env eval --remote`。
2. `env.eval.vars.ALLOWED_HOSTS` 填 `pickfit-mcp-eval.<workers.dev 子網域>.workers.dev`（env 部署的 Worker 名稱是 `pickfit-mcp-<env>`），commit。
3. `uv run pickfit publish --dry-run --env eval`（會印出這個 env 的 `TOOLS`、`MATCH_MODE`、上限），沒問題再 `uv run pickfit publish --env eval`。
4. 金鑰：把文末第 6 步的指令改成 `npx wrangler secret put MODEL_API_KEY --env eval`。
5. 確認 `GET /` 的 `tools` 是 `readonly`、`data_sha256` 和另一個 arm 相同；`tools/list` 只有 3 個工具。

## D1（`migrations/`）

`0001_init.sql`：`events`、`submissions`、`reverify_queue`、`meta_budget`。`0002_outcome_once_by_result.sql`：回報的去重索引加上 `success`。不記 IP；`events.need` 只存條件（agent 給的參數＋模型解析出的 `task`、`search_terms`、痛點等），不存使用者原話。

## 部署檢查清單

**先決條件**：`data/software/` 有真的 profile 並已 commit（P2.6），而且念誠同意部署。下面的指令都在**主 checkout** 的 `worker/` 下跑（`.env` 在主 checkout 根目錄）。

1. **建 D1**：`npx wrangler d1 create pickfit`，把輸出的 `database_id` 填進 `wrangler.jsonc`（取代全 0 的佔位），commit。
2. **遠端建表**：`npx wrangler d1 migrations apply pickfit --remote`（`0001`、`0002` 都要套；之後 `migrations/` 有新檔就再跑一次，**`pickfit publish` 不會幫你跑**）。
3. **`ALLOWED_HOSTS`**：在 `wrangler.jsonc` 的 `vars` 填 `pickfit-mcp.<workers.dev 子網域>.workers.dev`（子網域就是 P0.5 hello 部署用的那個，dashboard 的 Workers & Pages 也看得到），commit。沒填的話遠端每個請求都是 403，`pickfit publish` 也會拒絕部署。
4. **先 dry run**：在 repo 根目錄 `uv run pickfit publish --dry-run`。它會驗 `data/software/` 每一筆、確認不是 fixture、資料都已 commit、`wrangler.jsonc` 已填好；任何一項不過就列出問題、exit 1。
5. **部署**：`uv run pickfit publish`。它用真資料重建 `worker/src/generated/index.json`，再跑 `npx wrangler deploy`。（之後本機要回到假資料：`npm run build:index -- --data test/fixtures/software`。）
6. **設金鑰**（第一次部署後；在設好之前，`find_*` 會以 `no_api_key` 退回規則排序）。從 `.env` 只讀這一個值、經 pipe 交給 wrangler，不會印在終端機：

   ```bash
   uv run --project .. python -c "import sys; from pickfit.env import read_env; sys.stdout.write(read_env(['MODEL_API_KEY'])['MODEL_API_KEY'])" | npx wrangler secret put MODEL_API_KEY
   ```

7. **確認**：`curl https://<host>/` 的 `entries` 等於 dry run 的筆數；`claude mcp add --transport http pickfit https://<host>/mcp`（用 `env -i` 啟動，見上）看得到 5 個工具；問一題，回應的 `matched_by` 是 `muse-spark-1.3`。
8. **緊急關模型**：`npx wrangler deploy --var MATCH_MODE:off`，或把 `META_DAILY_CAP_USD` 調成 `0` 再部署；兩種都會讓 `find_*` 改用規則、標 `degraded`。
