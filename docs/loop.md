# pickfit loop：收錄、驗證，發現問題就自己修 harness

2026-11-15 · 給念誠與接手的 agent。這份講為什麼這樣設計。每一圈實際怎麼做，寫在 [.claude/skills/pickfit-loop/SKILL.md](../.claude/skills/pickfit-loop/SKILL.md)。

## 要解決什麼

產品的形態大致定了，現在花力氣的地方是自動測試：沙盒少東西、安裝卡住、操作層送不進動作。這些問題多半 agent 自己想得出辦法，但以前每遇到一次就停下來等念誠批准。這個 loop 把「停下來問」換成「記下來、自己試、試不出來就擱著換下一個」，念誠改成事後看紀錄。

11/15 的現況：1,058 筆紀錄裡 324 筆未驗證，其中 43 筆的原因是 pickfit 的沙盒自己的限制（沒有 root 17、沒有編譯器 15、資源不夠 7、沒有 Docker 4）。這 43 筆是第一批佇列。

## 一圈做什麼

```
拿一個項目 ──▶ 在沙盒裡驗證 ──▶ 通過 ──▶ 寫回紀錄 ──▶ 記錄，拿下一個
                    │
                    └─ 沒過 ──▶ 是誰的問題？
                                 ├─ 軟體自己壞了 ────────▶ 照實記成未驗證，拿下一個
                                 ├─ 合理的限制（帳號、硬體）▶ 記下原因，拿下一個
                                 └─ pickfit 的 harness ──▶ 重現 → 寫測試 → 修 → 驗收
                                                             ├─ 修好：等它的項目全部排回佇列
                                                             ├─ 試三種做法都不行：擱著，拿下一個
                                                             └─ 要改判定規則：寫成提案等念誠，拿下一個
```

修好一個 harness 問題，受益的是所有卡在同一個問題上的軟體，所以佇列裡每個項目都記著它在等哪個問題（`H-001`、`H-002`…），問題一修好，`loop_state.py` 就把它們排回去重跑。

## 讓它不停下來，靠三樣東西

agent 會停，有三種原因，各用一樣東西處理。

**每個指令都要批准。** 用 Claude Code 的 auto mode：由分類器逐一判斷工具呼叫，一般的讀寫、跑測試、開沙盒直接放行，危險的才擋。這個專案原本沒有任何 allow 規則，所以在手動模式下幾乎每個指令都會跳出來問。auto mode 只能由使用者自己選（權限模式選單，或 `claude --permission-mode auto`），專案設定檔裡寫了不算數。

**做完一輪就停下來等人說「繼續」。** 用 `/goal`：給一個看得出來有沒有達成的條件，每一輪結束時由另一個小模型判斷達成沒，沒達成就自動開下一輪。判斷的模型只看得到對話，不會自己跑指令，所以條件要寫成「印出來的東西」：loop 每做完一個項目就印一行 `LOOP_STATUS todo=… done=… parked=…`。

**遇到沒把握的事就問。** 這靠規則：skill 裡寫明每種狀況該怎麼辦，以及「擱著」是一個正式的出口。每個 harness 問題最多試三種做法；每個項目最多被領三次。超過就 park，不會卡死在同一個地方，也不用問。

## 原本要批准的事，現在怎麼處理

| 以前停下來問的事 | 現在 |
|---|---|
| 可以跑這個指令嗎 | auto mode 判斷；push、發布、部署由 hook 直接擋 |
| 這個失敗要不要修、怎麼修 | 照分流規則自己決定；做了什麼寫進 `loop/journal.md` |
| 修不好怎麼辦 | 試三種做法，還不行就 park，寫清楚試過什麼 |
| 可以裝這個套件嗎 | MIT、Apache-2.0、BSD、ISC 直接用並記進 `NOTICE`；其他授權寫成提案 |
| 要改判定或計分的規則 | 不改。寫成 `loop/proposals/H-00X.patch`，問題標成 `review`，繼續做別的 |
| 要 push、發布、合併 | 不做。分支留著，念誠或協調的 session 看過再合 |

念誠要看的只有三個地方：`loop/journal.md` 裡寫「需要你」的段落、`loop/proposals/`、合併前的分支 diff。

## 怎麼防止它為了過關把標準改鬆

長時間自己跑的 agent 最常見的毛病，是把測試改到會過，或直接宣布成功。這裡分四層擋。

1. **判定不在 loop 手上。** 通過與否由管線決定：安裝 agent 跑完，換一個全新的箱子重播，再由 judge 看。寫回用 `scripts/guarded_write_back.py`，紀錄只會變好不會變差。
2. **決定判定的檔案 loop 不能改。** `verdict.py`、`judge.py`、`feature_judge.py`、`failure.py`、`limits.py`、`web_guard.py`、`score.py`、`schema.py` 和 guard 自己。`scripts/loop_guard.py` 是 PreToolUse hook，編輯這些檔案、手改 `data/software/`、刪測試、讀 `eval/` 與 `.env`、`git push`、`pickfit publish`、`wrangler deploy` 都會被拒絕，不管權限模式是什麼。
3. **hook 之外再查一次。** shell 改檔案的方法太多，hook 擋不完。所以 `scripts/loop.sh` 每跑完一批，會從 session 外面比對分支的 diff：受保護的檔案有變動，或有測試被刪，整個 loop 就停（exit 4）。這一步 session 自己動不到。
4. **修 harness 要過三關**：全部單元測試（現在 1,644 個，約 85 秒）；動到箱子就重跑 `--limits-test`，隔離不能變鬆；原本失敗的項目重跑通過，再挑一筆原本就通過的重跑確認沒變差。既有的測試可以改不能刪，改過哪些會列在 journal 請念誠看一眼。

