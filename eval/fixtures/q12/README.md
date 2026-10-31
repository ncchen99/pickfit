# q12 測試資料：Mac 上的 MLX 本機 OpenAI 相容伺服器

題目與檢查項目見 [../../questions.yaml](../../questions.yaml) 的 q12；評分規則見 [../../README.md](../../README.md) 第 5 節。q12 只能在 Mac 實跑（`sandbox: mac_only`），由念誠親手在另開的 macOS 帳號執行。帳號準備、斷網、移除清單與共用腳本在 [../q11/mac/RUNBOOK.md](../q11/mac/RUNBOOK.md)（和 q11 共用，本題不需要記憶體量測）。

全部是自己寫的腳本，不含任何工具名稱或預期答案。凍結的測試模型在開跑前選定並固定（`needs.json`、`calibration.md`），本資料夾只放固定用的工具。

## 檔案

| 檔案 | 用途 |
|---|---|
| `pin_model.py` | 開跑前固定測試模型：把 repo id 解析成 commit、下載每個檔、記下大小與 SHA-256，寫出下面三個檔 |
| `model_pin.json`、`model_pin.env`、`model_files.sha256` | 固定的結果（**開跑前由 `pin_model.py` 產生後 commit**，現在還沒有） |
| `fetch_model.sh` | 答案從本機資料夾載入模型時，用固定的 commit 下載一份並驗證雜湊 |
| `check_model_files.py` | L2-2：伺服器啟動後，新出現的權重檔都要和固定的檔完全相同（沒有轉檔），快取的是固定的 revision |
| `client_check.py` | L2-3、L2-4（L2-5 再跑一次）：用固定版本的官方 openai Python client 打非串流與串流請求 |
| `stub_server.py` | 只給自我測試用的假伺服器（不載入模型，不用來評任何答案） |
| `selftest.py` | 自我測試 |
| `calibration.md` | 開跑前要做的固定與確認（待填） |
| `needs.json` | 要從外部取得、要念誠決定的東西 |

## 共同準備

1. 開跑前（主帳號）：照 `calibration.md` 固定測試模型、建好評分用的 venv `/Users/Shared/eval-grader/venv`（裝固定版本的 `openai`）。這個 venv 不在測試帳號的 PATH 裡，不影響答案的環境。
2. 每次實跑照 [RUNBOOK](../q11/mac/RUNBOOK.md) 第 2～3 步：新的測試帳號、before 快照、`preflight.sh` 要 PASS。以下 `F=/Users/Shared/eval-fixtures`、`R=/Users/Shared/eval-runs/<題號-組別>`、`G=/Users/Shared/eval-grader/venv/bin/python`。
3. 第一個安裝指令之前：`touch $R/marker`。
4. 伺服器另開一個終端機分頁，也用 `script -q $R/server-transcript.txt` 紀錄；步驟用 `script -q $R/steps-transcript.txt` 紀錄。

## 逐項說明

### L2-1

> [L2] In a fresh macOS user with empty HF_HOME and no hub token, the install steps run from the terminal without installing any GUI application

- **用到**：`../q11/mac/preflight.sh`、`snapshot_state.sh`、`diff_state.py`。
- **「empty HF_HOME」與「no hub token」**：`preflight.sh` PASS，也就是 `HF_HOME`、`HF_HUB_CACHE`、`HF_TOKEN`、`HUGGING_FACE_HUB_TOKEN` 等都沒設，`~/.cache` 不存在（所以預設的 Hugging Face 快取與 token 檔都不存在），讀得到的地方沒有模型檔。評分者不另外設定 `HF_HOME`；答案要設就照答案。
- **做法**：答案的安裝指令在終端機逐行照原樣執行（第 5 節允許的調整照做並記錄），每個指令 exit 0。
- **「without installing any GUI application」**：跑完後 `diff_state.py before after` 的 `applications.txt`（`/Applications`、`/Applications/Utilities`、各家目錄的 `~/Applications`）與 `brew-casks*.txt` 都沒有新增項目，而且步驟沒有要求打開任何 app 的視窗。命令列程式附帶的輔助 bundle（例如放在套件目錄裡、不在上述位置的 `.app`）不算。
- **過**：preflight PASS、每個安裝指令成功、沒有新增 GUI app。
- **不過**：任一不成立。

### L2-2

> [L2] The server starts with the frozen fixture model (an MLX-format 4-bit instruct model of at most 3B parameters, repo id and revision pinned at freeze), referenced by repo id or local path, with no conversion step

- **用到**：`model_pin.env`／`model_pin.json`／`model_files.sha256`、`fetch_model.sh`、`check_model_files.py`。
- **做法**：
  1. 用答案啟動伺服器的指令，把模型的佔位字換成固定的 repo id（`model_pin.env` 的 `REPO_ID`）。答案的範例用的是本機資料夾時，改填 `/Users/Shared/eval-models/<名稱>`（主帳號事先用 `fetch_model.sh` 下載並驗證過）。這是第 5 節的「填入佔位字」，其他參數照答案。
     - `/Users/Shared/eval-models` 平常只有主帳號讀得到（`chmod 700`），所以 preflight 與 q11 的測試帳號都看不到它。只有在這一步、答案要用本機資料夾時，才 `sudo chmod -R a+rX /Users/Shared/eval-models`，跑完再改回 `700`。
  2. 伺服器印出就緒訊息、`lsof -nP -iTCP -sTCP:LISTEN -a -u $USER` 看得到它在本機的 port 上監聽。記下 port 與綁定的位址。
  3. `python3 $F/q12/check_model_files.py --marker $R/marker`（本機資料夾時加 `--local-path /Users/Shared/eval-models/<名稱>`）。
