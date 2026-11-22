# brief 第 15 節落差盤查（2026-11-22）

> 對象是 `main`（e269337c，brief 第 15 節剛合進來）。只讀程式與資料，沒有改其他檔案，沒有呼叫付費 API，沒有開沙盒或 VM，也沒有讀 `eval/`、`.env`。資料數字來自附錄的本機 Python 腳本（只讀 `data/software/*.json`，免費），程式位置是讀原始碼確認過的 `file:line`。
>
> 和 [product-ux-cost-audit.md](product-ux-cost-audit.md)（11/20）重複的項目不再展開，只在第五節標出哪些已經做完、哪些和第 15 節有關要一起做。

## 一、總結與最大的五個落差

**一句話**：第 15 節要 pickfit 從「收很多、驗一次」改成「少而精、持續重驗、推得嚴」。現在的程式和資料幾乎全是前者的形狀：每筆紀錄都沒有賽道、沒有過期日、沒有失效狀態，重驗只在使用者回報失敗時才會發生，而且重驗失敗也不會寫回紀錄。

| # | 落差 | 實測 | 對應 |
|---|---|---|---|
| G1 | **驗證會一起過期，但沒有任何過期機制。** 988 筆有驗證的紀錄全部在最近 30 天內驗的；沒有重驗週期、沒有到期日、沒有「被查到才重驗」。唯一的時間規則是 90 天後在回答裡加一句提醒（`worker/src/freshness.ts:8,35`）。 | 988／988 在 30 天內；0 筆有到期日 | 15.4 |
| G2 | **失效寫不進紀錄。** 管線從不寫 `failed`（`pickfit/verify/result.py:537-538`），重驗沒過時紀錄原封不動（`pickfit/reverify.py:418-423`），重驗通過但步驟相同時連 `checked_at` 都不更新（`reverify.py:429-432`）。「以前能用、現在裝不起來」這件事，pickfit 目前記不下來。 | 1,274 筆裡 `failed` 只有 1 筆（人工） | 15.4 |
| G3 | **推薦門檻比第 15.6 節寬。** 只要裝得起來就會被推（`worker/src/filter.ts:50-51`），install 等級的 187 筆照樣進候選；寶藏也不要求 function（`pickfit/schema.py:313` 的 `TREASURE_MIN_FUNCTION_COVERAGE = None`），202 款寶藏裡有 13 款只到 install。也沒有「新作」標記，年輕的 repo 在維護分數裡反而被加分（`pickfit/score.py:531-533`）。 | listed 且 function 以上 732 筆；install 187 筆 | 15.6、15.4 |
| G4 | **schema 沒有賽道、使用者是人還是 agent、重用方式、介面屬性。** 現有的 `audience` 是 `end_user／import_only`（`pickfit/schema.py:68`），意思是「能不能直接用還是只能 import」，和 15.2 的「人用還是 agent 用」不同，直接沿用這個名字會撞名。 | `audience` end_user 1,207／null 67；`maturity` null 1,071 | 15.2、15.3、15.5 |
| G5 | **MCP 回答還不會回答「直接用／擴充／參考自己做／自己做就好」。** prompt 只有「內建就夠了」（`worker/src/prompt.ts:20` 規則 9），回答 schema 沒有重用方式或「自己做」的欄位（`prompt.ts:81-127`、`worker/src/find.ts:136-138`）。工具說明也沒告訴 agent「動手寫之前先來查」（`worker/src/server.ts:551`）。 | — | 15.1、15.5 |

另外三件小但會誤導人的事：

- **brief 15.4 的一個數字要更正。** 804 筆沒有推送時間，brief 說是「網頁、Flathub 等不是從 GitHub 來的」。實測其中 **751 筆有 GitHub repo**，只是 `scores.inputs.github` 是 null（schema 的說明是「not recovered; fetched at the next score」，`pickfit/schema.py:1806`），真正沒有 repo 的只有 53 筆網頁應用。補齊維護訊號的第一步因此很便宜：重抓 GitHub 就有，不用先發明替代訊號。
- **「988 筆全部是黑客松期間驗的」也要小修。** 776 筆在 11/04 以前，212 筆在 11/05 之後。結論不變：全部在 30 天內，會在同一段時間一起過期。
- **`last_release` 凍結在抽取當下。** 只有 `pickfit/profiles.py:402-404` 會寫它，沒有排程更新。所以「出了新版本，步驟可能不同」的提醒（`freshness.ts:22-28`）目前 0 筆會觸發，不是因為沒有新版本，而是 pickfit 不知道。

## 二、資料模型與現有目錄

### 2.1 1,274 筆的真實分佈（11/22 本機量）

**狀態與類型**

| 項目 | 數字 |
|---|---|
| 總數 | 1,274（listed 1,265、hidden 9） |
| kind | cli_tool 458、desktop_app 240、mcp_server_or_agent_plugin 226、web_app 114、server_daemon 91、tui 83、self_hosted_web_app 60、browser_extension 2 |
| category | dev_cli 339、local_ai 298、mcp_server 230、other 213、security_net 46、media_files 45、infra_devops 36、data_db 35、productivity_docs 32 |
| 首次收錄 | 10 月 648、11 月 626 |

**驗證**

| 項目 | 數字 |
|---|---|
| 等級 | function 522、unverified 352、service 192、install 188、inference 19、failed 1 |
| 沒驗證的原因 | not_run 285、needs_root 14、needs_account 12、suspected_tool_fault 11、其他 30 |
| 最後驗證時間 | 10 月 244、11/01–11/04 532、11/05 之後 212、從沒跑過 286 |
| 驗證距今 | 全部 < 30 天 |
| 驗過的系統 | 只有 Linux 828、Linux＋macOS 86、只有 macOS 65、含 Windows 9 |
| 有逐項功能檢查 | 468 筆 |
| 有 `readme_wrong` 避坑 | 195 筆（15.5 說的「累積下來的知識」雛形） |
| GUI 等級 | ui_rendered 118、action_checked 26、window 2 |
| `usability` 有值 | **0 筆**（schema 有欄位，資料裡沒有） |

**維護訊號**

