# Meta Model API 調研筆記

2026-10-28（台北）· 查證日一律為 2026-10-28。資料來自 Meta 官方文件與 Help Center，第三方來源會標出。
**沒有 API key，所有模型呼叫都是「未實測」**；只用 curl 打了不需認證的端點（`/v1/status`、401 錯誤訊息）。

**2026-10-28 下午已帶 key 實測**，結果見文末「帶 key 實測」；與上文不同時以實測為準。
已由第二位 agent 逐條對官方文件查核並修正，見文末「查核紀錄（2026-10-28）」。

---

## 0. 結論（影響架構的部分）

| # | 事實 | 對 pickfit 的意思 |
|---|---|---|
| 1 | 官方文件在 `https://dev.meta.ai/docs`。舊網址 `ai.developer.meta.com/docs`、`llama.developer.meta.com/docs` 都轉址過來。每頁網址加 `.md` 就有純文字版，索引在 `https://dev.meta.ai/llms.txt` | 之後查文件直接 curl `.md`，不必爬 HTML |
| 2 | API 與 OpenAI 相容：base URL `https://api.meta.ai/v1`，有 `/chat/completions` 和 `/responses`；另有 Anthropic 相容的 `/v1/messages` | 不需要專用 SDK；Python 用 `openai` 套件改 `base_url` 就好 |
| 3 | 主力模型 `muse-spark-1.3`：吃文字、圖片、影片、PDF（音訊在 1.3 品質會變差），支援 tool calling、JSON schema（constrained decoding）、streaming，context 1,048,576 | 抽取、截圖判讀、配對都能用同一個模型 |
| 4 | 價格：`muse-spark-1.3` 每百萬 token input $1.25 / cached $0.15 / output $4.25；Contributor 版 `muse-spark-1.3-contributor` 為 $0.10 / $0.002 / $0.20 | Contributor 版輸入便宜 12.5 倍、輸出 21 倍，但 150 RPM、內容可能被 Meta 拿去訓練、不可送個資 |
| 5 | Muse Spark Open、Muse Glimmer 是開放權重，**不在 Meta Model API 上** | 要另外走 Baseten / Modal / Together 等，或自架 |
| 6 | Baseten、Modal 上 Muse Spark Open 的價格 = Meta 標準版（$1.25 / $0.15 / $4.25） | 開放權重路徑不會比 Meta API 便宜，用途是爭取 Open Weight 獎與展示 |
| 7 | `tool_choice` 只能是 `"auto"`；`stop`、`n>1`、`logprobs` 都會回 400 | 不能強制模型呼叫某工具；要固定格式就用 structured output |
| 8 | Muse Spark 一定會推理（`reasoning_effort: "none"` 回 400），推理 token 算輸出費用 | 大量初篩要設 `minimal` 或 `low`，並把推理成本算進預算 |
| 9 | Chat Completions 不跨回合保留推理；官方建議多步工具迴圈用 Responses API | 驗證 agent（安裝、讀錯誤、修正）用 Responses API |
| 10 | 沒有硬性花費上限；Spend Limit 只寄 email | 程式要自己記帳、超過門檻就停 |
| 11 | 文件沒有 Batch API 端點；長任務用 Responses 的 `background: true` | 大量處理就是並行呼叫 + rate limit 控制 |
| 12 | 台灣不在地理限制名單。7/8 上線時只開放美國；8/5 Muse Code 部落格宣布「expanding global access」。Help Center：在「Meta AI 可用且支援付款」的地區開放，以地理政策為準 | 台灣帳號能不能註冊與付款：**未驗證**，申請時第一件事確認 |
| 13 | $150 credits 的 Credit Terms（公開 PDF）：用表單申領，要填 Team ID；11/4 9:00 PM ET 截止；2 個工作天內入帳；入帳後不過期；先扣 credits 再扣卡 | 先註冊、綁卡、抄 Team ID，再填表；用完會直接刷卡 |

---

## 1. 官方文件位置

| 用途 | URL |
|---|---|
| 文件首頁 | https://dev.meta.ai/docs |
| 文件索引（給 agent 讀） | https://dev.meta.ai/llms.txt |
| 任一頁的 Markdown | 網址加 `.md`，例如 https://dev.meta.ai/docs/models.md |
| API reference | https://dev.meta.ai/docs/api-reference |
| Help Center（帳號、Billing、rate limit） | https://dev.meta.ai/help |
| Dashboard（註冊、API key、Billing、Usage） | https://dev.meta.ai/ |
| Meta 的比賽頁 | https://dev.meta.ai/events/global-hackathon |
| 服務狀態（免認證） | https://api.meta.ai/v1/status |

轉址（curl -L 實測）：`https://ai.developer.meta.com/docs/models/` → `https://dev.meta.ai/docs/models`；`https://llama.developer.meta.com/docs/` → `https://dev.meta.ai/docs/overview`。
Llama 不在 Model API 上（Help Center「Is Llama available on Meta Model API?」）。

---

## 2. 模型清單

### 2.1 能力表

「Meta API」= Meta Model API（`api.meta.ai`）。「開放權重」= 不在 Meta API 上，要自架或走第三方。

