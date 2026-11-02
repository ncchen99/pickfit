## 主要推薦：Backlog.md

我沒有找到完全符合所有條件、且已驗證 JSON 輸出的工具。pickfit 的 18 個候選都不符合，只提到 Taskwarrior，但它是 pickfit 未驗證的選項。在可查到的工具中，**Backlog.md** 最接近你的需求：

- 任務存成 repo 裡的 Markdown 檔（放在 `.backlog` 資料夾），直接用 git 版本控制。
- 有命令列介面，可新增、列出、搜尋任務。
- MIT 授權，免帳號，本機執行，可離線使用。
- 可用 npm、Bun 或 Homebrew 安裝。

**未確認的部分：JSON 輸出。** 我查到的資料沒有提到 JSON 輸出的參數。來源是 [MrLesk/Backlog.md](https://github.com/MrLesk/Backlog.md)，README 與 CLI 說明文件裡有指令細節，你可以先確認。如果沒有 JSON 輸出，agent 也能直接讀 Markdown 檔，因為它們本來就是純文字。

### 安裝（以下為假設的步驟，請先對照 README 確認指令）

```bash
# 擇一：Homebrew
brew install backlog-md

# 或 npm（需要 Node.js）
npm i -g backlog.md
```

### 第一次使用

```bash
cd your-repo
backlog init                              # 在 repo 中初始化（指令名稱請確認）
backlog task create "修正登入逾時的問題"  # 新增任務
backlog task list -s "To Do"              # 列出待辦
backlog --help                            # 查看關閉任務與 JSON 相關參數
```

建議初始化後，把 `backlog` 的使用說明加到 `AGENTS.md`（Codex 會讀）和 `CLAUDE.md`（Claude Code 會讀），讓兩個 agent 都知道要用這個 CLI 管理任務。

## 其他候選

- **Beads（`bd`）**：專為 coding agent 設計，指令支援 `--json`，安裝方式有 Homebrew、npm、Go 與 curl 腳本。但它較新的版本改用 Dolt 資料庫儲存，不是純文字，跟你的需求有衝突。要用的話先確認它目前是否仍提供可 commit 的 JSONL 檔。來源：[pkg.go.dev 版本紀錄](https://pkg.go.dev/github.com/steveyegge/beads@v0.54.1)。
- **todo.txt（todo.sh）**：最純的純文字格式，但原生沒有 JSON 輸出，你需要自己寫小腳本轉換。我這次沒有驗證它的現況。
- **Taskwarrior**：有 JSON 匯出，但資料存在自己的資料目錄，不適合放進 repo。pickfit 未驗證。

## 我的假設

- 你要的是單一 repo 的任務清單，不是跨專案的看板。
- 「Mac 和 Linux 都能跑」指的是 CLI 本身，不需要 GUI。
- 我沒有實際執行任何安裝或指令，以上步驟都需要你自己確認。

Sources:
- [MrLesk/Backlog.md](https://github.com/MrLesk/Backlog.md)
- [Beads 版本與安裝資訊（pkg.go.dev）](https://pkg.go.dev/github.com/steveyegge/beads@v0.54.1)