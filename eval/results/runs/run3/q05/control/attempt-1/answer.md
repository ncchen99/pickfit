## 推薦：Docling（IBM 開源，MIT 授權，免費）

Docling 最符合你的條件：

- **PDF 和 Word 都能轉**：一個 CLI 可以處理 PDF、DOCX、PPTX、XLSX、HTML 和圖片，輸出 Markdown。
- **表格會保留**：它用 TableFormer 模型辨識 PDF 表格的結構，輸出 Markdown 表格。合併儲存格和跨頁表格也比一般純文字抽取工具處理得好。
- **完全在本機跑**：模型下載一次後就可以離線使用，文件不會上傳。
- **只用 CPU 也能跑**：不需要 GPU，只是比較慢。一般文字型 PDF 大約每頁 1 到數秒，依機器而定。
- **MIT 授權**：公司內部商用沒有問題，也不需要訂閱。

**標題層級要先講清楚**：DOCX 的標題層級由 Word 樣式決定，所以會正確（Heading 1 → `#`、Heading 2 → `##`）。PDF 本身沒有「標題層級」這種資訊，Docling 能認出哪些是標題，但匯出 Markdown 時常常會把所有標題都輸出成同一層（`##`）。這是我知道的已知限制，不確定最新版是否已經改善。如果規格書的章節有編號（例如 1、1.1、1.1.2），AI 通常還是讀得懂層級。如果一定要正確的 `#` 層級，可以：
1. 寫個小腳本，依章節編號的點數重新調整 `#` 的數量（最簡單也最可靠）。
2. 或者改試下面的替代方案 Marker，它在 PDF 標題層級上通常表現較好。

---

## 安裝步驟（Linux，以下指令我都沒有執行過）

假設：Python 3.10 以上，可以連網下載一次套件和模型（之後就可以離線）。

```bash
# 1. 建一個獨立的虛擬環境
python3 -m venv ~/docling-env
source ~/docling-env/bin/activate

# 2. 安裝 CPU 版 PyTorch，避免下載好幾 GB 的 CUDA 套件
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 3. 安裝 Docling
pip install docling

# 4. 先把模型下載到本機（之後就可以完全離線）
docling-tools models download -o ~/docling-models
```

## 第一次執行

```bash
source ~/docling-env/bin/activate

# PDF 轉 Markdown（文字型 PDF，不做 OCR，比較快）
docling spec.pdf --to md --output out/ --no-ocr \
  --artifacts-path ~/docling-models

# 表格比較複雜時，改用精確表格模式
docling spec.pdf --to md --output out/ --no-ocr \
  --table-mode accurate --artifacts-path ~/docling-models

# Word 也一樣
docling spec.docx --to md --output out/

# 整個資料夾一起轉
docling ./specs/ --to md --output out/ --artifacts-path ~/docling-models
```

補充說明：
- 如果 PDF 是**掃描檔**，就把 `--no-ocr` 拿掉，讓它跑 OCR。中文掃描檔的 OCR 品質要實際測過才知道，速度也會慢很多。
- 想確認它真的不連外網，可以先 `export HF_HUB_OFFLINE=1` 再執行。
- 可以先用 `docling --help` 確認你裝到的版本支援哪些參數，因為選項名稱在不同版本間可能會變。
- 預設的 standard pipeline 就適合純 CPU 使用。不要選 VLM pipeline（例如 granite_docling），它在 CPU 上會非常慢。

---

## 替代方案

| 工具 | 優點 | 缺點 |
|---|---|---|
| **Marker** | PDF 標題層級和表格品質都很好 | 程式碼是 GPL，模型權重有商用限制（公司營收超過一定門檻要付費授權），使用前要先讀授權條款；CPU 上比 Docling 慢 |
| **MinerU** | 中文 PDF 和複雜版面很強 | AGPL 授權；設定比較重，CPU 模式很慢 |
| **MarkItDown**（Microsoft） | 很輕量、安裝簡單 | PDF 只抽純文字，表格和標題結構基本上會流失，不符合你的需求 |
| **pandoc**（繼續用） | DOCX 的標題層級很準 | 不能讀 PDF |

**實務建議**：DOCX 如果你覺得 pandoc 已經夠好，可以繼續用 pandoc，PDF 就交給 Docling。建議先挑 2 到 3 份表格最複雜的規格書試轉，確認表格和標題的品質可以接受，再整批處理。

Sources:
- [Docling CLI reference](https://docling-project.github.io/docling/reference/cli)
- [Docling v2 docs](https://docling-project.github.io/docling/v2/)
- [Docling paper (arXiv)](https://arxiv.org/html/2501.17887v1)
- [docline on PyPI](https://pypi.org/project/docline/)