| 模型 | model ID（請求裡填的字串） | 在哪 | 輸入 | 輸出 | tool calling | JSON schema | streaming | context | 最大輸出 |
|---|---|---|---|---|---|---|---|---|---|
| Muse Spark 1.3 | `muse-spark-1.3` | Meta API | 文字、圖片、影片、音訊¹、PDF | 文字 | 有 | 有 | 有 | 1,048,576 | 131,072²（未驗證） |
| Muse Spark 1.3 Contributor | `muse-spark-1.3-contributor` | Meta API | 同上 | 文字 | 有 | 有 | 有 | 1,048,576 | 131,072²（未驗證） |
| Muse Spark 1.2 | `muse-spark-1.2` | Meta API | 文字、圖片、影片、音訊、PDF | 文字 | 有 | 有 | 有 | 1,048,576 | 未驗證 |
| Muse Spark 1.2 Contributor | `muse-spark-1.2-contributor` | Meta API | 同上 | 文字 | 有 | 有 | 有 | 1,048,576 | 未驗證 |
| Muse Spark 1.1 | `muse-spark-1.1` | Meta API | 文字、圖片、影片、音訊、PDF | 文字 | 有 | 有 | 有 | 1,048,576 | 未驗證 |
| Muse Wonder（preview） | `muse-wonder-1.0` | Meta API；南韓不可用（出自 models.md，地理政策沒列） | 文字、圖片、影片、音訊、PDF | 文字 | 有 | 有 | 有 | 1,048,576 | 未驗證 |
| Muse Image | `muse-image-1.0` | Meta API；印度不可用 | 文字、圖片 | 圖片 | — | — | 未查 | — | — |
| Muse Voice Transcribe | `muse-voice-transcribe-1.0` | Meta API（`/v1/asr/*`） | 音訊 | 逐字稿 | 無 | 無 | 有（WebSocket、SSE） | — | — |
| SAM 3.1 | `sam-3.1` | Meta API（Responses） | 文字提示、圖片、影片 | 框與遮罩 | — | — | 有 | — | — |
| Muse Spark Open | HF：`meta-models/Muse-Spark-Open-816B-A42B`（`-NVFP4`）；Baseten/Together/Groq/Nebius：`meta-models/muse-spark-open`；Fireworks：`accounts/fireworks/models/muse-spark-open` | 開放權重 | 文字、圖片、影片、音訊（依託管商⁴） | 文字 | 有（vLLM/SGLang 用 `--tool-call-parser muse`） | 看 runtime³ | 看 runtime | 1,048,576（Groq 上 131,072⁴） | 未驗證 |
| Muse Glimmer | HF / Together：`meta-models/Muse-Glimmer-30B` | 開放權重 | 文字、圖片 | 文字 | 有，一回合只能一個 call，不支援平行 | 看 runtime，未驗證 | 看 runtime | 預設 128K（可設更長） | 未驗證 |

1. Muse Spark 1.3 的音訊理解「not fully supported」，品質可能變差；官方建議音訊用 1.2 或 Muse Voice Transcribe。
2. **未驗證**。131,072 只出現在 quickstart 與 coding-agents 頁的設定範例（`Limits: context 1048576, output 131072`），不是規格表。API reference 只寫「超過 model's configured maximum 回 400」，沒給數字；`GET /v1/models` 的 Model 物件也沒有 context / 輸出上限欄位。輸出上限和輸入共用 context，`input + max_output` 不能超過 1,048,576（error-handling.md）。
3. TensorRT-LLM 文件寫支援 JSON mode 與 JSON schema（xgrammar）。Baseten 部落格寫支援 tool calling、reasoning output、1M context；Baseten、Modal 上是否支援 `json_schema`：未驗證。
4. 依 muse-spark-open/deploy.md：Baseten 收文字、圖片、影片、音訊，1M context；Fireworks 寫「text and images」，1M context；Groq 上 context 131,072，支援 tool calling、structured outputs、圖片輸入。

各版本差異：
- `muse-spark-1.3`：官方「Recommended for new work」，支援 `reasoning_effort: "max"`（`muse-wonder-1.0` 也支援；`muse-spark-1.3-contributor` 不支援 `max`）。
- `muse-spark-1.1`：只有 Standard 版，不在 Muse Code 裡。
- Muse Wonder：最強、最貴，Model API 上只有 Standard 版；Muse Wonder Full 只在 Muse Code 訂閱。

### 2.2 價格與 rate limit

Rate limit 以 **team** 計，不是以 key 計；每個模型各自獨立。

| model ID | input / 1M | cached input / 1M | output / 1M | RPM | TPM | 其他 |
|---|---|---|---|---|---|---|
| `muse-wonder-1.0` | $4.00 | $0.20 | $20.00 | 3,000 | 4,000,000 | |
| `muse-spark-1.3`、`1.2`、`1.1` | $1.25 | $0.15 | $4.25 | 3,000 | 4,000,000 | |
| `muse-spark-1.3-contributor`、`1.2-contributor` | $0.10 | $0.002 | $0.20 | **150** | 3,000,000 | 內容可能用於訓練 |
| `muse-image-1.0` | $0.01 / 張 | | | 150 | 無 | |
| `muse-voice-transcribe-1.0` | $0.18 / 小時音訊（約 $0.003 / 分鐘），整秒計 | | | 無 | 無 | 同時 256 串流；每小時 16,000 串流 |
| `sam-3.1` | 圖片 $2.50 / 1,000 張；影片 $0.20 / 1,000 幀（每次至少 50 幀） | | | 3,000 | 無 | |
| `web_search` 內建工具 | $2.50 / 1,000 次搜尋，另計 token | | | | | 只在 Responses、Messages |
| Muse Spark Open @ Baseten | $1.25 | $0.15 | $4.25 | | | 比賽 credits 附 2M TPM |
| Muse Spark Open @ Modal Shared Endpoint | $1.25 | $0.15 | $4.25 | | | |
| Muse Glimmer @ Together | $0.35 | $0.04 | $1.50 | | | Meta 文件轉載 Together 頁面的數字 |

其他計費規則：
- 長 context 不加價（pricing 頁）。
- 推理 token 算在 output 並計費（reasoning.md；quickstart 的 `usage` 範例也算在 `output_tokens`）。pricing 頁本身沒寫這條。
- Meta 會在每個 prompt 注入少量 steering context，不計費、也不算進 `usage`（pricing 頁）。
- Muse Voice Transcribe、Muse Wonder 在 Model API 上沒有 Contributor 版（pricing 頁）。

---

## 3. 四個模型的實際能力

### 3.1 Muse Spark（1.1 / 1.2 / 1.3）

| 項目 | 內容 |
|---|---|
| 取得方式 | 只在 Meta Model API（與 Muse Code）；無權重 |
| 輸入 / 輸出 | 文字、圖片、影片（mp4）、音訊（mp3、wav）、PDF → 文字 |
| 推理 | 永遠推理。Chat 用頂層 `reasoning_effort`，Responses 用 `reasoning.effort`。值：`minimal`、`low`、`medium`、`high`、`xhigh`、`max`（Muse Spark 只有 `muse-spark-1.3` 支援，Contributor 版不行）；`none` 回 400 |
| 功能 | tool calling、structured output、streaming、prompt caching、search grounding（Responses/Messages）、computer-use 工具（Responses）、圖片定位（0–1000 座標） |
| 取樣 | `temperature` 預設 1.0，官方建議不要調；不支援 `stop`、`n>1`、`logprobs`、`logit_bias`、`frequency_penalty`、`presence_penalty` |
| Standard vs Contributor | 用 model ID 切換。Contributor 版內容可能被用來訓練（"may be used to train future Meta models"）；Help Center 要求不得送個資或機密；ZDR team 不能用 |

### 3.2 Muse Spark Open（開放權重）

