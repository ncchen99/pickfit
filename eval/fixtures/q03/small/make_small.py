#!/usr/bin/env python3
"""Build the frozen q03 fixture CSV and its expected outputs.

The CSV text below is written by hand (24 data rows, LF line endings, UTF-8,
no BOM). Its quoted fields contain commas, escaped double quotes ("") and
embedded newlines; some fields are quoted although they need not be. The
expected outputs are computed with Python's csv module and written to
expected/. Run with --check to verify the committed files are unchanged.

  python3 make_small.py          # (re)write sample.csv, tasks.json, expected/*.csv
  python3 make_small.py --check  # exit 1 if any committed file differs

Python 3.9+ standard library only.
"""
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

SAMPLE = (
    'id,customer,note,region,amount,status\n'
    '1,Acme Corp,Standard order,north,120.50,shipped\n'
    '2,"Smith, Jane","Leave at the door, ring twice",south,75.00,pending\n'
    '3,Globex,"He said ""ship it"" today",east,310.25,shipped\n'
    '4,"Initech ""West""","Line one\nLine two",west,42.10,cancelled\n'
    '5,Umbrella,"Contains, commas, and ""quotes""\nand a second line",north,980.00,shipped\n'
    '6,Hooli,,"west",15.75,returned\n'
    '7,"Zoë Café",Café order,central,260.40,shipped\n'
    '8,Vandelay,"Note mentions shipped, but status is pending",south,199.99,pending\n'
    '9,"Wayne, Bruce & Co.","Fragile\nhandle with care\nthree lines",north,450.00,shipped\n'
    '10,Stark,Plain note,"north",33.30,pending\n'
    "11,O'Brien Ltd,Apostrophe is fine,east,88.80,returned\n"
    '12,Tyrell,"Comma at end,",west,251.00,shipped\n'
    '13,Cyberdyne,"""Leading quote",south,249.99,cancelled\n'
    '14,Soylent,"Trailing quote""",north,500.01,shipped\n'
    '15,"東京商事",東京向け,east,1200.00,pending\n'
    '16,Wonka,"Embedded ""quotes"", commas, and\na newline",west,64.00,shipped\n'
    '17,Oscorp,Quick note,south,301.00,returned\n'
    '18,"Pied Piper","",central,12.00,pending\n'
    '19,"Massive Dynamic","Status: shipped\n(see above)",north,77.70,cancelled\n'
    '20,Aperture,Test,west,250.50,pending\n'
    '21,"Black Mesa","Quote "" in middle",north,99.00,returned\n'
    '22,Gringotts,"Vault, 713",west,700.00,shipped\n'
    '23,Nakatomi,Holiday party,east,15.00,pending\n'
    '24,"Prestige, Worldwide","Boats, and more",south,410.00,shipped\n'
)

TASKS = {
    "comment": "Placeholder values the grader fills into the answer's own commands for q03 L2 item 2. Columns are named exactly as in sample.csv's header.",
    "input": "sample.csv",
    "filter_eq": {"description": "rows whose status column equals shipped (exact, whole-field match)",
                  "column": "status", "value": "shipped",
                  "expected": "expected/filter_status_eq_shipped.csv"},
    "filter_gt": {"description": "rows whose amount column is greater than 250 (numeric); use only when the answer's filter example is a numeric comparison",
                  "column": "amount", "value": 250,
                  "expected": "expected/filter_amount_gt_250.csv"},
    "select": {"description": "keep columns id, note, amount in that order (all rows)",
               "columns": ["id", "note", "amount"],
               "expected": "expected/select_id_note_amount.csv"},
    "groupby": {"description": "count rows per distinct value of region",
                "column": "region",
                "expected": "expected/groupby_region_count.csv"},
}


def to_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerows(rows)
    return buf.getvalue()


def build():
    rows = list(csv.reader(io.StringIO(SAMPLE, newline=""), strict=True))
    header, data = rows[0], rows[1:]
    assert len(data) == 24 and all(len(r) == 6 for r in data), "bad fixture shape"
    col = {name: i for i, name in enumerate(header)}
    out = {}
    out["filter_status_eq_shipped.csv"] = to_csv(
        [header] + [r for r in data if r[col["status"]] == "shipped"])
    out["filter_amount_gt_250.csv"] = to_csv(
        [header] + [r for r in data if float(r[col["amount"]]) > 250])
    sel = ["id", "note", "amount"]
    out["select_id_note_amount.csv"] = to_csv(
        [sel] + [[r[col[c]] for c in sel] for r in data])
    counts = {}
    for r in data:
        counts[r[col["region"]]] = counts.get(r[col["region"]], 0) + 1
    out["groupby_region_count.csv"] = to_csv(
        [["region", "count"]] + [[k, str(counts[k])] for k in sorted(counts)])
    files = {"sample.csv": SAMPLE,
             "tasks.json": json.dumps(TASKS, indent=2, ensure_ascii=False) + "\n"}
    for name, text in out.items():
        files[os.path.join("expected", name)] = text
    return files


def main():
    files = build()
    check = "--check" in sys.argv[1:]
    bad = 0
    for rel, text in sorted(files.items()):
        path = os.path.join(HERE, rel)
        data = text.encode("utf-8")
        if check:
            try:
                with open(path, "rb") as f:
                    same = f.read() == data
            except FileNotFoundError:
                same = False
            print(("OK      " if same else "DIFFERS ") + rel)
            bad += 0 if same else 1
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            print("wrote " + rel)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
