# 給 agent 的說明

本專案原為參加 Meta Global AI Developer Hackathon（開發期間 2026-10-27 – 11-04 ET）所建，**黑客松已於 2026-11-04 結束**，目前已進入**賽後持續開發與擴充階段**（2026-11-15 更新）。

動手前先讀：

1. [docs/brief.md](docs/brief.md)：產品定位、目標與設計原則。
2. [docs/hackathon-rules.md](docs/hackathon-rules.md)：歷史文件（比賽期間的工作守則，僅供追溯）。
3. [docs/plan.md](docs/plan.md)：任務清單、歷史狀態紀錄，以及第 8 節「賽後階段更新」。

賽後階段的重要方針（2026-11-15 起）：

- **不再受黑客松時程與凍結限制**：沒有比賽截止日或功能凍結期限，也不再受賽期 credit 硬性額度上限綁定（帳本仍可作成本追蹤）。
- **API 切換為 Anthropic API**：解除「產品必須使用 Meta 模型」與「Anthropic 僅限評測」的限制，改以 **Anthropic API** 作為主要模型來源；**Modal** 平台仍有剩餘 API key 與沙盒（`ModalBox`）可持續使用。
- **收錄與驗證策略（Linux / CLI / MCP / Web 優先）**：優先擴大收錄 **Linux、CLI、MCP server 與網頁應用（Web Apps）**。CLI 與 MCP 工具在 Linux 沙盒驗證的結果與 macOS / Windows 高度一致，可在無需維護大量 Mac / Windows 實體機的情況下維持高驗證品質；暫不優先收錄驗證成本高的 macOS / Windows 桌面 GUI App。
- **保留歷史紀錄誠實性**：不要竄改任何過往 commit 時間、歷史紀錄或比賽期間的評測／帳本紀錄。
- **安全與隔離**：不要 commit API key 或其他機密；新增第三方程式碼、資料、素材前先確認授權；若執行評測，建資料與配對的 session 仍不讀 `eval/`。

賽前研究的位置記在 `CLAUDE.local.md`（不進 repo）。
