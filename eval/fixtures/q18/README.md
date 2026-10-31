# q18 測試資料：終端機用戶端把本機模型接上 stdio MCP 伺服器

這個資料夾是 [eval/README.md](../../README.md) 第 8 節要求的 q18 測試資料，只給評分者用，**不給受測 agent 看**。題目原文在 [questions.yaml](../../questions.yaml) 的 `q18`。

全部自己寫的：沒有第三方檔案、沒有 commit 任何金鑰或 token、不含任何工具名稱或預期答案；任何答案推薦的用戶端都用同一套資料與步驟檢查。腳本只用 Python 標準函式庫（3.9 以上）或 POSIX shell。要外部取得的東西（固定版本的 Ollama、工具呼叫用的模型、dev image 內容）列在 `needs.json`，**沒有下載**。

## 0. 檔案

| 檔案 | 用途 |
|---|---|
| `request.txt` | 凍結的請求原文：`Use the get_project_code tool to look up project alpha and tell me its code.` |
| `mcp_server/project_code_server.py` | 凍結的 stdio MCP 測試伺服器：一個工具 `get_project_code(name)`；`alpha` 回傳本次的 token，其他名稱回錯誤；每個訊息、每次 tools/call 寫進 `server.log` |
| `new_run.py` | 每次執行前產生**新的隨機 token**（寫進 `state/token.txt`）與該次的資料夾、開始時間 |
| `check_run.py` | 依 3 次執行的紀錄判 L2-2、L2-3 |
| `calibrate_toolcall.py` | 開跑前校準：模型透過 Ollama 自己的 API 做工具呼叫是否 3/3 |
| `pins.env` | 固定版本（凍結時填） |
| `setup_pinned_ollama.sh` | 建 base image 時安裝固定版本的 Ollama、拉模型（**要網路**，只在建 image 時用） |
| `start_fixture_servers.sh`、`stop_fixture_servers.sh` | 啟動／停止固定版本的 Ollama（127.0.0.1:11435）與 logging proxy（127.0.0.1:11434，Ollama 的預設位址） |
| `tools/logging_proxy.py` | 透明的 HTTP 記錄 proxy：原樣轉送，記下每個請求與模型的回應 |
| `tools/run_steps.py` | 把答案的安裝指令原字不改、依序打進同一個終端機 session |
| `tools/pty_drive.py` | 在虛擬終端機裡跑用戶端：送出請求、自動同意工具提示、記錄輸出與時間 |
| `tools/gen_dummy_key.py` | 執行時產生假的金鑰值（只在答案說「填什麼都可以」時用） |
| `../_shared/egress.py` | egress check（各題共用，[`_shared/README.md`](../_shared/README.md) 第 1 節；第 1 節寫本題怎麼用） |
| `selftest.sh`、`tests/` | 離線自我測試（用假的模型伺服器，不呼叫真模型） |
| `needs.json`、`calibration.md` | 待決定的外部資料；開跑前校準步驟與結果欄位 |

### 測試環境長什麼樣

使用者「已經在用 Ollama」，所以 Ollama 與模型是**環境的一部分**，不是答案要裝的：

```
用戶端（答案推薦的）──HTTP──> 127.0.0.1:11434  logging proxy ──> 127.0.0.1:11435  固定版本的 Ollama ＋ 凍結的模型
        │
        └─stdio─> python3 $F/mcp_server/project_code_server.py --state-dir $W/state
```

proxy 佔用 Ollama 的預設位址，原樣轉送所有請求（含串流），所以用戶端照 Ollama 預設設定就會連到模型；proxy 記下的**模型回應**讓評分者分辨「模型自己說出了 token」和「用戶端只是把工具輸出印出來」。

## 1. 共用做法

### 環境

- dev image：needs.json（念誠決定）。下文假設 Ubuntu 24.04、使用者 `dev`（可免密碼 sudo）、`F=/opt/eval-fixtures/q18`、`W=/eval-work/q18/<組別>`。
- q18 base image ＝ dev image ＋ `setup_pinned_ollama.sh` 裝好的固定 Ollama 與模型（建一次，記 digest；評測中不再拉模型）。
- Modal Sandbox，4 vCPU、16 GiB、無 GPU（與 q17 相同）。本題的檢查**不封鎖網路**，但全程量測 egress（L2-3）。
- 佔位字（第 5 節允許填）：
  - 模型名稱 → `pins.env` 的 `FIXTURE_MODEL`（檢查項目指定「the frozen tool-calling fixture model」；答案寫的模型名視為「你的模型」的佔位字，見 open question）；
  - Ollama 位址 → 答案寫的值（Ollama 預設 `http://localhost:11434`，或其 OpenAI 相容的 `/v1`）；
  - 「你自己寫的 stdio 伺服器」→ 指令 `python3`、參數 `["/opt/eval-fixtures/q18/mcp_server/project_code_server.py", "--state-dir", "/eval-work/q18/<組別>/state"]`，伺服器名稱填 `projects`；
  - 檔案系統伺服器：題目舉例提到，但檢查項目不用；評分者**不另外設定**它。
