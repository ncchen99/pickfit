# 評分和抽取

> 提案（2026-11-19）。總覽和共同規則在 [README.md](README.md)。現在的公式是 b3.v6+visual.v1，在 [pickfit/score.py](../../pickfit/score.py)。

## 現況

- **同分太多。** 217 筆剛好 69 分，149 筆剛好 79 分（後者全是被漏洞封頂的）。三成多的紀錄擠在這兩個分數上，同分之間沒辦法排序。
- **掃不了的反而贏。** 161 個 treasure 裡，108 個 clean，53 個 unchecked。
- **缺資料沒有懲罰。** 缺的項目直接從分母拿掉，沒有往類別平均拉。沒測功能的，可能贏過測了但一項失敗的。`usage_outcomes` 全部沒資料，confidence 有存卻沒拿來用。
- **`sandbox_score` 不分驗證層級**（[score.py:424-438](../../pickfit/score.py)）：只看安裝步驟的等級乘上 README 修正係數，install、function、service 三種層級都一樣。
- **原始輸入沒存。** maintenance、hygiene、responsiveness 占 25% 權重，紀錄裡只存 0–1 的結果，原始值在本機沒進 git 的 `runs/pipeline.db`。`refresh_scores` 把舊數字直接沿用（:1033），issue 是即時抓的、沒存（:1231）。
- **熱門度基準借用。** `other` 和新的五個類別借用 dev_cli 的基準（:693），190 顆星就是 100 分。
- **rubric 沒有版本。** docs_rubric 沒存 prompt 版本，Muse 和 Claude 評的分數混在一起。rubric 又把同一份 README 讀一次（:1104）。
- **重用的 key 會害到大量收錄。** 抽取和 rubric 用「處理後來源的 hash」決定要不要重做（[extract.py:465](../../pickfit/extract.py)、score.py:1241）。只要改一下 README 的處理方式，下一輪就會把 1,158 筆全部重抽、重評，約 US$160。

## 提案

### R1 存原始評分輸入（收錄前）

紀錄加 `scores.inputs`：

- GitHub 原始訊號：stars、forks、open issues、最後 commit、release 日期和數量、contributors、issue 回應時間的原始值。
- 每個值的 `fetched_at` 和來源。
- maintenance、hygiene、responsiveness 改成從 `scores.inputs` 算出來。之後換公式，可以離線重算，不用再打 GitHub API。

附遷移程式：能從 `runs/pipeline.db` 補的就補（本機才有），補不到的標成缺，下一次 refresh 時抓。遷移由協調 session 跑。

### R2 rubric 的版本和校準集（收錄前）

- docs_rubric 存 `prompt_version`、`model`、輸入 sha、評分者。Muse 評的標出來，之後重評。
- 從 `data/software/` 挑約 50 份 README 當固定的校準集（不要用 `eval/` 裡的東西）。改 rubric prompt 時，先在這份集合上比較新舊分數。比較工具寫好就好，不要真的跑（要花錢）。

### R3 抽取重用的 key（收錄前，最急）

重用的判斷改成：

- 存三個值：原始輸入的 sha（README 原文、抓到的文件原文）、`prompt_version`、`renderer_version`。
- 原始輸入的 sha 一樣，就重用，不管 renderer 有沒有改。
- prompt 或 renderer 改了，不自動重做。要重做時明講（例如 `--refresh-before <version>`），由人決定哪些筆要重抽。
- 舊紀錄沒有原始 sha 的，遷移時照現有的 `sources_sha` 視為「目前版本」，不觸發重抽。

驗收：測試要涵蓋「只改 renderer → 不重抽」「README 原文改了 → 重抽」「明講 refresh → 重抽」。

### R4 rubric 併進抽取（可以並行做）

抽取時同一份 README 已經在快取裡，讓同一次呼叫一起輸出 rubric 的分數，省掉 score.py:1104 再送一次。每筆約省 US$0.015–0.03。

切換之前要拿約 30 份 README 比對新舊分數。比較工具寫好，列出要跑的指令和預估花費，不要真的跑。切換做成設定，預設維持現狀。

之後抽取和 rubric 要改走 Batch API（[tokens.md](tokens.md) 的 T3）。設計時讓這一步容易接。

### R5 封頂改成 treasure 門檻和扣分（收錄前定欄位）

- 紀錄存未封頂的原始總分，和套用規則之後的分數分開。
- 安全的效果改成讀 `security.assessment.level`（定義在 [security.md](security.md)）：

  | 等級 | 對分數的影響 |
  |---|---|
  | blocked | 不上架 |
  | exposed | 不能當 treasure，扣分（幅度做成設定） |
  | conditional | 不扣分，頁面有一行說明 |
  | present_unreachable、not_shipped | 不影響 |
  | partial、unchecked | 見 R9 |

- 舊紀錄沒有 `assessment` 的，照現在的規則（vulnerable 封頂 79），等重掃後才換。
- 「修好的版本已經出了 90 天，最新版還沒跟上」算進 maintenance 扣分，從 finding 的 `fix_published_at` 算。

### R6 依資料多寡往類別平均拉（可以並行做）

缺的項目不再直接拿掉。分數依有多少資料、資料多可靠（confidence），往同類別的平均拉。資料越少，越接近平均。`usage_outcomes` 等有資料再算，現在先不納入，但寫進公式說明。

### R7 驗證層級算進分數（可以並行做）

`sandbox_score` 區分 install、function、service。只裝起來的，分數低於功能也驗過的。

### R8 每個類別自己的熱門度基準（可以並行做）

用 `scripts/calibrate_popularity.py` 替 `other` 和新的五個類別算各自的基準。資料不夠的類別用全體的基準，不要借 dev_cli。

### R9 unchecked 能不能當 treasure（待念誠決定）

現在 53 個 treasure 是 unchecked。兩個選項：

1. unchecked 不能當 treasure。安全提案的 S3 上線後，多數紀錄都能從裝好的東西掃，unchecked 會少很多。
2. 維持現狀，只在頁面標「沒驗證」。

程式做成設定，預設維持現狀，回報裡附上兩種選項各會讓多少筆失去 treasure。

### R10 其他

- issue 的原始資料存進 `scores.inputs`，不要每次即時抓。
- `refresh_scores` 改成從存下的輸入重算，不沿用舊結果。
- 公式版本改成 `b3.v7`，舊版的結果保留在紀錄的歷史裡。

## 遷移和驗收

- 新欄位、遷移程式、各規則都有測試。
- 附一個本機重算的工具：讀 `data/software/`（只讀），用新公式算一遍，輸出前後比較表（格式參考 [security-score-changes.md](../security-score-changes.md)）和分數分布。回報裡寫出 69 分和 79 分還剩多少筆。不要寫回紀錄。
- 寫回由協調 session 跑。

## 不做的事

- 不直接改 `data/software/`。
- 不用 `eval/` 的資料校準。
