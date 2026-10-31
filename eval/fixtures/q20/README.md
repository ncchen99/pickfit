# q20 測試資料：只會講 OpenAI API 的腳本改用本機 Ollama

這個資料夾是 [eval/README.md](../../README.md) 第 8 節要求的 q20 測試資料，只給評分者用，**不給受測 agent 看**。題目原文在 [questions.yaml](../../questions.yaml) 的 `q20`。

全部自己寫的：沒有第三方檔案、沒有 commit 任何金鑰、不含預期答案；任何答案都用同一份腳本與同一套步驟檢查。唯一寫死的外部事實是使用者**已經在用**的 Ollama 的文件預設位址（L2-1 的判準本身），在 calibration.md C3 依固定版本的文件確認。腳本只用 Python 標準函式庫（3.9 以上）或 POSIX shell；要外部取得的東西（固定版本的 Ollama、小模型、openai 套件、dev image 內容）列在 `needs.json`，**沒有下載**。

L3（主要答案是否說不用另外裝 proxy／gateway）從答案原文判斷，不用測試資料。

## 0. 檔案

| 檔案 | 用途 |
|---|---|
| `script/ask.py` | 凍結的使用者腳本：官方 openai 套件、`client = OpenAI()`、`model="gpt-4o-mini"`、問一句話、印出回答（回答是空的就以非 0 結束） |
| `check_script_diff.py` | 確認改過的腳本只動了 `OpenAI(...)` 的 `base_url`、`api_key` 與 `model=` 的值（比對語法樹，註解與排版不算） |
| `check_base_url.py` | L2-1：base_url 是否為 Ollama 文件的預設位址與 OpenAI 相容路徑 |
| `run_ask.py` | 在乾淨的環境變數下跑一次腳本（`OPENAI_*` 只留答案給的），記錄結果；`--egress-dir` 時包在共用的 `egress.py run` 裡 |
| `pins.env` | 固定版本（凍結時填） |
| `setup_pinned_ollama.sh`、`setup_user_env.sh` | 建 base image 時裝固定版本的 Ollama 與小模型、建使用者的 venv 與固定版本的 openai 套件（**要網路**，只在建 image 時用） |
| `start_ollama.sh`、`stop_ollama.sh` | 以 Ollama 自己的預設位址啟動／停止（不設 `OLLAMA_HOST`），並確認模型 digest |
| `tools/gen_dummy_key.py` | 執行時產生假的金鑰值（只在答案說「填什麼都可以」時用） |
| `tools/run_steps.py`、`tools/pty_drive.py` | 答案要另外裝東西時，把指令原字不改、依序打進同一個終端機 session |
| `../_shared/egress.py` | egress check（各題共用，[`_shared/README.md`](../_shared/README.md) 第 1 節；第 1 節寫本題怎麼用） |
| `selftest.sh`、`tests/` | 離線自我測試；設 `Q20_OPENAI_PYTHON` 時另外用真的 openai 套件對假伺服器跑端到端 |
| `needs.json`、`calibration.md` | 待決定的外部資料；開跑前校準步驟與結果欄位 |

## 1. 共用做法

### 環境

- dev image：needs.json（念誠決定）。下文假設 Ubuntu 24.04、使用者 `dev`、`F=/opt/eval-fixtures/q20`、`W=/eval-work/q20/<組別>`。
- q20 base image ＝ dev image ＋ 固定版本的 Ollama ＋ 凍結的小模型 ＋ `/opt/q20-venv`（固定版本的 openai）＋ `/home/dev/ask.py`（`script/ask.py` 的複本）。這些都是使用者**原本就有的**，不是答案要裝的。
- 兩個沙盒：**沙盒 A**（網路開）做 L2-1、L2-2；快照檔案系統；**沙盒 B** 用快照開機、封鎖網路（只留 localhost），做 L2-3。封鎖方式在 calibration.md 的 E 段校準。
- 模型名：一律用 `pins.env` 的 `FIXTURE_MODEL`（檢查項目指定「the frozen small model pulled」；答案寫的模型名視為「你已經下載的模型」的佔位字，見 open question）。答案要求先 `ollama pull` 某個模型時，不照做，記 `model_substituted`。
- 金鑰：不提供任何真的雲端金鑰。答案給了字面值（例如 `"ollama"`）就用字面值；答案只寫「任何值」時用 `python3 $F/tools/gen_dummy_key.py` 當場產生。

