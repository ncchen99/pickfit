# q11 測試資料：Mac 上離線跑繁體中文模型

題目與檢查項目見 [../../questions.yaml](../../questions.yaml) 的 q11；評分規則見 [../../README.md](../../README.md) 第 5 節。q11 只能在 Mac 實跑（`sandbox: mac_only`），由念誠親手在另開的 macOS 帳號執行；共用的帳號準備、斷網、量測與移除清單在 [mac/RUNBOOK.md](mac/RUNBOOK.md)（q12 也用）。

全部是自己寫的合成資料與腳本，不含任何工具、模型名稱或預期答案。腳本只用 POSIX sh 與 Python 3.8 以上的標準函式庫（macOS 內建的 `/usr/bin/python3` 就能跑）。

## 檔案

| 檔案 | 用途 |
|---|---|
| `prompts/P1.txt`～`P5.txt` | 五個凍結的題目，逐字取自 questions.yaml（`selftest.py` 會核對） |
| `score_replies.py` | L2-3 連貫性（字數、重複）、L2-4 字體、L2-5 用語；產生盲評請求；三次取兩次的彙整 |
| `opencc_scorer.py` | 第 5 節的共用 OpenCC 計分（逐字判斷），讀固定版本 OpenCC 的字元表；q15 也該用同一支 |
| `judge_rubric.md` | L2-3「是否回答了題目」的固定盲評說明 |
| `samples/` | 自己寫的假回覆（繁體、簡體、繁體字但大陸用語、重複、答非所問），自我測試與校準用 |
| `selftest_dict/` | 自我測試用的手寫小字元表（**不是** OpenCC 資料，正式計分不能用） |
| `selftest.py` | 自我測試；加 `--mac` 會在 macOS 上一併測記憶體量測 |
| `mac/` | Mac 共用腳本與 [RUNBOOK.md](mac/RUNBOOK.md) |
| `calibration.md` | 開跑前要做的校準與固定版本（待填） |
| `needs.json` | 要從外部取得、要念誠決定的東西 |

## 共同準備

照 [mac/RUNBOOK.md](mac/RUNBOOK.md) 第 1～3 步：開新的測試帳號（每題每組一個）、拍 before 快照、登入測試帳號、`preflight.sh` 要 PASS、在 `script -q` 紀錄的 shell 裡照答案的步驟做。以下 `F=/Users/Shared/eval-fixtures`，`R=/Users/Shared/eval-runs/<題號-組別>`。

**取樣設定**（第 5 節「能固定 temperature 或 seed 就固定；不能就跑 3 次、2 次過算過」）：依序選第一個做得到的，兩組用同一規則，寫進檢查紀錄：

1. 答案或工具文件有設定 seed 的方式：加上 seed `0`，temperature 照答案（答案沒寫就用預設值）。
2. 沒有 seed、但能設 temperature：設成 `0`。
3. 都不能：五個題目整組跑 3 次（`replies/run1`、`run2`、`run3`），每個檢查項目 3 次裡過 2 次算過。

（這個優先順序是本資料夾的建議，開跑前請念誠在 `calibration.md` 確認。）

**回覆怎麼存**：每個題目在一個新的對話裡問（重新執行答案的對話或執行指令；不沿用上一題的對話）。題目從 `prompts/Pn.txt` 複製貼上（`pbcopy < $F/q11/prompts/P1.txt`），一字不改。模型印在終端機的回覆原樣複製到 `$R/replies/run1/Pn.txt`（UTF-8）：只去掉執行程式自己的介面文字（提示字元、題目的回顯、速度與 token 統計），模型寫的每個字都保留，包括顯示在終端機上的思考過程。整段終端機紀錄另外保存在 `script` 的 transcript 裡。

## 逐項說明

### L2-1

> [L2] On a 16 GB Apple silicon Mac, in a fresh macOS user with empty model caches, the steps run from the terminal; the summed peak memory footprint of every process the steps start, including any background server (`/usr/bin/time -l` or `footprint`), stays under 12 GB

