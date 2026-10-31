# q02 測試資料：把 log 裡的金鑰、token、email、IP 遮掉的 stdin→stdout 過濾器

題目要一個免費、開源、在 Linux 本機執行的命令列過濾器，從 stdin 讀 log、把 API key、token、email、IP 遮掉後寫到 stdout，不用自己寫 regex。`sandbox: linux_sandbox`。

這個資料夾放 L2 項目用到的測試資料產生器與檢查腳本。**假的金鑰、token 不 commit**：repo 裡只有產生器，測試時才產生 log（`eval/README.md` 第 8 節）。腳本只用 Python 3.9 以上的標準函式庫或 POSIX sh，不含任何工具名稱或預期答案。

## 1. 檔案

| 檔案 | 用途 |
|---|---|
| `gen_log.py` | 凍結的 seeded 產生器：寫出 `app.log`（一般行＋6 行各帶一個假的敏感值）與 `manifest.json`（6 個值、所在行號、一般行的行號）。輸出目錄在這個 git repo 裡時拒絕執行 |
| `check_clean.py` | 比對 `app.log` 與 `clean.log`，分別判定「遮罩」與「一般行不變」兩項；不印出任何假值 |
| `egress/run_traced.sh`、`egress/egress_check.py` | egress check（與 q01 相同的檔案） |
| `needs.json` | 需要外部取得的東西（strace、dev image） |
| `calibration.md` | 第一次開跑前的校準步驟與紀錄表（待填） |

## 2. 產生的 log

`python3 gen_log.py OUT_DIR`（預設 seed `q02-v1`）產生 246 行，其中 240 行一般行、6 行敏感值行：

- **一般行**只由時間戳（`2026-10-27T08:00:00.346Z`）、log 等級（INFO、DEBUG、WARN、ERROR）、檔案或請求路徑、HTTP 狀態碼、耗時（`998ms`、`1.25s`）組成，加上 `path=`、`status=`、`duration=`、`file=` 這幾個欄位名。沒有 UUID、雜湊、帶點的版本字串、IP、email。
- **6 個敏感值**，每個獨佔一行，前後有自然的 log 文字：
  1. AWS 格式的 access key ID：`AKIA` 加 16 個隨機字元。字元取自 `[A-Z2-7]`（AWS 實際使用的 base32 字母表），它是題目寫的 `[A-Z0-9]` 的子集，所以同時符合題目與真實格式。
  2. GitHub 格式的 personal access token：`ghp_` 加 30 個隨機 base62 字元，再加 6 個字元的 checksum（30 個字元的 CRC32，以 `0-9A-Za-z` 的 base62 表示、左補 0），總長 40。
  3. `example.com` 的 email、4. `example.org` 的 email（local part 是「名.姓」形式）。
  5.、6. 兩個公用 unicast IPv4：排除 RFC 6890 的所有特殊用途範圍（含題目列的 private、loopback、link-local、100.64/10、documentation、multicast，另外也排除 0/8、192.0.0/24、192.88.99/24、198.18/15、240/4）。
- **讓檢查只會被這 6 個值觸發**：產生器確認 key 與 token 的隨機部分沒有任何 5 個字元的片段出現在 log 其他地方，也不含常見遮罩字樣（REDACTED、MASKED、TOKEN 等）的 5 字元片段；兩個 email 的 local part 不出現在其他地方、也不互相包含；IP 的第三、第四段數字（都在 100–254，且不是 200、201、204）不以獨立數字出現在其他地方，而且兩個 IP 的 8 個段數字互不相同。不符合就換下一組（`manifest.json` 的 `attempt` 記下用了第幾組）。
- **固定**：同一個 seed 一定產生逐位元相同的檔案（用 SHA-256 計數器當亂數來源，不依賴 Python 版本）。預設 seed 的 `app.log` SHA-256 應為 `ac585975926b1d4af3a74b9a75a29e462926053244a182612e151c56b5b655d9`（出題時在 Python 3.9、3.12、3.13 與 Debian x86_64 的 Python 3.12 上相同）；校準步驟 2 在 dev image 再確認一次。
- **假值只存在測試當下的目錄**：`app.log`、`manifest.json`、`clean.log` 都含假值，**不可以 commit**（包括 `eval/results/`），否則 GitHub 的 push protection 會擋。可以 commit 的是 `check_clean.py --report` 的報告（不含值）和 egress 報告。

## 3. 共同設定

