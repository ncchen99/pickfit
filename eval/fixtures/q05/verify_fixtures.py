#!/usr/bin/env python3
"""Check that fixture.docx and fixture.pdf carry exactly the content of content.json.

    python3 verify_fixtures.py [--docx fixture.docx] [--pdf fixture.pdf]

DOCX: block order, heading styles with outline levels 0/1, a 3x4 table whose first row is
a header row, bullet numbering on the three list paragraphs, no title in the properties.
PDF:  one page, every font embedded (FontFile2) with a ToUnicode CMap, no Type3 fonts, and
the text layer (decoded with this script's own small parser) contains every block's text
in reading order. Prints sha256 of both files. Exit 0 when everything holds.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
import zlib
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def expected_sequence(blocks):
    seq = []
    for b in blocks:
        if b["type"] == "heading":
            seq.append(("heading%d" % b["level"], b["text"]))
        elif b["type"] == "paragraph":
            seq.append(("paragraph", b["text"]))
        elif b["type"] == "table":
            for i, r in enumerate([b["header"]] + b["rows"]):
                seq.append(("table_header" if i == 0 else "table_row", tuple(r)))
        elif b["type"] == "list":
            seq += [("bullet", it) for it in b["items"]]
    return seq


def verify_docx(path, blocks):
    errs = []
    z = zipfile.ZipFile(path)
    doc = ET.fromstring(z.read("word/document.xml"))
    styles = ET.fromstring(z.read("word/styles.xml"))
    numbering = ET.fromstring(z.read("word/numbering.xml"))
    core = z.read("docProps/core.xml").decode("utf-8")
    if "<dc:title>" in core:
        errs.append("docProps/core.xml has a title")
    lvls = {}
    for st in styles.findall(W + "style"):
        o = st.find(W + "pPr/" + W + "outlineLvl")
        if o is not None:
            lvls[st.get(W + "styleId")] = int(o.get(W + "val"))
    if lvls.get("Heading1") != 0 or lvls.get("Heading2") != 1:
        errs.append("heading styles missing outline levels: %r" % lvls)
    fmt = numbering.find(".//" + W + "lvl/" + W + "numFmt")
    if fmt is None or fmt.get(W + "val") != "bullet":
        errs.append("numbering is not a bullet list")

    def ptext(p):
        return "".join(t.text or "" for t in p.iter(W + "t"))

    got = []
    for el in doc.find(W + "body"):
        if el.tag == W + "p":
            ps = el.find(W + "pPr/" + W + "pStyle")
            style = ps.get(W + "val") if ps is not None else ""
            num = el.find(W + "pPr/" + W + "numPr") is not None
            kind = {"Heading1": "heading1", "Heading2": "heading2"}.get(style, "bullet" if num else "paragraph")
            got.append((kind, ptext(el)))
        elif el.tag == W + "tbl":
            for tr in el.findall(W + "tr"):
                hdr = tr.find(W + "trPr/" + W + "tblHeader") is not None
                cells = tuple(ptext(tc) for tc in tr.findall(W + "tc"))
                got.append(("table_header" if hdr else "table_row", cells))
    want = expected_sequence(blocks)
    if got != want:
        errs.append("docx block sequence differs:\n  got  %r\n  want %r" % (got, want))
    return errs


def pdf_objects(data):
    objs = {}
    for m in re.finditer(rb"(\d+) 0 obj\s*(.*?)\s*endobj", data, re.S):
        body = m.group(2)
        sm = re.search(rb"stream\r?\n(.*)\r?\nendstream", body, re.S)
        stream = None
        if sm:
            stream = sm.group(1)
            if b"/FlateDecode" in body[:sm.start()]:
                stream = zlib.decompress(stream)
            body = body[:sm.start()]
        objs[int(m.group(1))] = (body, stream)
    return objs


def ref(body, key):
    m = re.search(rb"/" + key + rb"\s+(\d+) 0 R", body)
    return int(m.group(1)) if m else None


def verify_pdf(path, blocks):
    errs = []
    data = open(path, "rb").read()
    objs = pdf_objects(data)
    pages = [n for n, (b, _) in objs.items() if re.search(rb"/Type\s*/Page\b", b)]
    if len(pages) != 1:
        errs.append("expected 1 page, found %d" % len(pages))
        return errs, ""
    if re.search(rb"/Subtype\s*/Type3", data):
        errs.append("Type3 font present")
    if re.search(rb"/StructTreeRoot|/Outlines|/Title", data):
        errs.append("PDF has tags, outline or a title")
    page = objs[pages[0]][0]
    fonts = dict((k.decode(), int(v)) for k, v in re.findall(rb"/(F\d+)\s+(\d+) 0 R", page))
    maps = {}
    for name, num in fonts.items():
        body = objs[num][0]
        desc_font = int(re.search(rb"/DescendantFonts\s*\[\s*(\d+) 0 R", body).group(1))
        fd = ref(objs[desc_font][0], b"FontDescriptor")
        if fd is None or ref(objs[fd][0], b"FontFile2") is None:
            errs.append("font %s is not embedded" % name)
        tu = ref(body, b"ToUnicode")
        if tu is None:
            errs.append("font %s has no ToUnicode" % name)
            continue
        cmap = objs[tu][1].decode("ascii")
        maps[name] = dict((int(a, 16), bytes.fromhex(b).decode("utf-16-be"))
                          for a, b in re.findall(r"<([0-9A-F]{4})>\s*<([0-9A-F]+)>", cmap)
                          if a != "0000" or b != "FFFF")
    content = objs[ref(page, b"Contents")][1].decode("latin-1")
    lines, cur_font = [], None
    for m in re.finditer(r"/(F\d+)\s+[\d.]+\s+Tf|<([0-9A-Fa-f]*)>\s*Tj", content):
        if m.group(1):
            cur_font = m.group(1)
        else:
            hx = m.group(2)
            lines.append("".join(maps[cur_font].get(int(hx[i:i + 4], 16), "�")
                                 for i in range(0, len(hx), 4)))
    text = "\n".join(lines)
    if "�" in text:
        errs.append("unmapped glyph in text layer")
    flat = re.sub(r"\s+", "", text)
    pos = 0
    for kind, value in expected_sequence(blocks):
        parts = value if isinstance(value, tuple) else (value,)
        for part in parts:
            p = re.sub(r"\s+", "", part)
            i = flat.find(p, pos)
            if i < 0:
                errs.append("text not found in order in PDF text layer: %r" % part)
            else:
                pos = i + len(p)
    return errs, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", default=os.path.join(HERE, "content.json"))
    ap.add_argument("--docx", default=os.path.join(HERE, "fixture.docx"))
    ap.add_argument("--pdf", default=os.path.join(HERE, "fixture.pdf"))
    a = ap.parse_args()
    blocks = json.load(open(a.content, encoding="utf-8"))["blocks"]
    ok = True
    for label, path, fn in (("docx", a.docx, verify_docx), ("pdf", a.pdf, verify_pdf)):
        if not os.path.exists(path):
            print("%s: MISSING %s" % (label, path))
            ok = False
            continue
        res = fn(path, blocks)
        errs = res[0] if isinstance(res, tuple) else res
        print("%s: %s  sha256=%s  bytes=%d" % (label, "OK" if not errs else "FAIL", sha(path), os.path.getsize(path)))
        for e in errs:
            print("  - " + e)
        ok = ok and not errs
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
