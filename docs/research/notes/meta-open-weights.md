# Meta 開放權重模型：Muse Spark Open 與 Muse Glimmer

2026-10-28 查證（台北時間）· 技術調研筆記 · 沒有 API key，所有呼叫都**未實測**。

範圍：模型規格與授權、Baseten／Modal／Fireworks 等推論服務怎麼用、「Best Build on Meta Open Weight Models」的條件，以及 pickfit 的大量初篩要花多少錢、多少時間。

狀態標記：**已確認**＝親自讀過官方文件或 Hugging Face（HF）頁面；**估算**＝自己算的，假設寫在旁邊；**未驗證**＝沒找到第一手資料，或需要金鑰才能確認。

---

## 0. 結論

1. **兩個模型都能讀圖片、都支援 tool calling、都一定會推理（關不掉）。** Spark Open 還能吃影片和音訊。（已確認）
2. **Baseten 上的 Spark Open 不強制 JSON schema。** `json_schema` 和 `json_object` 都收，但不約束輸出。要靠提示詞加程式端驗證，或改用強制 tool calling 來拿結構化結果。（已確認：Baseten 文件；tool calling 是否有約束則未驗證）
3. **用開放權重模型「省錢」這個理由不成立。** Baseten／Modal／Fireworks 上的 Spark Open 牌價都是 $1.25／$4.25 每百萬 token，和 Meta Model API 上的 Muse Spark（Standard 模式）一樣。Muse Spark 的 Contributor 模式反而便宜約 15 倍。走開放權重的理由是：**合作夥伴另外給的 credits、獨立的 rate limit，以及 $10K 的開放權重加碼獎**。（已確認：價格）
   - 查核補註：「獨立的 rate limit」不代表比較高。Meta Model API 的 `muse-spark-1.3` Standard 是 3,000 RPM／4M TPM；Baseten 預設帳號只有 15–120 RPM（見 4.3）。要的是吞吐量，Meta API 反而較寬。（已確認：https://dev.meta.ai/docs/pricing-rate-limits.md ；https://docs.baseten.co/inference/model-apis/pricing-and-limits.md ）
4. **Glimmer 沒有任何比賽合作夥伴提供按 token 計費的服務。** Baseten 和 Modal 只能部署專用 GPU；Fireworks 的 serverless 已在 2026-09-25 下架。按 token 計費的只有 Together 和 DeepInfra，但它們不在比賽的合作夥伴名單上。（已確認）
5. **建議**：大量初篩用 **Baseten 上的 Spark Open**，`reasoning_effort` 一律設 `low`。不自己架 GPU。一個人只有 6 天，架 Glimmer 的時間不划算（第 9 節）。
6. **用 Spark Open 必須在產品或文件中顯示「Built with Muse Spark Open」**（Muse Model License 第 2 條）。README 要加這行。（已確認）
7. 每 1000 筆候選（初篩＋抽取＋去重）約 **430 萬 token、$6.7–7.6、13–110 分鐘**；時間主要卡在 Baseten 的 RPM。$100 credits 約夠處理 1.3 萬筆。（估算，第 8 節）
8. 比賽指定的 `meta-models/muse-spark-open-1026` **不在 Baseten 公開文件裡**。拿到金鑰後要先用 `/v1/models` 確認。（未驗證）

---

## 1. 模型規格

| 項目 | Muse Spark Open | Muse Glimmer |
|---|---|---|
| 發布日 | 2026-10-15 | 2026-08（HF repo 建於 08-09） |
| 參數量 | 816B 總量／42B active（Baseten 部落格寫 42.7B） | 29.6B（含視覺編碼器），dense |
| 架構 | MoE：256 個 expert、每 token 選 8 個；62 層，其中 46 層是 sliding window（2,048）、16 層是全域注意力；另有約 1.8B 的感知編碼器 | dense：52 層，每 3 層 local（2,048 window）配 1 層 global；GQA 32/2；另有約 1.8B 的 ViT-G/14 |
| Context | 1,048,576 token | 131,072（Meta 文件寫「預設 128K，支援更長」） |
| 輸入模態 | 文字、圖片、影片、音訊 | 文字、圖片 |
| 輸出 | 文字 | 文字 |
| 推理 | 一定會推理。`reasoning_effort` 可設 `low`／`medium`／`high`／`xhigh`，**預設 xhigh**；分別對應強度 8／32／256／512 | 一定會推理。強度 low／medium／high／xhigh，**預設 high**；用 system prompt 寫 `Reasoning strength: low`，或送 `chat_template_kwargs: {"reasoning_strength": "low"}`。**參數名是 `reasoning_strength`，不是 `reasoning_effort`**；llama.cpp 不實作 `reasoning_effort`，ExecuTorch 會回 400（查核補註，來源：https://dev.meta.ai/docs/muse-glimmer/deploy.md ） |
| Tool calling | 支援（原生 ATEM 格式，伺服器端解析成 OpenAI 的 `tool_calls`） | 支援（ATEM；vLLM 用 `muse_glimmer` parser） |
| 知識截止 | 2026-01-04（chat template 的預設值） | 2026-01-04 |
| 建議取樣 | temperature 1.0、top_p 1.0、不設 top_k | temperature 1.0、top_p 0.95、top_k 64；**不要用 greedy**（會鬼打牆） |
| 停止 token | `<\|eot\|>`、`<\|end_of_text\|>`；**不能在 `<\|eom\|>` 停** | 同左 |
| HF repo | `meta-models/Muse-Spark-Open-816B-A42B`（BF16）、`-NVFP4`；**需人工審核才能下載**（HF `gated: manual`；表單要填姓名、生日、國家、所屬組織、職稱。也可在 dev.meta.ai 登入、接受授權後下載） | `meta-models/Muse-Glimmer-30B`（BF16）、`-GGUF`、`-assistant`（DFlash）、`-ExecuTorch-PTE`；不需審核 |
| 授權 | Muse Model License（見第 2 節） | Apache 2.0 |

### 硬體需求

