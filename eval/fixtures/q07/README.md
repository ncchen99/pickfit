# q07 測試資料：放在 git 裡的純文字 API 請求檔，CLI 當測試跑

題目在 [../../questions.yaml](../../questions.yaml) 的 q07。這裡放 q07 各 [L2] 項目用到的測試資料、檢查腳本與評分步驟。評分規則以 [../../README.md](../../README.md) 第 5 節與第 9.1 節為準。

所有檔案都是為這題自己寫的，只用 Python 3.8 以上的標準函式庫（diff 檢查另外需要 git）。請求的定義不屬於任何工具的格式，評分者依答案的格式自己寫出請求檔。

## 1. 檔案

| 檔案 | 用途 |
|---|---|
| `requests.json` | 三個請求的中立定義（方法、網址、標頭、主體、斷言），以及 L2-4 要改的網址 |
| `server.py` | 本機測試伺服器（127.0.0.1 與 ::1 的 18081 埠），三種模式，記錄每個請求 |
| `check_q07.py` | 從三次執行的報告與伺服器紀錄算出 L2-2、L2-3、L2-5 的判定 |
| `diff_check.py` | L2-4：建立 git 基準、改網址、量 diff |
| `egress_run.py` | 記錄連線、計時、逾時的執行包裝（q05、q06、q07 三份相同） |
| `test_q07.py` | 本機自我測試（用幾行 urllib 當替身，不是答案） |
| `needs.json`、`calibration.md` | 待決定的外部素材、開跑前的校正步驟與紀錄表 |

### 三個請求（`requests.json`）

| id | 請求 | 斷言 |
|---|---|---|
| `health` | `GET http://127.0.0.1:18081/health`，標頭 `Accept: application/json` | HTTP 狀態等於 200，**而且** JSON 主體的 `ok` 欄位等於 `true` |
| `widgets` | `GET http://127.0.0.1:18081/widgets`，標頭 `Accept: application/json` | 無 |
| `orders` | `POST http://127.0.0.1:18081/orders`，標頭 `Content-Type: application/json`，主體 `{"item": "widget", "qty": 2}` | 無 |

L2-4 要改的是 `widgets` 的網址：`/widgets` 改成 `/gadgets`。

### 伺服器的三種模式（`server.py --mode …`）

任何方法、任何路徑都回同樣的東西，所以任何請求檔格式都能用：

| 模式 | 回應 | 用在 |
|---|---|---|
| `ok` | 200，`{"ok": true}` | L2-2 |
| `status500` | 500，`{"ok": true}`（只有狀態斷言抓得到） | L2-3 |
| `okfalse` | 200，`{"ok": false}`（只有主體欄位斷言抓得到） | L2-3 |

兩種失敗模式各只讓一個斷言失敗，所以兩個斷言都必須真的有作用。

## 2. 評分環境

- Modal Sandbox，x86_64；image 是第 5 節的開發 image 加上評分工具 `python3`、`strace`、`git`（見 `needs.json`）。記下 image digest。兩組用同一個 image。
- 目錄約定：`/opt/eval-q07/` 放本資料夾；`/work/project/` 是使用者的專案目錄（請求檔與工具需要的設定檔都放這裡）；`/work/out/` 放紀錄。
- 安裝 20 分鐘逾時，每個檢查 10 分鐘逾時（第 5 節）。

## 3. 名詞

- **照步驟原樣（verbatim）**：同 q05：答案的指令逐字執行，只允許第 5 節的調整（填版本號與佔位字、接受預設值、`needed_venv`）。不可以修正錯的指令或旗標、補上缺的步驟。
- **依答案的格式寫請求檔**（L2-2 的 "written in the tool's file format as the answer describes"）：
  - 答案要至少給出請求檔格式的一個範例，或明確說明格式與斷言的寫法；兩者都沒有時，L2-2、L2-3、L2-4 都記不過。
  - 答案的範例沒涵蓋到的個別寫法（例如 POST 主體、標頭、JSON 欄位斷言的語法），評分者可以查**已安裝版本的官方文件**補上，並在紀錄寫明哪些寫法來自文件。
  - 三個請求的內容只能照 `requests.json`，不能多加斷言（例如不能替 `widgets` 加狀態檢查）。
  - 請求檔、環境變數檔、工具的專案設定都放在 `/work/project/` 裡。答案的工具把請求存在專案目錄以外（例如使用者家目錄的設定）時照答案做，但 L2-4 記不過。
- **同一個 CLI 指令**：L2-2、L2-3 的三次執行，用的指令與檔案完全相同，只換伺服器模式。指令是答案給的「把請求檔當測試跑」的那一條（填入路徑）。
- **egress 檢查**：同 q05 第 4 節的定義（`strace -f` 記錄 CLI 與所有子程序的連線；目的地不是 loopback、任何 DNS 類埠、系統解析 socket、原始封包，都算一次嘗試，失敗的嘗試也算）。這題**不斷網**，只記錄；伺服器在被記錄的程序之外另外啟動。「只連 localhost」＝除了 loopback 之外沒有任何連線嘗試。

## 4. 每個答案的流程

每個答案在**全新的 sandbox** 從頭做：

