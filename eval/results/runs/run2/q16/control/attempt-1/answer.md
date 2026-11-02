I recommend running **Tradutor**, an English-to-European-Portuguese model, locally with **llama.cpp**, driven by a small Python script. The script sends only prose to the model. Code blocks and URLs are never translated, and a check after each file confirms they came out unchanged.

I haven't run any of this on your machine, and I haven't run the script itself, so test it on a few files first.

## Why this setup

- **It targets European Portuguese specifically.** [liaad/Tradutor](https://huggingface.co/liaad/Tradutor) is an 8B Llama-3 model from LIAAD / INESC TEC in Portugal, trained only on English → pt-PT ([paper](https://arxiv.org/abs/2502.14385v1)). General models like NLLB or Llama default to Brazilian Portuguese; this one was built to avoid that.
- **It fits your hardware.** The repo includes a ready-made `model.gguf` of 8.54 GB ([file list](https://huggingface.co/liaad/Tradutor/tree/main)). Judging by the size, it's 8-bit, so it should fit in 16 GB of RAM and run on CPU with llama.cpp.
- **Your documents stay on the box.** After the one-time model download, the server listens only on 127.0.0.1.
- **Code and links are protected by the script, not left to the model.** Fenced blocks are copied as they are. Inline code, link targets `](...)`, bare URLs, HTML tags and table pipes are swapped for placeholders like `⟦0⟧` before translation and put back afterwards. If the model loses a placeholder, the script retries. If it still fails, that piece stays in English and is listed in a report. After each file, the script checks that the fenced code and the URL list match the source exactly.

## Install (one time)

```bash
# 1. Build llama.cpp (CPU)
sudo apt install -y git cmake build-essential python3
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp && cmake -B build && cmake --build build --config Release -j

# 2. Download the model (the only network step)
mkdir -p ~/models/tradutor
wget -O ~/models/tradutor/model.gguf \
  https://huggingface.co/liaad/Tradutor/resolve/main/model.gguf
```

## First run

**Terminal 1: start the local server**
```bash
~/llama.cpp/build/bin/llama-server -m ~/models/tradutor/model.gguf \
  --host 127.0.0.1 --port 8080 -c 4096 -t "$(nproc)"
```

**Terminal 2: try one file first**
```bash
mkdir -p /tmp/mdtest && cp docs/some-page.md /tmp/mdtest/
python3 md_translate_ptpt.py /tmp/mdtest /tmp/mdtest-pt
cat /tmp/mdtest-pt/translation-report.txt
```

Then run the whole folder. The output folder must not be inside the source folder:
```bash
python3 md_translate_ptpt.py ./docs ./docs-pt-PT
```

The script mirrors the folder structure and copies images and other non-Markdown files as they are. If you stop it, running it again skips files already done.

### `md_translate_ptpt.py`

Standard library only, so nothing to install:

```python
#!/usr/bin/env python3
"""Translate a folder of Markdown from English to European Portuguese using a
local llama-server. Fenced code blocks are copied verbatim; inline code, URLs,
link targets and HTML tags are masked so the model never sees them as text."""
import json, re, shutil, sys, urllib.request
from pathlib import Path

API = "http://127.0.0.1:8080/v1/chat/completions"
SYSTEM = "You are a translator from English to European Portuguese"
PROMPT = "Translate this text from English to European Portuguese: "

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
PREFIX = re.compile(r"^(\s*(?:#{1,6}\s+|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+|>\s?)*)")
STARTS_UNIT = re.compile(r"^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s|>|\|)")
VERBATIM = re.compile(r"^\s*(<|\[[^\]]+\]:\s|[-*_=|: ]+$)")  # HTML, link refs, rules, table separators
PROTECT = re.compile(
    r"(`+)[^\n]*?\1"          # inline code
    r"|\]\([^)\n]*\)"         # link/image targets: ](url "title")
    r"|<[^>\n]+>"             # autolinks and inline HTML
    r"|https?://[^\s)\]>]+"   # bare URLs
    r"|\|"                    # table pipes
)
URL = re.compile(r"https?://[^\s)\]>\"]+")


def mask(text):
    saved = []
    def keep(m):
        saved.append(m.group(0))
        return f"⟦{len(saved) - 1}⟧"
    return PROTECT.sub(keep, text), saved


def ask(text, temperature):
    body = json.dumps({
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": PROMPT + text}],
        "temperature": temperature, "max_tokens": 2048,
    }).encode()
    req = urllib.request.Request(API, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()


def translate(text):
    masked, saved = mask(text)
    tags = [f"⟦{i}⟧" for i in range(len(saved))]
    for temperature in (0.0, 0.3, 0.6):
        out = " ".join(ask(masked, temperature).splitlines())
        if all(out.count(t) == 1 for t in tags) and out.count("⟦") == len(tags):
            for t, original in zip(tags, saved):
                out = out.replace(t, original)
            return out, True
    return text, False


def translate_file(text, name, log):
    lines, out, unit, fence, start = text.splitlines(), [], [], None, 0
    prefix = ""

    def flush():
        if not unit:
            return
        joined = " ".join(s.strip() for s in unit)
        done = joined
        if re.search(r"[A-Za-z]", PROTECT.sub("", joined)):
            done, ok = translate(joined)
            if not ok:
                log.append(f"{name}: left in English: {joined[:100]}")
        out.append(prefix + done)
        unit.clear()

    if lines and lines[0].strip() == "---":  # YAML front matter: copy as-is
        end = next((j for j in range(1, len(lines)) if lines[j].strip() in ("---", "...")), None)
        if end:
            out.extend(lines[:end + 1])
            start = end + 1

    for line in lines[start:]:
        if fence:
            out.append(line)
            s = line.strip()
            if s.startswith(fence) and set(s) == {fence[0]}:
                fence = None
            continue
        m = FENCE.match(line)
        if m:
            flush()
            fence = m.group(1)
            out.append(line)
        elif not line.strip() or VERBATIM.match(line):
            flush()
            out.append(line)
        elif STARTS_UNIT.match(line) or not unit:
            flush()
            prefix = PREFIX.match(line).group(1)
            unit.append(line[len(prefix):])
        else:
            unit.append(line)  # wrapped continuation line
    flush()
    return "\n".join(out) + "\n"


def code_and_urls(text):
    code, fence = [], None
    for line in text.splitlines():
        s = line.strip()
        if fence:
            code.append(line)
            if s.startswith(fence) and set(s) == {fence[0]}:
                fence = None
        elif FENCE.match(line):
            fence = FENCE.match(line).group(1)
            code.append(line)
    return code, sorted(URL.findall(text))


def main(src_dir, dst_dir):
    src_dir, dst_dir, log = Path(src_dir), Path(dst_dir), []
    for src in sorted(p for p in src_dir.rglob("*") if p.is_file()):
        dst = dst_dir / src.relative_to(src_dir)
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() not in (".md", ".markdown"):
            shutil.copy2(src, dst)
            continue
        print(f"-> {src}", flush=True)
        source = src.read_text(encoding="utf-8")
        result = translate_file(source, src, log)
        if code_and_urls(source) != code_and_urls(result):
            log.append(f"{src}: CODE/URL MISMATCH - check manually")
        dst.write_text(result, encoding="utf-8")
    (dst_dir / "translation-report.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"Done. {len(log)} issue(s) in {dst_dir / 'translation-report.txt'}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
```

## After the run: check for Brazilian Portuguese

```bash
grep -rnwiE 'você|vocês|arquivo|tela|usuários?|celular|baixar|cadastr\w*' docs-pt-PT/
grep -rniE '\b(estou|está|estão|estamos) [a-zà-ú]+ndo\b' docs-pt-PT/   # BR gerund
```

In pt-PT these should be *ficheiro, ecrã, utilizador, transferir, registar*, and *"está a fazer"* instead of "está fazendo". Also ask someone in the Lisbon office to review a few pages, because I haven't seen how Tradutor handles your technical vocabulary.

## Assumptions and caveats

- **Speed:** with an 8-bit 8B model on CPU, expect a few tokens per second, roughly several minutes per page. That's fine for an overnight batch. For about 1.5–2× more speed with a small quality loss, you can shrink the model to 4-bit (`llama-quantize --allow-requantize model.gguf q4.gguf Q4_K_M`). Re-quantizing an already-compressed file loses a bit more quality than starting from the original weights.
- **What counts as code:** I assumed your code is in fenced blocks (```` ``` ```` / `~~~`) or inline backticks. Old-style indented code blocks (4-space indent) aren't detected. Lines that start with an HTML tag are copied untranslated.
- **What gets lost:** wrapped paragraphs come out as one line each, which renders the same in Markdown. URLs that contain parentheses may not be fully protected, but the mismatch check will flag them.
- **License:** the model card doesn't state a license. Because it's built on Llama 3, assume the Llama 3 Community License applies and check that for internal use.
- **Faster fallback:** [Helsinki-NLP/opus-mt-tc-big-en-pt](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-pt) is a much smaller translation model that's quick on CPU. You pick the variant with a `>>por<<` or `>>pob<<` prefix; `>>pob<<` is Brazilian in OPUS-MT naming. Its pt-PT output is less reliable and it would need the same masking script, so I'd only use it if Tradutor is too slow.
- **Alternative tool:** [mdpo](https://mondeja.github.io/mdpo/latest/cli.html) (`md2po`/`po2md`) also skips code blocks, but it rewrites the Markdown formatting and still leaves URLs inside the text to translate. The script above keeps your original layout.

Sources:
- [liaad/Tradutor model card](https://huggingface.co/liaad/Tradutor) · [file list](https://huggingface.co/liaad/Tradutor/tree/main)
- [Tradutor paper (arXiv 2502.14385)](https://arxiv.org/abs/2502.14385v1)
- [Helsinki-NLP/opus-mt-tc-big-en-pt](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-pt)
- [mdpo CLI docs](https://mondeja.github.io/mdpo/latest/cli.html)