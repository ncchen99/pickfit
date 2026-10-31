# q19 測試資料：只連自架 OpenAI 相容伺服器的終端機 coding agent

這個資料夾是 [eval/README.md](../../README.md) 第 8 節要求的 q19 測試資料，只給評分者用，**不給受測 agent 看**。題目原文在 [questions.yaml](../../questions.yaml) 的 `q19`。

全部自己寫的：沒有第三方檔案、沒有 commit 任何金鑰、不含任何工具名稱或預期答案；任何答案推薦的 agent 都用同一套資料與步驟檢查。腳本只用 Python 標準函式庫（3.9 以上）或 POSIX shell。要外部取得的東西（固定版本的伺服器、模型、dev image 內容、git）列在 `needs.json`，**沒有下載**。

## 0. 檔案

| 檔案 | 用途 |
|---|---|
| `task.txt` | 凍結的請求原文：`Create a file named hello.py in the current directory that prints exactly this line: Hello from the self-hosted model 4721` |
| `expected_output.txt` | 凍結的字串：`Hello from the self-hosted model 4721` |
| `workdir_seed/` | 使用者的 repo（3 個小檔）；每次執行複製一份新的 |
| `new_run.py` | 每次執行前建新的工作資料夾（有 git 時做成固定 commit 的 git repo）與該次的資料夾、開始時間 |
| `check_hello.py` | `hello.py` 存在、`python3 hello.py` 印出的正好是凍結字串 |
| `check_run.py` | 依 3 次執行的紀錄判 L2-2、L2-3 |
| `reference_harness.py` | 開跑前校準：直接呼叫伺服器工具 API 的參考 agent，同一個任務要 3/3 |
| `pins.env` | 固定版本（凍結時填） |
| `setup_pinned_ollama.sh` | 建 base image 時安裝固定版本的伺服器、拉模型（**要網路**，只在建 image 時用） |
| `start_fixture_servers.sh`、`stop_fixture_servers.sh` | 啟動／停止「自架伺服器」：固定版本的 Ollama（127.0.0.1:11435）與前面的 logging proxy（127.0.0.1:8000） |
| `tools/logging_proxy.py` | 透明的 HTTP 記錄 proxy，就是檢查項目說的「the local server's log」 |
| `tools/run_steps.py`、`tools/pty_drive.py`、`tools/gen_dummy_key.py` | 逐字執行安裝指令；在虛擬終端機跑 agent 並同意提示；執行時產生假的金鑰值 |
| `../_shared/egress.py` | egress check（各題共用，[`_shared/README.md`](../_shared/README.md) 第 1 節；第 1 節寫本題怎麼用） |
| `selftest.sh`、`tests/` | 離線自我測試（用假的模型伺服器） |
| `needs.json`、`calibration.md` | 待決定的外部資料；開跑前校準步驟與結果欄位 |

### 測試環境長什麼樣

公司的「自架模型伺服器」由評分者提供，是環境的一部分：

```
agent（答案推薦的）──HTTP──> http://127.0.0.1:8000/v1  logging proxy ──> 127.0.0.1:11435  固定版本的伺服器 ＋ 凍結的模型
   │ 工作資料夾：每次一份新的 workdir_seed/ 複本
```

答案裡自架伺服器的 base URL 是佔位字，評分者填 `http://127.0.0.1:8000/v1`。Ollama 的預設位址 11434 上**沒有東西**，所以 agent 若繞過設定的 URL，請求會直接失敗。

## 1. 共用做法

### 環境

- dev image：needs.json（念誠決定）。下文假設 Ubuntu 24.04、使用者 `dev`（可免密碼 sudo）、`F=/opt/eval-fixtures/q19`、`W=/eval-work/q19/<組別>`。
- q19 base image ＝ dev image ＋ `setup_pinned_ollama.sh` 裝好的伺服器與模型（建一次，記 digest）。
- Modal Sandbox，4 vCPU、16 GiB、無 GPU。本題的檢查**不封鎖網路**，但全程量測 egress（L2-3）。
- 佔位字（第 5 節允許填）：base URL → `http://127.0.0.1:8000/v1`；模型名 → `pins.env` 的 `FIXTURE_MODEL`（檢查項目指定「the frozen tool-calling fixture model」，見 open question）；專案路徑 → 該次的工作資料夾。
- 金鑰：自架伺服器不驗證。agent 一定要填金鑰時，用答案寫的字面值；答案只寫「任何值」或「你的金鑰」時，用 `python3 $F/tools/gen_dummy_key.py` 當場產生（不 commit）。不提供任何真的雲端金鑰。

