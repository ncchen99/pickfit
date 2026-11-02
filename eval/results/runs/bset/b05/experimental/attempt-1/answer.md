I'd split this into two steps, and Tesseract is the step to replace. First, read the scans with a modern OCR engine. Second, translate the text with a local LLM and lay it back into place. The Safari and Google results you liked come from strong OCR plus layout detection plus machine translation. You can now build the same thing locally on a Mac.

**Assumptions:** you're on an Apple Silicon Mac with at least 16 GB of RAM, the scans are mostly dark print on a light background, and they're in a European language. If the type is Fraktur/blackletter or another non-Latin script, see the notes at the end.

I haven't run any of this on your machine. pickfit, the tool-testing service I checked, had no tested tool for this task, so these recommendations come from the projects' own documentation and are untested.

---

## Main recommendation: Apple Vision OCR → BabelDOC + Ollama

This setup gives the result closest to Safari's: a PDF with the translated text placed over the original layout.

1. **OCRmyPDF with an Apple Vision plugin** adds a text layer to each scan. Apple Vision is the OCR engine behind Safari's and Live Text's text recognition, and it does much better than Tesseract on poor print.
2. **[BabelDOC](https://github.com/funstory-ai/BabelDOC)** is the layout-preserving engine behind PDFMathTranslate. It finds the page's text blocks, sends them to an LLM to translate, and writes the translation back into the same boxes. Its `--ocr-workaround` mode is built for scanned pages: it puts white boxes over the original text and writes the translation on top. It's meant for black text on a white background, so it handles yellowed paper reasonably but not colored backgrounds.
3. **Ollama** runs the translation model locally. BabelDOC works with any OpenAI-compatible endpoint, and Ollama provides one.

### Install
```bash
brew install uv ollama
uv tool install ocrmypdf --with ocrmypdf-appleocr   # Apple Vision plugin; check the plugin's README for exact name/flags
uv tool install --python 3.12 BabelDOC
ollama serve &                                      # or start the Ollama app
ollama pull qwen3:14b       # good multilingual translator; use qwen3:8b on 16 GB, or a ~30B model on 32 GB+
```
If the Apple Vision plugin doesn't install or work for you, plain `ocrmypdf` still runs. In that case, use the MinerU path below for OCR instead of Tesseract.

### First run (test on 5 pages first)
```bash
mkdir test && cp scans/page00{1..5}.png test/
# 1. images → one PDF with an OCR text layer (one PDF per document is also fine)
ocrmypdf --plugin ocrmypdf_appleocr --image-dpi 300 test/page001.png test/page001.pdf
# 2. translate while keeping the layout, using the local model
babeldoc --files test/page001.pdf \
  --openai --openai-base-url "http://localhost:11434/v1" \
  --openai-model "qwen3:14b" --openai-api-key "x" \
  --lang-in de --lang-out en \
  --ocr-workaround
```
Check the output PDF in the output folder. BabelDOC usually writes both a translated-only version and a bilingual version, and the bilingual one is very handy for research. If the pages look good, loop over the whole pile with a shell `for` loop and leave it running overnight. On a Mac, expect roughly tens of seconds per page, mostly spent on translation.

---

## For the hardest layouts: a vision-language document parser → Markdown → LLM translation

Some pages will be badly degraded or have complex layouts (columns, tables, marginal notes, mixed fonts). For those, it's usually more useful to get the reading order right than to reproduce the exact page look. The current leaders here are vision-language model (VLM) document parsers. They recognize text, layout, reading order and tables together, and give you each block's position on the page:

- **MinerU 2.5**, **PaddleOCR-VL-1.6** and **GLM-OCR** are at the top of the OmniDocBench benchmark (about 95–96), well ahead of the older pipelines. PaddleOCR-VL and GLM-OCR are reported to run on Apple Silicon through MLX ([comparison](https://pasqualepillitteri.it/news/25567/migliori-ocr-locali-pc-server), [PaddleOCR-VL-1.6 paper](https://arxiv.org/pdf/2606.03264)).
- Setup for MinerU: `uv tool install "mineru[all]"`, then `mineru -p scans/ -o out/`. Run `mineru --help` to pick the VLM or MLX backend. The output is Markdown plus a JSON file with every block's coordinates.
- Then translate the Markdown block by block with the Ollama model, using a short script or any Ollama front end. For translated output in the original layout, you can paint each translated block back onto the page image at its coordinates. That reproduces what Google's camera mode does, and it's roughly 50 lines of Python with Pillow.

---

## Tips for 500–1,000 pages
- **Preprocess** the scans: deskew them, make sure they're at least 300 DPI, and convert to grayscale. `ocrmypdf --deskew --clean` handles much of this. It matters more than the choice of OCR engine.
- **Keep the source text** next to the translation, because OCR mistakes in historical print are inevitable. The bilingual PDF or a side-by-side Markdown file lets you check doubtful passages.
- **Give the LLM context** in the prompt: the period, the subject and how you want old spellings handled. This noticeably improves historical translations.
- **Fraktur or other historical scripts:** Apple Vision and the VLM parsers are weaker on these. Try Tesseract's dedicated `frk`/`deu_latf` models or Kraken for the OCR step, and keep the rest of the pipeline as it is.
- **The translation_layoutrecovery repo you tried** is an older research prototype with outdated dependencies. BabelDOC/PDFMathTranslate is the maintained successor of that idea ([ACL 2026 paper](https://aclanthology.org/2026.acl-demo.25/)).

Sources:
- [BabelDOC on GitHub](https://github.com/funstory-ai/BabelDOC)
- [BabelDOC on PyPI](https://pypi.org/project/babeldoc)
- [BabelDOC ACL 2026 demo paper](https://aclanthology.org/2026.acl-demo.25/)
- [PDFMathTranslate overview](https://blog.brightcoding.dev/2026/02/08/pdfmathtranslate-the-revolutionary-tool-preserving-scientific-layouts)
- [PaddleOCR-VL paper](https://arxiv.org/pdf/2510.14528)
- [PaddleOCR-VL-1.6 paper](https://arxiv.org/pdf/2606.03264)
- [Local OCR comparison 2026](https://pasqualepillitteri.it/news/25567/migliori-ocr-locali-pc-server)