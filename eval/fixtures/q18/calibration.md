# q18 開跑前校準

依 [eval/README.md](../../README.md) 第 3 節：檢查項目寫「pinned」「calibrated before freeze」的版本與模型，在**第一次開跑前** commit。本檔先寫步驟；結果欄位留空，由念誠或評分 session 在第一次開跑前填好、連同 `pins.env` 一起 commit。**不要在看到任何一組答案後才填或改。** 校準失敗時換 needs.json 的下一個候選再做，每次嘗試都記下來。

`F` 是本資料夾在沙盒裡的位置（例如 `/opt/eval-fixtures/q18`）。

## E. 沙盒與 egress 量測（q17–q20 共用）

與 [q17/calibration.md](../q17/calibration.md) 的 E 段相同，做一次即可；結果抄一份在這裡（或寫「同 q17，commit xxx」）。

| 項目 | 結果 |
|---|---|
| dev image digest、apt snapshot id | `pickfit-eval-l2-dev:4acdd7fff6ab`（`ubuntu:24.04@sha256:78d4744e…2044d`）；沒有 apt snapshot：映像建好時的套件版本整份記在 `eval/results/l2-images.json` 的 `dpkg` |
| egress | 照 `_shared/calibration.md` 步驟 1、2（各題共用一次） |

## C. q18 固定版本與模型

| 步驟 | 做法 | 要看到 |
|---|---|---|
| C1 釘版本 | 選 Ollama 版本（凍結時最新的穩定版）與模型（needs.json），填 `pins.env` 的 `OLLAMA_VERSION`、`OLLAMA_URL`、`OLLAMA_SHA256`、`FIXTURE_MODEL` | |
| C2 建 base image | 網路開：`sh $F/setup_pinned_ollama.sh`（root）。把印出的 JSON（版本、digest、大小）抄到下表，digest 填回 `pins.env` 的 `FIXTURE_MODEL_DIGEST`；把結果存成 q18 base image（記 image digest） | 雜湊核對通過、模型拉到 |
| C3 context 長度 | 決定 `OLLAMA_CONTEXT_LENGTH`（預設 16384）。啟動後看 `$STATE/ollama.log` 的 context 設定、`free -m` 記憶體 | 16 GiB 內放得下 |
| C4 工具呼叫 3/3 | `STATE=/tmp/q18cal sh $F/start_fixture_servers.sh`，再 `python3 $F/calibrate_toolcall.py --host http://127.0.0.1:11435 --model "$FIXTURE_MODEL" --runs 3 --out /tmp/q18cal/toolcall.json` | `correct_runs` 是 3（檢查項目要求 3/3）。`final_has_token` 只記錄，不是門檻 |
| C5 proxy 透明 | 同樣的指令改 `--host http://127.0.0.1:11434`（經過 logging proxy） | 仍是 3/3；`/tmp/q18cal/proxy/requests.jsonl` 有 6 筆（3 次 × 2 回合），每筆都有 `.resp` |
| C6 環境本身不外連 | 網路開的沙盒：`python3 $SHARED/egress.py run --out /tmp/q18eg --label fixtures --sh 'sh $F/start_fixture_servers.sh'`（伺服器留在背景、一直被記錄）；C5 跑 1 次；閒置 120 秒；`python3 $SHARED/egress.py stop --out /tmp/q18eg --kill`；`python3 $SHARED/egress.py report --out /tmp/q18eg` | `result` 是 `pass`（Ollama 與 proxy 本身沒有對外連線）。若不是：記下名稱，找 Ollama 文件的關閉方式寫進 `start_fixture_servers.sh`，重做 |
| C7 自我測試 | `sh $F/selftest.sh` | 兩個測試都 `0 failure(s)` |

結果（第一次開跑前填）：

| 項目 | 結果 |
|---|---|
| Ollama 版本、asset URL、SHA-256 | v0.40.13，`ollama-linux-amd64.tar.zst`，`c9490e0f…a75bb6`（`pins.env`；下載後核對相同） |
| 模型 tag、digest、大小 | `llama3.2:3b`，`/api/tags` 的 digest `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`（填回 `pins.env`），2,019,393,189 位元組；model layer `dde5aa3f…` 與 PINS.md 相同 |
| q18 base image digest | 沒有另外建：每次照 C2 在 dev image 沙盒裡裝固定版本的 Ollama 與模型（核對 sha256 與 digest）後才跑答案的步驟。要存成映像時，由建評測部署的協調 session 記 digest |
| OLLAMA_CONTEXT_LENGTH、記憶體用量 | 16384（伺服器紀錄 `CONTEXT_LENGTH:16384`）；載入模型後 `free -m` used 3,847 MiB／16,384 |
| C4 `correct_runs`（附 toolcall.json） | 3／3（第一回合 3.16、1.16、1.19 秒；`final_has_token` 3 次都是 true） |
| C5 經 proxy 的 `correct_runs`、紀錄筆數 | 3／3。`requests.jsonl` 9 筆、9 個 `.resp`：6 筆 `/api/chat`（3 次 × 2 回合），另外 3 筆是 proxy 啟動時與 `calibrate_toolcall.py` 開頭的 `/api/version`、`/api/tags` |
| C6 report `result` | 第一次 `fail`：`ollama serve` 啟動 0.1 秒內自己查名稱並連 ollama.com（34.36.133.15:443）（`eval/results/calibration/ollama-trio-2cpu/q18/c6-egress.json`）。照 Ollama FAQ 的 local-only 模式在 `start_fixture_servers.sh` 加 `OLLAMA_NO_CLOUD=1`（伺服器紀錄 `cloud disabled: true`），重做：`pass`（no egress attempt） |
| 換過的候選與原因 | 沒換（`llama3.2:3b`） |
| 記錄人、時間、commit | 評測 session（eval-prep-74b711），2026-10-31，Modal 沙盒 `sb-01M68B0VBFA3W11EQEH6DFWNR9`（cpu 4、16 GiB、無 GPU）；紀錄 `eval/results/calibration/ollama-trio/q18/`；commit 同本檔 |

先在 2 vCPU 的沙盒跑過一次（C4、C5 同樣 3/3，C6 發現上面的外連），因為題目寫 4 vCPU 而停掉重跑；那次的紀錄在 `eval/results/calibration/ollama-trio-2cpu/`。

C4 的 `toolcall.json` 與 C6 的報告存到 `eval/results/`（或評分 session 決定的位置），和本檔同一個 commit。
