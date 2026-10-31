# q05 測試資料：PDF 與 Word 轉 Markdown

題目在 [../../questions.yaml](../../questions.yaml) 的 q05。這裡放 q05 各 [L2] 項目用到的測試資料、檢查腳本與評分步驟。評分規則以 [../../README.md](../../README.md) 第 5 節與第 9.1 節為準；本文只把 q05 的檢查寫成可以照做的步驟。

所有檔案都是為這題自己寫的合成資料，內容是一份虛構的「智慧溫控器規格書」，和任何轉檔工具無關。腳本只用 Python 3.8 以上的標準函式庫，固定輸出（同樣的輸入產生同樣的位元組）。

## 1. 檔案

| 檔案 | 用途 | 怎麼來 |
|---|---|---|
| `content.json` | 兩份測試文件的標準內容（依閱讀順序） | 手寫 |
| `fixture.docx` | Word 測試檔（4.6 KB） | `python3 make_docx.py`，已 commit |
| `fixture.pdf` | PDF 測試檔（約 50–100 KB） | `python3 make_pdf.py --font …`，**等念誠決定字型後產生再 commit**（見 `needs.json`） |
| `make_docx.py`、`make_pdf.py` | 產生上面兩個檔 | 手寫 |
| `verify_fixtures.py` | 確認兩個檔的內容與 `content.json` 一致 | 手寫 |
| `check_md.py` | **凍結的比對腳本**：檢查一份轉出來的 `.md` | 手寫 |
| `test_check_md.py` | `check_md.py` 的自我測試（20 個合成案例） | 手寫 |
| `egress_run.py` | 斷網、記錄連線、計時、逾時的執行包裝（q05、q06、q07 三份相同） | 手寫 |
| `needs.json` | 需要外部素材、等念誠決定的項目 | — |
| `calibration.md` | 第一次開跑前要跑的校正步驟與紀錄表（待填） | — |

### 測試文件的內容

兩份文件內容相同（`content.json`）：

- 1 個一級標題、2 個二級標題；
- 3 段內文，每段都是繁體中文加英文；
- 1 個 4 欄表格：1 列表頭加 2 列資料，共 12 格，每格都只有一行字；
- 1 個 3 項的項目符號清單。

漢字共 144 個，其中多數是繁簡不同的字（例如「體」「規」「書」「說」「溫」「設」），轉成簡體會被抓到。

**fixture.docx**：標題用 Word 內建的 heading 1／heading 2 樣式（大綱層級 0、1）；表格是真的 Word 表格，第一列標成表頭列；清單用項目符號編號定義（numPr）。文件屬性沒有標題，避免轉檔工具多加一個標題。

**fixture.pdf**：A4 一頁、文字型 PDF。所有字都是嵌入的 TrueType 子集字型（Type0／CIDFontType2，Identity-H）畫出來的真文字，附 ToUnicode 對照表，文字層可以還原成 Unicode。標題字比內文大、用粗體；表格有框線、表頭列有底色；清單用項目符號字元加懸掛縮排。PDF **沒有標籤（tagged PDF）、沒有書籤、沒有 /Title**，結構只能從頁面本身判斷。

## 2. 開跑前要做的事（測試資料凍結）

1. 念誠依 `needs.json` 決定字型，下載後記下來源與 sha256（字型檔**不 commit**）。
2. 產生 PDF 並檢查：

   ```sh
   python3 make_pdf.py --font <Regular.ttf> --bold-font <Bold.ttf>   # 只有一個字重時省略 --bold-font
   python3 verify_fixtures.py        # 兩個檔都要 OK
   python3 test_check_md.py          # 20/20
   ```

   `make_pdf.py` 只接受 TrueType 外框（有 `glyf` 表）的字型；CFF 外框的 `.otf` 會被拒絕。可變字型只會嵌入預設字重，會印出警告，盡量用靜態的 Regular／Bold 檔。
3. 打開 PDF 看一眼：字形正常（不是方框）、標題明顯較大較粗、表格有框線。
4. 照 `calibration.md` 在評分用的 image 裡跑一次校正，填好紀錄。
5. commit `fixture.pdf` 與填好的 `calibration.md`。之後不再改這個資料夾（第 3 節的勘誤規則除外）。

## 3. 評分環境

