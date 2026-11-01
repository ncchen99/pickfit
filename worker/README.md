# pickfit MCP server（Cloudflare Worker）

無狀態的 Streamable HTTP MCP server（官方 TypeScript SDK v2 的 `createMcpHandler`，新舊兩代協定都收）。5 個工具：`find_software`、`find_alternatives`、`get_install_guide`、`report_outcome`、`submit_software`（`TOOLS=readonly` 時只有前 3 個，見「評測部署」）。已部署在 `https://pickfit-mcp.ncchen99.workers.dev/mcp`（10/29 起）；部署步驟見文末的檢查清單。同一個 Worker 也提供產品網頁（瀏覽器開 `/`，見「產品網頁」）。

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
| `find_software` | `muse-spark-1.3` 一次；合格超過 60 款時先多一次小呼叫取英文關鍵字（超預算或失敗退回規則） | `events`（find） | 見下節 |
| `find_alternatives` | 同上，同一條路徑 | `events`（alternatives） | 多送 `current_software`、`pain_points`、`must_keep`；回 `current`、`keep_current` |
| `get_install_guide` | 不呼叫 | `events`（install_guide） | 只回實跑過的步驟；沿用或新發 `rec_id` |
| `report_outcome` | 不呼叫 | `events`（outcome）、`reverify_queue` | 帶有效 `rec_id` 才計分；同一回報只記一次 |
| `submit_software` | 不呼叫（Worker 不抓網址） | `submissions`、`events`（submit） | 只收 GitHub repo；重送就是查進度 |

每個推薦與安裝指南都帶 `rec_id`、`matched_by`、`how_we_know`、`evidence_url`（`find_*` 在每個 pick 上；`get_install_guide` 在頂層，`matched_by` 固定是 `rules`，因為步驟是錄下來的實跑紀錄，沒經過模型）。這些欄位都由程式從資料產生。

GUI 桌面 app 的實跑另帶 `verification.gui`（`find_*` 的 pick 與 `get_install_guide` 都有；其他軟體是 `null`）：`tier`（`window`＝出現 app 自己行程的視窗；`ui_rendered`＝另一個模型看截圖判定 app 自己的介面畫出來了）、`screen`（模型看到的畫面：主畫面、首次設定畫面、登入牆等）、`display`（虛擬螢幕）、`launch_offline`（新沙盒重播時斷網也啟動成功）。`how_we_know` 會照實寫出看到了什麼，並註明沒用過任何功能；`level` 一律維持 `install`，啟動成功不算 function。視窗標題是 app 自己設定的文字，不進索引。

### `find_software`、`find_alternatives` 怎麼配對（architecture F.2）

