**Recommendation: Ollama for the local model, the `llm` CLI for search and answers, and `pdftotext` for PDFs.** It is free, open source, runs fully offline on CPU, and prints the file path for each answer. I have not verified this exact pipeline with pickfit, so treat the commands below as a plan to check on your machine. Run `llm embed-models` and `llm models` to confirm the names before you rely on them.

I'm assuming you're on the Linux laptop you described (Debian/Ubuntu-style commands, 16 GB RAM, no GPU). The sandbox I checked reports macOS, so tell me if your package commands need changing.

**Install (review each command before running it)**

```bash
sudo apt install pipx poppler-utils jq        # PDF text extraction, JSON parsing
curl -fsSL https://ollama.com/install.sh | sh  # pipes a script to sh; read it first
ollama pull llama3.2:3b                        # answer model, about 2 GB, fine on CPU
ollama pull nomic-embed-text                   # embedding model for search
pipx install llm
llm install llm-ollama                         # connects llm to Ollama
```

**First run**

```bash
# 1. Convert PDFs to text. Scanned PDFs have no text layer and need OCR first (ocrmypdf).
mkdir -p ~/kb/pdf-text
for f in ~/pdfs/*.pdf; do pdftotext -layout "$f" ~/kb/pdf-text/"$(basename "$f" .pdf).txt"; done

# 2. Index notes and PDF text. --store keeps the text so answers can quote it.
llm embed-multi kb --files ~/notes '**/*.md' -m nomic-embed-text --store
llm embed-multi kb --files ~/kb/pdf-text '*.txt' -m nomic-embed-text --store
```

Indexing about 2,000 notes on CPU may take a while. Run it once and re-run it when your notes change.

**Ask questions** (add this function to `~/.bashrc`):

```bash
ask() {
  q="$*"
  ctx=$(llm similar kb -c "$q" -n 6 | jq -r '"SOURCE: " + .id + "\n" + .content + "\n---"')
  printf '%s\n' "$ctx" | llm -m llama3.2:3b \
    -s "Answer using only the SOURCE blocks. After each claim, cite the SOURCE path in brackets. If the sources don't answer it, say so." "$q"
}
ask "What did I decide about the server migration?"
```

Each answer should end with citations such as `[~/notes/infra/migration.md]`. Check the cited files, because a 3B model can still miscite.

**Things to know**

- **Offline:** after the models are pulled, you can disconnect Wi-Fi and everything still runs. Ollama, `llm`, and the embeddings all stay local.
- **Speed and quality:** a 3B model on CPU gives a few tokens per second and answers are decent, not great. If you want better answers and can wait longer, try `qwen2.5:7b` (about 5 GB, fits in 16 GB RAM).
- **Long PDFs:** very long documents can exceed the embedding model's context. Split them into per-page or per-section text files so each one is indexed separately.
- **Alternative with a GUI:** HilbertRaum (GPL-3.0, Linux, offline) is a desktop app. pickfit confirmed only that it installs and starts. Its document Q&A with citations was not tested, and it needs at least 8 GB RAM plus Node 22.12 or later. Choose it if you prefer a window to a terminal.

Sources: [pickfit HilbertRaum record](https://github.com/HilbertraumAI/HilbertRaum). The Ollama, `llm`, and `pdftotext` steps come from my general knowledge and were not checked against current docs.