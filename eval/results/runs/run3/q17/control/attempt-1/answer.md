I'd use **Ollama** to run the models on your laptop and **aichat** as the terminal app that searches your notes. Both are free and open source (MIT / MIT-or-Apache-2.0), run fine on a CPU, and nothing leaves the laptop once the models are downloaded.

## Recommendation: aichat + Ollama

- **Ollama** runs a small chat model and an embedding model (which turns notes into searchable vectors) locally.
- **aichat** is a single command-line program with built-in search over your documents. It combines meaning-based search with plain keyword search, so you don't need a separate database. It can read PDFs if you have `pdftotext` installed.
- **Sources:** after any answer, run `.sources rag` to see exactly which files and passages the answer was based on. That list is more reliable than citations the model writes itself, because small models sometimes get those wrong.

**My assumptions:**
- Your PDFs contain real text. Scanned images would first need OCR, for example `ocrmypdf in.pdf out.pdf`.
- You're on a Debian/Ubuntu-style system. On Fedora use `dnf`, on Arch use `pacman`.
- I haven't tested this exact setup, so check the config keys below against aichat's README if anything errors.

## Install

```bash
# 1. PDF text extraction
sudo apt install poppler-utils

# 2. Ollama (look over the script first, or use the manual tarball from ollama.com/download/linux)
curl -fsSL https://ollama.com/install.sh -o ollama-install.sh
less ollama-install.sh && sh ollama-install.sh

# 3. Models: a small chat model plus an embedding model
ollama pull qwen3:4b            # ~2.5 GB; llama3.2:3b or gemma3:4b also work
ollama pull nomic-embed-text    # ~270 MB

# 4. aichat: get the prebuilt Linux binary from github.com/sigoden/aichat/releases
#    or, if you have Rust:
cargo install aichat
```

With 16 GB of RAM and no GPU, a 3–4B model answers at a usable speed. An 8B model like `qwen3:8b` gives better answers but is noticeably slower.

## Configure

Create `~/.config/aichat/config.yaml`:

```yaml
model: ollama:qwen3:4b
rag_embedding_model: ollama:nomic-embed-text
rag_top_k: 6
document_loaders:
  pdf: 'pdftotext $1 -'
clients:
  - type: openai-compatible
    name: ollama
    api_base: http://localhost:11434/v1
    models:
      - name: qwen3:4b
        max_input_tokens: 32768
      - name: nomic-embed-text
        type: embedding
        default_chunk_size: 1000
        max_batch_size: 50
```

By default Ollama gives the model only a small amount of text to read at once, so the retrieved passages can get cut off. Give it more room by setting `OLLAMA_CONTEXT_LENGTH=8192`. If Ollama runs as a systemd service, set it with `sudo systemctl edit ollama` by adding `Environment="OLLAMA_CONTEXT_LENGTH=8192"`, then restart Ollama. Ollama only listens on localhost by default.

## First run

```bash
aichat --rag notes
```

1. aichat asks for the embedding model, chunk size and which documents to add. For the documents, enter something like:
   `~/notes/**/*.md;~/pdfs/**/*.pdf`
2. It indexes everything. On a CPU, expect roughly 10–30 minutes for 2,000 notes. This only happens once.
3. Ask questions in the prompt that opens:
   ```
   > What did I decide about the backup strategy last spring? Cite the file names.
   > .sources rag      # shows the exact files/passages used
   ```
4. Later:
   - Start it again with `aichat --rag notes`.
   - Ask a single question without opening the prompt: `aichat --rag notes "your question"`.
   - After you add or edit notes, run `.rebuild rag` inside aichat.

## Alternatives, if aichat doesn't suit you

- **Simon Willison's `llm` + `llm-ollama`:** a scriptable command-line tool with embeddings, but you'd have to build the question-answering and source-listing part yourself.
- **Khoj** or **Open WebUI** with Ollama: also offline and open source, but you use them in a browser, not the terminal. They handle citations nicely and are worth a look if you ever want a graphical interface.