1. **硬條件（程式）**：只留有實跑過安裝步驟的（`install.<os>` 的 basis 是 `replayed` 或 `human`）；類別、`budget: free_only` → `pricing = free`、`must_run_locally` → `processing = local`、不需網路、不需 API key；作業系統要在 `platforms` 或已驗證過。只在別的 OS 驗證過的留下，但卡片與回應都會標明。`verified_on_user_os` 要 OS 相同；請求有給 `arch` 時，跑的 CPU 架構也要相同，所以只在 arm64 Mac 跑過的，對 Intel Mac 是 `false`，並在取捨裡寫明。沒給 `arch` 就只看 OS，回應的 `verification.arch` 和 `get_install_guide` 的 note 會寫出實際跑的架構。`find_alternatives` 另外把使用者目前的工具（依 slug 或名稱比對到目錄裡的那筆）排除。
2. **候選卡**：全部合格的卡（≤60 張，依 slug 排，不給模型看熱門度順序）。超過 60 張時（dev_cli、local_ai、不分類別幾乎都會）改成**先看相關度**（`src/filter.ts`、`src/relevance.ts`）：
   - **英文關鍵字**（`src/expand.ts`）：先送一次小的 `muse-spark-1.3`（`store: false`、effort `minimal`、strict schema、最多 600 個輸出 token），把需求變成 6–15 個英文關鍵字：別的語言就是翻譯，英文就是同義詞。實測中位數 1.4 秒、約 $0.0012。最多等 5 秒；失敗、逾時、超預算、模型關掉時，改用下面「規則的相關度」挑卡（什麼字都對不到才是寶藏分數排序）。關鍵字只用來挑卡，模型讀到的仍是使用者原本的需求；不寫進 D1。
   - **BM25**：需求原本的字加關鍵字，對卡片上的名稱（slug）、tags、summary、`alternatives_to`、use cases、`why_worth_it`、MCP 握手列出的工具名算 BM25（欄位加權：名稱 3、tags 2、summary 與 alternatives 1.5、其他 1；小寫、拆 camelCase／snake_case、去停用字、簡單去字尾）。
   - **挑 60 張**：（`find_alternatives`）`alternatives_to` 提到目前工具的先放，再放 BM25 最高的，合計最多 50 張；剩下 10 張以上給其餘寶藏分數最高的，好的通用選項不會因為沒對到字就消失。沒有任何字對到就全照寶藏分數。硬條件完全不放寬。
   - 回應的 `coverage_note` 說明幾張是因相關度、幾張是因寶藏分數；`events.need.shortlist` 記 `by_relevance`（張數）與關鍵字呼叫的結果（`ok`、`model_off`、`model_timeout`…），不記任何字。
   - **規則的相關度**（`rulesRelevance`，只在沒有關鍵字時用：規則模式、關鍵字呼叫失敗、規則排序）：一樣的 BM25，但（1）通用字（`src/lexicon.ts` 的 `GENERIC_WORDS`，加上 OS 名稱，因為 OS 是硬條件）只算 IDF 的 0.2；（2）分數乘上「卡片對到的需求字權重 ÷ 需求字總權重」，對到越多具體需求的越前面；（3）中文用 `ZH_EN` 小字典（約 260 個常見軟體與功能詞，最長的詞優先）轉成英文，不呼叫任何模型；（4）否定後面的字是限制、不是功能，不算（見下面「否定」）。字典與通用字清單在看任何測試結果前寫好（`f05edf4`）。這次改動時，有關鍵字時送給模型的 60 張卡與順序完全不變（`bench/ai_path_same.ts` 用存下的關鍵字比對整個請求，1268 筆 0 筆不同）；之後的否定修正讓需求原字少了被否定的字，1268 筆中有 42 筆的卡片不同（見下）。
   - **否定（`dropNegated`，`src/relevance.ts`；規則排序、有關鍵字時 shortlist 用的需求原字、合不合標記共用）**：中文 `不需要`、`不用`、`不要`、`不必`、`不想`、`無需`／`無須`、`沒有`、`免`（`免費`、`有沒有` 不算），英文 `without`、`no`、`no need for`、`don't／doesn't need／require／want`。這些詞後面的字不算想要的字，中英文都一樣（`不需要 GPU` 的 GPU 也不算）。
     - 範圍是一個項目：英文字，或一個字典裡的中文詞加上後面的英文受詞（`免安裝 Docker`）；前面可以有一兩個字典外的短動詞（`不想裝 Python`）。`和`、`、`、`或`、`or`、`/` 讓否定延續到下一項（`不需要 GPU 和 Docker`）。
     - 遇到標點、轉折或新的肯定動詞（`但`、`需要`、`要`、`用`、`能`、`but`、`need`、`with`…）、`的`、英文 `and`／`for`／`to`（動名詞後的 `to` 除外）、英文後面接的中文詞、其他字，或滿 4 個字就結束（`不需要 GPU，但需要 CUDA` 只排除 GPU）。
     - `find_alternatives` 的痛點不套用：痛點裡的 `no dark mode` 是想要 dark mode，所以規則排序、標記與模型路徑的 shortlist 都照原字算；`must_keep` 照常套用否定。
     - 模型路徑：1268 筆存下的關鍵字請求中 42 筆的 60 張卡不同（都來自真的否定詞）；把其中 20 筆實際送給模型（舊請求兩次、新請求一次），最後選的工具只在第 3 個或順序上變，和模型自己兩次之間的差異差不多（`scripts/replay_match.py`）。`find_alternatives` 的模型請求 0 筆不同。
   - 量法：`scripts/shortlist_needs.py` 只從 `data/software` 產生檢查集（每筆驗證過的工具，用 Meta 模型把它的 summary 改寫成使用者的英文與中文需求），`bench/shortlist.ts` 算「自己那款有沒有進 60 張」；`bench/keywords.ts`、`bench/latency.ts` 量關鍵字呼叫與整體延遲（要花錢）。
