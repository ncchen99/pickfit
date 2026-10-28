# 給 agent 的說明

本專案正在參加 Meta Global AI Developer Hackathon（開發期間 2026-10-27 – 11-04 ET）。

動手前先讀：

1. [docs/brief.md](docs/brief.md)：這次要做什麼、目標、範圍、時程與待決定事項。
2. [docs/hackathon-rules.md](docs/hackathon-rules.md)：比賽規則，特別是第 9 節的工作守則。
3. [docs/plan.md](docs/plan.md)：任務清單，現在做到哪、下一步做什麼、花費守則。

最重要的守則：

- 不要竄改任何時間紀錄（commit 時間、歷史、檔案時間），也不要把賽前資料寫成比賽期間的成果。
- **這個 repo 只放比賽期間的成果。** 不要把賽前的研究、規格、評測題目或素材複製進來；需要參考時，只取知識，不搬檔案。
- 所有程式碼都在開發期間內寫並 commit；commit 要小而頻繁。
- 產品必須使用 Meta 的模型；新增第三方程式碼、資料、素材前先確認授權。
- 不要 commit API key 或其他機密。
- 建資料（發現、抽取、驗證、計分）的 session 不讀 `eval/`，避免照著評測題目準備資料；只有評測執行與評分讀。

賽前研究的位置記在 `CLAUDE.local.md`（不進 repo）。