| 項目 | 內容 |
|---|---|
| 架構 | 816B MoE，42B active；1,048,576 context；文字、圖片、音訊、影片輸入 |
| 授權 | Muse Model License + Acceptable Use Policy（**不是** Apache） |
| 權重大小 | BF16 約 1.65 TB（8×B300）；NVFP4 約 537 GB（單一 4-GPU Blackwell 節點）。個人自架不實際 |
| 託管 | Together、Fireworks、Baseten、Groq（需核准）、Nebius、Modal、OpenRouter |
| 比賽 credits | Baseten $100 + 2M TPM；Modal $100；Fireworks $25。公開活動頁只寫「select participants」；「Baseten 限 2,000 人、Modal 前 1,000 人」出自需登入的 Participant Guide（未驗證） |
| Baseten model ID | 公開文件：`meta-models/muse-spark-open`；hackathon-rules 第 6 節：比賽要用 `meta-models/muse-spark-open-1026`（來自需登入的 Participant Guide，未驗證） |
| 與 Muse Spark 1.x 的對應 | 文件沒寫是哪一版（未驗證） |

### 3.3 Muse Glimmer（開放權重）

| 項目 | 內容 |
|---|---|
| 架構 | 30B dense，從 Muse Spark 蒸餾；文字 + 圖片輸入；預設 128K context |
| 授權 | Apache 2.0 |
| Tool calling | 原生 ATEM 格式；vLLM、llama.cpp 會轉成標準 `tool_calls`。**一回合只能一個工具，不支援平行** |
| 硬體 | bf16 約 60 GB；GGUF `Q4_K_M` 約 17 GB（< 24 GB VRAM），另需 1.4 GB vision projector |
| 託管 | 官方文件只列 Together AI。Baseten 沒有 Glimmer 頁；Modal 的 `library/meta/muse-glimmer` 是 404 |
| 對 brief 的修正 | brief 第 6 節寫「Muse Spark Open 或 Muse Glimmer（透過 Baseten 或 Modal）」：Baseten、Modal 只託管 Spark Open；Glimmer 在 Modal 上要自己用 vLLM / llama.cpp 起 GPU 服務 |

### 3.4 Muse Voice Transcribe

| 項目 | 內容 |
|---|---|
| 取得方式 | 只在 Meta Model API |
| 能做 | 語音轉文字；說話者分離；VAD / endpointing；`languageBias`、`keywords` 偏置；turn 級時間戳 |
| 不能做 | TTS、speech-to-speech、字級時間戳、信心分數 |
| 語言 | 25 種，含 Mandarin Chinese、English、Japanese、Korean，支援 code-switching |
| 即時 | `wss://api.meta.ai/v1/asr/realtime`；送 16-bit mono PCM（16 或 24 kHz）；一個 session 最長 60 分鐘 |
| 檔案 | `POST /v1/asr/transcribe`（multipart）；**只吃 WAV**（mono、16-bit PCM、16 或 24 kHz）；≤ 10 分鐘；≤ 32 MB |
| tool / JSON | 不支援 tool calling，也沒有 JSON schema 結構化輸出。回應格式由 `Accept` 選：JSON（預設，含 `turns`）、SSE、純文字 |
| 計價 | $0.18 / 小時音訊，整秒計；沒有 Contributor 版 |
| 對 pickfit | brief 的「作者影片介紹轉文字」可改用 `muse-spark-1.2` 直接讀 mp4（影片內音訊會一起讀），少一步轉檔；Voice Transcribe 留給需要逐字稿的情況 |

---

## 4. API 用法

### 4.1 基本設定

| 項目 | 值 |
|---|---|
| Base URL | `https://api.meta.ai/v1` |
| 認證 | `Authorization: Bearer $MODEL_API_KEY` |
| Key 格式 | `LLM_<數字ID>_<secret>` |
| 官方環境變數名 | `MODEL_API_KEY`（OpenAI SDK 不會自動讀，要明確傳 `api_key`） |
| Python SDK | `pip install openai`，`OpenAI(base_url="https://api.meta.ai/v1", api_key=...)` |
| TypeScript SDK | `npm install openai`，同上 |
| Anthropic SDK | `base_url="https://api.meta.ai"`（不含 `/v1`），key 傳 `auth_token` |
| LiteLLM | `model="openai/muse-spark-1.3"`, `api_base="https://api.meta.ai/v1"` |
| Meta 自己的套件 | 只有 SAM 解析器：`meta_sam_parser`（Python）、`@meta-sam/parser`（TS） |

未認證請求的實際回應（2026-10-28 curl）：

```
GET https://api.meta.ai/v1/models          → 401 {"error":{"code":"invalid_api_key","message":"Unauthorized","param":null,"type":"authentication_error"}}
POST https://api.meta.ai/v1/chat/completions → 401（同上）
GET https://api.meta.ai/v1/status          → 200 {"is_alive":true,"service_status":"operational",...}
```

### 4.2 端點

| 端點 | 用途 |
|---|---|
| `POST /v1/chat/completions` | OpenAI Chat Completions 相容 |
| `POST /v1/responses`、`GET`/`DELETE /v1/responses/{id}`、`POST /v1/responses/{id}/cancel` | OpenAI Responses 相容；官方推薦的預設 |
| `POST /v1/responses/input_tokens` | 推論前算 input token |
| `POST /v1/messages`、`POST /v1/messages/count_tokens` | Anthropic Messages 相容 |
| `POST`/`GET /v1/files`、`GET`/`DELETE /v1/files/{id}`、`GET /v1/files/{id}/content` | 上傳檔案（`purpose`：`user_data` 或 `batch`） |
| `GET /v1/models`、`GET /v1/models/{model}` | 列出可用模型（需認證） |
| `POST /v1/images/generations`、`POST /v1/images/edits` | Muse Image |
| `POST /v1/asr/transcribe`、`wss://api.meta.ai/v1/asr/realtime` | Muse Voice Transcribe |
| `GET /v1/status` | 健康檢查，免認證 |

### 4.3 三種協定的差異

| | Responses | Chat Completions | Messages |
|---|---|---|---|
| 推理跨回合保留 | 有（加密 replay 或 `previous_response_id`） | **沒有** | 有（`thinking` replay） |
| search grounding（`web_search`） | 有 | 沒有 | 有 |
| `custom`（自由文字）工具 | 有 | 沒有（400） | 未查 |
| computer-use 工具 | 有（唯一支援） | 沒有 | 未查 |
| `background: true` 長任務 | 有 | 沒有 | 沒有 |
| 結構化輸出參數 | `text.format` | `response_format` | 未查 |
| 價格 | 相同 | 相同 | 相同 |