| 模型／版本 | 權重大小 | 部署需求（官方） |
|---|---|---|
| Spark Open BF16 | 約 1.65 TB | 8 × B300（TP8/EP8），VRAM 約 2 TB |
| Spark Open NVFP4 | 約 537 GB | 4 × B300 或 GB300（TP4/EP4）；model card 寫至少 700 GB VRAM |
| Spark Open on Mac | NVFP4 | 2 台 M5 Ultra 512 GB，或 4 台 256 GB 的 Mac Studio（MLX） |
| Glimmer BF16 | 約 60 GB | **服務時約需 72 GB VRAM**（vLLM recipe）。SGLang 驗證過的單卡：B300、B200、H200、RTX PRO 6000 96 GB、DGX Spark |
| Glimmer FP8（RedHatAI） | 32.78 GB | vLLM recipe 有列；視覺塔維持 BF16 |
| Glimmer NVFP4（Inferact／RadixArk） | 約 25 GB | 只有文字，不含視覺塔 |
| Glimmer GGUF Q4_K_M | 16.8 GB（加視覺 1.4 GB、DFlash 1.6 GB） | 24 GB 卡，總共約 19–20 GB；Q4_K_XL 版 19.7 GB，適合 32 GB 卡 |

Glimmer 官方的量化品質損失：K-Quant-Dynamic 為 0.2%，K-Quant-17GB 為 1.0%（15 個 benchmark 的平均）。RTX 5090 跑 17GB 版加 DFlash 約 233 tok/s（batch 1）。

結論：**Spark Open 不可能在一般硬體上自己跑**，只能用託管服務。Glimmer 一張 24–32 GB 的卡就能跑量化版。

---

## 2. 授權

### Muse Spark Open：Muse Model License（版本日期 2026-10-15）

| 條款 | 內容 | 對 pickfit 的影響 |
|---|---|---|
| 授權範圍 | 可以使用、修改、微調、蒸餾、散布、販售 | 可以商用 |
| 第 1 條 | 必須遵守 Usage Policy（附件 A）；散布本軟體或衍生物（Derivatives）時，要附上版權聲明、本授權與 Usage Policy | 禁止用途見下；pickfit 不散布權重，只透過 API 用 |
| 第 2 條 | 使用本模型或衍生物的產品或服務，**必須在 UI、文件、網站或設定選單中明顯標示「Built with Muse Spark Open」**。「衍生物」包含用本模型的**輸出**訓練出來的模型 | README 與展示頁要加這行；若日後拿輸出訓練模型，那個模型也算衍生物 |
| 第 3 條 | 對第三方以 API 等方式提供模型（Model as a Service），**而且授權方與關係企業的合計總營收**在任連續 12 個月超過 2,000 萬美元，才需要先通知 Meta 並另簽書面協議。門檻是公司總營收，不是 MaaS 營收。內部使用、研究、非 MaaS 的商業活動，或拿模型當自家產品（非 MaaS）的功能，不在此限 | 不影響 |
| 第 4 條 | Meta 不主張輸出的所有權 | — |
| Usage Policy | 不適用 18 歲以下（原文「not intended for individuals under the age of 18」）；禁止把模型輸出說成人寫的；禁止惡意程式、詐騙、垃圾訊息、假評論與假互動、冒充他人、無照執業（醫療、法律、金融）、未經授權推論個人敏感資訊、軍事用途等 | 「不做醫療建議」本來就在 brief 的排除清單；注意不能產生假評論或假互動 |

### Muse Glimmer：Apache 2.0

- 可以商用、修改、再散布，不需顯示標語；再散布時要保留 LICENSE。HF repo 沒有 NOTICE 檔（查核補註：repo 檔案清單只有 LICENSE、README、USAGE_POLICY.md 等；https://huggingface.co/api/models/meta-models/Muse-Glimmer-30B ）。
- repo 另附 `USAGE_POLICY.md`，內容和上面的 Usage Policy 類似。它和 Apache 2.0 之間的法律關係，文件沒有寫清楚。（未驗證）

---

## 3. 誰提供這兩個模型

| 服務 | Muse Spark Open | Muse Glimmer | 是比賽合作夥伴嗎 |
|---|---|---|---|
| **Baseten** | Model APIs（按 token 計費）：`meta-models/muse-spark-open`，$1.25 輸入／$0.15 快取輸入／$4.25 輸出（每百萬 token） | 只有專用部署：BF16 跑在單張 H100 上（vLLM＋DFlash），按分鐘計費，H100 每小時 $6.50 | 是：$100 credits＋2M TPM |
| **Modal** | Shared Endpoint（按 token 計費），價格同上；NVFP4 | Dedicated Endpoint：BF16 或 RadixArk NVFP4，按秒計 GPU 費；**模型庫頁面只列文字模態** | 是：$100 credits（「透過 Endpoints 使用 Meta 開放權重模型」） |
| **Fireworks** | Serverless：`accounts/fireworks/models/muse-spark-open`，價格同上，context 1040K，支援圖片與 function calling | **Serverless 已於 2026-09-25 下架**，只剩 on-demand 部署；提供免費 SFT 到 11/30 | 是：$25，少數入選 |
| Together AI | `meta-models/muse-spark-open` | Serverless：`meta-models/Muse-Glimmer-30B`，$0.35／$0.04／$1.50（Together 模型頁與 Meta 文件一致，查核時直接讀過 Together 頁面）；伺服器端用 FP8（MLP 量化，attention 與視覺塔維持 bf16）；單次輸出上限 32,768 token（後兩項取自 Meta 部署文件轉述 Together 的說法） | 否（但是 Meta 的發布夥伴） |
| Groq | 需要組織先通過審核；context 131,072；支援 tool calling、structured outputs、圖片 | — | 否 |
| Nebius、OpenRouter | 有 | OpenRouter 有列（Meta 文件的發布夥伴名單） | 否 |
| DeepInfra | — | $0.30／$0.04／$1.20；131,072；頁面標示支援 JSON 與 Function | 否 |
| HF Inference Providers | 只透過 Baseten（HF router：`supports_tools` true、`supports_structured_output` false、約 172 tok/s、首 token 約 357 ms） | HF router `/v1/models` 只列 DeepInfra（tools 與 structured output 都是 true）和 Featherless；Together 在 `inferenceProviderMapping` 標 live，但 router 清單沒有它，structured output 未驗證 | — |

