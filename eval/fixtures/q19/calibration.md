# q19 開跑前校準

依 [eval/README.md](../../README.md) 第 3 節：檢查項目寫「pinned」「calibrated before freeze」的伺服器與模型，在**第一次開跑前** commit。本檔先寫步驟；結果欄位留空，由念誠或評分 session 在第一次開跑前填好、連同 `pins.env` 一起 commit。**不要在看到任何一組答案後才填或改。** 校準失敗時換 needs.json 的下一個候選再做，每次嘗試都記下來。

`F` 是本資料夾在沙盒裡的位置（例如 `/opt/eval-fixtures/q19`）。

## E. 沙盒與 egress 量測（q17–q20 共用）

與 [q17/calibration.md](../q17/calibration.md) 的 E 段相同，做一次即可；結果抄一份在這裡（或寫「同 q17，commit xxx」）。

| 項目 | 結果 |
|---|---|
| dev image digest、apt snapshot id | `pickfit-eval-l2-dev:4acdd7fff6ab`（`ubuntu:24.04@sha256:78d4744e…2044d`）；沒有 apt snapshot：映像建好時的套件版本整份記在 `eval/results/l2-images.json` 的 `dpkg` |
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
| 伺服器與版本、asset URL、SHA-256 | Ollama v0.40.13（同 q18），`ollama-linux-amd64.tar.zst`，`c9490e0f…a75bb6`（下載後核對相同）；local-only 模式（`OLLAMA_NO_CLOUD=1`，紀錄 `cloud disabled: true`） |
| 模型 tag、digest、大小 | **`qwen2.5:7b`**（換過，見下節），`/api/tags` 的 digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`（填回 `pins.env`），4,683,087,332 位元組；model layer 在沙盒裡算的 sha256 `2bada8a7…` 與 PINS.md 公布值相同 |
| q19 base image digest | 沒有另外建：每次照 C2 在 dev image 沙盒裡裝（核對 sha256 與 digest）後才跑答案的步驟。要存成映像時，由建評測部署的協調 session 記 digest |
| OLLAMA_CONTEXT_LENGTH、記憶體用量 | 32768；載入 `qwen2.5:7b` 後 `free -m` used 6,367 MiB，C4、C5 後 6,701 MiB（16,384 內） |
| C4 `passed_runs`、每次秒數（附 harness.json） | 3／3：16.94、8.39、7.89 秒（每次 2 回合：`write_file`，再一句說明；`hello.py` 印出 `Hello from the self-hosted model 4721`） |
| C5 prefill 秒數與決定 | 757.52 秒（17,162 個提示 token，約每秒 22.7 個）。超過 600 秒；比它小的兩個候選都沒過 C4（下節），所以照下節的選法仍用 `qwen2.5:7b`。估計：系統提示約 10,000 token 的 coding agent，第一回合要約 440 秒；之後的回合 Ollama 會沿用已處理的相同開頭，只算新加的部分。真的 agent 可能來不及在 15 分鐘內完成，兩組條件相同，報告照實寫明 |
| C6 伺服器紀錄 | 8 筆：`/v1/models` 1 筆、`/v1/chat/completions` 6 筆（3 次 × 2 回合，模型 `qwen2.5:7b`、`n_tools` 3）、長提示 1 筆 |
| C7 report `result` | `pass`（no egress attempt） |
| C8 git／head | git true，head `c6d8c979379ac0e649d5a9946ce81e11ef00a1ce`（三次校準都相同） |
| C9 自我測試 | 兩個都 `0 failure(s)` |
| 換過的候選與原因 | `llama3.2:3b` → `qwen2.5:7b`：見下節 |
| 記錄人、時間、commit | 評測 session（eval-prep-74b711），2026-10-31；`llama3.2:3b` 在 Modal 沙盒 `sb-01M68B0VBFA3W11EQEH6DFWNR9`（`eval/results/calibration/ollama-trio/q19/`），兩個候選在 `sb-01M68BV7Q7YJSX0V15B8WQ8B4Q`（`eval/results/calibration/q19-candidates/`），都是 cpu 4、16 GiB；commit 同本檔 |

C4 的 `harness.json` 與 C7 的報告存到 `eval/results/`（或評分 session 決定的位置），和本檔同一個 commit。

## 換候選（2026-10-31，看到任何答案之前）

**第 1 個候選 `llama3.2:3b` 沒過 C4**（`eval/results/calibration/ollama-trio/`，4 vCPU、16 GiB）：`passed_runs` 0／3。兩次呼叫了 `write_file`，但把那句話原樣寫進 `hello.py`（不是 `print(...)`，執行時 SyntaxError）；一次把工具呼叫寫成一般文字（`{"name":"write_file","parameters=...}`），沒有真的呼叫。C5 的 16,000 token 長提示 470.89 秒。照本檔開頭（校準失敗時換 needs.json 的下一個候選）與 9.3 C（協調 session 2026-10-31 轉達：沒到 3/3 就在任何一組開跑前換模型並記錄）換候選。

**選法**（跑之前寫下）：needs.json 的順序是 `qwen2.5:7b`、`qwen3:4b`，兩個都在同一個沙盒（4 vCPU、16 GiB）照 C1–C9 原樣各跑一次（`calibrate_candidates.sh`；每個候選用一份只改了 `FIXTURE_MODEL` 的 q19 複本）。取順序上第一個 C4 3/3（每次 ≤ 900 秒）而且 C7 `pass` 的候選；但它的 C5 長提示超過 600 秒、而另一個也 3/3、C7 `pass`、C5 ≤ 600 秒時，照 C5 換成那個較快的（理由：C5 寫的 15 分鐘內完成）。兩個都不過時，不自己再往下換，回報協調 session。q18 不受影響（`llama3.2:3b` 在 q18 C4、C5 都 3/3），所以換了之後 q18、q19 的固定模型會不同，報告寫明。

**結果**（`eval/results/calibration/q19-candidates/`）：

| 候選 | C4 `passed_runs` | 每次秒數 | C5 長提示 | C7 | 結論 |
|---|---|---|---|---|---|
| `llama3.2:3b` | 0／3 | 9.96、7.23、4.89 | 470.89 秒 | `pass` | 不過 |
| `qwen2.5:7b` | 3／3 | 16.94、8.39、7.89 | 757.52 秒 | `pass` | **採用** |
| `qwen3:4b` | 2／3 | 470.19、522.08、第 3 次第一回合超過 900 秒被停掉 | 807.27 秒 | `pass` | 不過 |

照上面的選法：順序上第一個 3/3 而且 C7 `pass` 的是 `qwen2.5:7b`；它的 C5 超過 600 秒，但沒有另一個 3/3 的候選可換，所以採用它。`qwen3:4b` 預設會先「思考」，在 CPU 上每一回合要幾分鐘，長提示也比 `qwen2.5:7b` 慢。`pins.env` 已改成 `qwen2.5:7b` 與它的 digest；兩個候選的 model layer 都在沙盒裡算過 sha256，與 Ollama registry 公布的相同（PINS.md）。
