# L2 共用工具

各題判定方式原本各寫一套的四件事，統一在這裡：沒有對外連線（egress）、繁體比例、記憶體量測、git diff 改了幾行。各題的 README 只寫「這題包哪些步驟、門檻是多少」，定義與做法都以本文為準。

全部自己寫的，只用 Python 3.8 以上的標準函式庫或 POSIX sh。要外部取得的東西（strace、OpenCC 的字典檔）列在 [needs.json](needs.json)，**沒有下載**。

在沙盒裡，本資料夾放在 `$SHARED`（例如 `/opt/eval/fixtures/_shared`，和各題的資料夾並列）；各題 README 的指令都寫成 `$SHARED/...`。

| 檔案 | 用途 | 用到的題 |
|---|---|---|
| `egress.py` | 沒有對外連線的檢查（第 1 節） | q01、q02、q04、q05、q06、q07、q09、q14、q15、q16、q17、q18、q19、q20 |
| `zh_script.py` | 繁體比例、轉成繁體（第 2 節） | q11、q15 |
| `mem_peak.sh` | 記憶體量測（第 3 節） | q03、q14 |
| `git_diff_lines.py` | git diff 改了幾行（第 4 節） | q07、q09 |
| `selftest_dict/` | `zh_script.py` 測試用的手寫小字典（**不是** OpenCC 的資料） | 測試 |
| `test_shared.py` | 本資料夾的測試（`python3 test_shared.py`；不用網路、不用 strace） | 測試 |
| `test_ollama_scope.py` | q18–q20 的啟動腳本只讓評分者啟動的那一個 Ollama 帶 `OLLAMA_NO_CLOUD=1`，答案自己啟動的伺服器不帶（9.3 C.5） | q18、q19、q20 |
| `needs.json` | 要外部取得、等念誠決定的東西 | |
| `calibration.md` | 第一次開跑前在 L2 沙盒做的校準與紀錄表 | |

## 1. 沒有對外連線（egress）

**一次對外連線嘗試**（失敗的也算）：
- 連往 IPv4／IPv6 位址，而它不是 loopback（127.0.0.0/8、::1、::ffff:127.0.0.0/104）、不是 0.0.0.0／::，也不是這個沙盒自己網卡的位址（`run` 時記下）；
- 任何位址（含 loopback）的查名稱用 port：53、853、5353、5355（本機的 resolver 會往外轉送）；
- strace 解不出的 IPv4／IPv6 位址；
- 連 systemd-resolved 的 socket（`/run/systemd/resolve/...`）；
- 其他能離開沙盒的 socket 家族（`AF_PACKET`、`AF_VSOCK` 等）。

不算：`AF_UNIX`（resolver 以外）、`AF_NETLINK`、`AF_UNSPEC`，以及沒有位址的呼叫（已連線的 socket 上的傳送；它的 connect 已經算過）。

**做法**：要檢查的每一步都用 `egress.py run` 包起來，strace `-f` 記下它和它啟動的所有程序的 `execve`、`connect`、`sendto`、`sendmsg`、`sendmmsg`。這一步留在背景的程序（服務、金鑰 agent）**繼續被記錄**，直到 `egress.py stop`；所以先啟動服務、之後才送請求的流程，服務後來的連線也記得到。

```sh
python3 $SHARED/egress.py run --out $EG --label 01-add --sh '<答案的指令，佔位字已填>'
python3 $SHARED/egress.py run --out $EG --label 02-sync --timeout 600 -- <argv...>
python3 $SHARED/egress.py stop --out $EG              # 停掉還在記錄的 tracer（程序繼續跑）；--kill 連程序一起停
python3 $SHARED/egress.py report --out $EG --json $EG/report.json
```

