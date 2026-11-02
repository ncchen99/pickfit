# Demo 情境候選（P5.6）

2026-11-02 · 給念誠挑 demo 主案與備案。只從現有、已經能用的紀錄挑；沒有改任何紀錄、配對程式或提示詞。

## 11/2 傍晚的新標準

念誠把 demo 工具的條件訂得更明確：

1. GUI app，做的是大家還在親手做、看著介面點才是重點的事（agent 的桌面介面、語音輸入、記帳、修圖、筆記）。AI agent 現在就能代勞的事（改檔案權限、改設定檔）排後面。
2. 介面好看、精緻。
3. 很多人都有的需求。
4. 能在 tart 的 macOS VM 裡驗證：沒有相機、沒有真的麥克風，主要功能不需要帳號或 API key。需要 API key 的 agent 介面、需要麥克風的語音輸入只會驗到 install，要標出來。

依這些條件，下面「第一版」的 4 個 CLI（`mcp-audit`、`tcount`、`pando`、`shine`）都會排後面：都不是 GUI，而且 agent 自己就能在終端機跑。

**另外，任何 GUI app 只要驗到 function 等級，現在就會碰到下方「線上 bug」（修正在 `claude/hotfix-gui-tier` 的 5eb1f2c，等念誠同意才部署），`find_software` 整個報錯。** List A 的前兩名、List B 裡的任何一個，驗到 function 之後都一樣。所以不管念誠選哪一個，這個 bug 都要先修好並部署。

### List A：目錄裡的 GUI app 重新排名

範圍：`data/software/` 裡 `status: listed`、有 macOS run 的 GUI app（約 40 個）。

| # | 工具 | 做什麼 | macOS 驗證 | 符合新標準的地方 | 問題 |
|---|---|---|---|---|---|
| 1 | `neon-vision-editor` | 原生 Mac 的 Markdown／筆記／程式碼編輯器 | function；有影片（40 秒） | 筆記；SwiftUI 原生介面，精緻；Apache-2.0；v2.1.5（10/26） | 線上 bug 會讓它報錯；兩句筆記需求裡，成功的 2 次都只回 install 等級的 `writer-computer`（另 1 次被 bug 擋住，不算沒排上）；驗過的只有「寫 Markdown 並存檔」 |
| 2 | `breaktimer-app` | 定時提醒休息 | function（4 項功能都驗過）；有影片（passed-only，49 秒，3 項功能） | 需求很大眾，非開發者也懂；agent 不能幫你起來休息 | 線上 bug；介面是普通的 Electron 設定頁，不算精緻；最新 release 是 2025-11-13，快一年 |
| 3 | `writer-computer` | 本機優先的 Markdown 筆記（資料夾裡的純文字） | 只到 install（VM 裡開不了資料夾選擇器） | 筆記；搜尋時排第 1 | 只到 install，功能沒驗到 |
| 4 | `opendisk` | 掃 Mac 硬碟看空間、刪大檔案 | 只到 install | 大家都遇過硬碟滿 | agent 用 `du` 也能做；只到 install |
| 5 | `sigil` | EPUB 電子書編輯器 | function（2 項） | 免費、GPL-3.0 | 需求太專門 |

語音輸入（`dictate`、`inlaut`、`opstrellis`、`quassel`、`quill`、`thundertalk`、`whisper-local`、`meeting-transcriber`、`charoite-audio`）：都需要麥克風，都只到 install。Agent 桌面介面（`hivemind`、`oxi`）需要 agent 的訂閱或 key；本機聊天（`camelid`、`hilbertraum`、`m1k3`、`llama-macos`）需要模型：也都只到 install。`itsypad-macos` 驗到 function，但是 freemium，而且全新 box 開不出視窗，錄不了影片。

**結論：目錄裡沒有完全符合的。** 最接近的是 `neon-vision-editor`（筆記、精緻、有影片），但它要等 bug 修好，而且成功回應的筆記需求裡它沒有出現；修好後要重測。

### List B：目錄外的免費開源 Mac GUI app

來源：Homebrew Cask，以及 GitHub 上 macOS 的筆記、記帳、修圖類專案。每個都比對過，**都不在**下列地方：