- Modal Sandbox，x86_64，**4 vCPU、16 GB 記憶體、沒有 GPU**；image 是第 5 節的開發 image（以 `ubuntu:24.04` 為底）加上評分工具 `python3` 與 `strace`（見 `needs.json`）。記下 image digest。兩組用同一個 image。
- 以 root 執行（斷網要用到建立網路命名空間的權限）。
- 目錄約定：
  - `/work/in/`：只放 `fixture.pdf`、`fixture.docx`；
  - `/work/out/`：轉出的 `.md` 與各種紀錄；
  - `/opt/eval-q05/`：本資料夾的腳本。
- 安裝 20 分鐘逾時，每個檢查 10 分鐘逾時（第 5 節）。

## 4. 名詞

- **照步驟原樣（verbatim）**：答案裡的指令逐字複製執行。只允許第 5 節列的調整：填入版本號與佔位字（這題就是輸入、輸出檔的路徑）、接受安裝程式的預設值；Ubuntu 擋下裸 `pip install` 時改在 venv 裡跑，記 `needed_venv`，但「照步驟原樣成功」那一項不過。不可以修正錯的指令或旗標、補上缺的步驟、換掉答案指定的模型。答案的指令只把 Markdown 印到標準輸出時，用 `egress_run.py --stdout` 存成檔案，這不算改指令。
- **斷網（egress blocked）**：`egress_run.py --block-network` 讓指令在一個新的網路命名空間裡執行，裡面只有已啟用的 loopback（`lo`），連不到機器外面，DNS 也查不到。腳本會確認命名空間裡只有 `lo`，否則中止（exit 125）。
- **egress 檢查**：同一次執行用 `strace -f` 記下指令與所有子程序的 `connect`、`sendto`、`sendmsg`、`sendmmsg`。下列任一種都算一次對外連線嘗試，**連線失敗也算**：
  - 目的地不是 loopback（`127.0.0.0/8`、`::1`、對應到 127.x 的 IPv6、`0.0.0.0`）；
  - 任何 DNS 類埠（53、853、5353、5355），即使在 loopback 上（代表查了網域名稱）；
  - 送往系統解析服務的 UNIX socket（`/run/systemd/resolve…`、nscd）；
  - AF_PACKET 原始封包。

  嘗試次數為 0 才算通過（報告裡 `egress.verdict` 是 `pass`）。紀錄檔（`.strace`）與報告一起保存當證據。

## 5. 各 [L2] 項目

每個答案（對照組、實驗組各一份）都在**全新的 sandbox** 裡從頭做一次。

### L2-1

> [L2] The install steps succeed verbatim in the dev image (x86_64, CPU only, 4 vCPU and 16 GB); any model downloads happen during setup

- **用到**：只有乾淨的開發 image，不用測試檔。
- **做法**：網路開著，照答案的安裝與設定步驟逐條執行，每條記下指令、exit code、輸出（`egress_run.py --report /work/out/install-NN.json -- <指令>`，不加 `--block-network`；這一步的 egress 結果不評分，只留紀錄）。答案自己寫的「先下載模型」「先執行一次讓它下載模型」等步驟屬於設定，照做；答案沒寫的，評分者**不可以**替它先跑一次暖機。
- **判定**：
  - 每條步驟都成功（exit 0，或答案說明的成功狀態）才過；
  - 「模型下載在設定時完成」由 L2-2 的斷網轉換檢驗：斷網轉換時因為要下載模型或其他資料而失敗，或 egress 紀錄顯示它想連外下載，本項也記不過。

### L2-2

> [L2] Frozen fixtures: a text-based PDF (CJK font embedded) and a DOCX with the same content: Traditional Chinese and English text, one H1, two H2s, a 4-column table with a header row and 2 data rows (12 cells), and a bullet list. With egress blocked, each converts to a .md file in which the headings are ATX headings at the right levels, the table is a Markdown pipe table whose 12 cell texts match the fixture, and the list items are Markdown list items

- **用到**：`fixture.pdf`、`fixture.docx`、`content.json`、`check_md.py`、`egress_run.py`。
- **做法**：兩個檔各轉一次，輸入、輸出換成下面的路徑，其餘照答案：

  ```sh
  cd /work
  python3 /opt/eval-q05/egress_run.py --block-network --timeout 600 \
      --report /work/out/pdf.run.json -- <答案的轉換指令：輸入 /work/in/fixture.pdf，輸出 /work/out/fixture_pdf.md>
  python3 /opt/eval-q05/check_md.py /work/out/fixture_pdf.md --report /work/out/pdf.check.json

  python3 /opt/eval-q05/egress_run.py --block-network --timeout 600 \
      --report /work/out/docx.run.json -- <答案的轉換指令：輸入 /work/in/fixture.docx，輸出 /work/out/fixture_docx.md>
  python3 /opt/eval-q05/check_md.py /work/out/fixture_docx.md --report /work/out/docx.check.json
  ```

  - 答案的轉換要先啟動本機服務、再送檔案時，整段用 `sh -c '…'` 包在同一次 `egress_run.py` 裡，讓服務和轉換在同一個斷網環境。
  - 工具輸出一個資料夾（含圖片等）時，取其中對應輸入檔的那一個 `.md`；有多個 `.md` 時取主檔，記下選了哪個。
  - PDF 和 DOCX 必須用**同一個工具**轉（題目要求一個工具處理兩種格式）；答案對兩種格式給不同指令時照答案。