3. **一次 `muse-spark-1.3`**（Responses API、`store: false`、`reasoning.effort: low`、strict JSON schema；slug 欄位的 enum 就是這次的候選）：解析需求成條件、選 1–3 個、每個理由引用一個卡片欄位與原值、取捨、和知名工具比、最好的免費選項、「內建就夠」、不在資料裡的知名免費工具（`well_known_option`，見下）、最多 1 個追問。模型固定在程式裡，不能換成 `-contributor`（使用者需求是私人資料）。`find_alternatives` 用同一份 prompt，**後面加 4 條規則**（`ALTERNATIVES_RULES`：只選做同一件事、至少解決一個痛點、保留 `must_keep` 的；和目前的工具比較；`keep_current`；解析出的痛點）；`find_software` 的 prompt 與 schema 不變。
4. **守門（程式）**：slug 必須在候選裡；理由引用的值要真的出現在該欄位；理由不能和卡片矛盾（離線、免費、開源、在某 OS 驗證過、不需 key、不需 GPU）。不合的理由丟掉，沒有理由的推薦丟掉。`well_known_option` 另有自己的檢查（見下）。
5. **退回規則**：模型關掉、沒有 key、超出預算、逾時、HTTP 錯誤（重試一次後仍失敗，見下面「重試」）、輸出壞掉、或推薦全被守門擋掉 → 依「（`find_alternatives`）卡片的 `alternatives_to` 提到目前的工具 → 規則的相關度分數（有關鍵字就加上關鍵字）→ 分數相同時：在使用者 OS 驗證過 → 寶藏分數」排序，理由用模板（只從欄位產生），標 `matched_by: "rules"`、`degraded: true`、`degraded_reason`。規則模式不判斷 `keep_current`（回 `null`）。
   - **合不合（`src/fit.ts`，只在規則模式；只加標記，不改列出的工具）**：把需求裡「具體的字」（去掉通用字、OS 名稱（整個字，`macOS` 不會變成產品 `OS`）、`MCP server` 這類工具種類、口語填充字與介系詞、`without`／`no` 到子句結束的限制、`不用` 之後的限制、`secret-project-xyz` 這類自己取的名字；只留目錄裡有出現過的字或產品名）和每個工具的能力欄位（名稱、summary、use cases、tags、MCP 工具名）比對。每個字算一樣重；一個中文詞的幾個英文同義字算一個字（`記憶體` → memory 或 ram，提到任一個就算）。判斷用的中文另有幾條修正（`ZH_PHRASES`：`編碼助手` 是 coding assistant 不是 encoding；`助手`／`助理` 是工具種類），排序用的 `ZH_EN` 不變。
     - **good**：需求點名的產品（Notion、GitHub、PostgreSQL 這類大小寫混合或句中大寫的字；PDF、JSON 這種縮寫算一般字；`my Node project` 這種「在哪裡做」的不算點名）全都直接提到，涵蓋**過半**的具體字，而且至少兩個字。需求只有一個具體字時最多 partial，除非那個字是點名的產品、卡片也直接提到它。
     - **partial**：至少提到一個點名的產品（有點名時），涵蓋至少三分之一的具體字：至少兩個字，或一個字但佔需求的一半以上。
     - **weak**：其他。需求的具體字目錄裡完全沒出現過，也是 weak。
     - 卡片只把某產品當成「替代誰」（tag `jira-alternative`、「an alternative to Notion」）時不算直接提到；只有需求說要它的替代品（`alternative to Jira`、`instead of`、`類似`）時才算數。
     - 回應：**列出的工具、順序、數量、`best_free`、追問都和沒有這個判斷時一樣**（`bench/rules_same.ts` 對 main 逐筆比對）；判斷只加標記。每個 pick 多一個 `match`（`quality`：good／partial／weak、`covers`、`missing`），partial 與 weak 的 `tradeoffs` 寫明「提到了哪些、沒提到哪些」。整體多一個 `match_quality`：列出的 picks 裡最好的那個標記，沒有一個到 partial 就是 none。
       - none：`coverage_note` 說 pickfit 沒有明確能做這件事的驗證工具，列出的是最接近的，但都沒提到某些字（列出來）；若排名更後面有工具到 partial，只說「列出的工具沒有一個明確做這件事」。
       - partial：`coverage_note` 說沒有一個列出的工具涵蓋整個需求，並寫出最接近的那個沒提到哪些字。
       - 文字不誇大 weak／partial，也不叫 agent 丟掉列出的工具：要不要用由 agent 和使用者決定。
       - `find_alternatives` 裡 `alternatives_to` 寫了目前工具的算 good。`events.need.match_quality` 也記下來。
     - **模型路徑完全不變**：`match`、`match_quality` 在模型選的回應裡不存在（schema 是 optional；`test/conformance.test.ts` 驗證兩種回應）；`bench/ai_path_same.ts` 用存下的關鍵字跑 1268 筆，模型回答的回應與 main 逐位元相同。
     - 量法：`scripts/rules_eval.py queries --fit` 產生新題目（Baseten，不看工具），`label` 給每題所有過硬條件的工具打分；`bench/fit_eval.ts` 依標註把題目分成 good／partial／none 三類，從 `findSoftware` 的回應算整體 `match_quality`、每個 pick 的標記分布、各標記有多少站得住，以及排序的 P@5。第二輪的保留題組在 `bench/fit-fresh/`（`queries --used …` 產生、只收新工作、全部保留；題目與標註先 commit，之後才跑判斷）。

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

### `report_outcome`

