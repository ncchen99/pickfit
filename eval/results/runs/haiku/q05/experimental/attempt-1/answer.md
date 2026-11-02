## 主要推薦：Docling（IBM 開源，MIT 授權）

Docling 能在本機用 CPU 轉換 PDF 與 Word（.docx）。表格會以 Markdown 表格輸出，標題也會轉成 `#` 層級。文件不會上傳，免費，沒有訂閱。

注意：pickfit 沒有找到完全符合需求的工具，Docling 是我從網路查到的知名工具，pickfit 並未驗證它。我也沒有在這台 Mac 上實際執行過它。

**需要注意的限制：**
- 標題層級不一定完全正確。有一位作者的測試中，40 頁 PDF 只抓到約一半標題，且層級被扁平化成 `###`/`####`。這只是單一測試，但轉換後請抽查標題。
- 第一次執行時，它會從 Hugging Face 下載模型，這一步需要網路。文件本身不會上傳。若要完全離線，請在有網路的時候先下載模型（見下方步驟）。
- CPU 可以跑，但速度較慢。數位原生的 PDF 不需要 OCR，加上 `--no-ocr` 會快很多。

### 安裝步驟（Linux，建議 Python 3.10 以上）

```bash
# 1. 建立獨立的虛擬環境
python3 -m venv ~/.venvs/docling
source ~/.venvs/docling/bin/activate

# 2. 先安裝 CPU 版的 PyTorch，避免下載幾 GB 的 CUDA 版本
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 3. 安裝 Docling
pip install docling

# 4. 預先下載模型（之後離線也能用）
docling-tools models download
```

### 第一次執行

```bash
# PDF 轉 Markdown（數位原生 PDF 建議加 --no-ocr）
docling --to md --no-ocr --output ./out 規格書.pdf

# Word 轉 Markdown
docling --to md --output ./out 說明.docx
```

輸出會在 `./out/` 下。打開 `.md` 檢查表格和標題，確認沒問題後再交給 AI 讀取。

## 備選方案

- **pymupdf4llm**：速度快、表格和標題處理不錯，但授權是 AGPL-3.0，商用需要另外的商業授權，請先確認公司的授權規定。
- **Marker**：品質不錯，但程式碼是 GPL-3.0，模型權重另有使用條款，且 CPU 上很慢。
- **MinerU**：功能強，但是 AGPL-3.0，且依賴較重。

如果你的 PDF 大多是純文字、表格很少，`pdftotext -layout`（poppler-utils）最輕量，但它不會輸出表格與標題結構，所以不符合你的需求。

## 我查證的依據

- [Docling Technical Report（arXiv）](https://arxiv.org/html/2408.09869v1)：說明 Docling 完全在本機執行、CPU 可用、表格用 TableFormer 辨識。
- [Docling 文件解析指南（bestllmfor.com）](https://bestllmfor.com/guides/docling-document-parsing/)：提到 MIT 授權，但模型授權可能另有規定。
- [Docling 標題測試報告（DEV Community）](https://dev.to/felipe_anyformat/pdf-to-markdown-for-llms-o2e)：標題層級問題的來源，只有單一測試。

安裝指令是依照一般 Docling 用法整理的，尚未在目標 Linux 環境實測。版本號與 CLI 參數可能隨版本變動，請以 `docling --help` 為準。