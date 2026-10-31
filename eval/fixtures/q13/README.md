# q13 測試資料

題目：CPU-only 的 Linux 伺服器上，找一個能直接從路徑載入 GGUF、有效處理並發請求、提供 OpenAI 相容 API 的開源伺服器（找替代品，現在用 Ollama）。沙盒：`linux_sandbox`。

這個資料夾只給評分者，受測 agent 看不到。內容全部自己寫、合成、固定；不含任何工具名稱、廠商或預期答案，對任何答案推薦的伺服器都一樣適用。腳本只用 Python 3.9+ 標準函式庫與 POSIX 工具。

## 1. 檔案

| 檔案 | 用途 |
|---|---|
| `sandbox.json` | 沙盒規格：x86_64、8 vCPU、16 GB、無 GPU、三個掛載 |
| `prompt.json` | 凍結的長輸出提示（`max_tokens` 128、`temperature` 0）、並發數 4、回合數 3、門檻 1.5 |
| `bench.py` | L2-3、L2-4：並發請求與吞吐量比 |
| `disk_usage.py` | L2-2：可寫檔案系統的磁碟用量快照與比較 |
| `gguf_info.py` | 凍結模型時讀 GGUF 檔頭、算 SHA-256 |
| `needs.json` | 要從外部取得的東西（GGUF 模型、唯讀儲存、dev image、評分用 Python），待念誠決定 |
| `calibration.md` | 第一次開跑前要做的固定與紀錄 |
| `tests/` | 本資料夾腳本的自我測試 |

模型檔太大，不進 repo：放在評測專用的唯讀儲存，SHA-256 記在 `calibration.md`。

## 2. 共同設定

- **dev image**：第 5 節的 Linux 沙盒（Modal Sandbox、x86_64、以 `ubuntu:24.04` 為底，digest 記在 `calibration.md`），不接 GPU。
- **掛載**：模型檔唯讀掛在 `/models/<檔名>`；本資料夾唯讀掛在 `/eval/q13`；評分輸出寫到 `/results`。三者都不算進磁碟用量。
- **評分用 Python**：下文的 `$EVAL_PY` 是評分者自己的 Python 3：dev image 有 `python3` 就用它，沒有就用唯讀掛在 `/eval` 上的獨立版本（`needs.json`），不裝進受測環境。
- **佔位字**：答案裡的模型路徑、檔名、port 是佔位字，評分者填入 `/models/<檔名>` 與答案指定的 port（第 5 節允許）。答案的伺服器要求 API key 時，當場產生一把假的：`export Q13_API_KEY=$($EVAL_PY -c 'import secrets; print("eval-" + secrets.token_hex(16))')`，啟動指令與 `bench.py --api-key-env Q13_API_KEY` 都用它；不寫進任何檔案。
- **照原樣（verbatim）**：評分者把答案的安裝指令依序、原封不動複製成 `/results/steps.sh`，在同一個 bash 裡逐條執行（`bash -x steps.sh 2>&1 | tee /results/install.log`）。只做第 5 節允許的調整：填版本號與佔位字、安裝程式詢問時接受預設值；每一處替換記在 `/results/substitutions.json`（原文、替換後、理由）。任何一條非 0 結束，或超過 20 分鐘，就是不過。Ubuntu 擋下裸 `pip install` 時，可以改在 venv 裡繼續做後面的項目（記 `needed_venv`），但「照原樣成功」不過。修正指令或旗標、補步驟、換模型都不允許。
- **網路**：本題沒有離線要求，安裝與檢查都可以連網。
- **逾時**：安裝 20 分鐘；`bench.py` 等伺服器就緒最多 600 秒，其餘每個檢查 10 分鐘（第 5 節）。
- **判讀模型輸出**：請求固定 `temperature` 0（由 `bench.py` 送出），所以每項只跑一次（第 5 節）。

## 3. 執行順序（同一個沙盒，從頭到尾不重開）

1. 照 `sandbox.json` 開沙盒。確認 `nproc` 是 8、沒有 `nvidia-smi`；`touch /models/x` 必須失敗；`sha256sum /models/<檔名>` 等於 `calibration.md` 的值。
2. 照原樣執行安裝步驟（L2-1）。
3. 磁碟快照 before（安裝完成後、第一次啟動伺服器前）：
   ```bash
   $EVAL_PY /eval/q13/disk_usage.py snapshot --exclude /models --exclude /eval --exclude /results \
     --label before --out /results/disk-before.json
   ```
4. 照答案啟動伺服器：模型路徑填 `/models/<檔名>`，答案給的並發、context 等設定原樣使用；背景執行，輸出存 `/results/server.log`，記下 PID。答案的流程若要求先「匯入」模型，照做（匯入造成的複製會反映在 L2-2）。
5. 並發與吞吐量（L2-3、L2-4）：
   ```bash
   $EVAL_PY /eval/q13/bench.py --base-url http://127.0.0.1:<port>/v1 [--model <答案的模型名>] \
     [--api-key-env Q13_API_KEY] --out /results/bench.json
   ```
   `--model` 用答案指定的名稱；沒有指定就用 `GET /v1/models` 的第一個 id。