- 7 個 stage 存成 `(stage, success)`，對照寫在 `migrations/0001_init.sql` 開頭；`satisfaction` 存成 1／0／-1。
- **計分**：`rec_id` 必須是 pickfit 發給這個 slug 的：`installed`、`first_run_*` 要在 7 天內，`still_using`、`replaced`、`abandoned` 是幾週後才回報的，放寬到 120 天（`REC_TTL_LATER_DAYS`）（`find_*` 推薦過它，或 `get_install_guide` 給過它的指南）。合格的回報保留 `rec_id`，不合格的存成 `rec_id = NULL`，所以「`rec_id IS NOT NULL` ＝ 計分」。回 `counted_in_score` 與 `not_counted_reason`。
- **去重**：同一個 `(rec_id, slug, stage, success)` 只記一次，重送回 `deduplicated: true`、同一個 `report_id`（`0002` 把 `success` 加進唯一索引，否則「先失敗、修好後成功」的第二筆會被當成重複）。`still_using`、`replaced`、`abandoned` 例外：狀態會來回變，只有和同一個 rec_id **最新一筆**相同（同樣的 success 與 `replaced_by`）才算重複，所以「還在用 → 不用了 → 又在用」是三筆（`0005` 把這個 stage 移出唯一索引）。rec_id 的有效期從它**第一次**發出算起，同一個 rec_id 再拿一次安裝指南不會重新起算。
- **重驗**：`install_failed`／`first_run_failed`＋有效 `rec_id`＋知道 OS（參數或推薦時的 OS）＋有 `error_excerpt` → 寫進 `reverify_queue`；同一 `(slug, os)` 還在排隊就回 `already_queued`，做完（`done_at` 有值）後再失敗會重新排。處理在管線：`pickfit reverify`（或 `pickfit watch --reverify`，P5.3）在全新沙盒重跑。任何拿到 `rec_id` 的人都能回報，所以回報只決定「要重驗」，不決定寫什麼：驗證 agent 只看到結構化欄位（stage、OS、arch）和 pickfit 自己給過的步驟，`error_excerpt` 與 `note` 都不送進模型（`error_excerpt` 留在結果檔給人看）。只有通過、重播成功、而且步驟和紀錄不同（`first_run_failed` 也比 check 與 first task）的 run 才寫回；新步驟裡的套件名稱與網址都要出現在 README、pickfit 先前的步驟或這個 repo 本身，否則標 `held` 不寫、等人看。寫回照 `write_back` 的規則（不寫 `failed`、較強的通過紀錄保留），印出並存下該筆紀錄的 `git diff`、單獨 commit（commit 失敗就把檔案放回），再設 `done_at`。部署由人看過 diff 後自己 `pickfit publish`：`watch --reverify` 不能和 `--publish` 一起用。同一台機器上用 lock 檔認領，`reverify` 和 `watch --reverify` 不會為同一筆回報重複付費。沙盒是 Linux：macOS／Windows 的回報也在 Linux 重跑，結果會註明。
- **還在用嗎（check-in）**：`get_install_guide` 回 `check_in`（`src/checkin.ts`）。裝好 7 天後到 `valid_until`（120 天）之間，使用者下次跟 agent 談到軟體、或自己問起時，agent **先問使用者同意**，才在本機跑幾個唯讀指令：`command -v`（Windows 用 `Get-Command`，指令名稱取自錄下的 check）；套件管理器只列這一個工具（`brew list --versions`、`npm ls -g --depth=0`，`uv tool list`、`pipx list`、`cargo install --list` 過濾到這個名字，`pip show`）；MCP server 看 `claude mcp get <name>`；macOS 的 app 用 `mdls -name kMDItemLastUsedDate`。指令只從錄下的安裝步驟產生，不經過模型。然後回報 `still_using` 或 `abandoned`（換掉了就 `replaced`），加上粗略的 `last_used`；不送指令輸出、確切時間、路徑或其他軟體。唯讀部署（`TOOLS=readonly`）沒有 `report_outcome`，`check_in` 是 `null`。沒有常駐程式：每次都是 agent 在對話裡、使用者同意後跑一次。
- **`last_used`**：只有 `still_using`、`replaced`、`abandoned` 會存（其他 stage 一律 `null`）；`0004` 的 CHECK 只收這四個值，確切時間存不進去。
- **個資**：`error_excerpt` 與 `note` 存之前先過 `src/scrub.ts`（家目錄的使用者名稱、email、`token=`／`Bearer` 之類的值、長串像金鑰的字元），`error_excerpt` 留最後 500 字元、`note` 最多 280 字元。`note` 是不可信的輸入：只給人看，**不出現在任何回應，也不送進模型**。

### `submit_software`