## 花費上限

賽後帳本不再有硬性上限（沒設就不擋），所以 loop 自己有一份，寫在 `loop/budget.json`。念誠 11/15 23:55 給了兩邊剩下的額度，上限設在那之下，留一些給線上的 Worker 和其他 session：

| 帳 | 算什麼 | 總額 | 每天 |
|---|---|---|---|
| `model` | 帳本裡 `since` 之後的所有模型呼叫，不分 session、不分供應商 | US$100 | US$40 |
| `box` | 每次驗證估出來的 Modal 沙盒費用（`outcome.json` 的 `box_usd`） | US$25 | US$10 |

另外單一項目以 US$5 為限。擋的地方有三層：

1. hook：到了上限，所有要花錢的管線指令都被拒絕，session 只能記錄和收尾。
2. `loop.sh`：每批開始前檢查，到了就不開新的一批（exit 6）。
3. 帳本自己：loop 的 session 帶著 `PICKFIT_PIPELINE_DAILY_CAP_USD=40`，Anthropic 切換合併後，單日超過時模型呼叫會在送出前被帳本擋下。

`box` 這本帳是 pickfit 自己的估計，不是 Modal 的帳單，映像建置、限制檢查和網頁驗證用的沙盒沒算進去，所以上限抓得比剩餘額度低不少。Modal 後台的 workspace 花費上限只有念誠能設，建議設成剩餘的額度當最後一道。loop 改不了 `loop/budget.json`。

## 狀態都在磁碟上

| 檔案 | 內容 | 誰寫 |
|---|---|---|
| `loop/queue.jsonl` | 每個項目一行：種類、目標、狀態、等哪個問題、領過幾次 | `scripts/loop_state.py` |
| `loop/issues.md` | harness 的問題，每個一段：症狀、怎麼重現、試過什麼 | 標題列由 `loop_state.py` 管，內文由 session 寫 |
| `loop/journal.md` | 每個項目一段，只加不改 | session；每批結束 `loop.sh` 加一段 |
| `loop/proposals/` | 要念誠決定的修改 | session |
| `loop/settings.json` | loop 專用的 hook 與 deny 規則 | 人；loop 不能改 |
| `loop/budget.json` | 花費上限與起算時間 | 人；loop 不能改 |

session 不靠記憶。每個 session 開始時讀這些檔案，結束時什麼都不用交接。

## 兩種跑法

先跑 `scripts/loop_setup.sh`：它開一個 loop 專用的 worktree（分支 `loop/<日期>`），連上主 checkout 的 `.env` 與 `runs/`，把 `loop/settings.json` 裝成那個 worktree 的 `.claude/settings.local.json`。hook 只在那個 worktree 生效，其他 session 不受影響。

**看著跑**：在那個資料夾開一個 Claude Code session，權限模式選 Auto，貼上 `loop_setup.sh` 印出來的那行 `/goal`。看得到每一步，隨時可以插話。適合頭幾次。

**放著跑**：`scripts/loop.sh`。每一批（預設 3 個項目）開一個全新的 `claude -p` session，跑完就結束，由腳本檢查、記錄，再開下一批。每批用全新的 session，是因為同一個 session 跑久了，前面的內容會被壓縮，判斷跟著變差。Anthropic 寫長時間 agent 的幾篇文章和社群的 Ralph loop 都是這個做法：狀態放檔案，context 用完就丟。停止的條件有五個：佇列空了、跑滿批數（預設 10）、`touch loop/STOP`、連兩批沒有任何進展、碰了受保護的檔案。

`loop.sh` 要在自己的終端機裡跑，而且那個 shell 不要 export `ANTHROPIC_API_KEY`，不然 `claude` 會改用 API key 計費（plan 第 2 節第 7 條）。

## GUI 操作改用現成套件（H-006）

現況是兩層都自己寫：模型端是 pickfit 自訂的動作格式（click、type、key、scroll、wait），執行端 Linux 用 xdotool、macOS 從主機經 VNC。滾輪進不了 macOS VM，就是因為 Virtualization.framework 的 VNC 不收滾輪事件。11/3 的繞法是在 VM 裡跑一段 JXA 送 CGEvent，可以用，但拖曳、右鍵、組合鍵都還得各寫一次。

建議分兩層換，Linux 先做。

