#!/usr/bin/env python3
"""Compare the output of an answer's q03 command with the frozen expected output.

  python3 check_outputs.py records --expected small/expected/filter_status_eq_shipped.csv --got out_filter.txt
  python3 check_outputs.py records --expected small/expected/select_id_note_amount.csv    --got out_select.txt
  python3 check_outputs.py groupby --expected small/expected/groupby_region_count.csv     --got out_groupby.txt
  python3 check_outputs.py groupby --expected /work/big.csv.expected_counts.csv          --got out_big_groupby.txt

records (row filter, column selection): the output is parsed as RFC 4180 CSV
(comma separator). It passes when its data records equal the expected data
records exactly and in order; the header row may be present (then it must
equal the expected header) or absent. Quoting style, CRLF vs LF and a missing
final newline do not matter. A cell matches when the strings are equal, or
when both are decimal numbers of equal value (120.50 and 120.5). Output that
is not CSV (for example an aligned or box-drawn table) fails, because such
output cannot carry the embedded newlines and commas back exactly.

groupby: the output may be CSV, TSV, whitespace-aligned or a box-drawn table,
in any row order, with any header, extra columns (such as a percentage) or a
row-count footer. It passes when every expected key appears on exactly one
row together with its exact count, and no other row carries a count next to
an unexpected key (a mis-parsed group such as '"west"' or a fragment of a
multi-line field).

Exit 0 pass, 1 fail, 2 usage error. Python 3.9+ standard library only; runs on
the grader host (the q03 sandbox has no Python on purpose).
"""
import argparse
import csv
import io
import re
import sys
from decimal import Decimal, InvalidOperation

BORDER_CHARS = set("─━│┃┆┊║┌┐└┘├┤┬┴┼╭╮╯╰═╔╗╚╝╠╣╦╩╬╞╡╪╤╧-+=|: \t")
FOOTER_RE = re.compile(r"^\W*\(?\d[\d,_ ]*\s+(rows?|columns?|records?)\b", re.I)


def read_text(path):
    with open(path, "rb") as f:
        data = f.read()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.decode("utf-8")


def as_number(s):
    try:
        if not re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?", s.strip()):
            return None
        return Decimal(s.strip())
    except InvalidOperation:
        return None


def cell_eq(a, b):
    if a == b:
        return True
    na, nb = as_number(a), as_number(b)
    return na is not None and nb is not None and na == nb


def row_eq(a, b):
    return len(a) == len(b) and all(cell_eq(x, y) for x, y in zip(a, b))


def parse_csv(text):
    rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    while rows and rows[-1] == []:
        rows.pop()
    return rows


def check_records(expected_path, got_path):
    exp = parse_csv(read_text(expected_path))
    header, data = exp[0], exp[1:]
    try:
        got = parse_csv(read_text(got_path))
    except csv.Error as exc:
        return False, "output is not valid CSV: %s" % exc
    note = "with header"
    if got and row_eq(got[0], header):
        got = got[1:]
    else:
        note = "without header"
    if len(got) != len(data):
        return False, "%d data records, expected %d (%s)" % (len(got), len(data), note)
    for i, (g, e) in enumerate(zip(got, data), 1):
        if not row_eq(g, e):
            return False, "data record %d differs: got %r, expected %r" % (i, g, e)
    return True, "%d data records match (%s)" % (len(data), note)


def split_cells(line):
    s = line.strip()
    if not s or all(ch in BORDER_CHARS for ch in s):
        return []
    if FOOTER_RE.match(s.strip("│┃║| ")):
        return []
    if any(ch in s for ch in "│┃║"):
        cells = re.split(r"[│┃║]", s)
    elif "|" in s:
        cells = s.split("|")
    elif "\t" in s:
        cells = s.split("\t")
    elif "," in s:
        try:
            cells = next(csv.reader([s]))
        except (csv.Error, StopIteration):
            cells = s.split(",")
    else:
        cells = s.split()
    return [c.strip() for c in cells if c.strip() != ""]


def as_count(cell):
    c = cell.replace(",", "").replace("_", "").replace(" ", "")
    return int(c) if re.fullmatch(r"\d+", c) else None


def check_groupby(expected_path, got_path):
    exp_rows = parse_csv(read_text(expected_path))[1:]
    expected = {r[0]: int(r[1]) for r in exp_rows}
    seen = {}
    problems = []
    for n, line in enumerate(read_text(got_path).splitlines(), 1):
        cells = split_cells(line)
        if not cells:
            continue
        keys = [c for c in cells if c in expected]
        counts = [as_count(c) for c in cells if c not in expected]
        counts = [c for c in counts if c is not None]
        if keys:
            k = keys[0]
            if len(set(keys)) > 1:
                problems.append("line %d holds several keys %r" % (n, sorted(set(keys))))
            elif expected[k] not in counts:
                problems.append("line %d: key %r count %r, expected %d" % (n, k, counts, expected[k]))
            seen[k] = seen.get(k, 0) + 1
        elif counts and any(as_count(c) is None and as_number(c) is None for c in cells):
            problems.append("line %d: unexpected group %r" % (n, cells))
    missing = sorted(k for k in expected if k not in seen)
    dup = sorted(k for k, v in seen.items() if v > 1)
    if missing:
        problems.append("%d expected key(s) missing, e.g. %r" % (len(missing), missing[:5]))
    if dup:
        problems.append("key(s) on more than one row: %r" % dup[:5])
    if problems:
        return False, "; ".join(problems[:6])
    return True, "all %d groups and counts match" % len(expected)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["records", "groupby"])
    ap.add_argument("--expected", required=True)
    ap.add_argument("--got", required=True)
    a = ap.parse_args()
    fn = check_records if a.kind == "records" else check_groupby
    ok, why = fn(a.expected, a.got)
    print(("PASS " if ok else "FAIL ") + why)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
