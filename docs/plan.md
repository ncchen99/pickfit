# 實作計畫：從驗證到交件

2026-10-28 · 給接手的 agent 與念誠。這份是**任務清單**：現在做什麼、做完怎麼算、沒過關怎麼辦。為什麼這樣設計見 [research/architecture.md](research/architecture.md)（下稱 arch），要做什麼見 [brief.md](brief.md)。brief 第 12 節的時程已由本文取代（理由見 arch H.2）。

---

## 怎麼用這份文件

- 照階段順序拿 task；依賴沒完成不開始。標 👤 的要念誠做或決定，其餘 agent 可以直接做。
- 每個 task 做完：打勾、在第 7 節「狀態紀錄」補一行（時間、結果、花費），commit。commit 小而頻繁。
- 檢查點沒過，照該處的「沒過就…」處理，不要自己加範圍。落後超過 2 小時就照 arch H.5 往下砍一項。
- 計畫改了就改這份文件，並在狀態紀錄寫原因。
- 呼叫任何付費 API 前，先讀第 2 節。

---

## 1. 目前狀態（2026-10-28 16:20 台北）

| 項目 | 狀態 | 備註 |
|---|---|---|
| Meta Model API | ✅ key 有效 | `/v1/models` 有 `muse-spark-1.3`、`muse-spark-1.3-contributor`、`muse-spark-1.2(-contributor)`、`muse-spark-1.1`、`muse-wonder-1.0`、`muse-image-1.0`、`muse-voice-transcribe-1.0`、`sam-3.1`；**沒有 embedding 模型**（確認 arch F.3）。一次 `muse-spark-1.3` 呼叫（`reasoning_effort: minimal`）：52 token（推理 29）、1.7 秒、約 $0.0002。限額 3,000 RPM、4M TPM。台灣帳號可用，第一輪的最大風險解除 |
| Meta credits | ✅ 表單已送、Spend Limit 通知已設 | 入帳狀態記在 `CLAUDE.local.md`（credits 與帳單資訊不進 repo） |
| Anthropic API key | ✅ 有效 | **只用在評測**（受測 agent），產品執行期不用 |
| Mac | ✅ Apple M5、24 GB、macOS 27 | demo 第 4 幕與 Mac 人工驗證在這台做 |
| Cloudflare | ✅ `wrangler` 已登入 | |
| GitHub | ✅ `gh` 已登入 | 管線用 `GITHUB_TOKEN=$(gh auth token)`，不必另建 PAT |
| Docker | 已安裝，daemon 沒開 | 本機沙盒開發前先開 Docker Desktop |
| Modal | ✅ token 在 `.env` | `MODAL_TOKEN_ID`／`MODAL_TOKEN_SECRET`；本機沒裝 CLI，用 `uvx --from modal modal …`；Python 端用 `uv run --python 3.12 --with modal …` |
| Baseten | ⏳ 10/28 已申請 | 審核制；沒回覆就當沒核准，照 P2.4 的退路走 |
| E2B | ❌ | 備案，Modal 不能用時才註冊 |
| Python | 系統 3.9 | 專案用 `uv` 管 Python 3.12 |

---

## 2. 花費守則（省 token）

Meta 的 $150 credits 是整場的模型預算，Spend Limit 只寄信、不會停止扣款，所以上限全部由程式執行。

