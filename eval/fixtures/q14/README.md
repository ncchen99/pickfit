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
| `egress_check.py` | L2-5：證明外連被擋、記錄外連嘗試（q14、q15、q16 各一份，內容相同） |
| `mem_peak.py` | L2-5：容器記憶體峰值 |
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
- **擋外連（egress blocked）**：在 A 階段安裝完成、模型下載完成之後才擋。做法：從 A 階段結束時的檔案系統快照開一個新沙盒，網路在沙盒層級關閉（首選）；或在同一個沙盒以 root 用 iptables／ip6tables 只放行 `lo`，其餘 REJECT（連線立刻失敗，不卡逾時）。用哪一種記在 `calibration.md`；兩組、所有答案都用同一種。本題首選新沙盒，因為這樣 `memory.peak` 只涵蓋 B 階段。
- **外連檢查（egress check）**：受測程序用 `egress_check.py run` 包起來：
  1. 執行前、後各探測一次：TCP 連 `1.1.1.1:443`、`8.8.8.8:53`、`9.9.9.9:443`、`[2606:4700:4700::1111]:443`，UDP 對 `8.8.8.8:53`、`1.1.1.1:53` 送 DNS 查詢，解析 `example.com`。全部失敗才算「確實擋住」。
  2. 執行期間用 strace（`-f --seccomp-bpf`，追蹤 `connect`、`sendto`、`sendmsg`、`sendmmsg`）記錄受測程序與它所有子程序的每一次連線；目的地不是 loopback（`127.0.0.0/8`、`::1`）也不是未指定位址（`0.0.0.0`、`::`）的，都算一次外連嘗試，包括 DNS 查詢、私有網段與 `169.254.169.254`。
  3. 通過：前後探測都擋住，而且外連嘗試 0 次（log 的 `verdict.egress_check_passed` 是 `true`）。探測顯示沒擋住，是評分環境的問題：修好重跑，不記答案不過。
  4. strace 不能用時，`/proc` 輪詢只是備案而且抓不到立刻失敗的連線（`calibration.md`），不能用來判過；要先照 `calibration.md` 解決。
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
7. 停止服務。裝評分工具 `apt-get install -y strace`（答案的安裝已完成，這不算答案的步驟）。做檔案系統快照。

### B 階段（擋外連，新沙盒，同樣 4 vCPU、8 GiB）

8. 從快照開新沙盒，網路關閉。`$EVAL_PY /eval/q14/egress_check.py probe --log /results/probe-b.json` 必須 exit 0。
9. 沒有 `memory.peak` 時，先在背景跑 `$EVAL_PY /eval/q14/mem_peak.py watch --out /results/mem-watch.json`。
10. 在監測下執行同一個啟動指令（背景）：
    ```bash
    $EVAL_PY /eval/q14/egress_check.py run --log /results/egress.json -- bash -c '<答案的啟動指令>' &
    ```
11. 等就緒（同步驟 4，`--wait 600`，輸出 `/results/service-b.json`），然後再送一次步驟 5 與步驟 6（輸出 `embed-b.json`、`rerank-b.json`）。
12. `kill -TERM <步驟 10 的 PID>`（`egress_check.py` 把訊號轉給整個程序群組，再寫 log）；停掉 `mem_peak.py watch`。
13. `$EVAL_PY /eval/q14/mem_peak.py read [--watch-log /results/mem-watch.json] --out /results/mem.json`。

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

- 測試資料：同 L2-2、L2-4；`egress_check.py`、`mem_peak.py`。
- 設定：第 3 節 B 階段。
- 「兩個請求」：B 階段的 embedding 請求（`embed-b.json` 的 `items.dims` 那兩次）與 rerank 請求（`rerank-b.json`）。
- 「外連檢查」：第 2 節的定義，範圍是 B 階段從啟動服務到停止服務的整段時間（含模型載入）。
- 「memory.peak」：B 階段沙盒 cgroup v2 的 `memory.peak`；沒有這個檔時用 `mem_peak.py watch` 的最大值（`memory.current`，再沒有就是所有程序 RSS 加總），`mem.json` 記下用了哪一種。8 GB = 8 GiB = 8589934592 bytes，也就是沙盒的上限。
- 通過，三個都要成立：
  1. `embed-b.json` 的 `items.dims` 通過，而且 `rerank-b.json` 回 200；
  2. `egress.json` 的 `verdict.egress_check_passed` 是 `true`；
  3. `mem.json` 的 `decision.passed` 是 `true`：峰值 < 8589934592，而且沒有 OOM kill。

## 5. 不適用

本題不是 Mac 題，沒有移除清單。

## 6. 自我測試

```bash
python3 -m unittest discover -s eval/fixtures/q14/tests -v
```

用本機假的 embedding／rerank 伺服器驗證各種回應格式與判定；外連探測只對 `127.0.0.1` 測，不連外；strace 與 `/proc/net` 的解析用樣本文字測。2026-10-30 另在離線（`--network none`）的 x86_64 Linux 容器跑過全部測試，並確認：預設探測回報「擋住」、`/proc` 輪詢抓不到立刻失敗的連線、cgroup v2 的 `memory.peak` 讀得到。