- `run` 在這一步自己的指令結束時就回來，exit code 就是那個指令的（逾時 124、設定失敗 125）。輸出寫在 `$EG/<label>.stdout`、`.stderr`（避免背景程序卡住呼叫端的 pipe），也可用 `--stdout`／`--stderr` 指定。
- `--block-network`：在新的 network namespace 裡跑，只有 loopback，DNS 也查不到（要 root）。Modal 的 gVisor 沙盒裡 root 沒有 CAP_SYS_ADMIN，所以改建 user＋network namespace，由留在原本 namespace 的輔助程序把所有 uid、gid 對應成自己（uid 1000 在裡面仍是 1000）；用了哪一種、uid 怎麼對應、loopback 自我測試，記在 `<label>.netns.json`。**每一次 `--block-network` 都是新的 namespace**：要互相連線的步驟（啟動服務與送請求）要寫進同一個腳本，用一次 `--sh 'bash 腳本'` 跑完。
- `--kill-leftovers`：這一步結束 2 秒後停掉它留下的程序。
- `--no-trace`：同樣的包裝但不用 strace，只計時（例如 q15 比速度時，兩邊都不能有 strace 的額外負擔）；`report` 不納入它。
- **判定**（`report`）：`pass`＝沒有任何嘗試、每份紀錄都有 execve（證明真的在 strace 下跑過）、沒有 tracer 還在跑（exit 0）；`fail`＝至少一次嘗試，報告列出每一筆與原始紀錄行（exit 1）；`undetermined`＝紀錄缺漏、沒有 execve，或還沒 `stop`：量測沒做好，不算答案的錯，修好後重跑該步驟（exit 2）。
- `report` 與 `parse` 可以在評分者的電腦上跑（把 `$EG` 整個複製出來）。

**擋外連**（題目寫 with egress blocked 時）：用 `egress.py run --block-network`（9.3 B.3；2026-10-31 在 Modal 的 dev image 實測，結果在 `calibration.md`）。擋了之後先跑 `egress.py probe`：直接連公開位址的 TCP 與送到公開 DNS 的 UDP 都失敗才算擋住（exit 0）。透過沙盒自己的 resolver 查名稱，結果只記在 `dns_resolves`、不影響判定：Modal 的 resolver 在擋網路的沙盒裡仍會回答（2026-10-31 其他 session 實測），而受測步驟的任何查名稱都已經在 strace 紀錄裡算成一次嘗試。`probe` 顯示沒擋住是評分環境的問題：修好重跑，不記答案不過。

**取代了什麼**：q01、q02、q04 的 `egress/run_traced.sh`＋`egress_check.py`；q05、q06、q07 的 `egress_run.py`；q09 的 `egress_parse.py`、`egress_selftest.sh`；q14、q15、q16 的 `egress_check.py`；q17–q20 的 `egress/egress.py`。統一後的差別：
- q14–q16 原本只算非 loopback 位址：現在 loopback 上的 DNS 也算（與其他題一致）。
- q05–q07 原本把連 nscd 的 socket 也算：現在不算（`su`、`id` 查使用者也會連它，會誤判；Ubuntu 24.04 沙盒沒有 nscd，查名稱會直接送 port 53，照樣記得到）。
- q17–q20 原本另有全系統的 DNS 紀錄層與 `/proc/net` 輪詢：拿掉。改成評分者啟動的服務也用 `run` 包起來，所有要看的程序都在 strace 底下；`/proc/net` 輪詢抓不到立刻失敗的連線（q14 出題時實測），不能當判定依據。
- 背景程序：q01 原本讓它脫離追蹤、q14 原本把它停掉；現在預設繼續記錄到 `stop`，要停掉的題用 `--kill-leftovers`。

strace 在 L2 沙盒不能用（`calibration.md` 的自我測試沒過）時，egress 項目全部記「無法檢查」並請念誠決定替代方式；不能只靠「擋網路後指令仍成功」判過。

## 2. 繁體比例與轉成繁體（OpenCC）

q11、q15 只用**同一個固定版本的 OpenCC**：那個 release tag 原始碼裡 `data/dictionary/` 的 `STCharacters.txt`、`STPhrases.txt`、`TSCharacters.txt`、`TWVariants.txt`（版本與 SHA-256 記在 `calibration.md`；不 commit）。不用 OpenCC 的程式或 Python 套件。

```sh
python3 $SHARED/zh_script.py --dict-dir $OPENCC ratio reply1.txt reply2.txt ...   # 繁體比例
python3 $SHARED/zh_script.py --dict-dir $OPENCC convert --to tw file.txt          # 轉成繁體（q15 的 CER）
python3 $SHARED/zh_script.py --dict-dir $OPENCC ref-stats reference.txt          # q15：參考稿的繁簡不同字數
```

