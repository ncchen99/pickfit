## 推薦：**Docling**（IBM 開源，MIT 授權，免費）

先說清楚：我用 pickfit 查過，它實際測試過的工具裡沒有符合你需求的，所以以下是我自己的推薦。pickfit 沒有幫我安裝驗證過。CLI 參數是我對照 Docling 官方 CLI 文件確認的。我也沒有在你的機器上執行任何指令。

**為什麼選它：**
- **一個指令就能處理 PDF 和 DOCX**，直接取代 pandoc 這一段，不用 PDF、Word 各用一套工具。
- **表格會保留成表格**：內建 TableFormer 表格結構模型，預設用 `accurate` 模式，輸出 Markdown 表格。合併儲存格這類複雜表格也比一般純文字抽取好很多。
- **標題層級**：會用版面分析模型判斷標題、段落、清單、頁首頁尾，頁首頁尾會被去掉。DOCX 則直接讀 Word 的樣式。
- **完全在本機跑，不需要 GPU**：模型下載一次後就能離線使用，可以指定 `--device cpu`。
- 免費，不是訂閱制，公司內商用也沒有授權問題。

**限制（請先知道）：**
- 只用 CPU 時，PDF 大約每頁 1–數秒，依 CPU 而定。開了 OCR 會更慢。上百頁的規格書要等一下。
- 掃描版 PDF 需要 OCR，中文的辨識品質要另外測。文字型 PDF 建議關掉 OCR（`--no-ocr`），速度快很多。
- PDF 的標題層級有時會被壓平，例如 H2、H3 都變成 `##`。這是 PDF 本身沒有結構資訊造成的，每套工具都有這個問題，Docling 算是比較好的。
- 安裝會連帶裝 PyTorch，佔幾 GB 空間。

---

## 安裝（Linux，只用 CPU）

假設你有 Python 3.10 以上。建議用獨立的虛擬環境，並安裝 CPU 版的 PyTorch，可以省掉好幾 GB 的 CUDA 套件：

```bash
python3 -m venv ~/docling-env
source ~/docling-env/bin/activate
pip install --upgrade pip
pip install docling --extra-index-url https://download.pytorch.org/whl/cpu
```

如果你習慣用 `pipx` 或 `uv`，也可以用 `uv tool install docling`，不過這樣可能會裝到含 CUDA 的 torch。

### 預先下載模型，之後完全離線

```bash
docling-tools models download        # 下載到 ~/.cache/docling/models
export HF_HUB_OFFLINE=1               # 之後禁止連網抓模型（可寫進 ~/.bashrc）
```

如果公司電腦完全不能上網，可以在另一台機器下載模型後複製過來，執行時加上 `--artifacts-path /路徑/models`。

## 第一次執行

```bash
# 文字型 PDF 規格書 → Markdown（關 OCR、用 CPU、表格高精度）
docling spec.pdf --to md --no-ocr --device cpu --table-mode accurate --output ./md

# Word 檔
docling design.docx --to md --output ./md

# 整個資料夾批次轉（PDF 與 DOCX 混在一起也行）
docling ./specs/ --from pdf --from docx --to md --no-ocr --device cpu --num-threads 8 --output ./md
```

如果是掃描版 PDF，把 `--no-ocr` 拿掉就會開啟 OCR。

**驗證建議**：先挑一份表格最複雜的規格書來轉，打開 `./md/spec.md`，確認兩件事：表格是不是 `| ... |` 格式，`#`/`##` 的層級是不是跟原文目錄一致。

---

## 備選

- **Marker**（`pip install marker-pdf`）：PDF 轉 Markdown 的品質也很好，加裝 extras 後也支援 DOCX。但只用 CPU 時明顯比 Docling 慢，而且程式碼是 GPL、模型權重另有商用授權條件，公司使用前要先確認。
- **MarkItDown**（Microsoft，`pip install 'markitdown[all]'`）：輕量快速，DOCX 轉得不錯。但 PDF 只做純文字抽取，**表格和標題基本上會不見**，不符合你的需求，只適合拿來處理 Word。
- 實務上的組合：**Word 繼續用 pandoc，PDF 用 Docling** 也完全可行。pandoc 處理 DOCX 的標題和表格本來就很穩定。