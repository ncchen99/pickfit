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

## 1. 目前狀態（2026-10-28 23:24 台北）

| 項目 | 狀態 | 備註 |
|---|---|---|
| Meta Model API | ✅ key 有效 | `/v1/models` 有 `muse-spark-1.3`、`muse-spark-1.3-contributor`、`muse-spark-1.2(-contributor)`、`muse-spark-1.1`、`muse-wonder-1.0`、`muse-image-1.0`、`muse-voice-transcribe-1.0`、`sam-3.1`；**沒有 embedding 模型**（確認 arch F.3）。一次 `muse-spark-1.3` 呼叫（`reasoning_effort: minimal`）：52 token（推理 29）、1.7 秒、約 $0.0002。限額 3,000 RPM、4M TPM。台灣帳號可用，第一輪的最大風險解除 |
| Meta credits | ✅ 表單已送、Spend Limit 通知已設 | 入帳狀態記在 `CLAUDE.local.md`（credits 與帳單資訊不進 repo） |
| Anthropic API key | ✅ 有效 | **只用在評測**（受測 agent），產品執行期不用 |
| Mac | ✅ Apple M5、24 GB、macOS 27 | demo 第 4 幕與 Mac 人工驗證在這台做 |
| Cloudflare | ✅ `wrangler` 已登入 | |
| GitHub | ✅ `gh` 已登入 | 管線用 `GITHUB_TOKEN=$(gh auth token)`，不必另建 PAT |
| Docker | ✅ OrbStack（docker context `orbstack`） | P3 的 `DockerBox` 在這上面跑過 |
| Modal | ✅ token 在 `.env` | `MODAL_TOKEN_ID`／`MODAL_TOKEN_SECRET`；本機沒裝 CLI，用 `uvx --from modal modal …`；Python 端用 `uv run --python 3.12 --with modal …` |
| Baseten | ✅ 10/29 核准、P2.4 已在用 | key 只能用 `meta-models/muse-spark-open-1026`（`/v1/models` 有列）；限額 100 RPM、2M TPM；`reasoning_effort: low` 一次初篩 1.7 秒、約 560 token；強制 tool calling 可用，輸出符合 schema；key 放 `.env` 的 `BASETEN_API_KEY`（入帳狀態記在 `CLAUDE.local.md`） |
| E2B | ❌ | 備案，Modal 不能用時才註冊 |
| Python | 系統 3.9 | 專案用 `uv` 管 Python 3.12 |

---

## 2. 花費守則（省 token）

Meta 的 $150 credits 是整場的模型預算，Spend Limit 只寄信、不會停止扣款，所以上限全部由程式執行。

1. **開發與測試用 `muse-spark-1.3-contributor`**（$0.10／$0.20 每百萬 token，比 1.3 便宜 12–20 倍，150 RPM）。它的內容可能被拿去訓練，所以**只送公開資料**（公開 README、測試資料），不送使用者需求。正式產生資料、配對、評測、錄影才用 `muse-spark-1.3`。
2. `reasoning_effort` 預設 `minimal` 或 `low`；只有驗證 agent 用 `medium`。
3. 所有呼叫都走 `call_meta`（P1.4）：記 trace（model、token、花費）、硬上限、開發模式的回應快取（同一個請求不重複付費）。單元測試一律用錄好的 fixture，不打真的 API。
4. **只有一本帳**：花費記在 repo 外、所有 worktree 共用的 `~/.pickfit/ledger.sqlite`（加鎖寫入）。上限照這本帳算，平行的 session 才不會各算各的。
5. **上限分階段**：10/29 前每日 $3；10/29 起管線每日 $25，10/31 $80、11/1–11/2 每日 $45（念誠 10/31 同意，總額不變）；管線總額 $120 硬停（10/31 念誠同意由 $100 調高到 $115，同日為 MCP 擴充再從 Worker 移 $5）。Worker 另計：每日 $3、評審期總額 $15（10/31 由 $40 調降為 $20、再降為 $15，之前只花約 $0.3）；評測部署總額 $10。Windows 主機有自己的帳本，用 `PICKFIT_PIPELINE_TOTAL_CAP_USD=5` 另設 $5 硬停（這個設定只能調低）。
6. **先小後大**：新 prompt 先跑 1 筆，再 5 筆、30 筆；每一步看過 `usage` 才放大。
7. **不要整份 `source .env`**：裡面有 `ANTHROPIC_API_KEY`，從那個 shell 啟動的 `claude` 會改用 API key 計費。spike 在 subshell 裡只帶需要的變數，例如 `(set -a; . ./.env; set +a; unset ANTHROPIC_API_KEY; python3 spikes/…)`；`pickfit` 程式自己從 `.env` 只讀它要的變數。
8. Anthropic key 只給評測執行器與評分：先跑 2 題估單題花費，再跑全部。評測上限（10/29 事先登記）：第 1 次 $30、補充重跑 $60、Claude 評分 $20；看到結果後不追加。
9. Claude Code 的子 agent、workflow 不在迴圈裡呼叫付費 API。需要呼叫時由主 agent 執行，並回報花費。
10. 每天結束時，把當日花費寫進狀態紀錄（數字由帳本產生；只記花費，不記 credits 餘額）。
11. **上限是安全網，不是要省到最後。** Meta 的 Spend Limit 只寄信、不會擋，所以由程式擋：管線 $120＋Windows $5＋Worker 評審期 $15＋評測部署 $10＝$150，最壞情況剛好用完 credits，預估實際花費約 $120（10/31 調整）。各家額度照用途分配，**產品裡每個決定都用 Meta 模型**（評分 25%，第一輪必查；arch D.3、I #19）：
    - **Meta**：用在品質與規模。正式資料用 `muse-spark-1.3`（contributor 只用在開發）；驗證 agent 用 medium；修錯時可用 `web_search`；困難案例用 `muse-wonder-1.0` 重試；驗證目標從 50 筆提高到 100 筆以上。**11/1 檢查**：若預估到交件的 Meta 花費 <$60，就再擴大發現與驗證規模。
    - **Baseten（Muse Spark Open，開放權重）**：初篩；MCP 擴充的驗證 agent（10/31 比對 20 筆：通過率是 1.3 的 0.92、多通過的 2 筆人工確認屬實；抽取的主要欄位只有 62–71% 一致，沒達 90%，所以抽取、判讀、評分、Worker 仍用 `muse-spark-1.3`）；評測的第三評分者。每筆紀錄記下各段用的模型。帳本上限總額 $80、每日 $25；key 由比賽提供，超出配額不會另外收費（念誠 10/31），照常記帳。
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
- [x] P0.7 👤 Baseten（10/29 核准，key 已進 `.env`，spike 實測通過）：註冊並申請比賽 credits、建 key 放 `.env` 的 `BASETEN_API_KEY`、月預算 $20 開 enforce。核准後 agent 跑 `spikes/meta_baseten_hello.py`，確認 `meta-models/muse-spark-open-1026` 存在。
- [x] P0.8 👤 Meta Billing（10/28 完成）：送出 credits 表單、Spend Limit 通知設 $50 與 $100。

**G0（今晚）：已通過**（P0.2、P0.3）。json_schema 與 tool calling 能用就照計畫走。json_schema 不行 → 用 `finish` 工具＋pydantic 驗證；tool calling 不行 → 驗證 agent 改成「模型回 JSON 動作、程式執行」。兩者都不擋進度。

### P1 骨架與評測凍結（10/28）

- [x] P1.1 👤 **評測 20 題凍結**（10/28 17:06，commit `5ac62ca`）：草稿由 agent 在 10/28 新寫（不讀、不搬 `CLAUDE.local.md` 指向的賽前資料夾裡的評測草稿），念誠逐題審閱、修改並拍板，之後 commit `eval/questions.yaml` 與 `eval/README.md`（評分方式）。**這一步要在任何資料（`data/`、候選庫）寫入前完成。** 題目只寫需求與可檢查的條件，不寫預期答案。README 要照實寫明「草稿由 AI 起草、念誠審定」。
- [x] P1.2 專案骨架：`pyproject.toml`（`uv`、Python 3.12）、`pickfit/` 套件與 `pickfit` CLI、`tests/`、`NOTICE`（第三方授權）、`.gitignore` 補 `runs/`。目錄約定見第 5 節。
- [x] P1.3 pydantic schema `software.v1` 當唯一來源，產生 Meta strict JSON schema 與 `schema/software.v1.json`。欄位照 arch J（brief 第 11 節）＋ `repo_id`、`aliases`、`first_seen_at`；`verification` 等級照 arch C.3；`scores.quality.components` 照 arch B.3 的 6 個分項。
- [x] P1.4 `call_meta` v0（`openai` SDK、`base_url` 可切 Meta／Baseten）：記帳（`usage` × 單價，寫進第 2 節的共用帳本）、trace JSONL 寫到 `runs/traces/`、開發模式快取、第 2 節的硬上限、429 退避、504 改用 streaming 重試。完成標準：`uv run pytest` 通過（用 fixture）；一次真的呼叫經過 `call_meta`，留下 trace 與花費。

