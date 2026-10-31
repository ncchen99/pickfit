# q10 測試資料：中文長段落的字元級 diff

題目與檢查項目見 [../../questions.yaml](../../questions.yaml) 的 q10；評分規則見 [../../README.md](../../README.md) 第 5 節。本資料夾只放 [L2] 項目要用的測試資料與腳本；[L3]（主要答案是否說「不用另外裝 diff 工具」）只讀答案，不用測試資料。

所有檔案都是自己寫的合成資料，不含任何工具名稱或預期答案。腳本只用 POSIX sh、git 與 Python 3.8 以上的標準函式庫。

## 檔案

| 檔案 | 用途 |
|---|---|
| `doc_old.md`、`doc_new.md` | 一行約 200 字（201 個漢字、216 字含標點）的繁體中文段落，前面一行標題。兩版只差一個字：第 104 個字「己」→「已」（`己經` 改成 `已經`）。這兩個字的 UTF-8 前兩個 byte 相同（`e5 b7 b1` / `e5 b7 b2`），以 byte 為單位比對就會切壞字；兩個字在檔案裡各只出現一次 |
| `expected.json` | 改動的位置、舊字、新字、前後各 2 字的鄰近字串（`果你己經照` / `果你已經照`）、span 上限 3 字 |
| `make_repo.sh` | 建出凍結的測試 repo（固定身分與時間，commit id 每次相同） |
| `capture.sh` | 在 pseudo-terminal 裡照檢查項目的寫法執行一個指令，存下原始 byte |
| `extract_spans.py` | 凍結的 span 擷取腳本：解析 ANSI 顏色或 `[-..-]`／`{+..+}` 標記，判定 L2-2、L2-3、L2-5，並用 `--same-as` 判定 L2-4 |
| `selftest.py` | 測試資料與擷取腳本的自我測試（開跑前跑一次） |
| `calibration.md` | 開跑前要在 base image 確認並記錄的事 |
| `needs.json` | 需要從外部取得、要念誠決定的東西（base image） |

## 共同準備

1. **base image**：`ubuntu:24.04`（記下 digest）＋ `apt-get install -y --no-install-recommends git`，不裝別的。以 image 預設的 root 執行，`HOME=/root`，沒有 `~/.gitconfig`。`git config --list --show-origin` 只能看到測試 repo 自己的 `user.name`／`user.email`。
2. 把本資料夾複製到 sandbox 的 `/fixtures/q10/`。
3. 建 repo：`sh /fixtures/q10/make_repo.sh /work/repo`。預設狀態是第一個 commit 有舊段落，新段落是**未 stage 的修改**，也就是使用者打 `git diff` 會看到的狀態。答案的指令比的是別的狀態時，評分者準備對應的狀態（這是準備測試資料，不算改答案的步驟）：
   - 答案用 `git diff --cached`／`--staged`：`make_repo.sh /work/repo --staged`
   - 答案比兩個 commit（`git show`、`git log -p`、`git diff HEAD~1` 等）：`make_repo.sh /work/repo --committed`
   - 第一個 commit 一律是 `cabbea1e89c5dce8e3bd050f0be2f45e23e438d3`；`--committed` 的第二個是 `a0d1e9729c91e5d4213c68256145ebff482a5547`。不同就表示測試資料被改過，停下來查。
4. **擷取輸出**：`sh /fixtures/q10/capture.sh /work/repo /work/out1.raw '<答案的 diff 指令>'`。它做的事就是檢查項目寫的 `script -qc '<cmd>' /dev/null`，再加上：
   - `LANG=C.UTF-8`、`GIT_PAGER=cat`，並清掉所有 `LC_*`、`LANGUAGE`；
   - `TERM=xterm-256color`。git 在 `TERM` 沒設或是 `dumb` 時當作終端機不能顯示顏色；真的終端機一定有 `TERM`，所以要設。
   - 不要把 stdin 導向 `/dev/null`（有些 `script` 版本會把 EOF 當成 `^D` 送進去；擷取腳本會把 `^D` 加退格去掉，但沒必要製造）。
5. 擷取腳本在評分者自己的機器上跑（base image 沒有 Python）：把 `out1.raw` 複製出來，`python3 extract_spans.py out1.raw`。要完整紀錄加 `--json`，存進檢查紀錄。

答案給了好幾個做法時，評**主要答案**的那一個（第 5 節）。答案同時給一次性的指令與永久設定時，L2-1～L2-3、L2-5 用一次性的指令，L2-4 用永久設定；只給永久設定時，先套用設定，再用答案說的日常指令做全部檢查。

## 逐項說明

### L2-1

> [L2] The proposed command or config uses only git and runs in the base image (git only) with LANG=C.UTF-8, under a pseudo-terminal (`script -qc '<cmd>' /dev/null`) with GIT_PAGER=cat

- **用到**：base image、`make_repo.sh`、`capture.sh`。
- **做法**：答案的設定指令（`git config ...`、建 `.gitattributes` 等）照原樣在 `/work/repo` 執行，環境同第 4 步；接著用 `capture.sh` 跑 diff 指令。
- **過**：下列都成立。
  1. 讀答案的指令與設定：只叫 git（含 git 子指令、選項、答案自己定義的 git alias；`cd` 等 shell 內建指令可以）。用 git 設定去叫非 git 的程式也算違反，例如 `core.pager`、`pager.<cmd>`、`interactive.diffFilter`、`diff.external`、`diff.<driver>.command`、`diff.<driver>.textconv` 指向另外安裝的程式。（檢查時 `GIT_PAGER=cat` 會蓋掉 pager 設定；但答案要靠別的 pager 或過濾程式才能標出字元時，這項不過。）
  2. 每個設定指令 exit 0；`capture.sh` 的輸出不是空的，擷取腳本印出 `L2-1 output check: ok`（輸出裡沒有 `fatal:`、`error:`、`command not found`、`unknown option`、`usage: git` 這類字）。印出 `PROBLEM` 時，評分者看原始輸出確認是不是真的錯誤。
