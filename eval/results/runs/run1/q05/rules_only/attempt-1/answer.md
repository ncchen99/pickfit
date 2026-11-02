# 建議：用 **Docling**（IBM 開源，MIT 授權，免費）

我的假設：你們的 PDF 規格書大多是由 Word 等軟體直接匯出、可以選取文字的 PDF，不是掃描檔；Linux 上有 Python 3.10 以上。

**選它的原因**
- **PDF 和 Word 一個工具搞定**：同一個指令就能轉 `.pdf` 和 `.docx`，也支援 pptx、xlsx、html。
- **表格**：PDF 表格由內建的 TableFormer 模型辨識，輸出成 Markdown 表格，跨欄、合併儲存格的處理比一般純文字抽取工具好很多。
- **全在本機跑，不用 GPU**：用 CPU 就能跑，速度大約每頁幾秒。文件不會上傳到任何地方。
- **免費、沒有訂閱**：MIT 授權，公司內部使用沒有限制。

**要先知道的限制：PDF 的標題層級**
PDF 本身沒有「標題 1／標題 2」這種結構資訊，Docling 從 PDF 抓到的標題常常全部變成同一層 `##`。Word 檔沒有這個問題，因為它直接讀 Word 的標題樣式，層級會正確。如果你們 PDF 的層級很重要，可以：
1. 試試社群外掛 `docling-hierarchical-pdf`，它會依字體大小和章節編號（例如 1.2.3）重建層級。這是第三方套件，請先自己用幾份文件測過。
2. 或者改用下面替代方案裡的 Marker。

## 安裝（CPU 版）

```bash
# 1. 安裝 pipx（Debian/Ubuntu 範例）
sudo apt install pipx && pipx ensurepath

# 2. 安裝 docling，並指定 CPU 版 PyTorch（可省下好幾 GB 的 CUDA 套件）
pipx install docling --pip-args="--extra-index-url https://download.pytorch.org/whl/cpu"
```

## 第一次使用

```bash
# 3. 先下載模型（只需要一次，下載的是模型檔，不會送出任何文件）
docling-tools models download

# 4. 之後可以強制離線，確定不會連網
export HF_HUB_OFFLINE=1

# 5. 轉 PDF（文字型 PDF 加 --no-ocr 會快很多；表格用精準模式）
docling spec.pdf --to md --no-ocr --table-mode accurate --output out/

# 6. 轉 Word
docling spec.docx --to md --output out/

# 7. 整個資料夾批次轉
docling ./specs/ --to md --no-ocr --output out/
```

先挑 2～3 份表格最複雜的規格書試轉，打開 `out/*.md` 檢查表格和標題。如果有掃描檔，就把 `--no-ocr` 拿掉，讓它跑 OCR。中文 OCR 的語言設定請用 `docling --help` 查看 `--ocr-lang` 和 OCR 引擎選項。

## 替代方案

| 工具 | 適合的情況 | 注意事項 |
|---|---|---|
| **Marker**（`pip install marker-pdf`） | PDF 標題層級比較準 | 只用 CPU 會明顯比較慢。程式碼是 GPL 授權，模型權重對年營收或募資超過 200 萬美元的公司要付費取得商業授權（不是訂閱），請先確認公司規模 |
| **MinerU** | 版面複雜、需要中文 OCR | AGPL 授權，安裝比較重 |
| **Microsoft MarkItDown** | 很輕、安裝快 | PDF 只抽出純文字，表格和標題基本上會丟失，**不符合你的需求** |

Word 檔如果你習慣用 pandoc，也可以繼續用，它轉 docx 的品質本來就很好。只把 PDF 交給 Docling 就行了。

補充：我也查了 pickfit 的已測工具清單，裡面沒有符合這個需求的工具（找到的是 PDF 編輯器和 Anki 卡片產生器），所以以上建議是根據我自己對這些工具的了解，pickfit 沒有實際測試過它們。安裝指令可能會隨版本更新改變，請以 Docling 官方文件為準：https://github.com/docling-project/docling