---

## 4. Baseten

### 4.1 怎麼呼叫（已確認：官方文件）

| 項目 | 值 |
|---|---|
| Base URL | `https://inference.baseten.co/v1` |
| 端點 | `/chat/completions`（OpenAI 相容）、`/responses`（OpenAI Responses，無狀態）、`/messages`（Anthropic 相容，beta） |
| 認證 | `Authorization: Bearer $BASETEN_API_KEY`；Anthropic SDK 也要改成送 `Authorization` |
| Model slug | 文件寫 `meta-models/muse-spark-open`；**比賽要用 `meta-models/muse-spark-open-1026`**（文件裡找不到，未驗證） |
| 列出模型 | `GET /v1/models`，或 `baseten model-api list` |
| 不帶金鑰時（實測 curl） | `GET /v1/models` 回 401 `No Authorization header provided`；帶錯的金鑰回 403 `{"error":"please check the api-key you provided"}` |

### 4.2 功能支援（Muse Spark Open on Baseten）

| 功能 | 支援 | 說明 |
|---|---|---|
| Tool calling | ✅ | 「All Model APIs support tool calling」。`tool_choice` 可設 `auto`／`required`／`none`，或指定某個函式（這是通用文件；對 Spark Open 是否有效未驗證） |
| JSON schema（`response_format: json_schema`） | ❌ | 「accepts `json_schema` but doesn't enforce the schema」 |
| JSON mode（`json_object`） | ❌ | 「accepts `json_object` but doesn't constrain output to JSON」 |
| 推理 | 一定開 | `reasoning_effort` 可設 low／medium／high／xhigh，預設 xhigh；`none` 和 `minimal` 會當成 `low`；推理內容放在 `reasoning_content` |
| 圖片 | ✅ | JPEG、PNG、WebP、GIF（只取第一格）、BMP、TIFF；每次最多 8 張，每張 URL 最大 10 MB；圖片＋影片＋音訊合計 200 MB，base64 時整個 request body 上限 100 MiB |
| 影片 | ✅ | 每次最多 2 支、每支 200 MB、最長 300 秒；最多取 96 格；720p 約每秒 144 token，上限約 6.9K token |
| 音訊 | ✅ | WAV、MP3、FLAC、OGG、M4A；最多 4 個檔，每個 25 MB、5 分鐘 |
| PDF | ❌ | 先自己抽出文字 |
| 其他限制 | — | `n` 大於 1 會回 400；`logprobs` 會被忽略；`seed` 和 `temperature: 0` 都不保證可重現 |
| Context | 1M | Baseten 部落格寫「the full 1M context window」，用 NVFP4 提供服務。文件的 supported models 表：context 1,048K、max output 1,048K；可用取樣參數 temperature、top_p、top_k、stop、presence_penalty、frequency_penalty（查核補註，來源：https://docs.baseten.co/inference/model-apis/overview 的 HTML 表格） |
| 資料保存 | 零保存 | 同步請求不保存輸入與輸出 |

### 4.3 價格與限制

- 價格：$1.25 輸入／$0.15 快取輸入／$4.25 輸出（每百萬 token），來自 Baseten 的 pricing 與模型庫頁面。圖片換算成輸入 token，沒有另外的單張費用。
- 快取自動生效。同一個任務的請求帶同一個 `x-session-affinity` header，比較容易命中快取；文件建議同一個 session 每分鐘最多約 60 個請求。
- 帳號預設的 rate limit：

| 等級 | RPM | TPM |
|---|---:|---:|
| Basic（未驗證） | 15 | 100,000 |
| Basic（已驗證） | 120 | 500,000 |
| Pro | 120 | 1,000,000 |

- 上表只是帳號預設值。文件寫「A model, service tier, or organization-specific configuration can set different limits」，所以 Spark Open 的實際限制可能不同；可用 `GET /v1/model_apis/{model_api_name}` 查有效限制。
- 比賽給 **2M TPM**，但 **RPM 會不會一起提高沒有寫**（未驗證）。從回應的 `x-ratelimit-limit-requests` 和 `x-ratelimit-limit-tokens` header 可以看到實際的限制。
- 可以設月預算；開啟「enforce」後，達到預算時會拒絕 Model API 請求。這和 Meta 的 Spend Limit 不同，真的會停止扣款。
- 錯誤碼：429 是超過 rate limit，529 是服務過載。都要退避後重試。402 是需要付款（credits 用完時可能出現，未實測）。

### 4.4 比賽的 credits 怎麼申請

- 公開活動頁寫的是「Baseten is offering $100 in credits and 2M TPM rate limits to select participants to use Meta's open-weights models」。
- rules 第 6 節寫限 2,000 人、需要審核。申請入口在 Participant Guide（cerebralvalley.ai，需要登入）。**表單內容與審核時間未驗證。**
- 步驟：(1) 在 app.baseten.co 註冊；(2) 照 Participant Guide 的連結申請；(3) 到 Settings → API Keys 建立金鑰，放進 `.env`；(4) 跑 `spikes/meta_baseten_hello.py`。

---

## 5. Modal

### 5.1 Modal 有現成的端點

| 方式 | 模型 | 怎麼建立 | 計費 |
|---|---|---|---|
| Shared Endpoint | Muse Spark Open（Shared Endpoint 表列文字、圖片、音訊；模型庫頁的規格另列影片，Shared Endpoint 是否收影片未驗證） | `modal endpoint create --shared --model meta-models/Muse-Spark-Open-816B-A42B` | 按 token：$1.25／$0.15／$4.25 |
| Dedicated Endpoint | Muse Glimmer 30B BF16 | `modal endpoint create --model meta-models/Muse-Glimmer-30B` | 按秒計 GPU；沒請求時縮到 0，不收費 |
| Dedicated Endpoint | Muse Glimmer 30B NVFP4（只有文字） | `modal endpoint create --model RadixArk/Muse-Glimmer-NVFP4` | 同上 |