### 「只套用答案給的改動」

- 複製 `/home/dev/ask.py` 成 `$W/ask.py`，只照答案改 `base_url`、`api_key`、`model` 三個值；答案用環境變數（`OPENAI_BASE_URL`、`OPENAI_API_KEY`）時，腳本只改模型名，環境變數交給 `run_ask.py --env`。
- `python3 $F/check_script_diff.py /home/dev/ask.py $W/ask.py` 必須 exit 0（只動了這三個值）。答案要求改別的地方（例如加 import、改呼叫方式）：照答案改，但記下 `check_script_diff` 不過；這違反題目「Only base_url, api_key and model may change」，L2-2 不過。
- 答案的主要做法是另外裝 proxy／gateway：照答案的步驟原字不改裝起來（`python3 $F/tools/run_steps.py --steps $W/steps-install.txt --out $W/install`），腳本指向它；L2-1 因為 base_url 不是 Ollama 的預設位址而不過，L2-2、L2-3 照常量。

### egress check（L2-3）

「egress」指**任何連往本機以外的嘗試**：查詢 localhost 以外名稱的 DNS，或對 loopback（127.0.0.0/8、::1）、0.0.0.0、本沙盒自己介面位址以外的 IPv4／IPv6 位址呼叫 connect／sendto／sendmsg（失敗的嘗試、UDP、多播都算）。

定義、做法與判定見 [`_shared/README.md`](../_shared/README.md) 第 1 節（共用工具在沙盒裡的 `$SHARED`）。本題：Ollama 的啟動（label `ollama`，留在背景、一直被記錄）與那一次呼叫（`run_ask.py --egress-dir`，label `blocked`）都用 `egress.py run` 包起來；判定只算呼叫時段（`--since`／`--until`）內的嘗試，Ollama 在那段時間的連線也算。

**「egress check 通過」**＝ `egress.py report` 的 `result` 是 `pass`。`fail` 列出位址與原始紀錄行；`undetermined` 表示量測沒做好，不能判過、也不算答案的錯。Ollama 本身在封鎖網路時不外連，已在 calibration.md C5 確認。

**「egress blocked (localhost allowed)」**＝ 沙盒 B 封鎖對外網路、loopback 可用（calibration.md E2 確認）；擋好後先跑 `egress.py probe`，必須 exit 0。

## 2. 各 [L2] 項目

### L2-1 base_url 是 Ollama 的預設位址

> [L2] The base_url the answer gives resolves to the runner's documented default host, port and OpenAI-compatible path (localhost, 127.0.0.1 and trailing-slash variants accepted); configuring the same values through OPENAI_BASE_URL and OPENAI_API_KEY is accepted

用到：`check_base_url.py`（`EXPECTED` 在 calibration.md C3 依固定版本的 Ollama 文件確認）。

做法：取答案主要做法裡的 base_url（腳本裡的 `base_url=`，或 `OPENAI_BASE_URL` 的值），`python3 $F/check_base_url.py "<base_url>"`。

通過：exit 0，也就是 scheme `http`、主機 `localhost` 或 `127.0.0.1`、埠 `11434`、路徑 `/v1` 或 `/v1/`、沒有 query。寫成環境變數 `OPENAI_BASE_URL`（加上 `OPENAI_API_KEY`）一樣算。`0.0.0.0`、少了 `/v1`、多了 `/chat/completions`、`https`、其他埠都不過。

### L2-2 固定的 Ollama 與小模型，腳本回出非空的回答