1. **開發與測試用 `muse-spark-1.3-contributor`**（$0.10／$0.20 每百萬 token，比 1.3 便宜 12–20 倍，150 RPM）。它的內容可能被拿去訓練，所以**只送公開資料**（公開 README、測試資料），不送使用者需求。正式產生資料、配對、評測、錄影才用 `muse-spark-1.3`。
2. `reasoning_effort` 預設 `minimal` 或 `low`；只有驗證 agent 用 `medium`。
3. 所有呼叫都走 `call_meta`（P1.4）：記 trace（model、token、花費）、硬上限、開發模式的回應快取（同一個請求不重複付費）。單元測試一律用錄好的 fixture，不打真的 API。
4. **只有一本帳**：花費記在 repo 外、所有 worktree 共用的 `~/.pickfit/ledger.sqlite`（加鎖寫入）。上限照這本帳算，平行的 session 才不會各算各的。
5. **上限分階段**：10/29 前每日 $3；10/29 起管線每日 $25；管線總額 $100 硬停。Worker 另計：每日 $3、評審期總額 $40（arch H.6）。
6. **先小後大**：新 prompt 先跑 1 筆，再 5 筆、30 筆；每一步看過 `usage` 才放大。
7. **不要整份 `source .env`**：裡面有 `ANTHROPIC_API_KEY`，從那個 shell 啟動的 `claude` 會改用 API key 計費。spike 在 subshell 裡只帶需要的變數，例如 `(set -a; . ./.env; set +a; unset ANTHROPIC_API_KEY; python3 spikes/…)`；`pickfit` 程式自己從 `.env` 只讀它要的變數。
8. Anthropic key 只給評測執行器：先跑 2 題估單題花費，再跑全部；評測總花費上限 $30。
9. Claude Code 的子 agent、workflow 不在迴圈裡呼叫付費 API。需要呼叫時由主 agent 執行，並回報花費。
10. 每天結束時，把當日花費寫進狀態紀錄（數字由帳本產生；只記花費，不記 credits 餘額）。
11. **上限是安全網，不是要省到最後。** Meta 的 Spend Limit 只寄信、不會擋，所以由程式擋：管線 $100＋Worker 評審期 $40＝$140，留 $10 給 $150 credits 的誤差。各家額度照用途分配，**產品裡每個決定都用 Meta 模型**（評分 25%，第一輪必查；arch D.3、I #19）：
    - **Meta**：用在品質與規模。正式資料用 `muse-spark-1.3`（contributor 只用在開發）；驗證 agent 用 medium；修錯時可用 `web_search`；困難案例用 `muse-wonder-1.0` 重試；驗證目標從 50 筆提高到 100 筆以上。**11/1 檢查**：若預估到交件的 Meta 花費 <$60，就再擴大發現與驗證規模。
    - **Modal**：更多沙盒驗證；本地 AI 工具必須用 GPU 時開 GPU 沙盒（T4 約 $0.59／小時），讓更多工具達到「推論驗證」等級。
    - **Anthropic**（11/27 到期）：只用在評測（受測 agent、補充重跑、獨立評分）與開發工具，不放進產品的發現、抽取、驗證、配對流程。

---

## 3. 階段總覽

| 階段 | 日期（台北） | 目標 | 關卡 |
|---|---|---|---|
| P0 驗證 | 10/28 | 把 arch D.4 的未驗證項變成數字；帳號到位 | G0：今晚 structured output 與 tool calling 能用 |
| P1 骨架與評測凍結 | 10/28 | 評測 20 題 commit；專案骨架、schema、`call_meta` | 評測題組在任何資料寫入前 commit |
| P2 發現與抽取 | 10/29 | GitHub 候選 ≥150 筆、5 份抽取檔過 schema | 用第一批 `usage` 換掉成本估算 |
| P3 驗證 agent | 10/30 本機 Docker → 10/31 Modal | 照 README 失敗 → 模型讀錯誤 → 自己修好 → 判讀 → 重播 | **G2（10/31 晚上，硬關卡）**：10 筆 demo 候選 ≥5 筆在 Modal 通過並重播 |
| P4 MCP | 10/28 hello → 10/31 細路徑 → 11/1 補完 | 5 個工具上線，Claude Code 連得到 | 10/31：問「Mac、免費、能離線的 X」回 2–3 筆真資料 |
| P5 計分、提交、閉環 | 11/1–11/2 | ≥30 筆 verified（目標 50）；提交約 10 分鐘內可被推薦；回報 → 重驗 → git diff | 11/1 晚上 demo 故事定案 |
| P6 評測 | 11/2 | 對照組 vs 實驗組，含輸的題 | **11/2 晚上功能凍結** |
| P7 README、影片、交件 | 11/3–11/4 | README、3 分鐘影片、交件 | **台北 11/4 22:00 前送出**（截止是 11/5 10:00） |

---

## 4. 各階段的 task

### P0 驗證（10/28，花費上限 $1）