注意：`include: ["reasoning.encrypted_content"]` 不能和 `previous_response_id` 同時用（400）。

### 4.4 功能細節

| 功能 | 支援情況 |
|---|---|
| 結構化輸出 | Chat：`response_format: {"type":"json_schema","json_schema":{"name","schema","strict"}}`；Responses：`text.format: {"type":"json_schema","name","schema","strict"}`。兩邊參數不能混用（Responses 收到 `response_format` 不會生效）。也有舊的 `{"type":"json_object"}`，**只保證是合法 JSON，不保證符合 schema**。`json_schema` 的 **decoding 受 schema 約束，保證符合**。不支援遞迴 schema（400）。上限：巢狀 10 層、5,000 個 property、字串總長 120,000、enum 值共 1,000 個（可申請調高）；超過回 400。這些上限也套用在 function tool 的 `parameters` |
| `strict` | 預設 `false`。對結構化輸出，`false` 與 `true` 的輸出一樣受約束；`true` 只多做 schema 子集檢查（`additionalProperties: false`、`required` 列出全部 key） |
| Tool calling | `tools`（`function` 型）；Chat 包在 `function` 底下，Responses 是平的。`tool_choice` 只能 `auto`；`parallel_tool_calls` 預設 `true`；函式名稱最多一個 `.`。**參數不保證符合 schema，要自己驗證** |
| 內建工具 | `web_search`、`tool_search`（Responses/Messages）、`computer`（Responses） |
| Streaming | `stream: true`，SSE。非 streaming 請求有伺服器時間上限，超過回 504 `gateway_timeout`；streaming 只要第一個事件準時就不受限；`background: true` 兩種上限都不受（error-handling.md） |
| Prompt caching | 自動前綴快取，不用設定。`usage.prompt_tokens_details.cached_tokens`（Chat）/ `usage.input_tokens_details.cached_tokens`（Responses）。可選 `prompt_cache_key`、`prompt_cache_retention: "24h"`（提示，不保證） |
| Batch | 文件索引（`llms.txt`）與 `sitemap.xml` 都沒有 batch 端點頁；`/docs/api-reference/batches.md` 回 404。Files schema 的 `purpose=batch` 寫「for Batch input files」，但沒有對應端點文件。`/v1/batches` 是否存在：**未驗證**（未帶 key 任何路徑都回 401）。可用替代：Responses `background: true`（每 team 每分鐘 600 次提交；建立請求的 body 上限 **1 MiB**，大檔改用 `file_id`；不能同時 `stream: true`） |
| Token 計算 | `POST /v1/responses/input_tokens`；`POST /v1/messages/count_tokens` |
| 檔案 | inline ≤ 50 MB；Files API ≤ 1 GiB；team 總量 100 GiB；上傳檔預設不過期，可設 `expires_after`（1 小時–30 天） |
| PDF | 前 100 頁抽文字，前 50 頁轉圖 |

### 4.5 圖片輸入

| 項目 | 內容 |
|---|---|
| Chat 格式 | `{"type":"image_url","image_url":{"url":"https://..." 或 "data:image/png;base64,...","detail":"auto|low|high"}}` |
| Responses 格式 | `{"type":"input_image","image_url":"https://... 或 data:..."}`，或 `{"type":"input_image","file_id":"file-..."}` |
| 位置 | **只能放在 `user` 訊息** |
| 單張大小 | inline（URL 或 base64）≤ 50 MB；Files API ≤ 1 GiB |
| 每次請求張數 | ≤ 50 張（超過回 400） |
| MIME | `image/jpeg`、`image/jpg`、`image/png`、`image/gif`、`image/webp`、`image/x-icon` |
| Token 估計 | 約 1280px 的圖 ≈ 1,300–1,500 tokens；1×1 ≈ 3 tokens |
| 定位 | 可要求回傳 0–1000 正規化座標（點、框、計數） |
| computer-use 截圖 | base64 PNG/JPEG，≤ 25 MiB |

### 4.6 最小 curl 範例

先設好 key（官方變數名；spike 也接受 `META_API_KEY`）：

```bash
export MODEL_API_KEY="LLM_..."
```

文字：

```bash
curl https://api.meta.ai/v1/chat/completions \
  -H "Authorization: Bearer $MODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "muse-spark-1.3",
    "reasoning_effort": "low",
    "messages": [{"role": "user", "content": "What does a package manager do? One sentence."}]
  }'
```

JSON schema 結構化輸出：

```bash
curl https://api.meta.ai/v1/chat/completions \
  -H "Authorization: Bearer $MODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "muse-spark-1.3",
    "reasoning_effort": "low",
    "messages": [
      {"role": "developer", "content": "Extract a software profile from the README."},
      {"role": "user", "content": "# tinyq\nA tiny jq alternative in Rust. brew install someone/tap/tinyq. MIT."}
    ],
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "software_profile",
        "strict": true,
        "schema": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "install_commands": {"type": "array", "items": {"type": "string"}},
            "license": {"type": ["string", "null"]}
          },
          "required": ["name", "install_commands", "license"],
          "additionalProperties": false
        }
      }
    }
  }'
# 結果是 choices[0].message.content 裡的 JSON 字串
```

Tool calling（第一輪）：

```bash
curl https://api.meta.ai/v1/chat/completions \
  -H "Authorization: Bearer $MODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "muse-spark-1.3",
    "messages": [{"role": "user", "content": "How many stars does someone/tinyq have?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_repo_stats",
        "description": "Return GitHub stars and last release date for a repository.",
        "parameters": {
          "type": "object",
          "properties": {"repo": {"type": "string", "description": "owner/name"}},
          "required": ["repo"]
        }
      }
    }]
  }'
# finish_reason 為 "tool_calls" 時，把整個 assistant 訊息（含 tool_calls）加回 messages，
# 每個 call 再加一則 {"role":"tool","tool_call_id":...,"content":...}，送第二輪。
```

圖片（base64；本機截圖）：

```bash
IMG_B64=$(base64 < screenshot.png | tr -d '\n')
curl https://api.meta.ai/v1/chat/completions \
  -H "Authorization: Bearer $MODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "model": "muse-spark-1.3",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "Is this CLI running successfully? Answer yes or no and why."},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,${IMG_B64}"}}
    ]
  }]
}
EOF
```

Responses API（最小）：

