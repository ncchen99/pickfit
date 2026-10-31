# q09 測試資料：存在 repo 裡的任務清單

題目與檢查項目見 [../../questions.yaml](../../questions.yaml) 的 q09；評分規則見 [../../README.md](../../README.md) 第 5 節。本資料夾放 [L2] 五個項目要用的測試資料與檢查腳本。

全部是自己寫的合成資料，不含任何工具名稱或預期答案；檢查腳本不假設任何工具的欄位名稱或檔案格式。腳本只用 POSIX sh、git 與 Python 3.8 以上的標準函式庫；`dev_shell.sh`、`setup_user.sh` 是給 Linux dev image 用的（要 `su`、`getent`、`useradd`）。

## 檔案

| 檔案 | 用途 |
|---|---|
| `titles.json`、`titles.sh` | 三個任務標題（同一份內容，一個給 Python、一個給 shell）：T1 `Add CI workflow for unit tests`、T2 `修正登入畫面的錯誤訊息，補上測試`（繁體中文）、T3 `Write release notes draft`。依 T1、T2、T3 的順序建立；L2-2 關 T1，L2-4 再關 T3；T2 一直開著，所以每次列表都要出現 |
| `make_repo.sh` | 新的 git repo：一個 README、一個 commit（固定身分與時間，commit id 一定是 `56cc386237ac98db667679cfb869d19e4359950a`） |
| `setup_user.sh` | 在 dev image 裡建非 root 使用者 `dev`（要不要給 sudo 見 `needs.json`） |
| `dev_shell.sh` | 以 `dev` 身分、在互動式 login bash 裡跑一個指令（等同開新終端機）；設 `EGRESS_LOG=資料夾/名稱.log` 時整段用共用的 `../_shared/egress.py run` 執行 |
| `inspect_listing.py` | 讀 JSON 列表，判定 L2-2；`--compare` 判定 L2-3 |
| `check_repo_data.py` | L2-4：`text` 檢查 commit 進去的資料是 UTF-8 文字，`diffsize` 算關掉一個任務改了幾行（用共用的 `../_shared/git_diff_lines.py`） |
| `../_shared/egress.py` | L2-5：沒有對外連線的檢查（各題共用，[`_shared/README.md`](../_shared/README.md) 第 1 節） |
| `selftest.py` | 檢查腳本的自我測試（macOS、Linux 都能跑） |
| `calibration.md` | 開跑前要確認並記錄的事 |
| `needs.json` | 要念誠決定的外部項目（dev image 內容、`dev` 有沒有 sudo、strace） |

## 共同準備

1. **dev image**：`ubuntu:24.04` 加上 `needs.json` 決定的套件，記下 digest。兩組用同一個 image。
2. 以 root：把本資料夾複製到 `/fixtures/q09/`、`_shared` 複製到 `/fixtures/_shared/`，`sh /fixtures/q09/setup_user.sh`（建 `dev`、`/work` 給 `dev`）。
3. 之後答案的所有指令都以 `dev` 身分執行，用 `sh /fixtures/q09/dev_shell.sh [-C 目錄] '<指令>'`。它開的是互動式 login bash，`~/.profile`、`~/.bashrc` 都會載入，等同使用者開一個新的終端機。
4. **只對當下 shell 有效的設定**：答案的安裝步驟裡只影響當下終端機的行（`export ...`、`source ...`、`eval "$(...)"`），照原樣抄進 `/work/prelude.sh`，之後每個指令用 `Q09_PRELUDE=/work/prelude.sh` 先載入，視同使用者還在安裝時那個終端機。這不算補步驟；抄錄內容記在檢查紀錄。
5. 每個指令的完整輸出與 exit code 都存進檢查紀錄。

## 逐項說明

### L2-1

> [L2] The install steps succeed verbatim in the dev image as a non-root user

- **用到**：dev image、`setup_user.sh`、`dev_shell.sh`。
- **做法**：答案的安裝指令依順序、一字不改抄進 `/work/install.txt`（一行一個指令，原本跨行的照原樣），然後
  ```sh
  sh /fixtures/q09/dev_shell.sh 'set -ex; . /work/install.txt'
  ```
  在同一個 shell 裡依序執行；遇到第一個失敗的指令就停，exit code 就是那個指令的。安裝程式停下來問問題時，評分者照第 5 節「接受安裝程式預設值」直接按 Enter，並記錄。安裝階段需要網路，不做 egress 檢查。
- **「verbatim」的意思**：指令內容不改，只允許第 5 節列的調整：填入版本號與佔位字、接受預設值。Ubuntu 擋下裸 `pip install`（externally-managed-environment）時可以改在 venv 裡跑以便繼續後面的檢查，記 `needed_venv`，但本項不過。不可以加 `sudo`、改路徑、補漏掉的步驟、換安裝方式。
- **過**：每個安裝指令 exit 0；之後在新的 shell（`dev_shell.sh`，含 prelude）裡，答案說的工具指令找得到（`command -v <工具指令>` 成功）。
- **不過**：任一指令失敗、需要 root 而答案沒寫 `sudo`（或 `dev` 沒有 sudo 時寫了 `sudo`，見 `needs.json` 的決定）、新 shell 找不到工具。

