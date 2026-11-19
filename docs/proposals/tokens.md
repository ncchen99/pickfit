# token 和模型用量

> 提案（2026-11-19）。總覽和共同規則在 [README.md](README.md)。

## 現況

11/15 以來，帳本（`~/.pickfit/ledger.sqlite` 的 `calls` 表）裡 Opus 共 2,016 次呼叫、US$52.6，Haiku 374 次、US$0.36。

依步驟分：verify US$19.7（733 次）、extract US$11.13、score-rubric US$4.10、web-operate US$3.80、gui-operator US$3.73、translate US$2.67、verify-judge US$1.81、usage_guide US$1.31、video-review US$1.28、video-edit US$0.99、feature-judge US$0.79、web-judge US$0.59。

一筆 CLI/MCP 紀錄約 US$0.40：

- 驗證 agent US$0.21，平均 7.7 輪。輸出占 43%，快取寫入占 38%。
- 抽取 US$0.09，rubric US$0.047，翻譯 US$0.025，判定 US$0.018，功能判定 US$0.011，使用說明 US$0.01。
- 網頁另外多 web-operate 約 US$0.17、web-judge 約 US$0.02。

判定類步驟加起來約 US$4.5，占 8.5%。花最多的是驗證 agent 和抽取，這兩個維持 Opus。

## 提案

### T1 預設模型改成 Opus（收錄前）

[meta.py:316-326](../../pickfit/meta.py) 在沒指定模型時讀 `PICKFIT_MODE`，沒設就用 `dev`，也就是 Haiku。watch 有釘死 Opus（[watch.py:72](../../pickfit/watch.py)），但 loop 照 skill 在本機跑的 `verify --batch` 沒帶 `--model prod`。帳本裡 11/16 有 243 次、11/17 有 24 次驗證呼叫用的是 Haiku，跟 11/17「不換模型」的決定相反。

改法：

- 沒指定時預設 `prod`（Opus）。要用 Haiku 就得明講 `--model dev` 或 `PICKFIT_MODE=dev`。
- 用 `dev` 跑時，在 stderr 印一行提醒，帳本照實記模型。
- 找出所有靠預設值的呼叫點，列在回報裡。測試裡本來就靠 dev 省錢的，改成明講。

驗收：單元測試涵蓋「沒設環境變數 → Opus」「`PICKFIT_MODE=dev` → Haiku」「明講 model 優先」。

### T2 多輪呼叫第一輪就快取（收錄前，改動小）

[anthropic_messages.py:369](../../pickfit/anthropic_messages.py) 目前要等出現 assistant 回合才自動快取，所以驗證 agent 第一輪送出的約 5.2K token 沒進快取。第二輪又要用全價重送一次。

改法：多輪的呼叫端（驗證 agent、GUI 操作員、網頁操作）從第一輪就在最後一個 user block 放 `cache_control`。單次呼叫（各種 judge、翻譯）不要加，因為快取寫入是 1.25 倍價，只呼叫一次反而比較貴。

驗收：

- 單元測試檢查第一輪的 payload 有 breakpoint，單次呼叫沒有。
- 回報寫出改動前後，第二輪預期的 `cache_read_input_tokens`。

估計省驗證費用約 10%，每次約 US$0.02。

### T3 Batch API（收錄前先做模組和兩個呼叫端）

Message Batches 半價，適合不急著要結果的步驟。新增 `pickfit/msg_batch.py`（不要叫 `batch.py`，`pickfit/verify/batch.py` 已經是 `verify --batch`）：

- 送出一批 request、輪詢狀態、取回結果，用 `custom_id` 對回原本的工作。
- 寫帳本時照 batch 價計費，`calls` 表加一欄標明是 batch。
- batch 不支援 `fallbacks` 參數。errored 或 expired 的結果改用一般 API 重送。
- 先接翻譯（`scripts/translate_zh.py` 和 `pickfit/i18n.py` 用到的翻譯呼叫）和使用說明（usage_guide）。
- 抽取和 rubric 先不要接。它們歸 [scoring.md](scoring.md)，等那邊重構完再接。

