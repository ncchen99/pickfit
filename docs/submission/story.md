# pickfit 的故事與 demo 影片筆記

2026-11-02 晚上，整理自念誠口述。產品事實以 [docs/brief.md](../brief.md) 為準，品牌以 [DESIGN.md](../../DESIGN.md) 為準。做影片的 session 先讀這份。

## 1. 核心

**讓原本看不見的軟體被看見，讓真正需要的人找到它。**

一句話：把獨特的軟體和獨特的使用者一對一配對，一個 AI 軟體平台。

## 2. 為什麼需要 pickfit

### 對需要軟體的人

1. **重做很貴。** 開發軟體最花成本的地方在微調和維護。只有使用者自己知道在特定情境下要什麼，就算 AI 能寫出第一版，人還是要一直跟它磨合，才會真的好用。直接用別人已經做好、持續維護的作品，省下的就是這些成本。
2. **找和裝很累。**
   - 軟體散在 GitHub、推薦網站和各個平台，要開好幾個分頁到處比較。
   - 想知道某個功能用起來長什麼樣子，要再去 YouTube 找。
   - 知道 Windows 有這款工具，卻不知道 Mac 有沒有，又要重新搜一輪。
   - 例如找聽寫（dictation）軟體，常常一次裝 3 到 4 款，一個一個試，再留下最喜歡的。
3. **網路上的比較多半是主觀評論。** 有人說 A 好，有人說 B 好，看不出軟體實際做得到什麼。其實只要符合自己的需求就好。
4. **Agent 自己上網找的資料參差不齊。** 一款是在 GitHub 看到的，另一款是在推薦網站看到的，來源和格式都不一樣。資訊不對稱，就很難推薦最合適的。

### 對開發者

用心做出來的作品，不靠行銷預算也能被看見，被真正需要的人用到。

### pickfit 怎麼解

- 每款軟體都在沙盒裡裝過、測過，產出同一格式的報告。Agent 拿到的是可以互相比較的事實，所以能客觀、精準地推薦。
- 使用者透過 MCP 請自己的 agent 找軟體、裝軟體，照 pickfit 實測成功的步驟裝。
- GUI app 附 pickfit 實際操作的影片，依功能分段，可以直接跳到想看的功能，確認是不是自己要的。
- 可以並排比較，不必再到處看評論。

## 3. 今天做得到的，和還在規劃的

影片和文案只能把「做得到」的說成現在式。

| 做得到（11/2） | 進行中或規劃中 |
|---|---|
| 約 960 款上架：開發者 CLI、本地 AI 工具、MCP 伺服器、網頁應用、桌面 GUI app。來源有 GitHub、Show HN、Flathub、Homebrew Cask | GUI 與網頁的介面、易用性評分（11/2 開始規劃） |
| 約 650 款驗證到 install 以上：Linux 沙盒（Modal）、全新的 macOS VM、沙盒瀏覽器 | 網頁應用的操作錄影（11/2 開始試跑） |
| MCP：find_software、find_alternatives、get_install_guide、report_outcome、submit_software；中英雙語網頁 | 繁體中文等語言支援度的實測（還沒做，不要宣稱） |
| Meta 模型：Muse Spark 1.3 抽取、評判、即時配對；Muse Spark Open 初篩、驗證 agent、操作 GUI app | 開發者大量投稿、使用回饋讓推薦越來越準（長期規劃） |
| 幾款 GUI app 有 pickfit 操作的錄影，依功能分段 | |
| 依適合度排序，不看星數；沒有廣告；沒驗證的會標出來 | |

數字在定稿前重新查一次（`uv run pickfit publish --dry-run` 與工具頁）。

## 4. 影片製作筆記（念誠 11/2）

### 4.1 規則上的固定要求

- **第一句話必須說明哪些是賽前就有的、哪些是這週做的**（官方 FAQ，見 [hackathon-rules.md](../hackathon-rules.md) 第 7、10 節）。開場文案接在這句之後，或把這句寫進開場的節奏裡，但它要是第一句。
- 片長 3 分鐘，連結公開可看，只展示比賽期間做的東西。