- **繁體比例**（第 5 節「逐字判斷，繁體比例 ≥0.95 且至少 30 個繁簡不同字」）：原文逐字看，不先轉換。一個字是 `STCharacters` 的 key、而且不在它自己的繁體候選裡 → 簡體字；是 `TSCharacters` 的 key、而且不在它自己的簡體候選裡 → 繁體字；兩者都是或都不是 → 不計（例如 后、里、台、着 這類兩種寫法都對的字）。比例＝繁體字／（繁體字＋簡體字）。沒有上下文判斷、沒有例外清單：在繁體文章裡可能正確的字，一律不算成簡體。
- **轉成繁體**：OpenCC 的 s2t 用同一批檔案做：`STPhrases`＋`STCharacters` 由左到右取最長的詞，用第一個候選；`--to tw` 再套 `TWVariants`（OpenCC 的 s2tw）。q15 的參考稿與答案兩邊都經過同一個函式，少數斷詞與 OpenCC 程式不同的地方不會偏向任何一邊。
- **取代了什麼**：q11 的 `opencc_scorer.py`（規則相同，搬過來）；q15 的 `zh_score.py` 原本用 OpenCC 套件、依上下文判斷，另有例外清單。現在 q15 的繁體比例與 q11 完全同一套，`zh_score.py` 只剩 CER，轉換改用本工具。

## 3. 記憶體量測（Linux）

```sh
MAX_BYTES=1000000000 sh $SHARED/mem_peak.sh run /work/mem-step1.json '<答案的指令>'   # 包一個步驟
sh $SHARED/mem_peak.sh watch /work/mem-watch.json &                                   # 跨好幾步：背景取樣
BELOW_BYTES=8589934592 sh $SHARED/mem_peak.sh read /work/mem.json /work/mem-watch.json
```

- 只用 POSIX sh、awk、coreutils（q03 的沙盒刻意沒有 Python）。
- 記錄：cgroup 的峰值計數（v2 `memory.peak`，v1 `memory.max_usage_in_bytes`）在步驟前後的值、每 0.2 秒取樣的 `memory.current` 與 `anon`（不含讀檔的 page cache）、所有程序 RSS 加總、上限、OOM kill 次數。
- **判定用的值**：有峰值計數、而且步驟開始時還沒超過門檻 → 峰值計數；否則取樣的 `memory.current` 最大值；再沒有就是 RSS 加總最大值。`MAX_BYTES`＝不超過（≤）、`BELOW_BYTES`＝低於（<），照題目原文選；另外要沒有 OOM kill。
- page cache 算不算（`memory.peak` 會把讀寫檔案的 page cache 算進去）由各題的 `calibration.md` 決定；`max_anon` 每次都記，讓那個決定可以用同一份紀錄做。
- **取代了什麼**：q03 的 `big/measure.sh` 與 q14 的 `mem_peak.py`。q11 是 Mac（沒有 cgroup），仍用 `q11/mac/footprint_watch.py`。

## 4. git diff 改了幾行

```sh
python3 $SHARED/git_diff_lines.py REPO BASE --json out.json
```

- 先 `git add -A`（新增、刪除、搬移的檔都算到），再看 `git diff --cached -M --unified=0 BASE`。BASE 是改動前的 commit（工具自己 commit 也看得到）。
- **改了幾行**＝每個 hunk 取 max（刪掉的行數，加上的行數），所有檔案加總。原地改一行＝1 行（diff 裡是一刪一加）；只加或只刪的每一行各算 1；只搬移、沒改內容的檔＝0 行，另列在 `renamed`；二進位的改動沒有行數（`changed_lines` 是 null，列在 `binary`）。
- 同時記下每個改動的檔、狀態、加刪行數，以及它是不是 UTF-8 文字（嚴格解碼、沒有 NUL、除了 tab、LF、CR、換頁之外沒有控制字元）。門檻（幾行、幾個檔）由各題判定。
- **取代了什麼**：q07 原本用 max（全部加的行，全部刪的行），q09 原本用加＋刪。這兩種在「原地改一行」時分別是 1 與 2，所以統一成上面的定義。**這個定義要念誠確認**（q09「closing one more task changes at most 5 lines」用新定義會比原本寬一些）。