### P2 發現與抽取（10/29）

- [x] P2.1 GitHub search：每類別 3 條 query（topic＋`created:`＋`pushed:`＋星數 5–300），序列化、間隔 ≥2.1 秒；補 repo、README、release。**discovery 的 query 依類別寫，不從評測題目推導，由沒讀過 `eval/` 的 session 撰寫**（[eval/README.md](../eval/README.md) 第 3 節）；每條 query 連同時間記在 trace。（實作：`pickfit/discover/`；query 與時間記在 `runs/pipeline.db` 的 `queries` 表）
- [x] P2.2 正規化、去重、候選庫（`runs/pipeline.db`）：主鍵 `gh:<repo id>`、舊名進 `aliases`。移植 spike 時拿掉所有 ecosyste.ms 呼叫。
- [x] P2.3 規則前置（arch B.1）：fork、archived、template、沒 README、函式庫訊號。從 `spikes/quality_signals.py` 移植時拿掉所有 ecosyste.ms 呼叫，改用 GitHub REST。（目前 496 筆過 466 筆、94%，偏寬；README-only 的可疑 repo 有擋下。P2.6 前再收緊）
- [x] P2.4 開放權重初篩：Spark Open @ Baseten（`meta-models/muse-spark-open-1026`、`reasoning_effort: low`、強制 tool call），低信心、矛盾（`usable_software` 與 kind 對不上）、kind 為 other 或失敗的送 `muse-spark-1.3` 複查（覆蓋初篩），另固定抽 5% 複查比一致率。不給星數。被拒的候選抽取時跳過。Baseten 在帳本裡有自己的預算（總額 $80、每日 $25）。指令 `pickfit prescreen --limit N`。（10/29：957 筆規則通過的全跑完：留 907、拒 50（函式庫 29、研究或 benchmark 10、demo 3、框架 3 等）；複查 83 筆，其中 18 筆被 1.3 改判（都在被標記的案例裡）；**5% 抽樣 34／34 一致**。每筆初篩約 $0.004、1–2 秒。已寫出的 39 筆 profile 沒有被拒的。發現：初篩信心幾乎都 ≥0.9，低信心門檻只觸發 1 次；模型判的類別有 305 筆是 other，和 query 類別不一致，還沒拿來用）
- [x] P2.5 抽取 v0：`muse-spark-1.3`，Responses、`text.format` strict，每欄附引用。照「1 → 5 → 30」放大。（開發時用 contributor 跑到 36 筆，全過 schema；程式檢查每段引用確實出現在來源，已在 v0 做好。1.3 正式批次在 P2.6，估每筆約 $0.017）
- [x] P2.6 抽取收尾（10/30 上午，arch H.2）：程式檢查引用真的出現在來源、授權與 release 等事實欄位改用 API 值、重試、批次；晚上背景跑批次抽取，產生 P3 要用的 ≥30 份 profile。（10/29：規則 v2 過 452／496＝91.1%，多擋了釣魚套件、只有 README、只有二進位又沒授權的 repo；`muse-spark-1.3` 抽取 52 筆、平均 $0.014；寫出 39 筆 profile（dev_cli 23、local_ai 16），全部先標未驗證。待補：引用只證明那句話存在，不證明它支持填入的值；local_ai 產量偏低。同日補本地 AI：依類別定義加 13 條 query、抽取前先只用 GitHub 資料排序，多寫 57 筆 profile（local_ai 37、dev_cli 20），共 96 筆）

**完成標準**：`pickfit discover` 產生 ≥150 筆候選；漏斗每一格標模型與花費；5 份抽取檔過 schema。推理 token 超過估算 2 倍就降 effort。

### P3 驗證 agent（10/30 本機 → 10/31 Modal）

- [x] P3.1 `Box` 介面與 `DockerBox`（沿用 `spikes/sandbox_docker_install.py` 的限制）。（10/29 已補：`DockerBox` 與 `ModalBox` 都擋雲端 metadata 與私有網段；`run_background` 對真的 server 測過）
- [x] P3.2 安裝方式排序（套件管理器 → release 二進位 → 從原始碼建置）＋ 6–8 條常見錯誤規則。
- [x] P3.3 驗證 agent：Responses＋`previous_response_id`、`reasoning: {effort: medium, summary: auto}`；工具 `list_dir`、`read_file`、`run_command`、`run_background`、`finish`；停止條件：25 回合、15 個指令、20 分鐘、每款 $0.50、同一錯誤 3 次。終端機逐步印出模型、指令、exit code、花費。P0.3 量到串接回合每回 15–18 秒：先用 3–5 回合比較「`previous_response_id` 串接」與「每回合重送完整歷史（`store: false`）」的延遲與花費，選快的。（結果：重送完整歷史每回合 1–7 秒、串接 11–25 秒且遇過一次 400 找不到 response，預設改為重送＋`prompt_cache_key`。evnx 照 README 失敗後由 1.3 自己修好、graphtty 一次通過。10/29 已補：等級只看指令紀錄，藏住 exit code 的步驟不算；輸出 `VerificationRun`；重播時斷網跑 smoke test）
- [x] P3.4 截圖（Pillow 重繪終端輸出）＋判讀（另一次呼叫，圖片＋schema，回證據框）。（證據框是大概位置，沒框到文字的由程式標出）
- [x] P3.5 重播：全新 Box 照記錄的步驟重跑，成功才寫回 `install` 與 `verification`。（`--write-back` 只在 P2.6 資料的副本上測過）
- [x] P3.6 `ModalBox`（需 P0.6）：`runtime="gvisor"`、資源上限、先開網路安裝再收緊、預建 image、`--limits-test`。（`--limits-test` 12／12；沙盒 3–4 秒啟動；記憶體超限時 Modal 會把整個沙盒停掉）
- [x] P3.7 批次：`pickfit verify --batch N --concurrency 5`，demo 類別優先。（10 筆測試候選：第一輪 7／10，修好 3 個問題後 10／10 通過並重播；每筆中位數 91 秒、Meta 約 $0.08）
- [x] P3.8 挑 10 筆 demo 候選（Mac 能裝、免費、能離線）。（10/29：見 `docs/demo-candidates.md`。39 筆中 11 筆不能在 Linux 沙盒跑（多是圖形介面 app），其餘 28 筆有 25 筆通過並重播、寫回資料；10 筆候選全部通過並重播。Mac 上的安裝還沒實測（P6.4）；10 筆中原本只有 1 筆本地 AI 工具（localm）；同日補本地 AI 後，第 10 筆改為 cluaiz（斷網時 `/health` 有回應，官方安裝支援 macOS arm64），另列 8 筆本地 AI 備選。schema 補上「斷網是否通過」與測試前的準備指令）
- [ ] P3.9 Show HN 管道（計畫內，10/30 最後做，1.5 h）：沿用 `spikes/ch_comm_hn_showhn.py`；落後就第一個砍（arch H.5 #2）。（10/31 念誠決定要做：找剛發表的冷門工具，符合 pickfit 的宗旨。交給新 session，Meta 上限 $3、Baseten $10）

**10/30 完成標準**：一個「照 README 會失敗」的工具，由 Muse Spark 自己讀錯誤、補步驟、呼叫 `finish`，trace 看得到推理摘要；≥30 份 profile 已 commit。修不好 → 10/31 上午繼續修，細路徑 MCP 延到 11/1；用規則表兜底，只做到「安裝驗證」等級。
**G2（10/31 晚上，硬關卡）**：10 筆 demo 候選中 ≥5 筆在 Modal 通過並重播成功。沒過 → 停掉所有計畫內與超前項目，11/1 上午只修驗證；Modal 不能用 → 換 E2B（約 2 h）。**10/29 提前達成：10／10。**

### P4 MCP（10/28 hello → 10/31 細路徑 → 11/1 補完）

