#!/usr/bin/env python3
"""Score q19 runs (Python stdlib only).

Each run folder was made by new_run.py and holds the agent transcript written by
pty_drive.py --out RUN/agent (agent.txt, agent.json). Then:

  python3 check_run.py --state-dir STATE RUNS/r1 RUNS/r2 RUNS/r3 [--egress-dir EGRESS]

Per run (window = run start .. agent end + 5 s, cut at the next run's start):
  hello           check_hello.py passes on the run's workdir
  in_time         not killed by the time limit, and the answer came within --limit
                  seconds (default 900): elapsed, or the last output when pty_drive
                  ended the session by --done / --done-file
  server_requests requests the logging proxy (the self-hosted server's front)
                  relayed in the window, with their paths
  egress          egress.py report for the window (when --egress-dir given)
  login_hits      lines that mention login / sign-in / account (for the grader)
L2-2 passes when at least 2 runs have hello and in_time.
L2-3 passes when every run that passed L2-2 shows at least one server request
and every run's egress result is "pass".
Exit 0 when L2-2 and L2-3 pass, 1 otherwise.
"""

import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--state-dir", default=os.path.join(HERE, "state"))
    ap.add_argument("--proxy-dir", help="default: STATE/proxy")
    ap.add_argument("--egress-dir")
    ap.add_argument("--limit", type=float, default=900.0)
    a = ap.parse_args()
    proxy_dir = a.proxy_dir or os.path.join(a.state_dir, "proxy")
    checker = load(os.path.join(HERE, "check_hello.py"), "q19_check_hello")
    egress = load(os.path.join(HERE, "egress", "egress.py"), "egress") if a.egress_dir else None
    reqs_all = read_jsonl(os.path.join(proxy_dir, "requests.jsonl"))
    starts = sorted(json.load(open(os.path.join(r, "run.json"), encoding="utf-8"))["t_start"] for r in a.runs)
    results = []
    for run in a.runs:
        with open(os.path.join(run, "run.json"), encoding="utf-8") as f:
            info = json.load(f)
        later = [t for t in starts if t > info["t_start"]]
        res = {"run": os.path.basename(run.rstrip("/")), "workdir": info["workdir"]}
        t0 = info["t_start"]
        try:
            with open(os.path.join(run, "agent.json"), encoding="utf-8") as f:
                summ = json.load(f)
            with open(os.path.join(run, "agent.txt"), encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            res.update({"error": "missing agent transcript: %s" % e, "pass": False})
            results.append(res)
            continue
        t1 = min([summ.get("end", t0) + 5] + later[:1])
        res["elapsed"] = summ.get("elapsed")
        res["answer_time"] = answer_time(summ)
        res["in_time"] = (not summ.get("timed_out")) and res["answer_time"] <= a.limit
        res["hello"] = checker.check(info["workdir"])
        reqs = [e for e in reqs_all if t0 <= e.get("ts_start", 0) <= t1]
        res["server_requests"] = len(reqs)
        res["server_paths"] = sorted({"%s %s" % (e.get("method"), e.get("path")) for e in reqs})
        res["server_models"] = sorted({str(e.get("model")) for e in reqs if e.get("model")})
        res["login_hits"] = [l.strip()[:160] for l in text.splitlines() if LOGIN.search(l)][:20]
        res["approvals"] = len(summ.get("approvals", []))
        res["pass"] = bool(res["hello"]["pass"] and res["in_time"])
        if egress:
            # egress window ends when the agent ended (the egress stop that follows must not fall inside it)
            rep = egress.build_report(a.egress_dir, since=t0, until=min(t1, summ.get("end", t1)))
            res["egress"] = rep["result"]
            res["egress_names"] = rep["layers"]["dns"]["names"]
            res["egress_remotes"] = sorted(set(rep["layers"]["strace"]["remotes"] + rep["layers"]["poll"]["remotes"]))
        results.append(res)
    n_pass = sum(1 for r in results if r.get("pass"))
    out = {"runs": results, "runs_passed": n_pass, "L2-2": "pass" if n_pass >= 2 else "fail"}
    seen = all(r.get("server_requests", 0) > 0 for r in results if r.get("pass")) and n_pass >= 1
    if egress:
        eg = [r.get("egress") for r in results]
        eg_state = "pass" if all(e == "pass" for e in eg) else ("fail" if "fail" in eg else "incomplete")
    else:
        eg_state = "not checked"
    out["server_log_shows_requests"] = seen
    out["egress"] = eg_state
    out["L2-3"] = "pass" if (seen and eg_state == "pass") else ("incomplete" if seen and eg_state != "fail" else "fail")
    print(json.dumps(out, indent=1))
    return 0 if (out["L2-2"] == "pass" and out["L2-3"] == "pass") else 1


if __name__ == "__main__":
    sys.exit(main())
