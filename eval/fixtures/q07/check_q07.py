#!/usr/bin/env python3
"""Verdicts for q07 L2-2, L2-3 and L2-5 from the run reports (stdlib only).

    check_q07.py --ok RUN_OK.json --ok-log LOG_OK.jsonl
                 --s500 RUN_500.json --okfalse RUN_OKFALSE.json [--report verdict.json]

RUN_*.json are egress_run.py reports of the same CLI command run against server.py in
mode ok, status500 and okfalse; LOG_OK.jsonl is server.py's log of the ok run.

ok_run      the ok run exits 0, did not time out, and the server saw all three requests:
            GET /health, GET /widgets, POST /orders whose JSON body equals requests.json
fail_runs   the status500 run and the okfalse run both exit non-zero and did not time out
egress      all three runs have egress.verdict == "pass"
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ok", required=True)
    ap.add_argument("--ok-log", required=True)
    ap.add_argument("--s500", required=True)
    ap.add_argument("--okfalse", required=True)
    ap.add_argument("--requests", default=os.path.join(HERE, "requests.json"))
    ap.add_argument("--report")
    a = ap.parse_args()
    runs = {k: json.load(open(p, encoding="utf-8")) for k, p in (("ok", a.ok), ("status500", a.s500),
                                                                  ("okfalse", a.okfalse))}
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
    eg = {k: r.get("egress", {}).get("verdict") for k, r in runs.items()}
    egress = {"pass": all(v == "pass" for v in eg.values()), "verdicts": eg,
              "first_attempts": {k: [x.get("line") for x in r.get("egress", {}).get("attempts", [])[:3]]
                                 for k, r in runs.items()}}
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
