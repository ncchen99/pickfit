## Recommendation: Ollama + the `llm` CLI, with a small retrieval step

I did not find a single mature, terminal-first, offline tool that handles mixed Markdown and PDF notes and cites sources out of the box. The most reliable setup is to combine two well-maintained open-source tools (both Apache-2.0 or MIT, so check the licenses on install):

- **Ollama** runs the language model and the embedding model locally on CPU.
- **`llm`** (Simon Willison's CLI) builds a local embedding index over your files. Its index uses the filename as the ID, so a search returns the note or PDF it came from.

I haven't verified the exact flags against current releases, so run `llm --help` and `llm embed-multi --help` before you rely on them.

**Assumptions:** You want answers with cited filenames, not a chat GUI. Your laptop is the only machine involved. The environment reports macOS (Darwin), not Linux, so I've written the install steps for both and noted the differences.

### Install

1. **Ollama:** Linux: `curl -fsSL https://ollama.com/install.sh | sh`. macOS: install the app from ollama.com or run `brew install ollama`.
2. **Models:** pull a chat model and an embedding model:
   - `ollama pull qwen2.5:3b` (fast on CPU; use `qwen2.5:7b` if you can wait longer for better answers)
   - `ollama pull nomic-embed-text`
3. **Python and `llm`:** `pipx install llm` (or `pip install llm` in a venv), then `llm install llm-ollama` to connect it to Ollama.
4. **PDF text extraction:** Linux: `sudo apt install poppler-utils`. macOS: `brew install poppler`. This provides `pdftotext`.

### First run

1. **Convert PDFs to text** into a separate folder so every source is searchable. Keep the original path in the filename so you can tell where it came from:
   ```
   mkdir -p ~/kb-text
   for f in ~/pdfs/*.pdf; do pdftotext -layout "$f" ~/kb-text/"$(basename "$f" .pdf)".pdf.txt; done
   ```
   Scanned PDFs will produce empty text. For those you need OCR (for example `ocrmypdf`, MPL-2.0).
2. **Build the index once** over the notes and the converted PDFs. This runs locally and may take a while on CPU:
   ```
   llm embed-multi notes -m nomic-embed-text --files ~/notes '*.md' --store
   llm embed-multi notes -m nomic-embed-text --files ~/kb-text '*.txt' --store
   ```
   (Check whether `-m` takes an Ollama embedding model name in your `llm-ollama` version. If not, the embedding step needs a different plugin.)
3. **Ask a question** and see which sources matched:
   ```
   llm similar notes -c "what did I decide about the budget?" -n 5
   ```
   This lists the top matching IDs, which are the file paths.
4. **Get an answer grounded in those files:** pass the top matches as context and ask the model to cite them:
   ```
   llm -m qwen2.5:3b -f ~/notes/budget.md -f ~/kb-text/tax-guide.pdf.txt \
     "Answer using only these files and cite the file name for each claim: what did I decide about the budget?"
   ```
   You can script steps 3 and 4 into one shell function so a single command does both.

### Things to know

- **Offline:** after the models are downloaded, nothing needs the network. To confirm, you can disable Wi-Fi and run a query.
- **Speed:** a 3B model on a 16 GB CPU laptop typically answers in seconds to a minute. A 7B model is slower but usually more accurate.
- **Re-indexing:** re-run `embed-multi` after you add or change notes. It replaces the stored entries for the same IDs.
- **Citation reliability:** the small model can still misattribute a claim. Treat the cited file as the thing to open and check.
- **Alternative if you'd rather have a GUI:** AnythingLLM (MIT) runs on Linux and macOS, uses Ollama, and shows sources in the interface. It is not terminal-based.

Sources:
- [canonical/localGPT](https://github.com/canonical/localGPT) (I found it while searching for a ready-made option; I didn't verify its current Ollama support)
- [sw30labs ollama-pdf2markdown](https://github.com/sw30labs/.github/wiki/ollama-pdf2markdown.stub) (a PDF-to-Markdown option; last commit listed as April 2025)