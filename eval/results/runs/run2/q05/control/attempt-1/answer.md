# 建議：Docling（IBM 開源，MIT 授權，免費）

我建議用 **Docling**。它符合你列的條件：

- **PDF 和 Word 都能轉**：一個 `docling` 指令就能處理 PDF、DOCX，也支援 PPTX、XLSX、HTML 等格式。
- **表格會保留**：它有專門辨識 PDF 表格結構的模型（TableFormer），輸出成 Markdown 表格。多數 PDF 工具只能抽出文字，表格會亂掉，這點是它最大的優勢。
- **完全在本機跑，不用 GPU**：第一次執行會下載模型，之後可以離線使用，CPU 就能跑，只是比較慢，一頁大約 1 到數秒。
- **免費**：MIT 授權，可以商用，沒有訂閱。

我的假設：你們的規格書大多是「文字型 PDF」（文字可以直接選取），不是掃描檔。掃描檔也能轉，但要開 OCR，速度會慢很多。

## 安裝

需要 Python 3.10 以上。建議用 `pipx` 或 venv 安裝，不要裝進系統的 Python：

```bash
# 方法 A：pipx（最乾淨）
sudo apt install pipx        # Debian/Ubuntu；其他發行版請換成對應的套件管理器
pipx install docling

# 方法 B：venv
python3 -m venv ~/docling-env
source ~/docling-env/bin/activate
pip install docling
```

**小提醒**：在沒有 GPU 的機器上，pip 有時會把 CUDA 版的 PyTorch 一起裝進來，多佔好幾 GB。可以先裝 CPU 版 PyTorch 再裝 docling：
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install docling
```

## 第一次執行

```bash
# 1. 先把模型下載好（之後就能離線使用）
docling-tools models download

# 2. 轉一個 PDF（文字型 PDF 可以關掉 OCR，速度會快很多）
docling spec.pdf --to md --no-ocr --table-mode accurate --output ./out

# 3. Word 檔一樣用這個指令
docling spec.docx --to md --output ./out

# 4. 整個資料夾批次轉換
docling ./specs/ --to md --no-ocr --output ./out
```

- 如果電腦完全不能連外網，先在可以上網的機器跑 `docling-tools models download`，把模型目錄（預設在 `~/.cache/docling/models`）複製過去，再加上 `--artifacts-path <模型目錄>`。
- 掃描型 PDF：把 `--no-ocr` 拿掉。中文掃描檔可能要指定 OCR 語言，用 `--ocr-lang`，參數值依 OCR 引擎而定。
- 指令參數可能會隨版本改變，請先跑一次 `docling --help` 確認。我這次只確認了安裝方式和基本用法，`--table-mode`、`--artifacts-path` 這些參數是依我的記憶寫的。

## 要先知道的限制

**PDF 的標題層級**：Docling 找得出哪些文字是標題，但 PDF 本身沒有記錄「這是第幾層標題」，所以它常把所有標題都輸出成 `##`。如果規格書的標題有編號（例如 1、1.1、1.1.1），AI 讀起來通常沒問題。如果一定要 `#`、`##`、`###` 分得正確，可以：
- 自己寫一個小腳本，依編號深度修正 `#` 的數量；或
- 用下面的 Marker 處理這類文件。

Word 檔的標題層級來自文件裡的樣式，所以會是正確的。不過 Word 檔繼續用你熟悉的 pandoc 也完全可以。

## 備選工具

| 工具 | 優點 | 缺點 |
|---|---|---|
| **PyMuPDF4LLM** (`pip install pymupdf4llm`) | 非常快，CPU 不吃力；依字體大小推斷標題層級 | 只處理 PDF；複雜表格（合併儲存格、跨頁）比 Docling 差；AGPL 授權，只在內部使用通常沒問題 |
| **Marker** (`pip install marker-pdf`) | 標題層級和表格品質都很好 | 只用 CPU 很慢；模型權重對營收超過一定規模的公司有商用限制，要另外買授權，使用前請看清楚條款 |
| **MinerU** | 對中文 PDF 和表格的效果好 | 安裝較重；AGPL；只用 CPU 偏慢 |
| **MarkItDown**（Microsoft） | 輕量，支援很多格式 | PDF 只抽出純文字，**表格和標題都會丟失**，不符合你的需求 |

**結論**：先用 Docling 試幾份有代表性的規格書，特別是表格最複雜的那幾份。如果只有標題層級不夠好，再拿那幾份用 Marker 或 PyMuPDF4LLM 比較看看。

Sources:
- [docling-project/docling (GitHub)](https://github.com/docling-project/docling)