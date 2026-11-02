我推薦 **Beads（指令名稱 `bd`）**。如果你比較在意任務檔要讓人直接閱讀，可以改用 **Backlog.md**。

先說明查證範圍：pickfit 已經實際裝過測試的工具裡，沒有一個符合「存在 repo 裡、輸出 JSON 給 agent 讀」這個需求（18 個候選都不合）。所以下面兩個都**沒有經過 pickfit 安裝驗證**，資料來自網路搜尋。我沒有在你的機器上執行任何指令。

## 主要推薦：Beads（`bd`）

- **為什麼適合你：** 它本來就是設計給 coding agent 用的 issue tracker。任務存成 repo 裡的 `.beads/issues.jsonl`，這個檔案就是正本，會跟著 git commit。本機另外有一個 SQLite 快取，已經加進 gitignore，不會進 repo。
- **JSON 輸出：** `bd list`、`bd show`、`bd update`、`bd close` 都能加 `--json`，agent 可以直接讀。
- **多個 agent 同時用：** 從 v0.20 開始，任務 ID 從流水號改成短 hash，Claude Code 和 Codex 在不同 branch 同時新增任務也不會撞號。`bd init` 還會設定 JSONL 的 merge driver，減少合併衝突。
- **授權與平台：** MIT 授權，免費，不用帳號，可以離線用，Mac 和 Linux 都能跑。
- **取捨：** 檔案是 JSONL，不是 Markdown。人可以讀，但不太適合手動編輯，主要還是透過 CLI 操作。

### 安裝（以下三種擇一）
```bash
# 方法 A：有 Go 的話最通用，Mac / Linux 都適用
go install github.com/steveyegge/beads/cmd/bd@latest

# 方法 B：用 Homebrew
#   README 裡有 brew 的安裝方式，但 tap 名稱可能改過，請以官方 README 為準

# 方法 C：官方 curl 安裝腳本
#   會把腳本直接 pipe 進 shell 執行，建議先打開來看過內容再跑
```
官方 repo：https://github.com/steveyegge/beads

### 第一次使用
```bash
cd your-repo
bd init                       # 建立 .beads/，裝好 git hooks 和 merge driver
                              # 給 agent 跑、不想要互動提示時用 bd init --quiet
bd create "修正登入逾時"       # 新增任務
bd list                       # 給人看的列表
bd list --json                # 給 agent 讀的 JSON
bd close <id>                 # 關閉任務
git add .beads && git commit -m "add tasks"
```
接著在 `CLAUDE.md` 和 `AGENTS.md`（Codex 會讀這個檔）各加一行，例如：「用 `bd` 管理任務，不要另寫 markdown 計畫；查詢時加 `--json`」。在新 clone 下來的 repo 裡跑 `bd init`，它會從 JSONL 匯入現有的任務。

**需要你自己確認的地方：** 我查到的資料是 pkg.go.dev 上幾個舊版本（v0.17 到 v0.25）的說明。Beads 版本更新很快，儲存後端和安裝方式後來可能改過。安裝前請先看官方 README，確認任務還是存成 git 追蹤的純文字檔。如果已經不是，請改用下面的 Backlog.md。

## 替代方案：Backlog.md

- **特點：** 每個任務是一個 Markdown 檔（`task-<id> - <標題>.md`），放在 repo 裡的專用資料夾。人讀起來比 Beads 舒服，也有看板和 Web UI。MIT 授權。
- **跟 agent 的整合：** 初始化精靈可以直接幫 Claude Code 和 Codex 設定 MCP 連線，也可以改成寫指令說明到 `CLAUDE.md` / `AGENTS.md`。
- **取捨：** 需要 Node.js 或 Bun（Homebrew 和 Nix 也有提供）。我沒有查到 `list` 指令能輸出 JSON。它的 agent 介面主要是 MCP 和純文字輸出，所以如果你一定要 CLI 直接吐 JSON，Beads 比較符合。

```bash
npm i -g backlog.md           # 或 bun add -g backlog.md，或 brew install backlog-md
cd your-repo
backlog init "My Project"     # 精靈裡選擇要不要接 MCP
backlog task create "修正登入逾時"
backlog task list --plain
# 選用：讓 Claude Code 透過 MCP 使用
claude mcp add backlog --scope user -- backlog mcp start
```
官方 repo：https://github.com/MrLesk/Backlog.md

**怎麼選：** 想要 agent 讀到穩定的 JSON、多個 agent 平行作業不撞號，選 **Beads**。比較重視任務是能用人眼閱讀、手動編輯的 Markdown，選 **Backlog.md**。

Sources:
- [pkg.go.dev – beads v0.20.0](https://pkg.go.dev/github.com/steveyegge/beads@v0.20.0)
- [pkg.go.dev – beads v0.17.7](https://pkg.go.dev/github.com/steveyegge/beads@v0.17.7)
- [pkg.go.dev – beads v0.21.1](https://pkg.go.dev/github.com/steveyegge/beads@v0.21.1)
- [pkg.go.dev – beads v0.25.0](https://pkg.go.dev/github.com/steveyegge/beads@v0.25.0)
- [MrLesk/Backlog.md](https://github.com/MrLesk/Backlog.md)
- [SourcePulse – Backlog.md](https://www.sourcepulse.org/projects/11036095)