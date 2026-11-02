# 評測結果（20 題第 1 次為主；2026-11-02 定稿）

數字都從 `eval/results/final/results.json`（`eval/runner/final.py` 產生）、`eval/results/l2/l2-results.json`、`eval/results/e-tags/` 與 `d5-*.json` 讀出；過程、每個偏離與評分者的失誤在 `eval/results/run-log.md`，偏離的正式紀錄在 `eval/README.md` 9.4。

## 1. 結論

**中等＋困難 12 題，L1 通過：實驗組 8 題、對照組 6 題（每組每題 1 次）。**

- D1（主要主張，差距 ≥ 3）：差 2，**未達到**。所以照 9.1 D 的寫法：**這 20 題沒有證明 pickfit 比較好。**
- D5（pickfit 自己不誇大，違反必須是 0）：**1 次違反**（內容見第 4 節）。照 D 的寫法，不論其他結果都寫明。
- 其餘門檻：D2 不退步（容易 8 題 8 比 8）達到；D3 L2（18 題 2 比 2）達到；D4 內建就夠（q10、q20 2 比 2）達到。
- 主要結果每題每組只跑 1 次；另有開跑前登記的 2 次補充重跑（第 9.1 節），不影響主要結果。第 2、3 次的 12 題 L1：實驗組 6、7 題，對照組 6、7 題（差距 0、0）。
- 限制（第 7 節與 9.3 J、9.4）：題目由 AI 起草、念誠審定並凍結；出題者與 pickfit 的開發者是同一人（個人參賽）。**L1 由和受測 agent 同一個模型（Claude Opus 5.5）盲評**，而且它判不出來（`unknown`）的都算不過，見第 2 節。

## 2. 評分方式與偏離（README 9.4）

- **L1 主判定**：念誠 11/2 22:15 決定不填 L1 表，改用 C4 的 Claude 評分者（`claude-opus-5-5`、effort high、盲評：看不到組別、次數、模型）。它只讀題目、檢查項目、首選名稱與安裝方式（q10、q20 另有答案原文；C6 的 4 項另有官方 repo 的 README 與授權），沒有上網查。
- **揭露（9.3 H.2）**：這個評分者和受測 agent 是同一個模型；若有偏好自己文字的傾向，最可能偏向對照組。
- **`unknown` 算不過**（C1：所有 [L1] 項目都過才算）。第 1 次 12 題裡判成 `unknown` 的：對照組 q02、q09、q11、q14、q16；實驗組 q01、q02、q11、q14；rules-only q01、q02、q09、q14、q16。只做描述、不改任何計數：若把 `unknown` 都當成過，12 題是實驗組 12、對照組 11、rules-only 11。結論對 `unknown` 怎麼算很敏感。
- **Muse Spark Open** 是第三份，只描述（第 8 節列出不一致）。
- **L2**：Linux 17 題照 9.3 在 Modal 沙盒；Mac 題（q08、q11、q12）改由 agent 在 tart 虛擬機做（念誠 11/2 決定），q08 因為 macOS 客體沒有巢狀虛擬化而兩組都「未實跑」。念誠 11/2 22:15 決定之後不再跑新的 L2（當時只剩 q11 實驗組在跑）。
- **C6**：q01 對照組的主要結論是「沒有工具符合」。agent 搜尋（cc-switch-cli）與念誠的搜尋（ChatGPT 建議的 mcpfold、sync-agents-settings、agentlink）的 4 個候選裡，Claude 評分者判 3 個 L1 通過（mcpfold、cc-switch-cli、sync-agents-settings），所以「沒有工具符合」被推翻，q01 對照組 L1 不過。

## 3. 20 題第 1 次

L1 欄：過／不過（括號是評分者原判為 `unknown`）。L2 欄：照 C1，所有 [L2] 項目都實跑而且都過才算過。q10、q20 的 L1 欄是它們的 [L3]。