| 項目 | 數字 |
|---|---|
| 有 GitHub `pushed_at` | 470；距今 < 30 天 414、30–60 天 42、60–90 天 4、90–180 天 5、180–365 天 1、> 1 年 4 |
| 沒有 `pushed_at` | 804；其中 751 有 repo（GitHub 資料沒補回）、53 沒 repo（網頁應用） |
| 有 `last_release` | 1,053；距今 < 30 天 550、30–60 天 258、60–90 天 68、90–180 天 75、180–365 天 68、> 1 年 34 |
| 推送時間和 release 都沒有 | 167 |
| repo 建立時間（只有 470 筆有） | < 30 天 6、30–90 天 94、90–180 天 99、180–365 天 134、> 1 年 137 |
| 有測試目錄（470 筆中） | 438 |

**安全、分數、使用結果**

| 項目 | 數字 |
|---|---|
| security.status | clean 559、vulnerable 354、unchecked 354、null 7；被 known_vulnerability 封頂 29 |
| 寶藏 | 202（function 126、service 56、install 13、inference 7）；其中 131 筆沒有 GitHub 原始資料，維護分數用的是 legacy 值 |
| 外部使用回報 | **全部 1,274 筆都是 0** |

**影片與截圖**

| 項目 | 數字 |
|---|---|
| 有影片 | 10 筆（desktop 6、web 4），共 405 秒，都是 11/02–11/03 錄的 |
| 有截圖路徑 | 834 筆（但都在本機 `runs/`，沒有上線，見 3.1） |
| 有 `evidence_url` | 0 筆 |

**各賽道的現況**

| 賽道 | 數字 |
|---|---|
| MCP server（kind 或 category） | function 38、service 133、unverified 77；握手斷網也能過 147、只在有網路時過 10；有成功呼叫一個 tool 132 筆；安全 clean 160、vulnerable 69、unchecked 19；描述裡有提示注入樣式而留下 note 的只有 2 筆 |
| web_app | function 73、install 29、unverified 12；PWA 驗過離線 6；第三方網域 0 個 35、1–5 個 58、超過 5 個 9；看到廣告 10；資料外送 none 52、unknown 38、observed 12；102 筆全部用 1280×900 的桌面尺寸測 |
| desktop_app | 240 筆，function 只有 31（install 123、unverified 86）；類別 other 120、local_ai 64、media_files 16、dev_cli 15、productivity_docs 7 |

### 2.2 先用 kind 粗分三條賽道（規則推得出來的部分）

不呼叫模型，光看 kind 與 category 就能先分掉九成：

| 暫定賽道 | 規則 | 筆數 | function 以上 |
|---|---|---:|---|
| A. agent 用的能力 | cli_tool、tui、mcp_server_or_agent_plugin、server_daemon、self_hosted_web_app | 918 | 多數 |
| B. 人用的網頁 | web_app | 114 | 73 |
| C. 人機協作的創作與文件工具 | desktop_app 且在 media_files／productivity_docs，加上 mcp-for-blender 這類「創作 App 的 MCP」 | 約 24 | 7 |
| 不屬三條、照 plan.md 第 8 節暫緩 | 其餘 desktop_app（other、local_ai、dev_cli 等） | 約 217 | 24 |
| browser_extension | 再議 | 2 | — |

要人判斷的是 self_hosted_web_app（例如 Trilium、BookStack 是人在用的 UI，卻是自架服務）和 C 的邊界。建議 schema 讓規則先填、模型或人再覆寫，並記錄來源（`evidence.method = rule／model／human`，現有機制就支援，`pickfit/schema.py:145`）。

### 2.3 schema 缺口

欄位定義在 `pickfit/schema.py:2498-2590`（`SoftwareRecord`），JSON schema 由它產生（`schema/software.v1.json`）。

| 需要的屬性 | 現況 | 建議 |
|---|---|---|
| 誰用（人／agent／兩者） | 沒有。`audience`（`schema.py:68,2515`）是 end_user／import_only，語意不同 | 新欄位 `used_by: human｜agent｜both`，**不要沿用 audience 這個名字** |
| 賽道 A／B／C | 沒有 | `track: A｜B｜C｜none`，加 `track_basis`（rule／model／human） |
| 對外介面（15.3 C 的「有沒有 MCP、命令列或腳本介面，能做到多少」） | 只有 `mcp`（限 category mcp_server，`schema.py:2559`）和自由文字的 `capabilities`（`schema.py:2480-2495`）。關鍵字粗估 415 筆提到 plugin／API／hook | `interfaces: [{kind: mcp｜cli｜scripting｜plugin｜api, coverage: full｜partial｜read_only, evidence}]` |
| 重用方式（15.5） | 沒有。可用的原料：`RepoFiles.tests`（`schema.py:1752-1760`，只記有沒有）、`capabilities`、`readme_wrong` 避坑 | `reuse_fit: {mode: use_directly｜extend｜reference｜fork_not_advised, basis}`；判斷依據先用規則（有擴充介面 → extend；有測試且模組化 → reference） |
| 最後一次通過 | 沒有。`Verification.checked_at` 是「任何結果的最新一次」（`schema.py:1463`），不是最後通過 | `last_passed_at` |
| 重驗週期與到期日 | 沒有 | `reverify_cycle_days`（依依賴類型，起始值 30／90）、`reverify_due_at` |
| 失效、不推薦 | `status` 只有 listed／hidden／removed（`schema.py:2509`）；`failed` 只能來自人工或套件檢查（`schema.py:1437-1441`） | `standing: active｜new｜stale｜broken`，和 `status` 分開。broken 保留在目錄、不進推薦 |
| 新作 | `first_seen_at` 有，沒有東西讀它 | `standing = new`，直到活過 N 個週期 |
| 替代維護訊號 | `registries.py` 只讀下載數（`pickfit/registries.py:1-16`）；網頁只在收錄時查一次活著沒（`pickfit/web_intake.py:1-26`） | `maintenance_signals: {registry_latest_at, site_alive_at, content_updated_at}` |
| 預覽（B、C 用） | 只有 `RunVideo`（`schema.py:1118-1179`）；截圖路徑在 `RunEvidence`（`schema.py:1020`）但不上線 | `preview: {image, captured_at, run_id}`，一張圖或幾秒，不是教學 |
| 資料品質（B 的拉麵地圖類） | 沒有 | 先記 `content_updated_at`，評分另議 |

### 2.4 `priority-20261120.md` 和三條賽道的對齊

這份清單有 106 款（P0 55、P1 51），寫成的時候目錄是 1,220 筆。實測現在**已有 44 款收進來**（11/20–11/21），等級如下：

