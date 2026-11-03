# Demo 影片：腳本與分鏡（v1）

2026-11-03 晚上。來源：念誠 11/3 的建議（一條主線、一款主角 App 不剪接，中段 30 秒 agent 快節奏）、[docs/submission/story.md](../docs/submission/story.md)（第 4、5、7 節的製作筆記、敘事線與主張檢查）、[docs/brief.md](../docs/brief.md) 第 5.1 節。Gemini 4 的 [VIDEO.draft.md](../docs/submission/VIDEO.draft.md) 不採用，這份沒有參考它。

## 0. 固定要求

- **第一句是賽前揭露**（[hackathon-rules.md](../docs/hackathon-rules.md) 第 7 節）。
- **≤ 3:00**，目標 2:56。英文版。旁白用念誠自己的聲音（ElevenLabs voice `2kaIk6v4SfGnZzWDde1Y`），配樂與音效也用 ElevenLabs。
- 只展示比賽期間做的東西；現在做不到的不說成現在式，「之後」的部分畫面上標 **Next**。
- 不照評分項目分段。Impact、Meta 模型、技術深度、Demo 在故事裡自然出現（每段最後一欄標出）。

## 1. 視覺方向

**品牌以現在的官網為準**（11/3 改版後；DESIGN.md 可能落後，顏色直接取 `worker/src/ui/styles.ts`，已和 pickfit.app 線上的 CSS 對過）。改版拿掉了舊的墨綠裁切墊、格線與量尺，story.md 第 5 節寫的「墊板綠漫上來」是舊識別，這版改掉。

| 元素 | 影片裡的樣子 | 顏色（styles.ts） |
|---|---|---|
| 地面 | 一個安靜的紙色平面，真實的柔光與陰影，不放格線 | `--paper #F7F7F4`、`--rule #DEDFD9` |
| 你的請求 | 白色的實體紙卡，2px 墨棕外框、右上斜切，底線是 Fitz 的捲尺 | `--raised #FFF`、`--fitz-line #4A2E22`、`--tape #F5C243` |
| Fitz 的回答 | 橄欖色的實體紙卡，右上斜切 | `--voice #F1F6E2`、`--voice-edge #A9B77E` |
| 縫線 | 3D 的赭紅棉線，跑線針法；只出現在驗證過的東西上 | `--stitch #C4552D` |
| 量身單 | 標籤、點線、數值 | `--ink`、`--ink-3`、`--leader` |
| 大頭針 | Compare 的符號 | 墨色 |
| 字 | Bricolage Grotesque 700（標題）、系統字（內文）、等寬（指令） | `--ink #1A1D17` |
| 一屏一個黃 | 每個畫面最多一個實心黃 | `--tape` |

**立體，但不花**（念誠：不要太扁平；motion 要看得出用心）：

- 用 Three.js 做真的 3D 場景：柔和的環境光、軟陰影、環境遮蔽、淺景深。物件是摸得到的材質：紙卡有厚度和斜切角、捲尺是有刻度的緞面帶子、縫線是棉線、Fitz 是黏土質感。
- **Fitz 做成 3D 黏土模型**：照 [brand/mascot/README.md](../brand/mascot/README.md) 的比例與配色（蛋形身體、小簇羽、從身後翹起的尾巴、菱形小喙、頸上的捲尺），外圈保留墨棕描邊，看得出就是網站上那隻。配色不改。轉頭姿勢才用喙咬東西。
- **顏色等於 pickfit**：開場那一晚是單色的（紙白黏土＋墨色，夜晚的冷光、螢幕的光）；Fitz 一出現，黃色捲尺、赭紅縫線、橄欖色才第一次進場。
- **真實錄影是 3D 世界裡的一塊螢幕**：網頁、Claude app、MangoDisk 的錄影貼在場景裡浮著的面板上，鏡頭飛進去變全螢幕，再拉出來接下一段。真實畫面不加假 UI。
- 動畫原則（Emil Kowalski 的 animate 筆記，story.md 4.2）：每個動作說得出目的；進場從 scale 0.94＋透明度；UI 不用 ease-in；沿用網站的曲線 `--ease-out cubic-bezier(.16,1,.3,1)`、`--ease-io cubic-bezier(.65,0,.35,1)`；驚喜留給三個時刻：倒轉這一晚、順著縫線飛回去、票牆。
- 畫面上同時最多三層；新的一層進來，舊的往後退、變暗。所有網站、評論、App 圖示都是虛構的通用樣式，不放真實品牌。

