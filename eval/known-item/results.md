# 已知項目測試：結果

這是一個**探索性**的小測試，和 P6 的主要結果分開；做法在 [README.md](README.md) 事先登記（commit `690e68c`，11/2 17:05），登記後的修改都在 README 的變更紀錄。它只量「目錄裡已經有合適的工具時，`find_software` 找不找得到」，不量覆蓋，也不代表 P6 開放題的表現。引用時不放在任何結論的第一句。

## 執行

- 部署：`https://pickfit-mcp.ncchen99.workers.dev`，資料 `data_sha256 acb3891c…`（768 筆，等於 commit `4e0dd4b` 的 `data/software/`），11/2 17:10–17:23（台北）呼叫。配對模型 `muse-spark-1.3`。
- 寫題目與 L1：`claude-opus-5-5`（寫題目 effort medium，L1 effort high）。
- 15 題，種子 `20261102`，每層照打亂後的順序取前幾筆，沒有任何一筆被跳過。題目全文、Worker 的完整回應、L1 的完整回覆都在這個資料夾。

## 數字

| 指標 | 命中 | Wilson 95% |
|---|---|---|
| hit@1 | 11/15 | 48%–89% |
| hit@3 | 13/15 | 62%–96% |
| acceptable@1 | 11/15 | 48%–89% |

去掉「目標本身沒通過 L1」的 1 題（quill）之後：hit@1 10/14、hit@3 12/14、acceptable@1 10/14。

分層（只列次數）：dev_cli hit@1 3/4、hit@3 3/4；local_ai 2/4、4/4；mcp_server 3/4、3/4；gui 3/3、3/3。

| # | 層 | 目標 | OS | 等級 | 名次 | 第一名 | 第一名 L1 | 目標 L1 | considered | 同類 listed | 目錄 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | dev_cli | `hako-code` | linux | service | — | `camelid` | fail | pass | 591 | 236 | 768 |
| 2 | dev_cli | `orbit` | linux | service | 1 | `orbit` | — | pass | 591 | 236 | 768 |
| 3 | dev_cli | `mnemoteca` | linux | function | 1 | `mnemoteca` | — | pass | 591 | 236 | 768 |
| 4 | dev_cli | `code-evolve` | linux | function | 1 | `code-evolve` | — | pass | 591 | 236 | 768 |
| 5 | local_ai | `lixbon` | linux | function | 1 | `lixbon` | — | pass | 591 | 234 | 768 |
| 6 | local_ai | `airdrop-llm` | linux | install | 2 | `omarchy-cluster` | fail | pass | 591 | 234 | 768 |
| 7 | local_ai | `tyloquant` | linux | function | 2 | `ggrun` | fail | pass | 591 | 234 | 768 |
| 8 | local_ai | `quill` | macos | install | 1 | `quill` | — | unknown | 399 | 234 | 768 |
| 9 | mcp_server | `iran-mcp` | linux | service | 1 | `iran-mcp` | — | pass | 591 | 185 | 768 |
| 10 | mcp_server | `wcode` | macos | service | 1 | `wcode` | — | pass | 399 | 185 | 768 |
| 11 | mcp_server | `memesh` | linux | service | — | `klypix-mcp` | fail | pass | 591 | 185 | 768 |
| 12 | mcp_server | `buddy` | linux | service | 1 | `buddy` | — | pass | 591 | 185 | 768 |
| 13 | gui | `mini-diarium` | linux | install | 1 | `mini-diarium` | — | pass | 591 | 113 | 768 |
| 14 | gui | `x11-calc` | linux | install | 1 | `x11-calc` | — | pass | 591 | 113 | 768 |
| 15 | gui | `djpdf` | linux | install | 1 | `djpdf` | — | pass | 591 | 113 | 768 |

`considered` 是通過硬條件的已驗證工具數；只傳了 `os`，所以它就是那個作業系統上的全部已驗證工具（Linux 591、macOS 399）。11 題命中第一名裡，有 6 題 Worker 只回了 1 個推薦（iran-mcp、wcode、buddy、mini-diarium、x11-calc、djpdf）。

## 第一名不是目標的 4 題

4 題的第一名都沒通過 L1（以下是 L1 給的理由，看的是那個工具上游的 README）：

| # | 目標 | 第一名 | 沒過的條件 |
|---|---|---|---|
| 1 | hako-code（沒進前 3） | camelid | 「只用 C 編譯器就能編」：camelid 是 Rust，前端還要 npm |
| 6 | airdrop-llm（第 2） | omarchy-cluster | 「兩台筆電透過家裡的 Wi-Fi 一起跑」：它的 README 說 Wi-Fi 只探測、不拿來推論，只用有線或 Thunderbolt |
| 7 | tyloquant（第 2） | ggrun | 「自己把 safetensors 量化」：ggrun 只啟動現成的 GGUF，沒有量化功能 |
| 11 | memesh（沒進前 3） | klypix-mcp | 「MIT 授權」：klypix-mcp 是 Apache-2.0（見下面的敏感度） |

