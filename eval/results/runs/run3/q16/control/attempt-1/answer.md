I haven't run anything on this machine. Below is my recommendation, plus a script I wrote for you but haven't tested.

## Recommendation: TranslateGemma 12B on Ollama, with a script that protects code and URLs

**Why this setup:**
- **It can target European Portuguese.** TranslateGemma is Google's open translation model, released January 2026. Its Ollama page lists **`pt-PT` and `pt-BR` as separate target codes**. General chat models drift into Brazilian Portuguese because most of their Portuguese training data is Brazilian. Giving TranslateGemma an explicit `pt-PT` target is the best lever you have.
- **It fits your machine.** `translategemma:12b` is an 8.1 GB download and runs on CPU within 16 GB RAM. `translategemma:4b` (3.3 GB) is about 3× faster but lower quality.
- **It runs entirely offline.** Ollama listens only on `127.0.0.1`. After the one-time model download, nothing leaves the box.
- **The model never sees code blocks or URLs.** You shouldn't rely on the model to leave them alone. The script below copies fenced code blocks and YAML front matter through unchanged. Before translation, it swaps inline code, link targets, bare URLs and HTML tags for placeholders like `⟦0⟧`, then puts the originals back. If any placeholder goes missing, it keeps that paragraph in English and logs it, so it never writes a damaged link.

**Assumptions:** the docs are UTF-8 `.md` files, code is in fenced blocks (```` ``` ```` / `~~~`), and Python 3.8+ is installed. The script uses only the standard library, so there's nothing to `pip install`.

### Install
```bash
# 1. Ollama (official Linux installer; read the script first if your policy requires it)
curl -fsSL https://ollama.com/install.sh | sh
#    The installer sets up a systemd service. If yours didn't, run `ollama serve` in another terminal.

# 2. Download the model once (this is the only network step)
ollama pull translategemma:12b

# 3. Quick check that you get European Portuguese
ollama run translategemma:12b "You are a professional English (en) to European Portuguese (pt-PT) translator. Produce only the European Portuguese translation, without any additional explanations or commentary. Please translate the following English text into European Portuguese:


Save the file and restart the screen session to apply the user settings."
```
In the output, look for European forms like **ficheiro, ecrã, utilizador, guardar**. Brazilian forms would be *arquivo, tela, usuário, salvar*.

### The batch script: save as `translate_md.py`
```python
#!/usr/bin/env python3
"""Translate a tree of Markdown files EN -> pt-PT with a local Ollama model.
Fenced code, front matter, inline code, URLs and HTML are passed through verbatim."""
import json, re, sys, urllib.request
from pathlib import Path

MODEL = "translategemma:12b"
OLLAMA = "http://127.0.0.1:11434/api/generate"
PROMPT = ("You are a professional English (en) to European Portuguese (pt-PT) translator. "
          "Your goal is to accurately convey the meaning and nuances of the original English text "
          "while adhering to European Portuguese grammar, vocabulary, and cultural sensitivities.\n"
          "Produce only the European Portuguese translation, without any additional explanations "
          "or commentary. Keep every token like ⟦0⟧ exactly as it is. "
          "Please translate the following English text into European Portuguese:\n\n\n{text}")

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
PREFIX = re.compile(r"^(\s*(?:#{1,6}\s+|>\s?|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)*)(.*)$")
VERBATIM = re.compile(r"^\s*(\[[^\]]+\]:\s|<|\|?\s*:?-{3,}|[-*_]{3,}\s*$)")  # ref defs, HTML, table rules, hr
INDENTED_CODE = re.compile(r"^( {4,}|\t)(?![-*+]\s|\d+[.)]\s)")
MASK = re.compile(r"(`+).+?\1"                                              # inline code
                  r"|\]\((?:[^()\s]|\([^()\s]*\))*(?:\s+\"[^\"]*\")?\)"     # ](url "title")
                  r"|\]\[[^\]]*\]"                                          # ][ref]
                  r"|<[^>\n]+>"                                             # autolinks / HTML tags
                  r"|https?://[^\s<>()\[\]]+")                              # bare URLs
URL = re.compile(r"https?://[^\s<>()\[\]\"']+")
BR_HINTS = re.compile(r"\b(você|vocês|arquivos?|telas?|usuários?|gerenciar|registro|equipe|celular)\b"
                      r"|\b(est(?:á|ão|ou|amos|ava))\s+\w+ndo\b", re.I)


def llm(text, temperature):
    body = json.dumps({"model": MODEL, "prompt": PROMPT.format(text=text), "stream": False,
                       "options": {"temperature": temperature}}).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)["response"].strip()


def translate(text):
    if not re.search(r"[A-Za-z]", MASK.sub("", text)):
        return text  # nothing translatable (pure code/URL/number)
    saved = []
    def keep(m):
        saved.append(m.group(0))
        return f"⟦{len(saved) - 1}⟧"
    masked = MASK.sub(keep, text)
    for attempt in range(3):
        out = llm(masked, 0 if attempt == 0 else 0.4)
        if all(out.count(f"⟦{i}⟧") == 1 for i in range(len(saved))):
            return re.sub(r"⟦(\d+)⟧", lambda m: saved[int(m.group(1))], out)
    print(f"  ! placeholders lost, kept English: {text[:70]}", file=sys.stderr)
    return text


