# 技術調研：pickfit 的架構與技術選型

2026-10-28 · 調研進行中。每完成一節就更新並 push；中途中斷時，以「目前的結論」為準。

需求來源：[docs/brief.md](../brief.md)、[docs/hackathon-rules.md](../hackathon-rules.md)。

---

## 0. 目前的結論

**狀態（2026-10-28 03:50 台北）**：調研剛開始。以下是動手前的**初步假設**，還沒有查證，之後會逐條改成有來源的結論。

| 問題 | 初步假設（未驗證） | 要查證的點 |
|---|---|---|
| A. 管道 | GitHub search API 當主幹；Show HN（官方 API）、Homebrew／PyPI 等套件資料、Hugging Face 補本地 AI 類；使用者貼連結當供給端入口 | 各管道條款、Threads API 能不能搜尋別人的貼文 |
| B. 品質 | 規則訊號（release、CI、文件、維護）＋ 沙盒驗證結果；知名度另外算 | Scorecard 對小專案的覆蓋率 |
| C. 沙盒 | Modal Sandbox 當主力（有比賽 credits） | 費用、啟動時間、能否限制網路；macOS 怎麼驗 |
| D. Meta 模型 | Muse Spark 做抽取、驗證判讀、配對；開放權重模型做初篩 | 官方文件中的實際能力（圖片、tool calling、JSON schema） |
| E. MCP | 無狀態 Streamable HTTP，部署在 Cloudflare Workers | 規格版本、SDK 用法、Claude Code／Codex 怎麼連 |
| F. 儲存與配對 | git 裡的 JSON 當正本，建置成索引給 MCP；配對以條件篩選為主 | 是否需要向量搜尋 |

各節的調研筆記會先寫進 [notes/](notes/)，查核後再整合進本文。

**調研方式**：每個主題由一個 agent 查官方文件並實測，另一個 agent 反向查核（找錯、標「未驗證」），最後由主控者整合。

---

## A. 軟體從哪裡來：管道盤點

（進行中）

## B. 怎麼判斷「可用的軟體」與「品質好」

（進行中）

## C. 沙盒驗證

（進行中）

## D. Meta 模型

細節與來源：[notes/meta-model-api.md](notes/meta-model-api.md)、[notes/meta-open-weights.md](notes/meta-open-weights.md)、[notes/meta-usage-design.md](notes/meta-usage-design.md)。三份都經過查核 agent 逐條對官方文件（查證日 2026-10-28）。**沒有 key，所有模型呼叫都還沒實測。**

### D.1 官方文件查到的事實

