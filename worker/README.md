# pickfit MCP server（Cloudflare Worker）

無狀態的 Streamable HTTP MCP server（官方 TypeScript SDK v2 的 `createMcpHandler`，新舊兩代協定都收）。5 個工具：`find_software`、`find_alternatives`、`get_install_guide`、`report_outcome`、`submit_software`（`TOOLS=readonly` 時只有前 3 個，見「評測部署」）。已部署在 `https://pickfit-mcp.ncchen99.workers.dev/mcp`（10/29 起）；部署步驟見文末的檢查清單。

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
- 輸出格式：`test/conformance.test.ts` 透過 MCP server 呼叫 5 個工具的每一種回應，用 SDK 自己的驗證器（`CfWorkerJsonSchemaValidator`）檢查 `structuredContent` 符合 `tools/list` 公布的 `outputSchema`。schema 是 `additionalProperties: false`，所以工具多回一個欄位、`server.ts` 的 zod 沒跟著加，這個測試就會失敗；嚴格驗證的客戶端遇到這種回應會整個拒收。
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
3. **一次 `muse-spark-1.3`**（Responses API、`store: false`、`reasoning.effort: low`、strict JSON schema；slug 欄位的 enum 就是這次的候選）：解析需求成條件、選 1–3 個、每個理由引用一個卡片欄位與原值、取捨、和知名工具比、最好的免費選項、「內建就夠」、不在資料裡的知名免費工具（`well_known_option`，見下）、最多 1 個追問。模型固定在程式裡，不能換成 `-contributor`（使用者需求是私人資料）。`find_alternatives` 用同一份 prompt，**後面加 4 條規則**（`ALTERNATIVES_RULES`：只選做同一件事、至少解決一個痛點、保留 `must_keep` 的；和目前的工具比較；`keep_current`；解析出的痛點）；`find_software` 的 prompt 與 schema 不變。
4. **守門（程式）**：slug 必須在候選裡；理由引用的值要真的出現在該欄位；理由不能和卡片矛盾（離線、免費、開源、在某 OS 驗證過、不需 key、不需 GPU）。不合的理由丟掉，沒有理由的推薦丟掉。`well_known_option` 另有自己的檢查（見下）。
5. **退回規則**：模型關掉、沒有 key、超出預算、逾時、HTTP 錯誤（重試一次後仍失敗，見下面「重試」）、輸出壞掉、或推薦全被守門擋掉 → 依「（`find_alternatives`）卡片的 `alternatives_to` 提到目前的工具 → 需求關鍵字命中 → 在使用者 OS 驗證過 → 寶藏分數」排序，理由用模板（只從欄位產生），標 `matched_by: "rules"`、`degraded: true`、`degraded_reason`。規則模式不判斷 `keep_current`（回 `null`）。

`find_alternatives` 的 `current`：`matched_slug` 是目錄裡的那筆（有的話，且不會出現在 picks）；`known` 是「目錄有它，或某張卡的 `alternatives_to` 提到它」。`keep_current.recommended: true` 表示沒有一個候選明顯比較好，這時 picks 可能是空的。

### `well_known_option`：不在資料裡的知名免費工具（未驗證）

資料只收 ≤300 星的長尾工具。有名的免費工具（或大廠產品的免費方案）真的比較適合某個人時，agent 只看 picks 就會錯過；中立也包括「不用付費」「內建就夠」（brief 第 2 節）。所以模型可以在 picks 之外**多講一個**，但 picks、`best_free` 照舊只從候選卡選。