### 4.2 動畫與視覺

- 要做 motion 動畫。節奏可以快，但畫面不要太花。要讓評審看得出動畫有用心，有一些新穎的效果。
- 配色、design system、吉祥物 Fitz 都照現在的品牌設定：
  - 品牌：[DESIGN.md](../../DESIGN.md) 與 [brand/mascot/README.md](../../brand/mascot/README.md)。
  - 網頁：<https://pickfit-mcp.ncchen99.workers.dev/>。
  - 調性：裁縫的試衣間，墨綠的裁切墊、黃色量尺、赭紅縫線，字體 Bricolage Grotesque。
  - Fitz 的配色不能改。
- 參考的動畫 Skill：Emil Kowalski 的 **animate**（<https://open-design.ai/zh/skills/animate/>）。
  - 原始碼：<https://github.com/emilkowalski/skills> 的 `skills/animate/SKILL.md`，MIT 授權。
  - 安裝：`npx skills add https://github.com/emilkowalski/skills --skill animate`。要裝時先告訴協調的 session，並記進 NOTICE。
  - 它從便宜的做法往上選：CSS transition、`@starting-style`、CSS animation、Web Animations API、Motion。依序決定六件事：要不要動、目的、工具、屬性、曲線與長度、打斷與退場。
  - 對影片有用的原則：
    - 每個動畫要有一個詞說得出的目的。
    - 只動 transform 與 opacity，clip-path 也可以。
    - 進場從 scale 0.9–0.97 加 opacity，不從 0 放大。
    - UI 不用 ease-in。
    - 沿用網頁現有的時間與曲線 token，不另立一套。
    - 驚喜效果留給少數時刻。

### 4.3 腳本與敘事

- [VIDEO.draft.md](VIDEO.draft.md)（Gemini 4 寫的腳本與分鏡）**不採用**，暫時擱置。新腳本不要以它為底。
- 不要照評分項目把影片切成一段一段回答（Impact、Use of Meta AI Tooling、Technical Depth、Demo）。那樣很無聊，看起來只是交作業。
- 要規劃一整個情境，用流暢的畫面敘事，評分重點在故事裡自然帶出來，讓人看到的是一個真正要落地的平台。
- 開場像形象或行銷文案：很快地丟出幾個渴望或痛點，讓看的人馬上懂價值。念誠的例子：「想找免費的替代軟體，在網路上一直比較挑選，花了好多時間才找到符合需求的那一款……」

### 4.4 聲音

- 用 ElevenLabs 的 API 產生配樂、音效和英文人聲旁白。念誠這個月有買方案。
- 念誠已在 Claude 的 connector 加入 ElevenLabs 並登入。
- 影片是英文版。

### 4.5 Demo 用的軟體

念誠正在從 [demo-shortlist.md](../demo-shortlist.md) 挑，選好後告訴協調的 session。腳本裡先用 [demo app] 佔位。

## 5. 開場文案與全片敘事線（草稿，11/2）

這一節是 4 份撰稿（痛點連發、同一個人的同一晚、維護者與使用者、意見對證據）經 3 位評審（看片很多的黑客松評審、挑剔的開發者、品牌剪輯）打分後合併的草稿，沒有參考 VIDEO.draft.md。念誠還沒選定，demo 軟體也還沒定，先用 [demo app] 佔位。

**還要補的兩件事：**
- **第一句一定是賽前揭露**（第 4.1 節）。建議 0:00–0:04 先放在紙色底上，例如：*"Before this week we had research notes only. Everything you'll see was built during the hackathon."*（賽前我們只有研究筆記，片中所有東西都是這週做的。）接著才進下面的開場，後面整體往後挪約 4 秒。
- **錄影前要先改 MCP 伺服器說明的範圍**。說明現在只寫 dev CLIs、local AI tools、MCP servers、web apps，沒有桌面 GUI app。如果 demo 是 GUI app，agent 可能當場說不在範圍內。

易用性評分如果在錄影前做好、而且校準通過，才可以放進片中，否則照下面的主張檢查不出現。