```bash
curl https://api.meta.ai/v1/responses \
  -H "Authorization: Bearer $MODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "muse-spark-1.3", "input": "What is the capital of France?"}'
```

健康檢查（免 key）：

```bash
curl https://api.meta.ai/v1/status
```

可直接跑的版本：`spikes/meta_api_hello.py`（只用標準函式庫；未實測）。

### 4.7 錯誤處理

| 狀態 | 意思 | 處理 |
|---|---|---|
| 400 | 參數不支援、對話結構錯（例如 tool 結果沒配對）、`input + max_output` 超過 context | 修請求，不要重試 |
| 401 `invalid_api_key` | key 沒設或錯 | 檢查 `MODEL_API_KEY` |
| 404 `model_not_found` | model ID 打錯 | 用 `GET /v1/models` 確認 |
| 429 | 超過 rate limit | 指數退避 + jitter；看 `Retry-After` |
| 504 `gateway_timeout` | 非 streaming 請求超時 | 不要直接重試；改 `stream: true`、`background: true`，或降低 `reasoning_effort` |

成功回應帶 `x-ratelimit-limit-tokens`、`x-ratelimit-remaining-tokens`、`x-ratelimit-limit-requests`、`x-ratelimit-remaining-requests`。

---

## 5. 申請 key 與比賽 $150 credits

| 步驟 | 做法 | 來源 |
|---|---|---|
| 1. 註冊 | https://dev.meta.ai/ → **Start building** → 保持 **Individual** → 用 email/手機，或 Facebook / Google / GitHub 登入。需年滿 18、在支援地區 | Help：sign-up |
| 2. 綁卡 | **Billing** → **Add payment method** → 填卡 → Save → 填 business information（非公司就填本名與郵寄地址）。所有帳號都要有付款方式才能用（Credit Terms 1.2）。「綁卡會有暫時預授權」只出現在 Participant Guide，公開文件沒寫（未驗證） | Help：set-up-billing；Credit Terms |
| 3. 建 key | **API keys** → **Create API key** → 命名 → 複製（只顯示一次） | Help：create-api-key；Docs：authentication |
| 4. 領 $150 credits | 用「Claim Form」申領（表單連結在錄取後的 know-before-you-go email，公開頁沒有）。要填姓名、報名用的 email、**帳號的 Team ID**。每人一份、每帳號一份，隊員各自領。截止 **2026-11-04 9:00 PM ET**。核准後 2 個工作天內入帳（分批，量大會更久）。入帳後**不過期**。可用於 API Terms 允許的任何 Services 用途（條款沒排除 Contributor 版與 `web_search`）。credits 先扣，用完直接刷卡、按標準價 | Credit Terms PDF（連結見第 9 節）；公開活動頁的 Official Rules 另寫「valid for a 10-day development window」，與 Credit Terms 3.5「不過期」矛盾，以 Credit Terms 為準但不要依賴 |
| 5. 設 Spend Limit | **Billing** → **Spend Limits** 設每月金額。**只寄 email，不會停止扣款**；超過的費用仍要付 | Help：spend-limit-alert |
| 6. 看用量 | **Usage** 頁可按模型、日期看 token 與請求數；**Limits** 頁看本 team 的 RPM/TPM | Help：api-usage、rate-limits |
| 7. 本機設定 | key 放 repo 根目錄 `.env`（`.gitignore` 已有 `.env*`），變數名 `MODEL_API_KEY` | — |

扣款方式：用量累積，達到 payment threshold 就扣，其餘每月 1 號扣（Help：api-bill）。

自保建議：
- 程式裡做預算守門：每次呼叫讀 `usage`，依第 2.2 節單價累計，超過門檻（例如 $120）就停。
- 發現、驗證、配對各用一把 key，出事可單獨撤銷（rate limit 仍是整個 team 共用）。
- 大量跑之前，先用 `POST /v1/responses/input_tokens` 量幾筆實際 token。

---

## 6. 對 pickfit 的用法建議

給 `docs/research/architecture.md` D 節參考，不在這裡做最終決定。

| 環節 | 建議模型 | API | 理由 |
|---|---|---|---|
| 讀懂與抽取（README → 結構化檔案） | `muse-spark-1.3-contributor`（只送公開 README）；品質不夠再換 `muse-spark-1.3` | Chat + `json_schema` | schema 保證可 parse；便宜 |
| 驗證 agent（照 README 安裝、讀錯誤、修正） | `muse-spark-1.3` | Responses + function tools + 加密推理 replay | 多步工具迴圈要跨回合推理 |
| 截圖判讀 | `muse-spark-1.3` | base64 圖片 + `json_schema` | 一張約 1.4K tokens |
| 配對（MCP 背後） | `muse-spark-1.3`（Standard） | Chat + `json_schema` | 使用者需求可能含個資，不能用 Contributor；`tool_choice` 不能強制，用 structured output 產出推薦 |
| 大量初篩（爭取 Open Weight 獎） | Muse Spark Open @ Baseten（比賽 credits），或 Muse Glimmer @ Together / Modal 自架 | OpenAI 相容 chat | 成本不比 Contributor 低；價值在「用開放權重模型」 |
| （選用）作者影片 | `muse-spark-1.2` 直接讀 mp4，或 `muse-voice-transcribe-1.0` | Chat / ASR | 1.3 音訊品質有警告 |

成本估算（**估算，未實測**；output 含推理 token，1,500 是猜的）：

| 工作 | 模型 | 每筆 token（in / out） | 每筆約 | $150 約可跑 |
|---|---|---|---|---|
| README 抽取 | `muse-spark-1.3` | 4,000 / 1,500 | $0.011 | 13,000 筆 |
| README 抽取 | `muse-spark-1.3-contributor` | 4,000 / 1,500 | $0.0007 | 210,000 筆（但 150 RPM，每小時最多 9,000 筆） |
| README 抽取 | Spark Open @ Baseten / Modal | 4,000 / 1,500 | $0.011 | 用合作夥伴 credits |
| README 抽取 | Glimmer @ Together | 4,000 / 1,500 | $0.0037 | 無比賽 credits |
| 截圖判讀 | `muse-spark-1.3` | 1,900 / 1,000 | $0.0066 | 22,000 張 |

官方 quickstart 的參考值：問「法國首都」在 `high` 推理下用了 258 output tokens，其中 241 是推理。

Use of Meta AI Tooling（25%）可展示、且有文件支持的能力：constrained JSON schema、多步 tool calling、截圖判讀與 0–1000 座標定位、computer-use 工具（GUI 驗證，Responses only）、`web_search` 內建搜尋（發現階段，$2.50 / 1,000 次）。