- 認證：先執行 `modal workspace proxy-tokens create`，再用 `Authorization: Bearer wk-<id>.ws-<secret>`。
- Shared Endpoint 的 base URL 是 `https://inference.us-west.modal.direct/v1`，`model` 欄位填端點的 hostname（例如 `my-endpoint.us-west.modal.direct`）。來源是 https://modal.com/docs/guide/endpoint-integrations.md （endpoints.md 只寫「填 dashboard 上顯示的值」）。實測 curl：不帶憑證時 `/v1/models` 回 401 `{"error":"invalid proxy auth credentials"}`（2026-10-28 重測一致）。
- Shared Endpoint 有「每個模型的並行請求上限」，整個 workspace 共用，超過回 429；數字文件沒寫（未驗證）。
- **注意**：Modal 文件寫「Credits included with your plan cannot be used for Shared Endpoint usage」。比賽的 $100 能不能拿來付 Shared Endpoint 的費用，**未驗證**（活動頁只寫「through Endpoints」）。
- Shared Endpoint 的 tool calling 與 JSON schema 支援，Modal 文件沒寫。（未驗證）
- Dedicated Endpoint 用哪種 GPU 由 Modal 的 recipe 決定，文件沒寫。（未驗證）

### 5.2 自己用 vLLM 或 SGLang 跑 Glimmer（官方指令，取自 Meta 文件）

```bash
# vLLM（官方 Docker image；需要 72 GB VRAM）
docker run --rm --gpus all --ipc=host -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:muse-glimmer meta-models/Muse-Glimmer-30B \
  --served-model-name muse-glimmer --tensor-parallel-size 1 \
  --enable-auto-tool-choice --tool-call-parser muse_glimmer \
  --reasoning-parser muse_glimmer --generation-config auto

# SGLang
sglang serve --model-path meta-models/Muse-Glimmer-30B \
  --served-model-name muse-glimmer --reasoning-parser muse --tool-call-parser muse \
  --mem-fraction-static 0.85 --host 0.0.0.0 --port 30000
```

- Parser 名稱：vLLM 用 `muse_glimmer`（底線；寫成連字號會失敗），SGLang 用 `muse`。
- 搬到 Modal 時可以參考：`examples/llm_inference`（vLLM、H200、`scaledown_window` 15 分鐘）、`examples/vllm_throughput`（離線批次）、`examples/sglang_low_latency`。Modal 沒有 Glimmer 專用的程式範例，只有 Dedicated Endpoint 會自動產生 `serve.py`。

### 5.3 GPU 選擇與價格（Modal 牌價，換算成每小時）

| GPU | 每小時 | $100 可用時數 | Glimmer 適合度 |
|---|---:|---:|---|
| L40S 48 GB | $1.95 | 51 | FP8 版（32.8 GB）放得下；Ada 支援 FP8。未驗證 |
| A100 80 GB | $2.50 | 40 | BF16 很緊（需要 72 GB）；Ampere 不支援原生 FP8 |
| RTX PRO 6000 96 GB | $3.03 | 33 | **SGLang 驗證過 BF16（含圖片）的最便宜選項** |
| H100 80 GB | $3.95 | 25 | BF16 很緊；建議用 FP8 版。Baseten 的 recipe 用 H100 跑 BF16 |
| H200 141 GB | $4.54 | 22 | SGLang 驗證過 BF16 |
| B200 | $6.25 | 16 | 驗證過 BF16 與 NVFP4 |

上表只算 GPU。Modal 的 CPU 與記憶體另外按秒計費，實際花費會略高。

另外，Baseten 的 H100 每小時 $6.50、B200 每小時 $9.98，按分鐘計費。

### 5.4 Cold start（估算）

| 階段 | 時間 | 根據 |
|---|---|---|
| 容器啟動 | 約 1 秒 | Modal cold start 文件 |
| 從 Volume 讀權重 | 每 GB 約 0.5–1 秒，BF16 60 GB 約 30–60 秒 | Modal 文件：每秒 1–2 GB |
| vLLM 編譯與 CUDA graph | 第一次數十秒到幾分鐘；有快取時約 10 秒 | Modal 的 vLLM 範例 |
| 第一次從 HF 下載 60 GB | 數分鐘（未驗證） | — |

合計：熱快取約 1–2 分鐘，第一次部署約 5–15 分鐘。用 GPU memory snapshot 可以再縮短。

---

## 6. Fireworks

- Spark Open 有 serverless：base URL 是 `https://api.fireworks.ai/inference/v1`，model 是 `accounts/fireworks/models/muse-spark-open`。價格 $1.25／$0.15／$4.25，只用美國的算力。
- 支援 tool calling、圖片、`reasoning_effort`；Meta 文件寫 JSON mode（`json_object`）可以用。`json_schema` 是否支援未驗證。
- Fireworks serverless 只收文字和圖片（不收影片、音訊）；`reasoning_effort: "none"` 會被拒絕（Baseten 則是把 `none`／`minimal` 當成 `low`）。（Meta 部署文件與 Fireworks 模型頁）
- Glimmer 只能用 on-demand 部署（serverless 已下架），但可以免費 SFT 到 11/30。
- 比賽 credits：$25，以團隊為單位，入選才有，會收到 email。

---

## 7. Best Build on Meta Open Weight Models

| 項目 | 內容 | 狀態 |
|---|---|---|
| 獎金 | $10K，可以和組別獎同時拿 | rules 第 5 節 |
| 條件 | 使用 Muse Glimmer 或 Muse Spark Open，跑在**自己的硬體**或**合作夥伴的推論服務**上 | rules 第 5 節 |
| 合作夥伴 | 活動頁列的推論夥伴是 Baseten、Modal、Fireworks | 已確認（公開活動頁） |
| Together、DeepInfra 算不算 | 它們不是比賽夥伴。Together 是 Meta 的發布夥伴 | 未驗證，避免使用 |
| 提交時怎麼標 | 提交表單有沒有專用欄位，**未驗證**（Participant Guide 要登入） | 未驗證 |