## 2. 哪些是真的錄影、哪些是動畫

| 段落 | 來源 | 怎麼錄 |
|---|---|---|
| pickfit.app 搜尋、結果、工具頁、章節影片 | **真實錄影**（網頁） | Playwright 以 1920×1080、2 倍像素開線上網站，CDP screencast 擷取，英文、淺色 |
| Claude app 安裝 MangoDisk、patient-zero、gutenberg-mcp-server | **真實錄影**（螢幕） | `screencapture -v`（已測：3200×1800、60 fps）。我用 Computer Use 操作念誠 Mac 上的 Claude app；剪輯時只裁對話欄，等待的部分加速並標出倍速，同意提示一律 1× |
| MangoDisk 第一次使用 | **真實錄影**（螢幕） | 同上，只裁 App 視窗；掃描結果裡的私人檔名做模糊 |
| 開場那一晚、Fitz 倒轉、順著縫線往回走、票牆、維護者、片尾 | **3D 動畫** | Three.js＋GSAP 寫成網頁，逐格渲染（Playwright 每格 seek 再截圖），ffmpeg 合成 |

**為什麼 Claude app 用真實錄影、不做擬真動畫**：Demo 佔 25%，評審看的是「能不能動」；擬真動畫再像也會被當成 mockup。story.md 的主張檢查也要求同意提示用 client 真正跳出來的那個。用錄影，但在剪輯裡把它放進 3D 面板、裁掉側欄、在關鍵處推近，就拿到動畫「乾淨、沒有雜訊」的好處，又保住真實。

## 3. 分鏡

時間是目標值，旁白錄好後依實際長度微調。總長上限 3:00。

### 0:00–0:05 賽前揭露（靜）

| 畫面 | 旁白 | 聲音 |
|---|---|---|
| 紙色地面，鏡頭很慢地推。一張白紙卡上兩行墨字：「Before this week: idea and planning notes.」「Built this week: everything you'll see.」 | **Before this hackathon, we had idea and planning notes. Everything you'll see was built this week.** | 只有房間的底噪 |

### 0:05–0:22 同一個人的同一晚：硬碟滿了（快，跳剪）

單色的 3D 書桌小場景（夜晚）：一台筆電、一盞檯燈、一個馬克杯、一個時鐘。一個沒有臉的黏土小人坐在桌前（膠囊身體、圓頭，紙白色）。時鐘一直走。

| 秒 | 畫面 | 旁白 | 音效 |
|---|---|---|---|
| 0:05 | 時鐘 7:02 PM。筆電跳出通用的「磁碟快滿了」提示（虛構樣式），紅色的容量條是畫面裡唯一的顏色 | **Seven p.m. Your disk is full. You need one small app.** | 提示音 |
| 0:09 | 紙籤一樣的分頁從筆電上緣一張張彈出，越擠越細：「Best free disk cleaner 2026」「Top 10…」 | **Ten tabs. Every review disagrees.** | 每張一聲輕點擊 |
| 0:12 | 兩個評論泡泡從左右疊上來：「A is the one.」「No. Get B.」；接著兩張卡：「Free trial · $39.99/yr」、「Allow Full Disk Access?」 | **One wants a subscription. One wants full disk access. Is it even safe?** | 紙張翻動 |
| 0:16 | 四個虛構的 App 圖示掉進 3D 的 Dock，三個依序飛進垃圾桶 | **Install four. Delete three.** | 落下、丟棄 |
| 0:18 | 筆電上程式碼快速生成，版本號 v1 → v9 跳，便條紙「fix scan」「fix crash」疊上來 | **Or have AI build one, and maintain it forever.** | 打字聲加速 |
| 0:21 | 時鐘 11:48 PM，全部定格，小人趴在桌上 | **Eleven forty-eight. Still full.** | 音樂抽掉，只剩一聲滴答 |

