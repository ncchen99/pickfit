# 產品盤點：體驗、品質、MCP 與成本（2026-11-20）

> 盤點對象是 `main`（c13eb3ae）。只讀程式、不改程式、不呼叫付費 API。數字的來源寫在各段：本機用真實 index 量的（免費）、從程式算的，或帳本與 11/20 審計報告（`audit-20261120.md`）裡的。三條還沒合進 main 的分支已經處理的項目不再重提，只在相關處註明：
>
> - `feat/opt-worker-judges`：find 卡片瘦身與 `MAX_CARDS` 60→50（每次查詢約省 36%）、易用性 judge 的 `ease_one` 與 `--pending`、feature judge 的 patch
> - `feat/opt-security-tokens`：抽取 prompt 快取一小時、yarn/bun lockfile、SBOM replay
> - `feat/opt-sandbox-env`：沙盒的 GPU、麥克風、PostgreSQL／Redis 等服務

## 先講結論

1. **pickfit.app 根本沒有自動部署。** CI 的「Deploy pickfit.app」步驟跑的是 `pickfit publish`，最後執行的是部署 Cloudflare Worker 的指令；但 `worker/wrangler.jsonc:11` 寫明 pickfit.app 已經指到 Cloud Run，那個部署碰不到正式站。結果是 CI 綠燈、網站沒變，watch 等不到新的 `data_sha256`，紀錄就一直停在「verifying」。58 筆卡住就是這個原因。修好之後，watch 現有的推送和比對流程會自己把紀錄改成 listed，不需要其他改動。
2. **prompt 快取能省的錢很少。** find 每次約 38.6k input tokens，其中固定的 system prompt 約 5.7k 字元、schema 約 2.5k 字元，合計約 1.5–2.2k tokens，其餘都是隨請求變動的候選卡片。快取固定部分只省約 3–5% 的 input 成本。要省一半以上，得靠卡片（已在分支上）、重複查詢的快取，和模型選擇。
3. **最容易改、使用者馬上感受得到的有四件：** 網頁沒有「裝不起來」的回報入口；MCP 回報失敗後回答「已排入重驗」，但正式環境沒有任何程序在處理重驗佇列；搜尋快取漏了「資料留在本機」這個條件，會回錯答案；模型寫的句子在中文頁面上一律是英文。

## 現況數字

| 項目 | 數值 | 來源 |
|---|---|---|
| find 每次 input | 約 38.6k tokens，60 張卡片，快取 0% | 審計報告（8 次平均） |
| find 每次花費 | 約 US$0.17 | 審計報告 |
| 卡片區塊 | 每次約 85.7k 字元；分支上的瘦身後 53.4k | `worker/bench/card_size.ts`（opt-worker-judges） |
| 固定 system prompt | find 5,736 字元、alternatives 6,811 字元、關鍵字呼叫 715 字元 | 本機量 `prompt.ts`、`expand.ts` |
| 回答 schema | 不含 slug 時 2,535 字元；含 60 個 slug 的 enum 時 4,913 字元 | 同上 |
| 一次搜尋的模型呼叫 | 2 次，都是 Opus 而且依序進行：關鍵字（候選超過 MAX_CARDS 時，幾乎每次都會）→ match | `find.ts:459-492` |
| MCP `find_software` 回應 | 平均 10.7k 字元（3 個 pick）；每個 pick 主要是 features 732、how_we_know 707、why 486、security 426 | 本機用真實 index、rules 模式量 5 個查詢 |
| MCP `get_install_guide` 回應 | 平均 5.5k 字元 | 同上 |
| Cloud Run | `--min-instances 0 --max-instances 4`，記憶體快取每個 instance 各自一份、冷啟動就清空 | `worker/cloudrun/deploy.sh:16-17` |

## 一、使用者體驗與速度