- [x] P0.1 Meta key：`/v1/models`＋一次最小呼叫（見第 1 節）。
- [x] P0.2 Meta 基本能力：在 subshell 只帶 `MODEL_API_KEY`（第 2 節第 7 條），跑 `META_REASONING=minimal python3 spikes/meta_api_hello.py`（text、json_schema、tools、image）。先用 `META_MODEL=muse-spark-1.3-contributor` 跑一次；json_schema 與 tools 再用 `muse-spark-1.3` 各跑一次。完成標準：四項的通過與否、`usage` 寫進 [research/notes/meta-model-api.md](research/notes/meta-model-api.md) 的實測小節與 [spikes/README.md](../spikes/README.md)。
- [x] P0.3 Responses API（`search_probe` 延後到需要「搜尋可見度」時再跑）：`spikes/meta_responses_agent_probe.py loop image_tool schema_tools`；`search_probe` 會產生搜尋費用，最後單獨跑。完成標準：arch D.4 #3–#5 有答案（截圖放哪模型看得到、`text.format` 能否和 tools 同一請求、推理 token 實際用量）。
- [x] P0.4 GitHub search 實際量：`GITHUB_TOKEN=$(gh auth token) python3 spikes/ch_hosting_github.py counts`。完成標準：兩個類別近 7／14 天的筆數寫回 [research/notes/channels-hosting.md](research/notes/channels-hosting.md)。
- [x] P0.5 hello MCP 上線：`spikes/mcp_stateless/` 用 `wrangler deploy` 部署到 `workers.dev`，`claude mcp add --transport http pickfit-hello <url>/mcp` 實連。完成標準：Claude Code 看得到並呼叫得到遠端 hello 工具。
- [x] P0.6 Modal：帳號與 token 已就緒（第 1 節）；workspace 花費上限已設約 $80（念誠，10/28）。agent 在 subshell 只帶 `MODAL_TOKEN_ID`、`MODAL_TOKEN_SECRET`，跑 `uv run --python 3.12 --with modal python spikes/sb_modal_verify.py --install "pip install httpie" --smoke "http --version"`，量沙盒啟動時間與網路政策；只跑這一筆。
- [ ] P0.7 👤 Baseten（10/28 已申請，等審核）：註冊並申請比賽 credits、建 key 放 `.env` 的 `BASETEN_API_KEY`、月預算 $20 開 enforce。核准後 agent 跑 `spikes/meta_baseten_hello.py`，確認 `meta-models/muse-spark-open-1026` 存在。
- [x] P0.8 👤 Meta Billing（10/28 完成）：送出 credits 表單、Spend Limit 通知設 $50 與 $100。

**G0（今晚）：已通過**（P0.2、P0.3）。json_schema 與 tool calling 能用就照計畫走。json_schema 不行 → 用 `finish` 工具＋pydantic 驗證；tool calling 不行 → 驗證 agent 改成「模型回 JSON 動作、程式執行」。兩者都不擋進度。

### P1 骨架與評測凍結（10/28）

- [x] P1.1 👤 **評測 20 題凍結**（10/28 17:06，commit `5ac62ca`）：草稿由 agent 在 10/28 新寫（不讀、不搬 `CLAUDE.local.md` 指向的賽前資料夾裡的評測草稿），念誠逐題審閱、修改並拍板，之後 commit `eval/questions.yaml` 與 `eval/README.md`（評分方式）。**這一步要在任何資料（`data/`、候選庫）寫入前完成。** 題目只寫需求與可檢查的條件，不寫預期答案。README 要照實寫明「草稿由 AI 起草、念誠審定」。
- [x] P1.2 專案骨架：`pyproject.toml`（`uv`、Python 3.12）、`pickfit/` 套件與 `pickfit` CLI、`tests/`、`NOTICE`（第三方授權）、`.gitignore` 補 `runs/`。目錄約定見第 5 節。
- [x] P1.3 pydantic schema `software.v1` 當唯一來源，產生 Meta strict JSON schema 與 `schema/software.v1.json`。欄位照 arch J（brief 第 11 節）＋ `repo_id`、`aliases`、`first_seen_at`；`verification` 等級照 arch C.3；`scores.quality.components` 照 arch B.3 的 6 個分項。
- [x] P1.4 `call_meta` v0（`openai` SDK、`base_url` 可切 Meta／Baseten）：記帳（`usage` × 單價，寫進第 2 節的共用帳本）、trace JSONL 寫到 `runs/traces/`、開發模式快取、第 2 節的硬上限、429 退避、504 改用 streaming 重試。完成標準：`uv run pytest` 通過（用 fixture）；一次真的呼叫經過 `call_meta`，留下 trace 與花費。