### 一句話定位

**pickfit is an AI fitting room for software. It matches one-of-a-kind software to the one person it fits.**
（pickfit 是軟體的 AI 試衣間：把獨特的軟體，一對一配給剛好需要它的人。）

更短的版本：**Unique software. Unique people. Matched one to one.**（獨特的軟體，獨特的人，一對一配對。）

標語三選一：

1. **Unseen software, meet the person it was made for.**（看不見的軟體，去見那個它本來就要服務的人。）← 推薦
2. Don't rebuild it. Find the one that fits.（別重做。找到合身的那一款。）
3. Not the most starred. The one that fits.（不是星數最多的，是最合身的。）

推薦第 1 個。它一句話就講到兩邊：做軟體的人被看見，需要的人找得到。這正是念誠說的核心價值，而且沒有做任何絕對的承諾。第 2 個留在片尾維護者那段當旁白用。

---

### 開場三版

三版共用的規則：
- 開場全部放在紙色底上，只用墨色，不出現綠、黃、紅棕。品牌色留到轉折時才第一次出現。
- 畫面同時最多三層。新的一層進來時，舊的往後退並變暗，不堆到滿版。
- 所有網站、評論、圖示都是虛構的通用樣式，不放真實品牌或 logo。

### A 版：痛點連發

| 秒數 | 畫面字 | 旁白 | 畫面 |
|---|---|---|---|
| 0.0–2.0 | free alternative to ___（___ 的免費替代） | Looking for a free alternative?（在找免費的替代軟體？） | 一個搜尋框，游標打字。按下 Enter，結果彈成一排分頁 |
| 2.0–4.0 | 12 tabs · "Top 10 … for 2026"（12 個分頁・「2026 十大…」） | Twelve tabs. Five best-of lists.（十二個分頁，五篇推薦清單。） | 分頁擠成細條，虛構的清單標題像卡片一樣翻過去 |
| 4.0–6.5 | 7:42 … there it is（7:42…找到了） | A whole video, just to see one button.（看完整支影片，只為了看一個按鈕。） | 無品牌的播放器，播放頭來回找，最後停在一個被圈起來的小按鈕 |
| 6.5–8.5 | Windows only.（只有 Windows 版。） | Is there a Mac version?（有 Mac 版嗎？） | 下載頁的系統欄只寫 Windows，字歪斜後滑出畫面 |
| 8.5–10.5 | 4 installed · 3 deleted（裝 4・刪 3） | Install four. Keep one.（裝四個，留一個。） | 四個虛構圖示照節拍掉進 Dock，其中三個依序飛進垃圾桶 |
| 10.5–12.5 | "A is better." "No, B."（「A 比較好。」「不，B。」） | Plenty of opinions. Few facts.（意見很多，事實很少。） | 留言泡泡從兩側疊進來 |
| 12.5–14.5 | "I think it works offline?"（「應該可以離線吧？」） | Ask your agent? It reads the same scattered pages.（問 agent？它讀的也是同一堆零散網頁。） | agent 的回覆泡泡是用 README 角落、舊論壇文、清單文的碎片拼起來的 |
| 14.5–18.0 | build me a … / v1 → v2 → v17（幫我做一個… / v1 → v2 → v17） | Or have AI build it… and tune it for months.（或叫 AI 做一個……再調上好幾個月。） | 程式碼一閃就生成，版本號一直往上跳，設定滑桿來回抖動 |

### B 版：同一個人的同一晚