- **用到**：`mac/preflight.sh`、`mac/footprint_watch.py`、`mac/RUNBOOK.md`。
- **做法**：
  1. 新帳號、`preflight.sh` PASS：家目錄只有 macOS 建立的東西、沒有 `~/.cache`、沒有 token／快取位置／離線相關的環境變數（`HF_TOKEN` 等都沒設）、讀得到的地方沒有 ≥100 MB 的模型檔。
  2. 在 `script -q` 的 shell 裡 `echo $$` 記下 pid。另開一個終端機視窗執行（要在答案的第一步之前開始）：
     ```sh
     sudo /usr/bin/python3 $F/q11/mac/footprint_watch.py --uid $(id -u) --shell-pid <pid> --out $R/footprint
     ```
  3. 照答案做完全部步驟，包括 L2-2 的五個題目（三次的話三次都做完），再 `touch $R/footprint/stop`。
- **量測方式**：`footprint_watch.py` 讀的是 `/usr/bin/time -l` 印出的「peak memory footprint」同一個核心計數（`ri_lifetime_max_phys_footprint`），對象是量測開始後才出現、而且是那個 shell 的子孫，或屬於測試帳號且不是從系統路徑執行的程式（涵蓋 launchd 或背景常駐的伺服器）。每 0.5 秒取樣一次，把「當下還活著的程式各自的峰值」加總，取整段時間的最大值。先後執行的程式不相加；同時存在的伺服器與用戶端會相加。上限是 12 GiB（12 × 2³⁰ bytes）。
- **過**：印出 `PASS`，而且評分者看過程式清單（`footprint.json` 的 `processes`）。清單裡有明顯不是步驟啟動的程式（例如剛好啟動的系統代理程式）時，用 `footprint_watch.py recompute $R/footprint/footprint.json --exclude-pid <pid>` 重算，排除哪個、為什麼都要記錄。
- **「the steps run from the terminal」**：每一步都是在終端機輸入的指令，問答也在終端機進行。步驟要求打開 GUI app、瀏覽器或系統設定（評分者自己的斷網操作除外）就不過。
- **不過**：上限超過、步驟需要 GUI、帳號不是新的。
- **硬體**：念誠的 Mac 是 24 GiB（不是 16 GB），本項以量到的 footprint 判定，報告寫明實際硬體（見 `needs.json`）。

### L2-2

> [L2] With all network interfaces off, each of 5 frozen prompts gets a reply in the terminal. P1: … P5: …

- **用到**：`prompts/`、`mac/offline.sh`。
- **做法**：
  1. 連網時把模型準備好：答案有下載步驟就照做；答案的流程是「第一次執行時才下載」，就在連網時執行一次答案的第一次執行指令，等到可以輸入時就離開，不送任何題目（記錄這件事）。
  2. `sudo sh $F/q11/mac/offline.sh off $R/net-state.txt`，要印出 `offline check: PASS`。
  3. 依前面的規則問 P1～P5，存回覆。
  4. 五題問完再跑一次 `sh $F/q11/mac/offline.sh check`，仍要 PASS；然後 `offline.sh on`。
- **「all network interfaces off」**：見 RUNBOOK 第 4 步的判準（所有網路服務停用、Wi-Fi 關閉、沒有預設路由、除了 loopback 沒有位址、HTTPS 測試失敗、沒有 VM bridge）。
- **過**：斷網檢查前後都 PASS，五題都在終端機得到非空白的回覆。
- **不過**：任何一題沒有回覆、報錯、卡住超過 10 分鐘，或需要網路。

### L2-3

> [L2] Coherence: the replies to P1, P2, P3 and P5 each contain at least 50 CJK characters, repeat no 10-character substring more than 3 times, and are judged by a blind grader as answering the prompt

- **用到**：`score_replies.py`、`judge_rubric.md`。
- **自動部分**：
  - CJK 字＝漢字（CJK Unified Ideographs 與各擴充區、相容表意文字），標點不算，每題 ≥ 50。
  - 重複：去掉所有空白後，任何含至少一個漢字的 10 字子字串，不重疊出現次數不超過 3（`str.count` 的算法）。只含符號的子字串（例如表格分隔線）不算。
