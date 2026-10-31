# q14 測試資料

題目：CPU-only、8 GB RAM 的 Linux 主機上，一個本機、開源的服務同時提供 OpenAI 相容的 `/v1/embeddings` 與 rerank 端點，模型要能處理中英混合、授權允許商用。沙盒：`linux_sandbox`。

這個資料夾只給評分者，受測 agent 看不到。內容全部自己寫、合成、固定；不含任何工具名稱、廠商、模型名稱或預期答案，對任何答案推薦的服務都一樣適用。腳本只用 Python 3.9+ 標準函式庫；只有 `embed_check.py` 的正式模式需要固定版本的 `openai` 套件。

## 1. 檔案

| 檔案 | 用途 |
|---|---|
| `sandbox.json` | 沙盒規格：x86_64、4 vCPU、8 GB、無 GPU；A、B 兩個階段 |
| `data.json` | 凍結的輸入：維度檢查的一句英文與一句中文、3 組中英翻譯對、1 句無關的中文干擾句、rerank 的查詢與 5 段中英混合文字（第 3 段，index 2，是相關的那段） |
| `service_check.py` | L2-1：一個啟動指令、同一個服務、兩個端點都就緒 |
| `embed_check.py` | L2-2、L2-3：透過 openai client 取向量、比較維度與 cosine |
| `rerank_check.py` | L2-4：送一次 rerank 請求，判讀排名 |
| `../_shared/egress.py` | L2-5：證明外連被擋、記錄外連嘗試（各題共用，[`_shared/README.md`](../_shared/README.md) 第 1 節） |
| `../_shared/mem_peak.sh` | L2-5：容器記憶體峰值（各題共用，同上第 3 節） |
| `needs.json` | 要從外部取得的東西，待念誠決定 |
| `calibration.md` | 第一次開跑前要做的固定與紀錄 |
| `tests/` | 本資料夾腳本的自我測試 |

`data.json` 的中文以繁體為主，每一部分各有一句簡體，因為題目只說「Chinese」。

## 2. 共同設定

- **dev image**：第 5 節的 Linux 沙盒（Modal Sandbox、x86_64、以 `ubuntu:24.04` 為底，digest 記在 `calibration.md`），不接 GPU，4 vCPU、8 GiB 記憶體上限。
- **掛載**：本資料夾與評分用的 Python（裝好固定版本的 `openai`）唯讀掛在 `/eval/q14`；評分輸出寫到 `/results`。評分工具都不裝進受測環境。
- **評分用 Python**：下文的 `$EVAL_PY` 是 `/eval` 上那個獨立的 Python 3（`needs.json`），裝好固定版本的 `openai`；其他腳本只用標準函式庫，也用它跑。
- **佔位字**：答案的 port、模型名稱、資料夾是佔位字時，評分者照答案填入（第 5 節允許）。答案的服務要求 API key 時，當場產生一把假的：`export Q14_API_KEY=$($EVAL_PY -c 'import secrets; print("eval-" + secrets.token_hex(16))')`，啟動指令與各檢查的 `--api-key-env Q14_API_KEY` 都用它；不寫進任何檔案。不要求時，`embed_check.py` 自己產生一次性的假 key（openai client 沒有 key 不肯啟動）。
- **照原樣（verbatim）**：評分者把答案的安裝指令依序、原封不動複製成 `/results/steps.sh`，在同一個 bash 裡逐條執行（`bash -x steps.sh 2>&1 | tee /results/install.log`）。只做第 5 節允許的調整：填版本號與佔位字、安裝程式詢問時接受預設值；每一處替換記在 `/results/substitutions.json`。Ubuntu 擋下裸 `pip install` 時可以改在 venv 裡繼續（記 `needed_venv`）。修正指令或旗標、補步驟、換模型都不允許。本題沒有單獨的「照原樣」項目；安裝失敗時，照 9.1 節 C7，其餘 [L2] 項目都記不過。
- **一個啟動指令**：答案給的「啟動服務」那一行指令（可以有參數、可以是設定檔路徑），評分者原樣執行一次，背景執行、記下 PID。答案需要兩個以上的啟動指令（例如兩個程序、兩個容器）才能提供兩個端點，L2-1 就不過；評分者不替答案合併。
- **擋外連（egress blocked）**：照 9.3 B.3 與 [`_shared/README.md`](../_shared/README.md) 第 1 節：`egress.py run --block-network`（只有 loopback 的 network namespace，DNS 也查不到；在 Modal 的 gVisor 沙盒裡是 user＋network namespace，uid 照原樣對應，2026-10-31 實測）。在 A 階段安裝完成、模型下載完成之後，從 A 階段結束時的檔案系統快照開新沙盒（網路照常，讓 `memory.peak` 只涵蓋 B 階段），B 階段的步驟才在擋住的 namespace 裡跑。要互相連線的步驟（啟動服務與送請求、檢查）寫進同一個腳本，用一次 `egress.py run --block-network --sh 'bash 腳本'` 跑完，因為每一次 `--block-network` 都是新的 namespace。兩組、所有答案都用同一種。
- **外連檢查（egress check）**：定義與判定見 [`_shared/README.md`](../_shared/README.md) 第 1 節（共用工具在沙盒裡的 `$SHARED`）：
  1. 擋了之後、啟動服務前，和停止服務後，各跑一次 `egress.py probe`：直接連公開位址的 TCP 與送往公開 DNS 的 UDP 都失敗，才算「確實擋住」。透過沙盒自己的 resolver 查名稱只記錄（`dns_resolves`），不影響判定。
  2. 受測程序用 `egress.py run` 包起來，strace 記錄它與它所有子程序（含在背景跑的服務）的每一次連線；目的地不是 loopback、未指定位址、沙盒自己的位址的，以及任何查名稱（DNS），都算一次外連嘗試，包括私有網段與 `169.254.169.254`。
  3. 通過：前後探測都擋住，而且 `egress.py report` 是 `pass`。探測顯示沒擋住，是評分環境的問題：修好重跑，不記答案不過。
  4. strace 不能用時，不能判過（`_shared/README.md` 第 1 節；`/proc` 輪詢抓不到立刻失敗的連線）。
