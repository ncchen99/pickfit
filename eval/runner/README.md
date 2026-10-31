# 評測執行器

照 [eval/README.md](../README.md) 第 4 節、第 9.1 節與第 9.2 節執行與核對。這個資料夾只有評測 session 讀；建資料與配對的 session 不讀 `eval/`。

## 怎麼跑

```bash
uv run python eval/runner/collect_evidence.py                          # D5 要比對的原始沙盒紀錄 → runs/eval-evidence/
uv run --with pyyaml==6.0.2 python eval/runner/run.py snapshot --label before   # A3
uv run --with pyyaml==6.0.2 python eval/runner/run.py run1             # B1、B2、B4
uv run --with pyyaml==6.0.2 python eval/runner/run.py check --round run1        # B2 核對
uv run --with pyyaml==6.0.2 python eval/runner/run.py reruns           # B3
uv run --with pyyaml==6.0.2 python eval/runner/run.py haiku            # 9.2 C（9.1 全部結束後）
uv run --with pyyaml==6.0.2 python eval/runner/run.py bset             # 9.2 E（9.2 C 之後）
uv run --with pyyaml==6.0.2 python eval/runner/run.py check --round haiku       # 每一輪都核對（run1、run2、run3、haiku、bset）
uv run --with pyyaml==6.0.2 python eval/runner/run.py snapshot --label after    # A3（所有輪都跑完之後）
uv run --with pyyaml==6.0.2 python eval/runner/run.py compare          # A3：前後是否相同
uv run python eval/runner/d5_check.py                                  # D5
uv run --with pyyaml==6.0.2 --with anthropic==2.3.0 python eval/runner/grade.py run --batch B.jsonl --grader claude --out G.jsonl   # C4 第二評分者
uv run --with pyyaml==6.0.2 python eval/runner/grade.py run --batch B.jsonl --grader muse --out G.jsonl                            # 9.2 B 第三評分者
uv run --with pyyaml==6.0.2 python eval/runner/grade.py agree --batch B.jsonl --human l1-form.csv --grades claude=G1 muse=G2 --out A.json
```

測試（不呼叫模型；不在 `tests/` 底下，pickfit 的測試不會收到評測程式）：

```bash
uv run --with pyyaml==6.0.2 --with pytest python -m pytest eval/runner/tests -q
```

## 隔離（第 4 節）

每次執行都是新的 `claude -p` 程序、新的空工作目錄、新的空 `HOME`，環境變數只有 `HOME`、`PATH=/usr/bin:/bin`、`ANTHROPIC_API_KEY`、`DISABLE_AUTOUPDATER=1`、`LANG`、`MCP_TIMEOUT=30000`（讓 Worker 冷啟動時也來得及在第一回合前連上）。這台 Mac 使用者層級的 CLAUDE.md、plugin、hook、skill、其他 MCP 都不會載入；這台 Mac 沒有管理員層級的 Claude Code 設定（10/29 確認）。

- 工具：`--tools WebFetch,WebSearch`，實驗組與 rules-only 另加 pickfit MCP（`--strict-mcp-config`，MCP 設定檔只有 pickfit；對照組是空的）。
- 不用 `--bare`：它會拿掉 WebSearch 與 WebFetch（10/29 用 Claude Code 2.1.304 實測）。
- 2.1.304 沒有回合上限的旗標，所以每次執行的上限是時間（`timeout_s`）與金額（`--max-budget-usd`，`per_run_budget_usd`）。達到上限都照 B2 算有效、照常評分。
- 10/29 冒煙測試：對照組的工具清單是 `WebFetch`、`WebSearch`；接上 pickfit 時多出 pickfit 的工具；不指定模型時預設是 `claude-opus-5-5`。

## 固定的設定（[config.json](config.json)，A4）

| 項目 | 值 |
|---|---|
| Claude Code | 2.1.304（`~/.local/bin/claude`；評測期間 `DISABLE_AUTOUPDATER=1`） |
| 模型 | `claude-opus-5-5`（Claude Code 對 API key 使用者的預設；念誠 2026-10-29 確認）；9.2 C 的對照模型 `claude-haiku-5-5` |
| 開場 | 第 4 節的原文 |
| 每次執行上限 | 900 秒、$3 |
| 花費上限 | 第 1 次 $30、補充重跑 $100（9.2 A）、評分 $20（B4）、Haiku 對照 $15（9.2 C）、B 題組 $40（9.2 E），Anthropic 合計 $205（9.2 F）；Muse Spark 第三評分者 Baseten $5（9.2 B） |
| 估算題 | q01、q02（B1、B4） |
| 部署 | `pickfit-mcp-eval`（模型配對）、`pickfit-mcp-eval-rules`（只用規則），都是唯讀工具 |

