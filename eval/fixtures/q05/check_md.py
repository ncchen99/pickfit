#!/usr/bin/env python3
"""Frozen check for q05: compare one converted .md file with content.json (stdlib only).

    python3 check_md.py OUTPUT.md [--content content.json] [--report report.json]

Exit 0 only if both items pass. Two verdicts are reported:

structure  (item "headings are ATX headings at the right levels, the table is a Markdown
           pipe table whose 12 cell texts match the fixture, and the list items are
           Markdown list items")
  * every fixture heading appears as an ATX heading ("#" / "##" at line start) with the
    same level as in the fixture; setext headings and HTML <h1> do not count;
  * no other fixture text (paragraph, table cell, list item) became an ATX heading;
  * one Markdown pipe table (header row, delimiter row, body rows; not an HTML <table>)
    has exactly 4 columns, its header row equals the fixture header, and its body rows
    (rows whose cells are all empty are ignored) are exactly the 2 fixture rows, in order;
  * every fixture list item appears as a Markdown list item ("-", "*", "+" or "1." / "1)"
    at line start), possibly wrapped onto continuation lines.
  Text comparison: Unicode NFKC, all whitespace removed, Markdown emphasis/code markers
  (* _ `), backslash escapes and <br> removed; a stray bullet glyph at the start of a list
  item's text is ignored. Characters themselves must match exactly (no Simplified forms).

cjk        (item "at least 98% of the fixture's CJK characters, in order, ... with no
           replacement characters")
  * fixture CJK characters = Han ideographs (U+3400-4DBF, U+4E00-9FFF, U+F900-FAFF,
    U+20000-3FFFF) of all blocks in reading order (tables row by row); punctuation is
    not counted;
  * ratio = longest common subsequence of that sequence and the Han characters of the
    whole output file, divided by the fixture count; pass needs ratio >= 0.98;
  * replacement characters: U+FFFD, or a "(cid:N)" placeholder; pass needs zero.
"""

import argparse
import json
import os
import re
import sys
import unicodedata

ATX_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
DELIM_CELL_RE = re.compile(r"^\s*:?-{1,}:?\s*$")
LIST_RE = re.compile(r"^(\s{0,12})([-*+]|\d{1,9}[.)])[ \t]+(.*)$")
BULLET_GLYPHS = "•‧・·▪◦●∙"
CID_RE = re.compile(r"\(cid:\d+\)")


def is_han(ch):
    o = ord(ch)
    return (0x3400 <= o <= 0x4DBF) or (0x4E00 <= o <= 0x9FFF) or (0xF900 <= o <= 0xFAFF) or \
        (0x20000 <= o <= 0x3FFFF)


def norm(text):
    t = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    t = re.sub(r"\\(.)", r"\1", t)
    t = unicodedata.normalize("NFKC", t)
    t = t.replace("*", "").replace("_", "").replace("`", "")
    return re.sub(r"\s+", "", t)


def norm_item(text):
    t = norm(text)
    return t.lstrip(BULLET_GLYPHS + "-")


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, i = [], "", 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            cur += s[i:i + 2]
            i += 2
            continue
        if s[i] == "|":
            cells.append(cur)
            cur = ""
        else:
            cur += s[i]
        i += 1
    cells.append(cur)
    return cells


def code_mask(lines):
    mask, fence = [], None
    for ln in lines:
        m = FENCE_RE.match(ln)
        if fence:
            mask.append(True)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)
            mask.append(True)
            continue
        mask.append(False)
    return mask


def find_tables(lines, mask):
    tables, i = [], 0
    while i < len(lines) - 1:
        if not mask[i] and not mask[i + 1] and "|" in lines[i] and "|" in lines[i + 1]:
            delim = split_row(lines[i + 1])
            if delim and all(DELIM_CELL_RE.match(c) for c in delim) and "-" in lines[i + 1]:
                header = split_row(lines[i])
                body, j = [], i + 2
                while j < len(lines) and not mask[j] and "|" in lines[j] and lines[j].strip():
                    body.append(split_row(lines[j]))
                    j += 1
                tables.append({"line": i + 1, "header": header, "rows": body, "rows_raw_end": j})
                i = j
                continue
        i += 1
    return tables