- function 23（DuckDB、Typst、Neovim、uv、Ruff、ImageMagick、qpdf、OBS、Blender MCP 等）
- service 5（Dolt、Caddy、Prometheus、AnythingLLM、Excel MCP）
- inference 1（llama.cpp）、install 1（calibre）
- **unverified 14**：Paperless-ngx、Karakeep、BookStack、Immich、Jellyfin、OCRmyPDF、Grafana、Vaultwarden、Headscale、Semgrep、testssl.sh、vLLM、Home Assistant、uBlock Origin。多數是當時缺服務或 root；11/21 合進來的 grants 與 full-privilege box（commit `dd667afc`、`3997cf8e`）之後可以重驗。

清單的 kind 分佈：cli_tool 43、self_hosted_web_app 28、server_daemon 10、desktop_app 10、mcp 8、tui 4、web_app 2、browser_extension 1。沙盒需求 linux 76、linux+services 19、linux+display 16、web 15。

對齊結論：

- **A 賽道對得很好。** 九成是知名、有人維護、Linux 沙盒驗得了的工具，正好符合 15.1「現在驗過、還有人維護」與 plan.md 第 8 節。和 brief 早期「默默無聞」的定位有點距離，但 15.1 已經說冷門不是護城河，這不算衝突。剩下 62 款照原計畫送管線即可。
- **B 賽道幾乎是空的。** 只有 drawDB 和 Squoosh 兩款，而且 Squoosh 是「要的只是結果」的轉檔工具，照 15.3 是遲早被 agent 取代的那一類。沒有一款是地圖、多人互動、遊戲這種「過程本身就是價值」的，也沒有台灣在地的。B 不適合用「同類最佳」的方式策展，比較適合走投稿與 Show HN 的網頁作品，另開一份清單。
- **C 賽道有幾款但沒成組。** 清單裡算得上 C 的有 Blender MCP、Excel MCP、Zotero 與 Zotero MCP、calibre、OBS、Xournal++、Marp／Slidev、Typst。15.3 要的是「GUI＋給 agent 的介面」成對，清單卻沒有 GIMP、Inkscape、Krita、Kdenlive／Shotcut、LibreOffice、darktable、Scribus（目錄裡也都還沒有）。建議補一份 C 清單，每款寫明 GUI 本體、MCP／腳本介面各是哪個 repo、授權（收錄前逐款查證，brief 15.3 也這樣要求）。
- **該降級的**：Thunderbird、Espanso、uBlock Origin 是人用的桌面或瀏覽器工具，不屬三條賽道，又是 plan.md 第 8 節暫緩的 GUI 類，建議從 P0／P1 移到「暫緩」。
- **清單本身要加一欄 `track`**，送管線時就把賽道寫進紀錄，不必事後回填。

## 三、驗證、防 slop 與新鮮度管線

### 3.1 停止新增教學影片（15.7）

現況分兩段：

- **原始錄影是自動的。** `PICKFIT_RECORD` 預設是 `replay`（`pickfit/verify/record.py:84`），所以每次 GUI 重跑都會錄 `replay-*.mp4` 到 `runs/`；`pickfit/verify/gui_operate.py:2102-2104` 開錄，`:2148-2152` 為了影片多等 `record.TAIL_S`。
- **剪成影片、掛上紀錄是手動的。** 入口是 `python -m pickfit.verify.video make`（`pickfit/verify/video.py:2655-2729`，`make` 在 `:2721-2728`）與 `pickfit/verify/web_video.py:541-549`。另一條是 `pickfit mac-host test --record`（`pickfit/verify/mac_host.py:738-740,940-942`）。watch、reverify、loop skill、systemd、CI 都沒有影片步驟。

要改的地方：

1. `record.py:84` 預設改成 `off`，`gui_operate.py:2148-2152` 的等待只在開錄時才等。
2. `mac_host.py:940-942` 的 `--record` 拿掉或改成需要明確環境變數。
3. **coverage 會把每一筆新的 GUI／網頁紀錄算成缺口**：`pickfit/coverage.py:796-814` 在「有通過的操作但沒影片」時回 `video.not_recorded`，算進 `verified_share`，頁面上顯示「使用中的影片：還沒有」。要改 `DIMENSIONS`（`coverage.py:93`）、缺口代碼（`:187`）、能力表（`:315`）、說明（`:29,34`）、重跑提示（`:1189`，這個提示本來就錯，verify 不會產生影片），並同步 `worker/src/catalog.ts:457` 與 `worker/src/ui/coverage.ts:19`。建議把 video 維度換成 preview，沒有影片時回 `not_applicable`。
4. 舊的 10 支影片照舊顯示：`pickfit/index.py:217-258` 與 `worker/src/pages/tool.ts:529-580` 不動。
5. 文件：`docs/proposals/video.md:17-86` 標成已停止，`docs/proposals/README.md:16` 同步。
6. 影片停掉之後，`pickfit/meta.py:202-206,486-517` 的影片 token 估算只剩 `video.py` 在用，可以留著（舊影片重剪還用得到），不急著刪。

**改成機器可讀紀錄加預覽**：機器可讀的部分其實已經有了（指令、輸出、smoke test、`judge.observed`、避坑），差在**上線**：`evidence_url` 0 筆有值（`index.py:243-259` 匯出這個欄位但資料是空的）。預覽要補的是整條上線路徑：

- 截圖目前只在本機 `runs/`，`scripts/copy_evidence.py` 只複製到 `~/.pickfit/evidence/`，不在 R2。
- `index.py:_run_summary`（`:243-259`）沒有匯出截圖。
- Worker 唯一的圖片路由是影片海報（`worker/src/video.ts:13-19,46-55`）。
- `tool.ts:529-531` 的 `showcase()` 沒影片就回空字串，1,264 筆的工具頁頂端什麼都沒有。

最省事的做法是借用海報那條路：`video.py:2513`（`make_poster`）和 `:2550`（R2 上傳）處理一張截圖，`video.ts` 允許這個檔名，`index.py` 匯出，`showcase()` 沒影片時改顯示截圖。網頁應用有 `install.png`、`after.png` 可挑（`pickfit/verify/web_record.py:199-210`）。

### 3.2 過期、分級重驗、被查到才重驗、失效不刪（15.4）