共同點：第一名都是很接近的鄰居，滿足大部分條件，但漏掉了題目裡一個具體的條件。hako-code 的紀錄摘要本身就寫著「single-file C」，模型還是選了別的；它前兩次降級時的規則排序也沒選到它。

## 要一起看的事

- **題目有效性**：quill 對自己的題目是 `unknown`，不是 `fail`。L1 讀到它的 README 說公開的 macOS 版本「仍不支援」、各 App 的插入方式還在驗證，所以「在任何 App 的游標處插入」判不了；pickfit 是在 macOS 上驗證到 install。quill 是 hit@1，去掉它之後的數字列在上面。
- **敏感度（不是登記的計分）**：memesh 的需求原文只說「be open source」，但寫題目的模型在條件清單裡寫成「Open source under MIT license」。照登記的規則，L1 檢查的是條件清單，所以 klypix-mcp 因為 Apache-2.0 沒過。如果照需求原文判，它的其他 4 個條件都過，acceptable@1 會是 12/15。主要數字仍是 11/15。
- **降級**：我送出、輸入有效的 18 次呼叫中，有 3 次降級，都在 17:10–17:13 的 3 分鐘內（hako-code 的 `model_incomplete` 1 次與 Meta 回 404 1 次；orbit 17:12:50 的 1 次約 3.6 秒，原因沒存下），之後 15 次都沒有。hako-code 用的是第 3 次（第一個沒降級的）回應。同一段時間的一次 `muse-spark-1.3` 直接呼叫是成功的，404 是間歇的；Worker 對 404 的備援還在另一個分支上，沒有部署。
- **輸入長度**：`need` 最多 500 個字元。第一次寫的題目有 4 題超過（510–562 字元），超過的會被 Worker 以輸入驗證錯誤拒絕（orbit 送出兩次都被拒，其他 3 題還沒送）；這 4 題在得到任何回應之前加上長度提示重寫（README 變更紀錄 17:18）。真實的 agent 也可能碰到這個限制。
- **這次測試在正式 Worker 留下的紀錄**：`find` 事件的 `reporter` 欄位是空的（`X-Pickfit-Reporter` 只標 `report_outcome`），所以在 D1 裡和外部的查詢看起來一樣。這個測試在 D1 留下 18 筆 `find` 事件：17 筆的 `rec_id` 在 `responses/`，另 1 筆是 17:12:50 那次降級、沒有存下 `rec_id`；同一段時間還有其他 session 在呼叫，所以要用 `rec_id` 排除，不能用時間。

## 限制

- 樣本只有 15 題，信賴區間很寬；分層只有 3–4 題。
- **目錄小**：線上 768 筆，同類別 113–236 筆，同一個作業系統上 399–591 筆。目錄到上千筆時，同樣的題目會有更多相近的工具競爭，第一名更難命中；這次 4 題沒中第一名的，都是輸給很接近的鄰居。
- 題目照目標的 README 寫，用詞和條件來自工具自己的說法，比真實使用者的需求更具體、更貼近目標。機械檢查只擋工具名，以及和紀錄重複 5 個字以上的片段，擋不了同義的改寫。這讓命中偏高。
- 只傳 `need` 與 `os`，沒有傳結構化條件（`must_run_locally`、`budget` 等），所以 Worker 的硬條件篩選沒有發揮。真實的 agent 可能會傳。
- 寫題目和 L1 用同一個模型（`claude-opus-5-5`），可能有同樣的盲點。L1 只看上游 README 與 GitHub 授權，沒有實際安裝；條件清單可能比需求原文更嚴（見 memesh）。
- 每題只算一次回應，配對模型的隨機性沒有量。結果只代表這次的部署（資料 `acb3891c…`、11/2 17:10–17:23）。
- 這個測試只說明「目錄裡有」的情況；P6 輸題裡「目錄裡沒有」的那一部分，它完全沒有量。

## 花費

| 項目 | 花費 | 上限 |
|---|---|---|
| Anthropic（寫題目 19 次、L1 19 次） | $1.81 | $8 |
| Worker 的 Meta（17 次有 `rec_id` 的呼叫，依 D1 `events.meta_cost_usd`） | $0.66 | $3 |

都記在共用帳本 `~/.pickfit/ledger.sqlite` 的 `known-item-anthropic` 與 `known-item-worker`；細目在 `spend.json`。

## 可以怎麼引用

不放在結論的第一句。例如在 P6 結果之後補一段：「另一個探索性的小測試把目錄裡已驗證的 15 個工具，照它們的 README 寫成需求，`find_software` 在 11 題把目標排第一、13 題排進前 3（目錄 768 筆，題目比真實需求更具體，見 eval/known-item/results.md 的限制）。」
