## 推薦：**Docling**（IBM 開源，MIT 授權，免費）

照你的需求，Docling 最合適：

- **PDF 和 Word 都能轉**：PDF、DOCX、PPTX、HTML 等都用同一個 `docling` 指令轉成 Markdown。
- **表格保留成表格**：內建 TableFormer 表格結構模型，PDF 裡的表格會輸出成 Markdown 表格。合併儲存格這類複雜表格可能還是要人工檢查。
- **標題層級正確**：Word 檔會直接讀標題樣式。PDF 要另外加 `--heading-hierarchy` 參數。預設情況下 PDF 的標題全部會變成同一層級，這是常見的問題。開啟後 Docling 會依序參考 PDF 書籤、標題編號（例如「3.2.1」）、字體大小與粗細來判斷層級（[官方說明](https://docling-project.github.io/docling/usage/heading_levels/)）。
- **完全在本機跑**：模型下載一次後就能離線使用，文件不會上傳。
- **不需要 GPU**：CPU 就能跑，但比較慢。我估計一般規格書每頁約 1 到數秒，實際速度要看你的機器。

### 安裝（假設：Linux，已有 Python 3.10 以上）

```bash
# 建議用獨立環境
python3 -m venv ~/docling-env
source ~/docling-env/bin/activate

# 只用 CPU 的話，先裝 CPU 版 PyTorch，可以省下好幾 GB 的 CUDA 套件
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install docling

# 先把模型下載好，之後就能離線使用
docling-tools models download
```

如果公司電腦完全不能連外，可以在可以連網的機器上執行 `docling-tools models download`，把模型目錄（預設在 `~/.cache/docling/models`）複製到公司電腦，轉檔時用 `--artifacts-path` 指定模型位置。另外設定 `export HF_HUB_OFFLINE=1`，確保它不會嘗試連網。

### 第一次使用

```bash
# PDF → Markdown（開啟標題層級判斷）
docling --to md --heading-hierarchy --output ./out spec.pdf

# 文字型 PDF（不是掃描檔）可以關掉 OCR，速度快很多
docling --to md --heading-hierarchy --no-ocr --output ./out spec.pdf

# 表格很複雜時，用較精準（但較慢）的表格模式
docling --to md --heading-hierarchy --table-mode accurate --output ./out spec.pdf

# Word 檔
docling --to md --output ./out spec.docx

# 整個資料夾批次轉換
docling --to md --heading-hierarchy --no-ocr --output ./out ./specs/
```

第一次跑完後，建議挑一份表格最多、章節最深的規格書，打開 `out/spec.md` 檢查兩件事：表格有沒有錯欄，`#`、`##`、`###` 的層級對不對。如果你們的文件章節編號很一致但字體不一致，官方說明建議關掉字體樣式判斷，只看編號，這要透過 Python API 設定 `HeadingHierarchyOptions`。

各參數的確切名稱可能因版本而異，請以 `docling --help` 為準。我沒有在你的機器上實際執行過這些指令。

---

### 其他選擇（如果 Docling 效果不理想）

| 工具 | 優點 | 缺點 |
|---|---|---|
| **pymupdf4llm** | 非常快，不需要 AI 模型，純 CPU 就很快；表格和標題（依字體大小判斷）效果還不錯 | 只能處理 PDF（Word 還是用 pandoc）；AGPL 授權，只在內部使用通常沒問題，但如果要整合進公司產品就要注意 |
| **Marker** | PDF 轉換品質很好，標題層級也不錯 | 用 CPU 跑很慢；GPL 授權，模型權重對商業使用另有營收門檻限制，公司使用前請先確認授權條款 |
| **MarkItDown**（Microsoft） | 輕量，Word 和 PDF 都支援 | PDF 只會抽出純文字，**表格和標題結構基本上會遺失**，不符合你的需求 |
| **MinerU** | 對中文文件和複雜版面處理得很好 | 安裝較重，沒有 GPU 時很慢；AGPL 授權 |

**簡單說**：先試 Docling，PDF 和 Word 用同一套工具處理。如果覺得 CPU 太慢，而且規格書都是文字型 PDF，可以改用 pymupdf4llm 處理 PDF，Word 繼續用 pandoc。以上工具都是免費開源，沒有訂閱費。

Sources:
- [Docling – Heading levels 官方說明](https://docling-project.github.io/docling/usage/heading_levels/)
- [Docling GitHub Discussion #1170（PDF 標題全變成 ## 的問題）](https://github.com/docling-project/docling/discussions/1170)