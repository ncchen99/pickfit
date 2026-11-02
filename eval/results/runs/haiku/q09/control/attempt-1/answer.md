**主要建議：Taskwarrior**，放在 repo 裡用 `.task/` 目錄存資料，並用 `task export` 輸出 JSON 給 agent 讀。它是免費、開源、離線、不需帳號的成熟 CLI，支援 macOS 與 Linux。

*假設：你說的「純文字」指資料能用文字編輯器讀、能進 git diff，不要求每個任務是獨立的 Markdown 檔。*

## 安裝

- **macOS**：`brew install task`
- **Linux**：Debian/Ubuntu 可用 `sudo apt install taskwarrior`，但套件版本可能較舊。如果需要新版，到官方 GitHub release 下載。
- **驗證**：`task --version`

## 第一次設定（在 repo 根目錄）

1. 建立 `.taskrc`，內容至少包含：
   ```
   data.location=.task
   confirmation=off
   ```
   `data.location` 的相對路徑是否會相對於 repo 根目錄解析，我沒有實測。若不是，改用絕對路徑，或改用下一步的環境變數方式。
2. 讓 Taskwarrior 讀這份設定，最簡單是在 shell 或 direnv 的 `.envrc` 裡加：
   ```
   export TASKRC="$PWD/.taskrc"
   ```
   這樣你和 agent 在同一個 repo 內執行 `task`，都會讀到同一份資料。
3. 把資料納入版控。建議在 `.gitignore` 加入 `.task/*.lock`、`.task/undo.data`、`.task/backup.data`，然後提交 `.taskrc` 與 `.task/pending.data`、`.task/completed.data`。

## 常用指令

- 新增：`task add project:core +agent "修正登入錯誤"`
- 列出（人看）：`task list`
- 列出（給 agent）：`task rc.json.array=on export status:pending`
- 關閉：`task <id> done`

給 agent 的建議：在指令前加 `rc.confirmation=off rc.verbose=nothing`，避免互動提示和多餘輸出干擾解析。

## 需要注意的點

- 兩個 agent 同時改同一任務時，可能產生 git 合併衝突。資料檔是一行一個任務，衝突範圍通常不大，但仍需要手動解決。
- 不要使用 `task sync`，那是連線到伺服器的功能，與你的離線需求不符。
- Taskwarrior 的資料檔是它自己的格式（每行一筆 JSON），人可以讀，但不是 Markdown。如果你堅持「一任務一個 Markdown 檔」，見下方替代方案。

## 替代方案：Backlog.md

[Backlog.md](https://github.com/MrLesk/Backlog.md) 把任務存成 repo 裡的 Markdown 檔，並提供 MCP 給 agent 使用，安裝可用 `brew install backlog-md` 或 `bun i -g backlog.md`。不過我在搜尋結果中**沒有找到它的 JSON 輸出選項**，因此它能否滿足你的 JSON 需求尚未確認。若你選它，請先查閱其 CLI 文件（CLI-INSTRUCTIONS.md）確認。

Sources:
- [Taskwarrior export 文件](https://taskwarrior.org/docs/commands/export.html)
- [Taskwarrior export 文件（另一頁）](https://taskwarrior.org/docs/commands/export/)
- [taskwarrior.utils（說明 export 輸出為 JSON 並可重導向至檔案）](https://github.com/enricoschumann/taskwarrior.utils)
- [Backlog.md（MrLesk）](https://github.com/MrLesk/Backlog.md)