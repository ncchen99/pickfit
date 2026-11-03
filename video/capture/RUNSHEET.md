# 錄影流程：Claude app 與 MangoDisk（念誠操作，我錄螢幕）

Claude 不能用 Computer Use 操作 Claude app 自己，所以這段由念誠操作；我從這邊用 `screencapture -v` 錄整個螢幕，剪輯時再裁切、加速並標倍速。同意提示一律照實按，不加速。

## 準備（約 1 分鐘）

- 開「勿擾模式」，關掉不需要的視窗；Claude app 視窗放大到幾乎全螢幕，側欄收起，字放大一到兩級（⌘＋）。
- 已準備好：
  - `~/pickfit-demo`：新的工作資料夾，pickfit MCP 已加入，請求帶 `X-Pickfit-Reporter: demo`，所以這次的查詢與 `report_outcome` 不會算進計分。
  - `.claude/settings.local.json` 預先允許 pickfit 的四個工具與之後的 gutenberg 工具，只有會改電腦的指令會跳出同意。
  - `~/Desktop/Old Exports`：四個大檔（共約 8.7 GB，全是 0 的假檔）和一對重複的 PDF，給 MangoDisk 掃。

## 第 1 段：主線（MangoDisk）

1. Claude app 開新的 Code session，資料夾選 `~/pickfit-demo`，權限模式選 **Ask**（預設，會問）。
2. 輸入：`Install MangoDisk for me, the one pickfit tested.`
3. agent 會先說已知漏洞，再提出 `brew …` 指令：按 **Allow**（之後它可能再要 `open …`：也按 Allow）。
4. MangoDisk 打開後：側欄 **Large File Cleanup** → 選資料夾 `Desktop/Old Exports` → 開始掃描 → 結果列出大檔 → 勾四個大檔 → 清除。（系統問能不能存取桌面，按允許；Full Disk Access 之類的系統設定不用開。）
5. 回到 Claude：`It worked, I cleared about 8 GB. Let pickfit know.`

## 第 2 段：agent 也在找軟體（另開一個新 session，同一個資料夾、Ask 模式）

6. 輸入：`Has the latest npm supply-chain attack reached my Mac? Find a tool that checks for it.` → 同意它跑掃描 → 看到結果。
7. 同一個 session 輸入：`Give yourself a tool for searching and reading Project Gutenberg books, then read me the opening of a book about the sea.` → 同意安裝與加入 → 它用新工具讀出開頭。如果它說要重開 session 才看得到新工具，照它說的做（我們剪輯時處理）。

完成後回到這個對話告訴我「錄完了」，我停止錄影。之後：

- `~/Desktop/Old Exports` 的大檔被 MangoDisk 清掉後會在垃圾桶，要不要清空由你決定。
- MangoDisk 1.2.2 會在 `~/Applications`，原本 `/Applications` 的 1.1.7 沒動。
