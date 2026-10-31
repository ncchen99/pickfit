# q03 測試資料：在終端機處理 2–5 GB 的 CSV

題目要一個免費、開源、單一執行檔或發行版套件的 CSV 工具（不能依賴 Python、Java、Node），能正確處理 RFC 4180 的引號欄位，做列篩選、選欄、分組計數，記憶體用量不超過檔案大小的一半。`sandbox: linux_sandbox`。

這個資料夾放 L2 項目用到的測試資料與檢查腳本。沙盒**刻意不裝 Python**，所以在沙盒裡跑的腳本（`check_runtime.sh`、`big/gen_big.sh`，以及共用的 `../_shared/mem_peak.sh`）只用 POSIX sh 與 awk；比對輸出的 `check_outputs.py` 在評分者電腦上跑（Python 3.9 以上標準函式庫）。內容不含任何工具名稱或預期答案。

## 1. 檔案

| 檔案 | 用途 |
|---|---|
| `check_runtime.sh` | 項目 1：逐一檢查 `python3`、`java`、`node` 不在 PATH 上 |
| `small/sample.csv` | 凍結的小 CSV：24 筆資料、6 欄，引號欄位裡有逗號、跳脫的雙引號（`""`）、換行，有些不必加引號的欄位也加了引號；UTF-8、LF |
| `small/tasks.json` | 項目 2 要填進答案指令的欄位名與值 |
| `small/expected/*.csv` | 凍結的預期輸出（用 Python `csv` 模組算出） |
| `small/make_small.py` | 產生上面三者；`--check` 確認 commit 的檔案沒被改過 |
| `check_outputs.py` | 比對答案指令的輸出與預期輸出（`records`：篩選、選欄；`groupby`：分組計數） |
| `big/gen_big.sh` | 凍結的 seeded 產生器：2 GB、20 欄、分組鍵 1,000 個值、約 5% 的列有引號欄位；同時寫出預期的分組計數 |
| `../_shared/mem_peak.sh` | 項目 3：量每一步的耗時、exit code、cgroup 記憶體（memory.peak、取樣的 memory.current 與 anon、OOM kill 次數）；各題共用（[`_shared/README.md`](../_shared/README.md) 第 3 節） |
| `needs.json` | 需要外部取得的東西（base image） |
| `calibration.md` | 第一次開跑前的校準步驟與紀錄表（待填；記憶體量法要在這裡定案） |

## 2. 共同設定

- **環境**：base image `ubuntu:24.04`（以 digest 固定，見 `needs.json`），評分者不另外裝任何套件。`ubuntu:24.04` 沒有 python3、java、node。本資料夾複製到 `FIXTURE=/opt/eval/fixtures/q03`，工作目錄 `/work`。
- **原樣（verbatim）**：逐字執行答案的指令，只做 `eval/README.md` 第 5 節允許的調整（填版本號與佔位字、接受預設值）。任何一步 exit code 不是 0、或要改指令、旗標、補步驟才能成功，就不過。
- **填佔位字的範圍**（項目 2、3）：只換檔名、欄位名、比較的值，以及答案自己示範的比較運算子；保留答案的指令結構與旗標。不可以加答案沒寫的旗標（例如輸出格式、有沒有標頭、筆數上限）。答案沒有給某個操作的指令，該操作就不過。
- **輸出**：答案指令印到 stdout 的，評分者把 stdout 存成檔；答案指令寫到檔案的，用那個檔。輸出檔複製到評分者電腦再跑 `check_outputs.py`。

## 3. L2 項目

### 項目 1

> [L2] The install steps succeed verbatim in the base image (no python3, node or java); afterwards `command -v python3 java node` prints nothing

- **測試資料**：`check_runtime.sh`。
- **做法**：新沙盒（base image），先跑一次 `sh $FIXTURE/check_runtime.sh` 確認基準是空的（校準步驟 1 已確認），再逐行原樣執行答案的安裝步驟，最後再跑一次：
  ```sh
  sh $FIXTURE/check_runtime.sh
  ```