自然帶出：Impact（人人遇過的痛；自己重做的代價）。

### 0:22–0:30 Fitz 把這一晚捲回來（招牌轉場）

| 畫面 | 旁白 | 聲音 |
|---|---|---|
| 半拍靜音。3D 黏土 Fitz 從畫面上方飛進來，落在筆電上（**第一次出現顏色**：橄欖身體、赭紅帽、黃色捲尺）。轉頭，用喙咬住捲尺的尾端往回拉：時鐘從 11:48 倒轉回 7:02，分頁飛回去一張張關掉，垃圾桶裡的圖示飛回、消失，程式碼倒退。鏡頭穿進筆電的螢幕，螢幕變成 pickfit 的請求卡（白卡、墨棕外框、斜切角），捲尺在卡底展開成黃色的底線；pickfit 的字標落下，赭紅的點用一針縫上 | **Chances are, someone already built it. pickfit finds it, and tells you what it actually tested.** | 捲尺回捲的「咻—」、時鐘倒轉、最後一聲穿針。**配樂從這一針進來** |

自然帶出：Impact（一句話講完核心價值），Demo（品牌、吉祥物、聲音一起出場）。

### 0:30–1:24 主線：MangoDisk，從需求到第一次使用（慢，不剪接）

鏡頭從請求卡拉出來，卡片變成一塊浮在紙面上的螢幕，裡面是真實錄影。角落有一個真實時間的小時鐘（錄影當下的時間，不是故事時間）。

| 秒 | 畫面（真實錄影） | 旁白 | 自然帶出 |
|---|---|---|---|
| 0:30 | pickfit.app（英文、淺色）。在請求欄打：「My Mac's disk is full. I want a free cleaner I can trust.」勾 macOS、Free。捲尺在字下展開。按 Find tools | **Seven p.m., again. This time, just say what you need.** | |
| 0:36 | 結果到：Fitz 的回答（橄欖卡）＝MangoDisk，量身單：Tested on macOS、how far it got、free；下面是安全提醒（紅盾牌：9 known advisories，OSV.dev）；Also fits 幾列 | **pickfit matches it against software it has installed and tested itself. Ranked by fit, not stars. No ads.** | Meta：即時配對（畫面小標「matching: Muse Spark 1.3」）；Impact：中立 |
| 0:44 | 點進 MangoDisk 的工具頁。影片「Recorded by pickfit」在第一屏；點章節「Find and clear largest files」，直接跳過去播放 | **Want to see it first? This is pickfit using MangoDisk on a fresh macOS VM. One chapter per feature it checked. The hands are Muse Spark Open, Meta's open-weight model.** | Meta：開放權重模型操作桌面 GUI；Impact：不用再去找 YouTube |
| 0:58 | 切到 Claude app（鏡頭從網頁面板滑到旁邊另一塊面板）。使用者打：「Install MangoDisk for me, the one pickfit tested.」工具呼叫 pickfit · get_install_guide 展開；agent 先說 pickfit 的安全檢查標出已知漏洞、問要不要照樣安裝（實錄：念誠選 Install anyway） | **Hand it to your agent. It gets the exact steps that worked in the sandbox. It warns you about known vulnerabilities first.** | 技術：只回重播過的步驟；安全檢查 |
| 1:07 | Claude 真正的權限提示跳出來（`brew tap … && brew install --cask --appdir=$HOME/Applications …`），使用者按 Allow（1×）；下載與安裝加速（標「8×」）；完成後 `open ~/Applications/MangoDisk.app` | **And it asks before it runs anything.** | 母題：先問你，再執行 |
| 1:13 | 切到 MangoDisk（真實錄影）：開始掃描（加速、標倍速）→ Large files 列出事先放好的大檔 → 勾選 → 清除，可用空間跳回 | **Scan. Find the big ones. Clear them. Your evening is back.** | Demo：從需求到能用，中間不剪 |

