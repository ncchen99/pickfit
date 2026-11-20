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

## 50 筆回補之後（2026-11-20）

先替 50 筆紀錄抽了 capabilities（run `extract-capabilities-20261120-005756`，claude-opus-5-5，50 筆全部成功，1925 個引文沒有一個對不上，花費 US$3.43）。寫進紀錄後，index 裡有 49 筆帶 capabilities（另一筆紀錄不在 listed，index 不收），共 905 項，每筆中位數 19 項。

查詢集裡有 31 筆查詢的目標工具剛好在這批 49 筆裡（16 個工具）。前後比較（不指定類別，rules 路徑，不呼叫模型）：

| | card | short | short+q | rules |
|---|---|---|---|---|
| 子集，英文 | 1/31 → 27/31 | 17/31 → 29/31 | 20/31 → 29/31 | 8/31 → 22/31 |
| 子集，中文 | 1/31 → 24/31 | 14/31 → 29/31 | | 3/31 → 14/31 |
| 全部 128 筆，英文 | 4 → 30 | 69 → 80 | 80 → 88 | 30 → 44 |
| 主功能對照組 65 筆，英文 | 65 → 65 | 62 → 62 | 64 → 64 | 45 → 48 |

card 這一欄從這次起照 matcher 實際收到的卡片算，也就是帶著這次請求的字詞、含 `capabilities_matched`。舊的 baseline 檔用的是舊的計算方式（卡片不帶請求），所以舊的 3% 不能直接拿來比，表裡的「前」是用同一份 index 拿掉 capabilities 重算的。

代價出現在 fit-fresh 的 dev 查詢。good 類的 P@5 從 16.0% 降到 14.7%（150 個 pick 裡少了 2 個 grade 2），新出現在 picks 裡的大多是這批工具（hurl、atuin、m1k3 等），這些工具在 dev 標註時沒被標過，分數算 0。照請求內容看，多數其實不合適，例如用 hurl 查壞掉的連結、用 atuin 同步 S3。下表是免費試過的幾組設定，用的是同一批資料。

| 設定 | 子集 rules（英／中） | dev P@5 | good 標籤站得住 |
|---|---|---|---|
| 現在：BM25 權重 0.5，rules 的 fit 也讀 capabilities | 22 / 14 | 14.7% | 34.8% |
| 權重 0.5，fit 不讀 capabilities | 22 / 14 | 14.7% | 40.0% |
| 權重 0.25 | 19 / 12 | 14.7% | 36–40% |
| 權重 0（等於沒補） | 8 / 3 | 16.0% | 40.0% |

P@5 的下降來自 BM25 只要讀 capabilities 就會出現，調低權重只會少掉召回。fit 不讀 capabilities 則召回不變，good 標籤回到原本的 40%。

**11/20 採用第二列的設定。** `worker/src/fit.ts` 的 rules fit 不再讀 capabilities，BM25 權重維持 0.5。實測結果：

- 子集的召回和上表一樣，英文 rules 22/31、中文 14/31。全部 128 筆英文 44，對照組英文 48、中文 40。
- dev 查詢中，標成 good 的 pick 站得住的比例回到 40.0%（n=20）。
- 答案是 good 的題數回到 8/30，和補之前一樣。
- partial 站得住的比例是 11.6%，補之前是 15.6%。
- P@5 仍是 14.7%。

剩下的落差在 BM25 這一側：這批工具被拉進 picks。要不要再處理，等 Opus 路徑的抽測結果再決定。

## Opus 路徑抽測（2026-11-20）

`opus-check.json` 有 46 題：補過能力的工具的 31 題次要功能查詢（英文），加上 rules 推薦結果因回補而改變的 15 題 fit-fresh dev 查詢（各用原本的語言和條件，`slug` 是 null，用 `bench/fit-fresh/labels.json` 評分）。在這個 worktree 的 `worker/` 跑，`--cap 10`，46 題全部由 claude-opus-5-5 回答，沒有退回 rules，花費 US$8.08（帳本 `capability-bench`，run `capability-model-20261120`）。逐筆結果在 `baseline-backfill50-model.json`，用 `uv run python scripts/capability_opus_report.py` 看。

**次要功能查詢：** Opus 推薦到目標工具 29/31（94%），rules 路徑是 22/31。其中 22 題回補前也是 Opus 跑的（`baseline-model.json`），從 16/22 升到 21/22。沒中的兩題：c099（serena）沒進候選，c049（khive）進了候選，但 Opus 選了另外三個做提醒和排程的 MCP server。