- **說明**：Ubuntu 的 `/bin/sh`（dash）執行 `command -v python3 java node` 時只查第一個名字，所以腳本逐一查三個名字，等同 bash 執行那一行的結果。
- **判定**：每一行安裝步驟 exit code 都是 0、沒有超出允許的調整，而且安裝後 `check_runtime.sh` 的 stdout 是空的（exit 0）→ 過。安裝過程把 python3、java、node 裝進來（例如被套件相依帶進來）也算不過。`python`、`nodejs`、`javac` 只列出供參考，不判定。

### 項目 2

> [L2] Frozen fixture CSV whose quoted fields contain commas, escaped double quotes and embedded newlines: the answer's commands for a row filter, a column selection and a group-by count return exactly the frozen expected outputs

- **測試資料**：`small/sample.csv`（欄位 `id,customer,note,region,amount,status`）、`small/tasks.json`、`small/expected/`、`check_outputs.py`。
- **要做的三件事**（填進答案自己的指令）：

  | 操作 | 填入 | 預期輸出 |
  |---|---|---|
  | 列篩選 | `status` 等於 `shipped`（整個欄位相等） | `expected/filter_status_eq_shipped.csv`（10 筆） |
  | 列篩選（答案只示範數值比較時改用這個） | `amount` 大於 `250` | `expected/filter_amount_gt_250.csv`（11 筆） |
  | 選欄 | `id`、`note`、`amount`，照這個順序 | `expected/select_id_note_amount.csv`（24 筆） |
  | 分組計數 | 依 `region` 計數 | `expected/groupby_region_count.csv`（5 組：central 2、east 4、north 7、south 5、west 6） |

  資料刻意放了幾個只有正確解析才會過的地方：`region`、`status` 排在含逗號與換行的 `note` 之後；有一筆 `note` 寫著 shipped 但 `status` 不是；`"west"`、`"north"` 有一筆加了引號；沒有任何值是另一個值的子字串，也沒有剛好等於 250 的金額。
- **做法**：
  ```sh
  mkdir -p /work/q03 && cp $FIXTURE/small/sample.csv /work/q03/ && cd /work/q03
  <答案的篩選指令，填入上表>  > out_filter.txt
  <答案的選欄指令>            > out_select.txt
  <答案的分組計數指令>        > out_groupby.txt
  ```
  在評分者電腦上：
  ```sh
  python3 check_outputs.py records --expected small/expected/filter_status_eq_shipped.csv --got out_filter.txt
  python3 check_outputs.py records --expected small/expected/select_id_note_amount.csv    --got out_select.txt
  python3 check_outputs.py groupby --expected small/expected/groupby_region_count.csv     --got out_groupby.txt
  ```
- **「exactly」的操作定義**：
  - 篩選、選欄（`records`）：輸出以 RFC 4180 CSV（逗號分隔）解析後，資料列必須與預期**逐筆、逐欄、同順序**相同。標頭可有可無；有的話必須與預期標頭相同。引號加法、CRLF 或 LF、最後一行有沒有換行不影響。數值欄位以數值比較（`120.50` 與 `120.5` 視為相同），其他欄位逐字比較。不是 CSV 的輸出（對齊表格、框線表格）不過，因為它無法原樣帶回欄位裡的換行與逗號。
  - 分組計數（`groupby`）：輸出可以是 CSV、TSV、空白對齊或框線表格，列的順序、標頭、多出的欄（例如百分比）、筆數註腳都不影響。每個預期的鍵必須剛好出現在一列，並與正確的計數同列；任何其他帶計數的列（例如解析錯誤產生的 `"west"` 或換行欄位的片段）都算錯。
- **判定**：三個 `check_outputs.py` 都印 `PASS` → 過。

### 項目 3

> [L2] On a 2 GB CSV from the frozen seeded generator (about 20 columns, a group key with 1,000 distinct values, quoted fields in 5% of rows), all commands the answer gives for the group-by count, including any index build, finish within 5 minutes on 4 vCPU, and container memory.peak stays at or below 1 GB