建議的標示方式（不依賴表單）：
1. README 開一節「Meta open-weight models」：寫明模型、服務商、model slug、用在管線哪一步、每天處理幾筆。
2. 附一份真實的用量證據，例如 `baseten model-api usage` 的輸出，或管線的 log（token 數、筆數）。
3. Demo 影片用一個畫面帶到「初篩由 Muse Spark Open（Baseten）完成」。
4. 提交表單的描述欄也寫一句。
5. 加上「Built with Muse Spark Open」（授權條款要求）。
6. 到 Discord 的 #questions 問清楚提交時要怎麼標。

---

## 8. 哪些工作適合交給開放權重模型，要花多少

### 8.1 工作分配

| 工作 | 適合開放權重嗎 | 理由 |
|---|---|---|
| 候選 repo 初篩：是不是可用的軟體、屬於哪一類 | ✅ 最適合 | 量最大；答案短；錯了只會少收錄一筆；`low` 推理就夠 |
| 社群貼文是不是在發表作品 | ✅ | 輸入短，答案只要一個布林值加一個類別 |
| 去重判斷（兩個候選是不是同一個專案） | ✅ | 先用規則（repo URL、名稱、homepage）篩出可疑的配對，再交給模型 |
| README 摘要與結構化抽取 | ⚪ 可以 | 欄位多。Baseten 不強制 schema，要驗證加重試。也可以留給 Muse Spark（Meta API，支援 JSON schema） |
| 驗證階段的截圖判讀、安裝錯誤修正 | ⚪ 可以，但建議留給 Muse Spark | Spark Open 能讀圖，但這是 demo 的核心，用 Meta API 比較穩，評審也看得清楚 |
| 配對與推薦理由 | ❌ 留給 Muse Spark | 直接影響 demo 品質，而且需要 JSON schema |

### 8.2 每 1000 筆候選的估算

假設：
- README 截斷：初篩取前 1,200 token，抽取取前 3,500 token。
- `reasoning_effort` 設 `low`，推理 token 約 200–500（**未實測**，這是誤差最大的地方）。
- 約 30% 的候選通過初篩、進入抽取。可疑的重複配對約 300 對。
- 不計快取。若 system prompt 命中快取，約可省 $0.9。

| 步驟 | 筆數 | 每次輸入 | 每次輸出（含推理） | 總輸入 | 總輸出 |
|---|---:|---:|---:|---:|---:|
| A. 初篩分類 | 1,000 | 2,000 | 400 | 2.00M | 0.40M |
| B. 結構化抽取 | 300 | 4,500 | 900 | 1.35M | 0.27M |
| C. 去重判斷 | 300 | 700 | 250 | 0.21M | 0.08M |
| **A＋B＋C** | 1,600 次請求 | | | **3.56M** | **0.75M** |
| D. 貼文判斷（另計，每 1000 則） | 1,000 | 500 | 250 | 0.50M | 0.25M |

費用（USD）：

| 服務與模型 | A | B | C | A＋B＋C | D | 備註 |
|---|---:|---:|---:|---:|---:|---|
| Spark Open（Baseten／Modal／Fireworks，牌價相同） | 4.20 | 2.83 | 0.58 | **7.62** | 1.69 | 有快取約 $6.7 |
| Glimmer（Together，$0.35／$1.50） | 1.30 | 0.88 | 0.19 | 2.36 | 0.55 | 不是比賽夥伴 |
| Glimmer（DeepInfra，$0.30／$1.20） | 1.08 | 0.73 | 0.15 | 1.96 | 0.45 | 不是比賽夥伴 |
| Glimmer 自架（Modal H100，$3.95/hr） | | | | 約 2.1–3 | | 估算：批次 prefill 5k tok/s、decode 600 tok/s（未實測），另加 cold start |
| 對照：Muse Spark（Meta API，Standard） | 4.20 | 2.83 | 0.58 | 7.62 | 1.69 | 和 Spark Open 同價 |
| 對照：Muse Spark（Contributor 模式，$0.10／$0.20） | 0.28 | 0.19 | 0.04 | 0.51 | 0.10 | 內容會被拿去訓練；RPM 150 |

**敏感度**：忘了設 `low`、用了預設的 xhigh，或推理比預期長時，每筆初篩每多 500 個推理 token，每 1000 筆就多約 $2.1。

**$100 credits 能做多少**（Spark Open 牌價）：
- A＋B＋C 全做：約 1.3 萬筆候選。
- 只做初篩（A）：約 2.4 萬筆。
- 換算成 token：以這個輸入輸出比例，平均每百萬 token $1.77，$100 約 5,600 萬 token。

**時間**（Baseten，每 1000 筆、1,600 次請求、約 430 萬 token）：

| 限制 | 需要的時間 |
|---|---|
| RPM 120（已驗證帳號） | 約 13 分鐘 |
| RPM 15（未驗證帳號） | 約 107 分鐘 |
| TPM 2M（比賽） | 至少約 2 分鐘 |
| TPM 500k | 約 9 分鐘 |
| 單次請求延遲 | 約 3–6 秒（HF 量到 Baseten 約 172 tok/s、首 token 約 0.36 秒；400–900 token 的輸出），並行約 6–12 個就能用滿 120 RPM（120 RPM＝每秒 2 個 × 3–6 秒）。注意：同一個 `x-session-affinity` 文件建議每分鐘最多約 60 個請求，批次要分多個 session |

→ **瓶頸是 RPM，不是 TPM。** 拿到金鑰後先看 `x-ratelimit-limit-requests`。

---

## 9. 對 pickfit 架構的建議