- **不過**：叫了 git 以外的程式、指令出錯、base image 裡沒有答案要的東西。

### L2-2

> [L2] Frozen fixture: a repo with a single-line paragraph of about 200 Traditional Chinese characters in which exactly one character is substituted. A frozen span-extraction script (parsing ANSI color runs or [-..-] and {+..+} markers) finds that the removed and added spans are each at most 3 characters and contain the changed character. Whole-line marking fails; default whitespace word-diff fails

- **用到**：`doc_old.md`、`doc_new.md`、`expected.json`、`make_repo.sh`、`capture.sh`、`extract_spans.py`。
- **擷取規則**（`extract_spans.py`）：
  - 去掉 `\r`、處理退格、略過 diff 的標頭行（`diff --git`、`index`、`---`、`+++`、`@@` 等）。
  - 有 `[-..-]`、`{+..+}` 標記時用標記（git 也會替標記上色，所以標記優先）；沒有標記時用顏色。
  - 顏色：紅色＝刪除、綠色＝新增。支援基本 8 色、亮色、256 色、24-bit（`;` 與 `:` 兩種寫法），前景、背景、反白都算。同一行裡同時有整行上色與背景或反白強調的小段時，只算強調的小段。
  - 每個 span 去掉前後空白；整行上色時去掉行首的 `-`／`+`。字數以 Unicode code point 計。
- **過**：至少一個刪除 span 與一個新增 span；刪除 span 合計不超過 3 字且含「己」；新增 span 合計不超過 3 字且含「已」；每個 span 單獨就是合法的 UTF-8。擷取腳本印出 `L2-2 spans: PASS`。
- **不過**：上述任一不成立，包括整行標記（刪除、新增各 216 字）、以空白分詞的預設 word diff（整段當成一個字）、沒有顏色也沒有標記的輸出、機器用格式。
- **測試資料本身的驗證**：`selftest.py` 確認「整行標記」與「預設 word diff」兩種輸出都會被判不過（檢查項目要求的兩個反例）；`calibration.md` 第 2 步在 base image 的 pty 下再確認一次。

### L2-3

> [L2] The changed character and its neighbours decode as valid UTF-8, with no split or garbled byte sequences

- **用到**：同 L2-2。
- **過**（擷取腳本印出 `L2-3 UTF-8: PASS`）：
  1. 去掉跳脫序列後，每一行內容都是合法 UTF-8；
  2. 每一段同樣式的文字（顏色 run）與每個標記 span 單獨也是合法 UTF-8，也就是 span 的邊界沒有落在一個字的中間；
  3. 整個輸出沒有 U+FFFD；
  4. 把新增部分拿掉還原出的舊版含 `果你己經照`，把刪除部分拿掉還原出的新版含 `果你已經照`（改動的字與前後各 2 字完整）。
- **不過**：任一不成立。例如在非 UTF-8 locale 下以 byte 比對，會把 `e5 b7` 留在共同部分，只把 `b1`／`b2` 標成刪除與新增。

### L2-4

> [L2] If the answer suggests a persistent setting (git config, alias or .gitattributes), after applying it the everyday command gives the same character-level result

- **用到**：同 L2-2。
- **做法**：
  1. 在同一個 sandbox 照答案套用永久設定（`git config --global`、alias、`.gitattributes` 加對應的 `git config`）。`.gitattributes` 放在答案說的位置；答案說要 commit 就 commit。
  2. 「日常指令」是答案說套用設定後平常要打的指令（例如答案定義的 alias）；答案沒說時用 `git diff`。
  3. `sh capture.sh /work/repo /work/out2.raw '<日常指令>'`，再 `python3 extract_spans.py out2.raw --same-as out1.raw`。
- **過**：`out2.raw` 本身通過 L2-2、L2-3、L2-5，而且刪除與新增 span 和 `out1.raw` 完全相同（印出 `L2-4 ... PASS`）。答案只給永久設定、沒有一次性指令時，`out1.raw` 就是這次的擷取，這項跟著 L2-2、L2-3、L2-5 判。
- **不適用**：答案沒有建議任何永久設定時記 `n/a`，不算不過（檢查項目以「If」開頭）。
- **不過**：設定指令出錯、日常指令的結果不是字元級，或與一次性指令的結果不同。

### L2-5

> [L2] The output is readable in a terminal (color or inline markers), not JSON or a patch that needs another tool

- **用到**：同 L2-2。
- **過**：擷取腳本以顏色或標記找到 span（`mode` 是 `color` 或 `markers`），而且輸出不是 JSON（印出 `L2-5 readable: PASS`）。
- **不過**：輸出是 JSON；沒有顏色也沒有行內標記（例如只有整行 `-`／`+` 的 patch，或要再交給別的工具才看得懂的格式）。

## 開跑前自我測試

```sh
python3 selftest.py        # 在 macOS 或 Linux 都可以跑；有 git 時會一併跑反例
```

在 Linux（有 util-linux 的 `script`）跑時，還會經過 `capture.sh` 在真的 pty 下跑兩個反例。結果記到 `calibration.md`。

## 中立性

- 段落是自己寫的一般技術文件內容，與任何工具無關。
- 反例只用檢查項目本身點名的兩種情況（整行標記、預設 word diff）。測試資料裡沒有任何「正確做法」的指令或設定；自我測試的正例是手工組出的 byte 序列，不是任何 git 選項的輸出。