| 15.4 的規則 | 現況 | 缺什麼 |
|---|---|---|
| 看最後一次驗證通過 | `checked_at` 是任何結果的最新一次（`schema.py:1463`）；重驗通過但步驟相同不更新（`reverify.py:429-432`） | `last_passed_at`，重驗通過就更新 |
| 依依賴變動速度分級 | 沒有任何週期。唯一的時間規則是安全掃描每週一次（`deploy/watch/pickfit-security-weekly.timer`，`pickfit/maintenance.py:103-115`） | 週期設定表（外部 API、MCP、網站 30 天；本機 CLI 90 天）與到期日 |
| 資安公告一出就重掃 | 每週掃 7 天沒掃過的，不是公告觸發 | 可以先維持每週，公告觸發列 Phase 3 |
| 被查到才重驗 | 重驗佇列只吃使用者的失敗回報（`worker/src/outcome.ts:85-97`），每天跑最多 3 筆，要人啟用（`deploy/watch/pickfit-reverify.service:18`），結果 commit 到審查分支（`maintenance.py:130-145`） | `find_software` 回傳到期的紀錄時，順便寫一筆 `reason=due` 進同一張 `reverify_queue` |
| 回答標「上次驗證是 N 天前」 | `freshness.age_days` 有，但文字只在超過 90 天或有新版本才出現（`freshness.ts:30-39`）；卡片只把日期塞在 `verified_on` 字串裡（`worker/src/cards.ts:78`） | 每個 pick 都帶一句，週期改成依紀錄的 `reverify_cycle_days` |
| 新作信心較低、更早重驗 | 年輕 repo 只要一個 release 就拿滿 cadence 分（`score.py:531-533`）；`first_seen_at` 沒人讀 | `standing = new`，卡片標出，分數的信心度打折，週期減半 |
| 失效不刪、改成不推 | 管線不寫 failed（`result.py:537-538`），重驗沒過紀錄不變（`reverify.py:418-423`） | 重驗沒過時寫 `standing = broken` 與失敗摘要，不動 `level`（不違反「sandbox 不自己判 failed」的原則，`schema.py:1439-1441`）。`filter.ts` 排除 broken，工具頁顯示「N 月 N 日重驗失敗」 |
| 補齊 804 筆的維護訊號 | 751 筆是 GitHub 資料沒補；完整的 `pickfit score` 會重抓 GitHub（`score.py:1682-1683,1296-1317`），但也會呼叫套件庫，而且 README 變過時會**花錢重評 docs rubric**（`score.py:1695-1719`），沒有關掉的開關 | 加 `--github-only`（不碰 rubric、不碰套件庫）；套件庫最後版本日期讀進 `registries.py`；網頁定期 HEAD 一次並讀 `Last-Modified` |

成本面：重驗是 15.9 說的線性成長風險。現在一次 verify 的花費在 run 上有記（`VerificationRun.cost_usd`），建議重驗排程用帳本的日上限擋住（plan.md 第 8 節說帳本不再是硬關卡，但重驗是自動花錢的排程，值得留一道），金額由念誠定。

### 3.3 寬收嚴推與防 AI slop（15.6）

- **推薦門檻**：`filter.ts:50-51` 只要求「某個 OS 有通過的安裝指南」，install 等級的 187 筆會被推；網頁只要打得開（`filter.ts:37-43`），install 等級的 29 筆網頁也會被推。15.6 要 function 加存活期。
- **馬上收緊會發生什麼**：「活過一個週期」今天沒有一筆做得到（全部 < 30 天）。所以存活期不能當硬條件，要先當標記：function 以上照推、標「新作，N 天前驗證」；install 等級改成只在沒有更好選擇時出現，並在 tradeoffs 寫明「pickfit 只確認裝得起來」。等第一輪重驗跑完再把存活期升為硬條件。這個門檻怎麼定需要念誠決定。
- **寶藏**：`TREASURE_MIN_FUNCTION_COVERAGE` 開起來（`schema.py:313`），13 款 install 等級的寶藏會掉下來。
- **排序**：`rules.ts:55-72` 依相關度、是否在使用者 OS 驗過、寶藏值排，驗證等級和年齡都不參與。模型路徑由 prompt 規則 3 管（`prompt.ts:14`），也沒提到等級或年齡。
- **主觀美醜**：已經符合 15.6。`pickfit/usability.py:9-11,35-38` 明說只看可量測的缺陷、「never taste」；`visual_check` 只能扣分（`score.py:100-106,1083-1106`）。不需要改。
- **存活訊號的原料**：GitHub 的 issue 回應（`IssueInputs`，`schema.py:1786-1794`）和 commit 時間已有欄位，751 筆補齊後就能用。真實使用回報目前 0 筆，短期內這一項不會有數字。

### 3.4 A 賽道：MCP 安全檢查（15.7）

現在有的：

- OSV 漏洞掃描（`pickfit/security.py:1-40`），MCP 專屬的只有「stdio server 沒 import HTTP transport 就算碰不到」（`security.py:698-710`）。
- 握手探針會掃工具描述，找 7 種提示注入樣式（`pickfit/verify/mcp_probe.py:60-76,109-123`：instruction_tag、override、conceal_from_user、side_channel、sensitive_files、other_tools、hidden_unicode）。描述本身不出沙盒，這點設計得很好。
- 斷網握手（`McpHandshake.offline`，`schema.py:1056`），147 筆斷網也能過。

缺的：

1. **注入樣式沒有結構化保存。** 探針的結果被 `pickfit/verify/mcp.py:190-218` 丟掉，只轉成自由文字的 `Pitfall(kind="note")`（`mcp.py:226-250`）。不能篩、不能計分、卡片也看不到。目前只有 2 筆（opencaselaw、openhire）留下這種 note。
2. **權限範圍沒記。** MCP 工具的 annotations（readOnlyHint、destructiveHint、openWorldHint）只被當文字掃，沒有存成欄位；碰了哪些檔案路徑、哪些環境變數也沒記。
3. **對外連線只記「斷網能不能過」，沒記連到哪裡。** CLI／MCP 的沙盒沒有逐主機的 egress 紀錄；只有網頁的 guard 有（`pickfit/verify/web_guard.py:419-428`）。
4. **卡片和 MCP 回答沒有這些資訊**，agent 在推薦時看不到「這個 server 會寫檔、會連外」。

建議順序：先把 1、2 做成欄位（純程式，免費，舊紀錄要等下次重驗才有值），再做 3（要改沙盒網路設定，Phase 2）。