- **逾時**：安裝 20 分鐘；第一次啟動（含下載模型）最多 20 分鐘；其餘每個檢查 10 分鐘（第 5 節）。
- **判讀模型輸出**：embedding 與 rerank 沒有取樣溫度，每項只跑一次。

## 3. 執行順序

### A 階段（可連網）

1. 照 `sandbox.json` 開沙盒，確認 `nproc` 是 4、記憶體上限 8 GiB、沒有 `nvidia-smi`。
2. 照原樣執行安裝步驟。
3. 執行答案的那一個啟動指令，背景執行，輸出存 `/results/server-a.log`，記下 PID。
4. L2-1（等待含第一次下載模型）：
   ```bash
   $EVAL_PY /eval/q14/service_check.py --embeddings-url http://127.0.0.1:<port>/v1/embeddings \
     --embedding-model <答案的 embedding 模型> --rerank-url <答案或文件的 rerank URL> \
     --rerank-shape <見 L2-4> [--rerank-model <答案的 rerank 模型>] --pid <PID> --wait 1200 \
     --out /results/service.json
   ```
5. L2-2、L2-3：
   ```bash
   $EVAL_PY /eval/q14/embed_check.py --base-url http://127.0.0.1:<port>/v1 \
     --model <答案的 embedding 模型> --out /results/embed.json
   ```
6. L2-4：
   ```bash
   $EVAL_PY /eval/q14/rerank_check.py --url <rerank URL> --shape <...> [--model ...] \
     --format-source answer|server-docs --out /results/rerank.json
   ```
7. 停止服務。做檔案系統快照（strace 已在 dev image 裡，9.3 B.2；不另外安裝）。

### B 階段（擋外連，新沙盒，同樣 4 vCPU、8 GiB）

8. 從快照開新沙盒（4 vCPU、8 GiB）。在背景跑記憶體取樣：`sh $SHARED/mem_peak.sh watch /results/mem-watch.json &`，記下 PID（取樣在 namespace 外面，看的是整個沙盒的 cgroup）。
9. 把 B 階段寫成一個腳本 `/results/phase-b.sh`，整個在一次擋外連裡跑（服務與請求要在同一個 namespace 才連得到）：
   ```bash
   $EVAL_PY $SHARED/egress.py run --out /results/egress --label phase-b --block-network --timeout 2400 \
     --sh 'bash /results/phase-b.sh'
   ```
   `phase-b.sh` 依序做：
   1. `$EVAL_PY $SHARED/egress.py probe --json /results/probe-b.json`，不是 exit 0 就停（擋外連沒生效，是評分環境的問題）；
   2. 背景執行答案的那一個啟動指令（原樣），記下 PID；
   3. 等就緒（同步驟 4，`--wait 600`，輸出 `/results/service-b.json`），再送一次步驟 5 與步驟 6（輸出 `embed-b.json`、`rerank-b.json`）；
   4. `$EVAL_PY $SHARED/egress.py probe --json /results/probe-b-after.json`；
   5. `kill -TERM` 服務的程序群組。
10. `$EVAL_PY $SHARED/egress.py stop --out /results/egress --kill`；`kill -TERM` 步驟 8 的取樣；`$EVAL_PY $SHARED/egress.py report --out /results/egress --json /results/egress.json`。
11. `BELOW_BYTES=8589934592 sh $SHARED/mem_peak.sh read /results/mem.json /results/mem-watch.json`。

## 4. L2 項目

### L2-1

> [L2] In the dev image, CPU only, with a 4 vCPU and 8 GB limit, one start command brings up one service serving both models

- 測試資料：`sandbox.json`、`data.json`（rerank 的就緒請求用它的查詢與段落）、`service_check.py`。
- 設定：第 3 節步驟 1–4。
- 檢查：`service.json`。`service_check.py` 反覆送一個 embedding 請求（`input` 是 `"ping"`）與一個 rerank 請求，直到兩個都回 200；並比較兩個 URL 的 scheme、host、port。監聽中的 port 與 PID 底下的程序樹只記錄，不判過。
- 通過：評分者只執行了一個啟動指令；20 分鐘內兩個端點都回 200；兩者同一個 scheme、host、port（`passed: true`）。

