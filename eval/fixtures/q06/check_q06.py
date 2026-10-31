#!/usr/bin/env python3
"""Verdicts for q06 L2-2, L2-3 and L2-4 from the run's evidence files (stdlib only).

    check_q06.py --client-report client_report.json --mock-log mock_log.jsonl
                 --mock-state mock_state.json --egress-dir DIR --egress-label session [--egress-label gen]
                 [--post-body post_body.json] [--report verdict.json]

--egress-dir is the folder of eval/fixtures/_shared/egress.py runs; --egress-label names the
session step (server startup plus both tool calls) and the generation step (if the answer has
one). Give every one of them.

tools_list  exactly two tools are listed (all pages) and they map one-to-one onto the two
            operations, either by name/title/description/schema (client mapping) or by
            behaviour (one tool's call produced GET /items/42, the other's POST /items)
tool_calls  the GET call's result (content and structuredContent) contains the mock's
            per-run token and is not an error, the mock log has GET /items/42, and the
            mock log has POST /items whose parsed JSON body equals post_body.json
egress      the shared egress verdict (_shared/README.md section 1) of the named steps is "pass":
            strace saw no attempt to reach anything but loopback; at least the session step
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("SHARED") or os.path.join(HERE, "..", "_shared"))
import egress as shared_egress  # noqa: E402


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
    ap.add_argument("--egress-dir")
    ap.add_argument("--egress-label", action="append", default=[])
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
    eg = shared_egress.step_verdicts(a.egress_dir, a.egress_label) if a.egress_dir and a.egress_label else []
    egress = {"pass": bool(eg) and all(x["result"] == "pass" for x in eg), "steps": eg}
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
