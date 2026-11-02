# 已知項目測試：目錄裡有合適的工具時，`find_software` 找得到嗎

2026-11-02 事先登記。這份說明連同 `prompts/` 在**任何一次執行之前** commit，commit 的時間就是登記時間。之後只在本文最後的「變更紀錄」追加，不改前面的內容。

## 1. 要回答的問題

P6 的題目是不看目錄寫的開放題。pickfit 輸了，分不出是「目錄裡沒有」還是「有，但沒配對到」。這個測試只量後者：**從目錄裡挑出已驗證的工具，照它上游的 README 寫一個需求，看 `find_software` 會不會把它找回來。**

- 這是**探索性**的測試，樣本小（15 題），和 P6 的主要結果分開報告。
- 不改任何紀錄、配對程式或提示詞；只量。
- 不讀 `eval/questions*.yaml` 與 `eval/results/`；只寫 `eval/known-item/`。

## 2. 母體與抽樣

**母體**：正在線上的 Worker（`https://pickfit-mcp.ncchen99.workers.dev`）所用的資料。它的 `data_sha256` 是 `acb3891c32173105a6521ed0a93b047500363b547c07db8a4e7b3e0d3b6cb3e2`（768 筆），和 commit `4e0dd4b` 的 `data/software/` 算出來的一致，所以從那個 commit 的資料抽。符合下列全部條件的紀錄才算：

- `status` 是 `listed`；
- `verification.level` 是 `inference`、`service`、`function` 或 `install`（install 以上）；
- `repo.url` 在 github.com、沒有 archived。

**分層**（依 `category`）與抽樣數：

| 層 | 條件 | 合格筆數 | 抽 |
|---|---|---|---|
| dev_cli | `category = dev_cli` | 202 | 4 |
| local_ai | `category = local_ai` | 119 | 4 |
| mcp_server | `category = mcp_server` | 121 | 4 |
| gui | `category = other`（這份快照裡都是 `desktop_app`；線上還沒有 web app） | 69 | 3 |

共 **15 題**。

**亂數種子**：`20261102`。每一層把合格的 slug 依字母排序，用 Python 的 `random.Random("20261102:<層名>").shuffle()` 打亂，照順序往下取，直到取滿。只有下列情況跳過一筆、改取下一筆，跳過的都記下原因：

1. 抓不到上游 README（GitHub API `GET /repos/{owner}/{repo}/readme`，見第 3 節）；
2. README 去掉圖片、HTML 標籤與連結網址後不到 400 個字元；
3. 寫題目的模型三次都沒通過機械檢查（第 3 節）。

## 3. 題目怎麼寫

**寫題目的模型沒看過 `data/`**：每個目標一次 Anthropic API 呼叫（`claude-opus-5-5`，effort `medium`），固定的系統提示在 [prompts/writer.md](prompts/writer.md)。它**只拿到上游 README**，不拿到 pickfit 的紀錄、slug、類別或分數。

- **README 釘在一個 commit**：先用 GitHub API 取預設分支當下的 commit SHA，再用 `GET /repos/{owner}/{repo}/readme?ref=<SHA>` 抓 README。SHA、檔名、抓取時間都記下。超過 40,000 個字元的只給前 40,000 個字元。
- **輸出**：一段使用者的需求（英文、第一人稱、2–4 句，講情境，加上 2–4 個硬條件）、這件事的核心工作（一句）、硬條件清單，每個條件附上 README 裡支持它的原句。
- 題目不提作業系統（作業系統另外傳，見第 4 節）。

**機械檢查**（由腳本做，腳本會讀紀錄，但寫題目的模型看不到結果的內容）：

1. **不含工具名**：需求裡不能出現紀錄的 `name`、`slug`、`aliases`、repo 名稱與 repo 擁有者（不分大小寫；`-`、`_`、空白視為相同；以字詞邊界比對）。
2. **不抄紀錄的文字**：需求和紀錄的 `summary`、每一條 `use_cases`，不能有連續 5 個以上相同的字（轉小寫、只取 `[a-z0-9]+` 當字）。

沒通過就用**同一個提示**再寫一次，只加一句固定的話（「上一稿沒通過檢查：可能用了工具名或照抄了說明。請用使用者自己的話重寫。」），**不給它看紀錄的任何文字**。最多寫 3 次；3 次都沒過，這個目標跳過、改取同一層的下一筆。

**人不改題目**：題目原樣送出，不手動修改。寫題目的輸入（README 全文與 SHA）、每一次的輸出、檢查結果都 commit。

## 4. 怎麼執行

- 每題直接呼叫線上 Worker 的 MCP 端點（`POST /mcp`，JSON-RPC `tools/call`，工具 `find_software`），**不經過 agent**。
- 參數只有兩個：`need` = 題目原文；`os` = 目標紀錄中**決定它驗證等級的那次 run** 的作業系統（通過的 run 中等級最高的；同等級取最新的）。不傳 `category`、`budget`、`must_run_locally` 等其他條件；`limit` 用預設的 3。
- 加上標頭 `X-Pickfit-Reporter: eval`，標明這是我們自己的測試。
- 每題跑 1 次，保留完整的回應。
- **降級時重跑一次**：如果回應的 `degraded` 是 true（沒用到模型，退回規則排序），等至少 60 秒再跑一次。計分用第一個沒降級的回應；兩次都降級就用第二次，並標記。兩次的回應都保留。這條只看基礎設施有沒有出錯，不看結果好壞。

## 5. 怎麼計分

**命中**：

- **hit@1**：`picks[0].slug` 就是目標。
- **hit@3**：目標在 `picks`（最多 3 個）裡。
- **acceptable@1**：hit@1，**或**第一名不是目標、但通過下面的盲測 L1 檢查（每個條件都 pass）。

