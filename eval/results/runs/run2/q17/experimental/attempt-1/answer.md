I recommend **AIChat with Ollama**. AIChat is a terminal chat tool with built-in document Q&A, and Ollama runs the AI models on your laptop. Both are free and open source (AIChat: MIT/Apache-2.0, Ollama: MIT). After you download the models once, nothing goes over the network. You can index a whole notes folder, add PDFs through a small converter, and ask questions in the terminal. The `.sources rag` command shows which files the last answer came from.

**What I assumed:** an x86_64 laptop, your notes in one folder (e.g. `~/notes`), and PDFs that contain real text rather than scanned images. Scanned PDFs need OCR first.

**How I checked this:** the PDF and folder setup below comes from AIChat's RAG guide on its wiki. The Ollama connection, model choices and `.sources rag` come from my own knowledge of these tools, not from a test. If anything doesn't match, check the project's README and `config.example.yaml`. pickfit, the tool-testing service I searched, hasn't tested AIChat or Ollama, and I didn't run anything on your machine.

## Install
1. **Ollama:**
   ```bash
   curl -fsSL https://ollama.com/install.sh -o ollama-install.sh
   less ollama-install.sh      # read it first; it uses sudo
   sh ollama-install.sh
   ```
   Or use the manual tarball steps on ollama.com/download/linux.
2. **Models:** download these once, while online.
   ```bash
   ollama pull nomic-embed-text   # turns notes into searchable vectors, ~270 MB
   ollama pull qwen2.5:7b         # writes the answers, ~4.7 GB, fits in 16 GB RAM
   ```
   If answers are too slow without a GPU, use `qwen2.5:3b` or `llama3.2:3b` instead.
3. **AIChat:** download the Linux binary from github.com/sigoden/aichat/releases and put it on your PATH. You can also use `cargo install aichat` or your distro's package (e.g. `pacman -S aichat`).
4. **PDF converter:** install Poppler's `pdftotext` (`sudo apt install poppler-utils` or your distro's equivalent).

## Configure (`~/.config/aichat/config.yaml`)
```yaml
model: ollama:qwen2.5:7b
rag_embedding_model: ollama:nomic-embed-text
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
document_loaders:
  pdf: 'pdftotext $1 -'
```

## First run
```bash
aichat --rag notes
```
- On the first run, AIChat asks for document paths. Enter a filtered folder such as `~/notes/**/*.{md,pdf}`. Separate several paths with `;`.
- Indexing about 2,000 notes on CPU should take somewhere from several minutes to under an hour. It only happens once.
- Then ask a question, e.g. `What did I decide about the backup strategy?`
- Type `.sources rag` to list the files the last answer drew on.
- Type `.rebuild rag` after you add or edit notes.
- Next time, `aichat --rag notes "your question"` asks a single question without opening the chat.

**To confirm nothing leaves the laptop:** turn off Wi-Fi and ask a question. It should still work, because Ollama only listens on localhost.

## Other options
- **Khoj** (AGPL): has an offline mode, but it's mostly a web or Obsidian/Emacs interface. Choose it if you want a GUI later.
- **pickfit results:** pickfit's top pick was **HilbertRaum** (GPL-3.0, offline document Q&A with citations). It's a desktop app in beta, not a terminal tool. pickfit only confirmed that it installs and opens offline; it didn't test document Q&A. Its other picks (Unlimited Context, Camelid) don't say they read PDFs or show sources.

Sources:
- [AIChat RAG Guide](https://github.com/sigoden/aichat/wiki/RAG-Guide)
- [AIChat repo](https://github.com/sigoden/aichat)
- [HilbertRaum](https://github.com/HilbertraumAI/HilbertRaum)