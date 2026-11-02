I recommend running **AMALIA‑9B** locally through **Ollama**, with a short Python script that hides code and URLs from the model. AMALIA is an open model built for European Portuguese by Portuguese universities and research centres, and its license is listed as Apache 2.0. The 4‑bit version is about 5.2 GB, so it fits in 16 GB of RAM on CPU.

The script fixes the mangling problem in a way that doesn't depend on the model behaving. It never sends fenced code blocks, front matter or link definitions to the model. Inline code, link targets, HTML and bare URLs are swapped for placeholders like `⟦3⟧` before translation. Afterwards the script checks that every placeholder came back exactly once. If any is missing it retries, and if that also fails it keeps that paragraph in English and logs a warning.

I didn't run anything on your machine, and neither the model nor the script has been tested here. The pickfit catalogue had no tool for this job, so this setup is my own recommendation from documentation and model cards. Check one or two docs before running the whole folder.

**Assumptions:** x86_64 Linux, Python 3.8 or newer, and internet access once to download the model. After that everything runs offline.

---

## 1. Install Ollama and pull the model

```bash
# Official installer (it pipes a script into the shell, so read it first if your policy requires that):
curl -fsSL https://ollama.com/install.sh -o ollama-install.sh && less ollama-install.sh && sh ollama-install.sh
# On systemd distros it runs as a service on 127.0.0.1:11434 (localhost only).

# Pull the European Portuguese model (community GGUF of the official DPO release, ~5.2 GB):
ollama pull hf.co/layerx-labs/AMALIA-9B-0626-DPO-GGUF:Q4_K_M
```

If that tag doesn't resolve, open the [layerx-labs GGUF repo](https://huggingface.co/layerx-labs/AMALIA-9B-0626-DPO-GGUF) and use the exact quant name from its file list. [teex-pt](https://huggingface.co/teex-pt/AMALIA-9B-0626-DPO-GGUF) has the same model. If you have spare RAM and time, Q5_K_M or Q8_0 give slightly better quality.

Quick check:
```bash
ollama run hf.co/layerx-labs/AMALIA-9B-0626-DPO-GGUF:Q4_K_M \
  "Traduz para português europeu: Download the file and open it on your screen."
# You want: "Transfira o ficheiro e abra-o no seu ecrã" (not "Baixe o arquivo ... na sua tela")
```

## 2. Save the batch script as `md2ptpt.py`

It uses only the Python standard library.

```python
#!/usr/bin/env python3
"""Translate a folder of Markdown from English to European Portuguese via local Ollama.
Fenced code, front matter and link definitions are copied verbatim; inline code, URLs,
link targets and HTML are masked as ⟦n⟧ placeholders and restored after translation."""
import json, pathlib, re, sys, urllib.request

MODEL = "hf.co/layerx-labs/AMALIA-9B-0626-DPO-GGUF:Q4_K_M"
OLLAMA = "http://127.0.0.1:11434/api/chat"
SYSTEM = (
    "És um tradutor técnico. Traduz o texto do utilizador de inglês para português europeu "
    "(pt-PT, norma de Portugal), nunca português do Brasil. Usa 'ficheiro', 'ecrã', 'utilizador', "
    "'transferir', 'palavra-passe', 'registo', 'equipa' e 'estar a + infinitivo' em vez do gerúndio. "
    "Mantém exatamente a formatação Markdown (#, *, -, |, >, numeração) e copia sem alterações "
    "todos os marcadores ⟦0⟧, ⟦1⟧, etc. Responde apenas com a tradução, sem comentários."
)

FENCE = re.compile(r"\s*(`{3,}|~{3,})")
PROTECT = re.compile(
    r"``[^\n]*?``|`[^`\n]+`"                      # inline code
    r"|\]\([^)\n]*\)"                             # link/image targets ](url "title")
    r"|<https?://[^>\s]+>|</?[A-Za-z][^>\n]*>"    # autolinks, HTML tags
    r"|https?://[^\s<>()\[\]]+"                   # bare URLs
    r"|\{#[^}\n]*\}"                              # heading anchors {#id}
)
REFDEF = re.compile(r"\s{0,3}\[[^\]]+\]:\s*\S+")  # [id]: https://...

