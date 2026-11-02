# 推薦：Backlog.md（指令是 `backlog`）

我沒有在這台機器上安裝或執行它。以下內容來自官方 README（2026-11 查閱）。

**為什麼適合你：**
- **純文字存在 repo 裡：** 每個任務是 `backlog/` 資料夾下的一個 Markdown 檔，直接用 git 版本控制，diff 和 code review 都看得懂。
- **新增、列出、關閉：** 用 `task create`、`task list`、`task edit -s Done` 這幾個指令。
- **JSON 輸出給 agent：** `task list`、`task view`、`search` 都支援 `--json`。輸出是一份有版本號的 JSON（schema version 1），錯誤訊息走 stderr 並回傳非 0 exit code，適合 agent 解析。
- **兩邊 agent 都能用：** `backlog init` 會產生 agent 指示檔。另外有 MCP server，Claude Code 和 Codex 都有官方的一行設定指令。
- **符合你的條件：** MIT 授權、免費、不用帳號、完全離線，macOS 和 Linux 都能跑。

## 安裝（擇一）
```bash
brew install backlog-md      # macOS / Linuxbrew
npm i -g backlog.md          # 需要 Node
bun add -g backlog.md        # 需要 Bun
```

## 第一次使用
```bash
cd your-repo
backlog init "My Project"                 # 建立 backlog/ 和 agent 指示檔
backlog task create "修正登入逾時"          # 新增任務，會拿到 ID，例如 TASK-1
backlog task list                         # 給人看
backlog task list --json                  # 給 agent 讀
backlog task list --json | jq '.tasks[] | .id'
backlog task edit TASK-1 -s Done          # 關閉（改成最終狀態 Done）
backlog task archive TASK-1               # 取消、重複或無效的任務用封存
git add backlog && git commit -m "tasks"
```
ID 前綴以 `init` 實際產生的為準，例如 `TASK-` 或 `BACK-`，可以用 `--task-prefix` 自訂。

README 沒有直接寫出「改成 Done」的完整指令。上面的 `-s Done` 是我依 `edit` 指令的語法推斷的。第一次用時請先跑 `backlog task edit --help` 確認。

## 讓 agent 使用（兩種方式擇一）
- **只用 CLI（較簡單）：** 在 `CLAUDE.md` 和 `AGENTS.md` 寫上「任務用 `backlog` 管理，先執行 `backlog instructions overview`；讀取請用 `--json`」。`init` 產生的指示檔大致就是這個內容。
- **用 MCP：**
  ```bash
  claude mcp add backlog --scope user -- backlog mcp start
  codex mcp add backlog -- backlog mcp start
  ```

## 其他選項
我先查了 pickfit 已實測的工具庫，結果沒有符合這個需求的工具，所以以上推薦和下面的選項都是從網路資料找的，pickfit 沒有驗證過。
- **Beads（`bd`）：** 專為 coding agent 設計，指令有 `--json`。不過新版的儲存後端已改成 Dolt 資料庫。舊版是把 JSONL 存在 `.beads/`。所以它不符合「純文字檔」這個條件，我才放在第二順位。
- **minibeads：** 用 Rust 重寫的 Beads，只用 `.md` 檔儲存，比較符合純文字需求。但它不是官方專案，使用者也少。
- **todo.txt-cli：** 最單純的純文字格式，但沒有 JSON 輸出，agent 要自己解析。

Sources:
- [MrLesk/Backlog.md (GitHub)](https://github.com/MrLesk/Backlog.md)
- [Backlog.md docs search (Algolia)](https://docsearch.algolia.com/mcp/docs/repo/mrlesk/backlog.md)
- [beads v0.52.0 (pkg.go.dev)](https://pkg.go.dev/github.com/steveyegge/beads@v0.52.0)
- [minibeads README](https://docs.rs/crate/minibeads/latest/source/README.md)
- [bitspace/beads fork](https://github.com/bitspace/beads)