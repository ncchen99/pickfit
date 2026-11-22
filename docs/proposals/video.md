# 驗證影片

> **狀態：已停止（2026-11-22），superseded by [docs/brief.md](../brief.md) §15.7。** 不再新增教學螢幕錄影：`PICKFIT_RECORD` 預設改成 `off`，`pickfit mac-host test --record` 要另外設 `PICKFIT_ALLOW_RECORD=1` 才會跑，coverage 的 video 維度改成 preview，沒有影片的紀錄不再算缺口。已經上線的 10 支影片保留，照舊顯示。之後改用機器讀得懂的驗證紀錄（指令、輸出、檢查結果），B、C 賽道另附幾秒的畫面預覽或一張截圖。落差與後續工作見 [brief-v15-gap-audit.md](brief-v15-gap-audit.md) 第 3.1 節。下面的原文保留供追溯，不再照著實作。
>
> 提案（2026-11-19）。總覽和共同規則在 [README.md](README.md)。

## 現況

- 前後各有 3.5 秒字卡（[video.py](../../pickfit/verify/video.py) 的 `CARD_S` 在 :106，片頭 :1783-1793，片尾 :1794-1795），在短片裡占 32–35%。
- 上方 40 px 的標籤列放日期、原始檔名、時間碼，下方 104 px 放步驟字幕（`overlay_png`，:1303-1320），全是英文。手機寬度下字幕約 9 px，標籤約 5.6 px，讀不到。
- 字卡上的資訊頁面都有了：日期和長度、打勾的功能、「pickfit 怎麼測的」摺疊區。
- 輸出 1280×944、8 fps、CRF 23、沒有聲音（:104、:1451）。原始錄影只有 4 fps、CRF 30（[record.py:43](../../pickfit/verify/record.py)、:51）。沒錄到的畫面以後補不回來。
- 上線的 10 支是 11/2–3 用 Muse 剪的，沒有去掉靜止畫面。concessio 49 秒裡約 40 秒畫面沒動，KeePassXC 96 秒裡約 44 秒。去靜止的 `still_waits`（:1061）11/18 之後才有。
- app 占畫面超過 75% 時就拍整個桌面，連 macOS 選單列和時鐘都拍進去。Linux 上游標是 X 形（x11grab，record.py:137）。桌面錄影也看不出點了哪裡。
- 頁面（[tool.ts](../../worker/src/pages/tool.ts)）：沒有聲音卻有靜音鍵（:321），「Recorded by pickfit」和「Unedited recordings」被當成章節，封面（`make_poster`，video.py:1937）燒進了字卡和標籤列。
- 剪輯清單（clip.json）和 replay 的動作紀錄只在這台 Mac 的 `~/.pickfit/videos` 和沒進 git 的 `runs/`。
- `DEFAULT_EDITOR` 還是 `"muse"`（video.py:91）。Opus 審一支要 US$0.10–0.77，164 列審查紀錄有 10 列失敗。

## 提案

### V1 原始錄影的品質（收錄前）

- 錄影從 4 fps 提到 10–12 fps，CRF 從 30 改成 20–23，preset 維持 veryfast。
- Linux 的 Xvfb 用箭頭游標（例如 `xsetroot -cursor_name left_ptr`，或換游標主題）。
- 回報寫出改動前後一分鐘錄影的檔案大小，還有 R2 儲存費用的估算。

### V2 動作紀錄跟原始錄影一起存（收錄前）

replay 每一步記下：

- 相對錄影開始的時間（開始、結束）
- 動作種類、按鍵或輸入的文字（密碼類欄位遮掉）
- 目標元件的名稱和角色（accessibility tree、UIA、DOM 有就記）
- 點擊座標、視窗位置和大小
- 操作員的 why 和看到的結果

寫成 `actions.json`，和 `clip.json`（剪輯清單）、原始錄影一起上傳到 R2（上傳在 video.py:1965 附近）。紀錄裡存 R2 的 key 和 sha256。之後要重剪、加點擊提示、重做字幕，都從這三個檔案來，不用重跑沙盒。

### V3 畫面裡不燒英文（收錄前）

| 畫面裡的字 | 改法 |
|---|---|
| 片頭字卡 | 拿掉。資訊移到頁面，影片最多在角落留一個小 logo |
| 片尾字卡（原始錄影長度、sha256、run id） | 拿掉。資訊移到摺疊區，sha256 本來就在 mp4 metadata 裡 |
| 上方標籤列 | 拿掉。追溯用的資訊改成章節旁邊的「看原始錄影」連結，連到原始錄影的那個時間點 |
| 下方步驟字幕 | 改成 WebVTT 字幕軌，預設打開 |
| 「2×」「略過 N 秒沒變的畫面」 | 留在畫面上，改成不用翻譯的小標記（「2×」「−11 s」）。誠實規則要求每個受影響的畫面都要標 |

字幕的做法：

- `RunVideo` 加 `captions`（cue 清單：開始、結束、文字），文字從動作紀錄產生。
- 加進 `pickfit/i18n.py` 的 `PROSE_KEYS`，跟頁面其他句子一起翻成中文。
- worker 依語言輸出 `.vtt`，`<video>` 加 `<track kind="captions" default>`，播放器有 CC 開關。
- `boundaries()`（video.py:1465-1491）的章節改成只有功能章節。

### V4 頁面的小修正（收錄前，改動小）

- 沒有聲音的影片不顯示靜音鍵。
- 「Recorded by pickfit」「Unedited recordings」不再列成章節。
- 原始錄影的連結和 sha256 放進「pickfit 怎麼測的」摺疊區（tool.ts:669-678 附近）。
- 封面用乾淨的畫面：取功能結果出現的那一格，不燒任何字。

只改 tool.ts 的影片區。安全區歸 security 提案。

### V5 點擊漣漪和按鍵提示（可以並行做）

從動作紀錄畫在影片上：點擊的位置出現一圈漣漪，按快捷鍵時在角落顯示按鍵（例如 ⌘⇧G）。都不用翻譯。

### V6 剪輯和審查改成以規則為主（可以並行做）

- `DEFAULT_EDITOR` 從 `"muse"` 改成規則版。黑客松結束了，Muse 不再是預設。
- 字幕和章節從動作紀錄產生，不用模型。
- 「看不看得到」改成拿影片的畫格和 pickfit 自己每一步的截圖比對。比對不過的、或抽樣到的，才請 Opus 審。

## 之後再做

有了 V1、V2 存下的資料，這些都能隨時重剪：

- 裁掉選單列和工作列，固定 16:10。
- 載入畫面快轉 4–8 倍，每個功能 30 秒內，整支 60 秒內。
- 把上線的 10 支用 `still_waits` 和新的字幕重剪。重剪要寫回紀錄、上傳 R2，由協調 session 決定什麼時候跑。

## 驗收

- 錄影參數、動作紀錄格式、WebVTT 產生、i18n、頁面輸出都有測試。
- 用本機已有的一支原始錄影（`~/.pickfit/videos`）在本機重剪一次，傳截圖給協調 session 看。不要上傳 R2，不要寫進 `data/software/`。

## 不做的事

- 不改已經上線的影片和紀錄。
- 「2×」「−11 s」這類標記不能拿掉，這是誠實規則。