**U1. 搜尋快取漏了「資料留在本機」（bug）。**
- 檔案：`worker/src/web.ts:320` 的快取 key 是 `[need, os, arch, free_only, offline]`，沒有 `form.private`；同一份 key 也拿來合併進行中的請求。
- 影響：勾了「資料留在本機」的人，十分鐘內可能拿到沒勾時的答案，推薦會把資料上傳雲端的工具。
- 改法：把 `form.private` 加進 key。工程量 S。

**U2. 搜尋卡片和工具頁的漏洞數不一致（bug）。**
- 檔案：`worker/src/page.ts:524-539` 的 `vulnLine` 用 `s.count`（findings 數），而且不看 `security.level`。工具頁用 `advisoriesOf` 算不重複的 advisory，`conditional` 等級顯示琥珀色的「部分用法」（`pages/tool.ts:310,487,1018`）。
- 影響：同一個工具，搜尋卡片寫紅色「高或嚴重」，點進去變成琥珀色，數字也不同。
- 改法：改用 advisories，依 level 分支。工程量 S。

**U3. 搜尋要等 10–16 秒，畫面只說「通常 5 到 15 秒」。**
- 檔案：`ui/script.ts:116-152`（fetch 送出，沒有 timeout 和 abort）、`page.ts:1157-1164`（loading 範本）。
- 兩段實際的等待：關鍵字呼叫（`find.ts:460`）和 match 呼叫（`find.ts:492`），都是 Opus、依序執行。
- 改法分三級：
  - S：loading 範本照實際順序顯示三行階段文字（讀需求、挑候選、請 Claude 比較），加上經過秒數和 30 秒逾時提示。
  - M：`Deps` 加 `onStage` 回呼，fragment 請求改成串流 `text/html`，客戶端用 `res.body.getReader()` 讀。不能用 EventSource，因為只支援 GET，而這裡要帶 POST 的 Origin 檢查。快取命中、合併請求和限流的路徑仍回一個 chunk。
  - 真正縮短時間的作法在第四節（C3、C4）。
- 效果：S 只改善體感；M 讓人看得到進度，不縮短總時間。

**U4. 首頁 8 個範例查詢每次都要等整整一輪。**
- 檔案：`page.ts:971-984`（英文 4 個、中文 4 個）、`web.ts:46-47`（記憶體快取，10 分鐘、64 筆）。
- Cloud Run 最少 0 個 instance、最多 4 個，記憶體快取常常是冷的。
- 改法：
  - 在 D1 開一張查詢快取表，key 是正規化後的查詢、全部條件、介面語言和 `data_sha256`。Cloud Run 已經透過 REST 連 D1（`cloudrun/bindings.ts:3`），不用新服務。工程量 M。
  - 資料一換，key 就跟著換，不會回舊答案。
  - 範例查詢可以在部署後的檢查步驟順便暖一次快取（8 次 match，約 US$0.9–1.4／次部署），或等第一個訪客付錢。
- 效果：範例查詢與重複查詢從 10–16 秒變成不到 1 秒，命中的查詢也不再花錢。命中率要上線後才量得到。

**U5. 依訪客 OS 預選安裝分頁：工具頁已經做了。**
- `ui/script.ts:441-480` 只在瀏覽器端讀取 OS，不做追蹤。
- 剩下的缺口是搜尋表單的 OS 預設為「任何系統」（`page.ts:987`）。可以加一個「你的系統：macOS」提示鈕，按了才套用。自動勾選會改變結果，所以不建議。工程量 S。

**U6. 搜尋結果一鍵比較：已經有了。**
- `page.ts:853-856`，不靠 JS 也能用。
- 缺口：`/compare` 的 OS 切換、移除連結和新增表單會丟掉 `arch`（`compare.ts:56,228,235-237`）。工程量 S。

**U7. 各頁的摩擦點。**
- `/browse` 沒有 JS 時文字篩選失效：輸入框沒有 `name`，表單也沒有送出（`browse.ts:113`）。改法是加 `name="q"` 並在伺服器端篩選。工程量 S–M。
- `/compare` 在手機上不好用：
  - 每欄 `min-width:200px`（`styles.ts:1140`），兩個工具就要約 580px 寬。
  - 列標題不會固定在左邊。
  - sticky 表頭因為外層 `overflow-x:auto` 而失效（`styles.ts:443,446`）。
  - 改法：第一欄 sticky，或窄螢幕改成上下排。工程量 M。
