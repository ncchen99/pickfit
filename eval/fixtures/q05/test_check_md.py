#!/usr/bin/env python3
"""Self-test of check_md.py: synthetic good and broken Markdown built from content.json.

    python3 test_check_md.py        (exit 0 when every case gets the expected verdict)

These inputs are written by hand for the test; they are not the output of any converter.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_md  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCKS = json.load(open(os.path.join(HERE, "content.json"), encoding="utf-8"))["blocks"]


def render(blocks, table_style="pipe", h2="##", bullet="- ", wrap_list=False, extra=""):
    out = []
    for b in blocks:
        t = b["type"]
        if t == "heading":
            out.append(("#" if b["level"] == 1 else h2) + " " + b["text"])
        elif t == "paragraph":
            out.append(b["text"])
        elif t == "table":
            if table_style == "pipe":
                out.append("| " + " | ".join(b["header"]) + " |")
                out.append("|" + "---|" * 4)
                for r in b["rows"]:
                    out.append("| " + " | ".join(r) + " |")
            elif table_style == "flat":
                for r in [b["header"]] + b["rows"]:
                    out.append(" ".join(r))
            elif table_style == "html":
                out.append("<table>" + "".join("<tr>" + "".join("<td>%s</td>" % c for c in r) + "</tr>"
                                                for r in [b["header"]] + b["rows"]) + "</table>")
        elif t == "list":
            for it in b["items"]:
                if wrap_list:
                    cut = it.index("。") + 1
                    out.append(bullet + it[:cut])
                    out.append("  " + it[cut:])
                else:
                    out.append(bullet + it)
        out.append("")
    return "\n".join(out) + extra


def mutate_chars(text, n):
    swaps = {"體": "体", "規": "规", "書": "书", "說": "说", "溫": "温", "設": "设", "線": "线", "組": "组"}
    done = 0
    for a, b in swaps.items():
        if done >= n:
            break
        if a in text:
            text = text.replace(a, b, 1)
            done += 1
    return text


def case(name, md, want_struct, want_cjk):
    r = check_md.check(md, BLOCKS)
    ok = r["structure"]["pass"] == want_struct and r["cjk"]["pass"] == want_cjk
    print("%-4s %-44s structure=%s cjk=%s ratio=%s" % ("ok" if ok else "FAIL", name, r["structure"]["pass"],
                                                       r["cjk"]["pass"], r["cjk"]["ratio"]))
    return ok


def main():
    good = render(BLOCKS)
    cases = [
        ("ideal markdown", good, True, True),
        ("bold cells, spacing, <br>, '* ' bullets", render(BLOCKS, bullet="* ").replace(
            "| 溫度感測器 |", "| **溫度感測器** |").replace("2.4 GHz", "2.4GHz").replace(
            "誤差小於 0.5 度", "誤差小於<br>0.5 度"), True, True),
        ("list item with stray bullet glyph", render(BLOCKS, bullet="- • "), True, True),
        ("wrapped list items", render(BLOCKS, wrap_list=True), True, True),
        ("empty row inside table", good.replace("|---|---|---|---|\n", "|---|---|---|---|\n|  |  |  |  |\n"),
         True, True),
        ("table flattened to text", render(BLOCKS, table_style="flat"), False, True),
        ("table only as HTML", render(BLOCKS, table_style="html"), False, True),
        ("H2 written as ###", render(BLOCKS, h2="###"), False, True),
        ("setext H1", good.replace("# 智慧溫控器規格書 Thermostat Spec", "智慧溫控器規格書 Thermostat Spec\n===="),
         False, True),
        ("list items as plain lines", render(BLOCKS, bullet=""), False, True),
        ("list items as bullet glyph only", render(BLOCKS, bullet="• "), False, True),
        ("paragraph promoted to heading", good.replace("安裝前請確認下列事項。", "## 安裝前請確認下列事項。\n\n", 1),
         False, True),
        ("header row missing (cells in body)", good.replace("| 元件 Part | 規格 Spec | 數量 Qty | 備註 Notes |\n|---|---|---|---|",
                                                           "| | | | |\n|---|---|---|---|\n| 元件 Part | 規格 Spec | 數量 Qty | 備註 Notes |"),
         False, True),
        ("1 Simplified char in a paragraph", mutate_chars(good, 1), True, True),
        ("1 Simplified char in a table cell", good.replace("| 溫度感測器 |", "| 温度感測器 |"), False, True),
        ("4 Simplified chars (ratio < 0.98)", mutate_chars(good, 4), False, False),
        ("U+FFFD present", good + "\n�\n", True, False),
        ("(cid:12) placeholder", good + "\n(cid:12)\n", True, False),
        ("CJK out of order", "\n".join(reversed(good.splitlines())), False, False),
        ("extra page-header heading is tolerated", "# Page 1\n\n" + good, True, True),
    ]
    results = [case(*c) for c in cases]
    print("%d/%d cases as expected" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