- [x] P4.1 hello 上線（＝P0.5）。
- [x] P4.2 `build_index`＋`pickfit publish`：驗 schema → commit → 建索引 → `wrangler deploy`；資料壞了就不部署。（`pickfit publish --env` 完成。10/29 第一次正式部署：`https://pickfit-mcp.ncchen99.workers.dev/mcp`，遠端 D1 `pickfit` 已建表、`MODEL_API_KEY` 已設；評測用的兩個部署等 P6 開跑前再建）
- [x] P4.3 D1 建表：`events`、`submissions`、`reverify_queue`、`meta_budget`（欄位照 arch E.3 的對照規則；`submissions` 要補 DDL）。不記 IP、不存需求原文，只存模型解析後的條件（brief 第 11 節）。（`worker/migrations/0001_init.sql`，目前只在本機 D1）
- [x] P4.4 細路徑：`find_software` 照 arch F.2 走「硬條件篩選 → 該類別 ≤60 張候選卡 → 一次 `muse-spark-1.3` 呼叫（`store: false`、effort `low`）解析需求並取捨 → 程式守門（slug 必須在候選裡、理由對得上欄位）」；模型失敗或超預算就退回寶藏分數排序，標 `matched_by: rules`、`degraded: true`。`MODEL_API_KEY` 用 `wrangler secret put` 設定。`get_install_guide` 只回重播過的步驟，不呼叫模型。（本機 `wrangler dev`＋假資料完成，37 個測試；部署步驟見 `worker/README.md`。**與 arch F.2 不同**：工具宣稱支援使用者的 OS 或在該 OS 驗證過就列入，回應一律註明實際驗證過的 OS；要改回嚴格版改 `worker/src/filter.ts` 的 `fits()`）
- [x] P4.5 補完：`find_alternatives`、`report_outcome`、`submit_software`；Host／Origin 檢查；Worker 每日上限與 `degraded`；回應帶 `how_we_know`、`evidence_url`、`matched_by`、`rec_id`。（10/29 完成，68 個 Worker 測試。另加評測專用唯讀部署：`TOOLS=readonly`、`eval` 環境 Meta 每日 $10、`eval-rules` 關掉模型配對。**還沒部署**，要念誠點頭後做 `wrangler d1 create`、遠端 migration、`ALLOWED_HOSTS`、`wrangler secret put`）

### P5 計分、提交、回報閉環（11/1–11/2）

- [x] P5.1 計分：規則分項＋`muse-spark-1.3` 文件 rubric＋寶藏分數（arch B.3，記 `formula_version`）。（10/29：`pickfit score`，公式 `b3.v1`；39 筆都有分開的品質、知名度、寶藏分數，已驗證的品質中位數 85，未驗證的壓在 69 以下；文件 rubric 每筆一次 1.3 呼叫，README 沒變就重用。待校正：寶藏分數分不開（25 筆已驗證有 22 筆算寶藏）、步驟數分級沒作用、知名度 7 項訊號有 4 項空白；校正由沒讀過 `eval/` 的 session 做。同日校正為 `b3.v3`（念誠選方案 1、寶藏門檻 80）：沙盒分數看驗證深度與安裝難度、只有真的修 README 才扣分，知名度改用候選池第 95 百分位當基準並補上下載量、套件庫、HN；96 筆已驗證 67 筆，品質中位數 81.2，寶藏 15 筆。審查找到的誤判（README 修正判斷、查不到下載量記成 0）交回 P5 session 修）
- [ ] P5.2 `pickfit watch`：每 60 秒讀 D1 `submissions` → 跑單筆管線 → publish。
- [ ] P5.3 回報 → 重驗 → git diff（計畫內）。只用**真的**失敗（評測或 Mac 實裝時照指南失敗的那一筆）測試與展示，回報標 `reporter: dev`；不送捏造的失敗回報（arch H.4、B.3）。
- [x] P5.4 run page：從 trace 產生靜態 HTML（計畫內）。（10/29：`scripts/run_page.py`，用方向鍵逐步看一次驗證；範例用 mcp-audit。trace 在不進 git 的 `runs/`；失敗的 run 目前沒留 trace）
- [x] P5.5 Meta 用量報表：從 trace 產生 README 與影片要用的數字。（10/29：`scripts/meta_usage.py`；02:46 時各 session 合計 1,429 次請求、80% 命中快取；沙盒驗證 79 次有 63 次通過並重播，每次中位數 73 秒、$0.048）
- [ ] P5.6 👤 11/1 晚上 demo 主案＋2 個備案定案；挑影片「供給端」那一幕（arch H.4 的 1:55–2:30）要提交的第三方 repo：不能是自己的作品，而且**從未送進 pickfit**。
- [ ] P5.7 產品網頁（交件前必做，見 brief 第 4.5 節）：使用者用一句自然語言搜尋，背後走和 MCP 同一份資料、同一套配對，回傳最適合的軟體，附理由、驗證結果與安裝方式；呈現 pickfit 的品牌與設計。demo 從 agent 帶到網頁現場（brief 第 5 節第 7 幕）。11/2 晚上功能凍結前完成；來不及就縮成只有搜尋與結果頁，不砍。

**11/1 完成標準**：≥30 筆 verified（目標 50），每筆有分開的品質、知名度、寶藏分數；在 Claude Code 用 `submit_software` 貼一個第三方 repo（**不能是 P5.6 留給錄影的那一個**），約 10 分鐘內出現在 `find_software`。

### P6 評測（11/2）

- [ ] P6.1 評測執行器：Claude Code 無頭模式（固定版本、固定提示），對照組（只有網路搜尋）與實驗組（＋pickfit MCP）；第三組 rules-only（要跑，只跑第 1 次）。**10/29 已事先登記**補充重跑、成立門檻、評分程序、輸題原因標記（`eval/README.md` 第 9.1 節，只有評測 session 讀）。對建資料的 session 有影響的只有這幾條：評測用兩個凍結的唯讀部署（`pickfit-eval`、`pickfit-eval-rules`；Worker 設 `TOOLS=readonly`、Meta 每日 $10）；從開跑到跑完不改 pickfit 的程式、資料、提示詞，不跑 `pickfit watch`、不 publish；開跑前記下 commit、部署版本與資料快照的雜湊。**隔離**：這台 Mac 的使用者設定裡有 toolradar 等 MCP，會污染對照組；每題在空的暫存目錄執行，用 `--strict-mcp-config --mcp-config <檔案>`（對照組空的、實驗組只有 pickfit），每題每組另外加跑 2 次當補充結果，主要結果仍是第 1 次（9.1）。旗標已在 P0.5 實測有效；記下 Claude Code 版本。**`claude` 一定要用 `env -i HOME="$HOME" PATH="$PATH" ANTHROPIC_API_KEY=… claude -p …` 啟動**，否則會繼承桌面 app 的 `ANTHROPIC_BASE_URL` 而失敗（P0.5）。先跑 2 題估花費。（10/30：執行器與 A4 的腳本、提示已 commit，還沒跑任何一題；`HOME` 改成每次全新的空目錄，使用者層級的設定、plugin、hook 都不會載入；`--bare` 會拿掉網路搜尋所以不用；模型 `claude-opus-5-5`，念誠確認。開跑前還缺：兩個評測部署、`eval/fixtures/`、L2 實跑環境、盲評工具）
- [ ] P6.2 收集答案；安裝步驟在乾淨容器（或 Mac）實跑。
- [ ] P6.3 照 `eval/README.md` 評分；👤 念誠做盲測兩兩比較。
- [ ] P6.4 👤 demo 那 3 筆在 Mac 上由念誠親手照 `get_install_guide` 驗證（`method: human`），驗完移除；agent 只準備檢查清單、收 log。

**完成標準**：結果表（含輸的題）＋系統數字（候選數、驗證通過率、提交到可被推薦的時間）。≥2 題「好答案在資料裡卻沒被推薦」→ 只調候選卡或加 BM25，不加新功能；調整後的版本不得再用這 20 題的成績當評測結果（9.1 F）。L2 實跑截止 11/3 12:00（台北）。**當晚功能凍結。**

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
| 10/31 | ✅ 開 Workers Paid（每月 $5；念誠自己在 Cloudflare 後台開）；demo 用的 agent 是 Claude 桌面 app（念誠 10/31） |
| 11/1 | demo 主案與備案；第 5 幕提交哪個第三方 repo |
| 11/2 | 到 Discord 問：開放權重獎怎麼標、Community Vote 看哪個頁面；評審期的提交怎麼處理 |
| 選做 | 寄信給 ecosyste.ms 取得同意；買 `pickfit.dev` |

---

## 7. 狀態紀錄

時間是記錄該列的 commit 時間（台北；`git log` 可對照）。10/28 19:25 更正：先前幾列寫的是估計時間，已改成實際 commit 時間。