**dev 查詢：** rules 路徑在這 15 題推了 45 個 pick，其中 15 個是沒標註過的回補工具，多半不合適。Opus 只推了 17 個 pick，回補工具剩 3 個：

- q02 的 m1k3（本機 OCR、摘要 PDF 再問答）
- q26 的 hurl（驗證 OpenAPI、mock、契約測試）
- q36 的 hurl（DNS、port、SSL 憑證到期）

這三個都還說得通，各自的能力清單上有對應的項目：hurl 有「Generate test reports」「Check SSL certificate properties」，m1k3 有「Ask questions over notes and PDFs with citations」。被擋掉的有 atuin（S3 同步、找重複檔）、github-mcp-server（Figma）、jj（整理筆記）、whisper-cpp（聲音複製、翻譯論文）、hurl（壞連結、OpenAPI mock）、marker、mise、comfyui、llm。Opus 的 17 個 pick 有 7 個是標註 2 分，rules 的 45 個只有 4 個。

另有 7 題 Opus 一個都沒推，回答「目錄裡沒有合適的」，例如 HEIC 轉檔、S3 加密同步、聲音複製。這些題目在回補前沒用 Opus 跑過，無法前後比。

**結論：** 回補後 BM25 拉進候選的不相關工具，Opus 看了卡片會擋掉。P@5 的落差只出現在 rules 備援路徑。不需要再調權重，可以直接全量回補。

## 全量回補之後（2026-11-20）

剩下的 373 筆也抽完了（run `extract-capabilities-20261120-012922`，373 筆全部成功，14,909 個引文有 14 個對不上而丟掉，US$23.14；兩次合計 423 筆、US$26.57）。寫進紀錄後，index 有 422 筆帶 capabilities，共 8,084 項，每筆中位數 19 項。查詢集的 66 個工具全部都補到了。

和完全沒有 capabilities 的同一份 index 比（rules 路徑，不呼叫模型，不指定類別）：

| | card | short | short+q | rules |
|---|---|---|---|---|
| 128 題，英文 | 4 → 119 | 69 → 119 | 80 → 116 | 30 → 73 |
| 128 題，中文 | 4 → 97 | 68 → 116 | | 17 → 52 |
| 對照組 65 題，英文 | 65 → 65 | 62 → 63 | 64 → 65 | 45 → 49 |
| 對照組 65 題，中文 | 65 → 65 | 59 → 58 | | 38 → 43 |

指定類別時，128 題的 rules 英文 38 → 84、中文 26 → 71。128 題裡只有 c090（中文）從推薦到變成沒推薦到。對照組有 14 筆從沒推薦到變成推薦到，5 筆從推薦到變成沒推薦到（m001、m014、m040 英文，m038、m055 中文）。

dev 查詢的 rules 路徑退得比 50 筆時多：答案是 good 的題數從 8/30 降到 6/30，P@5 從 16.0% 降到 10.7%。另一方面，`bench/dev_shortlist.ts` 量標註 2 分的工具有沒有進到 60 張候選卡片：rules 計分 55/90 → 54/90，用請求字詞的 BM25 49/90 → 49/90。所以 Opus 看得到的正確工具沒有變少，退步在 rules 備援路徑自己的排序。唯一明顯變差的是 q20（用 webcam 描述畫面的本機 AI），4 個 2 分工具只剩 1 個進得了候選：local_ai 類有 203 個工具補了 capabilities，有寫影像、相機的工具排到了通用的模型執行器前面。

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

## Sonnet 5.5 對照（準備好，還沒跑，2026-11-21）

`--model-id` 指定關鍵字和 match 兩個呼叫用的模型，預設還是正式站的 claude-opus-5-5。它只收 `src/meta.ts` 的 `MODEL_PRICES` 有價格的模型，`--cap` 才會用對的價格算花費。正式站不讀這個設定，Env 也改不了。

同一份 46 題，在這個 worktree 的 `worker/` 跑，金鑰從主工作區的 `.env` 讀：

```sh
node --env-file=../../../../.env bench/capability.ts src/generated/index.json bench/capability/opus-check.json --model-id claude-sonnet-5-5 --cap 6 --out bench/capability/sonnet-check-model.json
```

注意：`baseline-backfill50-model.json` 的 Opus 結果是 11/20 跑的，當時還是 60 張卡片、舊的 index。卡片瘦身（50 張）和之後的資料更新都會影響結果。要公平比較，就在同一個 build 用 `--model-id claude-opus-5-5 --out bench/capability/opus-check-model-20261121.json` 再跑一次 Opus（約 US$5）。