### L2-2

> [L2] In a fresh git repo, using only commands from the answer or the tool's docs: create 3 tasks (one titled in Traditional Chinese) and close 1. The JSON listing parses with jq and identifies exactly the 2 open tasks (either only open tasks are listed, or a status field marks the closed one), and the Chinese title round-trips intact

- **用到**：`make_repo.sh`、`titles.sh`、`inspect_listing.py`、`dev_shell.sh`（含 egress 紀錄）。
- **做法**（以 root 下指令，實際以 `dev` 執行）：
  ```sh
  mkdir -p /work/out /work/egress && chown dev /work/out /work/egress
  touch /tmp/q09-before-tasks                      # L2-3 用來找家目錄裡新寫的檔
  sh /fixtures/q09/dev_shell.sh 'sh /fixtures/q09/make_repo.sh /work/proj'
  # 以下每個指令都用：EGRESS_LOG=/work/egress/NN-名稱.log Q09_PRELUDE=/work/prelude.sh \
  #   sh /fixtures/q09/dev_shell.sh -C /work/proj '. /fixtures/q09/titles.sh; <工具指令>'
  #  1. 答案或文件要求的初始化指令（若有）
  #  2. 新增 "$T1"、"$T2"、"$T3"（依此順序）
  #  3. 關閉 T1（用工具印出的 id，或文件說的指定方式）
  #  4. JSON 列表：<列表指令> > /work/out/list1.json
  jq . /work/out/list1.json > /dev/null && echo jq-ok
  python3 /fixtures/q09/inspect_listing.py /work/out/list1.json
  ```
  指令來源只限答案與該工具的官方文件（README、`--help`、官方文件網站，以安裝的那個版本為準）；用到的每一行都記下來源。標題一律用 `titles.sh` 的變數傳入（等於填佔位字）。答案沒有某個操作、文件也查不到時，這項不過。
- **判定**（`inspect_listing.py`，不假設欄位名稱）：
  - 以標題找每個任務的紀錄（整個字串相等或包含在較長的字串裡都算）。
  - 只列出 T2、T3 →「只列開著的」；三個都列出時，要有欄位或分組把 T1 和 T2、T3 分開（欄位名或值是狀態字詞，例如 status、state、done、closed、completed；只在 T1 有值的時間欄位；`closed` 之類的分組名稱）。
  - T2 的繁體中文標題要原字出現（JSON 解碼後逐字相同；`\u` 跳脫可以），整份沒有 U+FFFD。
- **過**：`jq` exit 0，`inspect_listing.py` 印 `verdict: PASS`，而且每個工具指令 exit 0。
- **`verdict: REVIEW`**：腳本判斷不了，由評分者讀 JSON 決定，規則是：(a) 旁邊多出的項目只要有一個是開著的任務就不過；(b) 三個都列出但腳本沒認出狀態欄位時，只有工具文件說明的狀態欄位或分組確實把 T1 標成關閉、T2 和 T3 標成未關閉才過。判定與理由寫進檢查紀錄。
- **不過**：`jq` 解析失敗、少了 T2 或 T3、T2 標題被改、關閉的 T1 無法和其他兩個分開、任一指令失敗。

### L2-3

> [L2] After committing, a fresh clone with no other state (no home-directory data, no untracked files) lists the same tasks with the same statuses, so the committed text files are the source of truth

- **用到**：`dev_shell.sh`、`inspect_listing.py --compare`。
- **做法**：
  ```sh
  # 1. commit：工具自己會 commit 時，工作目錄乾淨就不用再 commit
  EGRESS_LOG=/work/egress/20-commit.log sh /fixtures/q09/dev_shell.sh -C /work/proj \
    'git add -A && git commit -q -m "Add tasks"'
  # 2. 工具寫在 repo 以外的檔（家目錄、/tmp）
  find /home/dev /tmp /var/tmp -newer /tmp/q09-before-tasks -type f \
    ! -path '/tmp/q09-*' > /work/out/state-outside-repo.txt
  # 3. 把清單裡 /home/dev 底下的檔暫時移到 /root/q09-stash/（保留路徑），做完再搬回
  # 4. 乾淨的 clone：空的 HOME、清掉 XDG_*，只有 git clone 出來的檔
  mkdir /tmp/q09-emptyhome && chown dev /tmp/q09-emptyhome
  EGRESS_LOG=/work/egress/21-clone.log sh /fixtures/q09/dev_shell.sh -C /work \
    'git clone -q file:///work/proj /work/clone && cd /work/clone &&
     git config user.name "Fixture Author" && git config user.email fixture@example.invalid &&
     test -z "$(git status --porcelain --ignored)" && echo clean'
  EGRESS_LOG=/work/egress/22-list-clone.log Q09_PRELUDE=/work/prelude.sh sh /fixtures/q09/dev_shell.sh -C /work/clone \
    'export HOME=/tmp/q09-emptyhome; unset XDG_CONFIG_HOME XDG_DATA_HOME XDG_STATE_HOME XDG_CACHE_HOME;
     <與 L2-2 相同的列表指令> > /work/out/list2.json'
  python3 /fixtures/q09/inspect_listing.py --compare /work/out/list1.json /work/out/list2.json
  ```
  - 用 `file://` clone，才會走一般的傳輸協定，只帶分支與 tag；工具若把資料存在自訂 ref、git notes 或 `.git/` 裡，這裡就看得出來。
  - clone 裡設的 `user.name`／`user.email` 是 repo 自己的 git 設定，不是任務資料，也不在家目錄；統一設定，避免工具只因沒有 git 身分而出錯。
  - `HOME` 換成空目錄是在 shell 載入完設定之後，所以工具指令還找得到，但看不到原本家目錄的資料；第 3 步再把工具寫在家目錄的檔搬開，防止工具不看 `HOME` 直接讀密碼檔裡的家目錄。
  - 工具文件明寫「clone 之後要先跑」的指令（例如從 repo 檔案重建索引）可以照文件跑一次並記錄；它也要過 L2-5。
