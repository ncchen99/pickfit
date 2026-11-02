I recommend **aichat** for the terminal, with **Ollama** running the models locally. I haven't run any of these steps.

**How I got here:** The tool-recommendation service I checked (pickfit) didn't find a good match. Its top result, HilbertRaum, is a desktop app, not a terminal tool, and pickfit never tested its document Q&A. I picked aichat myself: it's a well-known open-source tool (MIT/Apache) but pickfit hasn't tested it. I checked its PDF and Ollama settings against its official docs. The `.sources` command and the exact `.rag` prompts are from memory, so check them against `aichat --help` and `.help` in your version.

## Recommendation: aichat + Ollama

**Why it fits:**
- **Terminal only:** a single program, with an interactive mode or one-off questions.
- **Built-in document search:** it reads markdown directly, and reads PDFs through `pdftotext`.
- **Shows sources:** `.sources rag` lists the note or PDF chunks the last answer was based on.
- **Offline:** everything runs on your laptop. The only internet use is the one-time downloads during setup. After that you can turn off Wi-Fi.
- **Fits 16 GB RAM with no GPU:** a 3B–8B model plus a small search model is enough.

**Trade-offs:**
- Answers on a CPU are slow-ish: about 3–10 words per second with a 7–8B model.
- Building the index the first time, for about 2,000 notes, may take 10–30+ minutes on a CPU.
- Scanned PDFs with no text layer need OCR first.

## Install

1. **Install `pdftotext`** (part of poppler). Debian/Ubuntu: `sudo apt install poppler-utils`. Fedora: `sudo dnf install poppler-utils`. Arch: `sudo pacman -S poppler`.
2. **Install Ollama** from https://ollama.com/download/linux. The official one-liner is `curl -fsSL https://ollama.com/install.sh | sh`. That pipes a script into a root shell, so read it first, or use the manual tarball steps on the same page instead.
3. **Download the models** (the only step that needs internet):
   ```
   ollama pull nomic-embed-text      # turns notes into searchable vectors (~270 MB)
   ollama pull qwen2.5:7b            # answers questions (~4.7 GB); for faster answers use llama3.2:3b
   ```
4. **Install aichat** using one of these:
   - the prebuilt `x86_64-unknown-linux-musl` binary from https://github.com/sigoden/aichat/releases, copied to `~/.local/bin`
   - `cargo install aichat`
   - your distro's package (e.g. Arch: `pacman -S aichat`)

## Configure (`~/.config/aichat/config.yaml`)
Writing this file before the first run skips aichat's setup wizard:
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
Ollama only listens on localhost by default, so nothing is exposed to your network.

## First run
I'm assuming your notes are in `~/notes` and your PDFs in `~/pdfs`.
```
aichat
> .rag notes
```
- When it asks about the embedding model and chunk size, accept the defaults.
- At **"Add documents:"** enter `~/notes/**/*.md;~/pdfs/`. If the `;` separator isn't accepted, add the two folders one at a time.
- Ask a question, e.g. `What did I decide about the backup strategy?`
- Run `.sources rag` to see which files the answer came from.
- After you add or edit notes, run `.rebuild rag` to update the index.

For a one-off question without the interactive mode: `aichat --rag notes "your question"`.

**Tips:**
- For better source attribution, add a line to your question like "cite the file name for each claim".
- If answers feel too slow, switch `model` to `llama3.2:3b`.

**Fallback if you'd rather have a window than a terminal:** HilbertRaum (GPL-3.0). pickfit confirmed it installs and opens on Linux x86_64 offline, but it didn't test its document Q&A because the models were too large for its test sandbox.

Sources:
- [aichat RAG Guide](https://github.com/sigoden/aichat/wiki/RAG-Guide)
- [aichat config.example.yaml](https://raw.githubusercontent.com/sigoden/aichat/main/config.example.yaml)
- [HilbertRaum](https://github.com/HilbertraumAI/HilbertRaum)