- 只收 `github.com/<owner>/<repo>`（`.git`、大小寫、`/tree/...` 都正規化成 `https://github.com/owner/repo`）；其他網域、`/topics/...` 之類不是 repo 的路徑回工具錯誤。Threads 連結還沒做。
- 一個 repo 一列（`submissions.url` 唯一）；重送只讀狀態（`already_submitted: true`）。已在目錄裡的 repo 直接回 `listed` 與 slug，不新增一列。
- 每小時新提交上限 `SUBMIT_HOURLY_CAP`（預設 20，全體共用；不存 IP，所以沒辦法分人計）。
- Worker 只排隊，處理在管線：`pickfit watch`（P5.2）每 60 秒讀 `status = 'queued'` 的列，更新 `status`（`reading` → `verifying` → `listed`／`listed_unverified`／`rejected`）、`slug`、`reason`、`updated_at`（時間格式和 Worker 一樣是 UTC `toISOString`）。
  - 每筆走單筆管線：GitHub 資料 → 規則 → 初篩（Baseten 上的 Muse Spark Open）→ `muse-spark-1.3` 抽取 → 紀錄 → Modal 驗證（agent、全新沙盒重播、畫面判讀）→ 評分。紀錄先在 `runs/watch/<submission>/` 建好，全部完成才複製進 `data/software/` 並單獨 commit。
  - 全部通過：預設只 commit，`status` 停在 `verifying`、`reason` 寫「下次 publish 上線」；加 `--publish` 才跑 `pickfit publish` 部署並改成 `listed`。別人另外 `pickfit publish` 之後，watch 看到線上 Worker 的 `data_sha256` 等於 `data/software` 的，也把這些改成 `listed`。沒驗證成（沙盒跑不了或沒通過）：commit、`listed_unverified`。
  - commit 之後這筆就算「已落地」（記在 job 檔）：之後的重試只回報實際狀態，不重跑管線，也不會把自己的紀錄說成「已在目錄」；commit 失敗會把 `data/software` 放回原樣。同一個 repo 用兩個網址同時送進來，第二筆直接拒絕（不會產生兩筆同 `repo_id` 的紀錄，那會讓索引與部署失敗）。
  - 拒絕（`reason` 由程式寫，不放模型的文字）：非 GitHub repo、fixture、私有或不存在、已在 `data/software`（改回該紀錄的狀態）、和另一筆提交是同一個 repo、星數超過發現的上限（300）、規則擋下、初篩判定不是可安裝的軟體、不在 dev_cli／local_ai。
  - 上限：每小時開始處理的筆數照 `SUBMIT_HOURLY_CAP`；共用帳本的 Meta（每日、總額）與 Baseten 預算要留得下一筆的最壞花費（約 $1）才開始；`--max-usd` 管整次執行。每筆的各階段秒數與「從提交到可發布」的時間記在 `runs/watch/jobs/<submission>.json`。
  - `pickfit watch --status`（唯讀）列出 D1 的提交與重驗佇列；`--local` 用 `wrangler dev` 的本機 D1。

## 花費上限與 `degraded`

Worker 自己的帳在 D1 `meta_budget`（和本機管線的 `~/.pickfit/ledger.sqlite` 分開）：每日 $3、總額 $15（10/31 由 $40 調降為 $20，同日再降為 $15、把 $5 移給管線的 MCP 擴充；`META_DAILY_CAP_USD`、`META_TOTAL_CAP_USD`）。`find_*` 呼叫前先用「這次最多花多少」檢查兩個上限，超過就不呼叫、回 `degraded: true`、`degraded_reason: "over_budget"`；呼叫後記實際花費；逾時的呼叫照上限計。查不到 D1 就不呼叫模型（`budget_unavailable`）。

### 重試（暫時性錯誤只重試一次）

10/29 重新部署後，Meta 曾有幾分鐘對 `muse-spark-1.3` 時好時壞地回 404「model not found」，當時 `find_software` 一遇錯就退回規則。現在 `src/meta.ts` 的 `callMeta` 遇到下面三種狀態會**再試一次**：

- `429`；
- 任何 `5xx`；
- `404` 且內容說模型不存在（`model_not_found`，或 `model … not found／does not exist`）。

其他狀態不重試：`400`、`401`、`403`、路徑不對的 `404` 等。逾時、連線錯誤也不重試。Meta 已經回了答案的也不重試，不論輸出壞掉、`incomplete`，或推薦全被守門擋掉。

- **等待**：200–800 ms 隨機。Meta 給的 `Retry-After`（或 `retry-after-ms`）在 5 秒以內就照它等；要求等更久就不重試，直接退回規則。
- **時限**：兩次請求加上中間的等待都在 `META_TIMEOUT_MS` 之內；有關鍵字呼叫時，它用掉的時間也算在內，配對只拿剩下的。第二次的逾時是剩下的時間；剩不到 10 秒（一次配對約 6–8 秒）就不重試，照原本的方式退回規則。
- **花費**：HTTP 錯誤沒有 usage，記 $0；只記有回 usage 的那次。配對呼叫只寫一筆 `meta_budget`（`calls + 1`）；有關鍵字呼叫時它另記一筆，`events.meta_cost_usd` 是兩者的和。重試前不再查一次上限，因為失敗的那次沒有花到錢。
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

