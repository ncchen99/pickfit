## 推薦：Backlog.md（`backlog` 指令）

我假設你要的是：每個任務都是 repo 裡的一個檔案，直接 `git commit` 就能進版控，不需要另外的資料庫或同步服務。照這個條件，Backlog.md 最合適：

- **純文字**：每個任務是一個 `.md` 檔，放在 `backlog/` 資料夾。git diff 看得懂，衝突也能手動合併。
- **輸出 JSON**：`task list`、`task view`、`search` 等指令都支援 `--json`。Agent 讀到的是乾淨的 JSON，沒有互動提示。
- **專為 agent 設計**：初始化時可以幫你寫好給 Claude Code / Codex 的使用說明，或改用 MCP 連接。
- **授權與離線**：MIT 授權，官方標榜「no server, no account, no telemetry」。可以離線使用，這是我從說明推斷的，官方沒有直接寫「offline」。
- **平台**：Mac 和 Linux 都能用，可以透過 Homebrew、npm、bun 或 nix 安裝。

### 安裝（擇一）
```bash
brew install backlog-md        # Mac / Linux（Linuxbrew）
npm i -g backlog.md            # 或用 Node
bun add -g backlog.md          # 或用 Bun
```
不想安裝也可以先試：`npx backlog.md init "My Project"`

### 第一次使用
```bash
cd your-repo
backlog init "My Project"
```
初始化精靈會問 AI 整合方式，有三個選項：寫 CLI 使用說明（官方推薦）、MCP、或略過。選 CLI 說明，它就會把用法寫進 agent 的指示檔，Claude Code 和 Codex 都能讀到。

```bash
# 新增
backlog task create "實作登入頁" 
backlog task edit BACK-1 -d "詳細說明" --ac "驗收條件"

# 列出（人看 / agent 讀）
backlog task list -s "To Do"
backlog task list --json
backlog task BACK-1 --json

# 關閉：改狀態為 Done；取消、重複或無效的任務用 archive
backlog task edit BACK-1 -s Done
backlog task archive BACK-2

git add backlog/ && git commit -m "update tasks"
```

如果想讓 Claude Code 透過 MCP 使用：
```bash
claude mcp add backlog --scope user -- backlog mcp start
```
Codex 的話，用 CLI 說明（AGENTS.md）通常就夠了。

**注意事項：**
- 我沒有在你的機器上實際跑過這些指令。`-s Done` 的寫法和 `--json` 支援的範圍，請用 `backlog task edit --help` 和 `backlog task list --help` 確認一次。
- 建議讓你和 agent 都透過 CLI 修改任務，不要直接手改 `.md` 檔，這樣檔案格式和 ID 才不會亂掉。

## 其他選項（以及為什麼不是首選）
- **Beads（`bd`）**：同樣是為 coding agent 設計，`--json` 支援完整。但目前的版本以 Dolt 資料庫為主要儲存，`.beads/issues.jsonl` 只是匯出檔，所以不是你要的「純文字跟著 git 走」。如果你更在意任務之間的相依關係，而不在意儲存格式，可以考慮。
- **todo.txt-cli**：純文字、非常簡單，但沒有 JSON 輸出。
- **Taskwarrior**：有 JSON 匯出，但資料預設不存在 repo 裡，不適合你的用法。

Sources:
- [MrLesk/Backlog.md (GitHub)](https://github.com/MrLesk/Backlog.md)
- [saada/Backlog.md fork](https://github.com/saada/Backlog.md)
- [Backlog quick reference skill](https://skills.cat/skills/yebot/rad-cc-plugins/plugins-backlog-md-cli-skills-backlog-quick-reference)
- [beads on pkg.go.dev](https://pkg.go.dev/github.com/steveyegge/beads@v0.54.1)
- [beads v0.58.0 release notes](https://newreleases.io/project/github/steveyegge/beads/release/v0.58.0)
- [beads skill (agentskills.so)](https://agentskills.so/skills/itechmeat-llm-code-beads)