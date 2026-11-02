I've assumed you have an Apple Silicon Mac with 16 GB of RAM or more, that the documents are in a European language printed in Roman type (for example German or French), and that you're translating into English. I haven't run anything on your machine. I checked the current state of these tools on the web, but I haven't tested them on your scans.

## Main recommendation: Apple's own OCR, then layout-preserving translation with a local LLM

**The OCR Safari uses already runs locally on your Mac.** Safari's "translate text in image" uses Apple's Vision/Live Text engine, which runs on the Mac itself. The plugin **OCRmyPDF-AppleOCR** lets you run that same engine on a whole batch. That should close most of the gap you saw with Tesseract.

The pipeline:

1. **OCRmyPDF + AppleOCR plugin** turns each scan into a searchable PDF. The text is placed exactly where it appears on the page.
2. **pdf2zh-next (PDFMathTranslate-next, built on BabelDOC)** reads that text layer and its layout. It translates each block with a **local LLM through Ollama** and writes a translated PDF with the text in the original positions. It can also write a side-by-side bilingual PDF, which is very useful for research.

Nothing leaves your machine.

### Install

```bash
# Prerequisites (Homebrew)
brew install pipx uv ollama ghostscript tesseract
pipx ensurepath

# 1) OCR: OCRmyPDF + Apple Vision plugin (the plugin needs OCRmyPDF ≥ 17, same environment)
pipx install ocrmypdf
pipx inject ocrmypdf ocrmypdf-appleocr

# 2) Local LLM
ollama serve &               # or start the Ollama app
ollama pull qwen3:14b        # good multilingual model for 16–32 GB; use qwen3:8b on 16 GB if it's slow,
                             # or a larger/newer model if you have the RAM

# 3) Layout-preserving translator
uv tool install --python 3.12 pdf2zh-next
```

### First run (try 10 varied pages first, not all 1,000)

```bash
# Combine page images into a PDF (img2pdf comes with OCRmyPDF)
img2pdf scans/batch01/*.jpg -o batch01.pdf

# OCR with Apple Vision (plugin loads automatically; check `ocrmypdf --help` for its options
# such as recognition mode and language)
ocrmypdf --rotate-pages --deskew -l deu batch01.pdf batch01_ocr.pdf

# Translate: easiest first time via the web UI
pdf2zh_next --gui
```

In the web UI:
- Choose **Ollama** (or "OpenAI-compatible" with base URL `http://localhost:11434/v1` and any API key) as the service.
- Pick your model, then set the source and target languages.
- For scans, turn on the **OCR workaround**. It covers the original text with white boxes and draws the translation on top. It assumes black text on a white background, so very yellowed pages may look patchy.

Once the settings work, switch to the CLI for batches (`pdf2zh_next --help`; flag names change between versions). Leave it running overnight.

## Alternatives, depending on what fails

- **The layout is complex and the reading order comes out scrambled** (columns, sidebars, tables, footnotes): use **MinerU**. It has a fast `vlm-mlx-engine` backend for Apple Silicon. It produces Markdown/JSON in the correct reading order, which you then translate with the same Ollama model. You lose the exact visual layout but keep the structure. One user reported about 38 s per page on an M4 with 16 GB, so 1,000 pages would take about 10 hours. Install: `uv tool install "mineru[all]"`, then see its README for the MLX backend. For research, a "scan on the left, structured translation on the right" view is often more useful than a pixel-perfect re-render.
- **The print is badly degraded and OCR garbles it:** use a vision-language model, for example Qwen-VL via Ollama or LM Studio. Prompt it per page with "transcribe, then translate, keep headings/columns as Markdown". These models read damaged print much better than classic OCR, but they sometimes invent plausible text. Keep the transcription alongside the translation so you can check it.
- **The documents are in blackletter (Fraktur)**: Apple Vision handles it poorly. Use Tesseract's dedicated models (`-l deu_latf`) or Kraken/Calamari with a historical-print model in step 1, and keep step 2 the same.

## Practical notes

- **Skip phkhanhtrinh23/translation_layoutrecovery.** It's an older research prototype with pinned dependencies. pdf2zh-next/BabelDOC does the same job and is actively maintained.
- **Clean the scans before OCR.** Deskewing, cropping borders and scanning at 300 dpi or more help OCR more than switching engines does.
- **Keep the translation model consistent.** Use one model and a short glossary of recurring names and terms for the whole collection, so terminology stays the same across pages.

Sources:
- [OCRmyPDF-AppleOCR (GitHub)](https://github.com/mkyt/OCRmyPDF-AppleOCR) · [PyPI](https://pypi.org/project/ocrmypdf-appleocr/)
- [BabelDOC (GitHub)](https://github.com/funstory-ai/BabelDOC) · [PyPI](https://pypi.org/project/BabelDOC/) · [pdf2zh-next](https://pdf2zh-next.com)
- [MinerU MLX backend release notes](https://newreleases.io/project/github/opendatalab/MinerU/release/mineru-2.6.3-released) · [mineru-vl-utils](https://pypi.org/project/mineru-vl-utils/0.2.6/) · [mcp-mineru (speed figures)](https://pypi.org/project/mcp-mineru/0.1.2/)