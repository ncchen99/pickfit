# pickfit

一個不屬於任何一家的軟體顧問：主動找出默默無聞、但品質好的軟體，實際驗證過、整理好，讓每個人的 AI agent 都能推薦、安裝並帶人上手。

要做什麼、為什麼做、怎麼做，見 [docs/brief.md](docs/brief.md)。

## 關於黑客松

本專案參加 [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon)（開發期間 2026-10-27 – 11-04 ET）。

- **這個 repo 只包含比賽期間的成果**，建立於 2026-10-28。
- **賽前做過的事**：題目構想、使用者與市場研究、資料欄位與評測題目的草稿。這些資料**不在這個 repo 裡**，也不是要展示的作品。
- 所有程式碼均於黑客松期間開發。

規則與做法見 [docs/hackathon-rules.md](docs/hackathon-rules.md)。

## 非 Meta 模型產生的內容

產品的發現、抽取、驗證、配對與計分都用 Meta 模型。例外如下，每筆都在資料裡記下產生它的模型：

- **工具頁的功能說明**（`usage_guide`：功能的白話標題、已驗證功能的使用步驟、安裝後怎麼打開）：2026-11-02 改版工具頁時，已有的 667 筆紀錄由 Anthropic 的 `claude-opus-5-5` 補產生（`usage_guide.model`）。內容只根據紀錄與驗證 run 已有的資料改寫；程式只接受 run 驗證過的功能有步驟。產生程式 `pickfit/usage_guide.py` 預設用 Meta 模型，之後的新紀錄用 Meta 模型產生。
- **網頁的繁中翻譯**：見下一節。
- **評測**：受測 agent 與部分評分用 Anthropic 模型，不屬於產品流程。

## 網頁的雙語（英文、繁體中文）

產品網頁可以切換英文與繁體中文（右上角的切換，或 `?lang=zh-TW`；之後記在 cookie，沒選過就看瀏覽器語言）。只有網頁是雙語的：MCP 工具、`find_software` 的配對與每一步驗證都照舊用英文資料和 Meta 的模型。

- 介面文字在程式裡寫成 `L('English', '中文')`（`worker/src/i18n.ts`）。
- 每款工具的說明（摘要、功能、安裝步驟的用途、測試紀錄的註記）由 `scripts/translate_zh.py` 用 Claude（Anthropic API）翻成繁中，存在 `data/i18n/zh-TW/<slug>.json`；紀錄本身不動。網頁只在英文原句完全相同時換成中文，所以紀錄改了、還沒重翻的句子會顯示新的英文，不會顯示過期的翻譯。指令、名稱、網址與程式判斷用的值永遠不翻。
- 搜尋時模型拿到的內容和英文頁完全一樣；配對當下產生的理由句子仍是英文。
