## 主要推薦：Docling（IBM 開源，MIT 授權）

Docling 能在純 CPU 的本機執行，PDF 與 DOCX 都支援，表格會輸出成 Markdown 表格，標題也會依版面判斷層級。免費，沒有訂閱，也不需要 GPU。它還能直接讀 `.docx`，所以 pandoc 不一定還需要。

**假設：** 你描述的是 Linux 終端機。這台機器的環境資訊顯示是 macOS，指令在兩者上基本相同，只有安裝 Python 的方式可能不同。

### 安裝

需要 Python 3.10 以上（建議 3.11 或 3.12）。

```bash
python3 -m venv ~/venvs/docling
source ~/venvs/docling/bin/activate
pip install docling
docling --help        # 確認安裝成功，並查看目前版本的參數
```

### 第一次執行

```bash
# PDF 轉 Markdown
docling spec.pdf --to md --output ./md

# Word 轉 Markdown
docling spec.docx --to md --output ./md

# 圖片不另存成檔案，只留佔位文字，方便餵給 AI
docling spec.pdf --to md --image-export-mode placeholder --output ./md
```

第一次執行會從 Hugging Face 下載版面分析與表格辨識模型（數百 MB），之後就不需要網路。

### 公司內網／離線機器的做法

1. 在一台可連網的機器上執行 `docling-tools models download`，把模型下載下來。
2. 把模型目錄複製到離線機器。
3. 在離線機器設定環境變數 `DOCLING_ARTIFACTS_PATH` 指向該目錄，再執行轉換。

模型路徑與指令細節可能因版本不同而有差異，以 `docling --help` 和官方文件為準。轉換過程本身不會把檔案送到外部。

### 效果檢查建議

- **表格：** 合併儲存格或跨頁的表格可能會跑版，轉完後抽查幾張。
- **標題：** 層級判斷大致可靠，但深層標題可能不準。
- **掃描版 PDF：** 沒有文字層的 PDF 需要 OCR。Docling 有 OCR 選項，但在 CPU 上會明顯變慢。
- **速度：** 在 CPU 上，數十頁的規格書通常要幾分鐘，我沒有實測，請以你的機器為準。

## 其他候選

| 工具 | 授權／費用 | 優點 | 缺點 |
|---|---|---|---|
| **Docling**（推薦） | MIT，免費 | 表格與標題結構好，CPU 可跑，PDF＋DOCX 都支援 | 首次要下載模型，CPU 較慢 |
| Marker | 程式碼 GPL-3；模型權重有營收限制條款 | 輸出品質好 | 商用條款較複雜，CPU 也慢 |
| MinerU | AGPL-3，免費 | 功能完整 | 安裝較重，AGPL 對內部使用通常沒問題，但要看公司規定 |
| pymupdf4llm | AGPL-3，或付費商業授權（買斷） | 很快，依賴少 | 複雜表格較弱；如果公司不能接受 AGPL，要買商業授權 |
| pdftotext（poppler） | 免費 | 極快 | 不會輸出表格或標題結構，只適合純文字 |

如果你的規格書多半有文字層、表格不複雜，pymupdf4llm 也可以考慮；若重視表格與標題，選 Docling。

Sources: 未使用網路搜尋；以上為依既有知識整理的建議，指令與版本細節請對照官方文件（github.com/docling-project/docling）確認。