| 題 | 難度 | 對照組首選 | L1 | L2 | 實驗組首選 | L1 | L2 | rules-only 首選 | L1 |
|---|---|---|---|---|---|---|---|---|---|
| q01 | 困難 | 沒有工具符合（C6 推翻） | 不過 | 不過 | mcpshare | 不過（unknown） | 不過 | mcpshare | 不過（unknown） |
| q02 | 中等 | leakguard | 不過（unknown） | 不過 | leakguard | 不過（unknown） | 不過 | leakguard | 不過（unknown） |
| q03 | 容易 | qsv | 過 | 不過 | DuckDB CLI | 過 | 不過 | qsv | 過 |
| q04 | 容易 | SOPS | 過 | 不過 | SOPS | 過 | **過** | SOPS | 過 |
| q05 | 中等 | Docling | 過 | 不過 | Docling | 過 | 不過 | Docling | 過 |
| q06 | 中等 | @ivotoby/openapi-mcp-server | 過 | 不過 | 同左 | 過 | 不過 | AWS Labs openapi-mcp-server | 過 |
| q07 | 容易 | Bruno | 過 | 不過 | Bruno | 過 | 不過 | Bruno | 過 |
| q08 | 容易 | Colima | 過 | 未實跑 | Colima | 過 | 未實跑 | Colima | 過 |
| q09 | 中等 | Backlog.md | 不過（unknown） | 不過 | Beads (bd) | **過** | 不過 | Backlog.md | 不過（unknown） |
| q10 | 中等 | 內建 git diff --color-words | 過（L3） | **過** | 內建 git diff --word-diff | 過（L3） | 不過 | 內建 | 過（L3） |
| q11 | 困難 | Ollama + Llama-3-Taiwan-8B | 不過（unknown） | 不過 | Ollama + Llama-Breeze2-8B | 不過（unknown） | 不過 | Ollama + TAIDE | 不過 |
| q12 | 容易 | mlx-lm | 過 | 不過 | mlx-lm | 過 | 不過 | mlx-lm | 過 |
| q13 | 容易 | llama.cpp llama-server | 過 | 不過 | 同左 | 過 | 不過 | 同左 | 過 |
| q14 | 中等 | Infinity | 不過（unknown） | 不過 | Xinference | 不過（unknown） | 不過 | Infinity | 不過（unknown） |
| q15 | 中等 | whisper.cpp | 過 | 不過 | whisper.cpp | 過 | 不過 | whisper.cpp | 過 |
| q16 | 困難 | mdpo + Ollama + 翻譯模型 | 不過（unknown） | 不過 | llama.cpp llama-server + EuroLLM | **過** | 不過 | Ollama + AMALIA-9B | 不過（unknown） |
| q17 | 中等 | aichat | 過 | 不過 | aichat | 過 | 不過 | aichat | 過 |
| q18 | 中等 | ollmcp | 過 | 不過 | ollmcp | 過 | 不過 | ollmcp | 過 |
| q19 | 容易 | Aider | 過 | 不過 | Aider | 過 | 不過 | Aider | 過 |
| q20 | 容易 | 內建 Ollama 的 OpenAI 相容端點 | 過（L3） | **過** | 同左 | 過（L3） | **過** | 同左 | 過（L3） |

20 題合計 L1：對照組 14、實驗組 16、rules-only 14。L2 通過：對照組 2（q10、q20）、實驗組 2（q04、q20）。L3（q10、q20）：三組都 2 題。

## 4. 門檻（9.1 D，都用第 1 次）

| | 結果 | 判定 |
|---|---|---|
| D1 主要主張 | 12 題：實驗組 8、對照組 6，差 2（需要 ≥ 3）。實驗組贏：q09、q16；輸：無 | 未達到 |
| D2 不退步 | 容易 8 題：8 比 8；對照組過、實驗組沒過的題：無 | 達到 |
| D3 L2 | 兩組都把 [L2] 跑完的 18 題（排除 q08 未實跑、q16 實驗組的 L2-5、L2-7 未校準）：2 比 2 | 達到 |
| D4 內建就夠 | q10、q20 的 [L3]：2 比 2 | 達到 |
| D5 不誇大 | 實驗組與 rules-only 所有次數：518 筆主張找得到、**1 次違反**、3 筆無法檢查 | **未達到** |
| D6 rules-only | 12 題 6 題，少於實驗組 8 題 | 只報告 |