- `/tool` 在 1080px 以下，「一眼看懂」側欄（品質、安全盾牌）掉到頁尾（`styles.ts:1292`），只有 vulnerable 會在頁首另外顯示。改法是把安全狀態的小標籤一律放在頁首。工程量 S。
- 功能「未測試」的原因只放在 tooltip（`tool.ts:796`），手機上幾乎看不到。改法是改成可展開的一行。工程量 S。
- 深色模式：`--rule` 和背景的對比只有 1.19–1.58:1，比較表的格線幾乎看不見（`styles.ts:44-57,445`）；`--line-ctl` 為 3.19:1，勉強可用。工程量 S。

**U8. 新欄位的呈現。**
- 引用欄位時直接顯示代碼：「From its profile: `capabilities_matched` is …」，中文頁也一樣（`page.ts:566-568`）。`use_cases`、`verified_on`、`data_sent` 都是這樣。改法是一張欄位對白話名稱的對照表。工程量 S。
- `capabilities_matched` 的 rules 理由在中文頁沒有翻譯：`zhRuleClaim` 缺這個樣式（`web.ts:178-197`）。工程量 S。
- `beyond_budget` 的 tooltip 寫「pickfit 只逐項測試前四項功能」，等於把內部的測試額度講給使用者聽。可以改成「這一項 pickfit 沒有逐項測」。工程量 S。
- Verification Coverage（`pickfit/coverage.py`）沒有放進 index，頁面上看不到；`/how` 也沒提。要不要放上頁面要另外決定。工程量 M。
- 「品質信心度 62%」是行話（`kit.ts:338-352`）。工程量 S。

**U9. 中文體驗。**
- 最大的問題：模型寫的句子在中文頁面一律是英文，包括 fit、理由、tradeoffs、vs_well_known、clarifying_question 和 best_free 的理由。
  - prompt 規定用英文寫（`prompt.ts:36`）。
  - 網頁沒有傳 `ui_language`（`find.ts:44,617` 其實已經有這個欄位）。
  - `localizeResult` 只換 catalog 裡的句子。
  - 改法：claim 類欄位依 `ui_language` 寫中文；`value` 照舊抄卡片的英文原文，guard 不受影響。快取 key 加上語言。工程量 M。
- ZH_EN 詞典缺很多常用詞（`lexicon.ts:25-79`），例如：剪輯、錄影、錄螢幕、簡報、浮水印、縮圖、去背、轉碼、心智圖、電子書、播放器、直播、會議、雲端、自架、記帳、地圖、檢查、釋放、佔用。
  - 首頁 4 個中文範例裡有 3 個用到缺的詞（程式碼地圖、檢查設定、釋放連接埠）。
  - 這個詞典只在 rules 路徑（模型關掉，或關鍵字呼叫失敗）派上用場。
  - 改法：補詞並加測試。工程量 S。
- 生硬的用語：「量身中」（`script.ts:123`）、「資料在本地」（應為「資料留在本機」，`page.ts:1016`）、「比較匣」、「品質信心度」，還有沒有翻譯的 lockfile、repo、coding agent。工程量 S。

## 二、推薦品質與信任閉環

**Q1. guard 只檢查引用的值存在，不檢查說法對不對。**
- 檔案：`guard.ts:16-29,76-80`。值只要是卡片欄位的子字串（3 個字元以上）就算通過；說法本身只過 `contradiction()` 的幾個關鍵字。
- 例子：「把 DOCX 轉成 PDF」引用 `tags: "pdf"` 就會通過。
- 改法：值要佔列表項目的大半，不能只是子字串；只引用 `tags` 的理由不採用。工程量 M。