（旁白之間留真實操作的空檔，不塞滿。）

### 1:24–1:52 不只你在找軟體，你的 agent 也在找（快，加速並標倍速）

| 秒 | 畫面（真實錄影） | 旁白 |
|---|---|---|
| 1:24 | 標題卡，3D 小動畫：一隻 agent 游標的手，四周是它「沒有的工具」的空插槽 | **You're not the only one looking for software. So is your agent.** |
| 1:28 | CLI：使用者說「Scan my Mac for npm and PyPI supply-chain malware. Use pickfit to find a scanner and run it for me.」（第一、二次用 latest 的問法，agent 先去查新聞、自己掃，改成這句才照 pickfit 的工具跑） → pickfit · find_software → patient-zero（free、MIT、tested on macOS）→ 權限提示（1×）→ agent 先下載套件讀過才跑 → 結果「0 findings」，並照實說 IoC 清單沒有套件層的指標 | **Ask it something it has no tool for. pickfit finds a scanner that was tested on a Mac. Your agent asks first, then runs it.** |
| 1:40 | MCP：「Give yourself a tool for searching and reading Project Gutenberg books, then read me the opening of a book about the sea.」→ pickfit → gutenberg-mcp-server → 同意安裝 → 新 session 才載入工具（Claude Code 的限制）→ 讀出 Moby Dick 開頭 | **Or it gives itself a new skill: a Project Gutenberg server, installed with your okay, then put to work.** |

三拍的同意提示都是 client 真正跳出的，而且都不加速。自然帶出：Impact（agent 也是使用者）、Demo（三種軟體都能動）、Meta（配對）。

### 1:52–2:22 順著縫線往回走：這張票怎麼來的（中速，介紹技術）

3D 動畫，一鏡到底。鏡頭鑽進 MangoDisk 那張票的縫線，順著赭紅棉線往回飛，一次只對焦一站；每站的時間戳是 MangoDisk 那筆紀錄的**真實時間**（11/3）。

| 站 | 畫面 | 旁白 |
|---|---|---|
| 提交 18:04:23 | 一張小卡：`submit_software  github.com/harry0703/MangoDisk` | **That ticket existed before you asked. It started as one submission.** |
| 初篩 +2 s | 卡片穿過一道篩子；小標「Muse Spark Open」 | **Muse Spark Open made the first cut in two seconds.** |
| 抽取 +13 s | README 的句子被標亮、拉成量身單上的欄位，引文跟著走；小標「Muse Spark 1.3」 | **Muse Spark 1.3 read the README and kept the quotes.** |
| 沙盒 18:30–18:48 | 三個並排的沙盒（Linux on Modal／fresh macOS VM／sandboxed browser）；macOS 那個亮起：VM 裡放好的大檔、重複檔，四個功能一個個打勾；Linux 那個誠實標「needs root: not verified」 | **Then a fresh macOS VM. Muse Spark 1.3 installed it, Muse Spark Open clicked through all four features, and pickfit checked the results.** |
| 一次修正 | 一個勾選框被點偏 30 px（紅色十字），畫面放大 4 倍、十字重新對準；數字「5 → 13 of 14 hits」 | **When it kept missing small checkboxes, we measured why, and taught it to zoom in and aim again.** |
| 票牆 | 鏡頭拉遠：上百張票依種類分組成一整面牆（App／CLI／MCP server／Web app），有縫線和沒縫線的都看得到；邊上的計數 | **Nine hundred sixty-three tools listed. About six hundred fifty verified, at least through install. The rest say so.** |

