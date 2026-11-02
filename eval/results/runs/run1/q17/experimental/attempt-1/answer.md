I'm assuming an x86_64 Debian/Ubuntu-style distro and PDFs that contain real text, not scanned images. I haven't run anything on your machine.

# My recommendation: aichat + Ollama

- **[Ollama](https://ollama.com)** runs a small language model and an embedding model on your CPU. It's free and open source (MIT).
- **[aichat](https://github.com/sigoden/aichat)** is a single Rust program that runs in the terminal (MIT/Apache-2.0). It has built-in document search (RAG): it indexes a folder of `.md` files and PDFs, answers questions from them, and `.sources rag` shows which files the last answer came from.

**Caveat:** the tool-checking service I used (pickfit) has not tested this pair. It's my pick from general knowledge plus aichat's current documentation, which lists the `.rag` / `.sources rag` commands, folder/glob input, and PDF loading through `pdftotext`. Treat the steps below as unverified.

**Why not pickfit's tested picks?** It suggested three, and none fits as well:
- **HilbertRaum** (GPL-3.0) claims document Q&A with citations, but it's a desktop app, not a terminal tool. Pickfit only confirmed it installs and opens offline. It never tested the Q&A or the citations.
- **Unlimited-Context-LLM** doesn't list source citations or PDF loading.
- **Camelid** doesn't say it cites sources.

HilbertRaum is the one to try if you'd accept a graphical app.

## Install

```bash
# 1. PDF text extraction
sudo apt install poppler-utils          # provides pdftotext

# 2. Ollama (official script; read it first if you prefer)
curl -fsSL https://ollama.com/install.sh -o ollama-install.sh
less ollama-install.sh && sh ollama-install.sh

# 3. Models (one-time download, then fully offline)
ollama pull qwen2.5:7b          # answer model, ~4.7 GB, runs fine in 16 GB RAM on CPU
ollama pull nomic-embed-text    # embedding model, ~270 MB

# 4. aichat: prebuilt binary from GitHub Releases, or:
cargo install aichat
```

If 7B answers feel too slow on your CPU, use `qwen2.5:3b` or `llama3.2:3b`. They're faster but less precise.

## Configure `~/.config/aichat/config.yaml`

```yaml
model: ollama:qwen2.5:7b
rag_embedding_model: ollama:nomic-embed-text
rag_top_k: 5
document_loaders:
  pdf: 'pdftotext $1 -'
clients:
  - type: openai-compatible
    name: ollama
    api_base: http://localhost:11434/v1
    models:
      - name: qwen2.5:7b
        max_input_tokens: 32768
      - name: nomic-embed-text
        type: embedding
        default_chunk_size: 1000
        max_batch_size: 50
```

Everything goes to `localhost`, so nothing leaves the laptop.

## First run

```bash
aichat
```

Inside the aichat prompt:

```
.rag notes
```

When it asks which documents to add, give a glob such as `~/notes/**/*.{md,pdf}`. It then embeds everything. With about 2,000 notes on CPU, expect roughly 10–30 minutes the first time. After that:

```
What did I decide about the database migration last spring?
.sources rag        ← lists the note/PDF files behind that answer
```

## Day-to-day use

- Run `aichat`, then `.rag notes` to reopen the saved index.
- After editing or adding notes, run `.rebuild rag`.
- `.set rag_top_k 8` pulls in more passages when an answer seems incomplete.
- aichat also has a `--rag` flag for one-off questions straight from the shell. I haven't checked its exact syntax, so see `aichat --help`.

## Limitations

- Sources come from `.sources rag` after each answer. They aren't printed inline by default, so check that list before trusting an answer.
- Scanned PDFs have no text to extract. Run them through `ocrmypdf` first.
- Quality depends on the small local model. It's good for "find and summarise what I wrote," weaker for complex reasoning across many notes.

**Alternatives if this doesn't suit you:** Khoj (self-hosted, works with Ollama and cites sources, but is web/editor based) or PrivateGPT (local Q&A over documents with sources, API/web UI). Pickfit hasn't tested either.