### 3.5 B、C 賽道的驗證缺口

**B（人用的網頁）**

| 15.3 要驗的 | 現況 |
|---|---|
| 手機尺寸畫面正常 | 只有 `VIEWPORT = (1280, 900)`（`pickfit/verify/web_harness.py:47,492`），judge prompt 也寫死 1280x900（`pickfit/verify/web_verify.py:417`）。沒有手機尺寸、觸控或行動版 UA |
| 按得到 | 元素框有記（`web_harness.py:360`），沒量大小 |
| 核心功能走得完 | 有，逐項功能操作（`WebOperation`，`schema.py:1191-1208`），73 筆到 function |
| 載入速度 | 只有整次造訪的 `duration_s`（`web_verify.py:752`），沒有 TTFB、LCP |
| 追蹤器 | 只有 28 個廣告網域（`web_guard.py:88-95`，註解寫明「not a third-party tracker list」）和第三方網域數 |
| 資料最後更新時間 | 沒有 |

最小可行的補法：同一次造訪多開一個 390×844 的頁面截圖，量水平捲動與小於 44px 的點擊目標，這兩項不用模型。追蹤器清單要先查授權再用。

**C（人機協作）**

- GUI 操作的檔案檢查已經有「操作前雜湊、操作後比對 mtime 與 sha256，再查內容與格式」（`gui_operate.py:834,886,824`），這是 C 驗證的一半。
- 缺的另一半是**輸入來自軟體自己的 MCP／腳本**：現在 `GuiInput` 只放 pickfit 自己寫的文字或範例檔（`gui_operate.py:441-458`），而且範例格式沒有 docx、pptx、xlsx。
- 要做 15.10 第 5 點的「MCP 產出 → GUI 修改 → 檢查檔案」，需要：一個新的輸入來源（前一步 MCP tool call 的產出檔）、office 範例格式、以及一次 run 裡先跑 MCP 再開 GUI 的編排。這是 Phase 3 的 L 級工作，建議先挑 2–3 款開源、Linux 有套件的（例如 LibreOffice、Inkscape、Blender 加各自的 MCP，授權逐款查）。

## 四、產品設計與使用者需求

### 4.1 MCP：預設由 agent 查詢、動手做之前先查

現在的 MCP 是照「人要找軟體」寫的：`find_software` 的說明開頭是「Use when the user wants a tool for a job and has not settled on a product」（`server.ts:551`），`ABOUT` 說「pickfit matches software to the user's need」（`server.ts:16`）。15.1 的新句子是「agent 動手做之前先來查的地方」，觸發時機要多一種：**agent 自己準備寫一個工具或腳本的時候**。

建議改動：

1. **說明與 instructions 加觸發時機**：「Before writing a new tool, script or integration for the user, call find_software with the job」。`INSTRUCTIONS`（`server.ts:27-32`）和 `find_software` 的 description 各加一句。
2. **回答多一個重用方式。** 每個 pick 加 `reuse: use_directly｜extend｜reference`，附一句理由與擴充介面的位置；整體回答加 `build_it_yourself`（和 `no_install_option` 平行，`prompt.ts:20`、`find.ts:136`）。條件寫進 prompt：不存資料、不依賴外部、一次性的小工具，就說自己做，並附同類軟體的 `readme_wrong` 避坑和測試位置給 agent 參考。guard 要套和 `no_install_option` 一樣的檢查（不准網址、指令和「已驗證」字樣，product-ux-cost-audit Q3）。
3. **卡片多四個欄位**（`cards.ts:33-67`）：`used_by`、`track`、`interfaces`、`verified_days_ago`。目前卡片的 `verified_on` 是字串裡夾日期，模型要自己算天數。
4. **MCP 回答帶安全結構**：A 賽道的 pick 加 `mcp_risk`（注入樣式、會不會寫檔、會不會連外），讓 agent 在接上之前就能提醒使用者。`security_warning` 已有（`server.ts:234`），可以併在一起。
5. **新鮮度一律帶**：每個 pick 都回「N 天前驗證」，不只超過 90 天才說；`standing = new／stale` 時多一句。

這些都改 prompt 或回答 schema，上線前要跑一次付費 bench 確認命中率不退步（`worker/bench/`，product-ux-cost-audit C4 估過 Opus 46 題約 US$4–8）。程式可以先寫，bench 由念誠決定何時跑。

### 4.2 網頁版：殘留的黑客松假設

15.2 把網頁定位成「還沒用 agent 的人的入口，也是品牌被看見的地方」。對照現有文案：

| 位置 | 內容 | 和第 15 節的關係 |
|---|---|---|
| `worker/src/pages/info.ts:50` | 「For now they start with newer tools few people know yet, to show that such tools can be tested and trusted too」 | 和 15.4「新作品不等於好作品」相反。改成「先收現在驗得過、還有人維護的」 |
| `worker/src/page.ts:1153`、`:573`、`browse.ts:88,118-119`、`tool.ts:1086`、`info.ts:67` | 首頁數字、徽章、篩選與排序都以「寶藏（品質高、知名度低）」為主角 | 15.1 說冷門不是護城河，差異化是「這週驗過、有人維護」。建議首頁數字把「N 款寶藏」換成「N 款 30 天內重驗過」，寶藏留作次要標記。品牌用語要念誠決定 |
| `worker/src/pages/browse.ts:125` | 「pickfit has tried every tool here itself」 | 同一頁 `:118` 可以勾「含 345 款未驗證」，勾了之後這句不成立。改成依篩選狀態顯示 |
| `worker/src/page.ts:1133-1137` | 「Every tool, tested first」「It suggests tools it has already installed and tested」 | 方向對，但 install 等級也算「tested」。嚴推上線後再看要不要改成「做到它說的事」 |
| `worker/src/page.ts:1131-1160` | 首頁主軸是搜尋框，agent 入口在 `/agents` | 15.2 說預設由 agent 查。首頁可以在搜尋框下面加一行「在你的 agent 裡用」連到 `/agents`，不必改主軸 |
| `worker/src/pages/tool.ts:1101-1117` | 版面以影片為焦點，沒影片就由安裝區開頭 | 1,264 筆沒影片，B、C 賽道需要預覽圖（3.1） |
| `worker/src/ui/coverage.ts:19` | 「使用中的影片：還沒有」 | 停錄之後會出現在每一筆新的 GUI／網頁紀錄，要和 3.1 一起改 |
| `worker/src/pages/info.ts:51,128` | 提到 Muse Spark 和 Meta 黑客松 | 是歷史說明，寫法誠實，保留 |