### L2-2

> [L2] Through the pinned openai Python client with only base_url changed, an English input and a Chinese input return vectors of the same non-zero dimension

- 測試資料：`data.json` 的 `dimension_check`；固定版本的 `openai`（`calibration.md`）。
- 「只改 base_url」：`OpenAI(base_url=<答案的 base URL>, api_key=<假 key>)`，呼叫 `client.embeddings.create(model=<答案的模型>, input=<一個字串>)`，不加任何其他參數（不改 `encoding_format`、不加 header）。`--client raw` 只供本資料夾測試，不算數。
- 檢查：`embed.json` 的 `items.dims`。
- 通過：兩個向量長度相同且大於 0，全是有限數值，而且不是全零。

### L2-3

> [L2] For each of 3 frozen English-Chinese translation pairs, cosine similarity between the English sentence and its translation is higher than between the English sentence and a frozen unrelated Chinese distractor

- 測試資料：`data.json` 的 `pairs`（p1、p2 繁體，p3 簡體）與 `distractor_zh`（三組共用）。
- 做法：同 L2-2 的 client，一次一個字串取向量；cosine 在評分端算，不依賴伺服器是否正規化。
- 檢查：`embed.json` 的 `items.pairs`。
- 通過：三組都是 cos(英文, 譯文) > cos(英文, 干擾句)。

### L2-4

> [L2] A rerank request in the format given by the answer or by the server's docs for the installed version, with a frozen query and 5 frozen mixed-language passages (one relevant), ranks the relevant passage first

- 測試資料：`data.json` 的 `rerank`：英文查詢、5 段文字（2 段英文、2 段繁體、1 段簡體），相關的是 index 2（中文），index 4 是同主題（出差）但不相關的干擾段。
- 請求格式：答案有寫就照答案；沒寫就查**已安裝版本**的伺服器文件（版本號、文件網址記在 `rerank.json` 旁的 `rerank-format.txt`），以 `--format-source` 記下來源。`--shape query-documents` 送 `{"query", "documents"}`，`--shape query-texts` 送 `{"query", "texts"}`，其他格式寫成 `--template` 檔（`"{{query}}"`、`"{{documents}}"`、`"{{model}}"` 會被代換）；答案或文件要求的額外欄位用 `--extra-json`。
- 判讀回應：不預設格式。回應本身是陣列，或在 `results`、`data`、`rankings`、`ranking`、`result`、`documents` 底下找到陣列；每筆用 `index` 等欄位或原文對回段落，有分數（`relevance_score`、`score` 等）就依分數排序，沒有就依回傳順序。
- 通過：相關段落排第一；有分數時，它的分數嚴格高於其他每一段（同分不算第一）。

### L2-5

> [L2] After model download, with egress blocked, both requests succeed, the egress check passes, and container memory.peak stays under 8 GB

- 測試資料：同 L2-2、L2-4；`$SHARED/egress.py`、`$SHARED/mem_peak.sh`。
- 設定：第 3 節 B 階段。
- 「兩個請求」：B 階段的 embedding 請求（`embed-b.json` 的 `items.dims` 那兩次）與 rerank 請求（`rerank-b.json`）。
- 「外連檢查」：第 2 節的定義，範圍是 B 階段從啟動服務到停止服務的整段時間（含模型載入）。
- 「memory.peak」：B 階段沙盒 cgroup v2 的 `memory.peak`；沒有這個檔時用 `mem_peak.sh watch` 取樣的最大值（`memory.current`，再沒有就是所有程序 RSS 加總），`mem.json` 的 `method` 記下用了哪一種（共用規則，`_shared/README.md` 第 3 節）。8 GB = 8 GiB = 8589934592 bytes，也就是沙盒的上限。
- 通過，三個都要成立：
  1. `embed-b.json` 的 `items.dims` 通過，而且 `rerank-b.json` 回 200；
  2. `probe-b.json`、`probe-b-after.json` 都是 `blocked: true`，而且 `egress.json` 的 `result` 是 `pass`；
  3. `mem.json` 的 `result` 是 `pass`：峰值 < 8589934592，而且沒有 OOM kill。

## 5. 不適用

本題不是 Mac 題，沒有移除清單。

## 6. 自我測試

```bash
python3 -m unittest discover -s eval/fixtures/q14/tests -v
```

用本機假的 embedding／rerank 伺服器驗證各種回應格式與判定。外連檢查與記憶體量測的測試在 `_shared/test_shared.py`。以下是 q14 原本的外連工具在出題時的實測紀錄，結論已寫進 `_shared/README.md`：2026-10-30 另在離線（`--network none`）的 x86_64 Linux 容器跑過全部測試，並確認：預設探測回報「擋住」、`/proc` 輪詢抓不到立刻失敗的連線、cgroup v2 的 `memory.peak` 讀得到。
