## Recommendation

Use a **local LLM served by Ollama**, driven by a **small Python script** that protects code and URLs before translation. Use **EuroLLM-9B-Instruct** (Q4_K_M) as the primary model. It was built by Unbabel and IST in Lisbon and trained on European languages including Portuguese, so it is the best starting point for pt-PT. If you can't get its GGUF build, use **Qwen2.5-7B-Instruct** with the same prompt and glossary.

Neural MT engines like Argos, Opus-MT and NLLB are faster on CPU, but they have no pt-PT variant and tend to produce generic or Brazilian Portuguese. An instruction-tuned LLM can be told to write European Portuguese.

Expect slow throughput. A 9B Q4 model on a 16 GB CPU box probably generates a few tokens per second, so a large folder is an overnight job. Benchmark one file first. If it's too slow, the 3–4B-class model is the fallback.

**Assumptions:** Debian/Ubuntu-style Linux, Python 3.10+ installed, internet access only for the one-time install and model download. After that, everything runs offline. I haven't run anything here.

## Why this design handles code and URLs

Don't ask the model to leave code alone. Remove the protected parts before translation and put them back afterwards:

1. Copy fenced blocks (```` ``` ````/`~~~`), indented code, HTML blocks, and YAML front matter verbatim.
2. In prose, swap inline code, bare URLs, link targets `](...)`, and image paths for placeholders like `⟦0⟧`.
3. Translate each paragraph or list item separately, so the model keeps line structure and context stays small.
4. Restore the placeholders. If any are missing or duplicated, retry, then fall back to the English paragraph and flag it.
5. Verify each output file: fenced blocks must be byte-identical to the source, and the set of URLs must match.

## Install and first-run steps

```bash
# 1. Python env (only needs the requests library)
python3 -m venv ~/ptpt-tr
. ~/ptpt-tr/bin/activate
pip install requests

# 2. Ollama (review the install script before piping it to sh)
curl -fsSL https://ollama.com/install.sh | sh
ollama --version

# 3. Get the model (one-time download)
# Search Hugging Face for "EuroLLM-9B-Instruct GGUF" and pick the Q4_K_M file.
# Import it with a Modelfile, or use: ollama pull hf.co/<repo>:Q4_K_M
# Verify the exact repo name before pulling.
# Fallback: ollama pull qwen2.5:7b-instruct

# 4. Smoke test (should answer in European Portuguese)
ollama run <model> "Traduz para português europeu: 'Open the settings file and restart the service.'"
```

Quick check on memory and speed: keep the context window around 4096 tokens. The Q4 weights take about 6 GB, which leaves room on 16 GB.

## Core script outline

```python
# translate_docs.py: run from a directory outside the docs folder
import re, sys, pathlib, requests

MODEL = "euroLLM"  # the name you gave the model in Ollama
SYSTEM = (
    "Traduz de inglês para português europeu (pt-PT) de Portugal. "
    "Usa 'tu' ou a forma impessoal, 'ficheiro', 'ecrã', 'utilizador', 'palavra-passe', "
    "'autocarro', 'comboio', 'equipa', 'guardar', 'executar', 'gerir', 'contacto'. "
    "Nunca uses português do Brasil. Mantém os marcadores ⟦n⟧ exatamente como estão. "
    "Devolve apenas a tradução."
)
PROTECT = re.compile(r"(`[^`\n]+`|https?://\S+|\]\([^)]+\))")  # inline code, URLs, link targets
FENCE = re.compile(r"^(```|~~~).*?^\1\s*$", re.S | re.M)       # fenced blocks

def translate(text, glossary):
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": MODEL, "stream": False,
        "messages": [{"role": "system", "content": SYSTEM + "\nGlossário:\n" + glossary},
                     {"role": "user", "content": text}],
        "options": {"temperature": 0.2, "num_ctx": 4096}})
    return r.json()["message"]["content"].strip()

def process(src, dst, glossary):
    text = src.read_text(encoding="utf-8")
    parts = FENCE.split(text)  # alternates prose / fenced blocks
    ...  # protect inline spans, translate paragraphs, restore, verify
```

Complete the `process` function with the protect/restore logic from the steps above. Retry any paragraph that fails the placeholder check.

## Controls for pt-PT vs pt-BR

- **Glossary:** keep a CSV of EN→pt-PT terms (for example "file"→"ficheiro", "screen"→"ecrã", "user"→"utilizador", "password"→"palavra-passe", "bus"→"autocarro"). Inject the relevant entries into each prompt.
- **Regex lint:** after translation, flag Brazilian markers for human review. Examples: `você`, `ônibus`, `arquivo`, `tela`, `senha`, `usuário`, `celular`, `deletar`, `salvar`, `rodar`, `estou fazendo`, `trem`. Also flag `tu` mixed with `você` in one file.
- **Clitics:** pt-PT places pronouns after the verb ("envia-o", "diz-me"). Check a few samples.

## Limits to be aware of

- No model guarantees pt-PT. The glossary and lint reduce the risk but don't remove it.
- Get a native pt-PT speaker to review at least a sample of each doc type before publishing, especially for anything legal, contractual or customer-facing.
- Output is a draft. Diff the protected blocks and URLs automatically, but read the prose yourself.
- If you need the box to be verifiably offline, block its outbound traffic after the model is downloaded and check that the translation still works.

Sources: none. This answer is based on my own knowledge and I did not check the current model names or GGUF repos online, so verify them at install time.