### P2 發現與抽取（10/29）

- [ ] P2.1 GitHub search：每類別 3 條 query（topic＋`created:`＋`pushed:`＋星數 5–300），序列化、間隔 ≥2.1 秒；補 repo、README、release。**discovery 的 query 依類別寫，不從評測題目推導，由沒讀過 `eval/` 的 session 撰寫**（[eval/README.md](../eval/README.md) 第 3 節）；每條 query 連同時間記在 trace。
- [ ] P2.2 正規化、去重、候選庫（`runs/pipeline.db`）：主鍵 `gh:<repo id>`、舊名進 `aliases`。移植 spike 時拿掉所有 ecosyste.ms 呼叫。
- [ ] P2.3 規則前置（arch B.1）：fork、archived、template、沒 README、函式庫訊號。從 `spikes/quality_signals.py` 移植時拿掉所有 ecosyste.ms 呼叫，改用 GitHub REST。
- [ ] P2.4 開放權重初篩（計畫內，需 P0.7）：Spark Open @ Baseten，低信心送 1.3 複查，抽 5% 比一致率。Baseten 沒核准或 `-1026` 不存在 → 用公開 model ID 自付（<$5）→ 再不行試 Modal Shared Endpoint（先確認 credits 能付）→ 最後才只用規則（會失去 Best Open Weight 資格，arch I #3、H.5 #6）。
- [ ] P2.5 抽取 v0：`muse-spark-1.3`，Responses、`text.format` strict，每欄附引用。照「1 → 5 → 30」放大。
- [ ] P2.6 抽取收尾（10/30 上午，arch H.2）：程式檢查引用真的出現在來源、授權與 release 等事實欄位改用 API 值、重試、批次；晚上背景跑批次抽取，產生 P3 要用的 ≥30 份 profile。

**完成標準**：`pickfit discover` 產生 ≥150 筆候選；漏斗每一格標模型與花費；5 份抽取檔過 schema。推理 token 超過估算 2 倍就降 effort。

### P3 驗證 agent（10/30 本機 → 10/31 Modal）

- [ ] P3.1 `Box` 介面與 `DockerBox`（沿用 `spikes/sandbox_docker_install.py` 的限制）。
- [ ] P3.2 安裝方式排序（套件管理器 → release 二進位 → 從原始碼建置）＋ 6–8 條常見錯誤規則。
- [ ] P3.3 驗證 agent：Responses＋`previous_response_id`、`reasoning: {effort: medium, summary: auto}`；工具 `list_dir`、`read_file`、`run_command`、`run_background`、`finish`；停止條件：25 回合、15 個指令、20 分鐘、每款 $0.50、同一錯誤 3 次。終端機逐步印出模型、指令、exit code、花費。P0.3 量到串接回合每回 15–18 秒：先用 3–5 回合比較「`previous_response_id` 串接」與「每回合重送完整歷史（`store: false`）」的延遲與花費，選快的。
- [ ] P3.4 截圖（Pillow 重繪終端輸出）＋判讀（另一次呼叫，圖片＋schema，回證據框）。
- [ ] P3.5 重播：全新 Box 照記錄的步驟重跑，成功才寫回 `install` 與 `verification`。
- [ ] P3.6 `ModalBox`（需 P0.6）：`runtime="gvisor"`、資源上限、先開網路安裝再收緊、預建 image、`--limits-test`。
- [ ] P3.7 批次：`pickfit verify --batch N --concurrency 5`，demo 類別優先。
- [ ] P3.8 挑 10 筆 demo 候選（Mac 能裝、免費、能離線）。
- [ ] P3.9 Show HN 管道（計畫內，10/30 最後做，1.5 h）：沿用 `spikes/ch_comm_hn_showhn.py`；落後就第一個砍（arch H.5 #2）。