**Q2. 可以引用不該當理由的欄位。**
- prompt 規則 3 說 popularity 不能當理由，但 `popularity`、`quality` 仍在 `CARD_FIELDS`（`cards.ts:40,62-64`），guard 也不擋。
- 改法：guard 丟掉引用這兩個欄位的理由。工程量 S。
- 註：opt-worker-judges 已經不把 popularity 放進 prompt，但 guard 這一層還是要補。

**Q3. 有幾個模型欄位完全不檢查。**
- 不檢查的欄位：`tradeoffs`、`vs_well_known`、`no_install_option` 和 `best_free_reason`，只裁長度（`guard.ts:123-124`、`find.ts:285-288`）。
- 規則 7、9 允許用一般知識，和規則 2「只能用卡片事實」互相矛盾。
- `best_free` 常常和第一名重複，預設理由「Free and fits the request.」是空話。
- 改法：
  - tradeoffs 和 vs_well_known 也過 `contradiction()`。
  - `no_install_option` 套用和 `well_known` 一樣的檢查（不准網址、指令和「已驗證」字眼）。
  - best_free 只在不是 pick 時才回。
  - 工程量 S。

**Q4. 模型的 fit 句子被擋下時，會悄悄換成工具摘要**（`guard.ts:121`），讀起來答非所問。改法是直接不回這一句，或標示出來。工程量 S。

**Q5. rules 備援的回答像範本。**
- fit 直接用 summary，理由是「Use case: X」「Free to use」（`rules.ts:81-106`）。
- best_free 從整個排序裡挑（`find.ts:325`），可能是很弱的配對。
- 改法：第一條理由寫「提到你的需求裡的 X、Y」；best_free 只取 partial 以上的配對。工程量 S。

**Q6. 只有 rules 路徑會標出「部分符合」**（`find.ts:331-354`）。模型路徑沒有 `match_quality`，除非模型自己寫在 tradeoffs 裡。改法：schema 加每個 pick 的 `coverage`（full／partial）。工程量 M。

**Q7. 什麼都不合時，指示自相矛盾。**
- server 指示寫「Don't … say pickfit found nothing」（`server.ts:23,516`），會讓 agent 把弱配對講成好推薦。
- 改法：改成「沒有合適的就直說，有 well_known_option 就給」。工程量 S。

**F1. 網頁沒有回報失敗的入口。**
- 沒有路由也沒有表單（`web.ts:451-509`），只能寫信或開 GitHub issue（`pages/info.ts:113`）。
- 改法：安裝區加「我裝不起來」按鈕，送出 `install_failed`，內容是 slug、OS 和選填的錯誤片段。工程量 M。

**F2. MCP 回報要湊齊四樣東西才會觸發重驗。**
- 要有 `rec_id`、OS、`error_excerpt`，而且不能是網頁應用（`outcome.ts:116,173,182`）。但 schema 裡 `rec_id` 是選填，沒帶也不會報錯，只是不算數。
- 改法：失敗類的回報缺東西時，回傳 `next` 說明少了什麼。工程量 S。

**F3. 重驗佇列在正式環境沒人處理（死路）。**
- watch 服務沒有開 `--reverify`（`deploy/watch/pickfit-watch.service:24`），兩者在設計上互斥（`watch.py:634-636`）；也沒有 timer 跑 `pickfit reverify`。
- 但 `report_outcome` 回答 `reverify: "queued"`（`outcome.ts:70`），這個承諾目前不會兌現。
- 改法：加一個 reverify 的 systemd timer，跑完只 commit、不發布，等人確認；在那之前，回應改成「已收到，等人工確認」。工程量 S–M。

**F4. outcomes 同步也要手動跑**（`pickfit outcomes sync`，`cli.py:765`），算數的回報要有人跑過才會進到分數。改法是加 timer。工程量 S。

