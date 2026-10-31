# q17 測試資料：離線問答筆記與 PDF

這個資料夾是 [eval/README.md](../../README.md) 第 8 節要求的 q17 測試資料，只給評分者用，**不給受測 agent 看**。題目原文在 [questions.yaml](../../questions.yaml) 的 `q17`。

全部自己產生、合成的內容：沒有第三方檔案、沒有金鑰、不含任何工具名稱或預期答案；任何答案推薦的工具都用同一份資料、同一套步驟檢查。腳本只用 Python 標準函式庫（3.9 以上）或 POSIX shell，不需要網路。

## 0. 檔案

| 檔案 | 用途 |
|---|---|
| `corpus/` | 凍結的語料：50 個 Markdown 筆記、5 個文字型 PDF（共 55 個檔，約 40 KB） |
| `questions.json` | 5 題凍結問題、各自的 token 與出處檔名；另有一題暖身問題（見 L2-1） |
| `SHA256SUMS` | 語料與 `questions.json` 的雜湊 |
| `make_corpus.py` | 產生語料（固定 seed、輸出不含時間）；重跑得到逐位元組相同的檔 |
| `verify_corpus.py` | 核對雜湊、檔數、每個 token 只出現在它的出處檔；`--regenerate` 另外重產生並比對 |
| `check_answers.py` | 依 5 題的作答紀錄判 L2-2、L2-3 |
| `tools/run_steps.py` | 把答案的指令原字不改、依序打進同一個終端機 session，記下每條的 exit code |
| `tools/pty_drive.py` | 在虛擬終端機裡執行一個指令（可打字、可自動同意提示），記錄輸出與時間 |
| `tools/gen_dummy_key.py` | 執行時產生一個假的金鑰值（只在答案說「金鑰填什麼都可以」時用） |
| `egress/egress.py` | egress check（見第 1 節） |
| `selftest.sh`、`tests/` | 離線自我測試 |
| `needs.json` | 要外部取得、等念誠決定的東西（dev image 內容、strace） |
| `calibration.md` | 第一次開跑前要做的校準步驟與結果欄位 |

### 語料的設計

- 5 個合成事實，每個帶一個編出來的 token（例如 `VELDRAOLUN-7402`）。3 個在 Markdown 筆記裡；**2 個只在 PDF 裡**（`harbor-ferry-timetable-2024.pdf`、`kiln-care-manual.pdf`，都在第 2 頁），沒有任何 Markdown 檔含這兩個 token。
- 每個事實另有一篇「相關但沒有 token」的筆記（例如提到同一隻甲蟲、同一艘夜班渡輪，但說「號碼在另一份筆記／PDF 裡」），用來看引用的是不是真正的出處。其餘 42 篇筆記與 3 個 PDF 是不相關的日常內容。
- 檔名彼此不互相包含，問題文字裡沒有任何檔名或 token，所以「答案提到哪個檔」可以直接比對。
- PDF 是 PDF 1.4、Helvetica（WinAnsi）、Flate 壓縮的真文字，不是掃描圖。寫 fixture 時已用 stdlib 解碼、poppler `pdftotext`、Apple PDFKit、pypdf 6.16.2 確認讀得出完整 token。

## 1. 共用做法

### 環境

- dev image：needs.json 第 1 項（念誠決定）。下文假設 Ubuntu 24.04、使用者 `dev`（可免密碼 sudo）、本資料夾放在 `F=/opt/eval-fixtures/q17`、工作資料夾 `W=/eval-work/q17/<組別>`。
- 沙盒規格照題目：Modal Sandbox，**CPU only、4 vCPU、16 GiB**。
- 兩個沙盒：**沙盒 A**（網路開）做安裝、建索引；做完用 `snapshot_filesystem()` 快照檔案系統；**沙盒 B** 用快照開機並封鎖網路，只做提問。封鎖方式與量測方式在 calibration.md 的 E 段校準。
- 語料放在使用者的筆記資料夾 `~/notes`（`cp $F/corpus/* ~/notes/`，55 個檔平放）。答案裡的「你的筆記資料夾」之類佔位字一律填 `~/notes`（第 5 節允許填佔位字）。

### 答案的指令怎麼跑

- 評分者把答案的指令**原字不改**抄進步驟檔（`$W/steps-install.txt`、`$W/steps-index.txt`…），依答案的順序，一行一條；只能填版本號與佔位字（第 5 節）。
- 用 `python3 $F/tools/run_steps.py --steps <檔> --out <輸出>` 執行：它開一個 `bash --login -i`，把每條指令打進去，等上一條結束才打下一條，遇到第一條非 0 就停。安裝程式問問題時，以 `--accept '<提示的 regex>'` 送 Enter（接受預設值，第 5 節允許）。答案說「重開終端機」時，步驟檔寫一行 `#NEW_SHELL`。
- 答案沒有寫、但要跑起來非補不可的步驟，**不補**（第 5 節）；Ubuntu 擋下裸 `pip install` 時可改在 venv 裡做並記 `needed_venv`。
- 容器沒有 systemd：答案的安裝程式若把服務註冊成 systemd 服務，評分者照該服務設定的啟動指令手動在背景啟動，記 `started_service_manually`（見 open question）。