例外只有產品網頁自己的快取（下一節）：只在 `POST /search` 裡讀寫，MCP 的路徑碰不到（`test/web.test.ts` 有測：網頁同樣的搜尋兩次只呼叫一次模型，MCP 兩次仍是兩次）。

## 產品網頁（`GET /`、`POST /search`，P5.7）

一個搜尋框加上選填的作業系統、CPU、「只要免費」「要能離線」，對應 `find_software` 的 `need`、`os`、`arch`、`budget: free_only`、`must_run_locally`。程式在 `src/web.ts`（路由、限制）與 `src/page.ts`（HTML，純函式）。

- **同一個大腦**：`POST /search` 先用 `server.ts` 的 `findInput`（MCP 工具同一個 zod schema）驗表單，再呼叫 `find.ts` 的 `findSoftware`，每個 pick 再呼叫 `install.ts` 的 `installGuide`，最後才排成 HTML。沒有另一份配對或安裝步驟的程式碼，網頁和 agent 不會分岔。沒選 OS 時，安裝步驟用 pickfit 實際跑過的那個系統，並寫明在哪裡跑的。
- **路由**：`GET /` 只有在 `Accept` 含 `text/html`（瀏覽器）時回網頁；`curl`、健康檢查、`pickfit publish` 之後的確認照舊拿到 JSON（`Vary: Accept`）。所以公開網址打開就是產品，而部署檢查與評測部署比對 `data_sha256` 的方式不變。`GET /search` 轉回 `/`。沒有 JavaScript 時表單照樣送出，伺服器回整頁；有 JavaScript 時只換結果區（`X-Pickfit-Fragment: 1`）。
- **呈現**：每個 pick 有 fit 句、理由（每條附上它引用的卡片欄位與值）、取捨、和知名工具的比較、`best_free`、試驗紀錄（驗證等級、在哪個 OS／CPU、沙盒重播或人工、日期、離線測試通過、沒通過，或使用者要離線但還沒測過，以及「在你的系統上驗證過／沒有／請選 OS」）、`get_install_guide` 的步驟（第一個展開）、原始碼與 run record 連結（有才顯示）。`best_free` 不在 picks 裡時，也寫出它在哪裡跑過、是不是使用者的系統。`well_known_option` 的標題寫著「not verified by pickfit」，用一般字體（不是 pick 名稱的襯線大字）；第一行是一條填色的「pickfit 沒裝過也沒測過，沒有試跑紀錄和安裝指南」；沒有排名、徽章、試驗紀錄、安裝步驟或連結。沒有合適的工具時顯示 `coverage_note`。`find.ts` 給 agent 的「Verified on linux only…」取捨不重複顯示，因為試驗紀錄已經用完整句子說了。
  - **MCP server**：試驗紀錄寫出握手列出的工具，以及有沒有實際呼叫過其中一個。安裝步驟後面接 `get_install_guide` 的 `mcp_client_config`：
    - `claude mcp add` 那一行；
    - 給 Claude Desktop、Cursor 等客戶端的 JSON（收在可展開的區塊）；
    - 使用者要自己填的環境變數，標出哪些是必填。
  - **桌面 app**：試驗紀錄照 `verification.gui` 寫出畫面判讀看到什麼，並明說 pickfit 沒用過它的任何功能；斷網啟動有通過也會寫出來。只有 `main_ui`、`first_run` 打勾，顯示錯誤或空白視窗的不打勾，用警示色。
  - **規則路徑**：每個 pick 標 Good／Partial／Weak match，下面一行列出 profile 提到與沒提到的需求字；`find.ts` 加在取捨裡的同一句不重複。標題跟著 `match_quality`：partial 是「Partial fits」，none 是「No clear fit」，`coverage_note` 移到 picks 前面。