**D1. MCP 只給原始日期，沒有「多久以前」。**
- picks 帶 `verification.checked_at`（`find.ts:233`）；`last_release` 在卡片上，但不在 MCP 輸出裡。
- 改法：加 `age_days` 和 `last_release`；新版本比驗證日期新，或驗證超過 90 天時，加一句警示。工程量 S。

**D2. 網頁顯示版本發布多久，但沒顯示驗證多久**（`tool.ts:78`、`kit.ts:185`）。工程量 S。

**D3. 安全掃描沒有排程。**
- `pickfit security --stale-days N --write` 不呼叫模型（`security.py` 開頭的說明），`score --refresh` 也不花錢，但兩個都沒有排程。
- 新的漏洞公告只有在紀錄重新驗證時才會進來。
- 改法：watch VM 上加每週的 timer：security → score refresh → 用現有的 push 流程推上去，推送後自動部署（O1）。工程量 S–M。
- 效果：漏洞標示每週更新，模型費用為零。

## 三、MCP 開發者體驗

**X1. `/agents` 只有兩段設定。**
- 一段是 `claude mcp add --transport http pickfit …`，正確。
- 另一段是一份 `mcpServers` JSON，標示「Claude Desktop、Cursor 和其他客戶端」（`pages/info.ts:74-77`）。
- 問題：
  - Cursor 可以用這份 JSON。
  - Claude Desktop 的設定檔只啟動本機（stdio）伺服器，遠端伺服器要從 Settings → Connectors 加，或用 `npx mcp-remote <url>` 轉接。這點出自我對這些客戶端的了解，這次盤點沒有實際試過。
  - VS Code 的 `.vscode/mcp.json` 用的是 `"servers"`，不是 `"mcpServers"`。
  - Codex CLI、Gemini CLI（`httpUrl`）和 Windsurf（`serverUrl`）都沒有列。
- `mcpconfig.ts:112,144` 給推薦的 HTTP 伺服器產生的設定也有一樣的問題。
- 改法：每個客戶端一個分頁，各給正確格式和一鍵複製。上線前在 Claude Code、Cursor、VS Code 和 Claude Desktop 各實際接一次。工程量 S。

**X2. 每個回應都送兩份。**
- `result()` 把完整 JSON 放進 `content[].text`，又放一份在 `structuredContent`（`server.ts:492-497`）。兩份都交給模型的客戶端，token 會付兩次。
- 改法：`content` 只放一段簡短摘要，例如第一名、要跑的指令和警示，完整資料留在 structuredContent。工程量 S。
- 效果：在這類客戶端上，傳輸量與 token 最多省一半。

**X3. 回應裡的雜訊**（`find.ts:150-159`、`install.ts:110-122,255,266`）。
- 對 agent 沒用的欄位：`model_attempts`、`model_http_status`、`degraded_reason` 和 `considered`。
- 重複的內容：how_we_know 裡的「Quality x/100 and popularity y/100…」和「Chosen by claude-… among N tools」；guide 裡出現兩次的 `evidence_url`；重複 steps 的 `verified_in_pickfit`；同一個啟動方式寫了三種的 `mcp_client_config`。
- 網頁會濾掉、MCP 卻照送的：kind 為 sandbox、tool_handled 或 note 的 `known_issues`（網頁的過濾在 `tool.ts:847`）。
- 改法：預設 `verbose=false`，把以上欄位拿掉。工程量 M。
- 效果：每個回應約省 30–40%，依本機量的欄位大小估算。

**X4. 該放到前面的內容。**
- 要放前面的：`warnings`（安全、sudo；guide 已經放在最前面）、`steps` 與 `verify` 的確切指令、kind 為 `readme_wrong` 的避坑、blocked 或 exposed 的安全等級。
- 改法：在 `find_software` 每個 pick 加一行 `security_warning` 和 `readme_wrong` 摘要，讓 agent 在安裝前就能提醒使用者。工程量 S。