**10/30 完成標準**：一個「照 README 會失敗」的工具，由 Muse Spark 自己讀錯誤、補步驟、呼叫 `finish`，trace 看得到推理摘要；≥30 份 profile 已 commit。修不好 → 10/31 上午繼續修，細路徑 MCP 延到 11/1；用規則表兜底，只做到「安裝驗證」等級。
**G2（10/31 晚上，硬關卡）**：10 筆 demo 候選中 ≥5 筆在 Modal 通過並重播成功。沒過 → 停掉所有計畫內與超前項目，11/1 上午只修驗證；Modal 不能用 → 換 E2B（約 2 h）。

### P4 MCP（10/28 hello → 10/31 細路徑 → 11/1 補完）

- [ ] P4.1 hello 上線（＝P0.5）。
- [ ] P4.2 `build_index`＋`pickfit publish`：驗 schema → commit → 建索引 → `wrangler deploy`；資料壞了就不部署。
- [ ] P4.3 D1 建表：`events`、`submissions`、`reverify_queue`、`meta_budget`（欄位照 arch E.3 的對照規則；`submissions` 要補 DDL）。不記 IP、不存需求原文，只存模型解析後的條件（brief 第 11 節）。
- [ ] P4.4 細路徑：`find_software` 照 arch F.2 走「硬條件篩選 → 該類別 ≤60 張候選卡 → 一次 `muse-spark-1.3` 呼叫（`store: false`、effort `low`）解析需求並取捨 → 程式守門（slug 必須在候選裡、理由對得上欄位）」；模型失敗或超預算就退回寶藏分數排序，標 `matched_by: rules`、`degraded: true`。`MODEL_API_KEY` 用 `wrangler secret put` 設定。`get_install_guide` 只回重播過的步驟，不呼叫模型。
- [ ] P4.5 補完：`find_alternatives`、`report_outcome`、`submit_software`；Host／Origin 檢查；Worker 每日上限與 `degraded`；回應帶 `how_we_know`、`evidence_url`、`matched_by`、`rec_id`。

### P5 計分、提交、回報閉環（11/1–11/2）

- [ ] P5.1 計分：規則分項＋`muse-spark-1.3` 文件 rubric＋寶藏分數（arch B.3，記 `formula_version`）。
- [ ] P5.2 `pickfit watch`：每 60 秒讀 D1 `submissions` → 跑單筆管線 → publish。
- [ ] P5.3 回報 → 重驗 → git diff（計畫內）。只用**真的**失敗（評測或 Mac 實裝時照指南失敗的那一筆）測試與展示，回報標 `reporter: dev`；不送捏造的失敗回報（arch H.4、B.3）。
- [ ] P5.4 run page：從 trace 產生靜態 HTML（計畫內）。
- [ ] P5.5 Meta 用量報表：從 trace 產生 README 與影片要用的數字。
- [ ] P5.6 👤 11/1 晚上 demo 主案＋2 個備案定案；挑影片「供給端」那一幕（arch H.4 的 1:55–2:30）要提交的第三方 repo：不能是自己的作品，而且**從未送進 pickfit**。

**11/1 完成標準**：≥30 筆 verified（目標 50），每筆有分開的品質、知名度、寶藏分數；在 Claude Code 用 `submit_software` 貼一個第三方 repo（**不能是 P5.6 留給錄影的那一個**），約 10 分鐘內出現在 `find_software`。

### P6 評測（11/2）