這些值在任何一組開跑前都還能改；開跑後只能照 9.1 節另寫 9.x 小節。

## 對照第 9.1 節

| 規則 | 在哪裡 |
|---|---|
| A3 版本紀錄（前、後） | `run.py snapshot`：git commit 與是否有未 commit 的檔、資料快照（含 Worker 用的同一個 `data_sha256` 算法）、`runs/pipeline.db` 與漏斗的 SHA-256、原始紀錄清單的 SHA-256、兩個部署的 `/` 回應與最新版本 ID、Claude Code 版本、模型、config 與題目檔的 SHA-256 → `eval/results/versions-<label>.json`。兩個部署送出的資料必須相同，也必須等於 repo 的資料，否則記為問題；有問題時 `run1` 不會開跑。`run.py compare` 比對前後紀錄 |
| A4 腳本與提示 | D5：`d5_check.py`（檔頭列出欄位對應）；C6：[../prompts/c6_no_fit_search.md](../prompts/c6_no_fit_search.md)；B2：`run.py check` |
| B1 順序 | `run1_order`：單號題對照組先、雙號題實驗組先、rules-only 最後；同一題各組接著跑，不並行 |
| B2 無效執行 | `classify`：只有執行結束在 Anthropic API 錯誤（5xx、429、overloaded、回應途中的 server error），或執行器當掉、沒有最終答案，才算無效；立即重跑、最多 2 次，每次都保留。執行器中斷留下的資料夾補記為無效再續跑。逾時、金額上限照常評分。金鑰、帳號、額度錯誤不算一次執行：整個指令停下，修好再跑。每次有效執行後核對版本、模型（含中途換模型）、工具清單；某組設定錯誤就停下，`run.py void` 把該組那一輪整輪移到 `voided/`（保留、照報告）後重跑。pickfit 沒連上算 pickfit 的錯（照常評分，E 的 `tool_error`），不算設定錯誤 |
| B3 補充重跑 | `cmd_reruns`：每題 C2、E2、E3、C3；從 q01 第 1 次開跑起 24 小時或花費到上限才停；截止時正在跑（含跑完時已過截止）的那題兩組記「未跑」 |
| B4 花費 | 以結果訊息的 `total_cost_usd` 累加；沒有結果訊息（逾時）時，上限的計算保守地以每次上限計，預估則以平均單次花費計。q01、q02 跑完預估超過 $30 就停，要先 commit 9.2 才能繼續；補充重跑預估超過 $100（9.2 A；原本 $60）只跑第 2 次 |
| 第 4 節「同一個 24 小時」 | 第 1 次跑完時記下第一次開跑到最後結束是否在 24 小時內；超過時照實報告 |
| G | 第 1 次預算吃緊時，先砍 rules-only（G 的第 6 項），對照組與實驗組照跑。其他砍除項目用 `run.py cut --item haiku|bset --reason ...` 記錄（9.2 F 的順序：VM 紀錄、Haiku、Muse Spark、B 題組），不會默默略過 |
| 9.2 C Haiku 對照 | `run.py haiku`：要等 `reruns` 完成或停止；對照組與實驗組各跑 20 題一次，順序照 B1（不跑 rules-only），只換模型（`haiku_model`），其餘同第 1 次；B2 無效執行與設定核對同樣適用（核對的模型是 Haiku）；上限 $15，到了就停並記錄停在哪題。結果在 `runs/haiku/` |
| 9.2 E B 題組 | `run.py bset`：要等 9.1 與 9.2 C 都結束（或 C 被砍，`cut --item haiku`）；`questions-b.yaml` 的 12 題，對照組與實驗組各一次，順序照 B1（`b01` 單號對照組先），其餘同第 1 次；上限 $40；結果在 `runs/bset/`，分開報告。A3 紀錄也記下 `questions-b.yaml` 的雜湊 |
| 第 5 節盲測偏好、C4 盲評 | `blind.py`。去識別：pickfit、pick-fit、pickfit 的 MCP 工具名（含 `mcp__pickfit__` 前綴）、`rec_` 紀錄 ID、含 pickfit 的網址與主機一律換成 `[source]`，其他字不動；可能透露來源的字（sandbox、verified、replayed、treasure 等）逐一列給念誠看。`prefer --round run1 --seed N`：每題一對（對照、實驗），隨機排成 A、B，產生 `prefer-form.html`（離線可用，自動暫存，匯出 `choices.json`）與 `prefer-key.json`，表單印出 key 的 sha256。`answers --rounds run1 run2 run3 haiku --seed N`：所有有效執行的答案去識別、打亂，加上要填的 `picks.csv`（首選與安裝方式，C2）；B 題組另外一批（`--rounds bset`）。`l1-batch`：同題、同首選、同安裝方式的答案合成一項，打亂，產生給 `grade.py` 的 `l1-batch.jsonl` 與給念誠的 `l1-form.csv`（q10、q20 用 [L3] 項目，C1）。填完後才用 `unblind-prefer`、`unblind-l1` 以 key 對回組別。`--seed` 沒有預設值（怎麼固定 seed 是待決定的第 7 項），每個輸出都記下 seed 與輸入的雜湊 |
| C4、9.2 B 評分者 | `grade.py`：同一份評分說明（[../prompts/grader_l1.md](../prompts/grader_l1.md) 兩個標記之間的文字，原字送出）與同一批盲評資料（`blind.py` 產生，看不到組別、次數、模型、pickfit）。Claude 第二評分者：`grader_model`（`claude-opus-5-5`，effort `grader_effort`；這個模型不接受 temperature，固定的是模型 ID 與 effort），花費算進評分的 $20。Muse Spark 第三評分者：Baseten 的 `meta-models/muse-spark-open-1026`、temperature 0，花費算進 Baseten 的 $5。每次呼叫前以最壞情況估算，可能超過上限就停；花費記在 `eval/results/grading-spend.json`。可以中斷續跑。`agree` 只描述：三方兩兩一致率與每一個不一致的項目，以念誠的判定為準。10/31 冒煙測試各一次：Claude $0.0072、Muse $0.0039，都回傳合格的 JSON |
| D5 | `d5_check.py`：每一則 pickfit 回應的 (a)–(e) 主張逐一對照快照裡的沙盒原始紀錄，寫出每一筆主張與判定；原始紀錄要和清單、A3 紀錄的清單雜湊一致。10/31 起也對照：GUI（`verification.gui` 的 tier、screen、launch_offline ↔ replay 的 gui 檢查與 `judge.json` 的 screen）、MCP server（`mcp_client_config` 的工具清單、數量、`called_tool`、`works_offline` ↔ replay 的 handshake 與 tools/call）、功能覆蓋（`features.checked` ↔ replay 裡同一條指令通過，且 `feature_judge.json` 說 shows_it_working；欄位以合併進 main 的版本為準）、程式寫的 `how_we_know`（作業系統、架構、等級，以及 MCP、GUI 那一句）；紀錄的等級取 `verification_run.json` 與 replay 兩者較低者。規則路徑的 `match`／`match_quality` 是標籤、不是驗證主張，只核對一致性、另列 `labels`，不算違反。`coverage_note` 也當模型文字掃描。B 題組與 Haiku 各自用 `--rounds bset`、`--rounds haiku` 分開列出。10/31 用線上 Worker 的兩份安裝指南（aptu-coder 的 MCP、neuraldeck 的 GUI）對真的原始紀錄跑過：8 筆主張都找得到 |