**X5. tools/list 的大小。**
- 工具說明每個約 0.7–1.05k 字元，可以接受。
- output schema 的 `.describe()` 文字共約 8.8k 字元（`server.ts:52-486`）。客戶端如果把 output schema 也交給模型，每個對話都要多付這筆。
- 改法：精簡 findings、gui 等內層欄位的說明。工程量 S。

## 四、成本與維運

**C1. prompt 快取：省得少，但不用錢。**
- 現在 system 是純字串，沒有 `cache_control`（`meta.ts:152-156`）。
- Opus 5.5 最小可快取長度是 512 tokens，固定部分約 1.5–2.2k tokens，夠長；快取讀取價是 input 的 0.05 倍。
- 改法：
  - system 改成一個文字區塊並加 `cache_control`。
  - schema 拿掉每次不同的 slug enum（`prompt.ts:101,115`），slug 改由 guard 檢查（guard 本來就逐筆核對卡片），schema 才會固定。
  - 文件沒有寫 output schema 在快取前綴裡的位置，所以上線前先送兩次相同前綴的請求，看 `cache_read_input_tokens`，約 US$0.3。
- 效果：每次約省 1.5–2.2k tokens 的 input，約 US$0.006，佔 3–5%。流量小時幾乎都是冷寫入（1.25 倍），要每 5 分鐘內有第二次查詢才划算；也可以用 1 小時 TTL，寫入是 2 倍價。工程量 S。

**C2. 卡片數與內容：分支已完成大半。**
- opt-worker-judges 合併後，每次約省 36%（38.6k → 24.6k tokens，US$0.17 → 約 US$0.11）。
- 再降到 40 張可以省到約 48%，代價是 128 題查詢少 3–5 題命中，數字在分支的 commit 裡。

**C3. 英文查詢可以省掉關鍵字呼叫。**
- 關鍵字呼叫（Opus，約 460 tokens）幾乎每次都跑，而且排在 match 前面。
- 英文請求本身的字詞可以直接拿來做 BM25 候選：免費 bench 的 short+q 和 rules 計分幾乎一樣（116 對 119／128）。
- 改法：英文請求跳過關鍵字呼叫，中文和其他語言照舊。
- 驗證：
  - 先用 `bench/keywords.ts` 存下英文需求的關鍵字（約 US$0.3），比較有沒有關鍵字時的候選差異。
  - 再用 `bench/ai_path_same.ts` 確認送給 match 的卡片差多少。
- 效果：英文查詢少一次依序呼叫，延遲少一段。實際秒數要用 `bench/latency.ts` 量，屬於付費、量很小。工程量 S。

**C4. 模型分級：需要老闆決定。**
- 11/17 老闆否決過 Sonnet、Haiku 等較弱的模型，理由是會把結果弄壞，所以這一項只列出選項，不建議預設採用。
- 價格（Anthropic 現行定價）：Opus 5.5 US$4／US$20，Sonnet 5.5 US$2／US$10（每百萬 tokens）。
- 比較低風險的做法：
  - 關鍵字呼叫（C3 之後只剩非英文的請求）改用 Sonnet 5.5 或 Haiku 5.5。這是很小的翻譯和抽字工作，總花費本來就低，主要是縮短延遲。
  - match 改用 Sonnet 5.5 只在命中「簡單查詢」時：候選少於 MAX_CARDS、沒有條件衝突。
- 驗證門檻：同一批 46 題 Opus 抽測（`worker/bench/capability/opus-check.json`）加上 fit-fresh dev，在 Sonnet 上跑一次（約 US$4），命中與誤推都不能退步才採用。
- 效果：match 全改 Sonnet 時，每次約 US$0.11 → US$0.057。快取是依模型分開的，兩個模型會各有一份。

**C5. 查詢快取（U4）是成本面最直接的槓桿。** 命中的查詢花費為零。現在流量小（審計時兩天 18 次），命中率要上線後量。

**成本合計（每次 find，命中快取的不算）：**

