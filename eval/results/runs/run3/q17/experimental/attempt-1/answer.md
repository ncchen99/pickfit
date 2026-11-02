I'm assuming an x86_64 laptop running a common distro (Debian/Ubuntu or Fedora). I haven't run anything on your machine.

## Main recommendation: Ollama + aichat

**Ollama** (MIT license) runs the AI models on your laptop. **aichat** (MIT/Apache-2.0) is a terminal chat tool with built-in document search. You point it at your notes folder, it builds a local index, and you ask questions in the terminal. After each answer, the `.sources rag` command shows which files the answer came from. Both tools are free and open source. Once the models are downloaded, nothing needs the internet.

Some caveats so you know how sure I am:
- I'm recommending this from my own knowledge and the aichat docs. I couldn't test it here, and pickfit (the software checker I used) hasn't tested this pair either.
- `.sources rag` lists the passages and files used for the last answer. The answer text itself doesn't contain citation marks.
- Command names have changed slightly between aichat versions. If something doesn't match, type `.help` inside aichat.

### Install
1. **Ollama:** follow the Linux instructions at https://ollama.com/download. The quick method there pipes an install script into your shell and uses sudo, so read the script first. They also offer a manual download if you'd prefer to avoid that.
2. **pdftotext**, which aichat uses to read PDFs:
   `sudo apt install poppler-utils` (Debian/Ubuntu) or `sudo dnf install poppler-utils` (Fedora)
3. **aichat:** download the Linux binary from https://github.com/sigoden/aichat/releases and put it in `~/.local/bin`. If you have Rust installed, `cargo install aichat` works too.
4. **Models** (the last step that needs the internet):
   ```
   ollama pull qwen2.5:7b          # ~4.7 GB, answers questions; good quality for 16 GB RAM on CPU
   ollama pull nomic-embed-text    # small model used to index your notes
   ```
   If answers are too slow, try `llama3.2:3b` instead. It's faster but less accurate.

### Configure: `~/.config/aichat/config.yaml`
```yaml
model: ollama:qwen2.5:7b
rag_embedding_model: ollama:nomic-embed-text
rag_top_k: 6
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

### First run
```
aichat --rag notes
```
- When it asks for document paths, enter something like `~/notes/**/*.{md,pdf}` (separate multiple paths with `;`).
- The first indexing run takes a while on CPU. My rough guess for 2,000 notes is tens of minutes. You only do this once.
- Then ask a question, for example: `What did I decide about the backup strategy?`
- Type `.sources rag` to see which notes or PDFs the answer came from.
- When you add or edit notes, run `.rebuild rag`. Next time, `aichat --rag notes` opens the existing index.

**To confirm it's really offline:** turn off Wi-Fi after pulling the models and ask a question. It should still work. Ollama only listens on your own machine (`localhost:11434`) by default.

## Other options
- **HilbertRaum** (GPL-3.0): a free desktop app for asking questions about documents offline, with citations listed as a feature. pickfit confirmed it installs on Linux x86_64 and opens with the network off. It did not test the document Q&A, though, and the app is a beta GUI rather than a terminal tool. Repo: https://github.com/HilbertraumAI/HilbertRaum
- **Camelid** (MIT): runs offline from the terminal and has document-library search, but pickfit didn't check that search or whether it cites sources for documents. It's not a good fit for your citation requirement.

Sources:
- [aichat RAG Guide](https://github.com/sigoden/aichat/wiki/RAG-Guide)
- [aichat Chat REPL Guide (`.sources rag`, `.rebuild rag`)](https://github.com/sigoden/aichat/wiki/Chat-REPL-Guide/0e55945c682830f944f56b8bd4b8a0c5571d36f3)
- [aichat Command-Line Guide](https://github.com/sigoden/aichat/wiki/Command-Line-Guide/4b517397d19aae119b0ece820458f661b29b86dc)