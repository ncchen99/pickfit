## 推薦：Backlog.md（`backlog` CLI）

我認為 **Backlog.md** 最符合你的需求。說明一下：pickfit 的已驗證工具庫裡沒有這類工具，它回傳的結果都對不上。下面的資訊來自 Backlog.md 的官方 README，pickfit 沒有幫它做沙箱測試。我也只是提供建議，沒有在你的機器上執行任何指令。

**為什麼選它：**
- **純文字、放在 repo 裡**：每個任務是一個 Markdown 檔，預設放在 `backlog/` 目錄，直接跟 git 一起 commit、diff、merge。
- **人和 agent 都能用**：CLI 可以新增、列出、編輯和封存任務。官方也提供 MCP server，Claude Code 和 Codex 都有現成的接法。
- **能輸出 JSON**：`task list`、`task view`、`search` 等指令都支援 `--json`。
- **符合你的條件**：MIT 授權、免費開源，README 寫明「no server, no account, no telemetry」，可離線使用，Mac 和 Linux 都能跑。

### 安裝（三選一）
```bash
brew install backlog-md      # macOS / Linux 有 Homebrew 時
npm i -g backlog.md          # 有 Node.js 時
bun i -g backlog.md          # 有 Bun 時
```

### 第一次使用
```bash
cd your-repo
backlog init "My Project"    # 精靈會問要不要接 AI（可選 MCP、CLI + 指示檔，或略過）

backlog task create "修正登入逾時問題"
backlog task list                    # 給人看
backlog task list --json             # 給 agent 讀
backlog task list -s "To Do" --json  # 依狀態篩選
backlog task edit 1 -s "Done"        # 關閉任務
backlog task archive 1               # 封存（要還原用 backlog task restore）

git add backlog && git commit -m "Add tasks"
```
註：README 沒有直接列出 `edit -s "Done"` 和 `archive 1` 的完整寫法，這兩行是我依照 CLI 的慣例推測的。執行前請先用 `backlog task edit --help` 確認。

### 接上 agent（選用，建議用 MCP）
```bash
claude mcp add backlog --scope user -- backlog mcp start
codex mcp add backlog backlog mcp start
```
`backlog init` 會自動把使用說明寫進 `CLAUDE.md` 和 `AGENTS.md`，兩個 agent 都會知道怎麼操作任務。如果你不想用 MCP，也可以叫 agent 直接下 `backlog task list --json` 這類指令。

## 其他選項
- **Beads（`bd`）**：專門為 coding agent 設計，每個指令都支援 `--json`，還有 `bd ready --json` 可以列出目前能做的任務。不過最新版改用 Dolt 資料庫儲存，舊版才是把 JSONL 存在 `.beads/`。所以「純文字、跟 git 一起管」這點不如 Backlog.md 單純。如果你想試，請先確認你裝的是哪個版本的儲存方式。安裝方式：`brew tap steveyegge/beads && brew install bd`，或 `npm install -g @beads/bd`，再到專案裡執行 `bd init`。
- **todo.txt CLI**：最簡單、純文字，但沒有內建 JSON 輸出，也沒有幫 agent 準備的整合，不太適合你的用法。

Sources:
- [MrLesk/Backlog.md (GitHub)](https://github.com/MrLesk/Backlog.md)
- [Backlog.md on SourcePulse](https://www.sourcepulse.org/projects/11036095)
- [steveyegge/beads (GitHub)](https://github.com/steveyegge/beads)
- [beads on pkg.go.dev](https://pkg.go.dev/github.com/steveyegge/beads@v0.20.0)