- **不記個資**：不存 IP。`events` 和 MCP 一樣只存解析後的條件，另標 `client = 'web'`，網頁和 agent 的使用量分得開。網頁上顯示安裝步驟**不**寫 `install_guide` 事件，因為使用者還沒選，而 MCP 的那個事件代表「選了這一款」。不支援 `?need=` 預填：請求網址會進 Workers log，頁尾寫著 pickfit 不留使用者的原話。
- **花費與濫用**（每次搜尋是一次付費的 `muse-spark-1.3`，用 Worker 自己的 `meta_budget`）：
  - **網頁上限** `WEB_DAILY_CAP_USD`（預設 2）：呼叫模型前，先用**一條** D1 指令（`budget.ts` 的 `reserveSpend`，`INSERT … SELECT … WHERE` 加 upsert）預留這次最壞情況的花費（配對呼叫 `estimateCostUsd(150000)` 加上超過 60 筆時的關鍵字呼叫 `estimateCostUsd(8000, 600)`，約 $0.085；今天 60 張卡約 8.4 萬字元）。條件是「今天已花＋預留 ≤ `min(WEB_DAILY_CAP_USD, META_DAILY_CAP_USD)`」而且「總額＋預留 ≤ $40」。同時湧入的搜尋不會在任何一筆記帳前全部通過檢查；兩個 isolate 共用一個 D1 也一樣，`test/web.test.ts` 有測。呼叫結束（不論成敗）後釋放預留，實際花費照 MCP 原本的方式記帳。`findSoftware` 裡原本的檢查照跑，只是上限加上自己的預留，不重複計算。MCP 路徑不預留，程式沒變，但它的檢查看得到網頁正在進行的預留，所以比較保守。預留不到時改用規則排序，並說明原因：
    - 網頁今天的額度用完：「paused until 00:00 UTC」，並說明網頁和 agent 的花費合計已到上限；
    - 總額用完：不承諾重置；
    - 查不到 D1：照實說查不到。
  - **每人頻率**：`ratelimits` 綁定 `WEB_RATE_LIMITER`，每分鐘 6 次（以 Cloudflare 機房計）。鍵是「UTC 日期＋IP」的 SHA-256 前 32 字元，IPv6 位址以 /64 計（一戶或一台主機常持有整個 /64；IPv4-mapped 位址照 IPv4 計），只存在限流計數器裡，不進 D1、不進 log。沒有綁定時（例如在別的環境）改用這個 isolate 記憶體裡的計數；綁定出錯時放行並記 `web_rate_limit_failed`，花費仍受網頁上限擋。超過回 429、`Retry-After: 60` 與「Busy」訊息，不呼叫模型、不寫事件。
  - **快取與併發**：同樣的需求（忽略大小寫與多餘空白）加同樣的條件：
    - 10 分鐘內在同一個 isolate 直接重用結果，不呼叫模型、不寫事件，頁面註明是剛才的結果。
    - 還在跑的搜尋，後到的那筆等它的結果，不另外呼叫。
    - 鍵是雜湊，不留原話；`degraded` 的結果不快取，下一次會再試模型。
    - 一個 isolate 同時最多 `MAX_IN_FLIGHT`（6）筆模型搜尋，超過回 503、`Retry-After: 10` 與「Busy」。跨 isolate 的花費由上面的預留擋。
  - **跨站**：`POST /search` 和 `/mcp` 一樣檢查 Host 與 Origin，別的網站的表單不能花這裡的預算。表單以位元組計，邊讀邊算，超過 8 KB（`Content-Length` 已超過就不讀）回 413。需求以字元（code point）計，要 3–500 字，否則回 400 並說出字數，不會默默截斷；500 個中日文字約 4.5 KB，在上限內。都不呼叫模型。
- **設計**（10/30 改版）：用 frontend-design 與 taste-skill 做、web-design-guidelines 檢查。概念是「pickfit 在沙盒裝好一款工具時寫下的試跑紀錄，就是每個推薦印在上面的那張單子」。
  - 首屏：「Tools that fit, [一張真的試跑紀錄] tested first.」，搜尋框就在下面。手機上順序是標題、說明、搜尋框，試跑紀錄放在後面，搜尋框在第一個畫面裡。沒有 JavaScript 時，表單送到 `/search#results`，回來的頁面直接停在結果。
  - 結果：左邊是主張、右邊是證據，主張在捲動時停住。沒有排名數字（配對不是排名）。「內建就夠了」放在 picks 前面。沒驗證過的工具沒有試跑紀錄。
  - 搜尋前：最新的試跑表、另一個寶藏工具被修正的 README，以及一個四段的滑桿，帶同一款工具走過讀懂、安裝、配對、交付。這些全部從索引讀，不呼叫模型、不捏造。
  - 字級五階、一個強調色；沒有細線、外框、陰影、眉標、emoji。
  - taste-skill 檢查器從 8 FAIL／7 WARN 降到 0 FAIL／4 WARN。剩下的 4 個 WARN 都有理由：程式碼用等寬字；沒有照片或影片（軟體的圖就是自己的介面）；動態只回應使用者的操作。
