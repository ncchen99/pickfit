# q19 開跑前校準

依 [eval/README.md](../../README.md) 第 3 節：檢查項目寫「pinned」「calibrated before freeze」的伺服器與模型，在**第一次開跑前** commit。本檔先寫步驟；結果欄位留空，由念誠或評分 session 在第一次開跑前填好、連同 `pins.env` 一起 commit。**不要在看到任何一組答案後才填或改。** 校準失敗時換 needs.json 的下一個候選再做，每次嘗試都記下來。

`F` 是本資料夾在沙盒裡的位置（例如 `/opt/eval-fixtures/q19`）。

## E. 沙盒與 egress 量測（q17–q20 共用）

與 [q17/calibration.md](../q17/calibration.md) 的 E 段相同，做一次即可；結果抄一份在這裡（或寫「同 q17，commit xxx」）。

| 項目 | 結果 |
|---|---|
| dev image digest、apt snapshot id | |
| egress | 照 `_shared/calibration.md` 步驟 1、2（各題共用一次） |

## C. q19 固定伺服器與模型

建議與 q18 用同一個 Ollama 版本、同一個模型（needs.json）；那樣 C1、C2 直接沿用 q18 的結果。

| 步驟 | 做法 | 要看到 |
|---|---|---|
| C1 釘版本 | 填 `pins.env` 的 `OLLAMA_VERSION`、`OLLAMA_URL`、`OLLAMA_SHA256`、`FIXTURE_MODEL` | |
| C2 建 base image | 網路開：`sh $F/setup_pinned_ollama.sh`（root）；印出的 digest 填回 `FIXTURE_MODEL_DIGEST`；存成 q19 base image（記 digest） | 雜湊核對通過、模型拉到 |
| C3 context 長度 | 決定 `OLLAMA_CONTEXT_LENGTH`（預設 32768，coding agent 的系統提示很長）。啟動後看 `$STATE/ollama.log`、`free -m` | 16 GiB 內放得下 |
| C4 參考 harness 3/3 | `STATE=/tmp/q19cal sh $F/start_fixture_servers.sh`，再 `python3 $F/reference_harness.py --base-url http://127.0.0.1:8000/v1 --model "$FIXTURE_MODEL" --runs 3 --probe-prefill 16000 --out /tmp/q19cal/harness.json` | `passed_runs` 是 3（檢查項目要求 3/3），每次 ≤ 900 秒 |
| C5 長提示的速度（只記錄） | 看 `harness.json` 的 `prefill_probe.seconds`（約 16,000 token 的提示處理時間） | 若超過 600 秒，真的 coding agent 可能來不及在 15 分鐘內完成：在凍結前決定是否換較小的模型（寫下決定與理由） |
| C6 伺服器紀錄 | `/tmp/q19cal/proxy/requests.jsonl` | 每次 harness 的請求都有記錄（路徑 `/v1/chat/completions`、模型名、`n_tools` 為 3） |
| C7 環境本身不外連 | 網路開的沙盒：`python3 $SHARED/egress.py run --out /tmp/q19eg --label fixtures --sh 'sh $F/start_fixture_servers.sh'`（伺服器留在背景、一直被記錄）；C4 跑 1 次；閒置 120 秒；`python3 $SHARED/egress.py stop --out /tmp/q19eg --kill`；`python3 $SHARED/egress.py report --out /tmp/q19eg` | `result` 是 `pass` |
| C8 工作資料夾 | 依 needs.json 的 git 決定，`python3 $F/new_run.py --runs-dir /tmp/q19runs --label c --workdir /tmp/q19wd` | `run.json` 的 `git` 與 `head`；記下 head（每次執行都從同一個 commit 開始） |
| C9 自我測試 | `sh $F/selftest.sh` | 兩個測試都 `0 failure(s)` |

結果（第一次開跑前填）：

| 項目 | 結果 |
|---|---|
| 伺服器與版本、asset URL、SHA-256 | |
| 模型 tag、digest、大小 | |
| q19 base image digest | |
| OLLAMA_CONTEXT_LENGTH、記憶體用量 | |
| C4 `passed_runs`、每次秒數（附 harness.json） | |
| C5 prefill 秒數與決定 | |
| C7 report `result` | |
| C8 git／head | |
| 換過的候選與原因 | |
| 記錄人、時間、commit | |

C4 的 `harness.json` 與 C7 的報告存到 `eval/results/`（或評分 session 決定的位置），和本檔同一個 commit。
