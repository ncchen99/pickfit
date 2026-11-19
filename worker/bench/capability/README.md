# 次要功能查詢集

[capabilities 提案](../../../docs/proposals/capabilities.md) 的第 1 步，用來量「README 有寫、紀錄沒列」的功能，pickfit 找不找得到。這是開發用的資料，不是 `eval/`。

## 檔案

| 檔案 | 內容 |
|---|---|
| `queries.json` | 128 筆次要功能查詢，66 個工具。每筆有功能標籤、README 原文 quote、區分用的 key terms、英文和繁中的請求 |
| `control.json` | 對照組：同一批工具，每個工具一筆主功能查詢（紀錄第一項 feature，沒有就用第一項 use case），65 筆 |
| `baseline-queries.json`、`baseline-control.json` | 2026-11-19 的逐筆結果（不呼叫模型），改完之後拿來比 |
| `baseline-model.json` | 2026-11-19 模型路徑的逐筆結果（英文，主集），`matchedBy` 記每筆實際走哪條路 |

## 怎麼做出來的

[scripts/capability_queries.py](../../../scripts/capability_queries.py) 從 `runs/pipeline.db` 有 README（至少 3000 字元）的已驗證紀錄裡，照類別輪流抽 70 個工具。Opus 讀 README 和紀錄的 profile（summary、tags、use_cases、features、MCP tool 名稱），找出最多兩個 README 寫得很清楚、profile 卻沒提到的功能，再寫成使用者會打的請求。程式接著把三種情況丟掉：quote 不在 README 裡、key terms 全都已經在 profile 裡、請求直接講出工具名稱。

人工檢查時修了一筆（c096 的英文請求裡有一段自我更正的句子），另外有 4 個工具連續兩次只產出空的請求，沒有收進來（boring-notch、narwhal、protoagent、transmission）。產生查詢集花了 US$2.82（主集 US$2.47，對照組 US$0.35），都記在帳本的 `capability-check` stage。

## 量了什麼

[capability.ts](../capability.ts) 對每筆請求量四件事，不呼叫模型：

- **card**：目標工具的卡片（matcher 唯一看得到、能引用的內容）有沒有這項功能的 key term。
- **short**：目標工具有沒有進到送給 matcher 的 60 張卡片（rules scorer，沒有模型關鍵字）。
- **short+q**：同上，但 BM25 改用請求本身的英文字詞，代替模型產生的關鍵字（只量英文）。
- **rules**：rules-only 的推薦結果（最多 3 個）有沒有目標工具。

## 2026-11-19 的基準

不指定類別（全 catalog 1150 筆）：

| | card | short | short+q | rules |
|---|---|---|---|---|
| 次要功能（英） | 3% | 52% | 60% | 18% |
| 次要功能（中） | 3% | 52% | | 13% |
| 主功能對照（英） | 100% | 97% | 97% | 66% |
| 主功能對照（中） | 100% | 89% | | 52% |

指定目標工具的類別：

| | card | short | short+q | rules |
|---|---|---|---|---|
| 次要功能（英） | 3% | 72% | 78% | 25% |
| 次要功能（中） | 3% | 70% | | 18% |
| 主功能對照（英） | 100% | 98% | 98% | 77% |
| 主功能對照（中） | 100% | 92% | | 58% |

同一批工具，問主功能時九成以上進得了 matcher 的候選，問次要功能時只剩一半。進得去的那一半，卡片上也幾乎沒有這項功能（3%），而 matcher 規定只能引用卡片上的事實，所以就算模型自己知道這個工具做得到，也沒有可以引用的內容。

## 模型路徑的基準（2026-11-19）

`--model` 走產品真正的流程：候選超過 60 筆時先呼叫關鍵字，再由 claude-opus-5-5 做 match。念誠跑了英文主集 128 筆，設 `--cap 15`。

| 實際走的路 | 筆數 | 推薦到目標工具 |
|---|---|---|
| Opus match | 88（c000–c087） | 44（50%） |
| 超過上限，退回 rules | 40（c088–c127） | 10（25%） |
| 合計 | 128 | 54（42%） |

花費 US$15.397，比上限多 0.4 美元，因為上限是在送出前檢查，同時跑的 4 個請求已經送出去了。這筆記在帳本的 `capability-bench` stage（run_id `capability-model-20261119`）。

怎麼讀這組數字：

- Opus 那 88 筆的 50% 才是模型路徑的真實數字。退回 rules 的 40 筆等於 rules 路徑，跟上面的 rules 欄位同一回事。
- 這 88 筆不是隨機抽樣，是查詢集的前 88 筆。要跟主功能對照組比，得在同一批工具上跑對照組的模型路徑。
- 88 筆裡有 54 筆的目標工具，光靠請求本身的字詞就進得了 60 張候選（short+q），其中 34 筆被推薦到。另外 10 筆不在 short+q 裡，靠模型產生的關鍵字才進候選，也被推薦到。卡片上有這項功能的只有 3 筆。換句話說，Opus 常常是憑自己對工具的了解選中的，但規則要它只引用卡片，這部分不穩。
- 沒量的部分：剩下 40 筆走 Opus 的結果、中文查詢、主功能對照組的模型路徑。照每筆約 US$0.175 估算，補齊這三組大約還要 US$40（40 筆約 7 美元、中文 128 筆約 22 美元、對照組 65 筆約 11 美元）。

## 要注意的地方

- 樣本只有 dev_cli、local_ai、mcp_server、other 四類。本機的 pipeline.db 只有 423 筆紀錄存了 README，其他小類別剛好沒有夠長的 README。
- 請求都是 Opus 寫的。對照組照 profile 的功能寫，字詞本來就比較容易對上，所以差距有一部分來自措辭。不過 card 欄位（3% 和 100%）跟措辭無關，是 matcher 能不能引用的硬限制。
- **模型路徑要花錢。** loop session 不能讀 `.env`，所以這一段要念誠自己跑：

  ```bash
  cd worker && ANTHROPIC_API_KEY=<key> node bench/capability.ts src/generated/index.json bench/capability/queries.json --lang en --model --cap 15 --out bench/capability/baseline-model.json
  ```

  `--cap` 是這次執行的花費上限（美元），超過之後剩下的請求會退回 rules（看 `matchedBy`），不會停。跑完把印出的 `cost_usd` 記進帳本。128 筆全走 Opus 估計要 US$22 左右。對照組換成 `bench/capability/control.json`、輸出換成 `baseline-model-control.json`。

## 重跑

```bash
cd worker && node bench/capability.ts src/generated/index.json bench/capability/queries.json [--category] [--lang en|zh|both] [--show] [--out FILE]
```

`--show` 逐筆列出結果。查詢集本身不用重做。要擴充的話，用 `--tools N` 加大樣本，已經做過的工具會跳過。