> [L2] In the dev image with a pinned Ollama and the frozen small model pulled, the frozen openai-package script (run with OPENAI_API_KEY unset unless the answer sets it) returns a non-empty chat completion after only the changes the answer gives

用到：`pins.env`、`start_ollama.sh`、`script/ask.py`（`/home/dev/ask.py`）、`check_script_diff.py`、`run_ask.py`。

做法（沙盒 A，網路開）：

```sh
STATE=$W/state sh $F/start_ollama.sh                       # 使用者原本的 Ollama，預設位址
cp /home/dev/ask.py $W/ask.py                              # 再照答案改 base_url / api_key / model
python3 $F/check_script_diff.py /home/dev/ask.py $W/ask.py
python3 $F/run_ask.py --script $W/ask.py --python /opt/q20-venv/bin/python \
  [--env OPENAI_BASE_URL=<答案的值>] [--env OPENAI_API_KEY=<答案的值>] --out $W/runs/online
```

- `run_ask.py` 只給 `PATH`、`HOME`、`LANG` 與答案給的 `--env`；**答案沒說要設 `OPENAI_API_KEY`，就不設**。openai 套件在沒有金鑰時會直接報錯（calibration.md C6 記下訊息），所以沒交代金鑰的答案在這裡不過。
- 600 秒上限。

通過：`check_script_diff.py` exit 0，而且 `$W/runs/online.json` 的 `pass` 為 true（exit 0、stdout 非空）。

### L2-3 封鎖網路後同一個呼叫仍成功、egress check 通過

> [L2] With egress blocked (localhost allowed), the same call succeeds and the egress check passes

用到：`$SHARED/egress.py`、`start_ollama.sh`、`run_ask.py`；L2-2 的同一份 `$W/ask.py` 與同樣的 `--env`。

做法（沙盒 B：用 A 的快照開機、封鎖網路）：

```sh
python3 $SHARED/egress.py probe --json $W/runs/probe.json                                      # exit 0
python3 $SHARED/egress.py run --out $W/egress --label ollama --sh "STATE=$W/state sh $F/start_ollama.sh"   # Ollama 留在背景，一直被記錄
T0=$(python3 -c 'import time; print(time.time())')
python3 $F/run_ask.py --script $W/ask.py --python /opt/q20-venv/bin/python [--env ...] \
  --egress-dir $W/egress --label blocked --out $W/runs/blocked
T1=$(python3 -c 'import time; print(time.time())')
python3 $SHARED/egress.py stop --out $W/egress --kill
python3 $SHARED/egress.py report --out $W/egress --since $T0 --until $T1 --json $W/runs/egress-report.json
```

通過：`$W/runs/blocked.json` 的 `pass` 為 true，**而且** egress report 的 `result` 是 `pass`。`undetermined` 時修好量測後重做這一步。

## 3. 自我測試

```sh
sh selftest.sh                                             # 離線；不需要 root
Q20_OPENAI_PYTHON=/opt/q20-venv/bin/python sh selftest.sh  # 另外用真的 openai 套件對假伺服器跑端到端
```

測試內容：`check_base_url.py` 接受與拒絕的寫法；`check_script_diff.py` 允許三個值的改動、拒絕多加 import 或改提示；`run_ask.py` 端到端：腳本裡給 base_url 與 api_key → 成功；只給 base_url、沒給金鑰 → 失敗；只用環境變數 → 成功；空回答 → 失敗；egress、pty、run_steps 工具。寫 fixture 時已在 macOS 用 Python 3.9 與 3.12 跑過（端到端部分用本機 uv 快取裡的 openai 3.40.0，沒有下載），全部通過。

## 4. 還沒決定的事

見 `needs.json`（Ollama、小模型、openai 套件版本、dev image、strace）與 `calibration.md`（預設位址的文件確認、參考設定在網路開與封鎖下都成功）。另外要念誠確認：答案指定的模型名一律換成凍結的小模型、答案要求 `ollama pull` 另一個模型時不照做（檢查項目指定「the frozen small model」，但第 5 節寫「不可換掉答案指定的模型」）。