- **prompt 第 10 條**：通常是 null。只有當某個知名的免費工具（或知名產品的免費方案）比每個 pick 都適合、或沒有候選適合時，給 `well_known_name`（常用名稱）與 `well_known_why`（一句話，要說它免費或哪個免費方案就夠、為什麼比較適合）。它要符合 `<request>` 的每個條件（OS、預算、離線）。關於它的事實來自模型自己的知識（和第 7、9 條講的工具一樣），只能寫有把握的；不能說它被驗證或測試過；知名不是理由；不能是候選、使用者正在用的工具、或 `no_install_option` 講的那個。
- **回應**：`well_known_option: { name, why, verified: false, how_we_know }` 或 `null`。`how_we_know` 由程式產生，說明是誰提的、pickfit 沒裝過、沒有安裝指南（`get_install_guide` 不認得它），以及沒查過的事：價格，加上使用者給了的條件（OS、離線）。
- **程式能查的**（不合就整個丟掉，不截斷、不影響其他欄位）：
  - 名稱：`None`、`N/A` 之類的佔位字當作沒給；其餘要是單純的名稱（≤60 字、≤5 個字、只有字母數字空白和 `. + _ ' -`，不是網域、不是指令、沒有控制或 bidi 字元），否則 `not_a_name`。
  - 不是目錄裡的任何一筆，名稱寫法不同也算（`toolKey` 去掉 CLI、app、agent、engine 等通用字與版本號後，相同、或 4 字以上時一個是另一個的開頭；不比包含，因為 faster-whisper 不是 Whisper）：在目錄裡就該是 pick，或已被硬條件擋掉，不能改口說成「沒驗證過的知名工具」。
  - 不是 `find_alternatives` 的目前工具：同樣的比對，對使用者給的 `current_software` 和模型解析的 `need.current_tool` 都比。
  - `why`：≤300 字、純文字（沒有網址、網域、安裝指令、反引號、markdown、換行），要明確說它免費或開源（`not free`、`no free tier`、`free trial`、`hassle-free`、只限個人使用都不算），不能說 verified／tested／installed／checked／confirmed／vetted／proven／audited 或提到 pickfit。不截成一句，以免把模型自己寫的但書剪掉。
  - `events.need.well_known` 記模型給的名稱與丟掉的原因（`dropped`；留下的是 `null`），沒給就是 `null`。`not_a_name` 只記原因、不記文字（可能是從需求抄來的）。整個答案被守門擋掉（`guard_rejected_all`）時也記，`dropped` 是 `answer_rejected`。
- **程式查不到的**：工具存不存在、是不是真的免費、合不合 OS 與離線、是不是真的比較適合。所以只放一句話、標 `verified: false`，工具說明也要 agent 這樣轉告使用者。
- **沒有模型時**：規則模式永遠是 `null`（規則只認得資料）。沒有候選時不呼叫模型，`coverage_note` 多一句「pickfit 只收比較不知名的工具，知名的可能仍適合」。
- `no_install_option` 本來就是模型的一般知識；outputSchema 的說明現在寫明 pickfit 沒查過。server instructions 也多一句：`well_known_option` 沒經 pickfit 驗證，轉述時要說。

實測（10/29，真資料 96 筆，8 題自擬的需求，不是評測題；`muse-spark-1.3` 8 次 $0.16，記在共用帳本）：3 題有提，5 題是 null，沒有編造的工具。

| 需求 | picks | `well_known_option` |
|---|---|---|
| Mac 上免費、離線、好裝的本機 LLM 聊天 | xyntetik-runner | Ollama（句子說它「附帶模型」，不對：模型要另外下載。這就是要標未驗證的原因） |
| 終端機格式化、篩選 curl 的 JSON | 無 | jq（`no_install_option` 另給 `python3 -m json.tool`） |
| shell 裡模糊搜尋檔案與指令歷史 | 無 | fzf |
| 安裝前檢查 MCP 設定的權限 | patient-zero | null |
| 離線轉錄會議錄音、Linux GPU 上開 OpenAI 相容 API、換掉 Ollama、看誰佔用 port（`no_install_option` 給 `lsof`） | 有 | null |

模型偏保守：GPU 伺服器那題沒提 vLLM、換掉 Ollama 那題沒提 llama.cpp。寧可少提，不要每題都推知名工具蓋過長尾的 picks。

### 知名工具的參考紀錄（`well_known`，10/29 試做，未決定是否併入）

發現只收 ≤300 星的長尾工具，所以知名的免費工具永遠不會是 pick。參考紀錄讓少數知名工具也有實跑過的安裝步驟、可以被選，但和長尾分開標示。

