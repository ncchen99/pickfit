**Recommendation:** Run a quantized Qwen2.5-7B-Instruct locally with `llama.cpp`'s `llama-server`, and drive it with a short Python script. The script masks code and URLs before translating, restores them afterward, and applies a pt-PT spelling and vocabulary filter. Nothing leaves the box.

I'm assuming an x86_64 Linux box with no GPU and Python 3, and that you have sudo to install packages. I haven't run anything here, and I haven't measured pt-PT quality for any model. Test on a few pages before the full batch.

**Why not the pickfit result:** The only match was HilbertRaum. It's a GUI app rather than a terminal batch tool, its document translation needs a ~13 GB model that is too heavy for 16 GB of RAM on CPU, and its docs don't say it preserves code blocks or URLs. pickfit's check only confirmed that it installs and starts.

## Install (on the Linux box)

```bash
sudo apt install -y build-essential cmake git python3-venv
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp && cmake -B build && cmake --build build -j --config Release

python3 -m venv ~/mt-venv && ~/mt-venv/bin/pip install requests

mkdir -p ~/models && cd ~/models
# Q4_K_M is about 4.7 GB. If the repo splits the file, point the server at part 00001.
~/mt-venv/bin/pip install -U huggingface_hub
~/mt-venv/bin/hf download Qwen/Qwen2.5-7B-Instruct-GGUF --include "*q4_k_m*" --local-dir .
```

## First run

```bash
# Terminal 1: start the local model server
~/llama.cpp/build/bin/llama-server -m ~/models/qwen2.5-7b-instruct-q4_k_m*.gguf \
  -c 4096 -t $(nproc) --port 8080

# Terminal 2: check it answers
curl -s http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Traduz para português europeu: The file is saved."}]}'
```

## Translation script

Save as `~/translate_docs.py`. Run it with `~/mt-venv/bin/python ~/translate_docs.py ./docs-en ./docs-pt-PT`.

```python
#!/usr/bin/env python3
import re, sys, pathlib, requests

SRC, DST = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
API = "http://127.0.0.1:8080/v1/chat/completions"
SYSTEM = ("Traduz do inglês para português europeu (pt-PT). Usa ortografia e vocabulário de Portugal "
          "(Acordo Ortográfico de 1990). Nunca uses português do Brasil. Mantém a formatação Markdown. "
          "Os marcadores ⟦n⟧ ficam exatamente como estão. Devolve apenas a tradução.")
PROTECT = re.compile(r"(`[^`\n]+`|https?://[^\s)>\]]+|\]\([^)\n]*\)|<[^>\n]+>)")
FENCE = re.compile(r"^(```|~~~)")
PT_PT = [(r"\barquivo", "ficheiro"), (r"\busuário", "utilizador"), (r"\btela\b", "ecrã"),
         (r"\bsalvar\b", "guardar"), (r"\bequipe\b", "equipa"), (r"\bdeletar\b", "eliminar"),
         (r"\bsenha\b", "palavra-passe"), (r"\bcelular\b", "telemóvel"), (r"\bmouse\b", "rato"),
         (r"\bbanco de dados\b", "base de dados")]  # extend with your glossary

def ask(text):
    r = requests.post(API, json={"messages": [{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": text}], "temperature": 0.2}, timeout=600)
    return r.json()["choices"][0]["message"]["content"].strip()

def translate_line(line):
    slots = []
    def stash(m):
        slots.append(m.group(0))
        return f"⟦{len(slots) - 1}⟧"
    masked = PROTECT.sub(stash, line)           # hide code, URLs, link targets, HTML
    if not re.search(r"[A-Za-z]", masked):      # nothing left to translate
        return line
    out = ask(masked)
    for pat, rep in PT_PT:                      # pt-BR -> pt-PT filter on prose only
        out = re.sub(pat, rep, out)
    if sorted(re.findall(r"⟦(\d+)⟧", out)) != sorted(str(i) for i in range(len(slots))):
        print("placeholder mismatch, kept original:", line[:70], file=sys.stderr)
        return line                             # fail safe: keep English rather than mangle
    return re.sub(r"⟦(\d+)⟧", lambda m: slots[int(m.group(1))], out)

def translate_file(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    out, fence, front = [], False, False
    for i, line in enumerate(lines):
        if i == 0 and line == "---":            # YAML front matter: copy untouched
            front = True
        elif front:
            front = line != "---"
        elif FENCE.match(line):                 # fenced code: toggle and copy
            fence = not fence
        elif fence or not line.strip() or line.startswith(("    ", "\t")):
            pass                                # code, blank, or indented code: copy
        else:
            out.append(translate_line(line))
            continue
        out.append(line)
    return "\n".join(out)

for src in SRC.rglob("*.md"):
    dst = DST / src.relative_to(SRC)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(translate_file(src), encoding="utf-8")
    print("done", dst)
```

## Caveats

- **Dialect:** The prompt, the spelling filter and the glossary reduce Brazilian drift. They don't eliminate it. A native pt-PT reviewer should check the output, especially pronouns (tu/você) and verb forms.
- **Safe failure:** If the model drops or changes a placeholder, the script keeps the English line and prints a warning. Grep the output for lines that stayed in English.
- **Speed:** Expect several minutes per long page on CPU. Run the batch overnight.
- **Test first:** Run the script on one or two files and diff them against the source. Confirm that fences, inline code, URLs and front matter are byte-identical before running the full folder.

Sources:
- [HilbertRaum repository](https://github.com/HilbertraumAI/HilbertRaum)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [Qwen2.5-7B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF)