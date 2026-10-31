#!/usr/bin/env python3
"""Score the five q17 answers (Python stdlib only).

Each frozen question is run once with pty_drive.py, with --out RUN/<id>
(for example RUN/q17-1), which leaves RUN/q17-1.txt (transcript without escape
codes) and RUN/q17-1.json (timing). Then:

  python3 check_answers.py --run-dir RUN [--egress-report RUN/egress-report.json]

Per question it reports:
  answered    the answer came within --time-limit seconds (default 180; the
              run's elapsed time, or its last output when pty_drive ended an
              interactive session by --done), the run was not killed by the
              time limit, and it printed something
  token       the exact token (case-sensitive substring) is in the transcript
  cited       corpus files named in the transcript (file name with or without
              extension, any path prefix, case-insensitive)
  citation    "pass" when the fact's file is named and at most --max-cited
              (default 5) distinct corpus files are named; "manual" when the
              fact's file is named among more files (the grader decides by
              reading whether the answer cites it as its source); else "fail"

Item verdicts (README section "L2-2" and "L2-3"):
  L2-2  every question answered in time, at least 4 tokens, both PDF-only
        tokens, and the egress report says "pass"
  L2-3  at least 4 citations "pass" (a "manual" counts once the grader
        records it with --manual-pass q17-N)
Exit 0 when both items pass, 1 when either fails, 3 when a manual or the
egress report is still missing.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def answer_time(summ):
    """Seconds until the answer: last output when pty_drive ended the session by --done, else elapsed."""
    if summ.get("ended_by") == "done" and summ.get("last_output_t") is not None:
        return summ["last_output_t"]
    return summ.get("elapsed", 1e9)


def file_patterns(corpus):
    pats = {}
    for n in sorted(os.listdir(corpus)):
        stem = os.path.splitext(n)[0]
        pats[n] = re.compile(r"(?<![A-Za-z0-9_])%s(?:\.(?:md|pdf))?(?![A-Za-z0-9_])" % re.escape(stem), re.I)
    return pats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--questions", default=os.path.join(HERE, "questions.json"))
    ap.add_argument("--corpus", default=os.path.join(HERE, "corpus"))
    ap.add_argument("--time-limit", type=float, default=180.0)
    ap.add_argument("--max-cited", type=int, default=5)
    ap.add_argument("--egress-report")
    ap.add_argument("--manual-pass", action="append", default=[], help="question id whose 'manual' citation the grader accepted")
    a = ap.parse_args()
    with open(a.questions, encoding="utf-8") as f:
        qs = json.load(f)["questions"]
    pats = file_patterns(a.corpus)
    rows = []
    for q in qs:
        base = os.path.join(a.run_dir, q["id"])
        row = {"id": q["id"], "pdf_only": q["pdf_only"], "source_file": q["source_file"]}
        try:
            with open(base + ".txt", encoding="utf-8", errors="replace") as f:
                text = f.read()
            with open(base + ".json", encoding="utf-8") as f:
                summ = json.load(f)
        except OSError as e:
            row.update({"answered": False, "token": False, "citation": "fail", "cited": [], "error": str(e)})
            rows.append(row)
            continue
        row["elapsed"] = summ.get("elapsed")
        row["answer_time"] = answer_time(summ)
        row["timed_out"] = summ.get("timed_out")
        row["exit_code"] = summ.get("exit_code")
        row["answered"] = (not summ.get("timed_out") and row["answer_time"] <= a.time_limit
                           and bool(text.strip()))
        row["token"] = q["token"] in text
        cited = [n for n, p in pats.items() if p.search(text)]
        row["cited"] = cited
        if q["source_file"] in cited:
            if len(cited) <= a.max_cited:
                row["citation"] = "pass"
            elif q["id"] in a.manual_pass:
                row["citation"] = "pass (manual)"
            else:
                row["citation"] = "manual"
        else:
            row["citation"] = "fail"
        rows.append(row)

    egress = None
    if a.egress_report:
        with open(a.egress_report, encoding="utf-8") as f:
            egress = json.load(f).get("result")
    n_tok = sum(1 for r in rows if r["token"])
    pdf_ok = all(r["token"] for r in rows if r["pdf_only"])
    all_answered = all(r["answered"] for r in rows)
    item2 = all_answered and n_tok >= 4 and pdf_ok and egress == "pass"
    if item2:
        item2_state = "pass"
    elif all_answered and n_tok >= 4 and pdf_ok and egress in (None, "incomplete"):
        item2_state = "pending"
    else:
        item2_state = "fail"
    n_cit = sum(1 for r in rows if r["citation"].startswith("pass"))
    n_manual = sum(1 for r in rows if r["citation"] == "manual")
    if n_cit >= 4:
        item3_state = "pass"
    elif n_cit + n_manual >= 4:
        item3_state = "pending"
    else:
        item3_state = "fail"
    report = {"questions": rows, "tokens_found": n_tok, "pdf_only_tokens_found": pdf_ok,
              "all_answered_in_time": all_answered, "egress": egress,
              "L2-2": item2_state, "citations_pass": n_cit, "citations_manual": n_manual, "L2-3": item3_state}
    print(json.dumps(report, indent=1))
    if item2_state == "fail" or item3_state == "fail":
        return 1
    if "pending" in (item2_state, item3_state):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