1. **初篩（每天數百到數千筆）**：Baseten 的 `meta-models/muse-spark-open-1026`，`reasoning_effort: "low"`，`max_tokens` 留 2–4K，避免推理被截斷。輸出用 pydantic 驗證，失敗重試一次，再失敗就標 `null`、交給人工抽查。
2. **結構化抽取**：先試 Spark Open 加強制 tool calling（spike 的 `--tools`）。如果 tool 參數常常不合 schema，就改用 Muse Spark（Meta API）的 `response_format: json_schema`。
3. **不自己架 Glimmer。** Glimmer 對 pickfit 的價值是故事性（「可以在筆電上跑」，呼應本地 AI 類別），但 Spark Open 走 Baseten 已經符合加碼獎條件。時間不夠時，照 brief 第 13 節的順序先砍「開放權重初篩」。
4. **把 Meta 模型的分工講清楚**：Spark Open 做大量初篩（開放權重），Muse Spark 做抽取、視覺驗證、配對。README 和影片各講一句。
5. **合規**：README 加上「Built with Muse Spark Open」。不把模型輸出包裝成人寫的評論。
6. **預算控制**：在 Baseten 開啟月預算的 enforce；每次批次結束後記錄 `usage`。

---

## 10. 最小範例

### curl（Baseten）

```bash
curl https://inference.baseten.co/v1/chat/completions \
  -H "Authorization: Bearer $BASETEN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-models/muse-spark-open-1026",
    "reasoning_effort": "low",
    "max_tokens": 2048,
    "messages": [
      {"role": "system", "content": "Reply with one JSON object: {\"is_software\": bool, \"category\": \"dev_cli|local_ai|other|not_software\"}"},
      {"role": "user", "content": "repo: example-user/tinyfind\nREADME: A fuzzy file finder CLI. cargo install tinyfind"}
    ]
  }'
```

### Python（OpenAI SDK，Baseten）

```python
import json, os
from openai import OpenAI

client = OpenAI(base_url="https://inference.baseten.co/v1", api_key=os.environ["BASETEN_API_KEY"])
resp = client.chat.completions.create(
    model="meta-models/muse-spark-open-1026",
    reasoning_effort="low",          # 預設是 xhigh，批次工作一定要設
    max_tokens=2048,
    messages=[
        {"role": "system", "content": "Reply with one JSON object: {\"is_software\": bool, \"category\": str}"},
        {"role": "user", "content": "repo: example-user/tinyfind\nREADME: A fuzzy file finder CLI."},
    ],
)
data = json.loads(resp.choices[0].message.content)  # Baseten 不強制 JSON，要自己驗證
print(data, resp.usage)
```

### Python（Modal Shared Endpoint）

```python
import os
from openai import OpenAI
client = OpenAI(base_url="https://inference.us-west.modal.direct/v1",
                api_key=os.environ["MODAL_PROXY_TOKEN"])   # wk-<id>.ws-<secret>
client.chat.completions.create(model="<your-endpoint>.us-west.modal.direct", messages=[...])
```

### Spike

`spikes/meta_baseten_hello.py`：只用標準函式庫。設好 `BASETEN_API_KEY` 就能跑；沒有金鑰時只印說明。它會：
1. 列出 `/v1/models` 裡含 muse 的模型；
2. 跑一次初篩，檢查 JSON 能不能解析，印出 usage、估算費用、rate limit header；
3. 加 `--tools` 時，改測強制 tool calling。

狀態：**未實測**。已確認的只有：沒有金鑰時會正常結束；帶錯的金鑰時會印出 403 的說明。

---

## 11. 未驗證清單

| # | 項目 | 怎麼驗證 |
|---|---|---|
| 1 | `meta-models/muse-spark-open-1026` 是否存在、和 `muse-spark-open` 有什麼不同、價格是否一樣 | 拿到金鑰後跑 spike，看 `/v1/models` |
| 2 | 比賽的 2M TPM 會不會一起提高 RPM | 看 `x-ratelimit-limit-requests` |
| 3 | Baseten 比賽 credits 的申請表單與審核時間 | Participant Guide（需登入） |
| 4 | Spark Open 在 Baseten 上的強制 tool calling（`tool_choice` 指定函式）是否有效、參數是否合 schema | `spike --tools` |
| 5 | `low` 推理實際會用多少推理 token | spike 的 usage |
| 6 | Modal 比賽的 $100 能不能付 Shared Endpoint（按 token）的費用 | 問 Modal，或看帳單 |
| 7 | Modal Shared Endpoint 上的 Spark Open 是否支援 tool calling 與 JSON schema | 實測 |
| 8 | Modal Dedicated Endpoint 上的 Glimmer 用哪種 GPU、能不能讀圖片（模型庫只列文字） | 建立端點後看 Source |
| 9 | Glimmer 在 vLLM 上搭配 `muse_glimmer` reasoning parser 時，`response_format: json_schema` 是否有效 | 實測 |
| 10 | 開放權重加碼獎在提交時要怎麼標；Together 或 DeepInfra 算不算合作夥伴 | Discord #questions |
| 11 | Glimmer 自架的實際吞吐量（第 8 節的 5k／600 tok/s 是推估） | 實測 |
| 12 | Fireworks 上的 Spark Open 是否支援 `json_schema` | 實測，或查 Fireworks 文件 |
| 13 | Glimmer 的 `USAGE_POLICY.md` 對 Apache 2.0 授權有沒有約束力 | 讀 LICENSE（repo 沒有 NOTICE 檔）；有疑慮就照 Usage Policy 做 |
| 14 | ~~Baseten 推理文件的矛盾~~（查核：不是矛盾）。「Control reasoning」表的 Control 欄指的是**開關推理**的方式；Spark Open 一直開著，所以是 None。推理**深度**看「Set reasoning depth」表，`low`／`medium`／`high`／`xhigh` 都照送出的值執行。仍值得實測 | spike 實測：`low` 和 `xhigh` 的推理 token 數差多少 |

---

## 12. 來源（全部查證於 2026-10-28）

