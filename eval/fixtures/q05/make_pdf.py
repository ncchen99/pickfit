#!/usr/bin/env python3
"""Write fixture.pdf from content.json with an embedded CJK font subset (stdlib only).

    python3 make_pdf.py --font REGULAR.ttf [--bold-font BOLD.ttf] [--font-index N]
                        [--content content.json] [--out fixture.pdf]

The font must have TrueType outlines (a 'glyf' table: .ttf, or a .ttc collection with
--font-index). CFF-outline .otf files are refused. Variable TrueType fonts work: the
default outlines are embedded and the variation tables are dropped. Which font file to use
is decided by 念誠 (see needs.json); the font is not committed, only the PDF that embeds a
subset of it.

The PDF is a one-page A4, text-based PDF: every character is real text drawn with an
embedded TrueType subset (Type0 / CIDFontType2, Identity-H) and a ToUnicode CMap, so the
text layer maps back to Unicode. Headings are larger and bold (the bold font if given,
otherwise the regular font with fill+stroke), the table has ruled borders and a shaded
header row, and the list uses a bullet glyph with a hanging indent. The PDF has no tags,
no outline (bookmarks) and no /Title, so structure must be inferred from the page itself.
Output is deterministic for a given font file.
"""

import argparse
import hashlib
import json
import os
import struct
import sys
import zlib

PAGE_W, PAGE_H = 595.276, 841.89
MARGIN = 72.0
CONTENT_W = PAGE_W - 2 * MARGIN
BODY_SIZE, BODY_LEAD = 10.5, 16.0
H1_SIZE, H2_SIZE = 20.0, 15.0
TABLE_COLS = [96.0, 118.0, 78.0, CONTENT_W - 96.0 - 118.0 - 78.0]
ROW_H, CELL_PAD = 22.0, 6.0
BULLET_CANDIDATES = ["•", "‧", "・", "·"]


def u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def i16(b, o):
    return struct.unpack_from(">h", b, o)[0]


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


