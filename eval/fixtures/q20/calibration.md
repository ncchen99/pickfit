# q20 開跑前校準

依 [eval/README.md](../../README.md) 第 3 節：檢查項目寫「pinned」「frozen」的版本、模型與套件，在**第一次開跑前** commit。本檔先寫步驟；結果欄位留空，由念誠或評分 session 在第一次開跑前填好、連同 `pins.env` 一起 commit。**不要在看到任何一組答案後才填或改。**

`F` 是本資料夾在沙盒裡的位置（例如 `/opt/eval-fixtures/q20`）。C3、C4 用的「參考設定」是評分者自己的對照組，不是任何答案。

## E. 沙盒與 egress 量測（q17–q20 共用）

與 [q17/calibration.md](../q17/calibration.md) 的 E 段相同，做一次即可；結果抄一份在這裡（或寫「同 q17，commit xxx」）。

| 項目 | 結果 |
|---|---|
| dev image digest、apt snapshot id | `pickfit-eval-l2-dev:4acdd7fff6ab`（`ubuntu:24.04@sha256:78d4744e…2044d`）；沒有 apt snapshot：映像建好時的套件版本整份記在 `eval/results/l2-images.json` 的 `dpkg` |
| egress | 照 `_shared/calibration.md` 步驟 1、2（各題共用一次） |

## C. q20 固定版本、模型與使用者環境

| 步驟 | 做法 | 要看到 |
|---|---|---|
| C1 釘版本 | 填 `pins.env`：`OLLAMA_*`（建議同 q18）、`FIXTURE_MODEL`、`OPENAI_PKG_VERSION`（凍結時 PyPI 上最新的 openai） | |
| C2 建 base image | 網路開，root：`sh $F/setup_pinned_ollama.sh`、`STATE=/tmp/q20cal sh $F/setup_user_env.sh`、`cp $F/script/ask.py /home/dev/ask.py`；digest 填回 `FIXTURE_MODEL_DIGEST`；存成 q20 base image（記 digest） | 雜湊核對通過；`openai <版本>`；`/tmp/q20cal/pip-freeze.txt` |
| C3 預設位址 | 讀固定版本 Ollama 的官方文件（該版本 tag 下的 docs，例如 OpenAI 相容那一頁與 FAQ 的預設位址），確認預設監聽 `127.0.0.1:11434`、OpenAI 相容路徑 `/v1` | 與 `check_base_url.py` 的 `EXPECTED` 相同。不同時：在任何一組開跑前照 eval/README.md 第 3 節寫勘誤、改 `EXPECTED` |
| C4 參考設定，網路開 | `STATE=/tmp/q20cal sh $F/start_ollama.sh`；複製 `ask.py` 成 `/tmp/q20cal/ref/ask.py`，只改成 `OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")` 與 `model="<FIXTURE_MODEL>"`；`python3 $F/check_script_diff.py $F/script/ask.py /tmp/q20cal/ref/ask.py`；`python3 $F/check_base_url.py http://localhost:11434/v1`；`python3 $F/run_ask.py --script /tmp/q20cal/ref/ask.py --python /opt/q20-venv/bin/python --out /tmp/q20cal/ref-online` | 三個都 exit 0；`ref-online.json` 的 `pass` 為 true |
| C5 參考設定，網路封鎖 | 用 C4 的快照開封鎖網路的沙盒：`python3 $SHARED/egress.py run --out /tmp/q20eg --label ollama --sh 'sh $F/start_ollama.sh'`；`run_ask.py ... --egress-dir /tmp/q20eg --label ref --out /tmp/q20cal/ref-blocked`；`python3 $SHARED/egress.py stop --out /tmp/q20eg --kill`；`python3 $SHARED/egress.py report --out /tmp/q20eg` | `pass` 為 true；report `result` 是 `pass`（Ollama 本身也沒有對外連線） |
| C6 沒設金鑰時（只記錄） | 原始 `ask.py` 只改模型名，`run_ask.py --env OPENAI_BASE_URL=http://localhost:11434/v1`（不給 `OPENAI_API_KEY`） | 預期失敗、錯誤訊息提到 api_key；記下訊息。這就是 L2-2「OPENAI_API_KEY unset unless the answer sets it」量的東西 |
| C7 自我測試 | `Q20_OPENAI_PYTHON=/opt/q20-venv/bin/python sh $F/selftest.sh` | 兩個測試都 `0 failure(s)`，而且沒有跳過端到端部分 |