- **判定**（`check_md.py` 報告裡的 `structure.pass`，兩個檔都要 `true` 才過）：
  - 3 個標題都是 ATX 標題（行首 `#`、`##`），層級和測試文件相同（一級標題是 `#`、二級標題是 `##`，整體位移也不過）；setext 標題（`===`、`---` 底線）和 HTML `<h1>` 不算；
  - 測試文件的內文、表格儲存格、清單項目沒有被變成 ATX 標題（工具自己加的、文件裡沒有的字，例如頁碼，不算違規）；
  - 有一個 Markdown 管線表格（表頭列、分隔列、資料列；HTML `<table>` 不算）剛好 4 欄，表頭列等於測試文件的表頭，資料列（全部空白的列不計）剛好是那 2 列、順序相同；
  - 3 個清單項目都是 Markdown 清單項目（行首 `-`、`*`、`+` 或 `1.`、`1)`），可以折行。
  - 文字比對方式：Unicode NFKC、去掉所有空白、去掉 Markdown 的強調與程式碼記號（`*`、`_`、`` ` ``）、反斜線跳脫與 `<br>`；清單項目開頭殘留的項目符號字元（例如 `- • 文字`）忽略。**字本身要完全相同**，簡體字不算對。
- 兩個檔的 `.run.json` 要記到報告：exit code、時間、egress 結果也給 L2-4、L2-5 用。轉換失敗（非 0、沒有產生 `.md`）時，該檔的 L2-2、L2-3 都不過。

### L2-3

> [L2] A frozen diff script finds at least 98% of the fixture's CJK characters, in order, in each output, with no replacement characters

- **用到**：L2-2 轉出的兩個 `.md`、`check_md.py`（凍結的比對腳本）、`content.json`。
- **做法**：同 L2-2 的 `check_md.py` 報告，看 `cjk` 部分。
- **判定**（兩個檔都要 `cjk.pass` 為 `true`）：
  - 測試文件的「CJK 字」= 所有區塊依閱讀順序（表格逐列）的漢字（U+3400–4DBF、U+4E00–9FFF、U+F900–FAFF、U+20000–3FFFF），共 144 個；標點不算；
  - 「依序找到的比例」= 這串字與輸出檔全文漢字的最長共同子序列長度 ÷ 144，要 **≥ 0.98**（最多漏或錯 2 個字）；
  - 「替代字元」= U+FFFD，或 `(cid:數字)` 這種無法對應的字形佔位字；要 **0 個**。私用區字元只記錄，不判定。

### L2-4

> [L2] Each conversion finishes within 10 minutes

- **用到**：L2-2 的 `pdf.run.json`、`docx.run.json`。
- **判定**：兩次轉換都 exit 0、產生了 `.md`，而且 `duration_s ≤ 600`、`timed_out` 為 `false`，才過。`egress_run.py --timeout 600` 到時會砍掉整個程序群組（報告記 exit 124）。

### L2-5

> [L2] Egress check passes during the conversions

- **用到**：L2-2 的兩份 `.run.json` 與 `.strace` 紀錄。
- **判定**：兩次轉換的 `egress.verdict` 都是 `pass`（對外連線嘗試 0 次，定義見第 4 節），而且 `netns.ok` 為 `true`，才過。有嘗試時，把報告裡列出的紀錄行附在評分紀錄。

## 6. 自我測試（不是校正）

在任何有 Python 3 的機器上：

```sh
python3 test_check_md.py      # check_md.py 對 20 個合成案例的判定都符合預期
python3 egress_run.py --selftest
python3 verify_fixtures.py    # fixture.pdf 產生之前，pdf 會顯示 MISSING
```

2026-10-30 在 macOS 上用本機字型產生過暫時的 PDF（只在暫存目錄、不 commit），用 macOS 內建的 PDFKit 取出文字層，內容與 `content.json` 完全一致；`verify_fixtures.py` 也通過。斷網與 strace 只能在 Linux 上測，放在 `calibration.md`。