### 「逐字」（verbatim，L2-1）

- 把答案的安裝指令**原字不改**、依答案的順序抄進 `$W/steps-install.txt`，只填版本號與佔位字。
- 在全新的 q19 base image 沙盒裡，以使用者 `dev` 執行 `python3 $F/tools/run_steps.py --steps $W/steps-install.txt --out $W/install --step-timeout 600 --total-timeout 1200 [--accept '<安裝程式問題的 regex>']`：同一個 `bash --login -i` session、一條結束才打下一條、安裝程式的問題送 Enter（接受預設值）、要重開終端機時寫 `#NEW_SHELL`。
- 每條指令 exit 0，而且裝完後答案的第一個執行指令找得到。
- **任何修改都讓 L2-1 不過**（加 `sudo`、改旗標、補前置套件、裸 `pip install` 改 venv）。改 venv 能裝起來時記 `needed_venv`，後面照常做；其他修改不允許，照第 9.1 節 C7，其餘 [L2] 都記不過。

### egress check（L2-3）

「egress」指**任何連往本機以外的嘗試**：查詢 localhost 以外名稱的 DNS，或對 loopback（127.0.0.0/8、::1）、0.0.0.0、本沙盒自己介面位址以外的 IPv4／IPv6 位址呼叫 connect／sendto／sendmsg（失敗的嘗試、UDP、多播都算；遙測、更新檢查、下載都算）。

定義、做法與判定見 [`_shared/README.md`](../_shared/README.md) 第 1 節（共用工具在沙盒裡的 `$SHARED`）。本題網路不封鎖，但全程記錄：答案的設定步驟（label `config`）與每次執行（label `r1`、`r2`、`r3`，和執行資料夾同名）都用 `egress.py run` 包起來，留在背景的程序到 `egress.py stop` 為止都被記錄。

**「egress check 通過」**＝ 每次執行的判定是 `pass`：該次執行自己的紀錄全部算，其他步驟（設定步驟留下的背景程序、前幾次的殘留）只算落在該次時段內的嘗試（`check_run.py` 用共用的 `window_verdict`）。`fail` 列出位址與原始紀錄行；`undetermined` 表示量測沒做好，不能判過、也不算答案的錯，修好後重做。固定的伺服器與 proxy 本身不外連固定的伺服器與 proxy 本身不外連，已在 calibration.md C7 確認。

## 2. 各 [L2] 項目

### L2-1 安裝步驟逐字成功

> [L2] The install steps succeed verbatim in the dev image

用到：`tools/run_steps.py`；q19 base image。做法與通過條件見第 1 節「逐字」。紀錄：`$W/install.json`、`$W/install.txt`。

### L2-2 agent 用自架伺服器建出 hello.py

> [L2] A pinned local OpenAI-compatible server serves the frozen tool-calling fixture model (calibrated before freeze: a reference harness calling its tool API directly completes the same task 3 of 3 times). Configured as the answer describes and run in its documented non-interactive or auto-approve mode, or through a pty script that approves every prompt, the agent is asked to create hello.py printing a frozen string; the file exists and `python3 hello.py` prints it, in at least 2 of 3 runs, each within 15 minutes

用到：`pins.env`、`start_fixture_servers.sh`、`task.txt`、`expected_output.txt`、`workdir_seed/`、`new_run.py`、`check_hello.py`、`tools/pty_drive.py`、`check_run.py`；校準結果在 calibration.md C4。

做法（L2-1 的同一個沙盒）：