---

## 7. 限制與注意事項

- **永遠推理**：不能關；推理 token 計費；`max_completion_tokens` 包含推理，設太小會拿到空答案（`finish_reason: length`）。影片與音訊文件建議至少設 4,000。
- **`tool_choice` 只能 `auto`**：模型可能不呼叫工具，程式要同時處理「有 tool_calls」與「直接回文字」。
- **工具參數不保證符合 schema**：`strict` 只管 schema 檢查，參數仍要自己驗證。
- **Chat Completions 結構驗證較嚴**：assistant 的 `tool_calls` 與後面的 `tool` 結果要一一配對，否則 400。
- **不支援的參數會 400**：`stop`、`n>1`、`logprobs`、`logit_bias`、`modalities`、`verbosity`、`prediction`、`web_search_options`；`frequency_penalty`、`presence_penalty` 不要設。
- **非 streaming 有時間上限**（秒數文件沒寫）：長輸出用 streaming 或 `background`。
- **Contributor 版**：150 RPM；內容可能被用來訓練；Help Center 要求不得送個資或機密；ZDR team 不能用。
- **地區**：限制名單沒有台灣（Geographic Use Policy，2026-10-12 更新；第 2.2 節只列 Muse Image：印度）。Muse Wonder 南韓不可用出自 models.md。Help Center 寫「在 Meta AI 可用且支援付款的國家開放」，台灣實際能否註冊仍未驗證。Credit Terms 1.1(c) 要求居住地在地理政策允許的國家。
- **服務條款**（Help Center 的 Contributor mode 頁所摘要的條款）：開發者與最終使用者都須滿 18 歲；產品要有隱私權政策。完整條款見 https://dev.meta.ai/legal/terms-of-service（未逐條讀）。
- **沒有硬性花費上限**。
- **Muse Glimmer** 不支援平行工具呼叫；預設 context 只有 128K。
- **開放權重的託管價格**和 Meta 標準版一樣，不是省錢手段。

---

## 8. 未驗證清單

| # | 項目 | 為什麼未驗證 / 怎麼確認 |
|---|---|---|
| 1 | 所有模型呼叫（spike 四個測試） | 沒有 key。拿到 key 後跑 `python3 spikes/meta_api_hello.py` |
| 2 | 台灣帳號能否註冊、綁卡 | 7/8 部落格說 public preview 只開放美國；8/5 Muse Code 部落格說擴大到全球（沒列國家）；現行地理政策沒限制台灣；Help Center 另以「Meta AI 可用且支援付款」為條件。註冊時確認 |
| 3 | $150 credits 的表單網址、實際入帳畫面、Contributor 版實際能否扣抵 | Credit Terms 已確認：表單在錄取 email、要 Team ID、可用於任何 Services 用途。表單網址與實際扣抵要領到後看 Billing 頁 |
| 4 | 綁卡預授權金額 | 公開文件沒寫；只出現在 Participant Guide |
| 5 | 最大輸出 token 的正式數字 | 131,072 只出現在 agent 設定範例；Muse Wonder、1.1、1.2 沒寫 |
| 6 | Batch API 是否存在 | Files API 接受 `purpose=batch`，但 `llms.txt`、`sitemap.xml` 都沒有 batch 端點頁；未認證時任何路徑（含 `/v1/batches`）都回 401，無法從外部判斷 |
| 7 | Baseten 比賽用 model ID `meta-models/muse-spark-open-1026` | 只出現在 Participant Guide；公開文件是 `meta-models/muse-spark-open` |
| 8 | Baseten / Modal 上 Spark Open 的 `json_schema` 支援 | Baseten 部落格已寫支援 tool calling；`json_schema` 兩家都沒寫。Modal 的 tool calling 也沒寫 |
| 9 | Muse Glimmer 在 vLLM / llama.cpp 的 structured output | 文件只提 tool calling |
| 10 | Muse Spark Open 對應哪個 Muse Spark 版本 | 文件沒寫 |
| 11 | 各模型知識截止日 | Help Center 說看 Models 頁，但 Models 頁沒寫。對 pickfit 很重要（「模型不認識今年的專案」） |
| 12 | 非 streaming 請求的時間上限秒數 | 文件沒寫 |
| 13 | 新帳號是否有較低的 rate limit | 文件只列一組數字；以 Dashboard 的 Limits 頁為準 |
| 14 | Meta 官方 GitHub 組織 `github.com/meta-models` 的 repo 清單 | 本環境的 GitHub 存取受限，沒查到；文件說不需要專用 SDK |
| 15 | 新帳號送 $20 credits | 只見於第三方新聞（americancompanies.com），官方文件沒寫 |
| 16 | Voice Transcribe 的 Mandarin 是否輸出繁體字 | 文件只寫「Mandarin Chinese」 |
| 17 | $150 credits 的有效期 | Credit Terms 3.5 寫入帳後不過期；公開活動頁 Official Rules 寫「valid for a 10-day development window」。兩者矛盾，比賽期間用完最保險 |

---

## 9. 來源

查證日皆為 2026-10-28。除特別標註外都是 Meta 官方文件。