結果（第一次開跑前填）：

| 項目 | 結果 |
|---|---|
| Ollama 版本、asset URL、SHA-256 | 同 q18：v0.40.13，`ollama-linux-amd64.tar.zst`，`c9490e0f…a75bb6`（下載後核對相同）。以 local-only 模式（`OLLAMA_NO_CLOUD=1`）啟動，伺服器紀錄 `cloud disabled: true`（q18 C6、9.3 C.5） |
| 模型 tag、digest、大小 | `qwen2.5:0.5b`，`/api/tags` 的 digest `a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67`（填回 `pins.env`），397,821,319 位元組；model layer 在沙盒裡算的 sha256 `c5396e06…` 與 PINS.md 相同 |
| openai 版本、pip freeze（附檔） | `openai==3.42.0`；15 個套件，`eval/results/calibration/q20/q20/pip-freeze.txt`。venv 需要的 `python3-venv` 3.12.3-0ubuntu2.1 與 `python3.12-venv` 3.12.3-1ubuntu0.17 由評分者先裝（使用者原本的環境，不算答案的步驟） |
| q20 base image digest | 沒有另外建：每次照 C2 在 dev image 沙盒裡裝（核對 sha256 與 digest）後才跑答案的步驟。要存成映像時，由建評測部署的協調 session 記 digest |
| C3 文件連結與預設位址 | v0.40.13 tag 下的 `docs/faq.mdx`：「Ollama binds 127.0.0.1 port 11434 by default」；`docs/api/openai-compatibility.mdx`：`base_url='http://localhost:11434/v1/'`。實測伺服器紀錄 `Listening on 127.0.0.1:11434`。與 `check_base_url.py` 的 `EXPECTED` 相同，不需要勘誤 |
| C4、C5 結果 | C4：`check_script_diff.py` exit 0、`check_base_url.py` exit 0、`run_ask.py` pass（exit 0、1.06 秒、回答非空）。C5（一個 `--block-network` 腳本：probe、Ollama、呼叫）：probe 擋住（4 個 TCP、2 個 DNS 都失敗）；呼叫 pass（2.83 秒）；呼叫時段內的 egress report `pass`。整份紀錄有 21 次嘗試，全部是 probe（pid 566）在呼叫前 2 秒故意做的，Ollama 一次都沒有（`c5-egress-all.json`）。所以 README L2-3 的做法寫明只算呼叫時段、probe 不算；時段內的報告是下載紀錄後用同一個 `egress.py report --since/--until` 算的（`c5-egress.json`），`calibrate.sh` 已改成在沙盒裡直接這樣算 |
| C6 錯誤訊息 | exit 1：`` openai.OpenAIError: Missing credentials. Please pass an `api_key`, `workload_identity`, `admin_api_key`, or set the `OPENAI_API_KEY` or `OPENAI_ADMIN_KEY` environment variable. `` |
| C7 自我測試 | 兩個測試都 `0 failure(s)`，用沙盒裡真的 openai 3.42.0 跑了端到端部分（沒有 skip） |
| 記錄人、時間、commit | 評測 session（eval-prep-74b711），2026-10-31，Modal 沙盒 `sb-01M68CERZX7G5BZ2NZTCB9134N`（cpu 4、16 GiB）；紀錄 `eval/results/calibration/q20/`；commit 同本檔 |

第一次和 q18、q19 同一個沙盒跑時，C2 的 venv 沒建成（`calibrate.sh` 用 `dpkg-query -W` 判斷 `python3-venv` 已裝，但那只表示 dpkg 知道這個套件），沒有跑到 C3 以後；紀錄在 `eval/results/calibration/ollama-trio/q20-venv-failed/`。修正判斷後單獨重跑，就是上表。

## 8 vCPU 重跑（2026-10-31）

q18–q20 的 L2 沙盒（兩組）改成 8 vCPU、16 GiB（9.3 C.4），在 8 vCPU 重新校準（`eval/results/calibration/q18-q20-8cpu/q20/`，Modal 沙盒 `sb-01M68H40727S7JWQGHBQCGZKF0`，`nproc` 8）：C3 `Listening on 127.0.0.1:11434`；C4 三個都 exit 0（呼叫 0.83 秒）；C5 呼叫 pass（2.29 秒），呼叫時段內的 egress report `pass`（整份紀錄的 21 次仍全是 probe 的）；C6 同樣的錯誤訊息；C7 兩個 `0 failure(s)`，沒有 skip；模型 digest 與上表相同。