自然帶出：技術深度（多階段、真的 VM、保留出處、實驗與修正）、Meta（兩個模型各有分工）、Impact（規模）。數字錄影當天重讀紀錄。

### 2:22–2:42 線的另一端，是做出它的人（收）

| 畫面 | 旁白 |
|---|---|
| 縫線從票牆邊緣跑出去，接到一張維護者的卡：MangoDisk 的公開 repo 與 release 列表（只用公開資訊）。旁邊一張新卡浮起：`submit_software github.com/you/your-app`，同一套檢查的小圖示依序亮。畫面右上角一個 **Next** 標籤，下面兩行：「Makers submit their own work」「Real outcomes sharpen every match」 | **On the other end of the thread is the person who built it. This week, pickfit went looking. Next, makers come to it: submit from your agent in one call, and the same tests run. And what agents report back will sharpen every match.** |

自然帶出：Impact（供需兩端）、長期規劃（清楚標 Next）。

### 2:42–2:56 這一晚剩下的時間（收尾）

| 畫面 | 旁白 |
|---|---|
| 左右兩塊面板：Claude app 的對話與 pickfit.app 的結果，從中間被 Fitz 用喙縫起來。真實時間的小時鐘停在錄影的結束時間。Fitz 轉頭，喙咬著一片縫好的葉子（recommending）。字標、標語、網址。片尾小字：「Add pickfit to your agent over MCP · pickfit.app」「pickfit runs on Meta's Muse Spark 1.3 and Muse Spark Open」 | **Ask through your agent, or on the web. The rest of your evening is yours. pickfit: the right software, for the person who needs it.** |

音樂收在最後一聲穿針。

## 4. 主張檢查（這版新增或改變的）

story.md 第 5 節的主張檢查照舊適用。這版另外要確認：

| 主張 | 處理 |
|---|---|
| MangoDisk 有已知漏洞 | 不迴避：agent 依伺服器說明先警告，旁白說「warns you about known vulnerabilities first」。不說「它們不影響 MangoDisk」，那是我們人工查證的推論，不是 pickfit 的檢查結果 |
| 「tested on a fresh macOS VM」 | MangoDisk 的 macOS run `verify-mangodisk-20261103-183054-4c97`：function、離線重播通過、4／4 功能；操作者 Muse Spark Open、安裝與判定 muse-spark-1.3 |
| 「Muse Spark Open made the first cut in two seconds」 | plan.md 11/3 20:16 那列：初篩 2 秒、抽取 13 秒。錄前再從 D1 或 trace 確認一次 |
| 「zoom in and aim again」 | plan.md 11/3 22:05：離線評估 14 個 x、y 點擊從 5 中變 13 中。旁白不講數字，畫面寫「5 → 13 of 14」 |
| 963／約 650 | 11/3 晚上 `data/software`：listed 963，install 以上 652。錄影當天重讀 |
| 「pickfit using MangoDisk」那段錄影 | 是工具頁上 pickfit 自己的錄影；另一個 session 可能還在調整，網頁錄影排在它完成之後 |
| patient-zero「tested on a Mac」 | macOS run `verify-patient-zero-20261031-023503-51ea`，function |
| gutenberg-mcp-server | macOS run `verify-gutenberg-mcp-server-20261103-181350-c9b3`，service |
| report_outcome | demo 的回報會被算成外部回報。要嘛不在片中呼叫，要嘛錄完請協調的 session 把那一筆排除（待念誠決定） |
| 維護者 | 只用公開的 repo 與 release 頁；不替作者說話 |

## 5. 聲音