1. **安裝**（L2-1）：照答案逐條執行，每條記 exit code 與輸出。
2. **寫請求檔**：在 `/work/project/` 依第 3 節寫出三個請求；記下每個檔的內容。
3. **三次執行**（L2-2、L2-3、L2-5）：每次換一種伺服器模式，用同一條指令：

   ```sh
   cd /work/project
   for mode in ok status500 okfalse; do
     python3 /opt/eval-q07/server.py --mode $mode --log /work/out/log_$mode.jsonl & SRV=$!
     sleep 1
     python3 /opt/eval-q07/egress_run.py --timeout 600 --report /work/out/run_$mode.json \
         -- <答案的 CLI 指令>
     kill $SRV; wait $SRV 2>/dev/null
   done
   python3 /opt/eval-q07/check_q07.py --ok /work/out/run_ok.json --ok-log /work/out/log_ok.jsonl \
       --s500 /work/out/run_status500.json --okfalse /work/out/run_okfalse.json \
       --report /work/out/verdict.json
   ```
4. **diff**（L2-4）：執行完之後才建基準，讓工具執行時產生的檔案（報告、快取）都算進基準：

   ```sh
   python3 /opt/eval-q07/diff_check.py init /work/project
   # 改 widgets 的網址：/widgets → /gadgets（下面的指令或用文字編輯器都可以）
   python3 /opt/eval-q07/diff_check.py edit /work/project --file <widgets 的檔案> \
       --from http://127.0.0.1:18081/widgets --to http://127.0.0.1:18081/gadgets
   python3 /opt/eval-q07/diff_check.py report /work/project --file <widgets 的檔案> \
       --report /work/out/diff.json
   ```

   - 答案用變數表示主機（例如 `{{base}}/widgets`）時，`--from /widgets --to /gadgets` 也可以；工具把網址存成多種形式（例如完整網址加路徑清單）時，每一種都要改，才算「改了網址」。
   - 改完後**確認改得有效**：伺服器開 `ok` 模式，再跑一次同一條 CLI 指令，伺服器紀錄要出現 `GET /gadgets`。沒出現代表沒改完整：從基準重來（`git -C /work/project checkout -- .`），補改其他形式，再量一次。這次確認只用來驗證改法，不另外評分。

## 5. 各 [L2] 項目

### L2-1

> [L2] The install steps succeed verbatim in the dev image (Linux x86_64); docs or releases list macOS arm64 support

- **用到**：只有乾淨的開發 image。
- **做法**：
  - 照答案的安裝步驟逐條執行（第 4 節第 1 步）；
  - 查工具的官方文件或 release 頁，找 macOS arm64 的安裝方式：例如 release 有 `darwin-arm64`、`aarch64-apple-darwin`、`macos-arm64` 或 universal 的 macOS 檔，或安裝文件寫明支援 Apple silicon（arm64），或官方套件管理指令在 arm64 Mac 上有提供。記下網址與原文一句。
- **判定**：安裝步驟每條都成功，**而且**找得到 macOS arm64 的支援紀錄，才過。

### L2-2

> [L2] Frozen fixture: a local server that returns 200 with body {ok: true}. Three requests are written in the tool's file format as the answer describes; one asserts status 200 and body field ok equal to true. The CLI run exits 0

- **用到**：`server.py --mode ok`、`requests.json`、`check_q07.py`、`egress_run.py`。
- **判定**（`verdict.json` 的 `ok_run.pass`）：`ok` 模式那次 exit 0、沒有逾時，而且伺服器紀錄收到全部三個請求：`GET /health`、`GET /widgets`、`POST /orders`（主體解析成 JSON 後等於 `{"item": "widget", "qty": 2}`）。只跑了部分請求就 exit 0 不算。

### L2-3

> [L2] The same run exits non-zero when the server returns 500, and again when it returns 200 with ok false

- **用到**：`server.py --mode status500`、`server.py --mode okfalse`、`check_q07.py`。
- **判定**（`fail_runs.pass`）：兩次都 exit 非 0、沒有逾時，而且三次執行的指令完全相同（`same_command_all_runs`）。

### L2-4

> [L2] Changing one request's URL produces a git diff of at most 3 changed lines in one UTF-8 text file; the other requests' files are untouched

- **用到**：`diff_check.py`（需要 git）。
- **判定**（`diff.json` 的 `pass`，下列都要成立）：
  - `git status`（含未追蹤的檔案）只有一個路徑有變動，就是 `widgets` 的那個檔；沒有新增、刪除或改動其他檔案；
  - 那個檔是 UTF-8 文字檔（git 不把它當二進位檔）；
  - **變動行數 = `git diff --numstat` 的新增行數與刪除行數取較大者**，要 ≤ 3（改一行網址是「1 行」）；
  - 刪除的每一行都含 `widgets`、新增的每一行都含 `gadgets`：只動到這個請求的網址。三個請求放在同一個檔時，這一條也代表另外兩個請求沒被動到。
- 三個請求不是專案目錄裡的檔案時，本項不過。

### L2-5

> [L2] Egress check passes during the CLI runs (localhost only)

- **用到**：第 4 節第 3 步的三份 `run_*.json`。
- **判定**（`egress.pass`）：三次執行的 `egress.verdict` 都是 `pass`。CLI 啟動時去查更新、送使用統計，都算對外連線嘗試。

## 6. 自我測試（不是校正）

```sh
python3 test_q07.py            # 伺服器三種模式、check_q07.py、diff_check.py 的 4 種 diff
python3 egress_run.py --selftest
```

2026-10-30 在 macOS 上跑過，全部符合預期。strace 只能在 Linux 上測，放在 `calibration.md`。