| 秒數 | 畫面字 | 旁白 | 畫面 |
|---|---|---|---|
| 0.0–3.0 | 7:02 PM / free dictation app mac offline（免費離線 Mac 聽寫軟體）[佔位] | Seven p.m. You need one small app. Free, offline, on your Mac.（晚上七點。你只需要一個小工具：免費、離線、能在 Mac 上用。） | 一個搜尋框，游標打字。底部一條墨色時間尺從 7:02 開始走 |
| 3.0–4.8 | 1 → 10 tabs（1 → 10 個分頁） | Ten tabs.（十個分頁。） | 分頁像紙籤一樣擠進上緣，越擠越細，每個配一聲輕點擊 |
| 4.8–7.0 | "A is the one." / "No. Get B."（「就是 A。」／「不，選 B。」） | One review says A. The next says B.（這篇說 A，下一篇說 B。） | 兩張評論卡從左右翻進來，疊在一起 |
| 7.0–9.4 | 4:31 / 12:47 | A twelve-minute video, for one button.（為了一個按鈕，看十二分鐘的影片。） | 播放頭來回拖，時間尺往前跳一大段 |
| 9.4–11.2 | Windows only（只有 Windows 版） | The perfect one? Windows only.（最理想的那款？只有 Windows 版。） | 下載卡上 Mac 的位置是一個虛線空框，配一聲悶響 |
| 11.2–13.2 | Installed 4 · Deleted 3（裝 4・刪 3） | Install four. Delete three.（裝四個，刪三個。） | 四個圖示掉進 Dock，三個依序拖進垃圾桶 |
| 13.2–16.2 | build me a dictation app → v9 · "fix hotkey"（幫我做聽寫 app → v9・「修快捷鍵」） | Have AI build one? Then you'd tune it for weeks.（叫 AI 做一個？接下來要調好幾週。） | 程式碼生成後，便條紙一張張疊上來，小月曆翻頁。時間尺被拉成一條延伸出畫面的虛線 |
| 16.2–18.5 | 11:48 PM | Eleven forty-eight. Still not sure.（十一點四十八。還是不確定。） | 全部定格，音樂抽掉，只剩一聲時鐘滴答 |

### C 版：維護者與使用者

| 秒數 | 畫面字 | 旁白 | 畫面 |
|---|---|---|---|
| 0.0–3.0 | free dictation app mac offline（免費離線 Mac 聽寫軟體） | You need one small app.（你需要一個小工具。） | 畫面中間有一條還沒縫上的虛線，把畫面分成兩半，只有右半（使用者）亮著 |
| 3.0–6.5 | 10 tabs · A vs B · 4 in, 3 out（10 分頁・A 對 B・裝 4 刪 3） | You search. Compare. Install four. Keep one.（你搜尋、比較，裝四個，留一個。） | 搜尋紙籤、擠扁的分頁、Dock 圖示一進一出，節奏很快 |
| 6.5–9.5 | build me one → to-do list grows（幫我做一個 → 待辦清單越來越長） | Or have AI build one, and tune it for weeks.（或叫 AI 做一個，再調好幾週。） | 程式碼停下來了，待辦清單還在繼續長 |
| 9.5–14.5 | [demo app] changelog（更新紀錄，真實且須作者同意） | Someone already did that tuning. It just never reached you.（那些調整早就有人做完了，只是從沒傳到你面前。） | 左半亮起，維護者的更新紀錄往上捲，和右邊的待辦清單對成一對：同樣的調整付了兩次 |
| 14.5–17.5 | [demo app] ← → empty slot（空位） | Same tool. Two people.（同一個工具，兩個人。） | 拉遠看兩半，中間的縫線還空著。下一拍 Fitz 飛下來，用喙把縫線縫起來 |

**推薦 B 版。**
- B 把所有痛點放在同一條「一晚上」的時間尺上，接著 pickfit 把這一晚捲回來，不用解釋就看得出價值。三位評審給它的情緒和故事分數都最高。
- 做法是用 B 當骨架，借 A 的短句節奏。C 的維護者移到片尾當收尾，因為前 5 秒一定要是觀眾自己的痛。

---

### 全片敘事線

製作備註：旁白、配樂、音效全部用 ElevenLabs 產生英文版。開場只有環境音和 UI 音效，音樂在轉折那一針才進來。

