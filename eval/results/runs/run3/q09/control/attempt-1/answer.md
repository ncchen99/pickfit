我推薦 **[Backlog.md](https://github.com/MrLesk/Backlog.md)**。它是 MIT 授權、免費開源的工具，不需要帳號，可以離線使用，Mac 和 Linux 都能跑。

## 為什麼選它

- **每個任務是 repo 裡的一個 `.md` 檔**（放在 `backlog/` 目錄下，例如 `task-1 - 標題.md`），可以直接 diff、review、merge，跟著 git 版本控制。
- **人和 agent 用同一套 CLI**：可以新增、列出、改狀態、封存任務。
- **列表能輸出 JSON**：README 寫明 `backlog task list` 支援 `--json`。
- **預設不會自動 commit**，什麼時候 commit 由你決定。要自動 commit 的話，在設定檔加 `auto_commit: true`。
- 可以透過 MCP 接 agent，也可以把使用說明寫進 `CLAUDE.md` / `AGENTS.md`，Claude Code 和 Codex 都適用。另外附終端機看板，`backlog browser` 會開網頁介面。

## 安裝（擇一）

```bash
brew install backlog-md      # Mac / Linux(Homebrew)
npm i -g backlog.md          # 有 Node 就能用
bun add -g backlog.md
```

## 第一次使用

```bash
cd your-repo
backlog init "My Project"            # 會問要不要設定 MCP 或 agent 說明檔，兩種都可以選

backlog task create "修正登入逾時"
backlog task edit TASK-1 -d "說明" --ac "驗收條件"

backlog task list                    # 給人看
backlog task list -s "To Do" --json  # 給 agent 讀

backlog task edit TASK-1 -s Done     # 關閉任務（標成完成）
backlog task archive TASK-2          # 取消、重複或無效的任務

git add backlog && git commit -m "Add tasks"
```

**假設和要確認的地方：**
- README 沒有寫出「關閉」的確切指令。上面的 `edit -s Done` 是我根據它的狀態欄位推斷的，請先跑 `backlog task edit --help` 確認。
- `--json` 是 README 寫的，但舊版可能只有 `--plain`。安裝後也請用 `--help` 確認一次。
- 如果 agent 是跑在離線環境，可以在 config 設 `remote_operations: false`，這樣它就不會去 git fetch。

建議在 `AGENTS.md`（Codex 會讀）和 `CLAUDE.md` 都寫一段規則，例如：「用 `backlog task list --json` 查任務，完成後把狀態設成 Done 並 commit」。這樣兩個 agent 的做法才會一致。

## 其他選擇

- **[Beads (`bd`)](https://github.com/gastownhall/beads)**：專門為 AI agent 設計，`bd ready --json` 很好用，也支援任務之間的相依關係。但現在的版本主要資料存在 Dolt 資料庫（`.beads/embeddeddolt/`），`issues.jsonl` 只是匯出檔。早期版本是 JSONL 加 SQLite，資料來源是 JSONL；現在改成 Dolt，所以不符合「純文字檔才是資料來源」這個條件。如果你需要相依關係圖和多個 agent 同時領任務，可以考慮它。安裝：`brew install beads`，然後 `bd init`。
- **todo.txt-cli**：最單純的純文字工具，但沒有 JSON 輸出。
- **git-bug**：離線、分散式，但資料存在 git 物件裡，不是你能直接打開的文字檔。

Sources:
- [Backlog.md (MrLesk) GitHub](https://github.com/MrLesk/Backlog.md)
- [Beads GitHub](https://github.com/steveyegge/beads)
- [Beads on pkg.go.dev](https://pkg.go.dev/github.com/steveyegge/beads@v0.48.0)
- [Better Stack: Beads guide](https://betterstack.com/community/guides/ai/beads-issue-tracker-ai-agents/)
- [Ian Bull: Beads](https://ianbull.com/posts/beads/)
- [Beads TIL (2026/01)](https://divyavanmahajan.github.io/til/2026/01/beads-issue-tracker-for-agents/)
- [SourcePulse: Backlog.md](https://www.sourcepulse.org/projects/11036095)