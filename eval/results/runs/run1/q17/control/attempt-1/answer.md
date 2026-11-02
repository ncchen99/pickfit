I recommend **Ollama + AIChat**. Both are free and open source, and both work completely offline once the models are downloaded.

- **Ollama** runs a small language model and an embedding model on your CPU.
- **AIChat** (github.com/sigoden/aichat) is a terminal chat tool with document search built in. It indexes your notes and PDFs into a local database, finds the passages that match your question, and passes them to the model. Its `.sources rag` command lists the files each answer came from.

It's a single Rust binary with no Python setup or web interface. I'm assuming you're fine typing questions into a terminal chat prompt and don't need a graphical app.

## Install

1. **Ollama:**
   ```
   curl -fsSL https://ollama.com/install.sh | sh
   ```
   Or use your distro's package or the tarball from ollama.com.

2. **Models.** Download these once while you're online:
   ```
   ollama pull qwen3:4b            # chat model, ~2.5 GB, usable speed on CPU
   ollama pull nomic-embed-text    # embedding model for search
   ```
   With 16 GB RAM and no GPU, a 3–4B model is the practical choice. `qwen3:8b` or `llama3.1:8b` give better answers but are about half as fast. Model names change over time, so check ollama.com/library for current small models if these have moved on.

3. **PDF text extraction:**
   ```
   sudo apt install poppler-utils   # or: dnf install poppler-utils / pacman -S poppler
   ```

4. **AIChat.** Download the Linux binary from github.com/sigoden/aichat/releases and put it on your PATH. Or install it with `cargo install aichat`. Some distros also package it (for example, `pacman -S aichat`).

## Configure

Create `~/.config/aichat/config.yaml`:

```yaml
model: ollama:qwen3:4b
rag_embedding_model: ollama:nomic-embed-text
rag_top_k: 6

clients:
  - type: openai-compatible
    name: ollama
    api_base: http://localhost:11434/v1
    models:
      - name: qwen3:4b
        max_input_tokens: 32768
      - name: nomic-embed-text
        type: embedding
        default_chunk_size: 1500
        max_batch_size: 50

document_loaders:
  pdf: 'pdftotext $1 -'
```

AIChat only talks to Ollama on `localhost`, so nothing leaves your laptop. To check this, turn off Wi-Fi and run a query.

## First run

```
aichat --rag notes
```

1. AIChat asks you to confirm the embedding model, chunk size and overlap. The defaults are fine.
2. When it asks for documents, enter a glob such as:
   ```
   ~/notes/**/*.{md,pdf}
   ```
   Separate multiple paths with `;`.
3. Indexing about 2,000 notes on CPU will probably take somewhere between several minutes and around 30 minutes. It only happens once.
4. Ask questions at the prompt:
   ```
   notes> What did I decide about the backup strategy last spring?
   notes> .sources rag
   ```
   `.sources rag` lists the files and passages used for the last answer.
5. For one-off questions from the shell:
   ```
   aichat --rag notes "summarize my notes on Kubernetes networking"
   ```

**Maintenance:** after adding or editing notes, run `.rebuild rag` inside the session. It re-indexes only what changed.

## Tips and caveats

- **Citations in the answer itself:** you can add an instruction such as "cite the file name for each claim". Small models don't always follow it reliably, so treat `.sources rag` as the authoritative list.
- **Better search results:** add `rag_reranker_model` if you set up a local reranker. The default hybrid search (keyword plus vector) already works well for notes.
- **Scanned PDFs:** these have no text layer, so `pdftotext` returns nothing. Run them through `ocrmypdf` first.
- **Accuracy:** a 4B model sometimes gets details wrong. Check important answers against the cited files.

## Alternatives

- **llm (Simon Willison) + llm-ollama:** good for scripting, but you'd have to build the document search and citations yourself.
- **AnythingLLM** or **Open WebUI:** offline document chat with citations, but through a GUI or browser, not the terminal.
- **PrivateGPT:** more setup (Python), and it's built around an API or web interface.

Source: [AIChat RAG Guide](https://github.com/sigoden/aichat/wiki/RAG-Guide). Some details come from my own knowledge and weren't checked against that page: the Ollama and model install commands, the config keys other than `document_loaders`, and the `.sources rag` and `.rebuild rag` commands. If any of them doesn't work, check the AIChat README or `.help`.