| 時間 | 情節 | 畫面 | 旁白 | 自然帶出的評分重點 |
|---|---|---|---|---|
| 0:00–0:18 | 一個小需求，吃掉一整晚 | 同 B 版開場 | 同 B 版開場 | Impact：每個人都遇過的痛，也點到「乾脆自己重做」的成本 |
| 0:18–0:27 | Fitz 把這一晚捲回來 | 先靜音半拍。墊板綠和量尺格線從下緣漫上來，墨色時間尺變成黃色量尺。Fitz 用轉頭姿勢落地，喙咬住量尺尾端往回捲：時鐘從 11:48 倒轉回 7:02，分頁飛回去一一關掉。wordmark 落在墊板上，紅棕色的點用一針縫上 | Chances are, someone already built it. pickfit finds it, and tells you what it actually tested.（很可能早就有人做好了。pickfit 把它找出來，並告訴你它實際測過什麼。） | Impact：核心價值一句話講完。Demo：招牌轉場，品牌、吉祥物和聲音一起出場 |
| 0:27–0:42 | 晚上七點，重來一次 | 實際錄影：使用者自己的 MCP client，在 Mac 上。輸入 "I need dictation on my Mac. Free, works offline."（我要 Mac 上的聽寫，免費、能離線。）[demo app 類別待定]。出現工具呼叫標籤 pickfit · find_software，量身卡組起來：macOS · Apple silicon · free · offline。角落是 Fitz 的 searching 狀態。pickfit 這一側掛著小標籤 "matching: Muse Spark 1.3"（配對：Muse Spark 1.3）。畫面上沒有任何分頁 | Seven p.m., again. This time you ask your agent. On its own, it would read the same ten tabs. Instead, it asks pickfit, over MCP.（晚上七點，重來一次。這次你問你的 agent。它自己找，也只會讀同樣那十個分頁；這次它透過 MCP 去問 pickfit。） | Impact：發生在使用者本來就在用的 agent 裡，也回應了「agent 自己找的資料參差不齊」。Meta tooling：即時配對。Demo：真的能動 |
| 0:42–1:04 | 合身的票一張張落下 | 試衣票從量尺上滑下來，照合身程度排，張數照實際結果。每張票上半是合身句，縫線下是理由；滑過一個理由，就打開它的出處（README 引文或執行紀錄）。驗證過的票邊緣有紅棕縫線，執行標籤寫出平台。最下面是有名的那一款：沒有縫線、徽章、步驟和連結，標著 "not verified"（未驗證），旁邊的 Fitz 是 neutral。角落寫 "No ads. Ranked by fit."（沒有廣告，照合身程度排。） | Muse Spark 1.3 matches your words against pickfit's records. Ranked by fit, not stars. No ads. Each reason points to where it came from. A stitch means pickfit ran it. The famous one is here too, marked plainly: not verified.（Muse Spark 1.3 拿你的話去對 pickfit 的紀錄。照合身程度排，不看星數，沒有廣告。每個理由都指得出出處。有縫線，代表 pickfit 真的跑過。有名的那款也在，清楚標示：未驗證。） | Meta tooling：配對，加上帶引文的抽取。Technical depth：每個說法都有出處。Impact：中立、可信，小眾工具也能被看到 |
| 1:04–1:28 | 不用再拖影片進度條 | 點 [demo app] 的 "watch the run"（看執行過程），播放 pickfit 在全新 macOS 虛擬機上操作它的實際錄影。側邊章節列，一個章節對一個檢查過的功能，通過與否照紀錄顯示（用頁面本身的 UI，不另外疊動畫）。點章節直接跳過去。小字："fresh macOS VM · operated by Muse Spark Open"（全新 macOS 虛擬機・由 Muse Spark Open 操作）。角落是 Fitz 的 testing 姿勢。這段動態放慢，讓錄影當主角 | Normally you'd scrub a video here. This is pickfit using [demo app] on a fresh macOS VM. One chapter for each feature it checked. Jump to the one you care about. The hands are Muse Spark Open, Meta's open-weight model.（平常你得在這裡拖進度條。這是 pickfit 在全新 macOS 虛擬機上操作 [demo app]。每個檢查過的功能一個章節，直接跳到你在意的那段。操作的手，是 Meta 的開放權重模型 Muse Spark Open。） | Meta tooling：讓人意外的一刻，開放權重模型在操作桌面 GUI app。Technical depth：虛擬機、逐功能章節。Impact：不用再去找 YouTube 影片 |
| 1:28–1:50 | 裝一個，就留一個 | 回到 agent。使用者說 "Let's go with the first one."（就第一個吧。）get_install_guide 回傳步驟，附上當初成功的 OS、CPU 和日期（照執行紀錄）。client 真正的同意提示跳出來，使用者按同意；終端機跑完，app 打開，使用者第一次用它。接著 report_outcome: success，Fitz 這時才換成 happy。角落時鐘顯示真實時間 | Pick one. Your agent gets the exact steps that worked in the sandbox. It asks first, then runs them. [first-use line, e.g. You talk. It types.] Install one. Keep one. Then it tells pickfit how it went.（選一個。agent 拿到在沙盒裡成功的那套步驟，先問你，再執行。[第一次使用的一句，例如：你說話，它打字。] 裝一個，就留一個。最後它回報 pickfit 用得怎麼樣。） | Demo：從需求到裝好能用，中間不剪接。Impact：省下一整晚，裝起來也方便。Technical depth：重現實際跑過的步驟、有同意步驟、有結果回報 |
| 1:50–2:18 | 順著縫線往回走，看這張票怎麼來的 | 鏡頭鑽進選中那張票的縫線，順著紅棕線一路往回走，不剪接，一次只對焦一站。依序是：來源名稱用純文字（GitHub · Show HN · Flathub · Homebrew Cask）→ 初篩，掛 "Muse Spark Open" 小標籤 → README 的句子被標亮、提成欄位，掛 "Muse Spark 1.3" → 三個沙盒視窗並排（Linux on Modal / fresh macOS VM / sandboxed browser），驗證 agent 掛 "Muse Spark Open"，量尺讀數填滿 → 判定戳章 "Muse Spark 1.3"。最後拉遠成一整面票牆，依種類分組，有縫線和沒縫線的都看得到。量尺邊緣的計數：~960 listed · ~650 verified（約 960 收錄・約 650 驗證） | That ticket existed before you asked. pickfit looks where small projects live. Muse Spark Open makes the first cut. Muse Spark 1.3 reads the README and keeps the quotes. A Muse Spark Open agent installs it in a sandbox and tries it. Muse Spark 1.3 judges what passed. About nine hundred sixty tools listed. About six hundred fifty verified, at least through install. The rest say so.（你開口之前，這張票就已經在了。pickfit 去小專案會出現的地方找。Muse Spark Open 先篩一輪；Muse Spark 1.3 讀 README，留下引文；Muse Spark Open 的 agent 在沙盒裡安裝、試用；Muse Spark 1.3 判斷哪些通過。目前收錄約九百六十個工具，約六百五十個至少驗證到安裝。其餘的都標示清楚。） | Technical depth：多階段流程、三種沙盒、保留出處。Meta tooling：兩個 Meta 模型各有分工，遠超過基本串接。Impact：規模 |
| 2:18–2:42 | 線的另一端，是做出它的人 | 線從票牆邊緣跑出去，接到維護者：[demo app] 的真實 repo 和更新紀錄（須作者同意），看得出它被持續調整。開場那疊「叫 AI 重做」的便條紙閃一下就落下。接著維護者在自己的 agent 裡呼叫 pickfit · submit_software github.com/[maker]/[repo]。維護者的票和使用者的量身卡漂到一起，Fitz 用轉頭姿勢以喙縫上一針：一個工具，一個人 | On the other end of the thread: the person who built it, and still tunes it. Rebuilding it with AI would mean paying for all that tuning again. Don't rebuild it. Built something? Submit it from your agent, in one call.（線的另一端，是做出它、到現在還在調它的人。叫 AI 重做，等於把這些調整的成本再付一次。別重做。你也做了工具？在你的 agent 裡一個指令就能提交。） | Impact：兩邊都受益，回到核心價值。Demo：作者那一端的 MCP 工具也能用 |
| 2:42–3:00 | 這一晚剩下的時間 | 左右分割：左邊是 agent 對話，右邊是 pickfit 網頁（打一個搜尋，出現同樣樣式的票），兩半從中間縫起來。角落時鐘停在真實的結束時間。Fitz 用轉頭姿勢 recommending，喙咬著縫好的葉子。接著是 wordmark、標語、網址。片尾小字："Add pickfit to your agent over MCP"（用 MCP 把 pickfit 加進你的 agent）/ "pickfit runs on Meta's Muse Spark 1.3 and Muse Spark Open"（pickfit 跑在 Meta 的 Muse Spark 1.3 與 Muse Spark Open 上）。音樂收在最後一聲穿針 | Ask through your agent, or on the web. [real end time, e.g. Seven twelve.] The rest of your evening is yours. And a maker's work just found its person. pickfit.（透過 agent 問，或上網頁問。[真實結束時間，例如：七點十二分。] 這一晚剩下的時間是你的。而一位開發者的作品，剛好找到了它的人。pickfit。）畫面標語：Unseen software, meet the person it was made for. | Impact：兩個入口，誰都用得到，最後用一對一配對的畫面收尾。Meta tooling：片尾點名模型。Demo：完整的收尾 |