- **D5 的違反**（照 D5 寫明次數與內容）：第 1 次 q14 rules-only 的 `find_software` 回應，工具 `jevalt`、linux x86_64，`features.checked` 三項（`python3 /tmp/check_f1.py`、`check_f2.py`、`check_f3.py`）。開跑前 commit 的比對規則要求 replay 裡有完全相同指令的通過檢查；原始紀錄 `verify-jevalt-20261101-163415-6a0e` 的檢查指令是把 heredoc 寫檔與 `python3 /tmp/check_fN.py` 合成一行，三項都通過、印出預期訊號，資料檔把 heredoc 拆到 setup、指令只留最後一行。照規則算 1 次違反，比對規則沒有改。3 筆無法檢查都是被 Claude Code 擋下、沒到伺服器的呼叫。
- Haiku 與 B 題組的 D5 分開列（第 6 節）。

## 5. 補充重跑（第 2、3 次，只描述）

- 12 題 L1：第 1 次 實驗組 8、對照組 6；第 2 次 6、6；第 3 次 7、7。
- 不穩定（三次 L1 不全相同；20 題三次都有結果）：對照組 q16（不過、不過、過）；實驗組 q09（過、不過、不過）、q16（過、不過、過）。

## 6. 次要分析（只描述，不寫進結論第一句）

- **受測 agent 換成 Haiku 時**，中等＋困難 12 題 L1：實驗組 5 題、對照組 7 題（20 題：13、15）。D5：0 違反、61 找得到、2 無法檢查。
- **B 題組**（12 題公開提問，探索性，每組每題 1 次）：L1 實驗組 3 題、對照組 3 題（b01–b03 兩組都過，其餘兩組都不過；b04–b07、b09–b12 有評分者 `unknown`）。B 題組 L2 沒有做。D5：3 次違反，都是規則 (e) 的句子比對（b11 的 well_known「PostgreSQL MCP Server」句子 "…run on Linux…"；b12 的 indexio、agent-lsp 句子 "Verified only on linux x86_64, not on macOS, though platforms lists macOS."），內容在 run-log。
- **盲測偏好**（第 1 次，念誠）：對照組 7、實驗組 7、平手 6。偏好實驗組：q01、q03、q04、q09、q10、q11、q16；偏好對照組：q05、q06、q07、q14、q17、q18、q20；平手：q02、q08、q12、q13、q15、q19。**限制**：念誠說他從「查了工具、沒有找到合適的，所以推薦…」這類寫法認得出接了 pickfit 的答案；去識別留下了這類寫法與 `[source]` 佔位字，20 題裡 18 題只有實驗組那邊有（`blind/prefer-run1/blinding-tells.json`）。理由欄大多空白，他的兩段口述在 `blind/prefer-run1/prefer-notes.md`。
- **長尾標記**（第 5 節）：沒有做（時間）。

## 7. 輸題原因（E，只標第 1 次；Claude 標記為準、Muse 描述）

要標的 17 題：實驗組 L1 不過（q01、q02、q11、q14）或 L2 實跑後不過（q01–q03、q05–q07、q09–q19，q08 未實跑不標），以及輸給對照組（q10 的 L2）。

| 主要原因 | 題 |
|---|---|
| `tool_error`（pickfit 回空結果；不是錯誤或逾時） | q01、q02、q03、q05、q06、q07、q09、q10、q12、q14（次要：q02、q14 `no_known_fit`；q09 `filtered_out`） |
| `filtered_out`（參考工具在候選庫，但沒進資料） | q11、q15（次要 `not_in_data`）、q16（次要 `not_in_data`） |
| `other` | q13（agent 第一次呼叫送了壞掉的 JSON、被 Claude Code 擋下，重試後 pickfit 回了別的工具，agent 選自己找的 llama.cpp）、q17、q18、q19（pickfit 回了別的工具，agent 選自己找的參考工具，L1 過；L2 在安裝就失敗：q17 `less` 不在映像裡、q18 沒有 uv、q19 的 `brew install aider` 在 Linux 上沒有 brew） |