- **測試資料**：`big/gen_big.sh`、`$SHARED/mem_peak.sh`、`check_outputs.py`。
- **產生的檔案**：`sh gen_big.sh /work/big.csv` 寫出至少 2,000,000,000 位元組（GB 以十進位計）的 CSV：20 欄（`id,ts,account,category,note,amount,qty,unit_price,currency,country,city,group_key,status,channel,flag,score,latency_ms,device,ref,comment`），分組鍵 `group_key`（第 12 欄）有 `G0000`–`G0999` 共 1,000 個值；約 5.1% 的列 `note`（第 5 欄）加了引號並含逗號，其中一部分還含跳脫雙引號（約佔全部的 1.6%）或換行（約 1.0%）。只有 ASCII、LF。同時寫出 `big.csv.expected_counts.csv`（凍結的正確分組計數）與 `big.csv.meta`（列數、位元組數、seed）。亂數是 awk 實作的 Lehmer（MINSTD）產生器，以精確的整數運算，不同的 awk 產生的檔案逐位元相同（出題時完整的 2 GB 檔案在 macOS 的 BSD awk 與 Debian 的 mawk 1.3.4 上 SHA-256 相同）。完整 2 GB 檔案的參考雜湊記在 `calibration.md`。
- **環境**：4 vCPU；記憶體量法照校準步驟 3 定案的方式設定（見下）。檔案放在沙盒的本機磁碟。產生檔案不計時。
- **做法**：
  1. 新沙盒（base image），原樣跑答案的安裝步驟（同項目 1）。
  2. 產生檔案並核對：`sh $FIXTURE/big/gen_big.sh /work/big.csv && cat /work/big.csv.meta && sha256sum /work/big.csv`，雜湊必須等於 `calibration.md` 的參考值。
  3. 答案給的分組計數相關指令（含建索引）依序逐一包在 `mem_peak.sh run` 裡執行，分組鍵填 `group_key`（`$SHARED` 是 `eval/fixtures/_shared` 在沙盒裡的位置）：
     ```sh
     cd /work
     MAX_BYTES=1000000000 sh $SHARED/mem_peak.sh run /work/mem-step1.json '<答案的第一個指令，例如建索引>'
     MAX_BYTES=1000000000 sh $SHARED/mem_peak.sh run /work/mem-step2.json '<答案的分組計數指令>'
     ```
  4. 把 `mem-step*.json` 與最後一步的輸出（`mem-step2.json.stdout`，或答案寫出的檔）複製出來，在評分者電腦上：
     ```sh
     python3 check_outputs.py groupby --expected big.csv.expected_counts.csv --got mem-step2.json.stdout
     ```
- **判定**：以下全部成立 → 過：
  - 每一步 exit code 都是 0；
  - 各步耗時（`mem-step*.json` 的 `wall_seconds`）加總 ≤ 300 秒；
  - 記憶體：照校準步驟 3 定案的規則。依題目原文是 memory.peak ≤ 1,000,000,000 位元組；但出題時在本機 Linux 容器實測，cgroup v2 的 memory.peak 會把**讀寫檔案的 page cache** 算進去（產生 200 MB 檔案後、還沒跑任何工具，memory.peak 已經 208 MB），所以 2 GB 的檔案會讓任何工具都超過。校準若證實 L2 沙盒也是這樣，就改用登記的替代規則：沙盒設硬上限 ≤ 1,000,000,000 位元組、不用 swap（page cache 會被回收，工具自己的記憶體超過上限就會被 OOM kill），規則變成「沒有任何一步被 OOM kill（`oom_kills` 是 0、exit code 不是 137）」；這時 memory.peak 依定義不會超過上限。規則 A 時看每一步的 `result`（共用的判定：峰值計數 ≤ 1,000,000,000 而且沒有 OOM kill；步驟開始時計數已超過，就改用取樣值，見 `_shared/README.md` 第 3 節）；
  - 分組計數的輸出與 `big.csv.expected_counts.csv` 相符（`check_outputs.py groupby` 印 `PASS`）。沒算完、算錯或只印出部分組別，都表示「分組計數」沒有完成。

## 4. 外部材料與校準

- base image digest：見 `needs.json`。
- 凍結前校準（base image 基準、2 GB 檔案的參考雜湊與產生時間、記憶體量法定案、4 vCPU 確認）：見 `calibration.md`。