| 時間（台北） | task | 結果 | 花費 |
|---|---|---|---|
| 10/28 16:18 | P0.1 | Meta key 有效、9 個模型、一次 `muse-spark-1.3` 呼叫成功；Anthropic key 有效；Mac、Cloudflare、GitHub 就緒 | Meta 約 $0.0002 |
| 10/28 17:06 | P1.1 | 評測 20 題與評分方式凍結（`5ac62ca`）。念誠決定：Mac 題（q08、q11、q12）親手跑；q15 用 CC0 公開錄音 | — |
| 10/28 17:21 | P0.2 | contributor 4／4（text、json_schema、tools、image）；1.3 的 json_schema、tools 通過 | Meta 約 $0.004 |
| 10/28 17:21 | P0.3 | 截圖放 tool 輸出或 user 訊息都看得到；schema＋tools 同一請求可以；串接迴圈可用但每回 15–18 秒，遇一次暫時性 503 | Meta <$0.001 |
| 10/28 17:21 | P0.4 | 寶藏候選 cli 2,352、local-llm 351（數字見 channels-hosting 筆記） | — |
| 10/28 17:21 | P0.5 | hello MCP 部署到 workers.dev，9 項協定檢查通過；Claude Code 無頭模式（`--strict-mcp-config`）實連成功；測完已移除。桌面 app 裡直接跑 `claude` 會失敗，要用 `env -i` | Anthropic $0.002 |
| 10/28 17:21 | P0.6 | Modal gVisor：16.4 秒可用、安裝 5 秒、斷網 smoke test 通過 | Modal 約 $0.01 |
| 10/28 17:19 | P1.2 | 專案骨架（`46d5ea7`） | — |
| 10/28 17:46 | P1.3 | `software.v1` schema 與 Meta strict 版（`6025851`）。實測：Meta 接受 11.7K 字元的抽取 schema，輸出過 pydantic，每欄附原文引用、不知道的填 null | Meta $0.0004 |
| 10/28 17:46 | P1.4 | `call_meta`＋共用帳本＋trace＋快取（`b0abe6c`）、`pickfit ping`／`spend`（`f18c7f0`）。122 個測試通過；實測第二次相同請求從快取回、$0；trace 裡沒有金鑰 | Meta <$0.001 |
| 10/28 17:46 | — | **下一步**：P2 交給**沒讀過 `eval/` 的新 session**（本 session 看過題目）；P3.1–P3.2、P4.2–P4.4 可以同時各開一個 session（第 5 節） | 今日合計：Meta 約 $0.01、Anthropic $0.002、Modal 約 $0.01 |
| 10/28 18:55 | P0.6–P0.8 | 念誠：Baseten 已申請（等審核）、Meta credits 表單與 Spend Limit 通知、Modal 上限約 $80 都完成。P2、P3、P4 三個 session 已開工（各自的 worktree）。花費守則加第 11 條（各家額度的用途分配） | — |
| 10/28 23:24 | P2.1–P2.3、P2.5、P3.1–P3.3、P4.3–P4.4 | 三個 session 的分支併入 main（merge `914b3a9`、`62006dd`、`bceb932`），衝突只在 `pickfit/cli.py` 與 `NOTICE`，兩邊都留；221 個 Python、37 個 Worker 測試通過。P2：496 筆候選、規則過 466 筆、抽取 36 筆全過 schema。P3：evnx 照 README 失敗後由 1.3 自己修好；預設改為每回合重送完整歷史（1–7 秒／回合）。P4：`find_software`、`get_install_guide` 在本機完成，OS 條件放寬並註明實際驗證過的 OS（見 P4.4） | Meta：管線 $0.198（verify $0.158、extract $0.040）＋Worker 本機 D1 $0.044；Anthropic 約 $0.12 |
| 10/28 23:24 | — | **下一步**：P3.4–P3.7（判讀、重播、`ModalBox`、批次）、P2.6（收緊規則＋1.3 正式抽取）、P4.5（補完工具與部署）可各開一個 session；都不讀 `eval/` | — |
| 10/29 00:25 | P6.1 | 評測的事先登記 commit（`e2e025b`，`eval/README.md` 9.1）：補充重跑、成立門檻、盲評程序、輸題原因標記、砍除順序；先由 3 個獨立審查者找漏洞再修。念誠確認數字：補充重跑 $60、Claude 評分 $20、評測部署 Meta 每日 $10、L2 截止 11/3 12:00、rules-only 要跑。Baseten：申請已送出但還沒核准，核准前不呼叫 | — |
| 10/29 00:58 | P2.6、P3.4–P3.7、P4.2、P4.5 | 三個分支併入 main（merge `46c53c9`、`b18b657`、`fe40784`），沒有衝突；336 個 Python、68 個 Worker 測試通過。P2.6：39 筆 profile。P3：Modal 上 10 筆測試候選全部通過並在新沙盒重播。P4：五個工具與評測專用唯讀部署完成，還沒部署。另把上一列的 credits 餘額字樣拿掉（credits 資訊不進 repo） | Meta 累計 $2.44（10/29 $1.50）；Modal 約 $0.25 |
| 10/29 00:58 | — | **下一步**：P3.8 用這 39 筆跑批次驗證、挑 10 筆 demo 候選，衝 G2（10/31）；決定 P3 提出的 schema 缺口（「斷網也通過」與測試前的準備指令沒地方存、安裝步驟上限 500 字）；部署要念誠點頭 | — |
| 10/29 02:18 | P3.8、G2 | P3.8 分支併入 main（merge `c7a549b`）；342 個 Python、69 個 Worker 測試通過。39 筆中 25 筆在 Modal 通過並重播、寫回資料；10 筆 demo 候選（`docs/demo-candidates.md`）全部通過並重播，**G2 提前達成（10／10）**。驗證時找到 9 處 README 或 profile 寫錯（列在候選文件，沒有改寫抽取的事實） | Meta 累計 $4.92（10/29 $3.97）；Modal 約 $0.45 |
| 10/29 02:18 | — | **下一步**：P5（計分、提交、回報閉環）；部署 Worker 要念誠點頭；Mac 上親手驗 demo 前 3 筆（P6.4）；本地 AI 類的已驗證工具偏少，需要時再加發現 query | — |
| 10/29 | P0.7 | Baseten 核准比賽 credits（只能用 `meta-models/muse-spark-open-1026`）。`.env` 已留 `BASETEN_API_KEY` 欄位，等念誠從一次性連結取 key 貼上；之後跑 `spikes/meta_baseten_hello.py` 確認，P2.4 開放權重初篩解除封鎖 | — |
| 10/29 11:55 | P0.7 | key 進 `.env`，`spikes/meta_baseten_hello.py` 一般模式與 `--tools` 都通過：`-1026` 存在、JSON 與 tool call 都符合 schema；限額 100 RPM、2M TPM。P2.4 解除封鎖 | Baseten 約 $0.003 |
| 10/29 12:07 | P5.1、P5.4、P5.5 | P5 分支併入 main（merge `fdea9ed`）；375 個 Python、69 個 Worker 測試通過。39 筆都有評分（公式 `b3.v1`），驗證紀錄與安裝步驟沒變；run page 與 Meta 用量報表可用。寶藏分數待校正 | Meta 累計 $11.91（10/29 $10.96，含其他 session） |
| 10/29 12:07 | — | **下一步**：補本地 AI 的分支（local_ai 已驗證 4 → 28，新增 57 筆）測完再問念誠要不要合併，新增的要跑評分；推論等級驗證另有 session 在做；寶藏分數校正；部署 Worker 要念誠點頭；Mac 上親手驗 demo 前 3 筆（P6.4） | — |
| 10/29 12:11 | P2.4 | 開放權重初篩完成（`d82efba`）：957 筆規則通過的候選全跑，留 907、拒 50；複查 83 筆、改判 18；5% 抽樣和 `muse-spark-1.3` 一致 34／34。抽取已改成跳過被拒的候選。照 1 → 5 → 30 → 全部放大 | Baseten $3.80；Meta 複查 $0.66（Meta 10/29 累計 $11.15，含其他 session） |
| 10/29 12:12 | P2.6、P3.8 | 補本地 AI 與推論等級驗證兩個分支併入 main（merge `4944df7`）；388 個 Python、69 個 Worker 測試通過。新增 57 筆 profile（共 96 筆）；已驗證的本地 AI 工具 4 → 28 筆，其中 goinfer、xyntetik-runner 在沙盒實際載入小模型跑出推論；另多驗證 18 筆 CLI 工具。demo 第 10 筆改為 cluaiz。驗證加了 T4 GPU 選項（berth 只有裝假的 `nvidia-smi` 才過，維持未驗證）。新的 57 筆還沒評分 | Meta 累計 $12.09（10/29 $11.14）；這兩個 session 的 Modal 約 $0.31 |
| 10/29 12:12 | — | **下一步**：新的 57 筆跑評分、寶藏分數校正（交給沒讀過 `eval/` 的 session）；寫回要擋掉「只在沙盒裡才需要的步驟」；部署 Worker 要念誠點頭；Mac 上親手驗 demo 前 3 筆（P6.4） | — |
| 10/29 13:06 | P4.1、P4.2 | Worker 第一次正式部署（版本 `b53d4be6`，資料 commit `17924c7`、96 筆）：`https://pickfit-mcp.ncchen99.workers.dev/mcp`。遠端 D1 `pickfit` 建好並套用 0001、0002；`MODEL_API_KEY` 用 pipe 設成 secret。實測 5 個工具都在，問一題由 `muse-spark-1.3` 配對、沒有降級。新 57 筆的分數要等評分校正分支合併後再發布一次 | Worker 呼叫 1 次 |
| 10/29 14:31 | P5.1 | 評分校正 `b3.v3` 併入 main（merge `408b8e6`）；408 個 Python、69 個 Worker 測試通過。96 筆只有分數欄位變了；寶藏 28 → 15 筆（CLI 8、本地 AI 7），demo 候選只剩 mcp-audit、phantom 有寶藏標記。另修：第一次部署讓 2 個發布測試失敗（`d94d8c3`）、registries.py 註解不再出現 ecosyste.ms（`63b20b4`）。Worker 重新發布（版本 `dd5fe5f4`）。審查 workflow 確認 6 個計分誤判（README 修正判斷、查不到下載量記成 0 等），交回 P5 session。部署後前兩次 `find_software` 因 `model_http` 退回規則排序，Worker 遇到這種錯誤不會重試 | Worker 呼叫 4 次 |
| 10/29 14:47 | P5.1 | 評分 `b3.v4` 併入 main（merge `ca1767e`），修掉審查找到的 10 個問題：README 修正判斷從 21 筆降到 15 筆、檢查用指令不再算安裝步驟、查不到的下載量記成 null。5 筆品質和審查算出的正確值一致（second-brain 93.2、all-code 90.2 等）；寶藏仍 15 筆（second-brain 加入、babelscribe 移出），all-code 第一。420 個 Python、69 個 Worker 測試通過；Worker 重新發布（版本 `a186681b`）。Worker 模型呼叫的重試交給 P4.5 session（14:30 前後 Meta 間歇回 404「model not found」） | Meta $0（文件評分全部重用） |
| 10/29 15:14 | P5.7 | 文件分支併入 main（merge `9a074a0`），只動 brief.md、hackathon-rules.md：補上重複造輪子的代價（維護、成本、token）、從使用者渴望描述（這場比賽實質是創新創業競賽，兩個面向都講）、收錄的兩條路（長期有很多開發者投稿，用同一套 agentic 審查）、影片要講的問題與長期規劃（brief 5.1）。念誠決定產品網頁改成交件前必做（自然語言搜尋、和 MCP 同一套平台、呈現品牌），新增 P5.7 | — |
| 10/29 15:28 | P4.5 | Worker 的 Meta 重試併入 main（merge `42e0fe9`）：遇到 429、5xx、404「model not found」在逾時內重試一次，events 多記 `degraded_reason`、`model_attempts`、`model_statuses`。先對遠端 D1 套用 migration 0003 再發布（版本 `7e81b751`）；420 個 Python、78 個 Worker 測試通過，live 實測有記錄。審查順帶發現 main 上 `get_install_guide` 的回應不符合它宣告的 outputSchema（多了 `works_offline`、`first_task_setup`），嚴格驗證的用戶端會拒收，交給 P4.5 修。P3 的失敗紀錄分支審查仍有會把沙盒限制寫成「工具失敗」的情況，先不合併 | Worker 呼叫 2 次 |
| 10/29 15:41 | P4.5 | `get_install_guide` 的格式修正併入 main（merge `189a3e2`）：宣告補上 `works_offline`、`first_task_setup`、`known_issues[].kind`，新增 5 個工具共 21 種回應的格式測試。Worker 重新發布（版本 `68023a9c`）；線上 126 份安裝指南（macOS 96 筆、Linux 與 Windows 各抽 15 筆）全部符合宣告的格式。83 個 Worker 測試通過 | Worker 不呼叫模型 |
| 10/29 16:45 | P3 | 失敗紀錄的處理併入 main（merge `f91679f`），經 4 輪對抗審查後定案：管線**不會自動寫「失敗」**，沙盒看到的錯誤一律寫成「未驗證」（沙盒限制給具體原因，否則 `suspected_tool_fault`），失敗指令、全新沙盒與結構檢查的結果留作證據；「失敗」只能來自人工驗證或人工檢查發布檔案（`artifact_check`）。hillock 保留失敗（PyPI wheel 只有 dist-info、沒有程式碼），coderai `needs_container`、holdspeak `needs_root`，`checked_at` 改為沙盒實際執行的時間。另含：差異類型標記（`readme_wrong`、`sandbox`、`tool_handled`、`note`）、有新版本才重新排隊、擋假系統指令、較弱的通過不覆蓋較強的。555 個 Python、83 個 Worker 測試通過；Worker 重新發布（版本 `2be896e0`） | Meta $0.04、Modal 約 $0.03 |
| 10/29 21:07 | P4 | 兩個 Worker 修改併入 main：`well_known_option`（merge `947aba2`；資料裡沒有更合適的工具時，可以提一個知名免費工具，標 `verified: false`，「沒裝過、沒查過」由程式寫，名字、免費、說明都有防呆）與 `verified_on_user_os` 看 CPU 架構（merge `c199445`，解了 `find.ts` 一處衝突）。555 個 Python、104 個 Worker 測試通過；Worker 重新發布（版本 `a8573d34`），線上實測：linux/arm64 對只在 x86_64 驗過的工具回 false 並寫明、模糊搜尋檔案的需求提了 fzf 並標未驗證，格式全部合格。知名工具參考紀錄的試點（4 筆）留在分支、不進 main。Mac 分支第二輪審查仍有可能取得 root 的路（指令掛在 admin 的桌面工作階段），未合併 | Worker 呼叫 2 次 |
| 10/30 00:02 | P6.1 | 評測執行器與 9.1 A4 要求的腳本、提示 commit（`dc28da3`），**還沒跑任何一題**。照第 4 節隔離（每次全新的空 HOME 與工作目錄、只給 WebSearch、WebFetch，實驗組另加 pickfit），照 9.1 實作 B1 順序、B2 無效判定與重跑、B3 補充重跑、B4 上限與 q01、q02 估算、A3 前後紀錄（含兩個部署送出的資料必須一致）、G 的砍除順序、D5 比對。審查 workflow 確認 5 個問題（D5 在逗號切句會漏抓、金鑰或額度錯誤會被當成有效執行等），已修並補測試，37 個測試通過。70 筆原始驗證紀錄已從各 worktree 複製到 main 的 `runs/eval-evidence/`。模型 `claude-opus-5-5`（念誠確認） | Anthropic 冒煙測試約 $0.011 |
| 10/30 23:12 | P3 | P3 未讀腳本的註記併入 main（merge `98fc62f`）：安裝步驟執行了下載來、沒先讀過的腳本，記成 `note` 類的差異與執行備註，不改等級、不算 README 修正。macOS 驗證器併入 main（merge `4350c0e`）：Tart VM（macOS 26、arm64），主機端 softnet 在連網模式擋主機與多播、斷網模式全擋；限制檢查 27／27，經 4 輪對抗審查修掉 admin 取得 root、桌面工作階段提權、連得到主機、多播四條路；已知限制：只擋往外的連線、NAT hairpin。6 筆在真的 macOS arm64 上驗證通過：mcp-audit、patient-zero、orbit、mi-lsp、shep、cluaiz。603 個 Python、104 個 Worker 測試通過；Worker 重新發布（版本 `6f4258f7`，資料 `ea10aaafb181`、96 筆），線上 mcp-audit 的 macOS 安裝指南回 `verified`、`runner: tart-vz`。另外三個分支（P5 的 README 修正只算 `readme_wrong`、P5.2／P5.3 提交與回報閉環、P5.7 產品網頁）五個一起測過可合併，還沒合併；閉環分支審查找到 `reverify` 可被無限觸發的問題，要先修 | Worker 不呼叫模型 |
| 10/31 00:09 | P6.1 | 評測 9.2 事先登記 commit（`f0b48fe`），**仍未跑任何一題**：補充重跑上限 $60 → $100；Muse Spark Open（Baseten）當第三評分者，只描述、以念誠的判定為準；受測 agent 換成 `claude-haiku-5-5` 的小模型對照（次要分析）；Mac 題另在 Tart VM 跑一份（選做，只並列）；B 題組 12 題（開發者 CLI、本地 AI、MCP server 各 4 題，取自 10/27 前的公開提問，由沒看過資料的 session 依事先 commit 的查詢與種子抽樣，11/2 前凍結，分開報告、不參與 D 的判定）。Anthropic 評測上限合計 $205。另外：新增 MCP server 類別（`mcp-category` session）、擴充驗證資料（`grow-verified-data-extra` session）、Windows 驗證器（念誠 Windows 家用版上的 session：VirtualBox＋Windows 11 Enterprise 評估版＋路由 VM）已開工；GUI app 驗證等 Windows 做完再做 | — |
| 10/31 01:06 | — | Meta 上限調整（merge `3011cad`，念誠同意）：管線總額 $100 → $115、10/31–11/2 每日 $25 → $45；Worker 評審期總額 $40 → $20（到目前只花 $0.07），重新發布（版本 `624e11a2`）。Windows 主機有自己的帳本，用只能調低的 `PICKFIT_PIPELINE_TOTAL_CAP_USD` 設 $5。最壞情況合計 $150。原因：四個 session 共用管線帳本，10/31 已花 $21.80；擴充資料到 242 筆已驗證（dev_cli 39 → 166、local_ai 28 → 76，每筆中位數約 $0.09），還要評分、MCP server、功能覆蓋、GUI 探測，約 $55 | 管線累計 $44.14（10/31 $21.80） |
| 10/31 02:04 | P6.1 | 評測 B 題組凍結（`dec4cb9`，merge 進 main）：照 9.2 E，查詢條件與種子在抓資料前 commit（`111c4d3`）；候選池 3,834 則公開提問（GitHub Discussions 3,176、HN 561、SE 97），依種子順序讀 1,045 則、排除 1,033 則、收 12 則（開發者 CLI、本地 AI、MCP server 各 4 題）。念誠逐題審定：b01 維護期 12 個月、b07 手機記憶體 4 GB 以下、b08 保留開源條件。L2 測試資料與數字門檻在第一次開跑前 commit | — |
| 10/31 02:24 | P2–P5 | MCP server 第三類併入 main（merge `1f715c5`）：發現 520 → 規則 471 → 初篩留 442 → 抽取 69 筆 → **49 筆驗證通過**（service 38：handshake＋一次不需帳號的 `tools/call`；function 11：`initialize`＋`tools/list`），46 筆斷網也通過；未驗證 10 筆有原因（`needs_account` 6 等），另 10 筆 README 只支援 Windows／macOS 或沒有安裝方式。install 等級不算 MCP server 通過；要金鑰才能啟動的一律未驗證，不用假金鑰。工具說明不離開沙盒，只檢查有沒有對 agent 下指令的字句（記成 note）。MCP server 有自己的熱門度參考（`npx -y` 每次啟動都下載，下載量偏高）。`get_install_guide` 回 `claude mcp add` 與 `mcpServers` 設定。655 個 Python、111 個 Worker 測試通過；Worker 重新發布（版本 `4174b58d`，165 筆），線上 MCP 需求由 muse-spark-1.3 配對、考慮 49 筆 | 這個 session：Meta $6.93、Baseten $1.92、Modal 約 $0.35 |
| 10/31 02:29 | — | 10/31 的管線每日上限 $45 → $80（念誠同意，總額 $115 不變）：$45 在 02:25 用完，擴充資料與功能覆蓋都停下；剩下的工作約 $37、總額還剩 $47.67，提前用完讓兩個分支今天就能合併。11/1–11/2 維持每日 $45 | 管線累計約 $67.3 |
| 10/31 02:57 | P2.6、P3.8、P5.1 | 擴充資料併入 main（merge `f09b0a0`）：**已驗證 67 → 268 筆**（dev_cli 39 → 181、local_ai 28 → 87），新增 338 筆全部用 `b3.v4` 評分；連同 MCP server 共 503 筆。漏斗（累計）dev_cli 發現 2,786／抽取 103、local_ai 2,099／437；初篩 5% 抽樣與 1.3 一致 100／100。每筆已驗證工具 Meta 中位數 $0.107。sentinel-surveillance 的寫回撤回（只裝了 Flask），維持未驗證。656 個 Python、111 個 Worker 測試通過；Worker 重新發布（503 筆）。本機 `wrangler dev` 延遲：dev_cli 13–15 秒、local_ai 9–11 秒，都在 25 秒逾時內、沒有降級。**問題**：某類別超過 60 筆時，送給模型的 60 張卡是寶藏分數最高的，不是最相關的；dev_cli 現在一定超過 | 這個 session：Meta $38.71、Baseten $4.19、Modal 約 $1.72 |
| 10/31 03:05 | P3 | Linux GUI 啟動檢查併入 main（merge `0e6c630`）：Modal `runtime="vm"`＋虛擬顯示器，桌面 app 安裝後在顯示器上啟動、截圖、由模型判讀（只看 app 自己視窗的裁切）；等級仍是 install，另記 GUI 層級（`window`、`ui_rendered`）。經兩輪隔離審查：第一輪找到 app 能偽造視窗證據與截圖（證據工具以 box 使用者身分、靠 PATH 執行；回報行可被 app 的 log 蓋過），已改成證據由另一個 uid 以絕對路徑產生、寫進 0700 目錄、回報行帶只在 stdin 傳的 nonce；另修：關掉 user namespace、seccomp 擋 AF_VSOCK（原本 box 使用者連得到主機 CID 2 port 52）與 io_uring、Xvfb 也在同一個 filter 下、殘留行程讓啟動失敗、限制檢查的正向對照決定成敗（VM＋顯示器 29／29）。舊的 5 筆寫回因證據來自可偽造的路徑先撤回，再以新路徑重驗：ohmail、hilbertraum、lokalbot（首次執行畫面）、hivemind、neuraldeck（主畫面），斷網重播啟動。692 個 Python、111 個 Worker 測試通過；Worker 重新發布（版本 `26db33da`）| 這個 session：Meta 約 $2.7、Modal 約 $0.4 |
| 10/31 03:10 | P4 | Worker 顯示 GUI 證據（merge `40da021`）：`find_software`、`find_alternatives`、`get_install_guide` 的 `verification.gui`（層級、畫面、顯示器、斷網啟動），`how_we_know` 寫明看到什麼（虛擬顯示器上開了自己的視窗、另一個模型讀截圖判定主畫面已顯示、斷網重播），也寫明沒有用它的功能；`level` 仍是 install。視窗標題是 app 自己設的字，刻意不放進回應（避免 prompt injection）。693 個 Python、114 個 Worker 測試通過；Worker 重新發布 | — |
| 10/31 04:01 | P4 | 相關度優先的候選卡併入 main（merge `5bbca1e`，解了 `find.ts` 一處 import 衝突）：通過硬條件超過 60 筆時，先由 muse-spark-1.3（minimal、5 秒上限）把需求轉成英文關鍵字，再用 BM25 選 50 張最相關＋10 張寶藏分數最高的卡；失敗就用需求原文。693 個 Python、127 個 Worker 測試通過；Worker 重新發布（版本 `cc0eec5d`，503 筆）。上線驗證：5 個需求（英文與中文、指定類別與不限類別，候選 130–322 筆）全部由模型一次配對、沒有降級，關鍵字步驟都是 `ok`、50 張卡依相關度選；Worker 端延遲 7.7–15.4 秒（用戶端 8.0–15.6 秒），都在 25 秒逾時內，每次 $0.029–0.038。本機同一 commit：rules-only（MATCH_MODE off）沒有任何模型呼叫、$0、50 毫秒內；關鍵字呼叫失敗（無效金鑰）時退回需求原文、約 1 秒回降級答案（中文需求沒有關鍵字時回到寶藏分數順序）；關鍵字失敗但配對成功的情況由單元測試涵蓋。**觀察**：rules-only 與降級時的排序看起來不太相關（同一相關度層裡改用寶藏分數排），待改。檢查集的需求是從資料改寫的，偏向字面相符；獨立、真實的需求要看評測（20 題與 B 題組） | Worker 約 $0.17 |
| 10/31 04:27 | P4 | rules-only 與關鍵字失敗時的排序併入 main（merge `4f05ef1`）：泛用字（tool、terminal、file、OS 名稱…）權重 0.2、分數乘上需求字詞的涵蓋比例、258 詞的靜態中→英詞典（在任何測試集之前 commit）、「不用／without」後面的字當條件不算；改用實際分數排序，OS 驗證與寶藏分數只在同分時用。仍然零成本、不呼叫模型。獨立測試集：Muse Spark Open 依常見工作寫 30 則英文、20 則中文需求（沒看工具資料），依固定種子分成調整用與保留的兩半，相關度由 Muse Spark Open 評。保留的一半（25 則）：Precision@5 25.9% → 32.9%、前 5 名至少一個相關 58.8% → 82.4%、MRR 0.506 → 0.628、Recall@60 97.3% 不變；中文 P@5 13.3% → 26.7%。rules-only 延遲中位數 5 毫秒。AI 路徑不變：重播存下的關鍵字，1,268 個配對請求 0 個不同（對照組 1,015 個不同）。693 個 Python、134 個 Worker 測試通過；Worker 重新發布（版本 `039ca130`），線上兩則需求由模型配對、關鍵字 `ok`、約 12 秒 | Baseten $1.07、Meta $0（Worker 約 $0.07） |
| 10/31 11:26 | P4 | rules-only 的配合度標籤併入 main（merge `093c8b7`）：每個推薦依需求的具體字詞有幾個出現在工具資料裡，標 good／partial／weak，並寫出涵蓋與缺少的字；整個回答標 `match_quality`，沒有推薦達到 partial 時，說明 pickfit 沒有明確做得到這件事的已驗證工具、列出的是最接近的、缺哪些字。只加標籤：推薦、順序、數量與 main 相同（新保留集 60 則、調整用 107 則都 0 個不同）。共三輪：前兩輪在不合時拿掉推薦，新保留集上有合適工具的需求有 33% 被說成沒有，沒達標準，念誠決定改成只加標籤。新保留集（60 則，在任何判斷之前 commit `5e0b990`）：good 標籤 50% 成立（7/14）、weak 93% 確實不合；有合適工具的 30 則中 10 則整體標 none，但推薦照列。已知限制：詞典外的中文字看不到；「不需要 GPU」的 GPU 仍被當成需要的字。AI 路徑不變（1,268 個配對請求與回應 0 個不同），`find_software` 說明多一句請 agent 照標籤呈現 partial／weak。693 個 Python、145 個 Worker 測試通過；Worker 重新發布（版本 `63f4fbe3`），線上兩則由模型配對、沒有新欄位；本機 rules-only 五則都帶標籤、約 0 毫秒 | Baseten $2.17（三輪合計）、Meta $0（Worker 約 $0.03） |
| 10/31 12:29 | P4 | 否定詞範圍修正併入 main（merge `5d30990`）：中文否定（不需要、不需、不用、不要、不必、不想、無需／无需、無須／无须、沒有、免）與英文否定（without、no、no need for、don't／doesn't／do not／does not + need／require／want）都涵蓋後面的英文字與技術名詞，到子句結束為止（標點、但／可是／而是／but、新的肯定動詞、的、and、for、四個字）；和／或／、／or／/ 延續否定。「不需要 GPU」不再把 GPU 當成需要的字，「不需要 GPU，但需要 CUDA」保留 CUDA。用在 rules 排序、配合度標籤，以及 find_software 縮成 60 張卡時比對的字；find_alternatives 的痛點照原話讀（「no dark mode」是想要 dark mode）。硬性條件不受影響（用 agent 填的欄位，不讀需求文字）。AI 路徑：重播 1,268 個配對請求，42 個的 60 張卡不同（每個約換 5 張），都來自真的否定；find_alternatives 0 個。對其中 20 個實際呼叫 Meta（舊請求兩次、新請求一次）：舊請求兩次之間就有 5／20 不同；穩定的 15 個中 11 個推薦完全相同、2 個只換順序、2 個第三名不同，第一名除一次換序外都沒變，影響約在模型自身的雜訊範圍。排序 P@5 在五組標註集都不變、60 張卡的召回相同或略升；good 標籤仍 50% 成立。已知限制：否定在後（「GPU 不需要」）、「without Docker and Kubernetes」的 Kubernetes、詞典外的中文字（番茄鐘、模糊／放大）。693 個 Python、148 個 Worker 測試通過；Worker 重新發布（版本 `a4e147e6`），線上兩則由模型配對（20.8、13.8 秒），本機 rules-only 四則否定案例照預期 | Meta $1.90（重播）、Baseten $0（Worker 約 $0.03） |
| 10/31 13:18 | P5.1 | 評分 `b3.v5` 併入 main（merge `5f4130d`）：只有標成 `readme_wrong` 的差異才算 README 修正（舊的文字規則把 66 個 note、28 個 sandbox、1 個 tool_handled 也算進去，又漏掉部分 readme_wrong）。328 次通過的驗證中 README 修正 164 → 88；86 筆品質分數改變（76 升、10 降，−7.5 到 +13.9，中位數 +6.0）；寶藏 71 → 81（新增 11、少 1：modeljars）。紀錄只改 `scores` 與 `updated_at`，知名度與文件 rubric 不變，沒有呼叫模型、GitHub 或套件庫；`pickfit score --refresh` 會把 b3.v4 帶到 b3.v5。699 個 Python、148 個 Worker 測試通過；Worker 重新發布（版本 `f8684b96`）。另：Muse Spark Open（Baseten `/v1/responses`）實測相容嚴格 json_schema、strict function tools、重送 reasoning 與 function_call_output 的多回合、`prompt_cache_key`（有快取命中），不支援 `previous_response_id`；念誠決定 MCP 擴充改用它跑抽取與驗證 agent（判讀、評分、Worker 留在 1.3），先比對 20 筆過門檻才放量 | Meta $0、Baseten $0.011（測試） |
| 10/31 13:32 | P5.2、P5.3 | 提交與回報閉環併入 main（merge `29cf450`）：`pickfit watch` 每 60 秒讀 D1 的提交、一個 repo 一筆紀錄、狀態照實際發生的事走、用線上 Worker 的 `data_sha256` 判斷是否已上線；MCP server 與 GUI app 的提交會用對應的沙盒。`pickfit reverify`：回報只決定「要不要重驗」，回報文字完全不進模型；改寫的步驟只有在每個套件名與網址都出現在 README、pickfit 先前的步驟或 repo 裡時才寫回，否則標 `held` 等人看；`--reverify` 不能和 `--publish` 一起用。新增 darnlink（function 等級、已重播）。上一輪審查的 7 點都修好；已知限制 9 點記在交接筆記（例如 Worker 的 `next` 文字、reverify 只用 Linux 沙盒）。**線上實測還沒跑**：今日 Meta 已到上限，11/1 凌晨從 main 提交 `Alberto-Codes/docvet` 跑一次 | — |
| 10/31 13:32 | P5.7 | 產品網頁併入 main（merge `490f091`）並上線：`https://pickfit-mcp.ncchen99.workers.dev/` 用一句話搜尋，背後是和 MCP 同一個 `findSoftware`、`installGuide`；伺服器端產生、所有值都 escape、nonce CSP；顯示 MCP 握手與客戶端設定、GUI 啟動證據、rules 路徑的配合度標籤，知名工具標「not verified by pickfit」。網頁搜尋在 Worker 每日 $3 中用到 $2 就不再呼叫 Meta、每次先預留兩次呼叫的花費、每位訪客每分鐘 6 次；評測部署關掉網頁。779 個 Python、183 個 Worker 測試通過；Worker 重新發布（版本 `07125622`，504 筆），rate-limit binding 被接受；線上一次搜尋 14 秒、選出 3 個 MCP server。已知：寬泛的中文需求（322 筆通過）一次配對超過 25 秒逾時、退回規則排序 | Worker 約 $0.3（含分支實測 $0.22） |
| 10/31 13:52 | P2–P3 | MCP 擴充的模型與上限（merge `1fa3a68`）：念誠要求「介面相容就用 Muse Spark Open」。MCP session 比對 20 筆（Baseten $2.27、Meta $0.075）：驗證 agent 通過 11／20（1.3 是 12／20，比值 0.92，過 0.85 門檻；Spark Open 多通過的 ken、vibes-plug 人工確認屬實，錯誤主張都被守門擋下）；抽取主要欄位只有 62–71% 一致（第一輪 20 筆有 11 筆違反列舉值，Baseten 不強制 json_schema），沒過 90%。所以這批走混合：抽取、判讀、評分用 `muse-spark-1.3`（約 $4.8），驗證 agent 用 Spark Open（約 $7）。功能覆蓋停在 $110，$115 沒有餘裕，從 Worker 移 $5：管線總額 $115 → $120、Worker 評審期 $20 → $15，最壞情況合計仍 $150。779 個 Python、183 個 Worker 測試通過；Worker 重新發布（版本 `23c1b8eb`）。另：更深的 MCP 發現（$0）多找到 750 個新 repo，去掉一個 repo 農場後 520 筆待初篩 | Baseten $2.27（比對）、Meta $0.075 |
| 10/31 16:35 | P6.1 | 評測準備併入 main（merge `d7b5bef`，只動 `eval/`），**仍未跑任何一題**：20 題的 L2 測試資料（各題判定方式統一成 `_shared/` 的共用工具，產生器重跑與 commit 的檔案一致）；執行器支援 9.2（Haiku 對照組、B 題組、Muse Spark 第三評分者）；D5 擴充到 GUI 證據、MCP 握手、功能覆蓋與程式寫的 how_we_know；盲評與去識別工具（seed 20261102）。**9.3 事先登記**（開跑前 commit）：三個 L2 映像從同一個固定 digest 的 `ubuntu:24.04` 建出（q03 用 base、q10 用 base-git，其他用 dev）；擋外連用 user＋network namespace，連 DNS 一起擋，正反對照都通過；35 個固定版本工具 sha256 與官方 0 不一致；q19 測試模型改 `qwen2.5:7b`（llama3.2:3b 0/3），q18–q20 用 8 vCPU（q19 長提示 348 秒，4 vCPU 要 758 秒）；Ollama 的 local-only 只套在評分者啟動的伺服器；q11 在 24 GiB Mac 以實測峰值判定；改動行數一行算一次；第二評分者 `claude-opus-5-5`（與受測 agent 同模型，已揭露）；Muse Spark Open 跑第二批 MCP 驗證 agent 的揭露。q15 錄音（LibriVox〈一件小事〉，公有領域，念誠同意）已下載核對；語音只有 41.6／55 秒，念誠決定縮短同一錄音裡超過 0.5 秒的停頓，參考逐字稿待念誠校對後才 commit。779 個 Python、71 個執行器、25 個共用測試通過 | Modal 約 $1.9、Anthropic $0.007、Baseten $0.004 |
| 10/31 20:03 | — | 念誠決定：開 Workers Paid（每月 $5，他自己在 Cloudflare 後台開）；demo 用 Claude 桌面 app；P3.9 Show HN 管道要做。新開三個 session（各自的 worktree、不讀 `eval/`、合併前回報、11/1 18:00 前）：Show HN 管道（Meta 上限 $3、Baseten $10）；gVisor 沙盒斷網時仍查得到 DNS 的修正（VM 版已用 nftables 擋）；Mac 驗證器改由主機狀態判斷 VM 失敗，不再看 guest 的 stderr 文字（Windows 審查找到的同類問題）。另有工作標籤 `jobs`（給候選卡篩選與 rules 排序用，新測試集在產生 jobs 前 commit）在量，Meta 部分等 11/1 00:00 每日上限重置 | — |
| 10/31 20:41 | P6.1 | 評測準備 q15 併入 main（merge `cbc94f6`，只動 `eval/`），**仍未跑任何一題**：念誠核准的 LibriVox〈一件小事〉錄音，超過 0.5 秒的停頓縮成 0.3 秒，60 秒片段裡語音 46.66 秒（55 秒的目標沒達到，照實記為未通過）。片段從「這是民國六年的冬天」開始：原本從時間推的「從故事第一句開始」被念誠聽音檔推翻，各處已更正、量測數字沒改。參考逐字稿由念誠聽寫校正，到「……要自己惹出是非」為止；簡繁寫法不同的字剛好 60（門檻 ≥60，沒有餘裕）。重建逐位元相同。779 個 Python、q15 25 個、執行器 71 個測試通過（執行器要 `--with pyyaml`） | — |
| 11/1 00:48 | P3 | Windows 驗證器併入 main（merge `cdd23ed`）：VirtualBox 的 Windows 11 guest 放在 Alpine router VM 後面，安裝與測試用標準使用者 sbx；主機端鎖、確認 VM 是自己的才動、主機通道設定少一項就拒絕、權限只允許標準使用者那 5 種、密碼掃描有對照組。兩輪審查找到的問題都已修好。9 筆紀錄都來自 base `16ea69df29ff`：8 筆到 function，aria-code 記為 install，labelize 接受官方 release 執行檔。sbx 能開 `\\.\VBoxGuest`（筆記的風險 a）在現在的架構關不掉，已寫進筆記。**還沒寫回 `data/`**，先由 Windows session 提方案。865 個 Python、183 個 Worker、執行器 71 個測試通過；沒動 Worker，不用重新發布 | — |
| 11/1 01:06 | P3 | Mac 驗證器修正併入 main（merge `05effe2`，念誠同意）：VM 是否失效改看主機狀態（`tart run` 是否還在、agent 探測），不再比對 guest 的 stderr 文字；`read_file` 卡住會變成 box 錯誤；mDNS 探測失敗就擋下。872 個 Python 測試通過 | — |
| 11/1 01:06 | P3 | 功能覆蓋併入 main（merge `e8d8803`，念誠 10/31 同意跑完就併），Worker 重新發布（版本 `2e750b29`）：通過驗證的 run 記下 README 宣稱的主要功能哪些實際測過（要有通過的 smoke test，且另一個模型看輸出確認在做那件事；那個模型呼叫失敗就一個都不算），沒測的附原因；`find_software` 與 `get_install_guide` 都帶 `features`，分數公式不用它。329 筆通過驗證的紀錄中 237 筆有覆蓋：882 個功能測過 232 個、28 個測試失敗（26 個由沙盒限制解釋，open-self 與 supercli 指向工具本身）。重新驗證讓 14 筆等級上升、沒有下降；寶藏 3 進 3 出（新 run 的沙盒分不同）。跑到共用帳本 $110 停下（$109.76／$120），75 筆沒跑到。918 個 Python、189 個 Worker、執行器 71 個測試通過；上線後 `find_software` 兩題都走模型、約 10 秒 | Meta $2.20（今晚 20 筆） |
| 11/1 01:28 | P3 | Windows 資料併入 main（merge `7216140`，念誠同意；Windows session 的 commit `8c58618`，念誠在那邊確認後才推送），Worker 重新發布（版本 `5b79c056`）：9 款工具多了 Windows x86_64 的 run，install.windows 從 README 說法換成實際重播的步驟（base `16ea69df29ff`、router `583d254c306d`；不重跑、不呼叫 Meta）。8 款 function，aria-code 記為 install（要網路的 smoke 不算 function）。9 款都註明步驟在 PowerShell 7（pwsh 7.6.9）以標準使用者跑過，內建的 5.1 沒驗證；3 款加註裝完要開新終端機。Linux run、features、scores、紀錄等級逐欄不變；個資掃描無命中（只有沙盒帳號 sbx）。Windows run 早於功能覆蓋，所以不宣稱 Windows 上測過哪些功能。918 個 Python 測試通過、publish dry-run 504 筆；上線後 arm64 使用者會看到「只在 windows/x86_64 檢查過」 | — |
| 11/1 01:52 | P2 | MCP 批次併入 main（merge `c8ece9b`，念誠同意）：新增 100 筆 MCP 伺服器紀錄，58 筆通過驗證（agent 用 Baseten 上的 Muse Spark Open，judge 與評分用 muse-spark-1.3；`judge_model_for` 確保 agent 用 Spark Open 時 judge 仍是 1.3）。新規則：安裝引用到別的指令 clone 的資料夾不算（copy rule）；透過通用代理（mcp-remote 等）連到非本機網址的握手不算，opencaselaw 因此改為未驗證（它連的是官方託管的伺服器）。4 段被標記的工具描述經原文確認都不是要模型對使用者隱瞞，不下架。6 筆裝在或指向 /tmp 的加註要放到永久目錄。花費 Meta $4.38、Baseten $9.08 | Meta $4.38 |
| 11/1 01:52 | P3 | gVisor 斷網後的 DNS 修正併入 main（merge `e7c7374`，念誠同意，經一輪對抗審查後修正）：沙盒使用者跑在自己的網路命名空間裡，唯一的對外通道（slirp4netns）在斷網時被關掉，所以斷網後查不到 DNS，localhost 照常；Xvfb 也放進只有 loopback 的命名空間（審查發現它能替沙盒使用者查 DNS，VM 也有同樣的缺口）。被削弱的兩個探測已補回並加強，新增 display_no_network 探測（在原本的 main 上會失敗）。限制測試：gVisor 22/22、gVisor＋顯示 30/30、VM 23/23、VM＋顯示 31/31。重跑 305＋234 筆 gVisor 紀錄，只有 motita 的 `motita doctor` 變成需要網路（已改，works_offline 不變）。Worker 重新發布（版本 `ccfbec01`，604 筆，387 筆通過驗證）。975 個 Python、189 個 Worker、執行器 71 個測試通過。上線後 01:46–01:49 有 5 次 Meta 回 404（model not found，和 10/29 同一個 Meta 端問題），退回規則排序並如實標示；之後恢復 | Modal 約 $0.8 |
| 11/1 01:59 | P3.9 | Show HN 管道併入 main（merge `82d535b`，念誠核准的方案），Worker 重新發布（版本 `ae8f9ad1`，648 筆）：讀近 60 天的 Show HN 貼文（Algolia HN Search API 與官方 HN API，條款寫進 NOTICE），留下指向 GitHub repo、標題或內文有三個類別用詞、300 星以下的；貼文只說去哪裡找，紀錄的欄位都來自 repo，貼文只以 `hn` 來源列出網址。漏斗：7,893 篇 → 598 個 repo（511 個是新的）→ 抽取 45 → 紀錄 44 → 驗證 32（dev_cli 16、MCP 13、本地 AI 3），16 筆是寶藏。花費 Meta $1.92、Baseten $5.07（上限 $3／$10）。993 個 Python、189 個 Worker、執行器 71 個測試通過 | Meta $1.92 |