| 情境 | 每次約 | 對現況 |
|---|---|---|
| 現況（main） | US$0.17 | |
| 合併 opt-worker-judges | US$0.11 | −36% |
| 再加 C1 快取、C3 跳過英文關鍵字 | US$0.10 | −40% |
| 再把卡片降到 40 張 | US$0.085 | −50% |
| match 改用 Sonnet 5.5（需老闆同意） | US$0.05 | −70% |

不換模型也能降到一半，條件是卡片降到 40 張並接受上面的召回代價，或是 U4 的快取命中率夠高。

**O1. Cloud Run 自動部署（P0）。**
- 現況：
  - `.github/workflows/worker.yml` 只有部署 Cloudflare Worker（`:66-71` → `pickfit/publish.py:50`）。
  - `worker/cloudrun/deploy.sh` 只在念誠的電腦上手動跑，跑之前不做 typecheck 和測試，跑之後也不檢查（`:12-20`）。
- 一次性的 GCP 設定：
  - 建 GitHub OIDC 的 Workload Identity pool 和 provider，條件限定 `repository=='ncchen99/pickfit' && ref=='refs/heads/main'`。
  - 建部署用的服務帳號，給 run.admin（CI 不帶 `--allow-unauthenticated` 時用 run.developer 就夠）、cloudbuild.builds.editor、artifactregistry.writer、storage.objectAdmin、serviceusage.serviceUsageConsumer，以及對 runtime 和 Cloud Build 服務帳號的 iam.serviceAccountUser。
  - 不用 JSON 金鑰。
- workflow 新增 `deploy-cloudrun` job：
  - `needs: check`，只在 main 的 push 時跑。
  - `permissions: id-token: write`。
  - `concurrency: cloudrun-deploy`，不取消排隊中的；新的推送會取代等待中的那一次，所以最後的資料一定會上線。
  - 用 paths filter 限定在 `data/software/**`、`data/i18n/**`、`worker/**`（不含 bench）、`pickfit/index.py`、`pickfit/i18n.py` 等路徑才部署。
  - 步驟：auth（WIF）→ setup-gcloud → `deploy.sh`。
- 部署後的檢查：
  - 輪詢 `https://pickfit.app/` 的 `data_sha256`，等它和 `worker/src/generated/index.json` 一致，最多等 5 分鐘。
  - `entries` 不能少於門檻。
  - 跑一次 `/mcp` 的 find_software 冒煙測試。
  - 失敗就把流量切回前一個 revision。
- 舊的 wrangler 部署步驟要刻意決定留或拿掉（workers.dev 還有沒有人用）。
- 效果：watch 推上去的紀錄約 5–10 分鐘內自動變成 listed。58 筆積壓下一次推送就會清掉。
- 工程量 M：約 2 小時，含 IAM。GCP 設定要念誠做。

**O2. CI 沒跑 Python 測試。** 部署的 index 是 Python 建的（`pickfit/index.py`、`i18n.py`），但 CI 只跑 Node。改法：check job 加 `uv run pytest -q`。工程量 S。

**O3. 部署前沒有防呆。** `deploy.sh` 跳過了 `pickfit publish` 的檢查：fixture、工作區乾淨、有沒有 listed 紀錄（`publish.py:147-176`）。改法：CI 部署前跑 `pickfit publish --dry-run`。工程量 S。

**O4. 卡在 verifying 沒有警報。**
- 停在 `READY_REASON` 的紀錄沒有逾時，也不會提醒任何人；清理程序還會刻意跳過它們（`watch.py:347-350`）。
- `_mark_deployed` 要求正式站的 sha 和本機完全相同（`watch.py:1532-1556`），部署中途又 commit 就要等下一次部署。
- 改法：停超過 2 小時就在 status 頁和日誌示警；也接受出現在 git 歷史裡的 sha。工程量 S。

**O5. 設定分散在兩處。** `deploy.sh:18` 寫死的 `ALLOWED_HOSTS` 和 `wrangler.jsonc:35` 各自維護，遲早不一致。改法：從同一個地方讀。工程量 S。

