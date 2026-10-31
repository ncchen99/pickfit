#!/usr/bin/env python3
"""Verdicts for q06 L2-2, L2-3 and L2-4 from the run's evidence files (stdlib only).

    check_q06.py --client-report client_report.json --mock-log mock_log.jsonl
                 --mock-state mock_state.json [--egress REPORT.json]... [--post-body post_body.json]
                 [--report verdict.json]

--egress takes the egress_run.py reports of the generation step (if the answer has one)
and of the session (server startup plus both tool calls); give every one of them.

tools_list  exactly two tools are listed (all pages) and they map one-to-one onto the two
            operations, either by name/title/description/schema (client mapping) or by
            behaviour (one tool's call produced GET /items/42, the other's POST /items)
tool_calls  the GET call's result (content and structuredContent) contains the mock's
            per-run token and is not an error, the mock log has GET /items/42, and the
            mock log has POST /items whose parsed JSON body equals post_body.json
egress      every egress report has egress.verdict == "pass" (strace saw no attempt to
            reach anything but loopback); at least the session report must be given
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_log(path):
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client-report", required=True)
    ap.add_argument("--mock-log", required=True)
    ap.add_argument("--mock-state", required=True)
    ap.add_argument("--egress", action="append", default=[])
    ap.add_argument("--post-body", default=os.path.join(HERE, "post_body.json"))
    ap.add_argument("--report")
    a = ap.parse_args()
    rep = json.load(open(a.client_report, encoding="utf-8"))
    state = json.load(open(a.mock_state, encoding="utf-8"))
    body = json.load(open(a.post_body, encoding="utf-8"))
    log = [e for e in load_log(a.mock_log) if e.get("kind") == "api"]
    token = state["token"]

    get_hits = [e for e in log if e["method"] == "GET" and e["path"] == "/items/42"]
    post_hits = [e for e in log if e["method"] == "POST" and e["path"] == "/items"]
    post_match = [e for e in post_hits if e.get("body_json") == body]

    calls = rep.get("calls") or {}
    get_call, post_call = calls.get("get") or {}, calls.get("post") or {}
    get_blob = json.dumps(get_call.get("result"), ensure_ascii=False) if "result" in get_call else ""
    get_ok = bool(get_blob) and token in get_blob and not get_call.get("isError")

    def in_window(entries, call):
        s, e = call.get("started_utc"), call.get("ended_utc")
        return [x for x in entries if s and e and s <= x["ts"] <= e]

    get_by_call = bool(in_window(get_hits, get_call))
    post_by_call = bool(in_window(post_hits, post_call))
    mapping = rep.get("mapping") or {}
    behaviour = (get_by_call and post_by_call and get_call.get("tool") and post_call.get("tool")
                 and get_call.get("tool") != post_call.get("tool"))
    count = rep.get("tool_count")
    tools_list = {
        "pass": count == 2 and bool(mapping.get("bijection") or behaviour),
        "tool_count": count,
        "tool_names": [t.get("name") for t in rep.get("tools") or []],
        "mapping": mapping,
        "mapped_by_behaviour": bool(behaviour),
    }
    tool_calls = {
        "pass": get_ok and bool(get_hits) and bool(post_match),
        "get_result_has_token": get_ok,
        "mock_saw_get_items_42": len(get_hits),
        "mock_saw_post_items": len(post_hits),
        "post_body_matches": len(post_match),
        "post_bodies_seen": [e.get("body_json") for e in post_hits][:5],
        "other_api_requests": [(e["method"], e["path"], e["status"]) for e in log
                               if e not in get_hits and e not in post_hits][:20],
    }
    eg = []
    for path in a.egress:
        r = json.load(open(path, encoding="utf-8"))
        eg.append({"report": path, "command": r.get("command"), "verdict": r.get("egress", {}).get("verdict"),
                   "attempts": r.get("egress", {}).get("egress_attempts"),
                   "first_attempts": [x.get("line") for x in r.get("egress", {}).get("attempts", [])[:5]]})
    egress = {"pass": bool(eg) and all(x["verdict"] == "pass" for x in eg), "reports": eg}
    out = {"tools_list": tools_list, "tool_calls": tool_calls, "egress": egress,
           "client_errors": rep.get("errors"), "mock_token": token}
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    print("tools_list=%s tool_calls=%s egress=%s" % tuple(
        "PASS" if x["pass"] else "FAIL" for x in (tools_list, tool_calls, egress)), file=sys.stderr)
    sys.exit(0 if tools_list["pass"] and tool_calls["pass"] and egress["pass"] else 1)


if __name__ == "__main__":
    main()