- **安全**：每個回應一個 CSP nonce（`default-src 'none'`，只允許自己的 inline script／style、`connect-src 'self'`、`form-action 'self'`、`frame-ancestors 'none'`）。資料與模型輸出全部跳脫；連結只收 http(s)，帶 `rel="noopener noreferrer"`，`Referrer-Policy: no-referrer`。沒有第三方字型或腳本。
- **評測部署**：`env.eval`、`env.eval-rules` 設 `WEB_SEARCH: "off"`，`/` 永遠是 JSON、`/search` 是 404。`WEB_DAILY_CAP_USD` 與 `ratelimits` 也照列（wrangler 不會把它們繼承進 env，少了會警告），只是用不到。
- **實測**（10/29，本機 `wrangler dev`、真資料 96 筆、5 個自擬需求，不是評測題）：8 次 `muse-spark-1.3` 共 $0.139，平均 6.9 秒。git commit 訊息（Linux x86-64）→ Eckra，在你的系統上驗證過；講課影片離線字幕（macOS arm64、免費、離線）→ babelscribe，標「沒在你的系統上驗證」；壓測 OpenAI 相容端點（Linux）→ servebench；本機記錄 LLM API 花費（免費、不限 OS）→ TokenTracker；RAW 修圖（macOS、免費，不在涵蓋範圍）→ 沒有合適的，`well_known_option` 是 darktable，標未驗證。

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

`0001_init.sql`：`events`、`submissions`、`reverify_queue`、`meta_budget`。`0002_outcome_once_by_result.sql`：回報的去重索引加上 `success`。`0003_model_attempts.sql`：`events` 加 `degraded_reason`、`model_attempts`、`model_statuses`。`0004_last_used.sql`：`events` 加 `last_used`（只收 `this_week`、`this_month`、`older`、`unknown`）。`0005_later_stage_reports.sql`：`still_using` 這個 stage 移出去重索引，改由 Worker 對最新一筆去重。**一定要先套到最新的 migration（現在是 `0005`）再部署這版**，否則每一筆事件都寫不進去：

- `report_outcome` 會整個失敗：它等事件寫完才回應，寫入錯誤會讓每次呼叫都回錯誤。
- `find_*`、`get_install_guide`、`submit_software` 照常回應，但事件寫入失敗，只在 Workers log 留下 `d1_write_failed`。`rec_id` 不會進 `events`，之後拿這些 `rec_id` 回報也不能計分。

不記 IP；`events.need` 只存條件（agent 給的參數＋模型解析出的 `task`、`search_terms`、痛點等），不存使用者原話。

## 部署檢查清單

**先決條件**：`data/software/` 有真的 profile 並已 commit（P2.6），而且念誠同意部署。下面的指令都在**主 checkout** 的 `worker/` 下跑（`.env` 在主 checkout 根目錄）。

1. **建 D1**：`npx wrangler d1 create pickfit`，把輸出的 `database_id` 填進 `wrangler.jsonc`（取代全 0 的佔位），commit。
2. **遠端建表**：`npx wrangler d1 migrations apply pickfit --remote`（`0001`–`0005` 都要套，而且**要在部署這版之前套**；之後 `migrations/` 有新檔，也是先套再部署。**`pickfit publish` 不會幫你跑**；`eval` 等 env 的 D1 也要各自套）。
3. **`ALLOWED_HOSTS`**：在 `wrangler.jsonc` 的 `vars` 填 `pickfit-mcp.<workers.dev 子網域>.workers.dev`（子網域就是 P0.5 hello 部署用的那個，dashboard 的 Workers & Pages 也看得到），commit。沒填的話遠端每個請求都是 403，`pickfit publish` 也會拒絕部署。
4. **先 dry run**：在 repo 根目錄 `uv run pickfit publish --dry-run`。它會驗 `data/software/` 每一筆、確認不是 fixture、資料都已 commit、`wrangler.jsonc` 已填好；任何一項不過就列出問題、exit 1。
5. **部署**：`uv run pickfit publish`。它用真資料重建 `worker/src/generated/index.json`，再跑 `npx wrangler deploy`。（之後本機要回到假資料：`npm run build:index -- --data test/fixtures/software`。）
6. **設金鑰**（第一次部署後；在設好之前，`find_*` 會以 `no_api_key` 退回規則排序）。從 `.env` 只讀這一個值、經 pipe 交給 wrangler，不會印在終端機：

   ```bash
   uv run --project .. python -c "import sys; from pickfit.env import read_env; sys.stdout.write(read_env(['MODEL_API_KEY'])['MODEL_API_KEY'])" | npx wrangler secret put MODEL_API_KEY
   ```

7. **確認**：`curl https://<host>/` 的 `entries` 等於 dry run 的筆數（瀏覽器開同一個網址是產品網頁，試搜一次）；`claude mcp add --transport http pickfit https://<host>/mcp`（用 `env -i` 啟動，見上）看得到 5 個工具；問一題，回應的 `matched_by` 是 `muse-spark-1.3`。
8. **緊急關模型**：`npx wrangler deploy --var MATCH_MODE:off`，或把 `META_DAILY_CAP_USD` 調成 `0` 再部署；兩種都會讓 `find_*` 改用規則、標 `degraded`。