估計每筆省 US$0.06–0.085（15–20%），全部接完才有這個數字。翻譯和使用說明兩項先省約 US$0.018。

驗收：用假的 client 測送出、部分失敗、過期、重送、帳本計價。

### T4 驗證 agent 的 effort（先做比較工具，不改預設）

[agent.py:62](../../pickfit/verify/agent.py) 是 `REASONING_EFFORT = "medium"`。輸出約 55% 是 thinking，降到 low 每次約省 US$0.02–0.03，但可能影響判斷品質。

做一個離線比較工具（例如 `scripts/effort_compare.py`）：

- 從本機存下的驗證紀錄（`runs/` 底下的 report.json 和對話紀錄）取出每個決策點的對話歷史。
- 用 medium 和 low 各問一次「下一步要做什麼」，比較下一個動作是否一致。
- 印出一致率、不一致的例子、花費。

工具寫好、用假的 client 測過就好，不要真的跑。真的跑約 US$2，列在回報裡讓協調 session 決定。

### T5 判定類步驟

1. **「畫面上有沒有這段字」先跑 OCR。** 已經有 `marks.py` 的 OCR 和 [ocr_mac.swift](../../pickfit/verify/ocr_mac.swift)。OCR 找到了就不問模型，找不到才問。Linux 上用什麼 OCR（例如 tesseract）要確認授權和沙盒裡有沒有。這不是換模型，可以直接上，但要用已存的截圖測過，不能讓原本判「沒有」的變成「有」。
2. **CLI 判定不要同時送文字和截圖。** [judge.py:183-213](../../pickfit/verify/judge.py) 把同一份終端輸出用文字和 PNG 各送一次。有文字就只送文字，文字被截斷或有 TUI 畫面時才附截圖。
3. **便宜模型的離線比較工具（不改預設）。** 做一個工具（例如 `scripts/judge_compare.py`），拿已存的截圖和輸出，讓 Opus 和 Haiku 5.5 各判一次。對象是 GUI 開啟畫面的六種分類、CLI 判定的三種結果、網頁功能有沒有出現、影片審查的「看不看得到」。報告一致率，還有 Haiku 多判成「能用」的筆數。換模型的條件是這個數字要是 0，而且要念誠同意。工具寫好就好，不要真的跑。

### T6 GUI 操作員和網頁操作的輸入大小（做成可設定，預設不變）

- GUI 操作員把截圖放大 2 倍（[gui_operate.py:940](../../pickfit/verify/gui_operate.py)），另外 101 次裡有 45 次是額外的「aim」呼叫。先查放大的原因（小字？座標精度？）。可以改成只放大需要看清楚的區域，或在有 accessibility tree 時先用它找座標。
- 網頁操作每次送出的元素清單上限 12K 字元（[web_harness.py:48](../../pickfit/verify/web_harness.py)）。先拿掉看不見的元素、重複的文字、很長的 class 名稱，目標 7K 左右。

這兩項會影響操作的準確度。做成設定，預設維持現狀，回報裡寫出要怎麼離線比較。

## 之後再做（這次不實作）

- **README 沒有安裝步驟時會再抽一次**（[watch.py:873-883](../../pickfit/watch.py)，約 20% 的項目）。這段在 `watch.py`，等 throughput 的修改合併後再處理。做法是用便宜的規則先判斷 README 有沒有安裝段落，沒有的話一開始就把 INSTALL.md 或文件網站一起抓進來，只抽一次。
- 抽取和 rubric 改走 Batch API。

## 不做的事

驗證 agent、抽取、GUI 操作員、網頁操作、aim 都維持 Opus。這些步驟輸出的是動作或座標，程式沒辦法核對對錯。
