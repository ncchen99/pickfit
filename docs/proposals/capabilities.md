# 功能清單：分開「驗過的主打功能」和「拿來比對的能力」

> 提案（2026-11-19）。起因是念誠發現每筆紀錄的功能幾乎都剛好四項：功能多的軟體被截掉，只有一個功能的軟體被湊滿，而沒列到的功能會讓 pickfit 不推薦它。

## 現在的狀況

**數量是寫死的。** 抽取 prompt 第 8 條要模型列「2-4 項主要功能」（[extract.py:95](../../pickfit/extract.py)），schema 再把超過 `FEATURES_MAX = 4` 的切掉（[schema.py:208](../../pickfit/schema.py)）。`use_cases` 也限 5 項，`tags` 限 10 項。現有 1158 筆紀錄的分布：

| 功能數 | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| 筆數 | 189 | 5 | 25 | 230 | 709 |

六成剛好撞到上限，可見是被截掉的，不是軟體本來就只有四項。另外 189 筆一項都沒有。

**限制的原因在驗證那一側。** `features` 同時做兩件事：

1. 驗證和展示。驗證 agent 要對每一項回報 checked／not_checked／test_failed（[agent.py:1190](../../pickfit/verify/agent.py)），feature judge 逐項判，影片每項一個章節，工具頁逐項打勾。項目越多，沙盒時間、token 和影片長度都跟著漲，所以才限四項。
2. 推薦時的證據。matcher 的 prompt 規定「只能講卡片上寫的事」「不要加一個做不到這件事的工具」（[prompt.ts](../../worker/src/prompt.ts) 第 2、4 條）。卡片上和「這個工具能做什麼」有關的只有 `summary`、`tags`、`use_cases`、`features_checked`、`features_not_checked`。

第二點是問題的來源。卡片沒寫的能力，matcher 不能引用，也就不會推薦。候選超過 60 筆時，BM25 初篩讀的是 name、tags、summary、alternatives_to、use_cases、why_worth_it、MCP tool 名稱（[relevance.ts:54](../../worker/src/relevance.ts)），連 `features` 都沒讀，次要功能更進不了前 60 名。rules fallback 的 `fitOf` 也一樣（[fit.ts:159](../../worker/src/fit.ts)）。

舉例：pandoc 的四項功能是「轉換幾十種標記格式」「透過 LaTeX 輸出 PDF」「Lua filter」「自訂 reader／writer」。有人問「把 docx 轉成 EPUB」，卡片上沒有 EPUB 這個字，只能靠模型自己從「幾十種格式」推，而規則叫它不要推。

## 做法：拆成兩層

驗證成本限制的是「要逐項驗的東西」，不該限制「拿來比對的東西」。所以把兩種用途分開。

### 第一層：`features`，驗過的主打功能（保留，改數量規則）

- 照來源列，**不湊數也不硬砍成四項**：單一用途的工具可以只有一項。上限放寬到 6，prompt 改成「1 到 6 項，來源主打幾項就列幾項」。
- 驗證仍只逐項驗前 4 項（`VERIFY_FEATURES_MAX = 4`），第 5、6 項標成 not_checked，reason 新增 `beyond_budget`（「這次驗證只測了前四項」）。影片和沙盒成本不變。
- 工具頁照舊逐項打勾。

### 第二層：`capabilities`，拿來比對的能力索引（新欄位）

- 內容是這個軟體**有文件佐證**的所有能力，短標籤，英文，每項附 quote 或來源位置。上限先訂 40。
- 不逐項驗證。卡片和頁面上都講清楚這是「文件寫的」，和「pickfit 看過它做到」分開。
- 功能很多的軟體（ffmpeg、pandoc、ImageMagick）照文件的分類分組：`{area: "formats", items: ["docx", "epub", "odt", ...]}`。格式、協定、支援的服務這種清單類的東西放 items，才不會佔掉 40 項。

來源依可信度排：

1. **沙盒裡實際印出來的說明**：`--help`、子命令清單、`man` 頁、MCP 的 `tools/list`（MCP 已經在收）。這是工具自己說的，比 README 準，而且裝起來時就能拿到，不用多開箱子。本機 476 份 verify run 裡，265 份的 `report.json` 出現過 `--help`，這部分可以直接回補。
2. README 的功能清單、小標和範例（抽取現在就讀）。
3. 官網的功能頁和文件目錄（web app 已經會抓首頁，CLI 可以多抓一頁 docs 索引）。

### 比對端的改法（worker）

1. **BM25**：`FIELDS` 加 `features`（權重 1）和 `capabilities`（權重 0.5）。能力清單很長，BM25 的長度正規化會把它壓住，不會讓大工具每個查詢都排前面。權重和 `B` 要用下面的測試集調。
2. **卡片**：不把 40 項全塞進去（60 張卡片會多出很多 token）。卡片加 `capabilities_matched`，只放跟這次查詢詞（含 expand.ts 產生的關鍵字）對得上的幾項，最多 5 項，沒有對上的就空著。
3. **matcher prompt**：第 2 條允許引用 `capabilities_matched`。第 6 條改成，工作需要的能力只出現在 `capabilities_matched`、不在 `features_checked`，tradeoffs 要說「文件寫有這個功能，pickfit 沒有實際測過」。
4. **`fitOf`**：profile 的 `does` 加入 features 和 capabilities，rules fallback 才不會把它判成 weak。

## 先量再改

改之前先做一份**次要功能查詢集**，放 `worker/bench/`（開發用，不是 `eval/`，建資料的 session 照規定不讀 `eval/`）。每筆是「一個查詢 + 應該出現的工具」，查的都是不在現有 features／use_cases 裡、但文件確實寫了的功能，例如：