def lcs_len(a, b):
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b):
            cur.append(prev[j] + 1 if ca == cb else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def fixture_parts(blocks):
    heads, others, han = [], [], []
    for b in blocks:
        t = b["type"]
        if t == "heading":
            heads.append((b["level"], b["text"]))
            han.append(b["text"])
        elif t == "paragraph":
            others.append(b["text"])
            han.append(b["text"])
        elif t == "table":
            for row in [b["header"]] + b["rows"]:
                others += row
                han += row
        elif t == "list":
            others += b["items"]
            han += b["items"]
    return heads, others, [c for s in han for c in s if is_han(c)]


def check(md_text, blocks):
    lines = md_text.splitlines()
    mask = code_mask(lines)
    heads, others, fixture_han = fixture_parts(blocks)
    table_block = next(b for b in blocks if b["type"] == "table")
    list_block = next(b for b in blocks if b["type"] == "list")

    atx = []
    for n, ln in enumerate(lines):
        if mask[n]:
            continue
        m = ATX_RE.match(ln)
        if m:
            atx.append({"line": n + 1, "level": len(m.group(1)), "text": (m.group(2) or "").strip()})
    heading_results, matched_lines = [], set()
    for level, text in heads:
        hits = [h for h in atx if norm(h["text"]) == norm(text)]
        ok = any(h["level"] == level for h in hits)
        for h in hits:
            matched_lines.add(h["line"])
        heading_results.append({"expected_level": level, "text": text, "pass": ok,
                                "found_levels": [h["level"] for h in hits]})
    norm_others = [norm(o) for o in others]
    violations = []
    for h in atx:
        if h["line"] in matched_lines:
            continue
        nh = norm(h["text"])
        if len(nh) >= 2 and any(nh == o or (len(nh) >= 4 and nh in o) for o in norm_others):
            violations.append(h)

    want_header = [norm(c) for c in table_block["header"]]
    want_rows = [[norm(c) for c in r] for r in table_block["rows"]]
    tables = find_tables(lines, mask)
    table_result = {"pass": False, "tables_found": len(tables), "best": None}
    best_score = -1
    for t in tables:
        header = [norm(c) for c in t["header"]]
        rows = [[norm(c) for c in r] for r in t["rows"]]
        rows = [r for r in rows if any(r)]
        ok = (len(header) == 4 and header == want_header and len(rows) == len(want_rows)
              and all(len(r) == 4 for r in rows) and rows == want_rows)
        score = sum(1 for a, b in zip(header, want_header) if a == b) + sum(
            1 for r, w in zip(rows, want_rows) for a, b in zip(r, w) if a == b)
        if ok or score > best_score:
            best_score = score
            table_result["best"] = {"line": t["line"], "columns": len(header), "body_rows": len(rows),
                                    "matching_cells": score, "of": 12, "pass": ok}
        if ok:
            table_result["pass"] = True
            break

    in_table = set()
    for t in tables:
        in_table.update(range(t["line"] - 1, t["rows_raw_end"]))
    items, n = [], 0
    while n < len(lines):
        if mask[n] or n in in_table:
            n += 1
            continue
        m = LIST_RE.match(lines[n])
        if m and not ATX_RE.match(lines[n]):
            text = m.group(3)
            k = n + 1
            while k < len(lines) and lines[k].strip() and not mask[k] and k not in in_table \
                    and not LIST_RE.match(lines[k]) and not ATX_RE.match(lines[k]) and "|" not in lines[k]:
                text += " " + lines[k].strip()
                k += 1
            items.append({"line": n + 1, "text": text})
            n = k
            continue
        n += 1
    got_items = [norm_item(i["text"]) for i in items]
    list_results = [{"text": it, "pass": norm_item(it) in got_items} for it in list_block["items"]]

    structure_pass = (all(h["pass"] for h in heading_results) and not violations
                      and table_result["pass"] and all(r["pass"] for r in list_results))

    out_han = [c for c in md_text if is_han(c)]
    lcs = lcs_len(fixture_han, out_han)
    ratio = lcs / float(len(fixture_han))
    fffd = md_text.count("�")
    cids = len(CID_RE.findall(md_text))
    pua = sum(1 for c in md_text if 0xE000 <= ord(c) <= 0xF8FF)
    cjk_pass = ratio >= 0.98 and fffd == 0 and cids == 0
    return {
        "structure": {"pass": structure_pass, "headings": heading_results,
                      "body_text_as_heading": violations, "table": table_result,
                      "list_items": list_results, "atx_headings_in_output": atx},
        "cjk": {"pass": cjk_pass, "fixture_han": len(fixture_han), "output_han": len(out_han),
                "lcs": lcs, "ratio": round(ratio, 4), "threshold": 0.98,
                "replacement_chars_fffd": fffd, "cid_placeholders": cids,
                "private_use_chars_info_only": pua},
    }


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md")
    ap.add_argument("--content", default=os.path.join(here, "content.json"))
    ap.add_argument("--report")
    a = ap.parse_args()
    with open(a.content, encoding="utf-8") as fh:
        blocks = json.load(fh)["blocks"]
    raw = open(a.md, "rb").read()
    try:
        text = raw.decode("utf-8-sig")
        decode_ok = True
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
        decode_ok = False
    res = check(text, blocks)
    res["file"] = os.path.abspath(a.md)
    res["utf8"] = decode_ok
    if not decode_ok:
        res["structure"]["pass"] = False
        res["cjk"]["pass"] = False
    out = json.dumps(res, ensure_ascii=False, indent=2)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            fh.write(out)
    print(out)
    print("structure=%s cjk=%s ratio=%s" % (
        "PASS" if res["structure"]["pass"] else "FAIL", "PASS" if res["cjk"]["pass"] else "FAIL",
        res["cjk"]["ratio"]), file=sys.stderr)
    sys.exit(0 if res["structure"]["pass"] and res["cjk"]["pass"] else 1)


if __name__ == "__main__":
    main()