### egress check（本題 L2-2 用）

「egress」指**任何連往本機以外的嘗試**：查詢 localhost 以外名稱的 DNS，或對 loopback（127.0.0.0/8、::1）、0.0.0.0、本沙盒自己介面位址以外的 IPv4／IPv6 位址呼叫 connect／sendto／sendmsg（失敗的嘗試、UDP、多播都算）。

`egress/egress.py` 有三層，寫在同一個輸出資料夾：

| 層 | 怎麼量 | 涵蓋 |
|---|---|---|
| dns（必要） | 在 127.0.0.1:53 起一個記錄所有查詢的 DNS，`/etc/resolv.conf` 指向它。`--mode sink`：localhost 以外一律回 NXDOMAIN（網路封鎖時用）；`--mode forward`：轉給原本的 DNS（網路開著時用） | 之後啟動的所有程序 |
| strace | `egress.py trace --out <資料夾> --label <名稱> -- <指令>`，在 strace 底下跑該指令與它的所有子程序 | 該指令的程序樹 |
| poll | 每 50 ms 讀 `/proc/net/{tcp,tcp6,udp,udp6}`，記下遠端不是本機的 socket | 整個沙盒（盡力而為） |

**「egress check 通過」**＝ `python3 $F/egress/egress.py report --out <資料夾> --since <開始> --until <結束>` 的 `result` 是 `pass`：時段內三層的違規都是 0，而且必要層都有在運作。`fail` ＝ 有對外嘗試（報告列出名稱與位址）。`incomplete` ＝ 必要層沒在運作，**不能判過，也不算答案的錯**：修好量測後重做。strace 層與 poll 層是不是必要層，在 calibration.md E7 決定，所有題、所有組一樣。

**「egress blocked」**＝ 在沙盒 B（網路封鎖）做，DNS 層用 `sink` 模式。

### 金鑰

評分者從頭到尾**不提供任何真的雲端金鑰**，沙盒環境變數裡也沒有。答案要求設定一個金鑰值、而且說明任何值都可以時（例如本機伺服器不驗證），用答案寫的字面值；答案只寫「你的金鑰」時，用 `python3 $F/tools/gen_dummy_key.py` 當場產生一個假值（不 commit）。

## 2. 各 [L2] 項目

### L2-1 建索引

> [L2] In the dev image (CPU only, 4 vCPU and 16 GB), the steps index a frozen corpus of 50 Markdown files and 5 text-based PDFs within 30 minutes. The corpus holds 5 synthetic facts with unique made-up tokens; the facts for 2 of them exist only in the PDFs

用到：`corpus/`、`SHA256SUMS`、`verify_corpus.py`、`questions.json` 的 `warmup_question`、`tools/run_steps.py`、`tools/pty_drive.py`。

做法（沙盒 A，網路開）：

```sh
python3 $F/verify_corpus.py                      # 語料沒被動過
mkdir -p ~/notes && cp $F/corpus/* ~/notes/
python3 $F/tools/run_steps.py --steps $W/steps-install.txt --out $W/install --step-timeout 600 --total-timeout 1200
python3 $F/tools/run_steps.py --steps $W/steps-index.txt --out $W/index --step-timeout 1800 --total-timeout 1800
```

- `steps-index.txt` 是答案裡「建索引／匯入文件」的指令（佔位路徑填 `~/notes`）。下載嵌入模型、語言模型若是答案的獨立步驟，算安裝（照第 5 節 20 分鐘上限）；若是建索引指令自己觸發的，算在 30 分鐘內。
- 答案沒有獨立的建索引步驟（第一次提問時才建）：改用 `questions.json` 的暖身問題觸發，`python3 $F/tools/pty_drive.py --out $W/index-warmup --timeout 1800 -- <答案的提問指令與暖身問題>`，計時算 L2-1；暖身問題不計分。

通過：建索引的指令（或暖身提問）全部 exit 0，總時間 ≤ 1,800 秒（`$W/index.json` 的 `elapsed`，或 `index-warmup.json` 的 `elapsed`），而且輸出裡沒有說略過或讀不了任何語料檔（評分者讀 `$W/index.txt`；工具若列出讀到的檔數，應為 55 或「50 + 5」）。PDF 讀不讀得到真正的內容，由 L2-2 的兩題 PDF 題決定。

做完後直接快照沙盒 A 的檔案系統，進沙盒 B（沙盒 A 不做 egress 量測）。

### L2-2 封鎖網路後作答

> [L2] With egress blocked after setup (egress check passes), each of 5 frozen questions is answered within 3 minutes; at least 4 of 5 answers contain the exact token, and both PDF-only questions pass