Meta 官方：
- Models 總覽：https://dev.meta.ai/docs/models.md
- 開放權重總覽：https://dev.meta.ai/docs/open-weight-models.md
- Muse Spark Open：https://dev.meta.ai/docs/muse-spark-open.md ；部署與託管服務：https://dev.meta.ai/docs/muse-spark-open/deploy.md ；建議設定：https://dev.meta.ai/docs/muse-spark-open/settings.md ；取得模型：https://dev.meta.ai/docs/muse-spark-open/get-the-model.md ；硬體：https://dev.meta.ai/docs/muse-spark-open/hardware-platforms.md
- Muse Glimmer：https://dev.meta.ai/docs/muse-glimmer.md ；部署：https://dev.meta.ai/docs/muse-glimmer/deploy.md ；取得模型：https://dev.meta.ai/docs/muse-glimmer/get-the-model.md ；量化：https://dev.meta.ai/docs/muse-glimmer/quantization.md ；硬體：https://dev.meta.ai/docs/muse-glimmer/hardware-platforms.md ；提示詞：https://dev.meta.ai/docs/muse-glimmer/prompting.md
- Meta Model API 價格：https://dev.meta.ai/docs/pricing-rate-limits.md

Hugging Face：
- https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B （model card、授權全文、推論服務資訊；API：https://huggingface.co/api/models/meta-models/Muse-Spark-Open-816B-A42B ）
- https://huggingface.co/meta-models/Muse-Glimmer-30B （model card、config、LICENSE、USAGE_POLICY.md）
- https://huggingface.co/meta-models/Muse-Glimmer-30B-GGUF

Baseten：
- Model APIs：https://docs.baseten.co/inference/model-apis/overview.md
- 價格與限制：https://docs.baseten.co/inference/model-apis/pricing-and-limits.md
- Structured outputs：https://docs.baseten.co/inference/structured-outputs.md ；JSON mode：https://docs.baseten.co/inference/json-mode.md ；Function calling：https://docs.baseten.co/inference/function-calling.md ；推理：https://docs.baseten.co/inference/model-apis/reasoning.md ；視覺：https://docs.baseten.co/inference/model-apis/vision.md
- 模型庫頁面：https://www.baseten.co/library/muse-spark-open ；https://www.baseten.co/library/muse-glimmer-30b/
- 全文索引（搜尋「1026」用）：https://docs.baseten.co/llms-full.txt ；supported models 表（HTML 內嵌資料）：https://docs.baseten.co/inference/model-apis/overview ；音訊：https://docs.baseten.co/inference/model-apis/audio.md
- 價格頁：https://www.baseten.co/pricing
- 部落格：https://www.baseten.co/blog/muse-spark-open-launch/

Modal：
- 模型庫：https://modal.com/library/meta/muse-spark-open ；https://modal.com/library/meta/muse-glimmer-30b-bf16 ；https://modal.com/library/meta/muse-glimmer-30b-nvfp4
- 支援的模型：https://modal.com/docs/guide/supported-models.md ；Endpoints：https://modal.com/docs/guide/endpoints.md ；Shared Endpoints：https://modal.com/docs/guide/shared-endpoints.md ；Dedicated Endpoints：https://modal.com/docs/guide/dedicated-endpoints.md ；Shared Endpoint 的 base URL：https://modal.com/docs/guide/endpoint-integrations.md
- 價格頁：https://modal.com/pricing
- Cold start：https://modal.com/docs/guide/cold-start.md ；https://modal.com/docs/guide/high-performance-llm-inference.md
- 範例：https://modal.com/docs/examples/llm_inference.md ；https://modal.com/docs/examples/vllm_throughput.md
- 部落格：https://modal.com/blog/meta-muse-spark-open-now-available-on-modal

Fireworks：https://fireworks.ai/models/fireworks/muse-spark-open ；https://fireworks.ai/models/fireworks/muse-glimmer-30b

其他服務：
- Together：https://www.together.ai/models/muse-glimmer （價格數字取自 Meta 部署文件的引用）
- DeepInfra：https://deepinfra.com/meta-models/Muse-Glimmer-30B
- vLLM recipe：https://recipes.vllm.ai/meta-models/Muse-Glimmer-30B
- HF Inference Providers 的路由清單：https://router.huggingface.co/v1/models

比賽：公開活動頁 https://cerebralvalley.ai/e/meta-ai-developer-hackathon （合作夥伴的 credits）；`docs/hackathon-rules.md` 第 5、6 節。

---

## 查核紀錄（2026-10-28）

查核者：另一個 agent，預設懷疑、逐條對第一手來源。全部用 curl 抓原文（Meta 文件 `.md`、HF API／model card、Baseten／Modal 文件 `.md` 與 HTML、Fireworks／Together／DeepInfra 模型頁）。沒有 API key，沒有做任何付費呼叫。

### 逐條結果