**盲測 L1 檢查**：目標不是第一名時，對第一名做一次。

- 模型 `claude-opus-5-5`、effort `high`，固定的評分說明在 [prompts/l1.md](prompts/l1.md)。
- 檢查項目：第 3 節的核心工作，加上每一個硬條件。全部 pass 才算過；`unknown` 算不過。
- 證據：那個工具上游 README（同第 3 節的方法釘 commit），加上 GitHub 回報的授權（SPDX）。**不給**pickfit 的紀錄或回應的任何文字，不說這個工具是怎麼選出來的，也不說有沒有「正確答案」。
- 第一名沒有 GitHub repo、或抓不到 README 時，只給 GitHub 回報的授權與 repo 說明；仍照樣判。
- `picks` 是空的：三項都算沒命中，不做 L1。

**題目有效性檢查**：每一題都用同一個 L1 檢查、同一種證據，判目標本身。目標自己沒通過的題，標為「題目可能有問題」。主要結果仍是全部 15 題；另外並列去掉這些題之後的數字。

**難度**：每題旁邊列出目錄大小（768 筆）、快照裡同一 `category` 的 listed 筆數，和回應裡的 `considered`（符合硬條件的已驗證工具數）。

**報告的數字**：hit@1、hit@3、acceptable@1 各自的「命中數／題數」，加上 Wilson 95% 信賴區間；分層的數字只列次數，不算比率。

## 6. 怎麼報告

- 這是**探索性**的結果，和 P6 的主要結果**分開**；在 README、提交文字、影片或任何結論裡，**都不放在結論的第一句**。
- 所有題目都列出來，包括沒命中的。
- 一定要寫的限制，至少包括：
  - 樣本只有 15 題，信賴區間很寬；
  - 目錄小：線上只有 768 筆，同類別一兩百筆，命中比在上千筆裡容易；
  - 題目是照目標的 README 寫的，用詞比真實使用者更接近工具自己的說法（即使擋掉了 5 個字以上的重複）；
  - 只傳 `need` 與 `os`，沒傳結構化條件，所以 Worker 的硬條件篩選沒有發揮；
  - 一個模型寫題、同一家的模型做 L1，L1 只看 README 與授權；
  - 線上 Worker 的配對模型與資料可能在測試後更新，結果只代表這次的部署（記下時間與 `data_sha256`）。

## 7. 花費

- Anthropic（寫題目＋L1）上限 **$8**；經過 Worker 的 Meta 上限 **$3**。
- 都記在共用帳本 `~/.pickfit/ledger.sqlite`：`known-item-anthropic`（總額 $8）與 `known-item-worker`（總額 $3）。Worker 的花費每次呼叫前先預留，跑完後用 Worker D1 `events.meta_cost_usd`（以 `rec_id` 對應）結算。

## 8. 檔案

| 檔案 | 內容 |
|---|---|
| `prompts/writer.md` | 寫題目的固定提示 |
| `prompts/l1.md` | L1 檢查的固定評分說明 |
| `known_item.py` | 抽樣、抓 README、寫題目、執行、計分的腳本（登記後、執行前 commit） |
| `sample.json` | 抽樣結果與跳過的原因 |
| `inputs.json` | 每個目標 README 的出處：repo、commit SHA、路徑、字數、sha256（全文不進 repo，見變更紀錄） |
| `questions.jsonl` | 每一次寫題目的輸出與機械檢查結果 |
| `responses/` | Worker 的完整回應 |
| `l1.jsonl` | L1 檢查的完整回覆（證據只記出處，不記全文） |
| `spend.json` | 花費 |
| `results.json` | 每題的計分 |
| `results.md` | 結果表與限制 |

## 變更紀錄

（登記之後的修改只寫在這裡，附時間與原因。）

- **11/2 17:07，任何執行之前**（和 `known_item.py` 同一個 commit）：
  1. README 全文不 commit。上游 README 是第三方的文字，授權各不相同，不轉載進 repo。改成 commit 出處（repo、commit SHA、路徑、字數、全文的 sha256），全文可以從那個 commit 原樣取回；執行時的全文快取在 repo 外的 `~/.pickfit/known-item/`。
  2. 寫題目的回覆格式不對（JSON 解析不了、硬條件不是 2–4 個）也算一次沒通過，照第 3 節重寫。
  3. Worker 回應是錯誤（HTTP 不是 200、`isError`、讀不出結果）時，比照降級重跑一次。
  4. L1 的證據一律附上 GitHub 的 repo 說明（不只在抓不到 README 時）。
- **11/2 17:14，執行到第 1 題時**：第 1 題（hako-code）兩次都降級：第一次 `model_incomplete`（24.8 秒，Meta 有收費 $0.047），第二次 Meta 回 HTTP 404（兩次請求都是 404）。第 2 題（orbit）的第一次 17:12:50 也降級（約 3.6 秒），在 60 秒的等待中我停掉了執行，所以這次的回應沒有存下（Worker D1 有這筆事件）。同時間一次很小的 `muse-spark-1.3` 直接呼叫（`pickfit ping`）成功，所以 404 是間歇的；Worker 遇到 404 的備援（Muse Spark Open）在另一個分支上，還沒部署。降級的回應是規則排序，量不到這個測試要量的模型配對，所以把第 4 節的重跑規則改成：
  - 每題最多 **4 次**，間隔至少 90 秒；計分用第一個沒降級、沒錯誤的回應。4 次都降級，用最後一次並標記。
  - 這條只看 `degraded` 與錯誤，不看命中與否；適用全部 15 題，包括已經跑過兩次的第 1 題（接著跑第 3、4 次）。
  - 所有回應（含降級的）都保留；結果裡另外列出降級的次數與原因，以及降級回應用規則排序時的命中情況（只當參考）。
