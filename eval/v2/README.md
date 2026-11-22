# 評測 v2：agent 有接 pickfit 和沒接，差多少

對應 [brief](../../docs/brief.md) 第 15.8 節與 [gap audit](../../docs/proposals/brief-v15-gap-audit.md) 的 P2-10。黑客松期間的 v1 評測（`eval/` 根目錄的題組、`eval/runner/`、`eval/results/`）原樣保留，v2 的東西都放在這個資料夾，不覆蓋也不重用 v1 的結果。

## 1. 要回答的問題

同一批需求，同一個 agent，一組沒接 pickfit、一組接了 pickfit MCP，最後的結果差多少。v1 只請 agent「推薦」，評分者再照答案去裝。v2 改成讓 agent 在乾淨的 Linux 沙盒裡**自己動手把事情做完**，做完後由檢查腳本判斷結果能不能用。這樣量到的才是 agent 實際上會碰到的情況：找錯工具、裝不起來、裝了不需要的東西、繞了很久才做完。

## 2. 兩組對照

| 組別 | agent | 工具 |
|---|---|---|
| control（沒接） | Claude Code 無頭模式，模型與版本固定（`config.json`） | Bash、Read、Write、Edit、Glob、Grep、WebSearch、WebFetch |
| treatment（有接） | 同一版本、同一模型、同一段開場 | 同上，加上 pickfit MCP（`find_software`、`find_alternatives`、`get_install_guide`） |

- 兩組唯一的差別是有沒有 pickfit。用 `--strict-mcp-config` 搭配每次產生的 MCP 設定檔，control 是空的，treatment 只有 pickfit，不會載入這台電腦上其他 MCP。
- 每題每組在一個新開的沙盒（`ubuntu:24.04`，x86_64，可連網，可 sudo）裡跑一次。兩組誰先跑由題號的 hash 決定（`runner.slot_order`），一半的題目 control 先、一半 treatment 先。
- 驗收結果無效的情況：treatment 沒載入 pickfit 的工具、control 竟然呼叫到 pickfit、沙盒本身起不來。這些記成 `valid: false` 並寫下原因，該題兩組都不進配對統計。agent 自己逾時不算無效，算這題沒做成。

## 3. 三個核心指標

每一筆紀錄（`runner.RECORD_FIELDS`）都有這幾個欄位：

| 指標 | 欄位 | 怎麼算 |
|---|---|---|
| 1. 第一次就裝好且能用 | `first_try_working` | agent 跑完後，評分者跑一次該題的檢查，exit 0 才算。只跑一次，評分者不修指令、不補步驟、不重試 |
| 2. 花掉的 token 與時間 | `tokens_in`、`tokens_out`、`cost_usd`、`elapsed_s` | 取自 Claude Code 的 stream-json：`tokens_in` 包含 cache 讀寫；`cost_usd` 優先用 CLI 回報的 `total_cost_usd`；`elapsed_s` 是整個 agent 執行的 wall-clock，不含檢查 |
| 3. 該說「自己做就好／內建就夠了」時有沒有說 | `decision_honest` | agent 最後要寫一行 `DECISION:`。決定落在該題的 `acceptable_decisions` 才算。H 類題（見下節）只要跑過任何安裝指令（apt、pip、npm、npx、cargo、`curl | sh` 等，見 `INSTALL_PATTERNS`）也算不誠實 |

`DECISION` 的四個選項對應 brief 15.5「怎麼用它」：`use_existing`（直接用）、`extend_existing`（從擴充介面加功能）、`build_it_yourself`（自己寫一小段）、`builtin_enough`（內建就夠）。

`score.py` 只拿兩組都有效的題目配對，並列出每題結果、各賽道小計，以及沒配對到的題目和原因。

## 4. 題組

[tasks.json](tasks.json) 共 20 題，2026-11-22 新寫，沒有讀 `data/software/`。題目只寫需求和檢查方式，**不寫預期的工具**（`validate_tasks` 會擋 `expected_tool`、`answer` 這類欄位）。