def translate_md(src):
    lines, out, para, fence, i = src.split("\n"), [], None, None, 0

    def flush():
        nonlocal para
        if para:
            out.append(para[0] + translate(" ".join(para[1])))
        para = None

    if lines and lines[0].strip() == "---":  # YAML front matter: copy verbatim
        end = next((j for j in range(1, len(lines)) if lines[j].strip() in ("---", "...")), 0)
        out += lines[:end + 1]
        i = end + 1
    for line in lines[i:]:
        m = FENCE.match(line)
        if fence:
            out.append(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        if m:
            flush(); fence = m.group(1); out.append(line); continue
        if not line.strip() or VERBATIM.match(line) or (para is None and INDENTED_CODE.match(line)):
            flush(); out.append(line); continue
        if line.lstrip().startswith("|"):  # table row: translate cell by cell
            flush(); out.append("|".join(translate(c) if c.strip() else c for c in line.split("|"))); continue
        prefix, rest = PREFIX.match(line).groups()
        if para and not prefix.strip():
            para[1].append(rest.strip())  # hard-wrapped continuation line
        else:
            flush(); para = (prefix, [rest.strip()])
    flush()
    return "\n".join(out)


def main(src_dir, dst_dir):
    src_dir, dst_dir = Path(src_dir), Path(dst_dir)
    for f in sorted(src_dir.rglob("*.md")):
        dst = dst_dir / f.relative_to(src_dir)
        if dst.exists():
            continue  # resumable: delete an output file to redo it
        print(f"→ {f}", file=sys.stderr)
        src = f.read_text(encoding="utf-8")
        result = translate_md(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(result, encoding="utf-8")
        if sorted(URL.findall(src)) != sorted(URL.findall(result)):
            print(f"  ! URL mismatch in {dst}", file=sys.stderr)
        for n, l in enumerate(result.split("\n"), 1):
            if BR_HINTS.search(l):
                print(f"  ? possible pt-BR {dst}:{n}: {l.strip()[:80]}", file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:3])
```

### First run
```bash
# Try a small sample first
mkdir -p /tmp/pilot && cp docs/some-doc.md docs/another.md /tmp/pilot/
python3 -I translate_md.py /tmp/pilot /tmp/pilot-pt 2> pilot.log
cat pilot.log                        # "!" = kept English or URL mismatch, "?" = possible Brazilian wording
diff <(grep -n '```' /tmp/pilot/some-doc.md) <(grep -n '```' /tmp/pilot-pt/some-doc.md)

# Then the whole folder (it can resume, so Ctrl-C and rerun is safe)
nohup python3 -I translate_md.py ./docs ./docs-pt-PT 2> translate.log &
tail -f translate.log
```
Have someone in the Lisbon office review the pilot output before you run the full folder.

### Things to expect
- **Speed:** the 12B model on CPU is slow, roughly a few words per second. A large folder is an overnight job. To go faster, set `MODEL = "translategemma:4b"`.
- **How it rewrites Markdown:** hard-wrapped paragraphs come out as one line each, which renders the same. Link titles and reference labels stay in English because they're protected along with the URLs. Indented (non-fenced) code blocks are kept only when they follow a blank line.
- **Placeholders:** if the log shows many "placeholders lost" lines, the model is changing the `⟦n⟧` markers. Switch the marker style (for example to `<x0/>`) in `keep()` and in the restore regex.
- **The "possible pt-BR" check is only a rough word list, not a judgement.** Have a reviewer look at the lines it flags.
- **Unverified:** I confirmed that Ollama lists `pt-PT` as a target, but I haven't seen independent measurements of TranslateGemma's European Portuguese quality. The pilot is the real test.

### Alternatives
- **Unbabel Tower-Plus-9B.** Unbabel is a Lisbon company, and the model card's own example prompt translates into Portuguese (Portugal). It's a good second choice, but I found no official GGUF/Ollama build, so you'd rely on a community conversion. I believe its license is non-commercial (CC-BY-NC-SA). Check that before using it for company docs. To use it, change `MODEL` and the prompt.
- **I don't recommend Argos Translate / LibreTranslate.** They only offer a generic "pt" model, which has the same Brazilian bias you've already seen.

Sources:
- [Ollama – translategemma (tags, prompt template, pt-PT code)](https://ollama.com/library/translategemma)
- [TranslateGemma technical report (arXiv 2601.09012)](https://arxiv.org/abs/2601.09012?context=cs)
- [Neowin – Google unveils TranslateGemma](https://www.neowin.net/amp/google-unveils-translategemma-a-new-family-of-translation-models-built-on-gemma/)
- [Takkie Translate (pt-BR vs pt-PT variants claim)](https://huggingface.co/datasets/vbookshelf/Takkie-Translate-Offline-TDA)
- [gemma-translator (ollama pull translategemma usage)](https://gh.hhj520.top/arrase/gemma-translator)
- [Tower-Plus-9B model card mirror](https://hf-2025.pages.dev/Unbabel/Tower-Plus-9B)
- [Tower-Plus-9B README (raw)](https://hf-mirror.492719920.workers.dev/Unbabel/Tower-Plus-9B/raw/main/README.md)