## 開跑前還要做的

1. 功能凍結後建兩個評測部署（A1；`worker/README.md` 的評測部署步驟），確認 `/` 回應的 `tools` 是 `readonly`、`match_mode` 各是 `model` 與 `off`。
2. 第 8 節的測試資料 commit 到 `eval/fixtures/`（L2 用）：10/31 已 commit（`eval/fixtures/README.md`）；外部素材等念誠決定。
3. L2 的實跑環境（第 5 節：Modal、`ubuntu:24.04`，記下 image digest）：`l2_image.py`。念誠確認第 6 項後：
   ```bash
   uv run python eval/runner/l2_image.py plan                                   # 不連網、不花錢
   uv run python eval/runner/l2_image.py build --variant dev --base-digest sha256:... --confirm-spend
   uv run python eval/runner/l2_image.py inspect --variant dev --confirm-spend  # 記下套件版本、跑 egress selftest
   ```
   三個變體：`dev`（`ubuntu:24.04` 加 python3、git、ca-certificates、curl、strace，第 6 項的提案）、`base`（原樣，q03 要求映像裡沒有 python3）、`base-git`（只加 git，q10）。基底一律用 digest 固定，Modal 不加 Python；紀錄在 `eval/results/l2-images.json`。
4. 跑 `collect_evidence.py` 與 `snapshot --label before`，兩者都 commit 後才跑 q01。
5. 9.3 節（q18–q20 的固定模型、q11 在哪台 Mac 跑、怎麼固定 seed）在第一次開跑前 commit。
