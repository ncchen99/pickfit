I'd use **[aichat](https://github.com/sigoden/aichat)** for the terminal side and **[Ollama](https://ollama.com)** to run the models on your laptop. Both are free and open source (aichat is MIT/Apache-2.0, Ollama is MIT). Once the models are downloaded, nothing leaves your laptop.

## Why this setup

- **Terminal only.** aichat is a single Rust binary. It has an interactive mode and a one-shot mode (`aichat --rag notes "question"`).
- **Search is built in.** It combines meaning-based search with keyword search. You don't need to run a separate database or server.
- **It shows where answers came from.** After any answer, `.sources rag` lists the notes and PDFs it pulled from. You can also tell it to name the file in the answer itself.
- **It reads Markdown directly.** For PDFs, it calls a command you choose; `pdftotext` works well.
- **It runs fine on 16 GB with no GPU.** Use a 7–8B model at Ollama's default 4-bit compression. Expect a few words per second, so a typical answer takes 10–40 seconds.

**Assumptions:** you're on a common distro (Debian/Ubuntu or Fedora), your notes are in one folder (I'll use `~/notes`), and your PDFs contain real text. Scanned PDFs need OCR first (see the end).

## Install (one time, needs internet)

```bash
# 1. Ollama (runs models locally; serves on 127.0.0.1:11434 only)
curl -fsSL https://ollama.com/install.sh -o ollama-install.sh
less ollama-install.sh          # read it before running it
sh ollama-install.sh

# 2. Models: one chat model, one embedding model (the one that indexes your notes for search)
ollama pull qwen2.5:7b          # ~4.7 GB; use qwen2.5:3b if it feels too slow
ollama pull nomic-embed-text    # ~270 MB

# 3. PDF text extractor
sudo apt install poppler-utils  # Fedora: sudo dnf install poppler-utils

# 4. aichat: download the Linux binary from
#    https://github.com/sigoden/aichat/releases  and put it on your PATH
#    (or: cargo install aichat)
```

If newer chat models are out when you install, any 7–8B instruct model from the Ollama library will work the same way.

## Configure aichat for offline use

Create `~/.config/aichat/config.yaml`:

```yaml
model: ollama:qwen2.5:7b
rag_embedding_model: ollama:nomic-embed-text
rag_top_k: 6

clients:
  - type: openai-compatible
    name: ollama
    api_base: http://127.0.0.1:11434/v1
    models:
      - name: qwen2.5:7b
        max_input_tokens: 32768
      - name: nomic-embed-text
        type: embedding
        default_chunk_size: 1000
        max_batch_size: 50

document_loaders:
  pdf: 'pdftotext $1 -'
```

The only client listed points at your own machine, so aichat has no way to call a cloud service.

## First run

```bash
aichat
> .rag notes
```

The first time, it asks a few setup questions. Accept the embedding model and chunk size it offers. When it asks for documents, give it your folders, for example:

```
~/notes/**/*.md;~/notes/**/*.pdf
```

Then it builds the index. With 2,000 notes on a CPU, expect roughly 10–30 minutes. This only happens once; after that, only changed files are processed.

Now ask questions:

```
notes> What did I decide about the backup strategy last spring? Cite the file name for each point.
notes> .sources rag        # lists the exact notes/PDFs used for the last answer
```

Other commands you'll use:

- One question without opening the interactive mode: `aichat --rag notes "your question"`
- After you add or edit notes: run `.rebuild rag` inside the `notes` session
- To confirm it works offline: turn off Wi-Fi and ask a question

## Notes and alternatives

- **Trust `.sources rag` over the answer.** A small local model sometimes names the wrong file or makes up a detail. The sources list shows what was actually retrieved, so check anything important against it.
- **Scanned PDFs:** if `pdftotext` returns blank text, run `ocrmypdf in.pdf out.pdf` (free, offline) and index the output file.
- **Speed vs. quality:** `qwen2.5:3b` is about twice as fast but gives weaker answers. Close your browser while it runs, because the 7B model needs about 6 GB of RAM.
- **If you'd like a Python tool instead:** [local-rag on PyPI](https://pypi.org/project/ollama-local-rag/) also uses Ollama. You add files with `rag add` and ask with `rag ask --show-sources`. It's simpler but less mature.
- **If you ever want a graphical interface:** Open WebUI or Khoj work with the same Ollama models. You said terminal, so I wouldn't start there.

My one caveat: aichat's guide confirmed the document folder patterns and the `pdftotext` setup, but I couldn't confirm the exact first-run questions or the `.sources` / `.rebuild` syntax in the current docs. If a command differs, `.help` inside aichat lists the current ones.

Sources:
- [aichat RAG Guide](https://github.com/sigoden/aichat/wiki/RAG-Guide)
- [ollama-local-rag (PyPI)](https://pypi.org/project/ollama-local-rag/)
- [Local RAG with Ollama + Qdrant](https://mahmadkhan.is-a.dev/blog/local-rag-ollama-qdrant)
- [rlama overview](https://www.sourcepulse.org/projects/1842952)
- [ragcli README](https://docs.rs/crate/ragcli/0.2.0/source/README.md)