- [ ] P6.1 評測執行器：Claude Code 無頭模式（固定版本、固定提示），對照組（只有網路搜尋）與實驗組（＋pickfit MCP）；第三組 rules-only（計畫內）。**隔離**：這台 Mac 的使用者設定裡有 toolradar 等 MCP，會污染對照組；每題在空的暫存目錄執行，用 `--strict-mcp-config --mcp-config <檔案>`（對照組空的、實驗組只有 pickfit），若 Anthropic 額度夠：每題每組另外加跑 2 次當「補充結果」，主要結果仍是第 1 次；要在任何一組開跑前寫進 `eval/README.md` 第 9 節勘誤區（不改題目與主要結果的定義）。旗標已在 P0.5 實測有效；記下 Claude Code 版本。**`claude` 一定要用 `env -i HOME="$HOME" PATH="$PATH" ANTHROPIC_API_KEY=… claude -p …` 啟動**，否則會繼承桌面 app 的 `ANTHROPIC_BASE_URL` 而失敗（P0.5）。先跑 2 題估花費。
- [ ] P6.2 收集答案；安裝步驟在乾淨容器（或 Mac）實跑。
- [ ] P6.3 照 `eval/README.md` 評分；👤 念誠做盲測兩兩比較。
- [ ] P6.4 👤 demo 那 3 筆在 Mac 上由念誠親手照 `get_install_guide` 驗證（`method: human`），驗完移除；agent 只準備檢查清單、收 log。

**完成標準**：結果表（含輸的題）＋系統數字（候選數、驗證通過率、提交到可被推薦的時間）。≥2 題「好答案在資料裡卻沒被推薦」→ 只調候選卡或加 BM25，不加新功能。**當晚功能凍結。**

### P7 README、影片、交件（11/3–11/4）

- [ ] P7.1 README：Meta 模型分工與用量、Built with Muse Spark Open、Why this is not RAG、評測結果、賽前／賽中說明、授權。
- [ ] P7.2 👤 彩排 2 次、錄影（錄影前最後一次 publish，資料凍結）、剪輯。分鏡與即時／回放規則照 arch H.4。
- [ ] P7.3 交件前檢查：[hackathon-rules.md](hackathon-rules.md) 第 11 節、金鑰掃描、`grep -r ecosyste.ms` 不能出現在產品程式碼、`NOTICE`。
- [ ] P7.4 👤 repo 轉 public 並登出確認、提交（Indie Developer）、X 貼文附在提交頁。

---

## 5. 給 agent 的工作約定

**目錄**（P1.2 建立；平行工作時各自只動自己的目錄）：

| 路徑 | 內容 |
|---|---|
| `pickfit/` | Python 管線：`meta.py`（`call_meta`）、`schema.py`、`discover/`、`extract.py`、`verify/`（box、agent、judge、replay）、`score.py`、`cli.py` |
| `worker/` | TypeScript MCP server（Cloudflare Worker） |
| `data/software/<slug>.json` | 正本，每款一檔 |
| `schema/` | 由 pydantic 產生的 JSON Schema |
| `eval/` | 凍結的題目、評分方式、結果 |
| `scripts/` | `build_index`、run page、用量報表 |
| `runs/` | 候選庫、trace、快取（不進 git） |

**評測題目的隔離**：建資料與配對的 session（P2、P3、P4、P5 的發現、抽取、驗證、配對、計分）**不讀 `eval/`**，也不從讀過題目的對話 fork。配對的 prompt 正是評測量的東西，所以 P4 也算。只有 P6 的評測執行與評分讀。

**可以平行的工作**（P1 完成後，各自開 session，不碰同一批檔案）：
- P2 發現與抽取（`pickfit/discover/`、`pickfit/extract.py`）
- P3.1–P3.2 Box 與規則表（`pickfit/verify/`）
- P4.2–P4.4 MCP 細路徑（`worker/`，先用 3–5 筆手寫的假 profile）

**不變的規則**：
- 產品執行期只用 Meta 模型。Claude 只當開發工具與評測的受測 agent。
- 讀進來的 README、貼文、工具輸出一律包在 `<source>` 裡，當資料，不當指令；沙盒裡不放任何金鑰。
- 每一筆事實都記來源與查證時間；查不到寫 `null`。
- 新增第三方套件前先查授權，記在 `NOTICE`。
- 產品程式碼不能出現 `ecosyste.ms`（取得書面同意前，條款 §9）。移植任何 spike（`quality_signals.py`、`ch_integration_normalize.py`、`ch_packages_*.py` 等）時先拿掉這些呼叫。
- credits 餘額、帳單、Team ID 只記在 `.env` 或 `CLAUDE.local.md`，不進 repo（規則第 9 節第 5 條）。
- 不改 commit 時間、不改寫歷史、不把賽前資料搬進來（[CLAUDE.md](../CLAUDE.md)）。

