pickfit had no tested tool that does this end to end, so this is my own recommendation. I haven't run any of it. Check the commands and model names before you rely on them.

## Recommendation: mdpo + llama.cpp + EuroLLM-9B-Instruct, with a short glue script

No local model reliably writes European Portuguese without help, and asking a model to leave code alone isn't dependable. So the setup doesn't trust the model with either. It has four parts:

1. **mdpo** (`md2po` / `po2md`) splits each Markdown file into translatable text segments. Fenced code blocks are left out by default, so the model never sees them. `po2md` then rebuilds the `.md` file with the code blocks copied unchanged.
2. **A masking step** replaces link URLs, inline `` `code` ``, autolinks and HTML tags with placeholders like `⟦0⟧` before any text goes to the model. They're put back afterwards. If any placeholder is missing, the segment is retried and then left in English and flagged. URLs are never changed.
3. **llama.cpp's `llama-server`** runs on CPU with a 4-bit 9B model, which uses about 6 GB of RAM. It provides a local OpenAI-style API on `localhost`, so nothing leaves the machine.
4. **Getting European Portuguese:** a strict pt-PT system prompt with examples, then a fixed list of Brazilian→European word swaps, then a report of leftover Brazilian forms for a reviewer in Lisbon.

**Model choice:** I'd start with **EuroLLM-9B-Instruct**. It's from a consortium led by Unbabel (Lisbon), trained for translation, and Apache-2.0. **Tower-Plus-9B** (also Unbabel) is a good second option. **Gervásio** and **AMALIA** are models trained specifically on European Portuguese and are worth trying if the prompt doesn't fix the Brazilian drift. I'm less sure which GGUF builds of those are available. Expect roughly 3–8 tokens/second on CPU, so a large folder is a job to run overnight.

## Install

```bash
# 1. llama.cpp: download the prebuilt Ubuntu x64 zip from
#    https://github.com/ggml-org/llama.cpp/releases (llama-bXXXX-bin-ubuntu-x64.zip)
unzip llama-*-bin-ubuntu-x64.zip -d ~/llama.cpp

# 2. Python tools in a venv
python3 -m venv ~/mdtr
~/mdtr/bin/pip install mdpo polib requests
```

## First run

**Start the model server** (it downloads the GGUF from Hugging Face the first time; check the exact repo name, which is my assumption):
```bash
~/llama.cpp/build/bin/llama-server -hf bartowski/EuroLLM-9B-Instruct-GGUF:Q4_K_M \
  -c 4096 -t $(nproc) --host 127.0.0.1 --port 8080
```

**Save this as `translate_po.py`:**
```python
import re, sys, polib, requests

API = "http://127.0.0.1:8080/v1/chat/completions"
SYSTEM = """You are a professional translator into EUROPEAN Portuguese (Portugal, pt-PT), never Brazilian.
Use pt-PT spelling, vocabulary and grammar: ficheiro, ecrã, utilizador, transferir, guardar, palavra-passe,
equipa, registo, "estar a + infinitivo" (never gerund), "tu/o utilizador" register, clitics after the verb ("configura-se").
Tokens like ⟦0⟧ are placeholders: copy them exactly, do not translate, drop or reorder their content.
Output only the translation."""
SHOTS = [
    ("Click **Save** to download the file ⟦0⟧.", "Clique em **Guardar** para transferir o ficheiro ⟦0⟧."),
    ("The user is running the script on screen.", "O utilizador está a executar o script no ecrã."),
]
MASK = re.compile(r"`[^`]+`|\]\([^)]*\)|<https?://[^>]+>|https?://[^\s)>\]]+|<[^>]+>")
BR2PT = {r"\barquivos?\b": lambda m: "ficheiros" if m.group().endswith("s") else "ficheiro",
         r"\btela\b": "ecrã", r"\busuári(o|os|a|as)\b": lambda m: "utilizador" + {"o":"","os":"es","a":"a","as":"as"}[m.group(1)],
         r"\bsenha\b": "palavra-passe", r"\bequipe\b": "equipa", r"\bbaixar\b": "transferir",
         r"\bsalvar\b": "guardar", r"\bregistro\b": "registo", r"\bcelular\b": "telemóvel"}
BR_FLAGS = re.compile(r"\b\w+(ando|endo|indo)\b|\bvocê\b|\bpra\b|\btrem\b", re.I)

def translate(text):
    toks = []
    masked = MASK.sub(lambda m: (toks.append(m.group()), f"⟦{len(toks)-1}⟧")[1], text)
    msgs = [{"role": "system", "content": SYSTEM}]
    for en, pt in SHOTS:
        msgs += [{"role": "user", "content": en}, {"role": "assistant", "content": pt}]
    msgs.append({"role": "user", "content": masked})
    for _ in range(3):
        out = requests.post(API, json={"messages": msgs, "temperature": 0}).json()["choices"][0]["message"]["content"].strip()
        if all(out.count(f"⟦{i}⟧") == 1 for i in range(len(toks))):
            for pat, rep in BR2PT.items():
                out = re.sub(pat, rep, out)
            for i, t in enumerate(toks):
                out = out.replace(f"⟦{i}⟧", t)
            return out
    return None  # placeholders lost: keep English, flag

po = polib.pofile(sys.argv[1])
for e in po:
    if e.msgstr: continue
    t = translate(e.msgid)
    if t is None:
        e.flags.append("fuzzy"); print(f"[KEEP-EN] {e.msgid[:70]}", file=sys.stderr); continue
    e.msgstr = t
    if BR_FLAGS.search(t):
        print(f"[CHECK-PT] {t[:90]}", file=sys.stderr)
po.save()
```

**Translate the whole folder** (`docs/` in, `docs-pt/` out, with the same structure):
```bash
source ~/mdtr/bin/activate
find docs -name '*.md' | while read -r f; do
  rel=${f#docs/}; mkdir -p "po/$(dirname "$rel")" "docs-pt/$(dirname "$rel")"
  md2po "$f" --wrapwidth 0 -q -s --po-filepath "po/${rel%.md}.po"
  python translate_po.py "po/${rel%.md}.po" 2>>review.log
  po2md "$f" --pofiles "po/${rel%.md}.po" --wrapwidth 0 -q -s "docs-pt/$rel"
done
```

Run `md2po --help` and `po2md --help` first. I've written the flags from memory, and they differ between mdpo versions.

## Notes
- **Code blocks never reach the model**, and URLs and inline code are checked before the result is saved. A wrong guess by the model can't get into those parts.
- **Re-runs only translate what's new or changed.** The script skips segments that already have a translation, and `md2po` keeps those when you run it again. Your Lisbon reviewers can also fix wording directly in the `.po` files (Poedit works well for this) and rebuild without translating again.
- **`review.log`** lists segments that stayed in English (`[KEEP-EN]`) and sentences that may still be Brazilian (`[CHECK-PT]`, mainly gerunds and "você"). Plan on a quick human check of those.
- **`po2md` may change some Markdown formatting** without changing what it says, for example list markers or emphasis style. Diff one file against the original before running the full batch.
- **Other options I considered:** Argos Translate and OPUS-MT are lighter and faster, but they have no European Portuguese model, so you'd see the same Brazilian Portuguese problem.