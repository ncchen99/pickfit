# C 賽道成對候選清單 v1（2026-11-22）

對應 [brief-v15-gap-audit.md](../proposals/brief-v15-gap-audit.md) 第 2.4、3.5 節與 P3-01。C 賽道收的是「GUI 本體＋給 agent 的介面」成對的創作與文件工具（brief 15.3 C）。這份清單只挑兩邊都開源、Linux 有套件、檔案是 pickfit 讀得懂的格式的組合。

GitHub 資料在 2026-11-22 用 `gh api graphql` 查（免費、只讀），欄位是 repo 名稱、`licenseInfo.spdxId`、`pushedAt`、是否封存、星數。GitHub 回 `NOASSERTION` 或沒有授權資訊的，另外讀了 repo 裡的授權檔。這份清單還沒進沙盒跑過，表裡的「Linux Xvfb 可測性」是依套件與介面判斷的預估，第一輪實測後要回填。

## 驗證流程（所有組合共用）

管線骨架在 `pickfit/verify/gui_operate.py`：

1. **MCP／腳本產出**：在同一個 box 裡用軟體自己的 MCP tool call 或腳本，把檔案存到家目錄下（不能放 `~/pickfit-in/`、`~/pickfit-out/`，這兩個資料夾在 GUI 啟動前會被清掉或改寫）。
2. **帶入 GUI**：`GuiInput(source="mcp_output", from_path=..., path="~/pickfit-in/...")`。`run_operation` 會把上游檔複製到 `~/pickfit-in/`，在紀錄裡留 `staged.sha256` 與大小。
3. **GUI 修改存檔**：operator 照 goal 在 GUI 裡改一個地方（加一段字、改一格、移一個物件）再存檔。
4. **驗檔**：`check.kind="file"`、`format` 填 `docx`／`pptx`／`xlsx`／`svg` 等。in-box 檢查會比對操作前的 sha256 與 mtime，再檢查格式能不能解析、內容有沒有 `{nonce}`。

本機可以先用 `verify_coedit_roundtrip(upstream, workdir, operate, format=..., contains=[...])` 跑同一套判定：上游檔格式要合法、存檔後檔案要在、sha256 要變（只動到 mtime 算沒改）、格式要還能解析、文字要包含指定字串。docx／pptx／xlsx 會檢查 zip 完整、`[Content_Types].xml` 與 `_rels/.rels` 存在，每個 XML 部件都要能解析，主文件的根元素也要對。svg 要能解析成 XML，根元素是 `<svg>`。

## 候選組合

| # | GUI 本體 | 授權（GUI） | GUI 最後推送 | MCP／腳本介面 | 授權（介面） | 介面最後推送 | 檔案格式 | Linux Xvfb 可測性 |
|---|---|---|---|---|---|---|---|---|
| 1 | LibreOffice（`LibreOffice/core`，GitHub 唯讀鏡像） | GPL-3.0（GitHub 判定；上游為 MPL-2.0 為主，收錄前再對 COPYING） | 2026-11-22 | `haris-musa/excel-mcp-server`（4.3k★）、`ForLegalAI/mcp-ms-office-documents`（docx／pptx／xlsx，45★）；即時操作 GUI 的備案：`quazardous/nelson-mcp`（UNO，47★） | MIT、MIT、MPL-2.0 | 11-20、11-20、11-19 | xlsx、docx、pptx | 高。Ubuntu 有 `libreoffice` 套件，Xvfb 下開得起來，`soffice --headless` 也可轉檔交叉比對 |
| 2 | Inkscape（上游在 GitLab；GitHub `inkscape/inkscape` 只剩一份指向 GitLab 的 README，2022-03 後沒更新） | **未核實**（GitHub 沒有授權檔，GitLab API 這次沒查，收錄前要補） | GitHub 鏡像 2022-03-03 | `aravindev/inkscape_mcp`（GUI 與 CLI 兩種模式，106★） | MIT | 11-16 | svg | 高，Ubuntu 有 `inkscape`，Inkscape 1.x 也有 `--actions` 命令列可對照 |
| 3 | GIMP（`GNOME/gimp`，唯讀鏡像） | GPL（repo 的 LICENSE 寫 GPL，GitHub 判 NOASSERTION） | 2026-11-22 | `gimp-mcp/gimp-mcp`（303★）；內建 Script-Fu／`gimp -i -b` 批次模式 | GPL-3.0 | 11-21 | png（目前已支援）、xcf（待補檢查） | 中。MCP 要連到執行中的 GIMP 外掛，啟動順序要另外編排 |
| 4 | Blender（`blender/blender`，官方鏡像） | GPL-2.0（COPYING 指向 `doc/license/GPL-license.txt`，GitHub 判 NOASSERTION） | 2026-11-22 | `ahujasid/blender-mcp`（現名 `mcp-for-blender`，35k★）；內建 `blender -b --python` | MIT | 11-18 | .blend（待補 `BLENDER` 檔頭檢查）、匯出 glTF／png | 中。Xvfb 下要軟體算圖（llvmpipe），啟動慢。目錄已有 Blender MCP 的 function 紀錄 |
| 5 | Shotcut（`mltframework/shotcut`） | GPL-3.0 | 2026-11-21 | `matrodrigs/shotcut-mcp`（編輯、驗證、算圖 .mlt 專案，29★） | MIT | 11-03 | .mlt（XML，可沿用 XML 解析檢查） | 中高。專案檔是 XML，檢查容易；GUI 操作時間軸比文書軟體難 |
| 6 | Kdenlive（`KDE/kdenlive`） | GPL-3.0 | 2026-11-22 | `mhbxyz/kdenlive-mcp`（6★）或 `AMMIROSOH/Kdenlive-mcp`（headless，19★）。`D-Ogi/mcp-kdenlive`（51★）沒有授權檔，不收 | MIT、Apache-2.0 | 11-16、09-21 | .kdenlive（XML） | 中。KDE 套件依賴多，映像會變大 |
| 7 | Krita（`KDE/krita`） | GPL-3.0 | 2026-11-22 | `SanSaSane/krita-mcp`（16★）或 `nanayax3/krita-mcp`（56★） | CC0-1.0、MIT | 10-23、02-26 | .kra（zip＋`maindoc.xml`，可沿用 zip／XML 檢查）、png | 中。MCP 走 Krita 的 Python 外掛，要先裝外掛再開 GUI |
| 8 | Zotero（`zotero/zotero`） | AGPL-3.0（COPYING 明寫，GitHub 判 NOASSERTION） | 2026-11-22 | `54yyyu/zotero-mcp`（6k★） | MIT | 11-19 | 本機 SQLite 書庫、匯出 BibTeX／RIS | 低。產物是書庫不是單一檔案，round trip 要改成「MCP 寫入 → GUI 修改 → MCP 讀回」，留到 v2 |