- Muse 不一致：q11、q13、q15（Muse 標 `not_matched`），其餘 14 題相同。
- 規則：標記只說明原因，不排除或調整任何計數。證據包在 `e-tags/bundles-run1.json`（工具名稱比對，可能漏）。
- **pickfit 空回應**（協調 session 要的）：實驗組在 20 題 4 輪與 B 題組共 82 則 pickfit 回應，51 則沒有任何推薦（20 題 71 則中 42 則、B 題組 11 則中 9 則）。這 51 則**都是「pickfit 的資料裡沒有任何通過 L1 的工具」**（0 則漏掉）：該題通過 L1 的工具都不在 4e0dd4b 的 `data/software`（比對名稱，人工核過；b03 的 Atlas 是名稱撞到不同的專案）。也就是說，空回應對 pickfit 自己的資料來說是對的，但那些題的正確工具多半是已知的大專案（Bruno、Docling、aichat 等），pickfit 的資料沒有收。

## 8. 評分者一致性（只描述）

- Claude 與 Muse 不一致：A 批 6 項（q06 @ivotoby/openapi-mcp-server 過／unknown；q09 Backlog.md unknown／過；q11 Ollama + Breeze2 unknown／過；q17 aichat 過／unknown；q11 Ollama + TAIDE 不過／Muse 沒有判定（回覆不是合法 JSON）；q06 openapi-2-mcp unknown／過）、B 批 8 項（b08 Open WebUI 不過／過；b09 兩項、b07 兩項、b06 unknown／不過；b12 Serena unknown／過；b03 sqldef 過／不過）、C6 0 項。照 9.4 不拿 Muse 改判。
- 評分者判 `unknown` 的（題，首選）共 33 項，逐項在 `results.json` 的 `grader_unknown_items`。

## 9. L2 與 Mac 題的紀錄

- Linux 17 題、Mac 3 題（q08 未實跑）的每一項判定與原因在 `l2/l2-results.json`；方法、替換、評分者的失誤與重做在 run-log。重點：
  - q11 實驗組：安裝第 4 行 `ollama pull` 和 `brew services start ollama` 同一秒執行而失敗（伺服器晚 1 秒起來），照 C7 算安裝失敗、整題不過。這個 race 算不算，留給念誠在看到結果後決定；其餘項目的觀察值也記下了：不算 race 時仍是 L2-3 不過（run 1 P1 模型重複迴圈超過 10 分鐘、run 3 P1 盲評不過），所以 L2 結果一樣是不過。
  - q11 對照組：答案的第一個安裝方式是 macOS app（下載、拖進「應用程式」、打開），第一次打開跳出要密碼的授權對話框，L2-1 不過；評分者代做對話框的預設動作後，其餘項目 L2-2～L2-5 都過（L2-5 是人工對應行）。記憶體量測因為評分者的失誤沒有量到。
  - q12 兩組：`uv tool install mlx-lm` 成功，但 `mlx_lm.*` 裝在不在 PATH 裡的 ~/.local/bin，答案沒有處理，伺服器起不來。
  - q15 兩組：whisper.cpp 在 gVisor 沙盒裡沒有 SIMD，每次都到 600 秒上限；可能是環境造成的，已標出。
  - q08：另附兩組答案和官方文件差異的盲評筆記（`l2/q08-docs-note/`，不是 L2）。
- Mac 題的環境：tart 虛擬機（cirruslabs macos-tahoe-base digest `4aaa751f…`，客體 macOS 26.6.2，16 GB／8 vCPU；q12 8 GB），每組一台新 clone、跑完刪除；主機是念誠的 M5、24 GB，評測時主機記憶體吃緊，每組題目前的讀數記在 run-log。

## 10. 花費

- Anthropic：評測執行器 $19.207（含作廢的試跑）；評分 $5.54／$20（萃取首選、兩批 L1、C6、q11 盲評、q08 筆記、E 標記）。
- Baseten（Muse）：$1.17／$5。沒有用到 Meta Model API 或 pickfit-eval Worker 以外的呼叫。