- 把 docx 轉成 EPUB → pandoc
- 只抽出影片的音軌 → ffmpeg、yt-dlp
- 下載影片的字幕 → yt-dlp
- 把 JSON 轉成 CSV → jq、miller

先挑 40 到 60 筆，從現有紀錄的 README 抽，人工確認。指標有兩個：

- **召回**：應該出現的工具有沒有在 picks 裡。這是這次要改善的。
- **誤推**：在 worker 現有的 dev 查詢上，picks 有沒有變差。能力清單一長，最怕的是大工具什麼都對得上、把專門工具擠掉。

改完要召回明顯上升，而且 dev 查詢沒有退步，才回補全部紀錄。

**2026-11-19 量到的現況**（細節在 [worker/bench/capability/](../../worker/bench/capability/README.md)）：128 筆次要功能查詢，66 個工具，另外用同一批工具的主功能查詢當對照組。不指定類別時，英文查詢的結果如下：

| | 卡片有這項功能 | 進到 60 張候選 | rules 推薦到 |
|---|---|---|---|
| 次要功能 | 3% | 52% | 18% |
| 主功能對照 | 100% | 97% | 66% |

模型路徑（念誠 11/19 跑的，英文主集）：前 88 筆由 claude-opus-5-5 做 match，推薦到目標工具的有 44 筆（50%）。後 40 筆碰到 15 美元上限、退回 rules，只推薦到 10 筆（25%）。合計 54/128（42%），花費 US$15.397。Opus 的 88 筆裡，卡片上有這項功能的只有 3 筆，大部分是模型憑自己的知識選中，而 matcher 的規則本來不允許這樣做。主功能對照組的模型路徑還沒跑。

## 步驟

| 步驟 | 內容 | 主要檔案 |
|---|---|---|
| 1 | 次要功能查詢集和量測腳本，跑出現在的數字 | `worker/bench/` |
| 2 | schema 加 `capabilities`，`features` 改 1–6 項，驗證只取前 4 項並加 `beyond_budget` | `pickfit/schema.py`、`schema/software.v1.json`、`pickfit/verify/agent.py`、`worker/src/features.ts` |
| 3 | 抽取加能力索引（新的 capabilities-only 模式，像現在的 features-only，不必重抽整筆） | `pickfit/extract.py`、`pickfit/profiles.py` |
| 4 | 從已存的 run 撈 `--help`／子命令輸出當來源，verify 之後固定存一份說明輸出 | `pickfit/verify/` 收證據的地方 |
| 5 | worker 比對端四項改法，用步驟 1 的查詢集調權重 | `worker/src/relevance.ts`、`cards.ts`、`prompt.ts`、`fit.ts` |
| 6 | 先回補 50 筆量一次，數字過了再回補全部 | `pickfit extract --capabilities-only` |
| 7 | 工具頁加一個摺疊區「文件寫的其他功能」，和打勾的功能分開 | `worker/src/pages/tool.ts` |

步驟 1 可以先做，跟其他步驟無關。步驟 2 到 4 是資料端，步驟 5 是比對端，5 要等 3 有一批資料才調得動。

## 進度（2026-11-19，分支 feat/capabilities-step2）

- **步驟 2 完成。** 紀錄的 `features` 上限改成 6，驗證仍只逐項測前 4 項，第 5、6 項記成 not_checked、reason `beyond_budget`（agent 的 finish 不會拿到這個選項，web 驗證也一樣）。紀錄多了 `capabilities` 欄位（label 加上可選的 items，最多 40 項），目前還沒有程式寫入。抽取 prompt 和 `FEATURES_DESCRIPTION` 還是寫 2-4 項，等步驟 3 一起改。
- **步驟 4 完成。** [help_text.py](../../pickfit/verify/help_text.py) 從已存的 verify run 撈 agent 跑過的 `--help`，`python -m pickfit.verify.help_text` 寫到 `runs/capabilities/help/<slug>.json`。本機 476 份 run 撈到 62 個工具、169 份說明文字，其中 38 個有子命令的說明。之後每次驗證通過，pickfit 會自己在 agent 的箱子裡跑一次 `<tool> --help` 和最多 8 個子命令的 help，存進 report.json 的 `help`。這些指令不算 agent 的額度，也不進指令紀錄。

## 成本

抽取目前每筆約 US$0.09（[tokens.md](tokens.md)）。capabilities-only 只讀來源、輸出一份清單，估計每筆 US$0.03 到 0.05，1158 筆約 US$35 到 60。走 tokens 提案的 Batch API 再打五折。不用重開沙盒：`--help` 先從已存的 run 撈，沒有的等下次重驗再補。

## 和其他提案的交界

- `extract.py`、`score.py` 歸 [scoring.md](scoring.md)。步驟 3 等 scoring 的抽取重構合併後再接，或請協調 session 決定誰先。
- `features` 數量變動會影響 [video.md](video.md) 的章節數。因為驗證仍只取前 4 項，影片章節上限不變。
- 評分（scoring）不讀 `capabilities`。沒驗過的能力不該加分。

## 還沒決定的

1. 上限 40 和 6 是先抓的數字，等步驟 1 的量測再調。
2. `capabilities_matched` 用字詞比對選，同義詞（例如 "subtitle" 和 "captions"）會漏。要不要讓 expand.ts 的關鍵字呼叫順便挑，等量測結果再說。
3. 還有一條路：查詢時對前幾名候選即時查文件，再決定推不推。準，但每次查詢都多一輪呼叫，先不做。