- **「no conversion step」**：答案的步驟裡沒有對測試模型做轉檔、量化或匯出；而且 `check_model_files.py` 印出 PASS：測試期間新出現的權重檔（含 Hugging Face 快取的 symlink 指到的檔）都和固定的檔大小、SHA-256 完全相同，快取裡的是固定的 revision。
- **固定的 revision 被更新時**：用 repo id 下載到的 revision 和固定的不同，就改用本機資料夾的方式重跑（若答案的工具文件支援本機資料夾），並記錄；兩種都不行時記為測試資料問題，依第 3 節處理（兩組一起）。`calibration.md` 要在每個實跑日先確認 repo 的最新 revision 仍是固定的那個。
- **過**：伺服器起得來、L2-3 的請求成功（代表模型載入了）、`check_model_files.py` PASS。
- **不過**：起不來、需要轉檔、載入的不是固定的模型。

### L2-3

> [L2] With the pinned official openai Python client and base_url set to the server, a non-streaming chat completion returns non-empty choices[0].message.content

- **用到**：`client_check.py`、評分 venv（固定版本的 `openai`）。
- **做法**：
  ```sh
  $G $F/q12/client_check.py --base-url http://127.0.0.1:<port>/v1 --model <答案說要送的模型名稱> --out $R/client-online.json
  ```
  `base_url` 用答案或工具文件寫的 OpenAI 相容位址（一般是 `http://127.0.0.1:<port>/v1`）；`model` 填答案或文件說要送的名稱（常是 repo id 或路徑），屬於填佔位字。請求只帶 `model`、`messages`（一句固定的英文）、`max_tokens: 64`，不重試。API key：答案有指定就用（`--api-key`），否則執行時產生一個隨機的假 key，不印出、不存檔。
- **過**：印出 `L2-3 non-streaming: PASS`（`choices[0].message.content` 去掉空白後不是空字串）。
- **不過**：錯誤、逾時（10 分鐘）、內容是空的。

### L2-4

> [L2] A streaming request yields at least 2 chunks and terminates normally through the SDK's stream iterator

- **用到**：同 L2-3（同一次執行）。
- **過**：印出 `L2-4 streaming: PASS`：`stream=True` 的請求，SDK 的 iterator 至少給出 2 個 chunk（任何 chunk 都算，包括只有 role 或 finish_reason 的），而且 `for` 迴圈正常結束、沒有丟出例外。
- **不過**：少於 2 個 chunk、中途斷線或任何例外、逾時。

### L2-5

> [L2] Offline: with all network interfaces down and using only the answer's commands (an offline environment variable counts only if the answer says to set it), both requests succeed again after a server restart

- **用到**：`../q11/mac/offline.sh`、`client_check.py`。
- **做法**：
  1. 停掉伺服器：在它的分頁按 Ctrl-C，或用答案說的停止指令。確認 port 不再監聽。
  2. `sudo sh $F/q11/mac/offline.sh off $R/net-state.txt`，要印 `offline check: PASS`。
  3. 用**和 L2-2 一模一樣**的指令重新啟動伺服器。只有答案自己寫了要設的離線環境變數才能設；評分者不加任何變數或旗標。
  4. `$G $F/q12/client_check.py --base-url ... --model ... --out $R/client-offline.json`
  5. `sh $F/q11/mac/offline.sh check` 仍要 PASS，然後 `sudo sh $F/q11/mac/offline.sh on $R/net-state.txt`。
- **「all network interfaces down」**：RUNBOOK 第 4 步的判準。
- **過**：斷網時伺服器重新起得來，L2-3 與 L2-4 兩個請求都 PASS。
- **不過**：起不來（例如啟動時一定要連線檢查）、任一請求失敗。

### L2-6

> [L2] No login or account prompt at any step

- **用到**：`steps-transcript.txt`、`server-transcript.txt`、`../q11/mac/scan_transcript.py`。
- **做法**：評分者在整個過程中留意：有沒有步驟停下來要帳號、密碼、token、API key，或打開登入、註冊頁面，或出現 Apple ID／帳號的對話框。跑完再 `python3 $F/q11/mac/scan_transcript.py $R/*transcript.txt`，逐一看列出的行。
- **判準**：有步驟等著輸入帳號類資料、要求登入才能繼續、或因為沒登入而拒絕下載，就不過。只是提到（例如「沒有 token，以匿名方式繼續」）而且自己繼續執行，不算。macOS 的 `sudo` 密碼提示、Homebrew 安裝程式要求的管理者密碼，是本機權限、不是帳號登入，不算。
- **過**：沒有任何帳號或登入提示。

## 開跑前自我測試

```sh
python3 selftest.py                                   # 任何 Python（沒有 openai 時只跑 urllib 版）
/Users/Shared/eval-grader/venv/bin/python selftest.py  # 用評分 venv，SDK 版也要全過
```

## 中立性

- 測試模型只要求檢查項目寫的條件（MLX 格式、4-bit、instruct、≤3B），挑主流架構、授權寬鬆、不需登入的；候選與理由在 `needs.json`，不考慮任何伺服器工具。
- `client_check.py` 只送最少的欄位，任何 OpenAI 相容伺服器都一樣。`stub_server.py` 只用來測評分腳本。