- 答案要求「任何值都可以」的金鑰時用答案寫的字面值，只寫「你的金鑰」時用 `gen_dummy_key.py` 當場產生；不提供任何真的雲端金鑰。

### 「逐字」（verbatim，L2-1）

- 把答案的安裝指令**原字不改**、依答案的順序抄進 `$W/steps-install.txt`，只填版本號與佔位字。
- 在全新的 q18 base image 沙盒裡，以使用者 `dev` 執行 `python3 $F/tools/run_steps.py --steps $W/steps-install.txt --out $W/install --step-timeout 600 --total-timeout 1200 [--accept '<安裝程式問題的 regex>']`：同一個 `bash --login -i` session，一條結束才打下一條；安裝程式的問題送 Enter（接受預設值）。答案說要重開終端機時，步驟檔寫一行 `#NEW_SHELL`。
- 每條指令 exit 0，而且裝完後答案的第一個執行指令找得到（例如答案給的 `--version` 或啟動指令）。
- **任何修改都讓 L2-1 不過**：加 `sudo`、改旗標、補漏掉的前置套件、把裸 `pip install` 改進 venv。改進 venv 能裝起來時記 `needed_venv`，後面的項目照常做；其他修改不允許，照第 9.1 節 C7，其餘 [L2] 都記不過。

### egress check（L2-3）

「egress」指**任何連往本機以外的嘗試**：查詢 localhost 以外名稱的 DNS，或對 loopback（127.0.0.0/8、::1）、0.0.0.0、本沙盒自己介面位址以外的 IPv4／IPv6 位址呼叫 connect／sendto／sendmsg（失敗的嘗試、UDP、多播都算；更新檢查、遙測、下載都算）。

定義、做法與判定見 [`_shared/README.md`](../_shared/README.md) 第 1 節（共用工具在沙盒裡的 `$SHARED`）。本題網路不封鎖，但全程記錄：答案的設定步驟（label `config`）與每次執行（label `r1`、`r2`、`r3`，和執行資料夾同名）都用 `egress.py run` 包起來，留在背景的程序到 `egress.py stop` 為止都被記錄。

**「egress check 通過」**＝ 每次執行的判定是 `pass`：該次執行自己的紀錄全部算，其他步驟（設定步驟留下的背景程序、前幾次的殘留）只算落在該次時段內的嘗試（`check_run.py` 用共用的 `window_verdict`）。`fail` 列出位址與原始紀錄行；`undetermined` 表示量測沒做好，不能判過、也不算答案的錯，修好後重做。固定的 Ollama 與 proxy 本身不外連，已在 calibration.md C6 確認。

## 2. 各 [L2] 項目

### L2-1 安裝步驟逐字成功

> [L2] The install steps succeed verbatim in the dev image

用到：`tools/run_steps.py`；q18 base image。做法與通過條件見第 1 節「逐字」。紀錄：`$W/install.json`（每條指令、exit code、秒數）、`$W/install.txt`（完整輸出）。

### L2-2 用本機模型呼叫 MCP 工具，回覆含 token