- **環境**：dev image（`needs.json`；需要 `python3`、`strace`）。本資料夾複製到 `FIXTURE=/opt/eval/fixtures/q02`，測試目錄 `/work/q02`，紀錄放 `/opt/eval/state/`。
- **原樣（verbatim）**：逐字執行答案的指令，只做 `eval/README.md` 第 5 節允許的調整（填版本號與佔位字、接受預設值；裸 `pip install` 被擋時改用 venv 並記 `needed_venv`，但「原樣成功」那一項不過）。任何一步 exit code 不是 0、或要改指令、旗標、補步驟才能成功，就不過。
- **egress check**：把指定步驟包在 `egress/run_traced.sh` 裡執行，strace 記下所有子程序的 `connect`、`sendto`、`sendmsg`、`sendmmsg`；`egress/egress_check.py` 把非 loopback 的 IPv4／IPv6 目的地、任何位址的 port 53（DNS）、其他能上網的 socket 家族都算成對外連線嘗試（失敗的也算）。exit 0＝過、1＝不過、2＝沒有追蹤成功的證據（要修好追蹤後重跑）。

## 4. L2 項目

### 項目 1

> [L2] The install steps succeed verbatim in the dev image

- **測試資料**：無。
- **做法**：新沙盒（dev image），逐行原樣執行答案的安裝步驟，記下 exit code 與輸出。安裝不在 egress check 範圍內。
- **判定**：每一行 exit code 都是 0，而且沒有超出第 5 節允許的調整 → 過。

### 項目 2

> [L2] Fixture log produced at test time by the frozen seeded generator (fake values are never committed): one AWS-format access key ID (AKIA plus 16 random [A-Z0-9]), one GitHub-format personal access token (ghp_ prefix, valid length and checksum format), two email addresses at example.com and example.org, two public unicast IPv4 addresses outside private, loopback, link-local, shared 100.64/10, documentation and multicast ranges, plus ordinary lines. Run as one pipeline (`cat app.log | <tool with the answer's flags> > clean.log`). A value counts as masked when its exact string is absent and: for the key and token, no run of 5 or more characters of the random part survives; for emails, the local part is gone; for IPs, at least the last two octets are gone. All six values must be masked

- **測試資料**：`gen_log.py` 產生的 `app.log`、`manifest.json`；`check_clean.py`。
- **做法**：
  ```sh
  python3 $FIXTURE/gen_log.py /work/q02            # 印出的 sha256 必須等於第 2 節的參考值
  cd /work/q02
  sh $FIXTURE/egress/run_traced.sh /opt/eval/state/q02-egress.log \
    'cat app.log | <答案的工具與旗標> > clean.log'
  echo "pipeline exit: $?" > /opt/eval/state/q02-exit.txt
  python3 $FIXTURE/check_clean.py --manifest manifest.json --input app.log --output clean.log \
    --report /opt/eval/state/q02-check.json
  ```
  管線的形狀固定是 `cat app.log | … > clean.log`。答案的工具若需要設定檔或規則檔，照答案的步驟放好；只能讀檔案參數、不能讀 stdin 的工具，照這個形狀跑會失敗，不另外改寫。
- **判定**（`check_clean.py` 的 `ITEM masking`）：對每個值，`clean.log` 裡都找不到它的完整字串，而且：
  - key 與 token：隨機部分（前綴 4 個字元之後的全部字元；token 含 checksum）的任何連續 5 個字元都不出現在 `clean.log`；
  - email：local part（`@` 之前）不出現在 `clean.log`；
  - IP：第三、第四段都不以獨立數字（前後不接英數字）出現在 `clean.log`。前兩段可以保留。

  6 個值都遮掉 → 過。管線的 exit code 只記錄、不判定（有些過濾器找到敏感值時會回傳非 0）。

### 項目 3

> [L2] Ordinary lines (timestamps, log levels, file paths, HTTP status codes and durations only; no UUIDs, hashes or dotted version strings) are byte-identical in the output

- **測試資料**：同項目 2（同一次執行的 `app.log`、`clean.log`）。
- **做法**：項目 2 的 `check_clean.py` 同時印出 `ITEM ordinary`。
- **判定**：`manifest.json` 列的 240 行一般行，每一行都以整行、逐位元相同的形式出現在 `clean.log`，而且順序不變 → 過。`clean.log` 多出的行（例如摘要）不影響；換行改成 CRLF、時間戳被改寫或遮掉、行被刪掉都不過。

### 項目 4

> [L2] Egress check passes during the run

- **測試資料**：`egress/`。
- **範圍**：項目 2 的那一條管線（產生 log、安裝、評分者的檢查都不算）。
- **做法**：
  ```sh
  python3 $FIXTURE/egress/egress_check.py /opt/eval/state/q02-egress.log \
    --json /opt/eval/state/q02-egress.json
  ```
- **判定**：exit 0 → 過；exit 1 → 不過，附上每一筆連線嘗試；exit 2 → 量測失敗，修好追蹤後在新沙盒重跑項目 2–4（答案原文不變），記錄原因。

## 5. 外部材料與校準

- strace、dev image：見 `needs.json`。
- 凍結前校準（追蹤方式、產生器在 dev image 的參考雜湊、檢查腳本的對照組）：見 `calibration.md`。