**O6. 帳本之外的花費。** Scaleway Mac 租用（`--mac-rent`，每週最多一台，最少收一天）沒有供應商端的預算警示。改法：在 Scaleway 設預算警示。工程量 S。

## 執行路線圖

**P0：立刻做，回報高、工程量小**

| # | 項目 | 工程量 | 效果 |
|---|---|---|---|
| 1 | O1 Cloud Run 自動部署＋部署後檢查（需要念誠做 GCP 設定） | M | 清掉 58 筆積壓；新紀錄 5–10 分鐘上線；不再手動部署 |
| 2 | O2 CI 加 pytest、O3 部署前 dry-run | S | 壞的 index 不會上線 |
| 3 | U1 快取 key 補上「資料留在本機」 | S | 修掉會回錯答案的 bug |
| 4 | F3 重驗佇列：在 timer 上線前，回應先改成「已收到，等人工確認」 | S | 不再承諾做不到的事 |
| 5 | X2 MCP 回應只送一份完整資料 | S | 部分客戶端的 token 最多省一半 |
| 6 | 合併 opt-worker-judges（卡片瘦身） | 已完成 | 每次 find 省約 36% |

**P1：本週做**

| # | 項目 | 工程量 | 效果 |
|---|---|---|---|
| 7 | D3 每週安全掃描＋score refresh 的 timer，F3 reverify timer，F4 outcomes timer | S–M | 零模型費用維持資料新鮮；回報真的會重驗 |
| 8 | X1 `/agents` 每個客戶端各自正確的設定，並實際接一次 | S | Claude Desktop、VS Code 使用者接得上 |
| 9 | U4 D1 查詢快取（含範例暖機） | M | 範例和重複查詢不到 1 秒、不花錢 |
| 10 | U9 模型句子依介面語言寫中文；補 ZH_EN 詞典；修生硬用語 | M | 中文頁面不再半中半英 |
| 11 | Q2、Q3、Q4、Q7 guard 和 prompt 的小修 | S | 少一些空話和沒有根據的說法 |
| 12 | F1 網頁「我裝不起來」按鈕，F2 回報缺欄位時提示 | M | 網頁使用者也能回報 |
| 13 | U2 漏洞數一致，U8 欄位白話名稱和 rules 理由翻譯 | S | 同一工具在各頁說法一致 |
| 14 | C1 prompt 快取（先用兩次請求驗證，約 US$0.3），C3 英文跳過關鍵字呼叫（先跑 bench，約 US$0.3） | S | 每次約再省 4%；英文查詢少一次依序呼叫 |
| 15 | D1、D2 驗證多久以前與版本漂移提示 | S | 使用者知道資料多新 |

**P2：之後做**

| # | 項目 | 工程量 |
|---|---|---|
| 16 | U3 串流階段進度 | M |
| 17 | X3 `verbose=false` 精簡回應、X4 安全與避坑提前、X5 schema 說明精簡 | M |
| 18 | Q1 guard 檢查說法、Q6 模型路徑的 coverage 標示 | M |
| 19 | U7 `/compare` 手機版、`/browse` 無 JS 篩選、深色格線 | M |
| 20 | U8 Verification Coverage 上頁面 | M |
| 21 | C2 卡片降到 40 張（接受召回代價時） | S |
| 22 | C4 模型分級（老闆決定後，先跑約 US$4 的 bench） | M |
| 23 | O4 verifying 警報、O5 設定統一、O6 Mac 租用預算警示 | S |

## 需要老闆決定的事

1. O1 的 GCP 設定（Workload Identity 和服務帳號）要念誠本人做，或交一組權限給 CI。
2. 舊的 Cloudflare Worker 部署（workers.dev）要留還是拿掉。
3. C4：要不要重新評估 Sonnet 5.5（11/17 否決過）。只用在關鍵字呼叫，或只用在簡單查詢。
4. U4：範例查詢的快取是部署時暖機（每次部署約 US$1），還是等第一個訪客。
5. U8：Verification Coverage 要不要給使用者看。