```sh
STATE=$W/state sh $F/start_fixture_servers.sh               # 自架伺服器：http://127.0.0.1:8000/v1
python3 $SHARED/egress.py run --out $W/egress --label config --inherit-output -- \
  python3 $F/tools/run_steps.py --steps $W/steps-config.txt --out $W/config   # 答案的設定（base URL、模型、金鑰、遙測關閉），佔位字照第 1 節
for r in r1 r2 r3; do
  RUN=$(python3 $F/new_run.py --runs-dir $W/runs --label $r --workdir /home/dev/inventory-$r)
  cd /home/dev/inventory-$r
  # (a) 答案的非互動或自動同意模式：請求填 task.txt 原文
  python3 $F/tools/pty_drive.py --out $RUN/agent --timeout 900 -- \
    python3 $SHARED/egress.py run --out $W/egress --label $r --inherit-output -- <agent 非互動指令>
  # (b) 只有互動模式：送出請求、同意每個提示、hello.py 出現後閒置 30 秒再結束
  # python3 $F/tools/pty_drive.py --out $RUN/agent --timeout 900 --send-file $F/task.txt \
  #   --send-after '<提示字元 regex>' --approve '<同意提示 regex>' --approve-keys '<同意鍵>' \
  #   --done-file /home/dev/inventory-$r/hello.py --idle 30 --exit-keys '<結束鍵>' -- \
  #   python3 $SHARED/egress.py run --out $W/egress --label $r --inherit-output -- <agent 指令>
done
python3 $SHARED/egress.py stop --out $W/egress --kill
python3 $F/check_run.py --state-dir $W/state --egress-dir $W/egress $W/runs/r1 $W/runs/r2 $W/runs/r3
```

- 每次執行是新的 agent 程序、新的工作資料夾（`new_run.py`，有 git 時每次都從同一個 commit 開始）；agent 自己的設定檔照它的行為保留。
- 「approves every prompt」：`--approve` 的 regex 與同意鍵依 agent 的提示寫，只同意，不輸入其他內容；agent 有文件記載的自動同意旗標時可改用旗標（記下來）。
- 「prints it」：`python3 hello.py` 在工作資料夾裡執行（30 秒上限），exit 0，stdout 正好是 `expected_output.txt` 那一行，後面最多一個換行；多印任何字都不算。
- 「within 15 minutes」：沒被 900 秒上限中止，而且作答時間 ≤ 900 秒（非互動：整次執行時間；互動：最後一次輸出的時間）。

通過（`check_run.py` 的 `L2-2`）：3 次中至少 2 次 `hello` 與 `in_time` 都成立。

### L2-3 伺服器紀錄看得到請求，egress check 通過

> [L2] The local server's log shows the agent's requests, and the egress check passes after applying the answer's telemetry settings

用到：`tools/logging_proxy.py` 的 `$W/state/proxy/requests.jsonl`；`$SHARED/egress.py`；L2-2 的同 3 次執行。

- 「the local server's log」＝ logging proxy 的紀錄（它就是自架伺服器的入口；每筆有時間、方法、路徑、模型名、工具數，只記標頭名稱不記值）。
- 答案給的遙測設定在 L2-2 之前套用（寫進 `steps-config.txt`，或加在 agent 指令前的環境變數）；沒給就不套用。
- 量測時段＝ L2-2 每次執行從 `new_run.py` 到用戶端（或 agent）結束；網路不封鎖。

通過（`check_run.py` 的 `L2-3`）：L2-2 通過的每一次執行，紀錄裡都有該次時段內的請求（`server_requests` ≥ 1），**而且** 3 次執行的 egress report 都是 `pass`。有 `undetermined` 時記 `undetermite`，修好量測後重做。

### L2-4 全程沒有登入提示

> [L2] No login prompt at any point

用到：`$W/install.*`、`$W/config.*`、每次的 `agent.txt`；`check_run.py` 的 `login_hits`（提到 login、sign in、account、authenticate、device code、subscription 等字的行）。

通過：安裝、設定、3 次執行都沒有出現要求登入、建立帳號、裝置碼授權或訂閱的提示。`login_hits` 只是提示，最後由評分者讀紀錄判定。

## 3. 自我測試

```sh
sh selftest.sh        # 離線；不需要 root；約 1 分鐘
```

測試內容：參考 harness 對假的伺服器 3/3（含 prefill 量測）；用假的 agent 經過 proxy 跑 3 次（對、錯、對），`check_run.py` 判 2/3 通過、錯的字串不過、每次的請求都記到；工作資料夾每次從同一個 commit 開始；egress、proxy、pty、run_steps 工具。寫 fixture 時已在 macOS 用 Python 3.9 與 3.12 跑過，全部通過。

## 4. 還沒決定的事

見 `needs.json`（伺服器與模型、git、dev image、strace）與 `calibration.md`（3/3 校準、長提示的速度、環境本身不外連）。另外要念誠確認：答案指定的模型名一律換成凍結的 fixture 模型（同 q18）；CPU 上真的 coding agent 是否來得及在 15 分鐘內完成，要看 C5 的量測，若太慢要在凍結前換模型。