頁面上也沒有任何「賽道」「人用還是 agent 用」「重用方式」「失效」的呈現。等 schema 有了欄位再加：工具頁的「一覽」側欄加「給誰用」與「上次驗證」，broken 的紀錄在頁首顯示失效日期。

## 五、可執行的 backlog

### 5.1 product-ux-cost-audit（11/20）的 P0 進度

照現在的程式看，下列已經做了：

- U1 快取 key 補上 private：`worker/src/web.ts:113`
- O1 Cloud Run 自動部署：`.github/workflows/worker.yml:112-126`
- O2 CI 跑 pytest：`worker.yml:71`
- F3 重驗 timer 與誠實的回應：`deploy/watch/pickfit-reverify.service`、`worker/src/outcome.ts:100-110`
- D1 新鮮度：`worker/src/freshness.ts`
- D3 每週安全掃描：`deploy/watch/pickfit-security-weekly.timer`
- X2 回應只送一份完整資料：`server.ts:532-536` 已改成摘要文字
- Q7 沒有合適的就直說：`server.ts:24`
- U9 依語言寫：`prompt.ts:36` 已有 `answer_language`

還沒做、和第 15 節有關、要一起排的：X3（回應精簡，新欄位加進來前先瘦身）、Q1–Q4（guard，`build_it_yourself` 要用同一套檢查）、Q6（模型路徑的 coverage 標示，和嚴推的 tradeoffs 有關）、U8（Verification Coverage 上頁面，要先改掉 video 維度）。

### 5.2 Phase 1：免費、不用人決定，可以立刻派給 Claude CLI

標 ✅ 的項目只改程式與測試，不呼叫付費 API、不開沙盒，可以直接派。

| 編號 | 任務 | brief | 影響檔案 | 量 | 人工／付費 | 驗收 | 派工 |
|---|---|---|---|---|---|---|---|
| P1-01 | 停止新錄影：`PICKFIT_RECORD` 預設 off，只有開錄才等 TAIL_S；`mac-host --record` 改成要明確開 | 15.7 | `pickfit/verify/record.py:84`、`gui_operate.py:2148-2152`、`mac_host.py:940-942` | S | 否 | `uv run pytest -q tests/test_web_video.py tests/test_coverage.py`；新測試：環境變數未設時 `record.wanted("replay-x")` 為 False | ✅ |
| P1-02 | coverage 的 video 維度換成 preview，沒影片回 not_applicable，舊影片照算；Worker 同步 | 15.7 | `pickfit/coverage.py:29,34,93,187,315,796-814,897,1189`、`worker/src/catalog.ts:457`、`worker/src/ui/coverage.ts:19` | S | 否 | `uv run pytest -q tests/test_coverage.py tests/test_index.py`；`cd worker && npm test`（`coverage-ui.test.ts`） | ✅ |
| P1-03 | 文件標示停錄：video.md 標已停止，proposals 索引同步 | 15.7 | `docs/proposals/video.md`、`docs/proposals/README.md:16` | S | 否 | `rg -n "superseded\|已停止" docs/proposals/video.md` | ✅ |
| P1-04 | schema 新欄位：`used_by`、`track`、`interfaces`、`reuse_fit`、`last_passed_at`、`reverify_cycle_days`、`reverify_due_at`、`standing`、`maintenance_signals`、`preview`（全部選填、預設 null），重產 JSON schema | 15.2–15.5 | `pickfit/schema.py`、`schema/software.v1.json` | M | 否 | `uv run pytest -q tests/test_schema.py`；用 `pickfit.schema.render_schema_files()`（`pickfit/schema.py:2894-2908`）重產 `schema/` 後和 git 裡的一致 | ✅ |
| P1-05 | 規則回填：依 2.2 的 kind／category 規則填 `track`、`used_by`；依 `verification.runs` 填 `last_passed_at`；依 kind 填週期（MCP、web、需要 api_keys 的 30 天，其餘 90 天）與到期日；`first_seen_at` 在 60 天內的填 `standing = new`。`evidence.method = rule` | 15.3、15.4 | 新增 `scripts/backfill_v15.py`、`data/software/*.json` | M | 否 | `uv run python scripts/backfill_v15.py --dry-run` 印出各賽道筆數（應接近 918／114／24／217）；`uv run pytest -q` | ✅ |
| P1-06 | 重驗通過就更新 `last_passed_at`；重驗沒過寫 `standing = broken` 與失敗摘要，不動 `level` | 15.4 | `pickfit/reverify.py:418-432`、`pickfit/verify/result.py:535-589` | S | 否 | `uv run pytest -q tests/test_reverify.py`（新增兩個案例：通過且步驟相同、沒通過） | ✅ |
| P1-07 | `pickfit score --github-only`：只重抓 GitHub，不碰 docs rubric、不碰套件庫 | 15.4 | `pickfit/score.py:1682-1719`、`pickfit/cli.py` | S | 否（執行會連 GitHub，免費） | `uv run pytest -q tests/test_score.py`；新測試確認這個模式下不呼叫 rubric 與 registries | ✅（實作）；跑 751 筆前確認 `GITHUB_TOKEN` 額度 |
| P1-08 | `last_release` 跟著 GitHub 重抓一起更新，讓 `releasedAfter` 能觸發 | 15.4 | `pickfit/score.py` 或 `pickfit/profiles.py:402-404` | S | 否 | `uv run pytest -q tests/test_profiles.py tests/test_score.py` | ✅ |
| P1-09 | 推薦路徑排除 `standing = broken`；卡片加 `verified_days_ago`、`standing`、`track`、`used_by`；每個 pick 都回「N 天前驗證」 | 15.4、15.6 | `worker/src/filter.ts:45-59`、`cards.ts:33-153`、`freshness.ts`、`find.ts:236-248`、`pickfit/index.py:425-454` | M | 否 | `cd worker && npm run typecheck && npm test`（`filter.test.ts`、`cards-prompt.test.ts`、`report-fresh.test.ts`）；`uv run pytest -q tests/test_index.py` | ✅ |
| P1-10 | MCP 注入樣式存成 `McpHandshake.description_flags`；tool annotations 存成 `read_only／destructive／open_world` 計數 | 15.7 | `pickfit/schema.py:1031-1064`、`pickfit/verify/mcp.py:190-250`、`mcp_probe.py:419-433` | M | 否（舊紀錄等下次重驗才有值） | `uv run pytest -q tests/test_mcp_probe.py tests/test_verify_mcp.py tests/test_schema.py` | ✅ |
| P1-11 | 網頁文案：`info.ts:50` 改掉「先收新的冷門工具」；`browse.ts:125` 依篩選狀態顯示 | 15.4 | `worker/src/pages/info.ts:50`、`browse.ts:118-125`、`data/i18n` | S | 否 | `cd worker && npm test`（`pages.test.ts`、`i18n.test.ts`） | ✅ |
| P1-12 | 優先清單加 `track` 欄，標出 B 只有 2 款、C 缺成對；Thunderbird、Espanso、uBlock 移到暫緩 | 15.3 | `docs/curation/priority-20261120.json`、`.md` | S | 清單內容要念誠看過 | `python3 -c` 讀 JSON，確認 106 筆都有 track | ✅（草稿） |