| 類別 | 題數 | 驗證重點 |
|---|---|---|
| A：agent 用的能力（CLI、MCP server、自架服務） | 10 | 裝得起來、功能有效。其中 3 題帶 `security_focus`，檢查 MCP 的權限範圍、對外連線或提示注入 |
| B：人用、UI 本身就是價值的網頁 | 3 | `web_probe`：指定的手機或平板尺寸下打得開、核心流程走得完，並記載入時間與追蹤器 |
| C：人機協作的創作與文件工具 | 3 | 先檢查輸出檔案格式，再用 `gui_spot` 在 Xvfb 抽查「打得開、改得到、存得回去」 |
| H：該說自己做就好／內建就夠了 | 4 | 一次性小腳本 2 題、作業系統內建就能做 2 題，`honesty_trap: true` |

另外依「誰來用結果」標了 `user_of_result`（agent 8 題、人 12 題），繁體中文題 4 題，難度 easy 9、medium 8、hard 3。這些分佈都能從 `--dry-run` 的輸出看到。

檢查用的 `verify-*` 指令放在沙盒的 `/opt/verify/bin`，以唯讀方式掛載，不在 agent 的 PATH 上，評分時才加進 PATH。需要標準答案的檢查（`--key`）讀評分者手上的 key，key 不放在沙盒裡，也不放進這個 repo 讓建資料的 session 看到。

## 5. 跑法

```bash
# 免費：驗證題組格式、列出執行計畫與花費估計，不呼叫任何模型、不開沙盒
uv run python eval/v2/runner.py --dry-run

# 離線自測
uv run pytest -q eval/v2/test_v2_eval.py

# 付費實跑（每組各跑一次；--box-cmd 是進沙盒執行指令的前綴，例如 docker exec -i <box>）
uv run python eval/v2/runner.py --execute --group control   --box-cmd "<prefix>" --run run1
uv run python eval/v2/runner.py --execute --group treatment --box-cmd "<prefix>" --run run1

# 對照表
uv run python eval/v2/score.py eval/v2/results/run1/control.json eval/v2/results/run1/treatment.json \
  --out eval/v2/results/run1/report.md
```

`--execute` 在這些條件都滿足前會直接拒絕：`tasks.json` 的 `frozen_at` 有值、每個 fixture 都有 `sha256`、`config.json` 的 Claude Code 版本已固定、操作的人自己 export 了 `ANTHROPIC_API_KEY`。runner 不會去找 `.env` 或任何 key 檔。花費上限以整個 run（兩組合計）計算，下一題可能超過上限就停。沙盒只透過 `--box-cmd` 進出，不綁定任何一家平台。

## 6. 開跑前還要做的事

目前完成的是設計、題組、runner、評分與離線測試。第一次付費實跑前還缺：

1. 依各題 `fixtures[].make` 產生 fixture，算出 `sha256` 填回 `tasks.json`；C 類的音訊與文件素材要先確認授權並記下來源。
2. 寫 `/opt/verify` 裡的 `verify-*` 檢查工具和評分 key，並用一個已知正確、一個已知錯誤的結果各跑一次，確認檢查本身沒壞。
3. 固定 Claude Code 版本與 pickfit 的程式、資料 commit，記進結果的 `meta`。
4. 先跑 `estimate_tasks` 兩題估單題花費，再決定全跑。
5. 上面都做完後填 `frozen_at` 並 commit，那一刻就是凍結。之後題目與檢查不改，只在本文最後追加勘誤。

## 7. 隔離守則

- 建資料、配對、計分的 session 不讀 `eval/`，包括這個資料夾。讀過題目的 session 不寫 discovery 的 query。
- 評測 session 不改 `data/`、`pickfit/`、`worker/`。
- v1 的題組、結果、帳本保持原樣，不回頭改。
- 評分 key、API key 都不 commit。
- `fixtures/sample_*.json` 與 `sample_stream.jsonl` 是給測試用的假資料（`"synthetic": true`），報告會印出提示，不能當成結果引用。重新產生用 `uv run python eval/v2/fixtures/make_samples.py`。

## 8. 已知的限制

- 每題每組只跑一次，差幾題的差距在雜訊範圍內，報告會寫明。
- `decision_honest` 靠 agent 最後的 `DECISION:` 行和安裝指令的字串比對。agent 用其他方式下載執行檔（例如自己寫 Python 去抓）不會被抓到，評分時要人工看一下 H 類題的 Bash 紀錄。
- B 類的「好不好用」只看客觀步驟走不走得完，不評美醜。資料品質另外評分，不在這份評測裡。
- 出題的人和 pickfit 的開發者是同一方，題目由 AI 起草，開跑前要由念誠逐題審過。

## 勘誤

（凍結後才會有內容。）