def mask(text):
    saved = []
    def sub(m):
        saved.append(m.group(0))
        return f"⟦{len(saved) - 1}⟧"
    return PROTECT.sub(sub, text), saved

def unmask(text, saved):
    found = sorted(int(n) for n in re.findall(r"⟦(\d+)⟧", text))
    if found != list(range(len(saved))):
        return None
    return re.sub(r"⟦(\d+)⟧", lambda m: saved[int(m.group(1))], text)

def ask(text):
    body = json.dumps({
        "model": MODEL, "stream": False,
        "options": {"temperature": 0, "num_ctx": 4096},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.load(r)["message"]["content"].strip()

def translate_block(block):
    if not re.search(r"[A-Za-z]", PROTECT.sub("", block)):
        return block                              # nothing translatable
    masked, saved = mask(block)
    for _ in range(2):
        out = unmask(ask(masked), saved)
        if out is not None:
            return out
    print(f"  ! placeholders lost, kept English: {block[:70]!r}", file=sys.stderr)
    return block

def translate_doc(src):
    lines = src.splitlines(keepends=True)
    out, para, fence, i = [], [], None, 0

    def flush():
        if para:
            text = "".join(para)
            body = text.rstrip("\n")
            out.append(translate_block(body) + text[len(body):])
            para.clear()

    if lines and lines[0].strip() == "---":       # YAML front matter: verbatim
        end = next((j for j in range(1, len(lines)) if lines[j].strip() in ("---", "...")), None)
        if end:
            out.extend(lines[:end + 1])
            i = end + 1
    for line in lines[i:]:
        if fence:                                 # inside a fenced block: verbatim
            out.append(line)
            c = re.fullmatch(r"\s*(`{3,}|~{3,})\s*", line)
            if c and c.group(1)[0] == fence[0] and len(c.group(1)) >= len(fence):
                fence = None
            continue
        m = FENCE.match(line)
        if m:
            flush()
            fence = m.group(1)
            out.append(line)
        elif not line.strip() or REFDEF.match(line):
            flush()
            out.append(line)
        else:
            para.append(line)
    flush()
    return "".join(out)

def main(src_dir, dst_dir):
    src_dir, dst_dir = pathlib.Path(src_dir), pathlib.Path(dst_dir)
    for f in sorted(src_dir.rglob("*.md")):
        dst = dst_dir / f.relative_to(src_dir)
        if dst.exists() and dst.stat().st_mtime >= f.stat().st_mtime:
            continue                              # already translated: run is resumable
        print(f"translating {f}", file=sys.stderr)
        result = translate_doc(f.read_text(encoding="utf-8"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(result, encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: md2ptpt.py SRC_DIR DST_DIR")
    main(sys.argv[1], sys.argv[2])
```

## 3. First run

```bash
# Try one small subfolder first:
python3 md2ptpt.py docs/getting-started docs-pt-PT/getting-started

# Then the whole tree. It can be stopped and re-run; finished files are skipped.
nohup python3 md2ptpt.py docs docs-pt-PT > translate.log 2>&1 &
grep '!' translate.log      # paragraphs kept in English because placeholders were lost
```

The output folder has the same layout as the source and the source files are never changed. Each paragraph is sent separately, so long documents don't overflow the model's context.

## 4. Check the output

```bash
# a) Fenced code blocks must match byte for byte
for f in $(cd docs && find . -name '*.md'); do
  diff -q <(awk '/^[[:space:]]*(```|~~~)/{f=!f;print;next} f' "docs/$f") \
          <(awk '/^[[:space:]]*(```|~~~)/{f=!f;print;next} f' "docs-pt-PT/$f") >/dev/null \
    || echo "CODE DIFFERS: $f"
done

# b) The set of URLs must match
for f in $(cd docs && find . -name '*.md'); do
  diff -q <(grep -oE 'https?://[^ )>"]+' "docs/$f" | sort) \
          <(grep -oE 'https?://[^ )>"]+' "docs-pt-PT/$f" | sort) >/dev/null || echo "URLS DIFFER: $f"
done

# c) Find Brazilian Portuguese wording that slipped through
grep -rniwE 'você|arquivo|tela|usuário|baixar|senha|registro|deletar|equipe|celular' docs-pt-PT/
grep -rniE '\b(está|estão|estamos|estou) [a-zà-ú]+ndo\b' docs-pt-PT/   # gerund → "estar a + infinitivo"
```

Have someone in the Lisbon office review the results. They can also extend the vocabulary list in `SYSTEM` with your company's terms.

---

## Things to know

- **Speed:** a 9B model on CPU is slow. Expect very roughly 3–8 tokens per second, so a few minutes per page of prose. A large folder is a job to leave running overnight. The 16 GB of RAM is enough.
- **Not covered by the script:** code blocks marked only by 4‑space indentation (they get translated as prose) and links whose label is a reference (`[text][id]`). The `[id]: url` definition lines themselves stay untouched. Table structure is kept, but check wide tables.
- **Privacy:** Ollama only listens on localhost. After the model download you can block the box's outbound traffic and everything still works.
- **Backup model:** [TranslateGemma](https://arxiv.org/abs/2601.09012) from Google is a translation model that one app built on it says handles pt‑PT separately from pt‑BR. A community tool pulls it as `translategemma:12b` (about 8 GB at 4‑bit). To use it, change `MODEL` and use the prompt format from its model card. I couldn't confirm the exact pt‑PT target code or how good its European Portuguese is, and its license is Gemma's own terms, not an OSI open-source license.
- **Not recommended for this:** NLLB has only one Portuguese target, and Argos Translate's en→pt output tends toward Brazilian Portuguese, which is the problem you already hit.

Sources:
- [AMALIA GitHub](https://github.com/AMALIA-LLM/AMALIA) · [AMALIA technical report (arXiv 2603.26511)](https://arxiv.org/abs/2603.26511) · [AMALIA‑9B‑1225‑SFT on HF](https://huggingface.co/amalia-llm/AMALIA-9B-1225-SFT) · [Portugal Global on AMALIA](https://portugalglobal.pt/en/trade/international-promotion/portugal-is-the-official-partner-country-of-the-smart-country-convention-2026/amalia-artificial-intelligence-multimodal-language-agent/) · [tech-insider on AMALIA](https://tech-insider.org/fr/portugal-amalia-llm-souverainete-2026/)
- GGUF builds: [layerx-labs DPO](https://huggingface.co/layerx-labs/AMALIA-9B-0626-DPO-GGUF) · [layerx-labs SFT](https://huggingface.co/layerx-labs/AMALIA-9B-0626-SFT-GGUF) · [teex-pt DPO](https://huggingface.co/teex-pt/AMALIA-9B-0626-DPO-GGUF) · [KikoCis SFT](https://huggingface.co/KikoCis/AMALIA-9B-0626-SFT-GGUF) · [NoxNotreve SFT](https://huggingface.co/NoxNotreve/AMALIA-9B-0626-SFT-GGUF)
- TranslateGemma: [arXiv 2601.09012](https://arxiv.org/abs/2601.09012?context=cs) · [Neowin](https://www.neowin.net/amp/google-unveils-translategemma-a-new-family-of-translation-models-built-on-gemma/) · [gemma-translator CLI](https://gh.hhj520.top/arrase/gemma-translator) · [Takkie Translate dataset card](https://huggingface.co/datasets/vbookshelf/Takkie-Translate-Offline-TDA) · [juliangoldie.com](https://juliangoldie.com/translate-gemma/) · [European Portuguese MT paper (arXiv 2502.14385)](https://web3.arxiv.org/pdf/2502.14385)