另外看過但這一版不列的：

- **darktable**（GPL-3.0，11-22）＋ `w1ne/darktable-mcp`（MIT，10-02）：產物是 .xmp 側檔，可以做，但 RAW 範例檔要先找授權乾淨的。
- **OBS Studio**（GPL-2.0）＋ `royshil/obs-mcp`（GPL-2.0，169★）：介面最後推送是 2025-08-26，已經一年多。OBS 的價值在錄影與直播，不是編輯一個檔案，比較接近 A 賽道的服務型工具。
- **Scribus**（GPL-2.0-or-later，COPYING 明寫）：沒找到 MCP，只有內建 Python 腳本介面，之後可以用腳本當上游。
- **Typst**（Apache-2.0）＋ `johannesbrandenburger/typst-mcp`（MIT）：Typst 沒有 GUI，屬於 A 賽道。
- **Xournal++**（GPL-2.0）：沒找到 MCP。
- **Word／PowerPoint MCP**（`GongRzhe/Office-Word-MCP-Server`、`Office-PowerPoint-MCP-Server`，MIT）：兩個 repo 都已封存，不當上游。

## 每組的驗證步驟設計

**1. LibreOffice ＋ office MCP**：MCP 建一份 xlsx（A1 寫 `{nonce}`、B1 寫數字），存到 `~/work/book.xlsx`。GUI 用 Calc 開 `~/pickfit-in/book.xlsx`，在 A2 打 `edited-{nonce}`，用 ctrl+s 存成 xlsx（遇到「保留目前格式」對話框就選保留）。檢查：`format=xlsx`、contains `edited-{nonce}`、sha256 有變。docx（Writer 加一段字）、pptx（Impress 改投影片文字）照同樣的方式做。

**2. Inkscape ＋ inkscape_mcp**：MCP 畫一個矩形和一段文字 `{nonce}`，存成 svg。GUI 用 Inkscape 開檔，改文字或加一個圓，存成 Inkscape SVG。檢查：`format=svg`（要能解析，根元素是 `<svg>`），contains 新加的字。

**3. GIMP ＋ gimp-mcp**：MCP 開新圖、畫一塊色、匯出 png。GUI 開 png，套一個濾鏡（例如反相），匯出覆蓋原檔。檢查：`format=png`、sha256 有變。像素有沒有真的改要另外比，P3-01 第二步再補。

**4. Blender ＋ blender-mcp**：MCP 在預設場景加一個名為 `{nonce}` 的物件，存 .blend。GUI 開檔、移動物件、存檔。檢查：要先補 `blend` 格式（`BLENDER` 檔頭），物件名稱在檔案裡是明文，可以用 contains 找。

**5. Shotcut ＋ shotcut-mcp**：MCP 建一個有一段 color clip 的 .mlt，clip 標題放 `{nonce}`。GUI 開專案，把 clip 剪短，存檔。檢查：XML 能解析，`out` 屬性有變，contains `{nonce}`。

**6. Kdenlive ＋ kdenlive-mcp**：做法和 Shotcut 相同，專案檔是 .kdenlive。

**7. Krita ＋ krita-mcp**：MCP 開新畫布、畫一筆、存 .kra。GUI 開檔、加一個圖層，圖層名稱設 `{nonce}`，存檔。檢查：zip 完整、`maindoc.xml` 能解析，contains 圖層名稱。

**8. Zotero ＋ zotero-mcp**：v2 再設計，見上表。

## 建議的試做順序

P3-01 要先挑 2–3 組。照「授權清楚、Linux 套件現成、格式檢查已經寫好」排：

1. **LibreOffice ＋ excel-mcp-server／mcp-ms-office-documents**：docx／pptx／xlsx 檢查和範例檔這次都補了。
2. **Inkscape ＋ inkscape_mcp**：svg 檢查已經有了。收錄前要先在 GitLab 補查 Inkscape 的授權。
3. **Krita ＋ krita-mcp** 或 **Shotcut ＋ shotcut-mcp**：兩者都沿用 zip／XML 檢查，只要在 `FORMATS` 加 `kra`／`mlt`。Blender 要先補 `.blend` 檔頭檢查，排在後面。

每組實測前都要再查一次授權與最後推送時間，因為這份清單的資料只代表 2026-11-22 當天的狀態。
