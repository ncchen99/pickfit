I couldn't find a ready-made tool that does all of this, so I'd combine three free pieces. A small script handles the code blocks and URLs, and a European Portuguese model fixes the Brazilian Portuguese problem. My usual tool catalogue (pickfit) had nothing that fit this job, so this recommendation draws on web searches and my own knowledge.

## Recommendation: Ollama + AMALIA-9B + a ~100-line Python script

1. **Ollama** runs the model locally on your box. It works on CPU only and offers an HTTP API on `localhost` that scripts can call.
2. **AMALIA-9B** is an open model built specifically for European Portuguese (Portugal), funded by Portugal and built on top of EuroLLM-9B. Its technical report says it does better on European Portuguese tests than other open models of similar size ([paper](https://arxiv.org/abs/2603.26511), [GitHub](https://github.com/AMALIA-LLM/AMALIA), [model card](https://huggingface.co/amalia-llm/AMALIA-9B-0626-SFT)). Generic models default to Brazilian Portuguese because most of their Portuguese training text is Brazilian, so picking this model is the main fix for that problem.
   - **Fallback:** EuroLLM-9B-Instruct ([GGUF](https://huggingface.co/QuantFactory/EuroLLM-9B-Instruct-GGUF), [Ollama notes](https://korben.info/en/eurollm-european-llm-runs-on-laptop.html)). It was trained heavily on translation but isn't specific to Portugal.
3. **The script** keeps the model from touching code or links. Before anything reaches the model, it replaces fenced code blocks, YAML front matter, inline `code`, link targets, bare URLs, reference definitions and HTML with placeholders like `⟦3⟧`. After translation, it checks that every placeholder came back unchanged and puts the originals back. If the model drops a placeholder, the script retries, and if it still fails, it keeps that paragraph in English and prints a warning. Your code and URLs never go through the model at all.

**Assumptions:**
- You're on a recent x86_64 distro with Python 3.8 or newer.
- Your docs use fenced code blocks (```` ``` ```` or `~~~`). Old-style code blocks marked only by 4-space indentation are **not** protected.
- The Q4_K_M quantization (about 5.2–5.6 GB) fits easily in 16 GB of RAM.
- **Speed is a guess:** on CPU, expect roughly 5–10 words per second of output, so about 5–10 minutes for a 2,000-word document. The script can resume where it left off, so you can run it overnight.
- The AMALIA GGUF files are **community conversions** (for example [teex-pt](https://huggingface.co/teex-pt/AMALIA-9B-0626-DPO-GGUF) and [layerx-labs](https://huggingface.co/layerx-labs/AMALIA-9B-0626-DPO-GGUF)), not official releases. Check the file names on the repo page before pulling.

## Install

```bash
# 1. Ollama (official installer: needs sudo and sets up a systemd service).
#    Download and read the script before running it:
curl -fsSL https://ollama.com/install.sh -o ollama-install.sh
less ollama-install.sh && sh ollama-install.sh

# 2. Model (about 5 GB). The tag must match a quant file listed in the repo.
ollama pull hf.co/teex-pt/AMALIA-9B-0626-DPO-GGUF:Q4_K_M
#    Fallback:
# ollama pull hf.co/bartowski/EuroLLM-9B-Instruct-GGUF:Q4_K_M
```

Local Ollama models run entirely on your machine. If you want proof, block outbound traffic from the box once the model is downloaded.

## Quick dialect check

```bash
ollama run hf.co/teex-pt/AMALIA-9B-0626-DPO-GGUF:Q4_K_M \
  "Traduz para português europeu: The user is downloading the file; save it before closing the screen."
```

You want to see *utilizador*, *está a transferir*, *ficheiro*, *guarde/guarda* and *ecrã*. If you see *usuário*, *baixando*, *arquivo* or *tela*, the output is Brazilian.

## The script: save as `md2ptpt.py` (standard library only)

````python
#!/usr/bin/env python3
"""Translate a folder of Markdown EN -> pt-PT with a local Ollama model.
Fenced code, front matter, inline code, URLs and HTML are masked and restored verbatim."""
import json, re, shutil, sys, urllib.request
from pathlib import Path

MODEL = "hf.co/teex-pt/AMALIA-9B-0626-DPO-GGUF:Q4_K_M"
OLLAMA = "http://localhost:11434/api/chat"

SYSTEM = """És um tradutor profissional. Traduz o texto Markdown do inglês para português europeu (Portugal), nunca português do Brasil.
Regras:
- Vocabulário de Portugal: ficheiro, ecrã, utilizador, palavra-passe, transferir, partilhar, guardar, equipa, registo, aplicação.
- Usa "estar a + infinitivo" (ex.: "está a correr"), nunca o gerúndio.
- Colocação pronominal europeia (ex.: "configura-se", "envia-nos").
- Mantém exatamente a sintaxe Markdown (#, -, *, |, >, números de lista, **, _).
- Marcadores como ⟦0⟧, ⟦1⟧ são código ou URLs: copia-os exatamente, sem traduzir nem remover.
- Não traduzas nomes de produtos, comandos ou identificadores.
- Responde apenas com a tradução, sem comentários."""

MASKS = [
    re.compile(r"<!--.*?-->", re.S),                          # HTML comments
    re.compile(r"(`+)(?:(?!\1).)+?\1", re.S),                 # inline code
    re.compile(r"^[ \t]*\[[^\]]+\]:[ \t]*\S+.*$", re.M),      # [ref]: url "title"
    re.compile(r"(?<=\])\([^)\s]*(?:[ \t]+\"[^\"]*\")?\)"),    # ](url "title")
    re.compile(r"(?<=\])\[[^\]]*\]"),                         # ][ref]
    re.compile(r"<https?://[^>\s]+>"),                        # <autolinks>
    re.compile(r"</?[A-Za-z][^>\n]*>"),                       # inline HTML tags
    re.compile(r"https?://[^\s<>()\[\]]+"),                   # bare URLs
]
TOKEN = re.compile(r"⟦(\d+)⟧")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def mask(text):
    saved = []
    def keep(m):
        saved.append(m.group(0))
        return f"⟦{len(saved) - 1}⟧"
    for rx in MASKS:
        text = rx.sub(keep, text)
    return text, saved


def unmask(text, saved):
    for _ in range(5):  # tokens can nest when masks overlap
        new = TOKEN.sub(lambda m: saved[int(m.group(1))], text)
        if new == text:
            break
        text = new
    return text


def ask(text, temperature):
    body = json.dumps({
        "model": MODEL, "stream": False,
        "options": {"temperature": temperature, "num_ctx": 8192},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.load(r)["message"]["content"].strip()


def translate_block(block, where):
    masked, saved = mask(block)
    if not re.search(r"[A-Za-z]", TOKEN.sub("", masked)):
        return block  # nothing translatable
    indent = re.match(r"[ \t]*", block).group(0)
    for temperature in (0, 0.3, 0.6):
        out = ask(masked, temperature)
        if sorted(int(n) for n in TOKEN.findall(out)) == list(range(len(saved))):
            return indent + unmask(out, saved).lstrip()
    print(f"  WARN {where}: placeholders lost, kept English", file=sys.stderr)
    return block


def translate_file(src):
    lines = src.read_text(encoding="utf-8").splitlines()
    out, para, fence, start = [], [], None, 0
    if lines and lines[0].strip() == "---":  # YAML front matter stays verbatim
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                out, start = lines[:j + 1], j + 1
                break

    def flush():
        if para:
            out.append(translate_block("\n".join(para), f"{src}:{n}"))
            para.clear()

    for n, line in enumerate(lines[start:], start + 1):
        m = FENCE.match(line)
        if fence:
            out.append(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line.strip(" `~"):
                fence = None
        elif m:
            flush()
            fence = m.group(1)
            out.append(line)
        elif not line.strip():
            flush()
            out.append(line)
        else:
            para.append(line)
    flush()
    return "\n".join(out) + "\n"


def main(src_dir, dst_dir):
    src_dir, dst_dir = Path(src_dir), Path(dst_dir)
    for src in sorted(src_dir.rglob("*")):
        if not src.is_file():
            continue
        dst = dst_dir / src.relative_to(src_dir)
        if dst.exists():
            continue  # resumable: skip files already done
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() in (".md", ".markdown"):
            print(f"translating {src}", file=sys.stderr)
            tmp = dst.with_name(dst.name + ".part")
            tmp.write_text(translate_file(src), encoding="utf-8")
            tmp.replace(dst)
        else:
            shutil.copy2(src, dst)  # images etc. copied as-is


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: md2ptpt.py SRC_DIR DST_DIR")
    main(*sys.argv[1:])
````

## First run

```bash
# Try one small folder first. The output folder must NOT be inside the source folder.
mkdir -p /tmp/sample && cp docs/README.md /tmp/sample/
python3 md2ptpt.py /tmp/sample /tmp/sample-pt
less /tmp/sample-pt/README.md

# Then the whole folder (Ctrl-C is safe; re-run to resume):
python3 md2ptpt.py docs docs-pt 2> translate.log
grep WARN translate.log
```

## Check the output

````bash
# Code blocks unchanged? (prints only files whose fenced content differs)
cd docs && find . -name '*.md' | while read f; do
  cmp -s <(awk '/^ *(```|~~~)/{c=!c;print;next} c' "$f") \
         <(awk '/^ *(```|~~~)/{c=!c;print;next} c' "../docs-pt/$f") || echo "code changed: $f"
done; cd ..

# URLs unchanged?
diff <(grep -rhoE 'https?://[^ )>"]+' docs | sort) <(grep -rhoE 'https?://[^ )>"]+' docs-pt | sort) && echo "URLs identical"

# Brazilian Portuguese that slipped through
grep -rniwE 'arquivo|tela|usuário|senha|baixar|cadastro|celular' docs-pt
grep -rnoE '\b(está|estão|estou|estamos) [a-zà-ú]+ndo\b' docs-pt
````

## Limitations and tuning

- **Wording:** add your company's preferred terms to the vocabulary line in `SYSTEM`. This is the cheapest way to get consistent wording.
- **Quality vs. speed:** if quality is weak, try Q5_K_M (about 1 GB more RAM, slower). If AMALIA does badly on technical text, switch `MODEL` to EuroLLM and compare results on the same sample.
- **Link titles:** the script also protects link titles (`"title"` in `[x](url "title")`), so those stay in English.
- **Line wrapping:** the model may re-wrap long paragraphs onto different lines. That doesn't change how the Markdown renders.
- **Review:** have someone in the Lisbon office proofread before you publish. A 9B model will get most of the way there, but it won't be perfect.

Sources:
- [AMALIA technical report (arXiv)](https://arxiv.org/abs/2603.26511)
- [AMALIA GitHub](https://github.com/AMALIA-LLM/AMALIA)
- [AMALIA-9B-0626-SFT model card](https://huggingface.co/amalia-llm/AMALIA-9B-0626-SFT)
- [teex-pt/AMALIA-9B-0626-DPO-GGUF](https://huggingface.co/teex-pt/AMALIA-9B-0626-DPO-GGUF)
- [layerx-labs/AMALIA-9B-0626-DPO-GGUF](https://huggingface.co/layerx-labs/AMALIA-9B-0626-DPO-GGUF)
- [Portugal launches AMALIA (news)](https://letsdatascience.com/news/portugal-launches-amalia-open-source-portuguese-language-mod-d12ab37e)
- [QuantFactory/EuroLLM-9B-Instruct-GGUF](https://huggingface.co/QuantFactory/EuroLLM-9B-Instruct-GGUF)
- [Korben: EuroLLM on Ollama](https://korben.info/en/eurollm-european-llm-runs-on-laptop.html)