- `data/software/`：主 checkout 與所有 worktree 都比對過。
- 所有本機 pipeline 資料庫：包含評測快照，共 7,935 個 repo。
- 線上 D1 的 `submissions`：目前 2 筆，是 `alberto-codes/docvet` 和 `15r10nk/matchify`。

沒有送進 pickfit。star 數與 release 是 11/2 17:30 前後從 GitHub API 取得的。

| # | app | 工作 | repo | 授權 | star | 安裝 | 最新 release | 截圖 | 不用麥克風、相機、帳號就能驗主要功能？ |
|---|---|---|---|---|---|---|---|---|---|
| 1 | MiaoYan | 筆記（本機 Markdown，原生 Mac） | [tw93/MiaoYan](https://github.com/tw93/MiaoYan) | MIT | 8,721 | `brew install --cask miaoyan` | V4.6.0（2026-10-26） | [split-preview.png](https://raw.githubusercontent.com/tw93/MiaoYan/main/assets/split-preview.png) | 可以：寫一則筆記，檢查資料夾裡的 .md 檔 |
| 2 | Super Productivity | 待辦、計時、每日規劃 | [super-productivity/super-productivity](https://github.com/super-productivity/super-productivity) | MIT | 23,349 | `brew install --cask super-productivity` | v19.3.1（2026-10-25） | [banner.png](https://github.com/super-productivity/super-productivity/blob/master/docs/screens/banner.png) | 可以：README 說 offline-first，不用帳號；檢查加任務、計時 |
| 3 | Redlamp | 修圖（RAW／JPEG 調色，原生 Mac） | [pdcgomes/redlamp](https://github.com/pdcgomes/redlamp) | MPL-2.0 | 363 | `brew tap pdcgomes/redlamp https://github.com/pdcgomes/redlamp && brew install --cask pdcgomes/redlamp/redlamp` | v0.3.4-alpha（2026-10-27） | [film-editor.png](https://github.com/pdcgomes/redlamp/blob/main/docs/images/film-editor.png) | 可以，要放一張範例 JPEG／DNG。需要 macOS 26＋Apple Silicon（tart 映像是 26.6.2）；還是 alpha；VM 裡的 Metal 效能不確定 |
| 4 | Pinta | 修圖、畫圖（像 Paint.NET） | [PintaProject/Pinta](https://github.com/PintaProject/Pinta) | MIT | 4,121 | `brew install --cask pinta` | 3.1.2（2026-04-02） | [官網](https://www.pinta-project.com/)（README 沒有截圖） | 可以：畫圖或調整大小，存成 PNG。GTK 介面，在 Mac 上不像原生 app；最新 release 是 7 個月前 |
| 5 | Lap | 照片管理，內建裁切、拉直、旋轉 | [julyx10/lap](https://github.com/julyx10/lap) | GPL-3.0 | 4,164 | `brew tap julyx10/lap && brew install --cask lap` | v0.3.3（2026-10-12） | [lap_library.png](https://github.com/julyx10/lap/blob/main/docs/public/screenshots/lap_library.png) | 可以，要放幾張範例照片；檢查裁切後存出的檔案 |
| 6 | Money Manager Ex | 記帳 | [moneymanagerex/moneymanagerex](https://github.com/moneymanagerex/moneymanagerex) | GPL-2.0 | 2,278 | GitHub release 的 `mmex-1.9.4-Darwin.dmg`（**沒有 Homebrew cask**） | v1.9.4（2026-08-31） | [README 截圖](https://github.com/user-attachments/assets/f586f51b-a2d8-4219-a691-a483d4ca8db7) | 可以：建一個資料庫，記一筆支出。wxWidgets 介面看起來比較舊，不算精緻；只能從 dmg 裝 |
| 7 | MarkEdit | 筆記（像 TextEdit，專門寫 Markdown，原生 Mac） | [MarkEdit-app/MarkEdit](https://github.com/MarkEdit-app/MarkEdit) | MIT | 5,929 | `brew install --cask markedit` | v1.37.0（2026-10-18） | [01.png](https://github.com/MarkEdit-app/MarkEdit/blob/main/Screenshots/01.png) | 可以：寫一份 .md 並存檔 |
| 8 | ColaMD | 筆記（Markdown 編輯器） | [marswaveai/ColaMD](https://github.com/marswaveai/ColaMD) | MIT | 1,292 | `brew install --cask colamd` | v2.7.9（2026-10-25） | [rendering-en.png](https://github.com/marswaveai/ColaMD/blob/main/docs/images/rendering-en.png) | 可以：寫一份 .md 並存檔。Electron |
| 9 | LosslessCut | 剪影片（看著時間軸剪掉頭尾） | [mifi/lossless-cut](https://github.com/mifi/lossless-cut) | GPL-2.0 | 45,598 | `brew install --cask losslesscut` | v3.70.2（2026-10-28） | [截圖](https://static.mifi.no/media/InHeghy_4DwVeujK/2000.jpg) | 可以，用 ffmpeg 先做一段測試影片；檢查輸出檔的長度。很有名，不算冷門寶藏 |
| 10 | AnythingLLM Desktop | agent／聊天桌面介面 | [Mintplex-Labs/anything-llm](https://github.com/Mintplex-Labs/anything-llm) | MIT | 67,845 | `brew install --cask anythingllm`（dmg 來自廠商的 CDN，不是 GitHub） | v1.19.0（2026-10-26） | [AnythingLLM720p.gif](https://github.com/Mintplex-Labs/anything-llm/releases/download/v1.11.2/AnythingLLM720p.gif) | **不確定**：內建本機 LLM 引擎，不用 key，但要下載模型（GB 等級），VM 裡跑不跑得動沒把握；沒有模型就只到 install。很有名 |

建議依工作挑：筆記選 **MiaoYan**（最精緻、cask、原生）；修圖選 **Redlamp**（精緻，但是 alpha、要 macOS 26），穩一點選 Pinta；記帳選 **Money Manager Ex**（找到唯一有 Mac 版的開源記帳 app，但介面舊）；日常規劃選 **Super Productivity**。

查過但沒列入：

- `janhq/jan`：授權是 "Other"（Menlo Research 版權），不確定是不是開源。
- `CherryHQ/cherry-studio`：AGPL-3.0、53k star、有 cask，但要 API key 或 Ollama，只會到 install。
- `actualbudget/actual`、`streetwriters/notesnook`、`TriliumNext/Trilium`、`glushchenko/fsnotes`、`Beaver-Notes/Beaver-Notes`：已經在本機 pipeline 資料庫裡，不算從沒送過。
- `heyman/heynote`：GitHub 認不出授權。
- `upscayl/upscayl`：最新 release 是 2024-12。
- `wulkano/Kap`：最新 release 是 2022，而且錄螢幕要權限。
- 語音輸入類：都要麥克風。

### List C：念誠自己提的候選

念誠 11/2 晚上的口述（語音轉文字，照錄）：

> 关于这个挑软体的方向，我又想到几个实际的案例，我想用口述的方式，请你帮我记下来。我自己有安装的是这个 Parley P A R L E Y 的这个 detection 软体，然后还有磁碟清理的这个 MongoDisk，但是呢，它因为这可能几个月。变得比较有名，所以它的星星已经超过五千个了。然后另外一个是我这个 Mac 管理显示器的这个 Crisp C R I S P 这个软体，我我当时在装的时候只只有几几千个星星了。哦，我想到有一个朋友，他花钱买了这个，呃，Mac 的这个可以看电池状态和充电充电情形那个电流分配的这一个小小的工具，它会在 Mac 的这个，呃，就是上面状态列嘛，这个有很多小工具这边它会出现一颗的这种东西。这个是他花钱买的，所以我在想，如果再再再再找一个一个一个开源，然后然后有同样功能的，可能 demo 也是不错。

確認對應的 repo：協調 session 從念誠 Mac 上的 app 認出來，我再對 GitHub 與 Homebrew 核對過。

- Parley：`pathorsAI/parley`。官網 parley.tw 與 bundle id `com.pathors.parley` 對得上，最新 release v0.35.2（11/1）也和他裝的版本一樣。
- 「MongoDisk」是 MangoDisk：`harry0703/MangoDisk`，Homebrew cask `mangodisk` 指向它的 release。
- Crisp：`didriksg/Crisp`，cask `crisp` 指向它的 release，官網 crispmac.app。

VM 的限制：tart 的 macOS VM 沒有電池、沒有外接螢幕（所以沒有 DDC）、沒有真的麥克風。主要功能需要這些的 app 只會驗到 install。

「在 pickfit 裡」欄比對了 `data/software/`、所有本機 pipeline 資料庫（含評測快照）和線上 D1 的 `submissions`。「被發現過」的意思是：discovery 抓到過，但從沒抽取、從沒驗證，所以不在目錄裡，也從沒用 `submit_software` 送過。

| app | 工作 | repo | 授權 | star | 安裝 | 最新 release | 截圖 | 在 pickfit 裡？ | VM 能驗到什麼 | 介面 |
|---|---|---|---|---|---|---|---|---|---|---|
| **MangoDisk** | 磁碟清理、空間分析、重複檔、移除 app | [harry0703/MangoDisk](https://github.com/harry0703/MangoDisk) | GPL-3.0 | 5,170 | `brew install --cask mangodisk` | v1.2.2（2026-11-01；cask 還在 1.2.1） | [en-light.jpg](https://assets.mangodisk.app/images/readme/en-light.jpg) | 沒有 | **主要功能可以驗**：預設是唯讀掃描。在家目錄放一個大檔和幾個重複檔，檢查「大檔案」「重複檔」頁有沒有列出來；要驗清理，就確認那幾個檔被刪掉。系統位置可能要「完整磁碟取用權限」，VM 裡掃到的會比較少。「AI 解釋」不是主要功能，可能要 key | 好：暖色調、側欄清楚，清單有大小與勾選，很適合錄影 |
| **Crisp** | 外接螢幕：HiDPI 縮放、DDC 亮度音量、預設組、虛擬螢幕 | [didriksg/Crisp](https://github.com/didriksg/Crisp) | MIT | 2,289 | `brew install --cask crisp` | v1.7.1（2026-10-11） | [crispmac.app/screenshot.png](https://crispmac.app/screenshot.png)（README 沒有截圖） | 被發現過（11/1，來源 `homebrew_cask:crisp`） | **主要功能驗不到**：沒有外接螢幕，DDC、外接螢幕 HiDPI 都只會到 install。可能驗得到的是「建立虛擬螢幕」，再用 `system_profiler SPDisplaysDataType` 看有沒有多一個螢幕，以及存一個預設組。虛擬螢幕在 VZ 虛擬機裡能不能建，沒有把握 | 好：原生深色選單面板，像控制中心；macOS 26 上用 Liquid Glass |
| **Parley** | 業務、談判通話的即時 AI 教練（逐字稿、建議、會後報告），附 54 個工具的本機 MCP server | [pathorsAI/parley](https://github.com/pathorsAI/parley) | Apache-2.0 | 24 | 只有 GitHub release 的 dmg（**沒有 cask**） | v0.35.2（2026-11-01） | [desktop-live-en.jpg](https://raw.githubusercontent.com/pathorsAI/parley/main/website/assets/shots/desktop-live-en.jpg) | 被發現過（10/30，`local_ai` 查詢，規則通過） | **主要功能驗不到**：要麥克風加系統音訊，還要自己的 STT 與 LLM key（或登入用他們的服務），只會到 install。可能驗得到的是匯入一份 `.txt` 逐字稿、整理到資料夾，以及本機 MCP server 回應 `list_folders` 這類工具；這些都不是它的主要工作 | 好：乾淨的三欄介面，但偏工作工具，不是視覺亮點 |

**電池工具（取代朋友買的付費 app）**：口述裡說的「看電池和充電的電流分配」，很像 AlDente Pro 的 Power Flow 畫面，但沒有確認；要問那位朋友是哪個 app。`find_alternatives` 需要那個 app 的名字。

| app | repo | 授權 | star | 安裝 | 最新 release | 截圖 | 在 pickfit 裡？ | 做到朋友那個功能的程度 | VM 能驗到什麼 | 介面 |
|---|---|---|---|---|---|---|---|---|---|---|
| **Stats** | [exelban/stats](https://github.com/exelban/stats) | MIT | 43,047 | `brew install --cask stats` | v3.0.24（2026-11-01） | [popups.png](https://cdn.mac-stats.com/assets/images/popups.png) | 沒有 | 選單列的電池面板：電量、電源來源、充電中與否、電流、電壓、功率、健康度、循環次數，加上電源轉接器的功率、電流、電壓 | 電池模組驗不到（沒有電池）。CPU、記憶體、磁碟、網路模組驗得到，但那不是這個情境的工作 | 好：原生小面板、圖表整齊；資訊很密，Mac 使用者熟悉的樣子 |
| **Status Trio** | [lingyired/status-trio](https://github.com/lingyired/status-trio) | Apache-2.0 | 1,303 | `brew install --cask status-trio` | v1.8.0（2026-10-29） | [menu-bar-wifi.jpg](https://raw.githubusercontent.com/lingyired/status-trio/main/screenshots/menu-bar-wifi.jpg) | 被發現過 | 一個選單列圖示整合 Wi‑Fi、電池、音量；電池那列展開後有轉接器功率、電壓、電流、循環次數 | 電池驗不到；音量、輸出裝置切換也許可以 | 很好：原生，像控制中心 |
| **AirStats** | [byrencheema/airstats](https://github.com/byrencheema/airstats) | MIT | 488 | `brew install --cask airstats` | v1.6（2026-10-15） | （README 的截圖連結抓不到；見 [airstats.app](https://airstats.app)） | 被發現過 | 選單列系統監看：CPU、記憶體、GPU、網路、磁碟、電池、溫度 | 電池驗不到；其他模組驗得到 | 沒看到截圖，沒有評 |
| **batt** | [charlie0129/batt](https://github.com/charlie0129/batt) | GPL-2.0 | 1,787 | `brew install batt`（formula） | v0.8.0（2026-07-21） | — | 沒有 | 只做充電上限（Apple Silicon），不是看電流的工具 | 驗不到（要真的電池與 SMC，還要 root 的 daemon） | — |

沒列入：

- `AppHouseKitchen/AlDente-…`：README 說 AlDente 已經不是開源，repo 只剩舊版程式碼。
- `rurza/BatFi`：開源的程式碼只到 2.3（2025），cask 裝的是封閉的 4.x。

**List C 的評估**：

1. **MangoDisk 最適合**。「硬碟滿了」大家都遇過，清理時要看著清單勾選，是親手做的事；介面好看；主要功能在 VM 裡驗得到；有官方 cask；11/1 還有 release。要注意：
   - 目錄裡已經有一個同類的 `opendisk`（只驗到 install），驗過的 MangoDisk 應該會排在它前面，但要實測才知道。
   - 它一驗到 function，就會碰到上面那個 GUI 的 schema bug。
2. **Crisp**：介面好看，需求也真實（外接螢幕糊、亮度調不了），但主要功能在 VM 裡驗不到。如果虛擬螢幕建得起來，頂多驗到那一項，demo 時「驗過」講的就不是使用者真正要的功能。
3. **Parley**：主要功能要麥克風和 key，只會到 install，不適合當「驗過」的 demo。
4. **電池工具**：Stats 最接近朋友那個 app，但 VM 沒有電池，電池功能只會到 install。目錄裡也沒有任何電池工具，所以今天用 `find_alternatives` 問「取代某某付費 app」，不會回 Stats，除非先送進去並驗證；而驗證只會到 install。拿來講「取代付費 app」的故事可以，但畫面上的 pickfit 結果會是「只驗到 install」。

## 第一版（11/2 下午，CLI 為主）

### 先講結論

- **建議主案：`mcp-audit`**（「我裝了一堆 MCP server，有沒有哪個有風險？」）。6 次呼叫都排第 1，回 3 個選項可以比較；服務等級；看的人多半自己就在用 MCP。
- **備案：`tcount`**（token 計數，4 項功能都驗過）、**`pando`**（給平行 coding agent 用的 git worktree）。
- **有影片的兩個 GUI app（`neon-vision-editor`、`breaktimer-app`）現在不能用來 demo**：線上 Worker 的 `find_software` 只要結果裡有功能等級的 GUI app 就會整個報錯（見下方「線上 bug」）。這個 bug 修好並部署之後，它們才能重新列入考慮。

### 篩選

從 `data/software/` 的 863 份紀錄篩出：`status: listed`；有 macOS arm64、等級 function 以上的 run（59 份）；再依下列條件刪減：

- 免費：`pricing` 是 `free`，或沒寫價格但有 OSI 授權。刪掉 `itsypad-macos`（freemium）、`stackengine`（freemium、沒有授權）、`cli`（沒有授權）。
- 安裝後能離線：功能檢查是在斷網時通過。刪掉 `halpradio`（網路電台，`network: required`）、`patient-zero`（每次都用 `npx -y …@latest`，smoke test 都不是離線）。
- 安全的安裝方式：brew／cask、pipx／uv、npm。刪掉 `script`、`binary`、`source`、`go`、`pip`、`other`（例如 `xyntetik-runner`、`shep`、`cluaiz`、`mi-lsp`）。
- 專案健康：授權清楚、最近有 release。
- 需求要大家都懂：刪掉很專門的（Allure TestOps、Darkube、Ark genomic enclaves、Tiingo、EPUB 編輯器 `sigil`），以及需要另外裝 Ollama 或模型、或要雲端 API key 的 coding agent。

剩下 8 個，每個寫 2 句使用者會打的需求，送進線上 Worker 試。

### 線上檢查

方法：直接用 HTTP 呼叫 `https://pickfit-mcp.ncchen99.workers.dev/mcp` 的 `tools/call find_software`。參數只有 `need`，加上 `os: macos`、`arch: arm64`（使用者在 Mac 上的 agent 會帶）；需求寫到「免費」的那一句加 `budget: free_only`。每句先跑 1 次篩選，排第 1 的再補 2 次。每次都是 `matched_by: muse-spark-1.3`、`degraded: false`、沒有追問。2026-11-02 約 17:15–17:28（台北），共 33 次呼叫。

「排名」＝目標工具在 picks 裡的位置；「—」＝沒出現；「被 bug 擋住」＝工具因下節的 bug 回傳錯誤，**不算沒排上**，只是看不到排名。成功回應的「—」是真的沒排上：picks 裡只要有功能等級的 GUI app 就會報錯，所以能成功回應，就表示 picks 裡沒有它。

| 工具 | 需求（使用者會打的話） | 3 次的排名 | 同時回傳的其他選項 |
|---|---|---|---|
| `mcp-audit` | I've added a bunch of MCP servers to Claude and Cursor. Is there a way to check whether any of them are risky? | 1, 1, 1 | `patient-zero`、`penthera` |
| `mcp-audit` | scan my MCP config for security problems before I commit it | 1, 1, 1 | `patient-zero`、`penthera` |
| `tcount` | check how many tokens a prompt file is and whether it fits in the model's context window | 1, 1, 1 | 無（只回 1 個） |
| `tcount` | count the tokens in every file in my repo before I paste it into an LLM | 1, 1, 1 | 無 |
| `pando` | I run several coding agents on different branches at once. Something to manage git worktrees with a dev server for each | 1, 1, 1 | `orbit`、`vincent` |
| `pando` | keep a separate checkout per branch and run each one's app on its own port | 1, 1, 1 | 無 |
| `shine` | preview my README nicely right in the terminal and catch markdown mistakes before I publish | 1, 1, 1 | 無 |
| `shine` | read markdown docs in the terminal without opening a browser | 1, 1, 1 | 無 |
| `neon-vision-editor` | I want a free app for writing Markdown notes with a live preview | —（1 次） | 只回 `writer-computer`（install 等級） |
| `neon-vision-editor` | a lightweight native text editor for my Mac to open and tweak scripts and config files（`free_only`） | 被 bug 擋住、—（2 次） | 成功的那次只回 `writer-computer` |
| `breaktimer-app` | I sit at my laptop for hours. I want something that nags me to stand up and take a break every so often | 被 bug 擋住 ×2 | — |
| `breaktimer-app` | an app that reminds me to rest my eyes every 20 minutes, but only during my work hours | 被 bug 擋住 ×2 | — |
| `jitllm` | run a small language model locally on my MacBook, offline | —（1 次） | `llama-macos`、`camelid`、`bitrun` |
| `jitllm` | chat with an LLM on my own laptop without sending anything to the cloud | —（1 次） | `camelid`、`m1k3`、`hilbertraum` |

`neon-vision-editor`、`jitllm` 篩選時就沒排上，沒有補跑。

### 線上 bug：功能等級的 GUI app 讓 `find_software` 報錯

Worker 回的是 `isError: true`，內容是：

> Output validation error: Invalid structured content for tool find_software: picks.0.verification.gui.tier: Invalid option: expected one of "window"|"ui_rendered"

原因：`worker/src/server.ts:93` 的輸出 schema 寫 `.enum(['window', 'ui_rendered'])`，但 `worker/src/catalog.ts:37` 與資料裡已經有 `action_checked`（GUI 功能驗證過，也就是所有功能等級的 GUI app）。`main`、`origin/main`、本機所有分支都還是這樣。影響不只 demo：任何使用者的需求只要配到功能等級的 GUI app（`breaktimer-app`、`neon-vision-editor`、`sigil` 等），整個回答都會失敗，而且 Muse 的配對已經跑完、花了錢。我沒有改（這個 session 不改程式），交給協調的 session 決定。修好之後算是修 bug，不是為了 demo 調整，GUI app 才能重新當候選（`breaktimer-app` 的兩句要重跑才知道排名）。

註：一開始有 3 次被擋住的呼叫，因為我的腳本解析失敗，沒存下原始回應（`neon` 第 2 句 1 次、`breaktimer` 兩句各 1 次）；之後每次都存下了，內容都是上面那段。

### 候選情境

| # | 需求（建議用的那句） | 3 次排名 | 為什麼大家都懂 | 影片 | 風險 |
|---|---|---|---|---|---|
| 1（主案） | I've added a bunch of MCP servers to Claude and Cursor. Is there a way to check whether any of them are risky? | 1, 1, 1（另一句也是 1, 1, 1） | 會看這支影片的人（評審、MCP 使用者）多半自己就裝了好幾個 MCP server；「裝的東西安不安全」大家都會擔心。而且很自然帶出 pickfit 自己就是 MCP server。 | 沒有；CLI 的 run 沒有影片錄製器（只錄 GUI 操作）。念誠在 Mac 上跑一次 `mcp-audit scan` 錄螢幕即可。 | 安裝要 `uv`（`uv tool install mcp-audit-scanner`），Mac 上沒裝 uv 要先裝。在念誠的 Mac 上掃會印出真的 MCP 設定路徑，可能有 token 或 key，錄影前要檢查、必要時打馬賽克。macOS 驗到「掃描」與「攻擊圖 dashboard」；「鎖定核准的 server」、「跨 server 的危險組合」沒驗到，旁白不要講。第 2 名 `patient-zero` 每次都用 `npx …@latest`，不是離線。 |
| 2 | check how many tokens a prompt file is and whether it fits in the model's context window | 1, 1, 1（另一句也是 1, 1, 1） | 有在用 LLM 的人都遇過「這段塞不塞得進 context」。 | 沒有（CLI）；終端機輸出畫面很清楚，好錄。 | 只回 1 個選項，沒有比較的畫面。Claude、Gemini 的數字是估算（工具自己標 Approx），旁白不要說「精確」。最新 release v0.7.0 是 9/12，約 7 週前。brew 要從作者的 tap 裝（`lancekrogers/tap/tcount`）。 |
| 3 | I run several coding agents on different branches at once. Something to manage git worktrees with a dev server for each | 1, 1, 1（另一句也是 1, 1, 1） | 平行跑 coding agent 是現在很多開發者在做的事，和 demo 的觀眾很貼近。回 3 個選項（`orbit`、`vincent`）。 | 沒有（TUI）。 | **需求說的「每個 worktree 一個 dev server」在 macOS 沒驗過**（agent 的 box 通過，全新 box 重播沒過）；驗過的只有建立、刪除 worktree。要用這個就換成另一句（keep a separate checkout per branch …），旁白只講 worktree。AGPL-3.0。public URL、服務副本要 cloudflared、Docker。 |
| 4 | preview my README nicely right in the terminal and catch markdown mistakes before I publish | 1, 1, 1（另一句也是 1, 1, 1） | 寫 README、發布前檢查 markdown，大部分開發者都做過。treasure 分數 65.9，這幾個裡最高。 | 沒有（TUI）。 | 最新 release v0.1.2 是 7/10，4 個月前，「最近有 release」偏弱；版本號 0.1.x。只回 1 個選項。npm 要裝指定版本 `@nk02/shine@0.1.2`。行內圖片沒驗到。 |
| （修好 bug 才能用） | I sit at my laptop for hours. I want something that nags me to stand up and take a break every so often | 被 bug 擋住 ×4（沒有排名） | 最大眾的需求，非開發者也懂；而且有 Muse Spark Open 剪的驗證影片（passed-only 版，49 秒，3 項功能）。 | 有（passed-only） | 現在線上會報錯，要先修 Worker 的 schema 並部署。最新 release v2.0.3 是 2025-11-13，快一年。「只在上班時間提醒」那項沒驗過，影片也拿掉了，所以不要用第 2 句。修好之後排名要重測。 |

`neon-vision-editor`（有影片）在兩句 markdown／文字編輯器需求裡成功回應的 2 次都沒排上，只回 install 等級的 `writer-computer`；另 1 次被 bug 擋住。bug 修好前不建議當 demo，修好後要重測。

### 供給端那一幕：要提交的 3 個 repo

條件：第三方（不是念誠的作品）、在 pickfit 的類別裡、從來沒送進 pickfit。查了三個地方，三個 repo 都不在：

- `data/software/`：主 checkout 與所有 worktree 的紀錄，`repo.full_name` 都比對過。
- 本機 pipeline 資料庫：主 checkout 與所有 worktree 的 `runs/*.db`，加上 `~/.pickfit/eval-snapshot-20261102/` 裡的快照，`candidates.full_name` 與 `aliases` 合起來 7,935 個 repo，都比對過。
- 線上 D1 的 `submissions`（`wrangler d1 execute pickfit --remote`，只讀查詢）：目前只有 2 筆，沒有這三個。

| repo | 類別 | 是什麼 | Mac 安裝 | 授權、活躍度 | 為什麼適合錄影 |
|---|---|---|---|---|---|
| [heydeer/pngdeer](https://github.com/heydeer/pngdeer) | dev_cli | 壓縮 PNG（輸出 PNG 或 WebP），自動挑品質；CLI 與瀏覽器（WebAssembly）同一份 Rust 程式 | `brew install heydeer/tap/pngdeer` | MIT；10/25 建立，11/2 還有 push；422 star；**還沒有 GitHub release** | 「壓圖」大家都懂（TinyPNG 的離線替代），結果是看得到的檔案大小變化。 |
| [scarletkc/seiso](https://github.com/scarletkc/seiso) | dev_cli | 給 AI 寫、人和 agent 讀的專案文件用的 Markdown 規範與 linter | `uv tool install seiso`、`pipx install seiso`、`npm install -g @scarletkc/seiso`（有 darwin-arm64 預編譯檔） | MIT；v0.4.0（10/13）；195 star | 三種安全安裝方式都有，驗證成功的機率高；和 demo 的「coding agent」主題接得上。 |
| [Graphicle-AI/graphicle](https://github.com/Graphicle-AI/graphicle) | mcp_server | 給 coding agent 的程式碼圖與記憶，一個 Rust 程式（Claude Code、Codex、Cursor） | `brew install graphicle-ai/tap/graphicle`；release 有 `aarch64-apple-darwin` 檔與 `.mcpb` | Apache-2.0；v0.1.11（11/2）；492 star | 示範 MCP 類別；release 很新。 |

備用：[init-co-jp/diff-tour](https://github.com/init-co-jp/diff-tour)（dev_cli，像資深工程師那樣帶你走過一個 diff 的 TUI；MIT；v0.6.1 10/29 有 darwin_arm64 檔；但官方安裝是 `go install`，README 說 macOS 還沒測過）。

風險：三個都還沒經過 pickfit 驗證，錄影那天實際送出才知道結果（這正是那一幕要呈現的）。`pngdeer` 沒有 release，如果 pickfit 的抽取或計分看重 release，結果可能比較弱；最穩的是 `seiso`。三個都是 10 月才建立的新專案，錄影前要再確認還沒被別人送進來（查 D1 `submissions` 就好），而且 P5 的完成標準測試**不能用掉要錄影的那一個**。
