#!/usr/bin/env python3
"""Score q18 runs (Python stdlib only).

Each run folder was made by new_run.py and holds the client transcript written by
pty_drive.py --out RUN/client (client.txt, client.json). Then:

  python3 check_run.py --state-dir STATE RUNS/r1 RUNS/r2 RUNS/r3 [--egress-dir EGRESS]

Per run (window = run start .. client end + 5 s, cut at the next run's start):
  tools_call      server.log has a tools/call of get_project_code for project alpha
  model_reply     a model response relayed by the logging proxy after that call
                  contains the run's token in its generated text (not in the
                  request, so an echoed tool result does not count)
  transcript      the token appears in the client's terminal output
  in_time         not killed by the time limit, and the answer came within --limit
                  seconds (default 600): elapsed, or the last output when pty_drive
                  ended the session by --done / --done-file
  egress          the shared egress verdict (when --egress-dir given): the run's own
                  traced step (label = run folder name) in full, every other step in
                  that folder (config steps, leftovers) inside the window
                  (eval/fixtures/_shared/egress.py window_verdict)
  login_hits      lines that mention login / sign-in / account (for the grader)
L2-2 passes when at least 2 runs have tools_call, model_reply, transcript and
in_time all true. L2-3 passes when every run's egress result is "pass".
Exit 0 when L2-2 passes (and L2-3 if checked), 1 otherwise.
"""

import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.environ.get("SHARED") or os.path.join(HERE, "..", "_shared")
LOGIN = re.compile(r"(?i)\b(log ?in|sign ?in|sign ?up|create an account|account required|authenticat\w*|device code|subscription)\b")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def answer_time(summ):
    """Seconds until the answer: last output when pty_drive ended the session by --done, else elapsed."""
    if summ.get("ended_by") == "done" and summ.get("last_output_t") is not None:
        return summ["last_output_t"]
    return summ.get("elapsed", 1e9)


def read_jsonl(path):
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def check_one(run, state, proxy_dir, limit, egress_mod, egress_dir, proxy_mod, server_mod, next_start=None):
    with open(os.path.join(run, "run.json"), encoding="utf-8") as f:
        info = json.load(f)
    token = info["token"]
    t0 = info["t_start"]
    res = {"run": os.path.basename(run.rstrip("/"))}
    try:
        with open(os.path.join(run, "client.json"), encoding="utf-8") as f:
            summ = json.load(f)
        with open(os.path.join(run, "client.txt"), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        res.update({"error": "missing client transcript: %s" % e, "pass": False})
        return res
    t1 = summ.get("end", t0) + 5
    if next_start is not None:
        t1 = min(t1, next_start)
    res["elapsed"] = summ.get("elapsed")
    res["answer_time"] = answer_time(summ)
    res["in_time"] = (not summ.get("timed_out")) and res["answer_time"] <= limit

    calls = [e for e in read_jsonl(os.path.join(state, "server.log"))
             if e.get("event") == "tools_call" and t0 <= e.get("ts", 0) <= t1]
    good = [e for e in calls if e.get("tool") == "get_project_code" and e.get("result") == "token"]
    res["tools_calls"] = len(calls)
    res["tools_call"] = bool(good)
    first_call = min((e["ts"] for e in good), default=None)

    reqs = [e for e in read_jsonl(os.path.join(proxy_dir, "requests.jsonl"))
            if t0 <= e.get("ts_start", 0) <= t1]
    res["model_requests"] = len(reqs)
    res["model_reply"] = False
    if first_call is not None:
        for e in reqs:
            if e.get("ts_end", 0) < first_call:
                continue
            p = os.path.join(proxy_dir, "%06d.resp" % e["id"])
            if not os.path.exists(p):
                continue
            with open(p, "rb") as f:
                if token in proxy_mod.model_text(f.read()):
                    res["model_reply"] = True
                    res["model_reply_request_id"] = e["id"]
                    break
    squashed = re.sub(r"\s+", "", text)
    res["transcript"] = token in text or token in squashed
    res["login_hits"] = [l.strip()[:160] for l in text.splitlines() if LOGIN.search(l)][:20]
    res["approvals"] = len(summ.get("approvals", []))
    res["pass"] = bool(res["tools_call"] and res["model_reply"] and res["transcript"] and res["in_time"])
    if egress_dir:
        # egress window ends when the client ended (the egress stop that follows must not fall inside it)
        rep = egress_mod.window_verdict(egress_dir, res["run"], since=t0, until=min(t1, summ.get("end", t1)))
        res["egress"] = rep["result"]
        res["egress_reason"] = rep["reason"]
        res["egress_attempts"] = rep["first_attempts"]
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--state-dir", default=os.path.join(HERE, "state"))
    ap.add_argument("--proxy-dir", help="default: STATE/proxy")
    ap.add_argument("--egress-dir")
    ap.add_argument("--limit", type=float, default=600.0)
    a = ap.parse_args()
    proxy_dir = a.proxy_dir or os.path.join(a.state_dir, "proxy")
    proxy_mod = load(os.path.join(HERE, "tools", "logging_proxy.py"), "logging_proxy")
    server_mod = load(os.path.join(HERE, "mcp_server", "project_code_server.py"), "project_code_server")
    egress_mod = load(os.path.join(SHARED, "egress.py"), "egress") if a.egress_dir else None
    starts = sorted(json.load(open(os.path.join(r, "run.json"), encoding="utf-8"))["t_start"] for r in a.runs)
    results = []
    for r in a.runs:
        t0 = json.load(open(os.path.join(r, "run.json"), encoding="utf-8"))["t_start"]
        later = [t for t in starts if t > t0]
        results.append(check_one(r, a.state_dir, proxy_dir, a.limit, egress_mod, a.egress_dir, proxy_mod,
                                 server_mod, later[0] if later else None))
    n_pass = sum(1 for r in results if r.get("pass"))
    out = {"runs": results, "runs_passed": n_pass, "L2-2": "pass" if n_pass >= 2 else "fail"}
    if a.egress_dir:
        out["L2-3"] = "pass" if all(r.get("egress") == "pass" for r in results) else \
            ("fail" if any(r.get("egress") == "fail" for r in results) else "undetermined")
    print(json.dumps(out, indent=1))
    ok = out["L2-2"] == "pass" and out.get("L2-3", "pass") == "pass"
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
