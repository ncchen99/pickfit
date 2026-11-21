# 大量收錄前的修改提案

> 提案（2026-11-19）。來源是 11/19 對 token、機器、影片、評分和安全審查的盤查。每份提案交給一個 subagent 在自己的 worktree 實作，合併前由協調 session 審查。

## 為什麼要在大量收錄前做

收錄一千多筆之後，再改評分、驗證或紀錄方式，就得把沙盒重跑一次，或者把每筆重新抽取、重新評分。這幾份提案的共同目標是：**把原始資料存夠**。存下 SBOM、原始 GitHub 訊號、錄影和動作紀錄之後，評分公式、安全政策、影片剪法都能離線重算，不必再開箱子。

## 提案清單

| 提案 | 主題 | 大量收錄前一定要做的 | 主要動到的檔案 |
|---|---|---|---|
| [tokens.md](tokens.md) | token 和模型用量 | 預設模型改 Opus、驗證 agent 第一輪就快取 | `pickfit/anthropic_messages.py`、`pickfit/meta.py`、`pickfit/verify/judge.py`、新的 `pickfit/msg_batch.py` |
| [throughput.md](throughput.md) | watch 吞吐量和 loop runner | 拿掉卡住吞吐量的入場限制 | `pickfit/watch.py`、`deploy/watch/`、`scripts/loop.sh`、`.claude/skills/pickfit-loop/` |
| [machines-cost.md](machines-cost.md) | 機器時間和成本帳 | 帳本記下每個箱子的實際用量 | `pickfit/ledger.py`、`pickfit/verify/modal_box.py`、`ec2_*.py`、`tart_box.py`、`mac_host.py`、`pipeline.py`（只動 replay 箱開啟的時間點） |
| [video.md](video.md) | 驗證影片 | 原始錄影品質、動作紀錄存 R2、字幕改 WebVTT | `pickfit/verify/record.py`、`video.py`、`web_video.py`、`pickfit/i18n.py`、`worker/src/pages/tool.ts`（影片區） |
| [security.md](security.md) | 安全審查 | 掃使用者實際裝到的東西、observation 和 assessment 分開存 | `pickfit/security.py`、新的 `pickfit/sbom.py`、`pipeline.py`（只加 SBOM 那一步）、`worker/src/server.ts`、`tool.ts`（安全區） |
| [scoring.md](scoring.md) | 評分和抽取 | 存原始評分輸入、rubric 版本、抽取重用的 key | `pickfit/score.py`、`pickfit/extract.py` |
| [coverage.md](coverage.md) | Verification Coverage（11/19 念誠定的方向） | 品質分數和驗證範圍分開、沒驗證的原因分類、把缺口轉成 harness 任務 | 新的 `pickfit/coverage.py`、`score.py` 和 `schema.py`（patch） |
| [privileges.md](privileges.md) | 要 root、要金鑰的軟體怎麼驗（11/21） | 紀錄記下給過什麼權限、用替身還是真服務驗的 | `pickfit/verify/agent.py`、`sandbox.Dockerfile`、`linux_box.py`、`services.py`、新的政策表和全權 VM 箱，`schema.py`、`failure.py`、`limits.py`（patch） |
| [aws.md](aws.md) | AWS 的花費怎麼分（11/21） | 沒有。模型呼叫接 Bedrock 要先做，分配才用得到 | `pickfit/meta.py`、`pickfit/anthropic_messages.py` 旁邊新的轉換模組、`pickfit/ledger.py`（價格表） |

## 跨提案的約定

幾個檔案會有兩份提案同時動到，先講好誰改哪一段：

1. **安全等級給評分用。** security 提案在紀錄裡新增 `security.assessment.level`（等級定義在 security.md）。scoring 提案只讀這個欄位，不自己判斷漏洞。舊紀錄還沒有 `assessment` 的，照現在的規則（`status == "vulnerable"` 就封頂 79）處理，等協調 session 重掃之後才換新規則。
2. **`pipeline.py`。** machines-cost 只改 replay 箱什麼時候開（目前在 [pipeline.py:232](../../pickfit/verify/pipeline.py)）。security 只在 replay 裝完、箱子關掉之前加一步「收 SBOM」，呼叫 `pickfit/sbom.py` 裡的函式。兩邊都盡量只改幾行。
3. **`worker/src/pages/tool.ts`。** video 只改影片區，security 只改安全區。
4. **`extract.py` 和 `score.py` 歸 scoring 提案。** tokens 提案做的 Batch API 模組，先接翻譯和使用說明。抽取和 rubric 改走 batch，等 scoring 的重構合併後再接。
5. **`watch.py` 歸 throughput 提案。** machines-cost 要記箱子成本，就在各個 box 類別建立和關閉的地方寫帳本，不改 watch 的排程。
6. **gap 代號歸 coverage 提案。** privileges 提案的 `grants` 和 `fidelity` 是新欄位，不另外發明 gap 代號。agent 的請求被拒絕時，沿用現有的 `needs_*`，新代號交給 coverage 的代號表。
7. **服務和計費代理歸 [sandbox-env-unlock.md](sandbox-env-unlock.md)。** privileges 提案只在上面加服務種類、替身模型端點和紀錄欄位，不另外做一套。
8. **全權 VM 箱的成本和 SBOM。** 全權箱建立和關閉時照 machines-cost 的 M1 寫 `boxes` 表，`purpose` 照樣分 agent 和 replay。security 提案收 SBOM 的那一步，在全權箱上也要能跑。
9. **`deploy/watch/watch.env.example` 和 `deploy/watch/bootstrap.sh`** 在 loop worktree 裡有別的 session 還沒 commit 的 harvest 修改。動到這兩個檔案時只在檔尾加新的設定，`pickfit/harvest/` 完全不要碰。

## 實作時的共同規則

- 不讀 `eval/`，不讀 `.env`。
- 不直接改 `data/software/`。紀錄格式改了，要附遷移程式和測試，但遷移由協調 session 跑。
- 不開 VM 或沙盒，不呼叫付費 API。要花錢的實驗（例如拿 30 份 README 比對 rubric）寫成可以直接跑的指令，列在回報裡。
- 不換成較弱的模型。判定類步驟的便宜模型只做離線比較工具，預設不變（11/17 念誠的決定）。
- 不能削弱「每次驗證都用全新箱子」的規則。
- 不 commit API key 或其他機密。不改過去的 commit、帳本和評測紀錄。
- 在自己的 worktree 分支 commit，不 push，不 merge 到 main 或 `loop/20261115`。
- 新增第三方工具（syft、govulncheck、cargo-audit）前先確認授權，寫在回報裡。

## 順序

1. **大量收錄前：** 每份提案標成「收錄前」的項目。重點都是紀錄格式和原始資料。
2. **收錄中可以並行：** 吞吐量和成本帳。成本帳要先上，才知道一筆實際花多少錢。
   11/21 加的兩份也在這一段：aws 的 A1（接 Bedrock）和 A2（上限和對帳）先做，privileges 的 P2 到 P8 照它自己的順序。
3. **之後再做：** 分級政策的細節、模型 triage、影片的裁切和快轉、便宜模型的實測。這些只要資料存好了，隨時都能離線重算。

## 還沒確認的

- `.env` 有沒有設 `PICKFIT_MODE`。hook 擋著，盤查時沒有看。
- 各項省多少錢都是照現在的 token 組成估的，還沒實測。
- 紀錄數字來自 11/18 建的 `worker/src/generated/index.json`。