- **盲評**：
  ```sh
  python3 $F/q11/score_replies.py --write-judge-requests $R/judge-requests.jsonl $R/replies/run1
  ```
  每行是一個請求（system＝`judge_rubric.md` 的評分說明，user＝題目＋回覆，不含組別或工具名稱）。把 `PINNED_JUDGE_MODEL` 換成 `calibration.md` 固定的模型 ID，temperature 0 送出；每個回覆的 `answers_prompt` 寫進 `$R/replies/run1/judge.json`（`{"P1": true, ...}`），原始回應存 `judge-raw.jsonl`。
- **過**：四題都達到字數、沒有過度重複、盲評為 true。
- **不過**：任一題不成立；沒有盲評結果時不算過。

### L2-4

> [L2] Script: the shared OpenCC scorer gives a Traditional ratio of at least 0.95 over the five replies (at least 30 script-differing characters)

- **用到**：`opencc_scorer.py`（由 `score_replies.py` 呼叫）、固定版本 OpenCC 的 `STCharacters.txt` 與 `TSCharacters.txt`（`needs.json`）。
- **判定方式**（第 5 節「逐字判斷」）：五個回覆接在一起逐字看。一個字是 STCharacters 的鍵、而且不在它自己的繁體候選裡，算「只屬簡體」；是 TSCharacters 的鍵、而且不在它自己的簡體候選裡，算「只屬繁體」；兩者皆是或皆非（兩種字體都通用的字，例如 OpenCC 把它自己列為候選的字）不計。繁體比例＝只屬繁體 ÷（只屬繁體＋只屬簡體）；「繁簡不同字」＝兩者之和。
- **做法**：`python3 $F/q11/score_replies.py --dict-dir <OpenCC 字元表資料夾> $R/replies/run1`（三次時接三個資料夾）。
- **過**：比例 ≥ 0.95 且繁簡不同字 ≥ 30。
- **不過**：比例不足，或不同字少於 30（回覆太短或幾乎沒有能分辨字體的字也不過）。

### L2-5

> [L2] Vocabulary: the P4 reply gives at least 6 of 軟體, 影片, 網路, 程式, 資訊, 預設, 檔案, 記憶體 on the matching lines and none of 软件, 軟件, 视频, 視頻, 网络, 網絡, 程序, 信息, 默认, 默認, 内存, 內存, or 文件 for 'file'. The P5 reply contains at least 2 of those Taiwan terms and none of 软件, 軟件, 视频, 視頻, 网络, 網絡, 默认, 默認, 内存, 內存

- **用到**：`score_replies.py`。
- **「matching lines」**：每個英文詞對到回覆裡第一個含有該英文詞的行（不分大小寫、整個詞）；回覆完全沒有英文詞、但剛好有 8 行含漢字時，依順序對應；其他情況只算找得到的詞，評分者可以人工對應並記錄理由。
- **P4**：8 個台灣用語中至少 6 個出現在對應的行；整個 P4 回覆不能出現列出的 12 個詞；「file」那一行不能有「文件」（找不到 file 那一行時，整個回覆都不能有「文件」）。比對是逐字的子字串比對，不做繁簡轉換。
- **P5**：整段至少出現 2 個台灣用語，不能出現列出的 10 個詞（P5 沒有禁止 程序、信息、文件）。
- **過**：P4 與 P5 都成立。

## 開跑前自我測試

```sh
python3 selftest.py          # 任何機器
python3 selftest.py --mac    # 在要實跑的 Mac 上，多測記憶體量測
```

## 中立性

- 題目是凍結的原文；假回覆、小字元表都是自己寫的，只用來測計分邏輯。
- 量測、斷網、移除清單只看程式、路徑、連線與檔案，不認任何工具或模型；`preflight.sh` 找模型檔只看副檔名與大小。