6. 記錄伺服器是否從該路徑讀模型（只記錄，不判過）：`grep /models/ /proc/<PID>/maps`，或 `ls -l /proc/<PID>/fd | grep /models/`。
7. 磁碟快照 after（伺服器仍在執行）與比較（L2-2）：
   ```bash
   $EVAL_PY /eval/q13/disk_usage.py snapshot --exclude /models --exclude /eval --exclude /results \
     --label after --out /results/disk-after.json
   $EVAL_PY /eval/q13/disk_usage.py compare /results/disk-before.json /results/disk-after.json \
     --model-file /models/<檔名> --out /results/disk-compare.json
   ```
8. 停止伺服器，保留 `/results` 全部檔案。

## 4. L2 項目

### L2-1

> [L2] The install steps succeed verbatim in the dev image on x86_64 with no GPU, at 8 vCPU and 16 GB

- 測試資料：`sandbox.json`。
- 設定：第 3 節步驟 1–2。
- 檢查：`install.log` 裡每一條指令都是 0 結束，20 分鐘內完成；`substitutions.json` 只有允許的替換。
- 通過：照原樣全部成功。用了 venv 或任何不允許的修改，就不過。

### L2-2

> [L2] The frozen fixture GGUF (0.5B-1.5B instruct, hash recorded) is mounted read-only at a path. Disk usage of all writable filesystems (`du -sx`, excluding the model mount) is measured after install and before the first server start; after the server loads the model from that path and answers requests, growth is under 5% of the model's size

- 測試資料：凍結的 GGUF（`needs.json`、`calibration.md`）；`disk_usage.py`。
- 「所有可寫檔案系統」：`/proc/self/mounts` 裡選項含 `rw` 的掛載，扣掉核心的虛擬檔案系統（proc、sysfs、cgroup、devpts、mqueue 等）與 `/models`、`/eval`、`/results`。tmpfs（`/dev/shm`、`/tmp`、`/run`）要算：複製到記憶體也是複製。每個掛載點跑 `du -sxk`；同一個裝置只算一次。
- 時間點：before 在安裝完成後、第一次啟動伺服器前；after 在 L2-3、L2-4 的所有請求都答完之後、伺服器仍在執行時。
- 檢查：`disk-compare.json` 的 `growth_bytes` 與 `limit_bytes`（= 模型檔 bytes × 0.05）。
- 通過：`growth_bytes < limit_bytes`，而且伺服器答了 L2-3 的請求。伺服器不能從這個唯讀路徑載入（例如要求寫入模型旁邊、只能從自己的模型庫載入）而答不了請求，就不過。

### L2-3

> [L2] 4 concurrent requests with the frozen long-output prompt (max_tokens 128, temperature 0) all return 200 with non-empty content

- 測試資料：`prompt.json`（要求至少 400 字，所以每個請求都會寫到 128 token 的上限）；`bench.py`。
- 做法：`bench.py` 等伺服器就緒，送 1 個暖機請求（不計），接著 3 回合，每回合先 1 個單一請求，再 4 個同時請求（用 barrier 同時放出，各自一條連線，`stream: false`）。
- 檢查：`bench.json` 的 `items.concurrent_ok`，看第 1 回合那 4 個並發請求。
- 通過：4 個都是 HTTP 200，`choices[0].message.content` 去掉空白後不是空的。

### L2-4

> [L2] With the parallel settings the answer gives, aggregate throughput for the 4 concurrent requests (total completion_tokens divided by wall time) is at least 1.5 times that of a single warmed-up request

- 測試資料：同 L2-3。
- 定義：
  - 單一 tps = 該請求的 `usage.completion_tokens` ÷ 該請求的秒數；
  - 並發 tps = 4 個請求中回 200 的 `completion_tokens` 總和 ÷ 從同時放出到最後一個回應結束的牆鐘秒數；
  - 比值 = 3 回合並發 tps 的中位數 ÷ 3 回合單一 tps 的中位數。
  - 取 3 回合中位數是為了降低單次量測的雜訊；這個做法在開跑前 commit，對所有答案相同。
- 「答案給的並發設定」：照答案的啟動指令與設定檔原樣使用；答案沒給任何並發設定，就用預設值啟動，照樣量。
- 檢查：`bench.json` 的 `items.throughput.ratio`。
- 通過：比值 ≥ 1.5。回 200 的回應沒有 `usage.completion_tokens`，這一項不過（項目就是用這個欄位定義的）；任一單一請求失敗，也不過。

## 5. 不適用

本題不是 Mac 題，沒有移除清單。沒有離線要求，不做外連檢查。

## 6. 自我測試

```bash
python3 -m unittest discover -s eval/fixtures/q13/tests -v
```

用本機假的 OpenAI 相容伺服器（並行、序列、不回 usage 三種）驗證 `bench.py` 的判定；用暫存資料夾驗證磁碟比較；用合成的 GGUF 驗證檔頭讀取。只用 loopback 與暫存檔，不連外。
