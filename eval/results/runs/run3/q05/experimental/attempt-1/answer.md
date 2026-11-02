# 建議：用 **Docling**，PDF 和 Word 都能轉

我假設這台是一般的 x86_64 Linux，有 Python 3.10 以上，而且大部分規格書是文字型 PDF，不是掃描檔。

## 主推：Docling（IBM 開源，MIT 授權，免費）

**為什麼適合你：**
- 一個 CLI 就能處理 **PDF 和 DOCX**（也支援 PPTX、XLSX、HTML），輸出 Markdown
- **表格**：內建 TableFormer 表格結構模型。預設 `--table-mode accurate`，會把 PDF 表格還原成 Markdown 表格，合併儲存格也會盡量處理
- **標題層級**：用版面分析模型判斷標題、段落、清單、頁首和頁尾，不是單純抽文字
- **完全在本機跑**：第一次要下載模型，之後可以設成完全離線。文件不會上傳
- **只用 CPU 也能跑**：有 `--device cpu`。速度大約每頁 1 到數秒，要看 CPU 和頁面複雜度
- 免費，沒有訂閱

**缺點：**
- 第一次安裝比 pandoc 大很多：PyTorch 加上模型，大約 1–2 GB
- 遇到很複雜的表格（跨頁、巢狀）偶爾還是要手動修
- 掃描型的中文 PDF 要另外設 OCR 語言（下面有說明）

### 安裝步驟

建議裝 CPU 版 PyTorch，可以省掉好幾 GB 的 CUDA 套件：

```bash
# 1. 用 pipx 安裝成獨立 CLI（沒有 pipx 的話：sudo apt install pipx && pipx ensurepath）
pipx install docling --pip-args="--extra-index-url https://download.pytorch.org/whl/cpu"

# 2. 先把模型下載到本機（只有這一步需要網路）
docling-tools models download
#    預設存在 ~/.cache/docling/models
#    如果公司電腦完全不能連網：在別台機器跑這一步，再把整個資料夾複製過來
```

### 第一次使用

```bash
# 確認安裝成功
docling --help

# 轉一份 PDF 規格書（文字型 PDF 關掉 OCR，比較快也比較準）
docling convert spec.pdf --to md --output ./md_out --device cpu --no-ocr

# 轉 Word 檔
docling convert manual.docx --to md --output ./md_out

# 強制離線執行，確認不會連網
HF_HUB_OFFLINE=1 docling convert spec.pdf --to md --output ./md_out \
  --device cpu --artifacts-path ~/.cache/docling/models
```

轉完後打開 `./md_out/spec.md`，檢查兩件事：表格是不是 `| ... |` 格式，`#`／`##`／`###` 的層級對不對得上原文。

**小技巧：**
- 掃描型 PDF 要去掉 `--no-ocr`。中文文件記得在 OCR 設定裡指定繁體中文，詳細參數用 `docling convert --help` 查。我沒有實際測過中文 OCR 的效果，建議先拿一份試試看
- 要批次轉換的話，`docling convert` 可以直接給一個資料夾路徑

## 備選

| 工具 | 優點 | 要注意的地方 |
|---|---|---|
| **MinerU** | 對中文 PDF 和表格的效果也很好，有純 CPU 模式 | AGPL 授權。Word 檔支援比較弱，可能還是要搭配 pandoc |
| **Marker** | PDF 轉 Markdown 品質高 | 程式碼是 GPL，**模型權重對營收較高的公司有商用限制**，公司使用前要先確認授權。只用 CPU 時很慢 |
| **MarkItDown**（Microsoft） | 很輕量，安裝很快 | PDF 基本上只抽純文字，**表格和標題通常保不住**，不符合你的需求 |
| **繼續用 pandoc 處理 DOCX** | pandoc 轉 Word 本來就很準 | 可以只拿 Docling 處理 PDF，兩個一起用 |

## 說明

我先用 pickfit 這個工具查過，它在已經實測的工具清單裡沒找到合適的，只順帶提了 MarkItDown，但也沒有驗證過。上面的 Docling 建議和 CLI 參數是根據 Docling 官方文件（docling-project.github.io）整理的。依你的要求，我沒有在這台電腦上執行或安裝任何東西，所以上面的步驟沒有在你的環境測過。建議先拿一兩份有代表性的規格書試轉，看表格和標題的品質，再決定要不要全面改用。

**來源：**
- [Docling CLI reference](https://docling-project.github.io/docling/reference/cli/)
- [Docling usage](https://docling-project.github.io/docling/usage/)