- **過**：clone 裡沒有未追蹤檔（印出 `clean`），列表指令 exit 0，`--compare` 印 `verdict: PASS`（同樣的任務、每個任務的狀態證據相同；時間欄位只比有沒有值）。
- **不過**：clone 列不出任務、任務或狀態不同、需要家目錄或 repo 外的資料才列得出來。

### L2-4

> [L2] The committed task data is UTF-8 text, and closing one more task changes at most 5 lines in git diff

- **用到**：`check_repo_data.py`。
- **做法**（第 3 步搬開的檔先搬回來，在原本的 `/work/proj` 做）：
  ```sh
  python3 /fixtures/q09/check_repo_data.py text /work/proj 56cc386237ac98db667679cfb869d19e4359950a
  BEFORE=$(git -C /work/proj rev-parse HEAD)
  EGRESS_LOG=/work/egress/30-close-t3.log Q09_PRELUDE=/work/prelude.sh sh /fixtures/q09/dev_shell.sh -C /work/proj \
    '. /fixtures/q09/titles.sh; <關閉 T3 的指令>'
  python3 /fixtures/q09/check_repo_data.py diffsize /work/proj "$BEFORE"
  ```
- **判定**：
  - `text`：從固定的第一個 commit 到 HEAD 之間變動的每個檔，在 HEAD 的內容要能以 UTF-8 嚴格解碼、沒有 NUL、沒有 tab／換行／CR／form feed 以外的控制字元，git 也不把它當 binary。沒有任何檔變動（任務資料沒進 repo）算不過。
  - `diffsize`：共用的行數定義（[`_shared/README.md`](../_shared/README.md) 第 4 節）：`git add -A` 後看 `git diff --cached -M $BEFORE`，每個 hunk 取刪掉與加上的行數較大者，加總。原地改一行算 1，搬檔（rename）只算內容變動。工具自己 commit 也算在內（比的是關閉前的 commit）。
- **過**：`L2-4 text: PASS` 而且 `L2-4 diff: PASS`（合計 ≤ 5、沒有 binary、確實有變動）。
- **不過**：任一不成立。

### L2-5

> [L2] Egress check passes for all commands

- **用到**：`dev_shell.sh`（`EGRESS_LOG`）、`$SHARED/egress.py`。
- **「egress check」的意思**：L2-2～L2-4 的每個指令（工具的初始化、新增、關閉、列表，clone 裡的列表，以及評分者的 git 指令）都用 `EGRESS_LOG=/work/egress/<名稱>.log` 經 `dev_shell.sh` 在共用的 `egress.py run` 底下執行（留在背景的程序也一直記錄到 `stop`）。什麼算一次對外連線嘗試（不論成功或失敗）見 [`_shared/README.md`](../_shared/README.md) 第 1 節。安裝步驟（L2-1）需要網路，不在範圍內。
- **做法**：
  ```sh
  python3 /fixtures/_shared/egress.py stop --out /work/egress
  python3 /fixtures/_shared/egress.py report --out /work/egress --json /work/out/egress.json
  ```
- **過**：印出 `egress: PASS`（沒有任何嘗試，而且每一步都有 strace 紀錄）。
- **不過**：任何一次 egress，例如檢查更新、送使用統計、自動 push。
- **strace 不能用時**：照 `_shared/README.md` 第 1 節，這項記「無法檢查」，請念誠決定替代方式；不能只靠擋網路後指令仍成功判過。

## 開跑前自我測試

```sh
python3 selftest.py              # 檢查腳本本身（macOS、Linux 都可以）
python3 ../_shared/egress.py selftest   # 在 dev image 裡以 root 跑（_shared/calibration.md 步驟 1，各題共用一次）
```

結果記到 `calibration.md`。

## 中立性

- 三個標題是自己寫的一般開發任務，避開常見純文字格式的語法字元（ASCII 的 `#`、`@`、`+`、`:`、`[ ]`、引號、行首 `-`），不偏向任何格式。
- 檢查腳本只認 JSON 結構與狀態字詞，不認任何工具的欄位名、檔名或目錄。`selftest.py` 用的「替身工具」是測試腳本用的幾行 shell，不模仿任何現有工具。