**模型端：改用 Anthropic 的 computer use 工具**（`computer_toolset_20260801`）。它定義了 17 個動作：截圖、放大、左中右鍵、雙擊、三擊、拖曳、按下與放開、移動、捲動、打字、按鍵、按住某鍵、等待。賽後模型本來就換成 Claude，這套動作是模型本來就會的，不用自己設計格式和提示。它是 client-side 的工具：Anthropic 只定義動作，執行由我們接，所以驗收和蒐證的做法都不用變。（官方文件查證過。）

**執行端**：

| 環境 | 建議 | 為什麼 | 查證到哪 |
|---|---|---|---|
| Linux（Modal） | Anthropic 官方範例 computer-use-demo 的執行器（MIT，xdotool） | 和現在同一條 XTEST 路徑，gVisor 下不用新東西，不開連接埠；多了拖曳、按下放開、水平捲動、放大 | 授權與做法來自查詢結果，動手前再看一次原始碼 |
| macOS（tart） | 在 GUI 基底映像裡裝 cua-driver（MIT），主機用 `tart exec` 呼叫它的 CLI | 動作在 VM 裡面送，捲動和拖曳都進得去，還拿得到 accessibility tree；走 stdio，不開連接埠 | 授權、平台、CLI 與 MCP 介面查證過；在 tart 上還沒試過 |

cua-driver 需要「輔助使用」和「螢幕錄製」兩個權限，要在做基底映像時先寫進 TCC。它的影像辨識擴充 cua-perception 是 AGPL，不裝。

沒有採用的：OSWorld 的 guest server（Flask 開在 0.0.0.0:5000，沒有認證）、ydotool（AGPL）、cua 舊的 computer-server（已停止維護）。Bytebot、UI-TARS-desktop、macOS-use 查到的狀態是已封存。

換的位置是 `gui_operate.py` 裡 display 的介面（`screenshot`、`click`、`type_text`、`key`、`scroll`）。套件只負責送動作、拿截圖與元件清單。結果照舊由 pickfit 自己檢查（檔案、剪貼簿、畫面上的字、nonce）。賽後方針是暫不優先收 macOS 的 GUI App，所以 macOS 那一半排在 Linux 後面。

## 資安

- **控制通道不開連接埠。** 控制程式裝在 guest 裡，主機用 exec 通道（Modal 的 exec、`tart exec`）叫它。被測的軟體和控制程式是同一個使用者，若控制程式開了本機的 HTTP 埠，被測的軟體就可能自己去叫它，所以只用 CLI 或 stdio。
- **金鑰和模型呼叫留在主機。** guest 裡沒有任何金鑰（既有規則），模型的迴圈在主機上跑，guest 只收到動作。
- **一次驗證一個全新的箱子**，用完就丟。網路沿用現有的限制（擋 metadata 與私有網段，可以整個斷網）。
- **畫面上的字是資料，不是指令。** Anthropic 會用分類器掃 computer use 回傳的截圖，但官方仍建議隔離、不給帳密、限制可連的網域。pickfit 在主機端檢查每個動作，驗收也不靠模型的說法。
- **套件釘住版本並核對 checksum。**
- **loop 自己的權限。** auto mode 不是安全保證，所以另外有 hook、deny 規則和批次後的外部檢查；loop 只在自己的 worktree 和分支上動，不 push、不發布。

## 還沒做、還沒驗證的

- **還沒跑過任何一批。** 測過的是 `loop_state.py` 與 `loop_guard.py`（50 個單元測試）、guard 直接吃 hook 輸入的行為、`loop.sh --dry-run`。
- **hook 在真的 session 裡會不會擋，還沒實測。** 從寫這份文件的 session 裡起 `claude -p`，回的是 `Credit balance is too low`（那個環境走 API key 登入）。`loop_setup.sh` 之後先跑一次 `scripts/loop.sh --probe`，它會開一個小 session 試著改 `verdict.py`，確認被擋。
- **佇列裡 43 筆，目前 `verify --batch` 只選得到 7 筆**（H-001）。loop 的第一件事多半是修這個。
- **模型**：Anthropic API 的切換在另一個 worktree 進行中。loop 用的是管線當下設定的模型，切換合併後不用改 loop。
- **Modal 的實際花費沒有進帳本。** `box` 的上限靠的是估計值，見「花費上限」一節。

## 參考

- Claude Code：[/goal](https://code.claude.com/docs/en/goal)、[權限模式與 auto mode](https://code.claude.com/docs/en/permission-modes)、[hooks](https://code.claude.com/docs/en/hooks)、[headless](https://code.claude.com/docs/en/headless)
- Anthropic 工程文章：[Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)、[Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)、[Building a C compiler](https://www.anthropic.com/engineering/building-c-compiler)
- 社群：[Ralph loop](https://ghuntley.com/ralph/)（Geoffrey Huntley）、官方的 [ralph-loop plugin](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/ralph-loop)
- Computer use：[Anthropic 的工具文件](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)、[computer-use-demo](https://github.com/anthropics/claude-quickstarts/tree/main/computer-use-demo)、[cua-driver](https://github.com/trycua/cua/tree/main/libs/cua-driver)
