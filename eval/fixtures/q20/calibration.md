# q20 開跑前校準

依 [eval/README.md](../../README.md) 第 3 節：檢查項目寫「pinned」「frozen」的版本、模型與套件，在**第一次開跑前** commit。本檔先寫步驟；結果欄位留空，由念誠或評分 session 在第一次開跑前填好、連同 `pins.env` 一起 commit。**不要在看到任何一組答案後才填或改。**

`F` 是本資料夾在沙盒裡的位置（例如 `/opt/eval-fixtures/q20`）。C3、C4 用的「參考設定」是評分者自己的對照組，不是任何答案。

## E. 沙盒與 egress 量測（q17–q20 共用）

與 [q17/calibration.md](../q17/calibration.md) 的 E 段相同，做一次即可；結果抄一份在這裡（或寫「同 q17，commit xxx」）。

| 項目 | 結果 |
|---|---|
| dev image digest、apt snapshot id | |
| E7 必要層 | dns ＋ （strace？）＋（poll？） |

## C. q20 固定版本、模型與使用者環境

| 步驟 | 做法 | 要看到 |
|---|---|---|
| C1 釘版本 | 填 `pins.env`：`OLLAMA_*`（建議同 q18）、`FIXTURE_MODEL`、`OPENAI_PKG_VERSION`（凍結時 PyPI 上最新的 openai） | |
| C2 建 base image | 網路開，root：`sh $F/setup_pinned_ollama.sh`、`STATE=/tmp/q20cal sh $F/setup_user_env.sh`、`cp $F/script/ask.py /home/dev/ask.py`；digest 填回 `FIXTURE_MODEL_DIGEST`；存成 q20 base image（記 digest） | 雜湊核對通過；`openai <版本>`；`/tmp/q20cal/pip-freeze.txt` |
| C3 預設位址 | 讀固定版本 Ollama 的官方文件（該版本 tag 下的 docs，例如 OpenAI 相容那一頁與 FAQ 的預設位址），確認預設監聽 `127.0.0.1:11434`、OpenAI 相容路徑 `/v1` | 與 `check_base_url.py` 的 `EXPECTED` 相同。不同時：在任何一組開跑前照 eval/README.md 第 3 節寫勘誤、改 `EXPECTED` |
| C4 參考設定，網路開 | `STATE=/tmp/q20cal sh $F/start_ollama.sh`；複製 `ask.py` 成 `/tmp/q20cal/ref/ask.py`，只改成 `OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")` 與 `model="<FIXTURE_MODEL>"`；`python3 $F/check_script_diff.py $F/script/ask.py /tmp/q20cal/ref/ask.py`；`python3 $F/check_base_url.py http://localhost:11434/v1`；`python3 $F/run_ask.py --script /tmp/q20cal/ref/ask.py --python /opt/q20-venv/bin/python --out /tmp/q20cal/ref-online` | 三個都 exit 0；`ref-online.json` 的 `pass` 為 true |
| C5 參考設定，網路封鎖 | 用 C4 的快照開封鎖網路的沙盒：`sudo python3 $F/egress/egress.py start --out /tmp/q20eg --mode sink`；`start_ollama.sh`；`run_ask.py ... --egress-dir /tmp/q20eg --label ref --out /tmp/q20cal/ref-blocked`；`stop`；`report --out /tmp/q20eg` | `pass` 為 true；report `result` 是 `pass`（Ollama 本身也沒有對外連線） |
| C6 沒設金鑰時（只記錄） | 原始 `ask.py` 只改模型名，`run_ask.py --env OPENAI_BASE_URL=http://localhost:11434/v1`（不給 `OPENAI_API_KEY`） | 預期失敗、錯誤訊息提到 api_key；記下訊息。這就是 L2-2「OPENAI_API_KEY unset unless the answer sets it」量的東西 |
| C7 自我測試 | `Q20_OPENAI_PYTHON=/opt/q20-venv/bin/python sh $F/selftest.sh` | 兩個測試都 `0 failure(s)`，而且沒有跳過端到端部分 |

結果（第一次開跑前填）：

| 項目 | 結果 |
|---|---|
| Ollama 版本、asset URL、SHA-256 | |
| 模型 tag、digest、大小 | |
| openai 版本、pip freeze（附檔） | |
| q20 base image digest | |
| C3 文件連結與預設位址 | |
| C4、C5 結果 | |
| C6 錯誤訊息 | |
| 記錄人、時間、commit | |