- **怎麼選（規則，不手挑）**：`pickfit.discover.well_known`。Homebrew core（不含 tap）依過去 365 天 install-on-request 排名，前 1000 名（約每年 ≥9.5k 次）且原始碼在 GitHub 的，當成 candidate 存進 pipeline DB（query `well_known:homebrew`），安裝數證據另存在 `well_known` 表。類別照常由 prescreen 與抽取決定（類別定義），每類取排名最前的 N 個。
- **紀錄**：`software.v1` 多一個選填的 `well_known`（basis、package、rank、count、門檻、期間、來源網址、查證時間）；有它的紀錄 `scores.treasure.excluded = "well_known"`，**永遠不是寶藏**，不論分數。兩個欄位是 null 時不寫進檔案，長尾紀錄不會變。索引帶 `well_known: {package, rank, count, period_end}` 或 `null`。
- **Worker**：卡片多 `well_known` 欄位；prompt 第 3 條說只有比長尾候選更適合時才選它，而且最多一個；守門與規則模式都只留一個。pick 帶 `well_known` 物件，`how_we_know` 多一句 Homebrew 排名。超過 60 張卡時參考紀錄一定留著（寶藏排序一定會把它們排掉）。

試做結果（排名前 700 名掃完；花費 Meta $0.47、Baseten $1.27）：

| 工具 | Homebrew 排名 | 驗證 | 品質 | 抽取的缺口 |
|---|---|---|---|---|
| ollama | 23 | install（沙盒沒有 root，改解壓 tarball 到 `~/.local`） | 64.9 | 價格 null、`processing: hybrid` |
| llama.cpp | 72 | inference | 89.6 | 價格 null、平台空、`hybrid` |
| whisper（openai-whisper） | 158 | install（`uv tool install`） | 52.3 | 價格 null、平台空 |
| whisper.cpp | 219 | 未驗證：抽取說只支援 macOS，Linux 沙盒不收 | 69.0（上限） | 價格 null |

llmfit（273）與 goose（469）prescreen 判 local_ai，但抽取判 dev_cli，所以不算。700–1000 名沒有掃；從名稱看只有 onnxruntime（函式庫）與 aider（coding agent）。

真實配對（10 題自擬需求，不是評測題，$0.22）：**參考紀錄 0 次被選**，即使它們在卡片裡（Linux 本機聊天有 ollama、llama.cpp；Linux 轉錄有 whisper），模型都選長尾工具。抽取沒寫價格，所以 `budget: free_only` 一律擋掉它們；ollama、llama.cpp 是 `hybrid`，`must_run_locally` 也擋掉。副作用：「Mac 上免費離線的本機聊天」這題，模型在 `well_known_option` 提了 Ollama，但 Ollama 現在是目錄裡的一筆，守門以 `listed_in_pickfit` 丟掉，使用者連一句未驗證的提及都沒有了。

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

### 重試（暫時性錯誤只重試一次）

10/29 重新部署後，Meta 曾有幾分鐘對 `muse-spark-1.3` 時好時壞地回 404「model not found」，當時 `find_software` 一遇錯就退回規則。現在 `src/meta.ts` 的 `callMeta` 遇到下面三種狀態會**再試一次**：

- `429`；
- 任何 `5xx`；
- `404` 且內容說模型不存在（`model_not_found`，或 `model … not found／does not exist`）。

其他狀態不重試：`400`、`401`、`403`、路徑不對的 `404` 等。逾時、連線錯誤也不重試。Meta 已經回了答案的也不重試，不論輸出壞掉、`incomplete`，或推薦全被守門擋掉。

- **等待**：200–800 ms 隨機。Meta 給的 `Retry-After`（或 `retry-after-ms`）在 5 秒以內就照它等；要求等更久就不重試，直接退回規則。
- **時限**：兩次請求加上中間的等待都在 `META_TIMEOUT_MS` 之內。第二次的逾時是剩下的時間；剩不到 10 秒（一次配對約 6–8 秒）就不重試，照原本的方式退回規則。
- **花費**：HTTP 錯誤沒有 usage，記 $0；只記有回 usage 的那次。整個 `find_*` 仍只寫一筆 `meta_budget`（`calls + 1`）。重試前不再查一次上限，因為失敗的那次沒有花到錢。
- **紀錄**：
  - `degraded_reason` 維持 `model_http`。
  - 回應多兩個欄位：`model_attempts`（送給 Meta 幾次；0 表示沒用模型，2 表示重試過）、`model_http_status`（`degraded_reason` 是 `model_http` 時，Meta 最後一次回的狀態碼）。
  - `events` 多三欄（`0003`）：`degraded_reason`、`model_attempts`、`model_statuses`（每次的狀態碼，例如 `[503, 200]`；沒拿到回應的記 `null`）。
  - Workers log 每次重試記一行 `meta_retry`，內容是 `status`、`wait_ms`、`left_ms`。

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