class TrueType:
    def __init__(self, path, index=0):
        with open(path, "rb") as fh:
            self.data = data = fh.read()
        self.path = path
        base = 0
        if data[:4] == b"ttcf":
            n = u32(data, 8)
            if index >= n:
                sys.exit("font collection has %d fonts; --font-index %d is out of range" % (n, index))
            base = u32(data, 12 + 4 * index)
        sfnt = data[base:base + 4]
        if sfnt == b"OTTO":
            sys.exit("%s has CFF outlines; use a TrueType-outline (.ttf with glyf) font" % path)
        if sfnt not in (b"\x00\x01\x00\x00", b"true"):
            sys.exit("%s is not a TrueType font" % path)
        self.tables = {}
        for i in range(u16(data, base + 4)):
            rec = base + 12 + 16 * i
            tag = data[rec:rec + 4].decode("latin-1")
            self.tables[tag] = (u32(data, rec + 8), u32(data, rec + 12))
        for need in ("head", "hhea", "maxp", "hmtx", "loca", "glyf", "cmap"):
            if need not in self.tables:
                sys.exit("%s lacks the %r table" % (path, need))
        head = self.t("head")
        self.upem = u16(head, 18)
        self.bbox = [i16(head, 36), i16(head, 38), i16(head, 40), i16(head, 42)]
        self.loc_long = i16(head, 50) == 1
        hhea = self.t("hhea")
        self.ascent, self.descent = i16(hhea, 4), i16(hhea, 6)
        self.n_hmetrics = u16(hhea, 34)
        self.num_glyphs = u16(self.t("maxp"), 4)
        self.cap_height = int(self.ascent * 0.7)
        if "OS/2" in self.tables:
            os2 = self.t("OS/2")
            if u16(os2, 0) >= 2 and len(os2) >= 90:
                self.cap_height = i16(os2, 88) or self.cap_height
        self.cmap = self._read_cmap()
        self.ps_name = self._ps_name()
        self.variable = "fvar" in self.tables
        self.weight_class = u16(self.t("OS/2"), 4) if "OS/2" in self.tables else None
        if self.variable:
            sys.stderr.write("warning: %s is a variable font; only its default instance (OS/2 weight "
                             "class %s) is embedded. Prefer static Regular/Bold files.\n"
                             % (path, self.weight_class))

    def t(self, tag):
        off, ln = self.tables[tag]
        return self.data[off:off + ln]

    def _ps_name(self):
        if "name" not in self.tables:
            return "FixtureFont"
        nm = self.t("name")
        count, str_off = u16(nm, 2), u16(nm, 4)
        for i in range(count):
            r = 6 + 12 * i
            pid, eid, _lang, nid, ln, off = struct.unpack_from(">6H", nm, r)
            if nid != 6:
                continue
            raw = nm[str_off + off:str_off + off + ln]
            try:
                s = raw.decode("utf-16-be") if pid in (0, 3) else raw.decode("latin-1")
            except UnicodeDecodeError:
                continue
            s = "".join(ch for ch in s if ch.isalnum() or ch in "-_")
            if s:
                return s
        return "FixtureFont"

    def _read_cmap(self):
        cm = self.t("cmap")
        subs = {}
        for i in range(u16(cm, 2)):
            pid, eid, off = struct.unpack_from(">HHI", cm, 4 + 8 * i)
            subs[(pid, eid)] = off
        for key in ((3, 10), (0, 4), (0, 6), (3, 1), (0, 3), (0, 1), (0, 0)):
            if key in subs:
                off = subs[key]
                fmt = u16(cm, off)
                if fmt in (4, 12):
                    return (fmt, cm, off)
        sys.exit("no usable Unicode cmap (format 4 or 12) in %s" % self.path)

    def gid(self, ch):
        fmt, cm, off = self.cmap
        c = ord(ch)
        if fmt == 12:
            n = u32(cm, off + 12)
            for i in range(n):
                s, e, g = struct.unpack_from(">III", cm, off + 16 + 12 * i)
                if s <= c <= e:
                    return g + (c - s)
            return 0
        if c > 0xFFFF:
            return 0
        seg2 = u16(cm, off + 6)
        ends = off + 14
        starts = ends + seg2 + 2
        deltas = starts + seg2
        ranges = deltas + seg2
        for i in range(seg2 // 2):
            end = u16(cm, ends + 2 * i)
            if c > end:
                continue
            start = u16(cm, starts + 2 * i)
            if c < start:
                return 0
            delta = u16(cm, deltas + 2 * i)
            ro = u16(cm, ranges + 2 * i)
            if ro == 0:
                return (c + delta) & 0xFFFF
            g = u16(cm, ranges + 2 * i + ro + 2 * (c - start))
            return (g + delta) & 0xFFFF if g else 0
        return 0

    def glyph(self, g):
        loca = self.t("loca")
        if self.loc_long:
            a, b = u32(loca, 4 * g), u32(loca, 4 * g + 4)
        else:
            a, b = 2 * u16(loca, 2 * g), 2 * u16(loca, 2 * g + 2)
        goff = self.tables["glyf"][0]
        return self.data[goff + a:goff + b]

    def metric(self, g):
        hm = self.t("hmtx")
        if g < self.n_hmetrics:
            return u16(hm, 4 * g), i16(hm, 4 * g + 2)
        adv = u16(hm, 4 * (self.n_hmetrics - 1))
        return adv, i16(hm, 4 * self.n_hmetrics + 2 * (g - self.n_hmetrics))

    def advance(self, ch):
        return self.metric(self.gid(ch))[0]


def composite_components(data):
    comps, pos = [], 10
    while True:
        flags, g = u16(data, pos), u16(data, pos + 2)
        comps.append(g)
        pos += 4 + (4 if flags & 0x1 else 2)
        if flags & 0x8:
            pos += 2
        elif flags & 0x40:
            pos += 4
        elif flags & 0x80:
            pos += 8
        if not flags & 0x20:
            return comps


def strip_glyph(data, remap):
    """Drop hinting instructions; renumber composite components."""
    if not data:
        return b""
    n = i16(data, 0)
    if n >= 0:
        ilen = u16(data, 10 + 2 * n)
        return data[:10 + 2 * n] + b"\x00\x00" + data[12 + 2 * n + ilen:]
    out, pos = bytearray(data[:10]), 10
    while True:
        flags, g = u16(data, pos), u16(data, pos + 2)
        size = 4 + (4 if flags & 0x1 else 2)
        if flags & 0x8:
            size += 2
        elif flags & 0x40:
            size += 4
        elif flags & 0x80:
            size += 8
        out += struct.pack(">HH", flags & ~0x100, remap[g]) + data[pos + 4:pos + size]
        pos += size
        if not flags & 0x20:
            return bytes(out)


def checksum(b):
    b = b + b"\0" * (-len(b) % 4)
    return sum(struct.unpack(">%dI" % (len(b) // 4), b)) & 0xFFFFFFFF


def build_subset(font, chars):
    """Return (ttf_bytes, cid_of_char, advances_by_cid)."""
    old = {0}
    cid_old = {}
    missing = []
    for ch in sorted(set(chars)):
        g = font.gid(ch)
        if g == 0 and ch != "\0":
            missing.append(ch)
        old.add(g)
        cid_old[ch] = g
    if missing:
        sys.exit("font %s has no glyph for: %s" % (font.path, " ".join(
            "%s(U+%04X)" % (c, ord(c)) for c in missing)))
    todo = list(old)
    while todo:
        g = todo.pop()
        d = font.glyph(g)
        if d and i16(d, 0) < 0:
            for c in composite_components(d):
                if c not in old:
                    old.add(c)
                    todo.append(c)
    order = sorted(old)
    remap = {g: i for i, g in enumerate(order)}
    glyf, loca = bytearray(), [0]
    hmtx = bytearray()
    advances = []
    for g in order:
        d = strip_glyph(font.glyph(g), remap)
        glyf += d + b"\0" * (-len(d) % 4)
        loca.append(len(glyf))
        adv, lsb = font.metric(g)
        hmtx += struct.pack(">Hh", adv, lsb)
        advances.append(adv)
    n = len(order)
    head = bytearray(font.t("head"))
    struct.pack_into(">I", head, 8, 0)
    struct.pack_into(">h", head, 50, 1)
    hhea = bytearray(font.t("hhea"))
    struct.pack_into(">H", hhea, 34, n)
    maxp = bytearray(font.t("maxp"))
    struct.pack_into(">H", maxp, 4, n)
    if len(maxp) >= 32:
        for off in (16, 18, 20, 22, 24, 26):
            struct.pack_into(">H", maxp, off, 0)
    # cmap: one (3,1) format 4 subtable, one segment per character
    pairs = sorted((ord(ch), remap[g]) for ch, g in cid_old.items() if ord(ch) <= 0xFFFF)
    segs = [(c, c, (gid - c) & 0xFFFF) for c, gid in pairs] + [(0xFFFF, 0xFFFF, 1)]
    sc = len(segs)
    sr = 2 * (1 << (sc.bit_length() - 1))
    es = sr.bit_length() - 2
    sub = struct.pack(">HHHHHHH", 4, 0, 0, 2 * sc, sr, es, 2 * sc - sr)
    sub += b"".join(struct.pack(">H", e) for _, e, _ in segs) + b"\0\0"
    sub += b"".join(struct.pack(">H", s) for s, _, _ in segs)
    sub += b"".join(struct.pack(">H", d) for _, _, d in segs)
    sub += b"\0\0" * sc
    sub = sub[:2] + struct.pack(">H", len(sub)) + sub[4:]
    cmap = struct.pack(">HHHHI", 0, 1, 3, 1, 12) + sub
    post = bytearray(font.t("post")[:32]) if "post" in font.tables else bytearray(32)
    struct.pack_into(">I", post, 0, 0x00030000)
    tables = {
        "head": bytes(head), "hhea": bytes(hhea), "maxp": bytes(maxp), "hmtx": bytes(hmtx),
        "loca": b"".join(struct.pack(">I", x) for x in loca), "glyf": bytes(glyf),
        "cmap": cmap, "post": bytes(post),
    }
    for keep in ("OS/2", "name"):
        if keep in font.tables:
            tables[keep] = font.t(keep)
    tags = sorted(tables)
    nt = len(tags)
    sr = 16 * (1 << (nt.bit_length() - 1))
    es = (1 << (nt.bit_length() - 1)).bit_length() - 1
    out = bytearray(struct.pack(">IHHHH", 0x00010000, nt, sr, es, 16 * nt - sr))
    offset = 12 + 16 * nt
    body = bytearray()
    for tag in tags:
        tb = tables[tag]
        out += tag.encode("latin-1") + struct.pack(">III", checksum(tb), offset + len(body), len(tb))
        body += tb + b"\0" * (-len(tb) % 4)
    ttf = bytearray(out + body)
    head_off = offset + sum(len(tables[t]) + (-len(tables[t]) % 4) for t in tags[:tags.index("head")])
    struct.pack_into(">I", ttf, head_off + 8, (0xB1B0AFBA - checksum(bytes(ttf))) & 0xFFFFFFFF)
    cid = {ch: remap[g] for ch, g in cid_old.items()}
    return bytes(ttf), cid, advances


class PdfFont:
    def __init__(self, name, font, chars, fake_bold=False):
        self.name, self.font, self.fake_bold = name, font, fake_bold
        self.ttf, self.cid, self.adv = build_subset(font, chars)

    def width(self, text, size):
        return sum(self.adv[self.cid[ch]] for ch in text) * size / self.font.upem

    def hex(self, text):
        return "".join("%04X" % self.cid[ch] for ch in text)


def is_cjk(ch):
    o = ord(ch)
    return (0x2E80 <= o <= 0x9FFF) or (0xF900 <= o <= 0xFAFF) or (0xFF00 <= o <= 0xFFEF) or o >= 0x20000


NO_LINE_START = set("。，、：；！？）」』〉》,.;:!?)")


def wrap(text, pf, size, width):
    units, word = [], ""
    for ch in text:
        if ch == " ":
            if word:
                units.append(word)
                word = ""
            units.append(" ")
        elif is_cjk(ch):
            if word:
                units.append(word)
                word = ""
            units.append(ch)
        else:
            word += ch
    if word:
        units.append(word)
    lines, cur = [], ""
    for u in units:
        if cur and pf.width((cur + u).rstrip(), size) > width and u != " " and u not in NO_LINE_START:
            lines.append(cur.rstrip())
            cur = "" if u == " " else u
        else:
            cur = "" if (not cur and u == " ") else cur + u
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


class Page:
    def __init__(self):
        self.ops = []

    def text(self, pf, size, x, y, s):
        if not s:
            return
        if pf.fake_bold:
            self.ops.append("BT /%s %.2f Tf 2 Tr %.3f w 1 0 0 1 %.2f %.2f Tm <%s> Tj 0 Tr ET"
                            % (pf.name, size, size * 0.035, x, y, pf.hex(s)))
        else:
            self.ops.append("BT /%s %.2f Tf 1 0 0 1 %.2f %.2f Tm <%s> Tj ET" % (pf.name, size, x, y, pf.hex(s)))

    def rect_fill(self, x, y, w, h, gray):
        self.ops.append("%.2f g %.2f %.2f %.2f %.2f re f 0 g" % (gray, x, y, w, h))

    def line(self, x1, y1, x2, y2, w=0.6):
        self.ops.append("%.2f w %.2f %.2f m %.2f %.2f l S" % (w, x1, y1, x2, y2))


def layout(blocks, reg, bold):
    pg = Page()
    y = PAGE_H - MARGIN
    for b in blocks:
        t = b["type"]
        if t == "heading":
            size = H1_SIZE if b["level"] == 1 else H2_SIZE
            if pg.ops:
                y -= 10 if b["level"] == 2 else 0
            if bold.width(b["text"], size) > CONTENT_W:
                sys.exit("heading does not fit on one line: %r" % b["text"])
            y -= size * 1.15
            pg.text(bold, size, MARGIN, y, b["text"])
            y -= size * 0.6
        elif t == "paragraph":
            for ln in wrap(b["text"], reg, BODY_SIZE, CONTENT_W):
                y -= BODY_LEAD
                pg.text(reg, BODY_SIZE, MARGIN, y, ln)
            y -= 8
        elif t == "table":
            y -= 4
            rows = [b["header"]] + b["rows"]
            top = y
            for r, cells in enumerate(rows):
                pf = bold if r == 0 else reg
                if r == 0:
                    pg.rect_fill(MARGIN, y - ROW_H, CONTENT_W, ROW_H, 0.88)
                x = MARGIN
                for c, cell in enumerate(cells):
                    if pf.width(cell, BODY_SIZE) > TABLE_COLS[c] - 2 * CELL_PAD:
                        sys.exit("table cell does not fit on one line: %r" % cell)
                    pg.text(pf, BODY_SIZE, x + CELL_PAD, y - ROW_H + 7.0, cell)
                    x += TABLE_COLS[c]
                y -= ROW_H
            bottom = y
            for r in range(len(rows) + 1):
                yy = top - r * ROW_H
                pg.line(MARGIN, yy, MARGIN + CONTENT_W, yy, 0.9 if r in (0, 1, len(rows)) else 0.6)
            x = MARGIN
            for c in range(len(TABLE_COLS) + 1):
                pg.line(x, top, x, bottom, 0.6)
                if c < len(TABLE_COLS):
                    x += TABLE_COLS[c]
            y -= 14
        elif t == "list":
            bullet = layout.bullet
            for item in b["items"]:
                lines = wrap(item, reg, BODY_SIZE, CONTENT_W - 22)
                for i, ln in enumerate(lines):
                    y -= BODY_LEAD
                    if i == 0:
                        pg.text(reg, BODY_SIZE, MARGIN + 8, y, bullet)
                    pg.text(reg, BODY_SIZE, MARGIN + 22, y, ln)
            y -= 8
        else:
            sys.exit("unknown block type %r" % t)
        if y < MARGIN:
            sys.exit("content does not fit on one page")
    return "\n".join(pg.ops).encode("ascii")


def tounicode(pf):
    lines = ["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
             "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
             "/CMapName /Adobe-Identity-UCS def", "/CMapType 2 def",
             "1 begincodespacerange", "<0000> <FFFF>", "endcodespacerange"]
    items = sorted((cid, ch) for ch, cid in pf.cid.items())
    for i in range(0, len(items), 100):
        chunk = items[i:i + 100]
        lines.append("%d beginbfchar" % len(chunk))
        for cid, ch in chunk:
            lines.append("<%04X> <%s>" % (cid, ch.encode("utf-16-be").hex().upper()))
        lines.append("endbfchar")
    lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
    return "\n".join(lines).encode("ascii")


def build_pdf(blocks, reg, bold):
    content = layout(blocks, reg, bold)
    objs = {}
    fonts = [reg] if bold is reg else [reg, bold]
    nxt = [5]

    def new():
        nxt[0] += 1
        return nxt[0] - 1

    font_refs = {}
    for pf in fonts:
        o_type0, o_cid, o_desc, o_file, o_tu = new(), new(), new(), new(), new()
        tag = "".join(chr(65 + b % 26) for b in hashlib.sha256(pf.ttf).digest()[:6])
        base = "%s+%s" % (tag, pf.font.ps_name)
        scale = 1000.0 / pf.font.upem
        widths = " ".join("%d" % round(a * scale) for a in pf.adv)
        f = pf.font
        objs[o_type0] = ("<< /Type /Font /Subtype /Type0 /BaseFont /%s /Encoding /Identity-H "
                         "/DescendantFonts [%d 0 R] /ToUnicode %d 0 R >>" % (base, o_cid, o_tu)).encode()
        objs[o_cid] = ("<< /Type /Font /Subtype /CIDFontType2 /BaseFont /%s /CIDSystemInfo << /Registry (Adobe) "
                       "/Ordering (Identity) /Supplement 0 >> /FontDescriptor %d 0 R /DW 1000 /W [0 [%s]] "
                       "/CIDToGIDMap /Identity >>" % (base, o_desc, widths)).encode()
        objs[o_desc] = ("<< /Type /FontDescriptor /FontName /%s /Flags 4 /FontBBox [%s] /ItalicAngle 0 "
                        "/Ascent %d /Descent %d /CapHeight %d /StemV %d /FontFile2 %d 0 R >>" % (
                            base, " ".join("%d" % round(v * scale) for v in f.bbox), round(f.ascent * scale),
                            round(f.descent * scale), round(f.cap_height * scale),
                            120 if (pf is bold and bold is not reg) else 80, o_file)).encode()
        comp = zlib.compress(pf.ttf, 9)
        objs[o_file] = (b"<< /Length %d /Length1 %d /Filter /FlateDecode >>\nstream\n" % (len(comp), len(pf.ttf))
                        + comp + b"\nendstream")
        tu = zlib.compress(tounicode(pf), 9)
        objs[o_tu] = b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(tu) + tu + b"\nendstream"
        font_refs[pf.name] = o_type0
    comp = zlib.compress(content, 9)
    objs[4] = b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp) + comp + b"\nendstream"
    fontdict = " ".join("/%s %d 0 R" % (n, o) for n, o in sorted(font_refs.items()))
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[2] = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    objs[3] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.3f %.2f] /Resources << /Font << %s >> "
               "/ProcSet [/PDF /Text] >> /Contents 4 0 R >>" % (PAGE_W, PAGE_H, fontdict)).encode()
    info = new()
    objs[info] = b"<< /Producer (eval fixture generator q05) >>"
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for n in sorted(objs):
        offsets[n] = len(out)
        out += b"%d 0 obj\n" % n + objs[n] + b"\nendobj\n"
    xref = len(out)
    size = max(objs) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for n in range(1, size):
        out += b"%010d 00000 n \n" % offsets[n]
    fid = hashlib.md5(bytes(out)).hexdigest().upper().encode()
    out += (b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R /ID [<%s> <%s>] >>\nstartxref\n%d\n%%%%EOF\n"
            % (size, info, fid, fid, xref))
    return bytes(out)


def all_text(blocks):
    parts = []
    for b in blocks:
        if b["type"] in ("heading", "paragraph"):
            parts.append(b["text"])
        elif b["type"] == "table":
            parts += b["header"] + [c for r in b["rows"] for c in r]
        elif b["type"] == "list":
            parts += b["items"]
    return "".join(parts)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--font", required=True)
    ap.add_argument("--bold-font")
    ap.add_argument("--font-index", type=int, default=0)
    ap.add_argument("--bold-font-index", type=int, default=0)
    ap.add_argument("--content", default=os.path.join(here, "content.json"))
    ap.add_argument("--out", default=os.path.join(here, "fixture.pdf"))
    a = ap.parse_args()
    with open(a.content, encoding="utf-8") as fh:
        blocks = json.load(fh)["blocks"]
    regular = TrueType(a.font, a.font_index)
    bullet = next((c for c in BULLET_CANDIDATES if regular.gid(c)), None)
    if bullet is None:
        sys.exit("font has none of the bullet glyphs %r" % BULLET_CANDIDATES)
    layout.bullet = bullet
    chars = set(all_text(blocks)) | {" ", bullet}
    reg = PdfFont("F1", regular, chars)
    if a.bold_font:
        bold = PdfFont("F2", TrueType(a.bold_font, a.bold_font_index), chars - {bullet})
    else:
        bold = PdfFont("F2", regular, chars - {bullet}, fake_bold=True)
    pdf = build_pdf(blocks, reg, bold)
    with open(a.out, "wb") as fh:
        fh.write(pdf)
    with open(a.font, "rb") as fh:
        font_sha = hashlib.sha256(fh.read()).hexdigest()
    print(json.dumps({
        "out": a.out, "bytes": len(pdf), "sha256": hashlib.sha256(pdf).hexdigest(),
        "font": os.path.basename(a.font), "font_sha256": font_sha, "font_ps_name": regular.ps_name,
        "font_variable": regular.variable, "font_weight_class": regular.weight_class,
        "bold_font": os.path.basename(a.bold_font) if a.bold_font else None,
        "bullet": "U+%04X" % ord(bullet), "glyphs_regular": len(reg.adv), "glyphs_bold": len(bold.adv),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