| # | 主張 | 結果 | 依據（2026-10-28 讀取） |
|---|---|---|---|
| 1 | Spark Open：816B／42B active、256 expert 選 8、1,048,576 context、輸入文字＋圖片＋影片＋音訊、輸出文字 | 確認 | HF model card；https://dev.meta.ai/docs/muse-spark-open.md ；settings.md（62 層＝46 SWA＋16 全域） |
| 2 | Glimmer：29.6B dense、131,072 context、文字＋圖片、Apache 2.0、知識截止 2026-01-04 | 確認 | HF model card（`Context length 131,072+`）；Meta 文件寫「30B」「128K by default」 |
| 3 | 授權：第 2 條標語；只有 MaaS 且年營收超過 $20M 才要另簽 | **部分修正** | 營收門檻是「授權方＋關係企業合計總營收、任連續 12 個月」，不是 MaaS 營收；另需先通知 Meta。第 1 條還要求散布時附授權與 Usage Policy；「衍生物」含用輸出訓練的模型。已改第 2 節 |
| 4 | 兩者一定推理；Spark 預設 xhigh（low＝8）；Glimmer 預設 high | 確認＋補充 | chat template（`reasoning_effort` 預設 `xhigh`；Glimmer `reasoning_strength` 預設 `high`）；GGUF README「Reasoning cannot be switched off」。補：Glimmer 的參數名是 `reasoning_strength` |
| 5 | Baseten base URL、Bearer；無金鑰 401、錯金鑰 403 | 確認（重測） | `GET /v1/models` 無 header → 401 `No Authorization header provided`；錯金鑰 `POST /v1/chat/completions` → 403 `{"error":"please check the api-key you provided"}` |
| 6 | Baseten 上 Spark Open 支援 tool calling；`json_schema`／`json_object` 收但不強制 | 確認 | overview.md「All except Muse Spark Open support structured outputs and JSON mode」；structured-outputs.md；json-mode.md |
| 7 | Spark Open $1.25／$0.15／$4.25（Baseten、Modal、Fireworks）＝Muse Spark Standard；Contributor $0.10／$0.20 | 確認 | Baseten pricing 頁內嵌資料 `perfCost 1.25／perfCostOutput 4.25／perfCostCacheInput 0.15`；Modal supported-models.md；Fireworks 模型頁；Meta pricing-rate-limits.md（Contributor 快取輸入 $0.002） |
| 8 | Baseten 預設 15／120／120 RPM、100K／500K／1M TPM；比賽 2M TPM、RPM 不明 | 數字確認；RPM 是否提高仍未驗證 | pricing-and-limits.md；活動頁只寫「$100 in credits and 2M TPM rate limits」。補：模型層級設定可能不同 |
| 9 | `meta-models/muse-spark-open-1026` 不在 Baseten 公開文件與 HF | 確認找不到（仍未驗證是否存在） | llms-full.txt 與 overview HTML 搜尋「1026」0 筆；HF API 搜尋無此 ID；HF provider mapping 是 `meta-models/muse-spark-open`；WebSearch 無結果 |
| 10 | Glimmer 沒有夥伴按 token 提供；Baseten 專用 H100 BF16；Modal 只有 Dedicated（只列文字）；Fireworks serverless 2026-09-25 下架 | 確認 | Baseten 模型庫 `availability: ["dedicated"]`、「single H100」；Modal supported-models.md；Fireworks FAQ「Only on serverless, starting on September 25, 2026」 |
| 11 | Together $0.35／$1.50、DeepInfra $0.30／$1.20（JSON、Function）；都不是比賽夥伴 | 確認 | Together 模型頁（直接讀到 $0.35／$0.04／$1.50）；DeepInfra 頁；活動頁夥伴只列 Baseten、Modal、Fireworks |
| 12 | Modal Shared Endpoint 指令、base URL、proxy token；plan credits 不能付 Shared Endpoint | 確認；比賽 $100 能否支付仍未驗證 | shared-endpoints.md「Credits included with your plan cannot be used for Shared Endpoint usage」；base URL 來源補為 endpoint-integrations.md；無憑證 curl → 401 `invalid proxy auth credentials` |
| 13 | Glimmer BF16 需 72 GB；Modal GPU 價；cold start 估計 | 價格與 VRAM 確認；cold start 仍是估算 | Meta deploy.md「about 72 GB of VRAM」；Modal pricing 每秒價換算：RTX PRO 6000 $3.031、H100 $3.949、H200 $4.540、B200 $6.250。補：只算 GPU，CPU／記憶體另計 |
| 14 | Spark Open 自架 NVFP4 約 537 GB（4×B300）、BF16 約 1.65 TB（8×B300） | 確認 | get-the-model.md；hardware-platforms.md；model card「at least 700GB of VRAM for NVFP4 and 2TB for BF16」 |
| 15 | 每 1000 筆 3.56M 入／0.75M 出、約 $7.6（快取約 $6.7）、$100 約 1.3 萬筆、120 RPM 約 13 分、15 RPM 約 107 分 | 算式重算無誤（仍是估算） | 4.20＋2.835＋0.581＝$7.62；1,600 次÷120＝13.3 分；÷15＝106.7 分。修正並行數 5–10 → 約 6–12 |
| 16 | 開放權重加碼獎的條件；夥伴是 Baseten／Modal／Fireworks；提交怎麼標不明 | 夥伴名單確認；標示方式仍未驗證 | 公開活動頁 Partners 段落；獎項條件只在 rules 第 5 節（Participant Guide 需登入），公開頁沒有這段 |
| 17 | Baseten 上 Spark Open：最多 8 張圖（每張 10 MB）、2 支影片（300 秒）、4 個音訊、不收 PDF、n>1 回 400、忽略 logprobs | 確認＋補充 | vision.md、audio.md、overview.md。補：媒體合計 200 MB、base64 時 body 上限 100 MiB |

### 其他修正

| 位置 | 原文 | 改成 | 依據 |
|---|---|---|---|
| 第 0 節第 3 點 | 「獨立的 rate limit」當成走開放權重的理由 | 補註：Meta API 的 Muse Spark Standard 是 3,000 RPM／4M TPM，遠高於 Baseten 預設 | Meta pricing-rate-limits.md |
| 第 1 節 HF repo | 「要填法定姓名、生日、組織」 | 表單欄位是姓名、生日、國家、所屬組織、職稱；也可從 dev.meta.ai 下載 | HF API `extra_gated_fields`；get-the-model.md |
| 第 2 節 Glimmer | 「要保留授權與 NOTICE」 | repo 沒有 NOTICE 檔，保留 LICENSE 即可 | HF API 檔案清單 |
| 第 3 節 HF Providers | Glimmer 有 Together／DeepInfra／Featherless，Together structured output true | router 清單只有 DeepInfra 與 Featherless；Together 只在 mapping 標 live | https://router.huggingface.co/v1/models |
| 第 11 節 #14 | Baseten 推理文件「矛盾」 | 不是矛盾：Control 欄是開關方式，深度另一張表 | reasoning.md |

### 沒查到、維持未驗證

- `-1026` 是否存在、價格與 `muse-spark-open` 是否相同（需金鑰跑 `/v1/models`）。
- 比賽 2M TPM 是否連帶提高 RPM。
- Modal 比賽 credits 能否付 Shared Endpoint；Shared Endpoint 的並行上限、tool calling、JSON schema。
- Baseten 上強制 `tool_choice` 對 Spark Open 是否有效、參數是否合 schema。
- `low` 推理實際用多少 token（第 8 節成本誤差最大的來源）。

### Spike 狀態

`spikes/meta_baseten_hello.py`：沒有金鑰時印說明、exit 0；帶錯的金鑰時 `GET /models` 回 403 並印出說明、exit 1（2026-10-28 重跑）。正常路徑仍**未實測**。