---

### 主張檢查

| 主張 | 文案怎麼處理 | 錄影前要確認 |
|---|---|---|
| 轉折句 | 加上 "Chances are" 保留空間，後半句改成 "tells you what it actually tested"，不寫 "tries everything" | 無 |
| 數字 | 一律說 about，而且 listed 和 verified 分開講；verified 寫成 "at least through install" | 錄影當天重新讀 catalog 的實際數字 |
| 理由的出處 | 寫 "points to where it came from"，不寫 "every reason quotes"。配對當下產生的理由是英文生成句，不是引文 | 挑一個確實連到 README 引文的理由來示範 |
| 縫線的意思 | 縫線代表 "pickfit ran it"，在哪個平台跑過寫在執行標籤上，不寫進縫線的定義裡 | [demo app] 真的在 macOS VM 上驗證過，才能寫 macOS |
| 錄影那段 | 寫 "each feature it checked"，不寫 every feature。不描述模型怎麼「看」畫面 | [demo app] 要是少數已有逐功能章節錄影的 GUI app，而且確實由 Muse Spark Open 操作。web app 的錄影要做完才放 |
| 聽寫的準確度 | "You talk. It types." 是使用者自己現場在用，不是 pickfit 的測試結果。VM 大概沒辦法測麥克風轉文字 | 旁白和字幕不能暗示 pickfit 測過辨識準確度 |
| fresh Mac | 旁白和字幕都寫 "fresh macOS VM"，不寫 fresh Mac 或 macOS machines | 無 |
| 模型分工 | Muse Spark 1.3 負責抽取（帶引文）、判定、即時配對；Muse Spark Open 負責初篩、驗證 agent、操作 GUI | 確認 discovery 進來的候選都會經過初篩，"first cut" 才成立 |
| 畫面上的 agent client | 它是使用者自己的第三方 client。pickfit 那一側一直掛著 "matching: Muse Spark 1.3"，片尾寫的是 "pickfit runs on…"，不是整條鏈都跑在 Meta 模型上 | 無 |
| MCP 的範圍說明 | 不需要改文案 | MCP 說明目前寫的還是 "Scope today: developer CLI tools and local AI/LLM tools"。錄影前要更新，也要確認 find_software 會回傳 GUI app，否則 agent 可能當場說不在範圍內 |
| submit_software | 只說 "Submit it from your agent, in one call"，不說 pickfit 會接著幫它測試 | 確認提交後真的會排進驗證，才可以加上那一句 |
| report_outcome | 只說 "tells pickfit how it went"，不說會改善排名 | 無 |
| 安裝前的同意 | 用 client 真正的同意提示，不另外做假的 | 無 |
| 時間 | 前面那一晚（7:02 到 11:48）是故事，畫面不放「4 h 46 min」這種看起來像量測數據的字。後面的結束時間用真實經過的時間 | 錄完再填真實的結束時間 |
| 維護者 | 不說 "hardly anyone found it"，也不說 "pickfit found it anyway" | 用真實 repo 要作者同意。"still tunes it" 只有在專案確實還在維護時才能用 |
| 開場的假畫面 | 全部是虛構的通用樣式：不放真實網站、評論、logo，不放 sponsored 清單，不放假統計。「裝四個留一個」只是故事，不是數據 | 無 |
| 照合身程度排，不看星數 | 「沒有廣告、照合身程度排」是真的，可以照講 | 只有實際結果的順序真的跟星數不同，畫面才凸顯這一點 |
| 有名的那一款 | 沒有縫線、徽章、步驟、連結，旁邊 Fitz 是 neutral。Fitz 只有在 report_outcome success 之後才 happy | 無 |
| 介面與易用性評分 | 還沒做，全片不出現，片尾也不放 "Next" 標籤 | 無 |
| 語言支援測試（例如繁中） | 還沒做，全片不提。念誠舉的繁中例子先拿掉。網頁的 EN／中文切換也不放進片裡，避免出現在聽寫 app 旁邊被誤解成測過語言 | 無 |
| 翻譯用哪個模型 | 片中不提 | README 寫的是 Claude，近期 commit 寫的是 Muse Spark Open，日後要提之前先確認 |
| 網頁和 agent 一樣 | 只說 "or on the web"，不說 "same picks"，因為即時配對每次可能不同 | 無 |
| 吉祥物的道具 | 量尺用來量，縫線由 Fitz 用喙縫，不讓 Fitz 拿量尺去縫 | 無 |