官方文件在 [dev.meta.ai/docs](https://dev.meta.ai/docs)（舊網址 `llama.developer.meta.com` 轉址過來；每頁加 `.md` 有純文字版，索引在 [llms.txt](https://dev.meta.ai/llms.txt)）。

| 模型 | model ID | 在哪 | 圖片 | tool calling | JSON schema | context | 價格（每百萬 token，in／out） |
|---|---|---|---|---|---|---|---|
| Muse Spark 1.3 | `muse-spark-1.3` | Meta API | 有（另有影片、PDF） | 有 | 有，constrained decoding，保證符合 | 1,048,576 | $1.25／$4.25（快取 $0.15） |
| Muse Spark 1.3 Contributor | `muse-spark-1.3-contributor` | Meta API | 有 | 有 | 有 | 1,048,576 | $0.10／$0.20；只有 150 RPM；內容可能被拿去訓練 |
| Muse Wonder | `muse-wonder-1.0` | Meta API | 有 | 有 | 有 | 1,048,576 | $4／$20 |
| Muse Voice Transcribe | `muse-voice-transcribe-1.0` | Meta API | — | 無 | 無 | — | $0.18／小時音訊；檔案模式只收 WAV、≤10 分鐘 |
| Muse Spark Open | Baseten：`meta-models/muse-spark-open`（比賽用 `-1026`，**未驗證**） | 開放權重；Baseten、Modal、Together 等 | 有 | 有 | Baseten 接受但**不強制** | 1,048,576 | Baseten／Modal 與 Spark 標準版同價 |
| Muse Glimmer | `meta-models/Muse-Glimmer-30B` | 開放權重（29.6B dense，Apache 2.0） | 有 | 有，一回合只能一個 | 未驗證 | 131,072 | 只有 Together／DeepInfra 按 token 計價，**都不是比賽合作夥伴** |

| API 事實 | 對 pickfit 的意思 |
|---|---|
| base URL `https://api.meta.ai/v1`，OpenAI 相容（`/chat/completions`、`/responses`），另有 Anthropic 相容的 `/messages`；Bearer 認證，變數名 `MODEL_API_KEY` | 直接用 `openai` 套件改 `base_url`，不需專用 SDK |
| `tool_choice` 只能 `auto`；不支援 `stop`、`n>1`、`logprobs` | 不能強制呼叫某工具；要固定格式用 structured output |
| 一定會推理（`reasoning_effort: none` 回 400），推理 token 算輸出 | 大量工作設 `minimal`／`low`，成本要算推理 |
| Chat Completions 不跨回合保留推理；多步工具迴圈官方建議 Responses API | 驗證 agent 用 Responses API＋`previous_response_id` |
| Responses 有內建 `web_search`（$2.50／千次）、`reasoning.summary` | 驗證時查錯誤訊息；推理摘要可當 demo 的 trace |
| 沒有 Batch API；Spend Limit 只寄 email，不會停止扣款 | 程式自己記帳，超過門檻就停 |
| 3,000 RPM／4M TPM（以 team 計） | 一個人的規模完全夠 |
| 台灣帳號能否註冊、綁卡：地理政策沒擋台灣，8 月宣布全球開放，但**未實際確認** | **今天第一件事就是註冊**；失敗則全部改走 Baseten 上的 Spark Open |

### D.2 開放權重：用在哪、為什麼

- 開放權重**不會比較便宜**：Spark Open 在 Baseten／Modal 和 Meta 標準版同價；Meta 的 Contributor 版還便宜約 12–20 倍。
- 用它的理由是：比賽給的 Baseten credits、獨立的 rate limit、以及 Best Build on Meta Open Weight Models 加碼獎。
- 所以只放在**初篩**這一個環節：Spark Open @ Baseten，`reasoning_effort: low`，輸出用 pydantic 在程式端驗證（Baseten 不強制 schema）；低信心才升級到 `muse-spark-1.3` 複查。
- Glimmer 不用：合作夥伴都只提供專屬 GPU（Modal H100 約 $3.95／小時），自架的時間不划算。
- 授權要求產品顯示「Built with Muse Spark Open」，README 要放。

### D.3 每個環節怎麼用（讓評審一眼看出是核心）

**原則：模型做判斷，程式做守門。** 每個環節都有一個沒有模型就做不了的決定；程式負責搬資料、限制步數與花費、檢查輸出。產品執行期不用任何非 Meta 的 LLM。

| 環節 | 模型 | 模型做的決定 | 程式做的事 | 每 100 筆（估算） |
|---|---|---|---|---:|
| 1 初篩 | Spark Open @ Baseten | 是不是可用的軟體、哪一類、為什麼不是（不給星數，避免知名度偏誤） | 前置規則、JSON 驗證、5% 抽樣和 1.3 比對 | $1.4 |
| 2 抽取 | `muse-spark-1.3` | 讀 README、release notes、貼文、截圖，填欄位，**每欄附原文引用** | 檢查引用真的出現在來源；授權、release 等事實欄位用 API 值 | $2.4–2.8 |
| 3a 驗證 agent | `muse-spark-1.3`（Responses＋function tools＋`web_search`） | 每一步跑什麼、錯了怎麼修、何時結束 | 沙盒、步數／時間／花費上限 | $10–27 |
| 3b 畫面判讀 | `muse-spark-1.3`（圖片＋schema） | 截圖裡的軟體是否真的在運作，框出證據（0–1000 座標） | 和 exit code、重播結果合併 | $1.3 |
| 3c 重播 | 不用模型 | — | 在乾淨沙盒照記錄的步驟重跑一次，確認可重現 | — |
| 4 計分 | `muse-spark-1.3` | 文件完整度、安裝說明準確度（0–3 分，有錨點與引用） | 驗證、維護、知名度、寶藏分數都用規則算 | $3.8 |
| 5 配對 | `muse-spark-1.3` | 需求 → 條件、比較 2–3 個候選、找最好的免費選項、最多問 1–2 個問題 | 結構化篩選；檢查理由對得上欄位 | $2.4／100 次查詢 |

- 驗證 agent 是最能證明「核心」的地方：Muse Spark 自己決定安裝方式、讀錯誤、改指令、跑 smoke test。官方 cookbook 有 Muse Spark 1.3 在拋棄式 Docker 沙盒自主跑 48 個 shell 指令的例子，同一個模式。
- 停止條件：呼叫 `finish`，或 25 回合、15 個指令、20 分鐘、每款 $0.50、同一個錯誤 3 次。
- 成本（估算，推理 token 未實測）：收錄並驗證 100 款，Meta API 約 $18–35，Baseten 約 $1.4。$150 credits 約可處理 400–800 款，demo 規模（100–300 款）夠用。
- Demo 與 README：每一步標出模型、model ID、token、花費、推理摘要；數字從 trace log 自動產生。

### D.4 未驗證、拿到 key 後先測

| # | 項目 | 備案 |
|---|---|---|
| 1 | 台灣帳號能否開 Meta Model API | 全部改走 Spark Open @ Baseten |
| 2 | Baseten 的 `meta-models/muse-spark-open-1026` 是否存在 | 用 `/v1/models` 查；不行就用公開 ID |
| 3 | 截圖放在 tool 輸出裡模型看不看得到（文件互相矛盾） | 截圖放 user 訊息，或只交給 3b 判讀 |
| 4 | `text.format` 能否和 tools 同一請求 | 用 `finish` 工具＋程式驗證 |
| 5 | 推理 token 實際用量 | 調 `reasoning.effort`；先用 spike 的 `usage` 換掉估算 |

spike：`spikes/meta_api_hello.py`（文字、JSON schema、tool calling、圖片）、`spikes/meta_responses_agent_probe.py`（多輪工具迴圈、截圖放哪、schema＋tools、web_search）、`spikes/meta_baseten_hello.py`。設好環境變數就能跑。

## E. MCP server

（進行中）

## F. 儲存與配對

細節、DDL、JSON Schema 草案與 spike：[notes/storage-matching.md](notes/storage-matching.md)（查證日 2026-10-28）。

### F.1 儲存：git 裡的 JSON 當正本，D1 只放事件

| | git 中的 JSON（每款一檔） | SQLite 檔 | Cloudflare D1 | Postgres（Neon／Supabase） |
|---|---|---|---|---|
| 開發時間 | 最短 | 短，要遷移 | 中 | 最長，多一個服務 |
| MCP（Worker）怎麼讀 | 建置時轉成索引，打包進 Worker | Worker 不能直接開，要 sql.js（WASM）或先轉 JSON | binding 直接查 | 要 HTTP driver |
| 可審計性 | **最好**：每次改動一個 commit，也是「比賽期間做的」證據 | 二進位，diff 看不懂 | 只能還原，看不到逐欄位變更 | 要自己做 audit 表 |
| 人工抽查 | 開檔改 | 要 SQL | 要 SQL | 要 SQL |

**建議**：

| # | 決定 | 理由 |
|---|---|---|
| 1 | 正本：`data/software/<slug>.json`，用 JSON 不用 YAML | diff 就是審計紀錄；不必處理 YAML 的隱式型別 |
| 2 | 建置時把全部檔案轉成一個 `index.json`（候選卡＋預先算好的 BM25 倒排），**打包進 Worker** | spike：3,000 筆 bundle 約 1 MB；8,198 筆 `JSON.parse` 16.5 ms，查詢中位數 <1 ms，離 Worker 啟動 1 秒上限很遠（本機量測） |
| 3 | 事件（查詢、安裝指南、回報、提交）寫 **D1**：`events`、`reverify_queue`、`meta_budget` 三張表 | 要 SQL 彙總與去重；KV 免費版每天只能寫 1,000 個 key、最終一致，不適合 |
| 4 | push → Workers Builds 自動 `validate → build_index → deploy` | 不用自己寫同步程式；資料壞了就不會部署 |
| 5 | 失敗回報進 `reverify_queue` → 驗證 agent 重跑 → 新步驟 commit 回 git | 「回報 → 重驗 → 安裝步驟被修正」留下一個 git diff，是「不是 RAG」最直接的證據 |
| 6 | 不記 IP，不存需求原文，只存模型解析後的條件 | brief 第 11 節 |

Cloudflare 免費額度（[Workers limits](https://developers.cloudflare.com/workers/platform/limits/)、[D1 limits](https://developers.cloudflare.com/d1/platform/limits/)）：Workers 每天 10 萬請求、每請求 CPU 10 ms；D1 每天讀 500 萬列、寫 10 萬列。demo 用不完。**未驗證**：Free 方案冷啟動時解析索引是否算進 10 ms CPU；出現 Error 1102 就改 Paid（每月 $5）。

### F.2 配對：條件篩選為主，模型負責理解與取捨

| 步 | 誰 | 做什麼 |
|---|---|---|
| A 解析需求 | Muse Spark | 自然語言 → 條件（OS、預算、隱私、類別、必要功能、目前在用的工具）＋英文 `search_terms` |
| B 硬條件篩選 | 程式 | 只留 `listed`、該 OS 驗證過、符合本機執行／免費等條件的 |
| C 取候選 | 程式 | 在合格清單上用 BM25 查 `search_terms`，取前 25 張候選卡（每張約 350 tokens） |
| D 該不該問 | 程式＋Muse Spark | 程式先找「前 5 名在這個屬性上不同、但需求沒說」的屬性；沒有就不准問；有的話由模型判斷問了會不會改變第一名 |
| E 比較取捨 | Muse Spark | 選 1–3 個，每個理由附對應欄位；寫和知名工具的取捨、最好的免費選項、「不需要新軟體」的情況 |
| F 守門 | 程式 | slug 必須在候選裡、理由對得上欄位；模型失敗就退回寶藏分數排序＋模板理由，標 `generated_by: rules` |
| G 安裝 | 程式 | `get_install_guide` 只回傳重播過的步驟，不呼叫模型 |
| H 回報 | 程式 | `report_outcome` 寫 D1；失敗就排入重驗 |

**和基本 RAG 的差別**：

| | 基本 RAG | pickfit |
|---|---|---|
| 知識從哪來 | 現成文件切塊 | 自己產生：模型讀懂、沙盒實際安裝、程式重播後寫成結構化檔案 |
| 候選怎麼來 | 向量相似度取段落 | 硬條件篩選＋關鍵字；模型負責改寫需求 |
| 模型做什麼 | 摘要檢索到的段落 | 轉條件、決定要不要問、比較取捨、找免費選項；每個理由要對得上欄位 |
| 輸出 | 一段文字 | 可執行的東西：重播過的安裝步驟、驗證指令 |
| 之後 | 結束 | 回報 → 重驗 → git 裡的步驟被修正 |

### F.3 不用向量搜尋

- Meta Model API 文件裡**沒有 embedding 模型或 `/v1/embeddings`**（沒有 key 無法用 `/v1/models` 確認，標未驗證）。用別家 embedding 等於在配對核心放非 Meta 模型，而「向量庫＋LLM」正是基本 RAG 的樣子。
- spike（`spikes/sm_index_bench.mjs`）：用 Homebrew 8,198 個 formula 的描述當語料、10 題。使用者原話直接查 BM25，好答案進前 25 名的只有 5／10；換成「模型會產生的英文關鍵字」（手寫模擬，不是模型輸出）後是 10／10。
- 結論：語意落差交給 Muse Spark 在兩端處理（抽取時寫 `use_cases`、`alternatives_to`；查詢時寫 `search_terms`）。評測時若有 2 題以上好答案沒進前 25 名，再考慮向量。

## G. 整體架構

（進行中）

## H. 每天的實作計畫

（進行中）

## I. 風險

（進行中）

## J. 建議修改 brief

（進行中）

## K. 需要念誠決定或提供的東西

（進行中）