### 5.3 Phase 2：要人決定，或要付費／沙盒

| 編號 | 任務 | brief | 影響檔案 | 量 | 人工／付費 | 驗收 |
|---|---|---|---|---|---|---|
| P2-01 | 嚴推門檻：function 以上照推；install 等級只在沒有更好選擇時出現並寫明；開 `TREASURE_MIN_FUNCTION_COVERAGE` | 15.6 | `worker/src/filter.ts:50-51`、`rules.ts:55-72`、`prompt.ts:14,17`、`pickfit/schema.py:313` | M | **念誠決定門檻**；改 prompt 後要跑 bench（約 US$4–8） | `npm test`（`filter.test.ts`、`shortlist.test.ts`）；`uv run pickfit score --refresh` 後寶藏中 install 等級為 0 |
| P2-02 | 回答加 `reuse` 與 `build_it_yourself`，instructions 加「動手做之前先查」，guard 同步 | 15.1、15.5 | `worker/src/server.ts:16-32,546-586`、`prompt.ts`、`find.ts:136-138,323`、`guard.ts` | M | 程式免費；上線前 bench 付費 | `npm run typecheck && npm test`（`find.test.ts`、`mcpserver.test.ts`、`conformance.test.ts`）；bench 命中率不退步 |
| P2-03 | 被查到才重驗：`find_software` 回傳到期或 stale 的 pick 時寫 `reverify_queue`（`reason=due`），每天上限 | 15.4 | `worker/src/find.ts`、`outcome.ts:85-97`、`pickfit/reverify.py`、`deploy/watch/pickfit-reverify.*` | M | **每日重驗預算由念誠定**；重驗本身付費 | `npm test`（`outcome.test.ts`）；`uv run pytest -q tests/test_reverify.py` |
| P2-04 | 套件庫最後版本日期（PyPI、npm、crates、Homebrew、Flathub 的公開 API） | 15.4 | `pickfit/registries.py` | S–M | 免費，連網 | `uv run pytest -q tests/test_registries.py` |
| P2-05 | 網頁存活與內容更新時間：定期 HEAD 一次，讀 `Last-Modified`／sitemap `lastmod` | 15.4、15.3 B | `pickfit/web_intake.py`、新的 maintenance 子命令 | S–M | **要念誠同意**（brief 2.2 的「每站只跑一次」是針對驗證操作；HEAD 檢查要另外定頻率） | `uv run pytest -q tests/test_web_intake.py` |
| P2-06 | 預覽圖上線：截圖走海報那條路進 R2，index 匯出，`showcase()` 沒影片時顯示 | 15.7 | `pickfit/verify/video.py:2513,2550`、`pickfit/index.py:243-259`、`worker/src/video.ts`、`pages/tool.ts:529` | M | R2 上傳要念誠的 wrangler 帳號（記憶：要帶 `CLOUDFLARE_ACCOUNT_ID`） | `uv run pytest -q tests/test_index.py`；`npm test`（`video.test.ts`、`pages.test.ts`） |
| P2-07 | 手機尺寸檢查：同一次造訪加 390×844 截圖，量水平捲動與小點擊目標 | 15.3 B | `pickfit/verify/web_harness.py:47,492`、`web_verify.py:417`、`schema.py:1211` | M | 跑網頁驗證會花 Modal 與模型費用 | `uv run pytest -q tests/test_web_verify.py tests/test_web_box.py` |
| P2-08 | 重驗那 14 款優先清單裡 unverified 的（用 grants 與服務） | 15.3 A | `loop/queue.jsonl` | S | 付費沙盒 | 各筆 `verification.level` 不再是 unverified，或留下環境限制的原因代碼 |
| P2-09 | 首頁與徽章的品牌用語：寶藏退為次要，主數字改成「30 天內重驗過」；首頁加 agent 入口 | 15.1、15.2 | `worker/src/page.ts:1131-1160`、`browse.ts`、`tool.ts:1086` | S | **用語要念誠決定** | `npm test`（`pages.test.ts`、`head.test.ts`） |
| P2-10 | 評測改成「有接 vs 沒接」：第一次就裝好的比例、token 與時間、該說自己做或內建就夠時有沒有說 | 15.8 | 另開 session（建資料與配對的 session 不讀 `eval/`） | M | 付費；需要獨立 session | 由評測 session 定 |

### 5.4 Phase 3：較大、需要設計

| 編號 | 任務 | brief | 量 | 人工／付費 |
|---|---|---|---|---|
| P3-01 | C 賽道試做：2–3 款開源創作或文件工具，「MCP 產出 → GUI 修改存檔 → 檢查檔案」。新的 GUI 輸入來源（前一步 MCP 的產出檔）、office 範例格式、同一 run 先 MCP 後 GUI 的編排 | 15.3 C、15.10-5 | L | 付費沙盒；逐款查授權 |
| P3-02 | CLI／MCP 沙盒的逐主機 egress 紀錄（nftables log），進 `McpHandshake` 與卡片 | 15.7 | M–L | 沙盒改動與測試要付費 |
| P3-03 | 存活計分：活過 N 個週期才拿完整分數，新作的信心度打折；維護分數改掉「年輕 repo 加分」（`score.py:531-533`），formula 升版 | 15.4、15.6 | M | 公式要念誠核可 |
| P3-04 | `reuse_fit` 進一步判斷：測試完整度與模組化（clone 已經在 security 做過，可共用） | 15.5 | M | 若用模型判斷就付費 |
| P3-05 | B 賽道冷啟動：台灣在地網頁的投稿管道與「資料品質」評分 | 15.3 B | L | 需要人經營 |
| P3-06 | 資安公告觸發重掃（取代每週掃描） | 15.4 | M | 免費 |
| P3-07 | 5–10 位使用者訪談（「做到一半才發現有人做過」「自己做的工具被外部變動弄壞」） | 15.8 | — | 人做 |