- `eval`：`TOOLS=readonly`、`MATCH_MODE=model`、每日 $10、總額 $10（評測協定登記的上限；每日上限設低會讓評測中途變成 `degraded`）、自己的 D1 `pickfit-eval`。
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

`0001_init.sql`：`events`、`submissions`、`reverify_queue`、`meta_budget`。`0002_outcome_once_by_result.sql`：回報的去重索引加上 `success`。`0003_model_attempts.sql`：`events` 加 `degraded_reason`、`model_attempts`、`model_statuses`。**一定要先套 `0003` 再部署這版**，否則每一筆事件都寫不進去：

- `report_outcome` 會整個失敗：它等事件寫完才回應，寫入錯誤會讓每次呼叫都回錯誤。
- `find_*`、`get_install_guide`、`submit_software` 照常回應，但事件寫入失敗，只在 Workers log 留下 `d1_write_failed`。`rec_id` 不會進 `events`，之後拿這些 `rec_id` 回報也不能計分。

不記 IP；`events.need` 只存條件（agent 給的參數＋模型解析出的 `task`、`search_terms`、痛點等），不存使用者原話。

## 部署檢查清單

**先決條件**：`data/software/` 有真的 profile 並已 commit（P2.6），而且念誠同意部署。下面的指令都在**主 checkout** 的 `worker/` 下跑（`.env` 在主 checkout 根目錄）。

1. **建 D1**：`npx wrangler d1 create pickfit`，把輸出的 `database_id` 填進 `wrangler.jsonc`（取代全 0 的佔位），commit。
2. **遠端建表**：`npx wrangler d1 migrations apply pickfit --remote`（`0001`–`0003` 都要套，而且**要在部署這版之前套**；之後 `migrations/` 有新檔，也是先套再部署。**`pickfit publish` 不會幫你跑**；`eval` 等 env 的 D1 也要各自套）。
3. **`ALLOWED_HOSTS`**：在 `wrangler.jsonc` 的 `vars` 填 `pickfit-mcp.<workers.dev 子網域>.workers.dev`（子網域就是 P0.5 hello 部署用的那個，dashboard 的 Workers & Pages 也看得到），commit。沒填的話遠端每個請求都是 403，`pickfit publish` 也會拒絕部署。
4. **先 dry run**：在 repo 根目錄 `uv run pickfit publish --dry-run`。它會驗 `data/software/` 每一筆、確認不是 fixture、資料都已 commit、`wrangler.jsonc` 已填好；任何一項不過就列出問題、exit 1。
5. **部署**：`uv run pickfit publish`。它用真資料重建 `worker/src/generated/index.json`，再跑 `npx wrangler deploy`。（之後本機要回到假資料：`npm run build:index -- --data test/fixtures/software`。）
6. **設金鑰**（第一次部署後；在設好之前，`find_*` 會以 `no_api_key` 退回規則排序）。從 `.env` 只讀這一個值、經 pipe 交給 wrangler，不會印在終端機：

   ```bash
   uv run --project .. python -c "import sys; from pickfit.env import read_env; sys.stdout.write(read_env(['MODEL_API_KEY'])['MODEL_API_KEY'])" | npx wrangler secret put MODEL_API_KEY
   ```

7. **確認**：`curl https://<host>/` 的 `entries` 等於 dry run 的筆數；`claude mcp add --transport http pickfit https://<host>/mcp`（用 `env -i` 啟動，見上）看得到 5 個工具；問一題，回應的 `matched_by` 是 `muse-spark-1.3`。
8. **緊急關模型**：`npx wrangler deploy --var MATCH_MODE:off`，或把 `META_DAILY_CAP_USD` 調成 `0` 再部署；兩種都會讓 `find_*` 改用規則、標 `degraded`。
