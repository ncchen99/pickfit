我推薦用 **Docling**（IBM 開源，MIT 授權，免費）。它是 Python 寫的命令列工具，PDF 和 Word 都能轉成 Markdown。PDF 裡的表格會轉成 Markdown 表格，有 `--heading-hierarchy` 選項來還原標題層級。只用 CPU 就能跑，第一次下載完模型之後就可以完全離線使用。

先說清楚：pickfit 查了 208 個工具，沒有找到它實際測試過、又同時符合你所有條件的。所以下面的建議和指令都是根據我自己的了解和 Docling 官方文件，**pickfit 沒有替它做過安裝測試**。

**我的假設：** 你的 Linux 有 Python 3.10 以上；規格書大多是軟體輸出的 PDF，不是掃描檔。

## 為什麼選 Docling

- **表格：** 用專門的表格辨識模型（TableFormer）找出表格結構，輸出成 Markdown 表格。
- **標題層級：** 這是 Docling 的已知弱點，**一定要加 `--heading-hierarchy`**。不加的話，PDF 裡所有標題都會變成同一層（全部是 `#` 或 `##`）。官方文件說這個功能預設關閉。開啟後它會參考 PDF 的書籤、章節編號（例如 3.2.1）和字體大小來判斷層級。如果規格書有書籤或編號標題，效果通常會比較好。
- **Word：** `.docx` 也能直接轉，所以 PDF 和 Word 可以用同一套流程。原本的 pandoc 也可以繼續用來轉 Word。
- **本機和沒有 GPU：** 模型很小，CPU 就能跑，但每頁要幾秒，大份規格書要多等一下。

## 安裝（Linux）

```bash
# 建一個獨立的虛擬環境
python3 -m venv ~/.venvs/docling
source ~/.venvs/docling/bin/activate

# 只用 CPU 的話，先裝 CPU 版 PyTorch，可以省下好幾 GB 的 CUDA 套件
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install docling

# 先把模型下載到本機，之後就能完全離線使用
docling-tools models download
# 模型預設放在 ~/.cache/docling/models
```

## 第一次使用

```bash
# PDF 轉 Markdown（文字型 PDF 用 --no-ocr 會比較快也比較準）
docling spec.pdf --to md --output ./out --heading-hierarchy --no-ocr --table-mode accurate

# Word 轉 Markdown
docling spec.docx --to md --output ./out

# 整個資料夾一起轉
docling ./specs/ --to md --output ./out --heading-hierarchy --no-ocr
```

**確保不會連網：** 加上 `--artifacts-path ~/.cache/docling/models`，或先執行 `export HF_HUB_OFFLINE=1`。這樣它只會用本機的模型。

**建議先測試：** 挑一份表格最多、層級最深的規格書轉轉看，打開 `out/spec.md` 檢查表格和 `#`、`##`、`###` 對不對。掃描型的 PDF 就把 `--no-ocr` 拿掉，但在 CPU 上會慢很多。如果你的版本不認得 `--heading-hierarchy`，執行 `pip install -U docling` 升級。

## 其他選擇

- **MarkItDown（Microsoft，免費）：** pickfit 有提到它，但同樣沒有驗證過。它轉 Word 沒問題，但 PDF 基本上只抽出純文字，**表格和標題層級都會不見**，所以不符合你的需求。
- **Marker：** PDF 轉 Markdown 品質很好，CPU 也能跑但比較慢。程式碼是 GPL 授權，模型權重對營收較高的公司有商用限制。公司內部使用前要先看清楚授權，所以我把它排在 Docling 後面。

Sources:
- [Docling – heading levels](https://docling-project.github.io/docling/usage/heading_levels/)
- [Docling heading_levels example](https://docling-project.github.io/docling/examples/heading_levels.py)
- [Docling discussion #1170（標題全部變成 ## 的問題）](https://github.com/docling-project/docling/discussions/1170)
- [md-reheader（第三方標題層級修復工具）](https://pypi.org/project/md-reheader/)