# pickfit MCP server（Cloudflare Worker）

無狀態的 Streamable HTTP MCP server（官方 TypeScript SDK v2 的 `createMcpHandler`，新舊兩代協定都收）。目前有 `find_software`、`get_install_guide` 兩個工具；`find_alternatives`、`report_outcome`、`submit_software` 是 P4.5。**還沒部署**，只在本機跑。

## 怎麼跑

```bash
cd worker
npm install
npm run build:index -- --data test/fixtures/software   # 還沒有真資料：先用 5 筆假 profile
npm run db:migrate:local                                # 本機 D1 建表
grep -E '^MODEL_API_KEY=' ../.env > .dev.vars           # 只取這一個變數；.dev.vars 已 gitignore
npm run dev                                             # http://127.0.0.1:8787/mcp
```

- 關掉模型：`npx wrangler dev --var MATCH_MODE:off`（或不放 `MODEL_API_KEY`）。
- 測試：`npm test`（先用 `scripts/build_index.py` 從 fixture 建索引；D1 用 `node:sqlite` 跑同一份 migration；Meta 回應是假的，不打 API）。型別：`npm run typecheck`。
- 真資料：`npm run build:index`（讀 `data/software/*.json`，任何一筆不合 `software.v1` 就失敗、不寫索引）。

Claude Code 連本機（桌面 app 的 shell 要用 `env -i`，否則會繼承 `ANTHROPIC_BASE_URL`）：

```bash
echo '{"mcpServers":{"pickfit":{"type":"http","url":"http://127.0.0.1:8787/mcp"}}}' > /tmp/pickfit-mcp.json
env -i HOME="$HOME" PATH="$PATH" ANTHROPIC_API_KEY=… claude -p "…" \
  --strict-mcp-config --mcp-config /tmp/pickfit-mcp.json \
  --allowedTools "mcp__pickfit__find_software,mcp__pickfit__get_install_guide"
```

## `find_software` 怎麼配對（architecture F.2）

1. **硬條件（程式）**：只留有實跑過安裝步驟的（`install.<os>` 的 basis 是 `replayed` 或 `human`）；類別、`budget: free_only` → `pricing = free`、`must_run_locally` → `processing = local`、不需網路、不需 API key；作業系統要在 `platforms` 或已驗證過。只在別的 OS 驗證過的留下，但卡片與回應都會標明。
2. **候選卡**：全部合格的卡（≤60 張，依 slug 排，不給模型看熱門度順序）。超過 60 張先取寶藏分數前 60（之後換 BM25）。
3. **一次 `muse-spark-1.3`**（Responses API、`store: false`、`reasoning.effort: low`、strict JSON schema；slug 欄位的 enum 就是這次的候選）：解析需求成條件、選 1–3 個、每個理由引用一個卡片欄位與原值、取捨、和知名工具比、最好的免費選項、「內建就夠」、最多 1 個追問。模型固定在程式裡，不能換成 `-contributor`（使用者需求是私人資料）。
4. **守門（程式）**：slug 必須在候選裡；理由引用的值要真的出現在該欄位；理由不能和卡片矛盾（離線、免費、開源、在某 OS 驗證過、不需 key、不需 GPU）。不合的理由丟掉，沒有理由的推薦丟掉。
5. **退回規則**：模型關掉、沒有 key、超出預算、逾時、HTTP 錯誤、輸出壞掉、或推薦全被守門擋掉 → 依「需求關鍵字命中 → 在使用者 OS 驗證過 → 寶藏分數」排序，理由用模板（只從欄位產生），標 `matched_by: "rules"`、`degraded: true`、`degraded_reason`。

`how_we_know`、`evidence_url`、`verification` 都由程式從資料產生，不經過模型。

## 花費上限

Worker 自己的帳在 D1 `meta_budget`（和本機管線的 `~/.pickfit/ledger.sqlite` 分開）：每日 $3、總額 $40（`META_DAILY_CAP_USD`、`META_TOTAL_CAP_USD`）。呼叫前先用「這次最多花多少」檢查兩個上限，呼叫後記實際花費；逾時的呼叫照上限計。查不到 D1 就不呼叫模型。

本機實測（假資料 3–4 張卡）：每次約 2,000–2,300 input、1,800–2,100 output token（推理 1,200–1,700），約 $0.011、8–11 秒。

## D1（`migrations/0001_init.sql`）

`events`、`submissions`、`reverify_queue`、`meta_budget`。不記 IP；`events.need` 只存條件（agent 給的參數＋模型解析出的 `task`、`search_terms` 等），不存使用者原話。`report_outcome` 的 7 個 stage 存成 `(stage, success)`，對照寫在 migration 開頭。