用到：`questions.json`、`tools/pty_drive.py`、`egress/egress.py`、`check_answers.py`。

做法（沙盒 B，用 A 的快照開機、網路封鎖，root 執行 egress 的 start/stop）：

```sh
T0=$(python3 -c 'import time; print(time.time())')
sudo python3 $F/egress/egress.py start --out $W/egress --mode sink
python3 $F/tools/run_steps.py --steps $W/steps-services.txt --out $W/services   # 只有答案要背景服務時：答案自己的啟動指令
# 每一題各跑一次，新的程序、各自計時（id 是 q17-1 … q17-5，問題文字取自 questions.json）
python3 $F/tools/pty_drive.py --out $W/answers/q17-1 --timeout 180 -- \
  python3 $F/egress/egress.py trace --out $W/egress --label q17-1 -- <答案的提問指令，問題填 q17-1 的原文>
...
T1=$(python3 -c 'import time; print(time.time())')
sudo python3 $F/egress/egress.py stop --out $W/egress
python3 $F/egress/egress.py report --out $W/egress --since $T0 --until $T1 --save $W/answers/egress-report.json
python3 $F/check_answers.py --run-dir $W/answers --egress-report $W/answers/egress-report.json
```

- 一題一次、互不續接；問題文字**原字照貼**。答案的工具只有互動模式時：`--send "<問題>" --send-after '<工具的提示字元 regex>' --done '<回答結束的標記 regex>' --idle 20`，這時作答時間取最後一次輸出的時間（`last_output_t`），不含等待與結束鍵。
- 「answered within 3 minutes」：5 題**每一題**都要在 180 秒內答完（被時間上限中止的那題算沒答）。
- 「contain the exact token」：作答輸出（去掉終端機控制碼後）含有一模一樣的 token 字串，大小寫、連字號都要相同。
- egress check：見第 1 節；時段是從 egress start 到最後一題結束。

通過（`check_answers.py` 的 `L2-2`）：5 題都在時限內作答、至少 4 題含 token、兩題 PDF 題（`q17-4`、`q17-5`）都含 token，**而且** egress report 是 `pass`。egress report 是 `incomplete` 時，L2-2 記 `pending`，修好量測後重做提問。

### L2-3 引用出處

> [L2] For at least 4 of 5 answers, the cited source names the file that contains the fact

用到：L2-2 的同一批作答紀錄、`check_answers.py`。

- 「names the file」：作答輸出裡出現出處檔的檔名（有沒有副檔名、前面帶什麼路徑都可以，不分大小寫）。只寫筆記標題、不寫檔名，不算。
- 每題列出輸出裡提到的所有語料檔名。出處檔在裡面、而且提到的語料檔不超過 5 個 → `pass`；出處檔在裡面但提到超過 5 個（例如把整個資料夾列出來）→ `manual`：評分者讀紀錄，判斷答案標為「出處」的檔是否包含出處檔（進度訊息、載入清單不算引用），判定後用 `--manual-pass q17-N` 記入；其餘 → `fail`。
- 與 token 對不對分開計：答錯但引用對，仍算引用對。

通過（`check_answers.py` 的 `L2-3`）：至少 4 題 `pass`。

### L2-4 全程不設雲端金鑰

> [L2] No cloud API key is set at any step

用到：第 1 節的金鑰規則；`run_steps.py`、`pty_drive.py` 的紀錄。

做法：每個沙盒一開始記一次環境變數名稱 `env | cut -d= -f1 | sort > $W/env-names-<A或B>.txt`（只記名稱，不記值），確認沒有任何金鑰類變數。評分者讀步驟檔與紀錄。

通過：沒有任何步驟要求向雲端服務申請金鑰、登入取得金鑰，或把金鑰設成環境變數／寫進設定檔；整個流程在沙盒裡沒有任何真金鑰的情況下完成。答案若要求設定一個「任何值都可以」的本機金鑰值（第 1 節），不算雲端金鑰。只要有一步要求雲端金鑰，就不過（而且通常 L2-2 也會失敗）。

## 3. 自我測試

```sh
sh selftest.sh        # 離線；不需要 root；約 1 分鐘
```

測試內容：語料可重產生且雜湊一致；`check_answers.py` 在全對、4/5、列出太多檔、逾時四種情況的判定；egress 三層的解析與 DNS 伺服器（高埠、不改 resolv.conf）；`pty_drive.py`、`run_steps.py` 的行為。寫 fixture 時已在 macOS 用 Python 3.9 與 3.12 跑過，全部通過。

## 4. 還沒決定的事

見 `needs.json`（dev image 內容與使用者、strace）與 `calibration.md`（封鎖網路與 egress 量測方式）。另外兩條規則要念誠確認：引用「超過 5 個檔算 manual」的門檻，以及容器沒有 systemd 時手動啟動服務的做法。
