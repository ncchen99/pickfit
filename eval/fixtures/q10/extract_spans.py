#!/usr/bin/env python3
"""q10 frozen span-extraction script (Python 3.8+ stdlib only).

Reads the raw bytes a diff command wrote to a pseudo-terminal (captured by
capture.sh) and reports which characters the output marks as removed and
added. It understands the two inline forms named in the q10 checklist:

  * ANSI colour runs: SGR escape sequences; red marks removed text, green
    marks added text (basic, bright, 256-colour and 24-bit forms; foreground,
    background or reverse video). When a line also has background/reverse
    highlighted runs inside a coloured line, only the highlighted runs count.
  * Inline markers: [-removed-] and {+added+}. When markers are present they
    take precedence over colour (git colours the markers too).

Anything else (whole-line +/- without colour, JSON, machine formats) yields
no spans.

Usage:
  python3 extract_spans.py OUTPUT_RAW [--expected expected.json] [--json]
  python3 extract_spans.py OUTPUT_RAW --same-as FIRST_RAW   # L2-4

Exit status: 0 when L2-2, L2-3 and L2-5 all pass, 1 otherwise, 2 on usage error.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

CSI_RE = re.compile(rb"\x1b\[([0-9;:?<=>]*)([ -/]*)([@-~])")
OSC_RE = re.compile(rb"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
ESC2_RE = re.compile(rb"\x1b[ -Z\\^_`a-~]")

HEADER_PREFIXES = (
    b"diff --git", b"diff --cc", b"diff --combined", b"index ", b"--- ", b"+++ ",
    b"@@", b"new file mode", b"deleted file mode", b"old mode", b"new mode",
    b"similarity index", b"dissimilarity index", b"rename from", b"rename to",
    b"copy from", b"copy to", b"Binary files", b"\\ No newline",
)

ERROR_RE = re.compile(
    r"(^|\n)\s*(fatal|error|warning):|command not found|not a git repository|"
    r"unknown option|unknown switch|usage: git|No such file or directory",
    re.IGNORECASE,
)

DEL_MARK_RE = re.compile(rb"\[-(.*?)-\]", re.S)
ADD_MARK_RE = re.compile(rb"\{\+(.*?)\+\}", re.S)


# ---------------------------------------------------------------- colours

def _cube_class(n):
    n -= 16
    r, g, b = n // 36, (n % 36) // 6, n % 6
    if r >= 2 and r > g and r > b:
        return "red"
    if g >= 2 and g > r and g > b:
        return "green"
    return None


def colour_class(spec):
    """spec: ('basic', idx) | ('256', n) | ('rgb', r, g, b) | None."""
    if spec is None:
        return None
    kind = spec[0]
    if kind == "basic":
        return {1: "red", 2: "green"}.get(spec[1])
    if kind == "256":
        n = spec[1]
        if n < 16:
            return {1: "red", 2: "green"}.get(n % 8)
        if n < 232:
            return _cube_class(n)
        return None
    if kind == "rgb":
        r, g, b = spec[1:]
        if r >= 128 and r > 1.5 * g and r > 1.5 * b:
            return "red"
        if g >= 100 and g > 1.3 * r and g > 1.3 * b:
            return "green"
    return None


class Style(object):
    __slots__ = ("fg", "bg", "reverse")

    def __init__(self):
        self.fg = None
        self.bg = None
        self.reverse = False

    def reset(self):
        self.fg = None
        self.bg = None
        self.reverse = False

    def classify(self):
        """Return (cls, emphasized): cls in {'del','add',None}."""
        fg, bg = colour_class(self.fg), colour_class(self.bg)
        if self.reverse:
            fg, bg = bg, fg
        if bg in ("red", "green"):
            return ("del" if bg == "red" else "add"), True
        if fg in ("red", "green"):
            return ("del" if fg == "red" else "add"), False
        return None, False


def _int(x, default=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _extended(nums):
    """Parse the tail of a 38/48 sequence -> (spec, consumed)."""
    if not nums:
        return None, 0
    if nums[0] == "5" and len(nums) >= 2:
        return ("256", _int(nums[1])), 2
    if nums[0] == "2" and len(nums) >= 4:
        return ("rgb", _int(nums[1]), _int(nums[2]), _int(nums[3])), 4
    return None, 1


def apply_sgr(params, st):
    if params == "":
        st.reset()
        return
    groups = params.split(";")
    i = 0
    while i < len(groups):
        g = groups[i]
        if ":" in g:  # colon sub-parameters, e.g. 38:2::255:0:0 or 38:5:1
            sub = g.split(":")
            code = _int(sub[0], -1)
            if code in (38, 48):
                rest = sub[1:]
                if rest and rest[0] == "2":
                    vals = [v for v in rest[1:] if v != ""][-3:]
                    spec = ("rgb",) + tuple(_int(v) for v in vals) if len(vals) == 3 else None
                elif rest and rest[0] == "5" and len(rest) >= 2:
                    spec = ("256", _int(rest[1]))
                else:
                    spec = None
                if code == 38:
                    st.fg = spec
                else:
                    st.bg = spec
            i += 1
            continue
        code = _int(g, -1) if g != "" else 0
        if code == 0:
            st.reset()
        elif code == 7:
            st.reverse = True
        elif code == 27:
            st.reverse = False
        elif 30 <= code <= 37:
            st.fg = ("basic", code - 30)
        elif 90 <= code <= 97:
            st.fg = ("basic", code - 90)
        elif code == 39:
            st.fg = None
        elif 40 <= code <= 47:
            st.bg = ("basic", code - 40)
        elif 100 <= code <= 107:
            st.bg = ("basic", code - 100)
        elif code == 49:
            st.bg = None
        elif code in (38, 48):
            spec, used = _extended(groups[i + 1:])
            if code == 38:
                st.fg = spec
            else:
                st.bg = spec
            i += used
        i += 1


# ---------------------------------------------------------------- parsing

def tokenize(data):
    """Return list of lines; each line is a list of (byte, cls, emphasized)."""
    st = Style()
    lines = [[]]
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        if c == 0x1B:
            m = OSC_RE.match(data, i)
            if m:
                i = m.end()
                continue
            m = CSI_RE.match(data, i)
            if m:
                if m.group(3) == b"m" and not m.group(2):
                    apply_sgr(m.group(1).decode("ascii", "replace"), st)
                i = m.end()
                continue
            m = ESC2_RE.match(data, i)
            if m:
                i = m.end()
                continue
            i += 1
            continue
        if c == 0x0D:  # pty line endings are \r\n
            i += 1
            continue
        if c == 0x08:  # backspace (e.g. a pty echoing "^D\b\b"): the next byte overwrites
            if lines[-1]:
                lines[-1].pop()
            i += 1
            continue
        if c == 0x0A:
            lines.append([])
            i += 1
            continue
        cls, emph = st.classify()
        lines[-1].append((c, cls, emph))
        i += 1
    return lines


def plain(line):
    return bytes(b for b, _, _ in line)


def is_header(pl):
    return pl.startswith(HEADER_PREFIXES)


def decode_ok(bs):
    try:
        bs.decode("utf-8", "strict")
        return True
    except UnicodeDecodeError:
        return False


def show(bs):
    return bs.decode("utf-8", "replace")


def span_text(bs, at_line_start, line_plain):
    """Span text for counting: strip whitespace and a whole-line +/- prefix."""
    t = bs
    if at_line_start and line_plain[:1] in (b"+", b"-") and t[:1] in (b"+", b"-"):
        t = t[1:]
    return t.strip()


def colour_runs(line):
    """Return list of (cls, start, end) runs of identical classification."""
    runs = []
    start = 0
    for idx in range(1, len(line) + 1):
        if idx == len(line) or line[idx][1:] != line[start][1:]:
            if line:
                runs.append((line[start][1], line[start][2], start, idx))
            start = idx
    return runs


def analyse(data, expected):
    lines = tokenize(data)
    content = []  # (index, line tokens, plain bytes)
    for idx, line in enumerate(lines):
        pl = plain(line)
        if is_header(pl):
            continue
        content.append((idx, line, pl))

    whole_plain = b"\n".join(plain(l) for l in lines)
    whole_text = show(whole_plain)

    # --- marker spans
    marker_spans = {"del": [], "add": []}
    for _, _, pl in content:
        for m in DEL_MARK_RE.finditer(pl):
            marker_spans["del"].append(m.group(1))
        for m in ADD_MARK_RE.finditer(pl):
            marker_spans["add"].append(m.group(1))
    have_markers = bool(marker_spans["del"] or marker_spans["add"])

    # --- colour spans (and run-level UTF-8 check)
    colour_spans = {"del": [], "add": []}
    run_utf8_ok = True
    bad_runs = []
    for _, line, pl in content:
        runs = colour_runs(line)
        for cls, emph, s, e in runs:
            seg = pl[s:e]
            if not decode_ok(seg):
                run_utf8_ok = False
                bad_runs.append(seg.hex())
        emphasized_present = any(emph and cls for cls, emph, _, _ in runs)
        for cls, emph, s, e in runs:
            if cls is None:
                continue
            if emphasized_present and not emph:
                continue
            colour_spans[cls].append(span_text(pl[s:e], s == 0, pl))
    have_colour = bool(colour_spans["del"] or colour_spans["add"])

    if have_markers:
        mode = "markers"
        spans = {k: [v.strip() for v in vs] for k, vs in marker_spans.items()}
    elif have_colour:
        mode = "color"
        spans = colour_spans
    else:
        mode = "none"
        spans = {"del": [], "add": []}

    span_utf8_ok = all(decode_ok(s) for k in spans for s in spans[k])

    # --- reconstruct old and new sides of the content lines
    old_parts, new_parts = [], []
    for _, line, pl in content:
        if mode == "markers":
            o = ADD_MARK_RE.sub(b"", pl)
            o = DEL_MARK_RE.sub(lambda m: m.group(1), o)
            nw = DEL_MARK_RE.sub(b"", pl)
            nw = ADD_MARK_RE.sub(lambda m: m.group(1), nw)
        elif mode == "color":
            o = bytes(b for b, cls, _ in line if cls != "add")
            nw = bytes(b for b, cls, _ in line if cls != "del")
        else:
            o = nw = pl
        old_parts.append(o)
        new_parts.append(nw)
    old_bytes = b"\n".join(old_parts)
    new_bytes = b"\n".join(new_parts)
    lines_utf8_ok = all(decode_ok(pl) for _, _, pl in content)

    old_c, new_c = expected["old_char"], expected["new_char"]
    old_nb, new_nb = expected["old_neighbourhood"], expected["new_neighbourhood"]
    old_txt, new_txt = show(old_bytes), show(new_bytes)
    nb_ok = (old_nb in old_txt) and (new_nb in new_txt)
    no_replacement = "�" not in whole_text

    del_texts = [show(s) for s in spans["del"]]
    add_texts = [show(s) for s in spans["add"]]
    del_len = sum(len(t) for t in del_texts)
    add_len = sum(len(t) for t in add_texts)
    limit = expected.get("max_span_chars", 3)

    # --- L2-2: span lengths and contents
    r2 = []
    if mode == "none":
        r2.append("no ANSI colour runs or [-..-]/{+..+} markers found")
    if not spans["del"]:
        r2.append("no removed span")
    if not spans["add"]:
        r2.append("no added span")
    if del_len > limit:
        r2.append("removed spans total %d chars > %d" % (del_len, limit))
    if add_len > limit:
        r2.append("added spans total %d chars > %d" % (add_len, limit))
    if old_c not in "".join(del_texts):
        r2.append("removed spans do not contain the old character")
    if new_c not in "".join(add_texts):
        r2.append("added spans do not contain the new character")
    if not span_utf8_ok:
        r2.append("a span is not valid UTF-8 on its own")
    l2_2 = {"pass": not r2, "reasons": r2}

    # --- L2-3: UTF-8 integrity
    r3 = []
    if not lines_utf8_ok:
        r3.append("a diff content line is not valid UTF-8 after removing escape sequences")
    if not run_utf8_ok:
        r3.append("a colour run starts or ends inside a multi-byte character")
    if not span_utf8_ok:
        r3.append("a span is not valid UTF-8 on its own")
    if not no_replacement:
        r3.append("output contains U+FFFD or undecodable bytes")
    if not nb_ok:
        r3.append("old/new neighbourhood (%s / %s) not found intact" % (old_nb, new_nb))
    l2_3 = {"pass": not r3, "reasons": r3}

    # --- L2-5: readable in a terminal
    r6 = []
    stripped = whole_text.strip()
    looks_json = False
    if stripped[:1] in ("{", "["):
        try:
            json.loads(stripped)
            looks_json = True
        except ValueError:
            pass
    if looks_json:
        r6.append("output is JSON")
    if mode == "none":
        r6.append("changes are not shown with colour or inline markers")
    l2_5 = {"pass": not r6, "reasons": r6}

    # --- L2-1 helper (the grader still reads the command line itself)
    errors = [m.group(0).strip() for m in ERROR_RE.finditer(whole_text)]
    l2_1_output = {
        "output_bytes": len(data),
        "error_like_text": errors,
        "pass_hint": bool(data.strip()) and not errors,
    }

    return {
        "mode": mode,
        "spans": {"del": del_texts, "add": add_texts},
        "span_chars": {"del": del_len, "add": add_len},
        "marker_spans_found": {k: len(v) for k, v in marker_spans.items()},
        "colour_spans_found": {k: len(v) for k, v in colour_spans.items()},
        "invalid_runs_hex": bad_runs[:10],
        "old_side_contains_full_old_neighbourhood": old_nb in old_txt,
        "new_side_contains_full_new_neighbourhood": new_nb in new_txt,
        "l2_1_output": l2_1_output,
        "l2_2": l2_2,
        "l2_3": l2_3,
        "l2_5": l2_5,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("raw", help="raw bytes captured from the pseudo-terminal")
    ap.add_argument("--expected", default=os.path.join(HERE, "expected.json"))
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    ap.add_argument("--same-as", metavar="FIRST_RAW",
                    help="L2-4: also require the same removed/added spans as this earlier capture")
    a = ap.parse_args(argv)
    with open(a.expected, encoding="utf-8") as f:
        expected = json.load(f)
    with open(a.raw, "rb") as f:
        data = f.read()
    rep = analyse(data, expected)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("mode: %s" % rep["mode"])
        print("removed spans: %r (%d chars)" % (rep["spans"]["del"][:5], rep["span_chars"]["del"]))
        print("added spans:   %r (%d chars)" % (rep["spans"]["add"][:5], rep["span_chars"]["add"]))
        for key, label in (("l2_2", "L2-2 spans"), ("l2_3", "L2-3 UTF-8"), ("l2_5", "L2-5 readable")):
            r = rep[key]
            print("%s: %s%s" % (label, "PASS" if r["pass"] else "FAIL",
                                "" if r["pass"] else " - " + "; ".join(r["reasons"])))
        hint = rep["l2_1_output"]
        print("L2-1 output check: %s%s" % ("ok" if hint["pass_hint"] else "PROBLEM",
                                             "" if hint["pass_hint"] else " %r" % hint["error_like_text"]))
    ok = rep["l2_2"]["pass"] and rep["l2_3"]["pass"] and rep["l2_5"]["pass"]
    if a.same_as:
        with open(a.same_as, "rb") as f:
            first = analyse(f.read(), expected)
        same = first["spans"] == rep["spans"]
        l2_4 = same and ok
        print("L2-4 same character-level result as %s: %s" % (
            a.same_as, "PASS" if l2_4 else "FAIL - " + (
                "spans differ: %r vs %r" % (first["spans"], rep["spans"]) if not same
                else "this capture fails L2-2/L2-3/L2-5")))
        ok = l2_4
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
