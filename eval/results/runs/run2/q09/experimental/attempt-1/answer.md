我推薦 **[Backlog.md](https://github.com/MrLesk/Backlog.md)**（MIT 授權，指令是 `backlog`）。我沒有在這台機器上執行任何指令，以下內容來自官方文件和 release notes。

## 為什麼選它
- **純文字放在 repo 裡**：每個任務是一個 `.md` 檔，放在 repo 的 `backlog/` 目錄，直接跟著 git commit、diff 和 merge，不需要資料庫。
- **人和 agent 都能新增、列出、關閉任務**。
- **可以輸出 JSON**：`task list`、`task view`、`search` 都支援 `--json`。輸出格式是 `{ "schemaVersion": 1, "kind": "task-list", "tasks": [...] }`。出錯時錯誤訊息寫到 stderr，回傳非 0，stdout 保持空白，agent 解析起來不會被雜訊干擾。另外還有 `--plain` 輸出精簡純文字，但不能和 `--json` 同時用。
- **兩個 agent 都照顧到**：`backlog agents --update-instructions` 會把使用說明寫進 `CLAUDE.md` 和 `AGENTS.md`，Claude Code 和 Codex 都讀得到。也可以選擇接 MCP。
- **免費、不用帳號、離線可用**，Mac 和 Linux 都能跑。它也有本機 Web 看板，只綁在 127.0.0.1，用不用都可以。

## 安裝（需要 Node.js）
```bash
npm i -g backlog.md
```
注意套件名稱是 `backlog.md`。官方特別提醒，`npx backlog` 會裝到另一個不相關的套件。官方文件只寫了 npm 這個方法；Homebrew（`brew install backlog-md`）和 Bun 的安裝方式是我自己的印象，用之前請先確認。

## 第一次使用
```bash
cd your-repo
backlog init "my-project"            # 或用 backlog init --defaults 跳過互動問答
backlog agents --update-instructions # 把用法寫進 CLAUDE.md / AGENTS.md

backlog task create "修正登入逾時"     # 新增
backlog task list --plain             # 列出（人看）
backlog task list --status "To Do" --json   # 列出（給 agent）
backlog task edit 1 -s Done           # 關閉（假設：-s 是設定狀態的參數，請用 backlog task edit --help 確認）
backlog task archive 1                # 封存（可選）

git add backlog/ CLAUDE.md AGENTS.md && git commit -m "Add backlog"
```
如果想讓它每次改動都自動 commit，可以跑 `backlog config` 開啟 auto-commit。

一個假設要先說明：官方 CLI 說明裡沒有直接寫出「把狀態改成 Done」的參數。`-s Done` 是我記得的用法，請以你安裝版本的 `--help` 為準。

## 其他選項（都不如 Backlog.md 貼合）
- **[Beads (`bd`)](https://github.com/steveyegge/beads)**：專門為 AI agent 設計的 issue tracker，支援 JSON。缺點是現在的主要儲存用 Dolt 資料庫（放在 `.beads/embeddeddolt/`），`issues.jsonl` 只是匯出檔。這不符合你「純文字檔就是資料本身」的要求。
- **git-bug**：離線、不用帳號，但資料存在 git 內部物件裡，不是 repo 裡看得到的檔案。
- **todo.txt-cli**：純文字，但不能輸出 JSON。

我也查了 pickfit 的已驗證工具庫，裡面沒有符合這個需求的工具。它回傳的是 Orbit 這類 agent 任務排程工具，所以上面的推薦都不是 pickfit 驗證過的。

Sources:
- [Backlog.md CLI-INSTRUCTIONS](https://raw.githubusercontent.com/MrLesk/Backlog.md/main/CLI-INSTRUCTIONS.md)
- [Backlog.md v1.52.0 release](https://github.com/MrLesk/Backlog.md/releases/tag/v1.52.0)
- [Backlog.md docs (Algolia)](https://docsearch.algolia.com/mcp/docs/repo/mrlesk/backlog.md)
- [steveyegge/beads](https://github.com/steveyegge/beads)
- [beads on pkg.go.dev](https://pkg.go.dev/github.com/steveyegge/beads@v1.2.2)