> [L2] A pinned Ollama on localhost serves the frozen tool-calling fixture model (calibrated before freeze: 3 of 3 correct tool calls through Ollama's own API). The frozen stdio fixture MCP server exposes get_project_code(name), which returns a unique token. Using the client's documented non-interactive mode, or a pty script that approves every tool prompt, the frozen request 'Use the get_project_code tool to look up project alpha and tell me its code.' produces a reply containing the token, and the fixture server's log shows the tools/call, in at least 2 of 3 runs, each within 10 minutes

用到：`pins.env`、`start_fixture_servers.sh`、`mcp_server/project_code_server.py`、`request.txt`、`new_run.py`、`tools/pty_drive.py`、`tools/logging_proxy.py`、`check_run.py`；模型與 Ollama 的校準結果在 calibration.md C4。

做法（L2-1 的同一個沙盒）：

```sh
STATE=$W/state sh $F/start_fixture_servers.sh          # 使用者原本的 Ollama（11435）＋ proxy（11434）
python3 $SHARED/egress.py run --out $W/egress --label config --inherit-output -- \
  python3 $F/tools/run_steps.py --steps $W/steps-config.txt --out $W/config   # 答案的設定步驟（MCP 伺服器、模型、遙測關閉），佔位字照第 1 節
for r in r1 r2 r3; do
  RUN=$(python3 $F/new_run.py --runs-dir $W/runs --label $r --state-dir $W/state)
  TOKEN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"])' $RUN/run.json)
  # (a) 答案有文件記載的非互動模式：請求原文當參數或 stdin
  python3 $F/tools/pty_drive.py --out $RUN/client --timeout 600 -- \
    python3 $SHARED/egress.py run --out $W/egress --label $r --inherit-output -- <用戶端非互動指令，請求填 request.txt 原文>
  # (b) 只有互動模式：送出請求、同意每一個工具提示、看到 token 後閒置 60 秒再結束
  # python3 $F/tools/pty_drive.py --out $RUN/client --timeout 600 --send-file $F/request.txt \
  #   --send-after '<提示字元 regex>' --approve '<工具同意提示 regex>' --approve-keys '<同意鍵>' \
  #   --done "$TOKEN" --idle 60 --exit-keys '<結束鍵>' -- python3 $SHARED/egress.py run --out $W/egress --label $r --inherit-output -- <用戶端指令>
done
python3 $SHARED/egress.py stop --out $W/egress --kill
python3 $F/check_run.py --state-dir $W/state --egress-dir $W/egress $W/runs/r1 $W/runs/r2 $W/runs/r3
```

- 每次執行用**新的 token**（`new_run.py`），而且是新的用戶端程序；答案的設定與對話紀錄檔照用戶端自己的行為保留。
- 「approves every tool prompt」：`--approve` 的 regex 與同意鍵依用戶端的提示寫（例如 `(?i)allow|approve|run tool`、`y\r`），只用來同意，不輸入其他內容。用戶端有文件記載的自動同意旗標時，可改用旗標（照答案或用戶端文件，記下來）。
- 每次執行的判定（`check_run.py`，時段＝該次開始到用戶端結束後 5 秒，不超過下一次開始）：
  - `tools_call`：`server.log` 有一筆 `get_project_code`、專案名是 alpha（大小寫、前後空白、`project ` 前綴不計）的 tools/call；
  - `model_reply`：proxy 記下的、這次工具呼叫之後的**模型回應**裡，模型生成的文字含本次 token（請求內容不算，所以用戶端把工具輸出原樣印出來不算模型的回覆）；
  - `transcript`：用戶端在終端機的輸出含 token；
  - `in_time`：沒有被 10 分鐘上限中止，而且作答時間 ≤ 600 秒（非互動：整次執行時間；互動：最後一次輸出的時間，不含等待與結束鍵）。

通過（`check_run.py` 的 `L2-2`）：3 次中至少 2 次四項都成立。

### L2-3 egress check

> [L2] Egress check passes, after applying any telemetry-off setting the answer gives

用到：`$SHARED/egress.py`；L2-2 的同 3 次執行。

- 答案給的遙測關閉設定（設定檔、環境變數、旗標）在 L2-2 開始前就套用，寫進 `steps-config.txt`（環境變數則加在用戶端指令前）。答案沒給就不套用。
- 量測時段＝ L2-2 每次執行從 `new_run.py` 到用戶端（或 agent）結束；網路不封鎖。

通過（`check_run.py` 的 `L2-3`）：3 次執行的 egress report 都是 `pass`。任何一次 `fail` 就不過；有 `undetermined` 時記 `undetermined`，修好量測後重做 L2-2 的 3 次。

### L2-4 全程沒有登入或帳號步驟

> [L2] No login or account step at any point

用到：`$W/install.*`、`$W/config.*`、每次的 `client.txt`；`check_run.py` 的 `login_hits`（列出提到 login、sign in、account、authenticate、device code 等字的行，供評分者看）。

通過：安裝、設定、3 次執行的任何一步，都沒有要求建立帳號、登入、裝置碼授權，或向雲端服務取得金鑰／token。`login_hits` 只是提示，最後由評分者讀紀錄判定（例如說明文字裡提到「不需要登入」不算）。

## 3. 自我測試

```sh
sh selftest.sh        # 離線；不需要 root；約 1 分鐘
```

測試內容：MCP 伺服器的 initialize（回應用戶端要求的協定版本）、tools/list、tools/call（alpha、大小寫、未知專案、未知工具）、批次、Content-Length 分框、解析錯誤；`calibrate_toolcall.py` 對假的 Ollama 3/3；用假的用戶端與假的模型伺服器跑完整流程，確認「模型說出 token」才算過、「只有用戶端印出工具輸出」不算；egress、proxy、pty 工具。寫 fixture 時已在 macOS 用 Python 3.9 與 3.12 跑過，全部通過。

## 4. 還沒決定的事

見 `needs.json`（Ollama 版本、模型、dev image、strace）與 `calibration.md`（釘版本、3/3 校準、環境本身不外連）。另外要念誠確認：答案指定的模型名一律換成凍結的 fixture 模型（檢查項目指定，但第 5 節寫「不可換掉答案指定的模型」）；L2-2 互動模式下的同意 regex 由評分者依用戶端提示決定。
