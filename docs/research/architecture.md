# 技術調研：pickfit 的架構與技術選型

2026-10-28 · 調研進行中。每完成一節就更新並 push；中途中斷時，以「目前的結論」為準。

需求來源：[docs/brief.md](../brief.md)、[docs/hackathon-rules.md](../hackathon-rules.md)。

---

## 0. 目前的結論

**狀態（2026-10-28 03:50 台北）**：調研剛開始。以下是動手前的**初步假設**，還沒有查證，之後會逐條改成有來源的結論。

| 問題 | 初步假設（未驗證） | 要查證的點 |
|---|---|---|
| A. 管道 | GitHub search API 當主幹；Show HN（官方 API）、Homebrew／PyPI 等套件資料、Hugging Face 補本地 AI 類；使用者貼連結當供給端入口 | 各管道條款、Threads API 能不能搜尋別人的貼文 |
| B. 品質 | 規則訊號（release、CI、文件、維護）＋ 沙盒驗證結果；知名度另外算 | Scorecard 對小專案的覆蓋率 |
| C. 沙盒 | Modal Sandbox 當主力（有比賽 credits） | 費用、啟動時間、能否限制網路；macOS 怎麼驗 |
| D. Meta 模型 | Muse Spark 做抽取、驗證判讀、配對；開放權重模型做初篩 | 官方文件中的實際能力（圖片、tool calling、JSON schema） |
| E. MCP | 無狀態 Streamable HTTP，部署在 Cloudflare Workers | 規格版本、SDK 用法、Claude Code／Codex 怎麼連 |
| F. 儲存與配對 | git 裡的 JSON 當正本，建置成索引給 MCP；配對以條件篩選為主 | 是否需要向量搜尋 |

各節的調研筆記會先寫進 [notes/](notes/)，查核後再整合進本文。

**調研方式**：每個主題由一個 agent 查官方文件並實測，另一個 agent 反向查核（找錯、標「未驗證」），最後由主控者整合。

---

## A. 軟體從哪裡來：管道盤點

（進行中）

## B. 怎麼判斷「可用的軟體」與「品質好」

（進行中）

## C. 沙盒驗證

（進行中）

## D. Meta 模型

（進行中）

## E. MCP server

（進行中）

## F. 儲存與配對

（進行中）

## G. 整體架構

（進行中）

## H. 每天的實作計畫

（進行中）

## I. 風險

（進行中）

## J. 建議修改 brief

（進行中）

## K. 需要念誠決定或提供的東西

（進行中）