### 5.5 建議的派工順序

1. 先派 P1-01、P1-02、P1-03（停錄），互不衝突，一個 session 就做得完。
2. P1-04 定了 schema 之後，P1-05、P1-06、P1-09、P1-10 才能並行，這幾項都依賴新欄位。
3. P1-07、P1-08 獨立，可以和 2 並行。跑 751 筆回填是唯一要連網的步驟（GitHub，免費）。
4. 念誠決定 P2-01 的門檻、P2-03 的預算、P2-09 的用語之後，再跑一次 bench。

## 附錄：統計腳本

只讀 `data/software/*.json`，Python 標準函式庫，免費。用法：`python3 -I 這段存成的檔案 data/software`。

<details><summary>展開</summary>

```python
import json, glob, sys, re, collections as C, datetime as D
NOW = D.datetime(2026, 11, 22, tzinfo=D.timezone.utc)


def P(s):
    return D.datetime.fromisoformat(s.replace('Z', '+00:00')) if s else None


recs = [json.load(open(f)) for f in sorted(glob.glob(sys.argv[1] + '/*.json'))]
print('TOTAL', len(recs))


def cnt(name, fn):
    print('\n## ' + name)
    for k, v in C.Counter(fn(r) for r in recs).most_common():
        print('  ', k, ':', v)


def gh(r):
    return ((r.get('scores') or {}).get('inputs') or {}).get('github')


def pushed(r):
    g = gh(r)
    return P(g.get('pushed_at')) if g else None


def age(d):
    if d is None:
        return 'none'
    days = (NOW - d).days
    for lim, l in [(30, 'a<30d'), (60, 'b30-60d'), (90, 'c60-90d'), (180, 'd90-180d'), (365, 'e180-365d')]:
        if days < lim:
            return l
    return 'f>365d'


runs = lambda r: r['verification']['runs']
web = lambda r: next((x['web'] for x in runs(r) if x.get('web')), None)

cnt('status', lambda r: r['status'])
cnt('kind', lambda r: r['kind'])
cnt('category', lambda r: r['category'])
cnt('audience', lambda r: r.get('audience'))
cnt('maturity', lambda r: r.get('maturity'))
cnt('level', lambda r: r['verification']['level'])
cnt('status x level', lambda r: (r['status'], r['verification']['level']))
cnt('unverified_reason', lambda r: r['verification'].get('unverified_reason'))
cnt('checked_at', lambda r: 'none' if not r['verification']['checked_at'] else (
    r['verification']['checked_at'][:10] if r['verification']['checked_at'] >= '2026-11-05'
    else r['verification']['checked_at'][:7]))
cnt('verification age', lambda r: age(P(r['verification']['checked_at'])))
cnt('pushed_at age', lambda r: age(pushed(r)))
cnt('no pushed_at: repo?', lambda r: ('repo' if r.get('repo') else 'no-repo') if pushed(r) is None else '-has')
cnt('last_release age', lambda r: age(P((r.get('last_release') or {}).get('published_at'))))
cnt('no pushed_at & no release', lambda r: pushed(r) is None and r.get('last_release') is None)
cnt('video x kind', lambda r: r['kind'] if any(x.get('video') for x in runs(r)) else '-none')
cnt('screenshot_paths', lambda r: any((x.get('evidence') or {}).get('screenshot_paths') for x in runs(r)))
cnt('evidence_url', lambda r: any((x.get('evidence') or {}).get('evidence_url') for x in runs(r)))
cnt('run os set', lambda r: ','.join(sorted({x['os'] for x in runs(r)})) or 'none')
cnt('security', lambda r: (r.get('security') or {}).get('status', 'null'))
cnt('treasure x level', lambda r: (((r.get('scores') or {}).get('treasure') or {}).get('is_treasure'),
                                   r['verification']['level']))
cnt('cap_reason', lambda r: ((r.get('scores') or {}).get('quality') or {}).get('cap_reason'))
cnt('mcp offline', lambda r: next((x['mcp'].get('offline') for x in runs(r) if x.get('mcp')), '-'))
cnt('web pwa/offline', lambda r: (web(r).get('pwa'), web(r).get('offline')) if web(r) else '-')
cnt('web data_sent', lambda r: web(r).get('data_sent') if web(r) else '-')
cnt('web browser', lambda r: web(r).get('browser') if web(r) else '-')
cnt('gui tier', lambda r: next((x['gui'].get('tier') for x in runs(r) if x.get('gui')), '-'))
cnt('usability', lambda r: r.get('usability') is not None)
cnt('readme_wrong', lambda r: any(p.get('kind') == 'readme_wrong' for x in runs(r) for p in x.get('pitfalls', [])))
cnt('first_seen month', lambda r: r['first_seen_at'][:7])
cnt('tests file', lambda r: bool(((gh(r) or {}).get('files') or {}).get('tests')) if gh(r) else 'no-gh')
ext = re.compile(r'\b(plugin|plugins|extension|extensions|hooks?|add-?ons?|scripting|lua|api)\b', re.I)
cnt('extensibility keyword', lambda r: bool(ext.search(' '.join(
    r.get('tags', []) + r.get('features', []) + [r['summary']]
    + [c.get('label', '') + ' ' + ' '.join(c.get('items', [])) for c in r.get('capabilities', [])]))))
cnt('desktop_app x category x level', lambda r: (r['category'], r['verification']['level'])
    if r['kind'] == 'desktop_app' else '-')
```

</details>

優先清單的「已收錄幾款」是另一段小腳本：讀 `docs/curation/priority-20261120.json` 的 `items`，用 GitHub `owner/name` 比對紀錄的 `repo.full_name`，沒有 repo 的用名稱比對（Blender MCP 名稱不同，另外確認是 `mcp-for-blender`）。
