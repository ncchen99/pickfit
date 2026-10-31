#!/usr/bin/env python3
"""Check a redacted log for eval q02 (two L2 items, judged separately).

  python3 check_clean.py --manifest OUT_DIR/manifest.json \
      --input OUT_DIR/app.log --output OUT_DIR/clean.log [--report r.json]

Item "masking": each of the six planted values counts as masked when its
exact string is absent from clean.log and
  - access key ID and token: no run of 5 or more characters of the random
    part (everything after the 4-character prefix) appears anywhere;
  - email: the local part (before "@") appears nowhere;
  - IPv4: neither the third nor the fourth octet appears anywhere as a
    standalone number (not touching a letter or digit). The generator makes
    sure those numbers occur nowhere else in app.log.
  All six must be masked.

Item "ordinary": every ordinary line of app.log appears byte-identical as a
whole line of clean.log, in the original order (extra lines in clean.log,
such as a summary, are allowed).

The fake values are never printed; lines are named by kind and line number.
Exit 0 when both items pass, 1 otherwise, 2 on usage errors.
Python 3.9+ standard library only.
"""
import argparse
import json
import re
import sys


def standalone(num):
    return re.compile((r"(?<![0-9A-Za-z])%s(?![0-9A-Za-z])" % re.escape(num)).encode())


def check_value(entry, clean):
    kind, v = entry["kind"], entry["value"]
    vb = v.encode("utf-8")
    if vb in clean:
        return False, "exact value still present"
    rp = entry.get("random_part")
    if rp:
        for i in range(len(rp) - 4):
            if rp[i:i + 5].encode() in clean:
                return False, "a 5-character run of the random part survives"
        return True, "masked"
    if kind.startswith("email"):
        if v.split("@")[0].encode() in clean:
            return False, "local part survives"
        return True, "masked"
    if kind.startswith("ipv4"):
        _, _, c, d = v.split(".")
        left = [n for n, o in (("third", c), ("fourth", d)) if standalone(o).search(clean)]
        if left:
            return False, "%s octet survives" % " and ".join(left)
        return True, "masked"
    return False, "unknown kind"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", default=None)
    a = ap.parse_args()
    with open(a.manifest, encoding="utf-8") as f:
        man = json.load(f)
    with open(a.input, "rb") as f:
        src = f.read()
    with open(a.output, "rb") as f:
        clean = f.read()

    mask_results = []
    for e in man["values"]:
        ok, why = check_value(e, clean)
        mask_results.append({"kind": e["kind"], "line": e["line"], "pass": ok, "why": why})
        print("%s  masking   %-18s (app.log line %3d) %s" % (
            "PASS" if ok else "FAIL", e["kind"], e["line"], why))
    masking_ok = all(r["pass"] for r in mask_results)

    src_lines = src.split(b"\n")
    if src_lines and src_lines[-1] == b"":
        src_lines.pop()
    out_lines = clean.split(b"\n")
    want = [(n, src_lines[n - 1]) for n in man["ordinary_lines"]]
    j = 0
    matched = 0
    first_missing = None
    for n, line in want:
        while j < len(out_lines) and out_lines[j] != line:
            j += 1
        if j == len(out_lines):
            first_missing = (n, line)
            break
        matched += 1
        j += 1
    ordinary_ok = matched == len(want)
    if ordinary_ok:
        print("PASS  ordinary  all %d ordinary lines byte-identical and in order" % len(want))
    else:
        print("FAIL  ordinary  %d of %d ordinary lines found in order; first missing is "
              "app.log line %d: %r" % (matched, len(want), first_missing[0],
                                       first_missing[1].decode("utf-8", "replace")))
    print("ITEM masking  " + ("PASS" if masking_ok else "FAIL"))
    print("ITEM ordinary " + ("PASS" if ordinary_ok else "FAIL"))
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump({"masking": {"pass": masking_ok, "values": mask_results},
                       "ordinary": {"pass": ordinary_ok, "matched": matched,
                                    "total": len(want)},
                       "app_log_sha256": man.get("app_log_sha256")}, f, indent=2)
            f.write("\n")
    return 0 if (masking_ok and ordinary_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
