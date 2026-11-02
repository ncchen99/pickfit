我推薦 **Backlog.md**（[MrLesk/Backlog.md](https://github.com/mrlesk/backlog.md)），它最符合你的需求。每個任務是 repo 裡 `backlog/` 資料夾下的一個 Markdown 檔，直接跟著 git 版本控制。它是 MIT 開源、免費，不用帳號，可以離線用，Mac 和 Linux 都能跑。

選它的原因：

- **純文字**：任務就是普通的 `.md` 檔，你可以手動編輯，在 PR 裡看 diff，也能直接 grep。
- **給 agent 讀的 JSON**：`task list`、`task view` 和 `search` 都支援 `--json`。成功時 stdout 只輸出一份 JSON；出錯時訊息寫到 stderr，回傳非零 exit code，stdout 留空，所以 agent 解析起來不會出錯。
- **本來就是給人和 AI 一起用的**：它內建 MCP server，文件裡有 Claude Code 和 Codex 的設定方式。還有一個 `agents` 指令，可以把使用說明寫進 `CLAUDE.md` 和 `AGENTS.md`。
- 附帶終端機 Kanban 看板（`backlog board`）和本機網頁介面（`backlog browser`），想用再用。

## 安裝（擇一）

需要先有 Node.js 或 Bun：
```bash
npm i -g backlog.md
# 或
bun add -g backlog.md
```
Mac 也可以用 Homebrew：
```bash
brew install backlog-md
```

## 第一次使用

```bash
cd your-repo
backlog init "My Project"        # 建立 backlog/ 資料夾，會互動式詢問設定（包括要不要寫 agent 說明檔）

# 新增
backlog task create "修正登入逾時" -d "session 30 分鐘就掉"

# 列出（給人看 / 給 agent 讀）
backlog task list --plain
backlog task list --json
backlog task 1 --json            # 單一任務

# 關閉
backlog task edit 1 -s Done      # 標成完成
backlog task archive 1           # 或者封存

git add backlog && git commit -m "Add tasks"
```

## 讓 agent 也會用

- 最簡單的做法：在 `CLAUDE.md` 或 `AGENTS.md` 加一句「任務一律用 `backlog` CLI 管理，讀取時加 `--json`」。也可以用 `backlog agents` 自動產生這段說明。
- 如果要接 MCP：
  ```bash
  claude mcp add backlog --scope user -- backlog mcp start
  codex mcp add backlog backlog mcp start
  ```

上面的旗標和子指令是照我記得的文件寫的，我沒有在你的機器上跑過。各版本之間可能有出入，第一次用請先跑 `backlog --help` 和 `backlog task --help` 對照一下。

## 其他選項

- **Beads（`bd`）**（[steveyegge/beads](https://github.com/steveyegge/beads)）：專門為 coding agent 設計，有任務依賴關係，`bd ready` 會列出目前沒被卡住、可以做的任務，所有指令都支援 `--json`。缺點是新版改用 Dolt 資料庫當主要儲存，JSONL 只是為了能放進 git 而另外匯出的格式，所以不算你要的「純文字為主」，也比較複雜。如果任務之間依賴關係很多，可以考慮它。安裝方式：`brew install beads` 或 `npm i -g @beads/bd`，然後 `bd init`。
- **todo.txt-cli**：最簡單的純文字工具，但沒有 JSON 輸出，對 agent 不夠友善。
- **git-bug**：離線、分散式，但資料存在 git 物件裡，不是你能直接打開的文字檔，所以不符合你的需求。

我的假設是：你想要「一個任務一個檔、可以手動編輯、PR 看得到 diff」，而且環境裡可以裝 Node 或 Bun。如果你不想裝 Node，請告訴我，我可以改推薦單一執行檔的工具。

Sources:
- [Backlog.md docs (Algolia index)](https://docsearch.algolia.com/mcp/docs/repo/mrlesk/backlog.md)
- [Backlog.md on awesome.ecosyste.ms](https://awesome.ecosyste.ms/projects/github.com%2Fmrlesk%2Fbacklog.md)
- [beads v0.54.1 on pkg.go.dev](https://pkg.go.dev/github.com/steveyegge/beads@v0.54.1)
- [beads v0.49.5 on pkg.go.dev](https://pkg.go.dev/github.com/steveyegge/beads@v0.49.5)
- [Beads Integration — Technical Guide](https://brenner-axiom.codeberg.page/beads-technical-guide/)