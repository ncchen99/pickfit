My recommendation is to use **mdpo** to handle the Markdown structure and **liaad/Tradutor** to do the translation, run locally through **Ollama** with a small script connecting the two. I haven't run any of this on your machine. Below I mark what I checked and what I'm assuming.

## Why this setup

- **It targets European Portuguese specifically.** [Tradutor](https://huggingface.co/liaad/Tradutor) is an English→European Portuguese model from LIAAD (University of Porto). It was trained on a large European Portuguese parallel corpus and tested with a classifier that tells European from Brazilian Portuguese ([paper](https://arxiv.org/abs/2502.14385v1)). General-purpose models are trained mostly on Brazilian text, which is why yours keep producing it. Tradutor is an 8B model whose card shows GGUF, Ollama and llama.cpp options. At Q4 it needs about 5 GB of RAM, so it fits in 16 GB on CPU.
- **The model never sees your code blocks.** [mdpo](https://mondeja.github.io/mdpo/latest/rationale.html) splits each Markdown file into translatable strings and leaves fenced code blocks out by default. It then rebuilds the Markdown from the original file plus the translations, so the code blocks are copied over byte for byte.
- **URLs are hidden from the model.** Before sending each string, the script swaps inline code, link targets and bare URLs for placeholders like `⟦0⟧`, and puts them back afterwards. If any placeholder goes missing, it keeps the English and marks the string `fuzzy` for review rather than writing broken output.
- **Bonus:** you get one `.po` translation file per document. When a doc changes, a re-run only translates the new strings. Lisbon staff can also fix wording in [Poedit](https://poedit.net/) without touching the Markdown.

## Install

```bash
# 1. Ollama (local LLM runtime)
curl -fsSL https://ollama.com/install.sh | sh

# 2. Get Tradutor as a 4-bit GGUF (about 5 GB)
ollama pull hf.co/liaad/Tradutor:Q4_K_M

# 3. Python tools
python3 -m venv ~/mdtrans && . ~/mdtrans/bin/activate
pip install mdpo polib
```

**Assumption:** the `:Q4_K_M` tag exists. The model card has a GGUF tag but doesn't list the quantization levels. If the pull fails, try `ollama pull hf.co/liaad/Tradutor` and pick a Q4 option from the model page. If that fails too, convert the model yourself with llama.cpp's `convert_hf_to_gguf.py` and `llama-quantize`.

## The script: `translate_po.py`

```python
#!/usr/bin/env python3
"""Fill empty msgstr entries in a PO file using local Tradutor via Ollama."""
import json, re, sys, urllib.request
import polib

MODEL = "hf.co/liaad/Tradutor:Q4_K_M"
API = "http://localhost:11434/api/chat"
# inline code, link/image targets "(url)", autolinks, bare URLs
PROTECT = re.compile(r"`[^`\n]+`|\]\([^)\s]+(?:\s+\"[^\"]*\")?\)|<https?://[^>]+>|https?://[^\s)>\]]+")

def llm(text):
    body = json.dumps({
        "model": MODEL, "stream": False,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": "You are a translator from English to European Portuguese"},
            {"role": "user", "content": "Translate this text from English to European Portuguese. "
             "Keep every ⟦n⟧ placeholder and all Markdown markup exactly as is. "
             f"Output only the translation: {text}"},
        ],
    }).encode()
    req = urllib.request.Request(API, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["message"]["content"].strip()

def translate(text):
    saved = []
    def mask(m):
        s = m.group(0)
        if s.startswith("]("):              # keep "]" visible, hide "(url)"
            saved.append(s[1:]); return f"]⟦{len(saved)-1}⟧"
        saved.append(s); return f"⟦{len(saved)-1}⟧"
    out = llm(PROTECT.sub(mask, text))
    for i, s in enumerate(saved):
        if out.count(f"⟦{i}⟧") != 1:
            return None                        # placeholder lost -> don't trust it
        out = out.replace(f"⟦{i}⟧", s)
    return out

po = polib.pofile(sys.argv[1])
for e in po:
    if e.msgstr or e.obsolete:
        continue
    t = translate(e.msgid)
    if t is None:
        e.msgstr = e.msgid
        e.flags.append("fuzzy")
        print(f"[fuzzy] {sys.argv[1]}: {e.msgid[:60]!r}", file=sys.stderr)
    else:
        e.msgstr = t
    po.save()   # save after each entry so an interrupted run can resume
```

## Batch run over the folder

The loop below assumes your source docs are in `docs/`. Output goes to `out/`, which mirrors the folder structure.

```bash
. ~/mdtrans/bin/activate
mkdir -p po out
find docs -name '*.md' -print0 | while IFS= read -r -d '' f; do
  rel=${f#docs/}; base=${rel%.md}
  mkdir -p "po/$(dirname "$rel")" "out/$(dirname "$rel")"
  md2po "$f" --po-filepath "po/$base.po" --save
  python3 translate_po.py "po/$base.po"
  po2md "$f" --pofiles "po/$base.po" --save "out/$rel"
done
```

Check the exact flag names with `md2po --help` and `po2md --help`, since they can differ between mdpo versions. Note that `md2po` and `po2md` also exist in translate-toolkit, but there code blocks are extracted unless you pass `--no-code-blocks`. Make sure the venv's mdpo versions are the ones on your PATH.

## First run: test before doing the whole folder

1. Try a single doc first. Diff the fences and URLs:
   `diff <(grep -E '^```|https?://' docs/x.md) <(grep -E '^```|https?://' out/x.md)`
   This should show no differences.
2. Spot-check for Brazilian Portuguese: `grep -rniE '\bvocê|\btela\b|arquivo|usuário|gerenciar|registro\b' out/`. The European forms are ficheiro, utilizador, ecrã, gerir and registo. Look out for "está fazendo"-style gerunds too; European Portuguese uses "está a fazer".
3. Open any entries marked `fuzzy` (they're listed on stderr) in Poedit and fix them by hand.

## Things to know

- **Speed:** an 8B Q4 model on CPU usually manages a few tokens per second. A long doc can take around 10 minutes, so run the full folder overnight. Because the script saves after every entry, an interrupted run picks up where it stopped.
- **Licence:** the Tradutor model card doesn't state a licence, and the model appears to be Llama-based. Have someone check the terms for internal company use.
- **YAML front matter and raw HTML** aren't handled well by mdpo. Strip front matter before translating and add it back afterwards, or check those files by hand.
- **Faster but weaker option:** [Helsinki-NLP/opus-mt-tc-big-en-pt](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-pt) via CTranslate2 is much faster on CPU. It has `>>por<<` and `>>pob<<` target tokens. I'm assuming `>>por<<` is European Portuguese and `pob` is Brazilian, because the card doesn't say. Its example output, "esfaquear-me", reads as European. You'd only need to change the `llm()` function to use it, but expect more Brazilian forms to slip through than with Tradutor.

Sources:
- [liaad/Tradutor on Hugging Face](https://huggingface.co/liaad/Tradutor)
- [Tradutor paper (arXiv 2502.14385)](https://arxiv.org/abs/2502.14385v1)
- [mdpo rationale](https://mondeja.github.io/mdpo/latest/rationale.html) · [mdpo CLI](https://mondeja.github.io/mdpo/latest/cli.html) · [mdpo releases](https://www.github.com/mondeja/mdpo/releases)
- [translate-toolkit md2po man page](https://dyn.manpages.debian.org/unstable/translate-toolkit/md2po.1.en.html)
- [Helsinki-NLP/opus-mt-tc-big-en-pt](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-pt)