- **旁白**：ElevenLabs、voice `2kaIk6v4SfGnZzWDde1Y`，英文，一段一檔，方便對齊。語氣：平實、溫暖、短句（和網站的口吻一樣，不誇張）。
- **配樂**：ElevenLabs Music，一首約 2:35 的曲子，分段：0:22 一針進來（輕的撥弦＋木質打擊）→ 0:30 主線穩定、讓錄影當主角 → 1:24 agent 段加快一點 → 1:52 縫線段往上堆 → 2:22 收、溫暖 → 2:56 最後一聲穿針收尾。開場 0:00–0:22 不放音樂，只有環境音與 UI 音效。
- **音效**：提示音、分頁紙籤的點擊、紙張翻動、Dock 落下、丟進垃圾桶、時鐘滴答、捲尺回捲、時鐘倒轉、穿針、縫線拉緊、蓋章。

## 6. 製作流程

1. **腳本與分鏡**（這份）→ 念誠看過、定案。
2. **素材**（可平行）：
   - 我：共用的 3D 套件（顏色、3D Fitz、紙卡、捲尺、縫線、燈光、逐格渲染器）。這是整支片的風格，先做、先給念誠看一張靜態圖。
   - 子 agent（2–3 個）：照套件做各段 3D 動畫（開場那一晚＋倒轉；縫線與票牆；維護者＋片尾）。
   - 我：真實錄影（網頁、Claude app、MangoDisk），需要念誠讓出螢幕的時段。
3. **聲音與剪輯**：ElevenLabs 旁白、配樂、音效 → ffmpeg 依時間軸合成 → 一個子 agent 以評審的眼光看完整片挑問題 → 修 → 輸出 1080p。附 YouTube 標題與說明。

程式放在 `video/`（`kit/`、`scenes/`、`capture/`、`edit/`），產生的影格、錄影與音檔不進 git。第三方：three.js（MIT）、GSAP（免費的 Standard License），用之前記進 NOTICE。

## 7. 待念誠決定

1. Claude app 那段用真實錄影（建議）還是擬真動畫。
2. 錄 Claude app 與 MangoDisk 時需要念誠讓出螢幕約 20 分鐘，由我用 Computer Use 操作；MangoDisk 1.2.2 會照 pickfit 的步驟裝進 `~/Applications`，不動 `/Applications` 裡現有的 1.1.7。
3. 片中要不要呼叫 report_outcome（見第 4 節）。
4. 標語：**The right software, for the person who needs it.**（11/3 定位更正後 story.md 建議的版本）或其他。

## 8. 實際製作紀錄（11/3 晚上）

- 旁白：11 段＋2 段重錄（揭露改成 idea and planning notes；安全那句拿掉數字，因為網頁的結果頁寫 15 個、agent 的安裝指南寫 9 則；Gutenberg 那句改成 installed … then put to work，因為要開新 session 才看得到新工具）。各段切成句子，位置在 `edit/timeline.json`。
- 錄影：Claude app 由念誠操作（Computer Use 不能操作 Claude app 本身），我錄螢幕。用的是第一次錄影（主線安裝、MangoDisk 英文介面的清除、Gutenberg）與第三次錄影（patient-zero）。Claude app 介面是中文，同意提示旁加英文字幕。
- 每段加速都在畫面上標出倍速（由 `edit/edl.json` 的片段自動算），同意提示一律 1×。
- MangoDisk 的安全檢查：網頁寫「15 known vulnerabilities」（筆數），get_install_guide 用不重複公告數 9。兩個數字不一致是網站的問題，另外處理；旁白不講數字。
- 片尾時鐘 7:05 PM：從 7:02 開始，實際流程約 3 分鐘（網頁 1 分鐘、安裝 1.5 分鐘、清除與回報 0.5 分鐘）。
- report_outcome：demo 資料夾的 pickfit MCP 帶 `X-Pickfit-Reporter: demo`，回報不算進計分，不必事後排除。
