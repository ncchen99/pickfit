"""q16: the Markdown reading shared by build_manifest.py, md_check.py,
lang_check.py and meaning/make_judge_input.py. Input and output files are
read the same way, so a rule never favours one side.

Blocks (CommonMark-like, only what the checks need):
  code       a fenced block: an opening fence of 3+ backticks or tildes
             (up to 3 spaces of indent), up to the closing fence of the same
             character and at least the same length, both lines included,
             kept byte for byte; an unclosed fence runs to the end of file
  heading    an ATX heading line (# .. ######), outside code
  refdef     lines of the form [label]: URL
  list       a block whose first line starts with -, *, + or 1. / 1)
  paragraph  any other run of non-blank lines
"Prose blocks" are paragraphs and lists, in file order.

Python 3.9+ standard library only.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from collections import Counter

FENCE_OPEN = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]|$)")
LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+")
BULLET = re.compile(r"^ {0,3}[-*+][ \t]+")
REFDEF = re.compile(r"^ {0,3}\[([^\]]+)\]:[ \t]*<?([^\s>]+)>?(?:[ \t]+.*)?$")
INLINE_LINK = re.compile(r"(!?)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
REF_LINK = re.compile(r"(!?)\[([^\]]*)\]\[([^\]]*)\]")
AUTOLINK = re.compile(r"<((?:https?|ftp|mailto):[^>\s]+)>")
BARE_URL = re.compile(r"(?:https?|ftp)://[^\s<>()\[\]]+")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")
NUMBER = re.compile(r"(?<!\d)\d+(?!\d)")
EN_WORD = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
ANY_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")

PRODUCT_NAMES = ("Quillstack", "Tarnwave", "Mossgate")
VARIANT_FILE = "02-team-handbook.md"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()


def read(path: str) -> str:
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8", "surrogateescape")


def _lines(text: str) -> list:
    return re.findall(r"[^\n]*\n|[^\n]+$", text)


def parse_blocks(text: str) -> list:
    lines = _lines(text)
    blocks = []
    cur = None

    def flush():
        nonlocal cur
        if cur:
            blocks.append(_classify(cur))
        cur = None

    i = 0
    while i < len(lines):
        bare = lines[i].rstrip("\r\n")
        m = FENCE_OPEN.match(bare)
        if m and not (m.group(2)[0] == "`" and "`" in m.group(3)):
            flush()
            ch, n = m.group(2)[0], len(m.group(2))
            close = re.compile(r"^ {0,3}" + re.escape(ch) + "{%d,}[ \t]*$" % n)
            j = i + 1
            while j < len(lines) and not close.match(lines[j].rstrip("\r\n")):
                j += 1
            end = min(j, len(lines) - 1)
            blocks.append({"kind": "code", "text": "".join(lines[i:end + 1]), "line": i + 1})
            i = end + 1
            continue
        if not bare.strip():
            flush()
        elif HEADING.match(bare):
            flush()
            blocks.append({"kind": "heading", "text": bare.strip(), "line": i + 1})
        else:
            if cur is None:
                cur = {"lines": [], "line": i + 1}
            cur["lines"].append(bare)
        i += 1
    flush()
    return blocks


def _classify(cur: dict) -> dict:
    lines = cur["lines"]
    text = "\n".join(lines)
    if all(REFDEF.match(ln) for ln in lines):
        return {"kind": "refdef", "text": text, "line": cur["line"],
                "urls": [REFDEF.match(ln).group(2) for ln in lines]}
    if LIST_ITEM.match(lines[0]):
        items, bullets = [], []
        for ln in lines:
            if LIST_ITEM.match(ln):
                items.append(LIST_ITEM.sub("", ln, count=1))
                bullets.append(bool(BULLET.match(ln)))
            elif items:
                items[-1] += " " + ln.strip()
        return {"kind": "list", "text": text, "line": cur["line"], "items": items, "bullet": bullets}
    return {"kind": "paragraph", "text": text, "line": cur["line"]}


def urls_in(text: str) -> list:
    """Link destinations in one prose block or heading: inline links and
    images, autolinks, then bare URLs in what is left."""
    found = [m.group(3) for m in INLINE_LINK.finditer(text)]
    rest = INLINE_LINK.sub(" ", text)
    found += AUTOLINK.findall(rest)
    rest = AUTOLINK.sub(" ", rest)
    rest = CODE_SPAN.sub(" ", rest)
    found += [u.rstrip(".,;:!?'\"") for u in BARE_URL.findall(rest)]
    return found


def plain(text: str, keep_code: bool = True) -> str:
    """Prose without Markdown syntax: link text kept, URLs dropped, code span
    contents kept (or dropped), emphasis markers removed, whitespace
    collapsed, Unicode NFC."""
    text = INLINE_LINK.sub(lambda m: m.group(2), text)
    text = REF_LINK.sub(lambda m: m.group(2), text)
    text = AUTOLINK.sub(" ", text)
    text = CODE_SPAN.sub((lambda m: m.group(2)) if keep_code else " ", text)
    text = BARE_URL.sub(" ", text)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<!\w)[*_](\S(?:.*?\S)?)[*_](?!\w)", r"\1", text)
    text = re.sub(r"^ {0,3}#{1,6}[ \t]*", "", text, flags=re.M)
    return " ".join(unicodedata.normalize("NFC", text).split())


def analyze(text: str) -> dict:
    blocks = parse_blocks(text)
    prose = [b for b in blocks if b["kind"] in ("paragraph", "list")]
    urls = []
    for b in blocks:
        if b["kind"] in ("paragraph", "list", "heading"):
            urls += urls_in(b["text"])
        elif b["kind"] == "refdef":
            urls += b["urls"]
    units = []
    for b in blocks:
        if b["kind"] == "list":
            units += b["items"]  # list markers (1. 2. -) are not numbers
        elif b["kind"] in ("paragraph", "heading"):
            units.append(b["text"])
    prose_plain = " ".join(plain(u, keep_code=False) for u in units)
    bullets = []
    for b in prose:
        if b["kind"] == "list":
            bullets += [it for it, is_b in zip(b["items"], b["bullet"]) if is_b]
    return {
        "blocks": blocks,
        "code_blocks": [b["text"] for b in blocks if b["kind"] == "code"],
        "headings": sum(1 for b in blocks if b["kind"] == "heading"),
        "urls": urls,
        "prose": prose,
        "numbers": Counter(NUMBER.findall(prose_plain)),
        "names": Counter({n: len(re.findall(r"(?<!\w)%s(?!\w)" % re.escape(n), prose_plain)) for n in PRODUCT_NAMES}),
        "bullets": bullets,
        "search_text": " ".join(plain(b["text"]) for b in blocks if b["kind"] in ("paragraph", "list", "heading")),
    }


def english_words(sentence: str) -> int:
    return sum(1 for w in EN_WORD.findall(sentence) if w not in PRODUCT_NAMES)


def sentences(prose: list) -> list:
    """(block index, sentence index, text) for every prose sentence; list
    items are split one by one."""
    out = []
    for bi, b in enumerate(prose):
        units = b["items"] if b["kind"] == "list" else [b["text"]]
        si = 0
        for unit in units:
            for s in re.split(r"(?<=[.!?])\s+(?=\S)", plain(unit)):
                s = s.strip()
                if s:
                    out.append((bi, si, s))
                    si += 1
    return out


def lang_text(block: dict) -> str:
    """Text handed to the language identifier: prose without code, URLs,
    product names or numbers."""
    units = block["items"] if block["kind"] == "list" else [block["text"]]
    text = " ".join(plain(u, keep_code=False) for u in units)
    for n in PRODUCT_NAMES:
        text = re.sub(r"(?<!\w)%s(?!\w)" % re.escape(n), " ", text)
    text = NUMBER.sub(" ", text)
    return " ".join(text.split())


def word_count(text: str) -> int:
    return len(ANY_WORD.findall(text))


def list_md(folder: str) -> list:
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(".md"):
                out.append(os.path.join(root, f))
    return sorted(out)


def map_outputs(input_dir: str, output_dir: str, overrides=None) -> dict:
    """Input file name -> output path (or None). An output for X.md is a .md
    file under output_dir named X.md or starting with X followed by '.', '_'
    or '-'; a file byte-identical to the untranslated input is not an output.
    Several candidates: those with 'pt' in the name win; still several ->
    ambiguous (the grader passes --map)."""
    overrides = overrides or {}
    inputs = sorted(f for f in os.listdir(input_dir) if f.endswith(".md"))
    cands = list_md(output_dir)
    result = {}
    for name in inputs:
        if name in overrides:
            result[name] = {"path": overrides[name], "how": "override"}
            continue
        stem = name[:-3]
        original = read(os.path.join(input_dir, name))
        mine = []
        for c in cands:
            base = os.path.basename(c)
            if base == name or (base.startswith(stem) and len(base) > len(stem) and base[len(stem)] in "._-"):
                if os.path.abspath(c) == os.path.abspath(os.path.join(input_dir, name)) and read(c) == original:
                    continue
                if read(c) == original:
                    continue
                mine.append(c)
        if len(mine) > 1:
            pt = [c for c in mine if "pt" in os.path.basename(c).lower()[len(stem):]]
            mine = pt if len(pt) == 1 else mine
        if len(mine) == 1:
            result[name] = {"path": mine[0], "how": "name"}
        elif not mine:
            result[name] = {"path": None, "how": "missing"}
        else:
            result[name] = {"path": None, "how": "ambiguous", "candidates": mine}
    return result