## 6. 評測告訴我們的事，以及平台的限制與展望（念誠 11/2）

評測定稿在 [eval/results/final/report.md](../../eval/results/final/report.md)。以下第 6.1 節是念誠讀完結果後的看法，第 6.2 節是報告裡支撐或還沒支撐這些看法的地方。

### 6.1 念誠的看法

- 評測是正向的回饋，但也說明我們的資料太少。我們已經加入 301–5000 星的 repo。
- 瓶頸在 API 額度。我們是個人開發者，念誠也還是學生，沒辦法投入很多資源。
- 好的開始：在還沒有使用者的時候，我們就能主動、大量地收集軟體。
- 從評測可以推斷：資料量提升、收進著名的軟體之後，效果會好很多。
- 模型能力也是限制。做同樣的事，Muse Spark Open 的能力有點不夠，換成 Muse Spark（1.3）就好很多，換成更強的模型會更好。實際測軟體功能、操作 GUI 這兩塊特別吃模型能力，從模型的跑分也看得出來。所以平台目前能做的深度，受限於模型。

### 6.2 證據對照（寫 README 或影片時照這個分寸）

- **資料覆蓋面是主要失分**（有證據）：
  - 輸的 17 題裡，10 題是 pickfit 回空結果。
  - 51 次空回應全部是資料裡沒有通過 L1 的工具，沒有一次是「有卻沒找到」。
  - 正確答案多半是 Bruno、Docling、aichat 這類已知的大專案，當時沒收。
- **資料變多就會更好**（推論，評測沒證明）：
  - 301–5000 星是看過結果後才加的，評測當時沒有。
  - 要說「變好」，只能做標明為事後、探索性的檢查。例如查那些正確答案現在有沒有收進資料，這不用花模型錢。
- **模型能力的差異**（念誠的觀察，要寫進 README 前先補具體例子）：
  - 可以引用的已有紀錄：Muse Spark Open 操作 Mac GUI 時會點偏幾十像素（易用性提案的風險段）；繁中翻譯比較時 Spark Open 的意思錯誤比 Claude 多（plan 11/2 22:10 那一列）。
  - 「換成 Muse Spark 1.3 就好很多」目前沒有同一任務的並排數據。要寫就寫成觀察，或先補一個小比較。
- **對外的說法**：
  - 不寫成「Meta 的模型不夠好」。
  - 寫成：功能實測與 GUI 操作的深度，會隨模型能力一起提升；同一套流程，換更強的模型就能測得更深。