| 主題 | URL |
|---|---|
| 文件索引 | https://dev.meta.ai/llms.txt |
| 模型總覽、model ID、可用性 | https://dev.meta.ai/docs/models.md |
| 價格與 rate limit | https://dev.meta.ai/docs/pricing-rate-limits.md |
| Quickstart（base URL、key、輸出上限範例） | https://dev.meta.ai/docs/quickstart.md |
| Coding agents（context / output 設定） | https://dev.meta.ai/docs/coding-agents.md |
| 認證 | https://dev.meta.ai/docs/authentication.md |
| SDK | https://dev.meta.ai/docs/sdks.md |
| 三種協定比較 | https://dev.meta.ai/docs/protocols.md |
| Chat Completions | https://dev.meta.ai/docs/protocols/chat-completions.md |
| Chat Completions schema（`json_object`、`detail`） | https://dev.meta.ai/docs/api-reference/chat-completions/schemas.md |
| Responses API | https://dev.meta.ai/docs/protocols/responses.md |
| Responses schema（`text.format`） | https://dev.meta.ai/docs/api-reference/responses/schemas.md |
| Messages API | https://dev.meta.ai/docs/protocols/messages.md |
| API reference 總覽 | https://dev.meta.ai/docs/api-reference.md |
| 結構化輸出 | https://dev.meta.ai/docs/structured-output.md |
| Tool calling | https://dev.meta.ai/docs/tool-calling.md |
| 圖片理解 | https://dev.meta.ai/docs/image-understanding.md |
| 檔案處理 | https://dev.meta.ai/docs/file-handling.md |
| Files schema（`purpose=batch`） | https://dev.meta.ai/docs/api-reference/files/schemas.md |
| 影片與音訊理解 | https://dev.meta.ai/docs/video-understanding.md |
| Prompt caching | https://dev.meta.ai/docs/prompt-caching.md |
| 推理 | https://dev.meta.ai/docs/reasoning.md |
| 錯誤處理 | https://dev.meta.ai/docs/error-handling.md |
| Search grounding | https://dev.meta.ai/docs/search-grounding.md |
| Computer use | https://dev.meta.ai/docs/computer-use.md |
| Speech to text | https://dev.meta.ai/docs/speech-to-text.md |
| Voice API（transcribe） | https://dev.meta.ai/docs/api-reference/voice/transcribe.md |
| Status API | https://dev.meta.ai/docs/api-reference/status.md |
| 開放權重總覽 | https://dev.meta.ai/docs/open-weight-models.md |
| Muse Spark Open | https://dev.meta.ai/docs/muse-spark-open.md |
| Muse Spark Open 推論與託管商 | https://dev.meta.ai/docs/muse-spark-open/deploy.md |
| Muse Spark Open 建議設定 | https://dev.meta.ai/docs/muse-spark-open/settings.md |
| Muse Glimmer | https://dev.meta.ai/docs/muse-glimmer.md |
| Muse Glimmer 下載 | https://dev.meta.ai/docs/muse-glimmer/get-the-model.md |
| Muse Glimmer 推論與託管商 | https://dev.meta.ai/docs/muse-glimmer/deploy.md |
| Muse Glimmer prompting（tool calling 限制） | https://dev.meta.ai/docs/muse-glimmer/prompting.md |
| Help：註冊 | https://dev.meta.ai/help/accounts-and-login/sign-up |
| Help：設定 Billing | https://dev.meta.ai/help/billing/set-up-billing |
| Help：Spend limit alert | https://dev.meta.ai/help/billing/spend-limit-alert |
| Help：計費方式 | https://dev.meta.ai/help/billing/api-bill |
| Help：建立 API key | https://dev.meta.ai/help/api-keys/create-api-key |
| Help：rate limits | https://dev.meta.ai/help/usage-and-limits/rate-limits |
| Help：用量 | https://dev.meta.ai/help/usage-and-limits/api-usage |
| Help：Contributor mode | https://dev.meta.ai/help/policies-and-privacy/contributor-tier |
| Help：支援國家 | https://dev.meta.ai/help/accounts-and-login/supported-countries |
| Help：Llama 與 Model API | https://dev.meta.ai/help/about-model-api/llama-and-model-api |
| 地理使用政策（2026-10-12 版） | https://dev.meta.ai/legal/geographic-use-policy |
| Muse Spark 上線部落格（2026-07-08，只開放美國） | https://dev.meta.ai/resources/blog/build-with-muse-spark |
| Muse Code 部落格（2026-08-05，擴大全球開放） | https://dev.meta.ai/resources/blog/build-with-muse-code |
| Help：Zero Data Retention | https://dev.meta.ai/help/policies-and-privacy/zero-data-retention |
| 錯誤處理（504、context 超出） | https://dev.meta.ai/docs/error-handling.md |
| 文件 sitemap（確認沒有 batch 頁） | https://dev.meta.ai/sitemap.xml |
| 比賽 Credit Terms（PDF，Meta 撰寫，連結自 Cerebral Valley 公開頁 Official Rules 的「Credit Terms」；fbcdn 簽名網址會過期，需從活動頁重新點） | https://cerebralvalley.ai/e/meta-ai-developer-hackathon |
| Baseten 上線部落格（第三方，tool calling 與 1M context） | https://www.baseten.co/blog/muse-spark-open-launch/ |
| Muse Spark 1.3 模型頁 | https://dev.meta.ai/models/muse-spark |
| Meta 比賽頁 | https://dev.meta.ai/events/global-hackathon |
| Cerebral Valley 公開活動頁（合作夥伴 credits） | https://cerebralvalley.ai/e/meta-ai-developer-hackathon |
| Baseten：Muse Spark Open（第三方，價格） | https://www.baseten.co/library/muse-spark-open |
| Modal：Muse Spark Open（第三方，價格） | https://modal.com/library/meta/muse-spark-open |
| 新聞：新帳號 $20 credits（第三方，未驗證） | https://americancompanies.com/news/meta-launches-paid-muse-spark-1-1-api-for-developers/ |
| 實測（curl） | `https://api.meta.ai/v1/status`（200）、`https://api.meta.ai/v1/models`（401 `invalid_api_key`） |

---

## 查核紀錄（2026-10-28）

查核者：第二位 agent。方法：用 curl 下載官方 `.md` 文件與 Help Center / legal 頁面重新比對，不採用原筆記的轉述。沒有 API key，沒有呼叫任何模型。

### 重新實測（未帶 key）

| 請求 | 結果 |
|---|---|
| `GET /v1/models` | 401 `{"error":{"code":"invalid_api_key","message":"Unauthorized","param":null,"type":"authentication_error"}}` |
| `POST /v1/chat/completions`、`POST /v1/responses`、`GET /v1/batches` | 401，同上（任何路徑都先擋認證，無法藉此判斷端點存不存在） |
| `POST /v1/messages` | 401，Anthropic 格式：`{"error":{"message":"Unauthorized","type":"authentication_error"},"type":"error"}` |
| `GET /v1/status` | 200 `{"is_alive":true,"service_status":"operational",...}` |
| 舊文件網址 | `ai.developer.meta.com/docs/models/` → `dev.meta.ai/docs/models`；`llama.developer.meta.com/docs/` → `dev.meta.ai/docs/overview` |

### 逐條結果