---

## 6. 念誠要做或決定的事（👤）

| 期限 | 項目 |
|---|---|
| **10/28 今天** | ✅ 評測凍結、Modal 上限、Baseten 申請、Meta credits 表單與通知都已完成。每天能投入幾小時還沒定，暫照 arch H.1 的 10.5 h（少於 9 h → 先砍 Show HN 與 run page） |
| 10/31 | 要不要開 Workers Paid（每月 $5）；demo 用的 agent（建議 Claude Code，搭配分割畫面秀 Meta trace） |
| 11/1 | demo 主案與備案；第 5 幕提交哪個第三方 repo |
| 11/2 | 到 Discord 問：開放權重獎怎麼標、Community Vote 看哪個頁面；評審期的提交怎麼處理 |
| 選做 | 寄信給 ecosyste.ms 取得同意；買 `pickfit.dev` |

---

## 7. 狀態紀錄

| 時間（台北） | task | 結果 | 花費 |
|---|---|---|---|
| 10/28 16:18 | P0.1 | Meta key 有效、9 個模型、一次 `muse-spark-1.3` 呼叫成功；Anthropic key 有效；Mac、Cloudflare、GitHub 就緒 | Meta 約 $0.0002 |
| 10/28 17:06 | P1.1 | 評測 20 題與評分方式凍結（`5ac62ca`）。念誠決定：Mac 題（q08、q11、q12）親手跑；q15 用 CC0 公開錄音 | — |
| 10/28 17:15 | P0.2 | contributor 4／4（text、json_schema、tools、image）；1.3 的 json_schema、tools 通過 | Meta 約 $0.004 |
| 10/28 17:20 | P0.3 | 截圖放 tool 輸出或 user 訊息都看得到；schema＋tools 同一請求可以；串接迴圈可用但每回 15–18 秒，遇一次暫時性 503 | Meta <$0.001 |
| 10/28 17:25 | P0.4 | 寶藏候選 cli 2,352、local-llm 351（數字見 channels-hosting 筆記） | — |
| 10/28 17:35 | P0.5 | hello MCP 部署到 workers.dev，9 項協定檢查通過；Claude Code 無頭模式（`--strict-mcp-config`）實連成功；測完已移除。桌面 app 裡直接跑 `claude` 會失敗，要用 `env -i` | Anthropic $0.002 |
| 10/28 17:40 | P0.6 | Modal gVisor：16.4 秒可用、安裝 5 秒、斷網 smoke test 通過 | Modal 約 $0.01 |
| 10/28 17:45 | P1.2 | 專案骨架（`46d5ea7`） | — |
| 10/28 19:10 | P1.3 | `software.v1` schema 與 Meta strict 版（`6025851`）。實測：Meta 接受 11.7K 字元的抽取 schema，輸出過 pydantic，每欄附原文引用、不知道的填 null | Meta $0.0004 |
| 10/28 19:10 | P1.4 | `call_meta`＋共用帳本＋trace＋快取（`b0abe6c`）、`pickfit ping`／`spend`（`f18c7f0`）。122 個測試通過；實測第二次相同請求從快取回、$0；trace 裡沒有金鑰 | Meta <$0.001 |
| 10/28 19:10 | — | **下一步**：P2 交給**沒讀過 `eval/` 的新 session**（本 session 看過題目）；P3.1–P3.2、P4.2–P4.4 可以同時各開一個 session（第 5 節） | 今日合計：Meta 約 $0.01、Anthropic $0.002、Modal 約 $0.01 |
| 10/28 20:10 | P0.6–P0.8 | 念誠：Baseten 已申請（等審核）、Meta credits 表單與 Spend Limit 通知、Modal 上限約 $80 都完成。P2、P3、P4 三個 session 已開工（各自的 worktree）。花費守則加第 11 條（各家額度的用途分配） | — |
