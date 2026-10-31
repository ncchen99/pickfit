#!/usr/bin/env python3
"""Verdicts for q07 L2-2, L2-3 and L2-5 from the run reports (stdlib only).

    check_q07.py --runs EGRESS_DIR --ok-log LOG_OK.jsonl [--report verdict.json]

EGRESS_DIR is the folder of eval/fixtures/_shared/egress.py runs of the same CLI command
against server.py, labelled ok, status500 and okfalse; LOG_OK.jsonl is server.py's log of
the ok run.

ok_run      the ok run exits 0, did not time out, and the server saw all three requests:
            GET /health, GET /widgets, POST /orders whose JSON body equals requests.json
fail_runs   the status500 run and the okfalse run both exit non-zero and did not time out
egress      the shared egress verdict (_shared/README.md section 1) of all three runs is "pass"
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("SHARED") or os.path.join(HERE, "..", "_shared"))
import egress as shared_egress  # noqa: E402
MODES = ("ok", "status500", "okfalse")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--ok-log", required=True)
    ap.add_argument("--requests", default=os.path.join(HERE, "requests.json"))
    ap.add_argument("--report")
    a = ap.parse_args()
    runs = {r["label"]: r for r in shared_egress.step_verdicts(a.runs, MODES)}
    spec = json.load(open(a.requests, encoding="utf-8"))
    log = [json.loads(ln) for ln in open(a.ok_log, encoding="utf-8") if ln.strip()]
    want_body = next(r["body"] for r in spec["requests"] if r["id"] == "orders")
    seen = {
        "GET /health": any(e["method"] == "GET" and e["path"] == "/health" for e in log),
        "GET /widgets": any(e["method"] == "GET" and e["path"] == "/widgets" for e in log),
        "POST /orders with body": any(e["method"] == "POST" and e["path"] == "/orders"
                                      and e.get("body_json") == want_body for e in log),
    }
    ok = runs["ok"]
    ok_run = {"pass": ok["exit_code"] == 0 and not ok["timed_out"] and all(seen.values()),
              "exit_code": ok["exit_code"], "requests_seen": seen,
              "all_requests_logged": [(e["method"], e["path"], e["status"]) for e in log][:20]}
    fails = {k: {"exit_code": runs[k]["exit_code"], "timed_out": runs[k]["timed_out"]}
             for k in ("status500", "okfalse")}
    fail_runs = {"pass": all(v["exit_code"] != 0 and not v["timed_out"] for v in fails.values()), **fails}
    eg = {k: r["result"] for k, r in runs.items()}
    egress = {"pass": all(v == "pass" for v in eg.values()), "verdicts": eg,
              "first_attempts": {k: r["first_attempts"][:3] for k, r in runs.items()}}
    commands = {k: r.get("command") for k, r in runs.items()}
    same_cmd = len({json.dumps(c) for c in commands.values()}) == 1
    out = {"ok_run": ok_run, "fail_runs": fail_runs, "egress": egress, "same_command_all_runs": same_cmd,
           "commands": commands}
    if not same_cmd:
        out["fail_runs"]["pass"] = False
        out["fail_runs"]["note"] = "the three runs must use the identical command"
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    print("ok_run=%s fail_runs=%s egress=%s" % tuple(
        "PASS" if out[k]["pass"] else "FAIL" for k in ("ok_run", "fail_runs", "egress")), file=sys.stderr)
    sys.exit(0 if all(out[k]["pass"] for k in ("ok_run", "fail_runs", "egress")) else 1)


if __name__ == "__main__":
    main()