| # | 主張 | 結果 | 依據 |
|---|---|---|---|
| 1 | base URL `https://api.meta.ai/v1`；Chat / Responses / Messages 三種格式同模型同價 | 確認 | protocols.md、api-reference.md |
| 2 | Bearer 認證、key 格式 `LLM_<數字>_<secret>`、變數名 `MODEL_API_KEY`、用 openai SDK、未帶 key 回 401 | 確認 | authentication.md、sdks.md、api-reference.md、curl |
| 3 | 9 個 model ID；新專案用 `muse-spark-1.3` | 確認 | models.md |
| 4 | Muse Spark 各版本輸入文字/圖/影/音/PDF、1M context、tool calling、structured output；1.3 音訊 not fully supported | 確認（streaming 寫在 protocols / sdks，不在 models.md） | models.md、sdks.md |
| 5 | 最大輸出 131,072 | **仍未驗證**。只在設定範例出現；API reference 只說超過 configured maximum 回 400；`/v1/models` 不回傳上限 | quickstart.md、coding-agents.md、api-reference/responses/schemas.md、api-reference/models/schemas.md |
| 6 | 價格 | 確認。修正來源：「推理 token 算輸出」出自 reasoning.md，不是 pricing 頁 | pricing-rate-limits.md、reasoning.md |
| 7 | Rate limit | 確認（含 background 600 次/分鐘、`x-ratelimit-*` 只在成功的 token 計費回應） | pricing-rate-limits.md |
| 8 | Contributor 版用於訓練、不得送個資、ZDR 不能用 | 確認，措辭修正為「可能被用來訓練」 | pricing-rate-limits.md、Help：contributor-tier、Help：zero-data-retention |
| 9 | 結構化輸出 | 確認。補充：`json_object` 只保證合法 JSON；上限也套用到 tool `parameters` | structured-output.md、chat-completions/schemas.md、responses/schemas.md |
| 10 | Tool calling：`tool_choice` 只能 `auto`、參數不保證符合 schema | 確認 | tool-calling.md |
| 11 | 一定推理；`stop`、`n>1`、`logprobs`、`logit_bias` 400；Chat 不跨回合保留推理 | 確認。補充：Responses 用 `reasoning.effort`；`max` 也支援 `muse-wonder-1.0` | protocols/chat-completions.md、reasoning.md |
| 12 | 圖片輸入限制 | 確認。補上 MIME `image/jpg` | image-understanding.md |
| 13 | 自動前綴快取；沒有 Batch 端點文件；background 600 次/分鐘 | 前兩項確認（llms.txt、sitemap 都沒有 batch 頁）；`/v1/batches` 實際存在與否仍未驗證。補充：background body 上限 1 MiB | prompt-caching.md、files/schemas.md、protocols/responses.md、sitemap.xml |
| 14 | Spark Open / Glimmer 規格、授權、託管商、ID | 確認。補充：Groq 上 context 只有 131,072；Fireworks 只寫文字+圖片 | muse-spark-open.md、muse-spark-open/deploy.md、muse-glimmer.md、muse-glimmer/deploy.md、muse-glimmer/prompting.md |
| 15 | Baseten、Modal 價格 = $1.25 / $0.15 / $4.25 | 確認（第三方頁面） | baseten.co/library/muse-spark-open、modal.com/library/meta/muse-spark-open |
| 16 | 比賽用 `meta-models/muse-spark-open-1026` | **仍未驗證**。公開文件、Baseten 頁、Cerebral Valley 公開頁、網路搜尋都找不到這個字串 | — |
| 17 | Voice Transcribe | 確認。措辭修正：「沒有 JSON 輸出」改為「沒有 JSON schema 結構化輸出」，因為預設回應就是 JSON | models.md、speech-to-text.md、api-reference/voice/transcribe.md |
| 18 | 沒有硬性花費上限 | 確認 | Help：spend-limit-alert |
| 19 | 台灣與地理政策 | 名單部分確認。**補上漏掉的事實**：2026-08-05 Muse Code 部落格宣布擴大到全球；Help 以「Meta AI 可用且支援付款」為條件。台灣能否註冊仍未驗證 | legal/geographic-use-policy、blog/build-with-muse-code、Help：supported-countries |
| 20 | $150 credits | **大部分已可確認**（原筆記標未驗證）：找到 Meta 的公開 Credit Terms PDF。表單在錄取 email、要 Team ID、截止 11/4 9 PM ET、2 個工作天入帳、不過期、可用於任何 Services。預授權、表單網址仍未驗證；10 天效期與不過期互相矛盾 | Credit Terms PDF、Cerebral Valley 公開頁 |

### 沒有發現的問題

- 沒有把舊 Llama API 的資訊套到 Muse 模型（Help Center 也確認 Llama 不在 Model API 上）。
- 沒有發現憑記憶補上的 model ID 或價格；所有數字都能在官方頁面找到。
- 第 6 節成本估算重算過，數字正確（仍是估算）。

## 帶 key 實測（2026-10-28 16:18–17:20 台北）

台灣帳號可用。全部呼叫合計約 US$0.004。

| 項目 | 結果 |
|---|---|
| `GET /v1/models` | 200。`muse-spark-1.3`、`muse-spark-1.3-contributor`、`muse-spark-1.2`、`muse-spark-1.2-contributor`、`muse-spark-1.1`、`muse-wonder-1.0`、`muse-image-1.0`、`muse-voice-transcribe-1.0`、`sam-3.1`。**沒有 embedding 模型** |
| rate limit header | `muse-spark-1.3`：3,000 RPM、4M TPM；`muse-spark-1.3-contributor`：150 RPM、3M TPM |
| 最小呼叫（1.3，`reasoning_effort: minimal`） | 52 token（推理 29）、1.7 秒 |
| `spikes/meta_api_hello.py`（contributor，minimal） | text、json_schema、tools（兩輪）、image（base64 與公開 URL）**4／4 通過**；第二輪 tools 有 497 個 cached token |
| 同上（1.3，minimal） | json_schema、tools **2／2 通過**；json_schema 輸出 240 token（推理 141） |
| `meta_responses_agent_probe.py image_tool`（contributor） | 截圖放在 `function_call_output` 或緊接的 user 訊息，模型**都看得到**（D.4 #3） |
| `… schema_tools` | 同一請求帶 tools 和 `text.format` json_schema **可以**，最後輸出合 schema（D.4 #4） |
| `… loop` | 第一次在第 2 回合回 **503 `persistence service error`**；重跑成功：5 回合後呼叫 `finish`，參數齊全；`cached_tokens` 跨 `previous_response_id` 有效（753 → 1,137）。**每個串接回合 15–18 秒**（第一回合約 2 秒） |
| `… search_probe` | 沒跑（會產生搜尋費用；只有「搜尋可見度」這個超前項目需要） |

對設計的影響：`call_meta` 要重試 503；驗證 agent 的回合延遲要實測比較「`previous_response_id` 串接」與「每回合重送完整歷史」（plan P3.3）；開發與測試用 contributor 可省 12–20 倍。
