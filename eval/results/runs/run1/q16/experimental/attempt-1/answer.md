My recommendation is **llama.cpp's `llama-server` running EuroLLM‑9B‑Instruct (Q4 GGUF), plus a short Python script I've written below.** The script handles your two problems. It never sends fenced code blocks to the model. It swaps URLs and inline code for numbered placeholders before translating and puts the originals back afterwards. It also lists Brazilian Portuguese words that get through.

Everything is free, runs from the terminal and works on CPU. The model needs about 6 GB of RAM, which fits in 16 GB. After the one‑time model download, no text leaves the machine.

## Why this setup

- **Brazilian Portuguese output:** No small local model reliably produces European Portuguese just because you ask. This setup tackles it three ways:
  1. **EuroLLM** comes from a European project led by Unbabel and IST in Lisbon, so it has a better chance than most.
  2. The prompt gives explicit pt‑PT rules: *ficheiro, ecrã, utilizador, equipa*, and "está a fazer" rather than "está fazendo".
  3. The script lists any Brazilian words left in the output so someone can fix them.
- **Code and URLs getting mangled:** Prompting alone won't fix this. The script separates code and URLs from the text, translates only the text, puts them back, and checks that every placeholder came back.
- **What pickfit suggested:** pickfit's only match was HilbertRaum. It's a desktop app, not a terminal tool, and pickfit didn't test its translation feature. That feature needs a TranslateGemma 12B model of about 13 GB, which is too tight on a 16 GB CPU‑only box. I'm not recommending it.
- **An option to watch:** [Tradutor](https://arxiv.org/html/2502.14385) is an open model built only for English → European Portuguese, based on Llama‑3 8B ([news coverage](https://tech.slator.com/?p=103667)). I couldn't find a ready‑made GGUF version of it. If one appears, switch the `-hf`/`-m` argument and keep the same script.

## Install (Ubuntu/Debian, x86_64; I haven't run any of this)

```bash
sudo apt install build-essential cmake git libcurl4-openssl-dev python3
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
cmake -B build && cmake --build build --config Release -j
```
llama.cpp also publishes prebuilt `ubuntu-x64` zips on its GitHub Releases page if you'd rather not compile.

Start the server. The first start downloads the model once; after that it runs offline.
```bash
./build/bin/llama-server -hf bartowski/EuroLLM-9B-Instruct-GGUF:Q4_K_M \
  --jinja -c 4096 --temp 0 --host 127.0.0.1 --port 8080
```
I'm assuming that repo name is right ([EuroLLM GGUF builds exist](https://huggingface.co/QuantFactory/EuroLLM-9B-GGUF), but check the exact repo on Hugging Face). If the box can't reach the internet, download the `.gguf` file on another machine and use `-m /path/model.gguf`. `--host 127.0.0.1` makes the server reachable only from that machine.

## The script: `md2ptpt.py` (Python standard library only)

```python
#!/usr/bin/env python3
"""Translate a folder of Markdown (en -> pt-PT) via a local llama-server.
Fenced code and front matter are copied verbatim; URLs, inline code and HTML are masked."""
import json, re, sys, pathlib, urllib.request

API = "http://127.0.0.1:8080/v1/chat/completions"
SYSTEM = (
    "You are a professional translator. Translate the user's Markdown from English into "
    "EUROPEAN Portuguese (Portugal, pt-PT, AO90 spelling). Never use Brazilian Portuguese. "
    "Use: ficheiro (not arquivo), ecrã (not tela), utilizador (not usuário), equipa (not equipe), "
    "registo (not registro), contacto (not contato), guardar (not salvar), transferir (not baixar), "
    "aplicação (not aplicativo), telemóvel (not celular), eliminar (not deletar); "
    "use 'estar a + infinitivo' (está a correr), never the gerund (está rodando); "
    "prefer clitic after the verb (configura-se). "
    "Keep every token like ⟦0⟧ exactly as is. Keep all Markdown syntax (#, -, *, |, [ ], links). "
    "Output ONLY the translation, with no comments or quotes."
)
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
PROTECT = re.compile(
    r"`+[^`\n]*?`+"                    # inline code
    r"|(?<=\])\([^)]*\)"                # link/image target (url "title")
    r"|^\s*\[[^\]]+\]:\s*\S+.*$"        # reference link definitions
    r"|https?://[^\s)\]>]+"             # bare URLs
    r"|<[^>\n]+>", re.M)                # autolinks and HTML tags
TOKEN = re.compile(r"⟦\d+⟧")
BR = re.compile(r"\b(arquivos?|usuári\w*|tela|equipe|registro|contato|salvar|baixar|aplicativo|"
                r"celular|deletar|est(?:á|ão|ava|avam)\s+\w+ndo)\b", re.I)

def ask(text):
    body = json.dumps({"messages": [{"role": "system", "content": SYSTEM},
                                    {"role": "user", "content": text}],
                       "temperature": 0, "max_tokens": 2048}).encode()
    req = urllib.request.Request(API, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()

def translate_para(para, name):
    saved = []
    def keep(m):
        saved.append(m.group(0))
        return f"⟦{len(saved) - 1}⟧"
    masked = PROTECT.sub(keep, para)
    if not re.search(r"[A-Za-z]{2,}", TOKEN.sub("", masked)):
        return para                                 # nothing translatable
    want = sorted(TOKEN.findall(masked))
    for _ in range(2):                              # one retry
        out = ask(masked)
        if sorted(TOKEN.findall(out)) == want and out.count("|") == masked.count("|"):
            return TOKEN.sub(lambda m: saved[int(m.group(0)[1:-1])], out)
    print(f"  ! {name}: kept English (placeholders broke): {para[:60]!r}", file=sys.stderr)
    return para

def translate_file(src, dst):
    lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    out, para, fence, start = [], [], None, 0
    if lines and lines[0].strip() == "---":         # YAML front matter: verbatim
        end = next((j for j in range(1, len(lines)) if lines[j].strip() in ("---", "...")), None)
        if end:
            out, start = lines[:end + 1], end + 1
    def flush():
        if para:
            text = "".join(para); body = text.rstrip("\n")
            out.append(translate_para(body, src.name) + text[len(body):])
            para.clear()
    for line in lines[start:]:
        m = FENCE.match(line)
        if fence:
            out.append(line)
            s = line.strip()
            if s and set(s) == {fence[0]} and len(s) >= len(fence):
                fence = None
        elif m:
            flush(); fence = m.group(1); out.append(line)
        elif not line.strip():
            flush(); out.append(line)
        else:
            para.append(line)
    flush()
    result = "".join(out)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(result, encoding="utf-8")
    # sanity checks
    url = re.compile(r"https?://[^\s)\]>\"']+")
    if sorted(url.findall(src.read_text(encoding="utf-8"))) != sorted(url.findall(result)):
        print(f"  ! {src.name}: URL mismatch, check manually", file=sys.stderr)
    for w in sorted({m.group(0).lower() for m in BR.finditer(result)}):
        print(f"  ? {src.name}: possible pt-BR: {w}", file=sys.stderr)

if __name__ == "__main__":
    src_root, dst_root = map(pathlib.Path, sys.argv[1:3])
    for f in sorted(src_root.rglob("*.md")):
        dst = dst_root / f.relative_to(src_root)
        if dst.exists():
            continue                                # resumable
        print(f"translating {f}")
        translate_file(f, dst)
```

## First run

1. Try it on a small sample first:
   ```bash
   mkdir -p /tmp/sample && cp docs/some-page.md /tmp/sample/
   python3 md2ptpt.py /tmp/sample /tmp/sample-pt
   diff <(grep -A999 '```' /tmp/sample/some-page.md) <(grep -A999 '```' /tmp/sample-pt/some-page.md)  # quick eyeball of code
   ```
2. Ask someone in the Lisbon office to read 2–3 translated pages. Then add their corrections (preferred terms, formal or informal tone) to the word list in `SYSTEM`.
3. Run the whole folder overnight:
   ```bash
   nohup python3 md2ptpt.py docs/ docs-pt-PT/ > translate.log 2>&1 &
   ```
   It skips files that are already done, so you can stop and restart it. On CPU, expect a few tokens per second, which works out to roughly minutes per page.
4. Check `translate.log`:
   - `!` lines: paragraphs left in English, or URLs that don't match the source.
   - `?` lines: Brazilian words that got through.

## Assumptions and limits

- **Front matter:** I assumed YAML front matter shouldn't be translated, so it's copied as is.
- **Link titles:** Link targets are copied as is, so link titles like `(url "Title")` stay in English.
- **Indented code:** Only fenced code blocks (``` or ~~~) are protected. Code that's only indented with 4 spaces would get translated.
- **Pt‑PT quality:** EuroLLM's published tests cover Brazilian Portuguese, not European Portuguese. The prompt and the word check lower the risk but don't remove it, so plan on a human review pass.
- **More RAM:** If the box ever has more memory, trying a bigger model with the same script is the easiest quality upgrade.

Sources:
- [Tradutor paper (arXiv 2502.14385)](https://arxiv.org/html/2502.14385)
- [Slator: Meet Tradutor](https://tech.slator.com/?p=103667)
- [EuroLLM 9B GGUF](https://huggingface.co/QuantFactory/EuroLLM-9B-GGUF)
- [EuroLLM 1.7B Instruct GGUF](https://huggingface.co/QuantFactory/EuroLLM-1.7B-Instruct-GGUF)
- [AMALIA pt-PT LLM report (arXiv 2603.26511)](https://arxiv.org/pdf/2603.26511)
- [HilbertRaum (pickfit result)](https://github.com/HilbertraumAI/HilbertRaum)