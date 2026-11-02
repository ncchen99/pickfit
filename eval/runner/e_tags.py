"""E loss tags for run 1 (eval/README.md 9.1 E; 9.4: the Claude tagger decides, Muse Spark Open describes).

For each run 1 question where the experimental answer fails L1, fails an L2 that was run, or loses to control on
the same layer, one evidence bundle is built from the A3 snapshot and the run records: pickfit's calls and
responses (stream-json), the agent's pick, the L1 and L2 results, the reference tools (every pick that passed L1
in any group and round, plus C6's), and whether each reference tool is in pickfit's data (data/software at
4e0dd4b) or only in the candidate pool. Both taggers get the same fixed instructions (E's ordered table, verbatim)
and the same bundle. Also writes the breakdown of empty pickfit responses (coordinator 2026-11-02).

  uv run --with anthropic==2.3.0 python eval/runner/e_tags.py --out eval/results/e-tags [--dry-run]
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade  # noqa: E402

ROOT = grade.ROOT
RES = ROOT / "eval" / "results"
SNAP = "4e0dd4b"
CAND = Path.home() / ".pickfit" / "eval-snapshot-20261102" / "candidates"
TAGS = ["not_called", "tool_error", "overreach", "wrong_fact", "bad_match", "install_failed", "agent_changed_steps",
        "agent_ignored", "not_in_data", "filtered_out", "not_matched", "no_known_fit", "other"]
SYSTEM = """You tag why an AI agent connected to a software-recommendation tool ("pickfit") lost on one evaluation question. You see only the evidence bundle; do not use outside knowledge about the tools.

Rules (fixed before the evaluation, quoted verbatim in Chinese; apply them in order, the first that holds is the primary tag, every other one that holds is a secondary tag):

| 順序 | 標記 | 條件 |
|---|---|---|
| 1 | `not_called` | 受測 agent 沒呼叫 pickfit |
| 2 | `tool_error` | pickfit 回錯誤、逾時、空結果，或標為降級 |
| 3 | `overreach` | q10、q20：pickfit 的第一個推薦需要另外安裝，而且沒有提內建做法 |
| 4 | `wrong_fact` | agent 的首選是 pickfit 推薦的工具，L1 沒過，而且 pickfit 對沒過那一項的描述與官方不符 |
| 5 | `bad_match` | 同上，但 pickfit 的描述正確：pickfit 推了不符條件的工具 |
| 6 | `install_failed` | agent 的首選是 pickfit 推薦的工具，L1 過，照 pickfit 原樣步驟 L2 不過 |
| 7 | `agent_changed_steps` | 同上，但 agent 改了 pickfit 的步驟 |
| 8 | `agent_ignored` | pickfit 推薦了某個參考工具，agent 卻選了別的 |
| 9 | `not_in_data` | 參考工具不在 A3 快照的候選庫 |
| 10 | `filtered_out` | 參考工具在候選庫，但被規則、初篩或驗證排除 |
| 11 | `not_matched` | 參考工具在 pickfit 的資料裡、可以推薦，但 pickfit 沒回傳 |
| 12 | `no_known_fit` | 沒有任何參考工具 |
| 13 | `other` | 以上都不成立，附一句說明 |

Notes for reading the bundle: a "reference tool" is any tool that passed L1 for this question in any group or round, or that the C6 check found. "In pickfit's data" means a record in data/software at the snapshot; "in the candidate pool" means a row in the discovery database at the snapshot (a tool in the pool but not in the data was excluded somewhere on the way). An "empty result" is a pickfit response with no picks; a response that only names an unverified well-known option still has no picks. Rules 9-11 are judged per reference tool; when there are several, use the one closest to being recommended (11 before 10 before 9) and list the others as secondary.

Reply with JSON only: {"primary": tag, "secondary": [tags], "reason": "<two short sentences in English citing the evidence fields>"}"""
SCHEMA = {"type": "object", "properties": {"primary": {"type": "string", "enum": TAGS},
                                           "secondary": {"type": "array", "items": {"type": "string", "enum": TAGS}},
                                           "reason": {"type": "string"}},
          "required": ["primary", "secondary", "reason"], "additionalProperties": False}


# name matches checked by hand and found to be a different project: (question, reference tool) -> why
FALSE_MATCHES = {("b03", "Atlas"): "pickfit's data has Atlas-Inf/atlas (an LLM inference engine); the b03 answer's Atlas is ariga/atlas, a database schema tool"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def parts(name: str) -> list[str]:
    """Names to look up for a pick: the whole, each '+'-joined part, the text before a parenthesis."""
    out = [name]
    for p in re.split(r"\s\+\s|,", name):
        out += [p.strip(), re.split(r"[\(\[]", p)[0].strip()]
    return [p for p in dict.fromkeys(out) if p and not p.lower().startswith("built-in")]


def data_index() -> dict[str, str]:
    idx = {}
    files = subprocess.run(["git", "ls-tree", "--name-only", SNAP, "data/software/"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    for f in files:
        d = json.loads(subprocess.run(["git", "show", f"{SNAP}:{f}"], cwd=ROOT, capture_output=True, text=True).stdout)
        keys = [d.get("slug"), d.get("name"), ((d.get("repo") or {}).get("full_name") or "").split("/")[-1]] + list(d.get("aliases") or [])
        for k in keys:
            if k:
                idx.setdefault(norm(k), d["slug"])
    return idx


def candidate_index() -> dict[str, dict[str, Any]]:
    idx = {}
    for db in glob.glob(str(CAND / "*" / "pipeline.db")):
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        tables = {t for (t,) in con.execute("select name from sqlite_master where type='table'")}
        if "candidates" not in tables:
            con.close()
            continue
        for rid, full, aliases, label in con.execute("select repo_id, full_name, aliases, rule_label from candidates"):
            pre = (con.execute("select status, result from prescreens where repo_id=? order by id desc limit 1", (rid,)).fetchone()
                   if "prescreens" in tables else None)
            info = {"full_name": full, "rule_label": label, "prescreen": (pre[0] if pre else None),
                    "prescreen_result": (json.loads(pre[1]).get("verdict") if pre and pre[1] and pre[1].startswith("{") else None)}
            for k in [full.split("/")[-1], full] + json.loads(aliases or "[]"):
                idx.setdefault(norm(k), info)
        con.close()
    return idx


def lookup(name: str, data: dict, cand: dict) -> dict[str, Any]:
    hits = {"in_data": None, "in_candidates": None}
    for p in parts(name):
        hits["in_data"] = hits["in_data"] or data.get(norm(p))
        hits["in_candidates"] = hits["in_candidates"] or cand.get(norm(p))
    if name.lower().startswith("built-in"):
        hits["note"] = "built-in way, not a tool record"
    return hits


def pickfit_responses(rnd: str, q: str, group: str) -> list[dict[str, Any]]:
    f = RES / "runs" / rnd / q / group / "attempt-1" / "stream.jsonl"
    names, out = {}, []
    if not f.exists():
        return out
    for line in f.open(encoding="utf-8"):
        try:
            m = (json.loads(line).get("message") or {})
        except ValueError:
            continue
        for b in m.get("content") or [] if isinstance(m.get("content"), list) else []:
            if b.get("type") == "tool_use":
                names[b["id"]] = (b["name"], b.get("input"))
            if b.get("type") == "tool_result" and "pickfit" in names.get(b.get("tool_use_id"), ("",))[0]:
                name, inp = names[b["tool_use_id"]]
                c = b.get("content")
                text = "".join(x.get("text", "") for x in c) if isinstance(c, list) else str(c)
                try:
                    body = json.loads(text)
                except ValueError:
                    body = None
                picks = [(p.get("name") or p.get("slug")) for p in (body or {}).get("picks", [])] if isinstance(body, dict) else None
                out.append({"tool": name.split("__")[-1], "input": inp, "is_error": bool(b.get("is_error")),
                            "picks": picks, "degraded": (body or {}).get("degraded") if isinstance(body, dict) else None,
                            "well_known": ((body or {}).get("well_known_option") or {}).get("name") if isinstance(body, dict) else None,
                            "text_if_unparsed": None if body is not None else text[:300]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    final = json.loads((RES / "final" / "results.json").read_text(encoding="utf-8"))
    rows = json.loads((RES / "final" / "answers-l1.json").read_text(encoding="utf-8"))
    claude_a = {r["item_id"]: r for r in grade.read_batch(RES / "grades" / "claude-A.jsonl")} if False else \
        {json.loads(x)["item_id"]: json.loads(x) for x in (RES / "grades" / "claude-A.jsonl").read_text(encoding="utf-8").splitlines()}
    data, cand = data_index(), candidate_index()
    refs: dict[str, set[str]] = {}
    for r in rows:
        if r["round"] in ("run1", "run2", "run3", "haiku") and r["l1"] == "pass" and r["item_id"]:
            refs.setdefault(r["question"], set()).add(r["pick"])
    refs.setdefault("q01", set()).update(final["c6"]["q01_candidates_passing"])

    bundles = []
    for t in final["run1_table"]:
        q, c, e = t["question"], t["control"], t["experimental"]
        l1_lose = c["l1"] == "pass" and e["l1"] != "pass"
        l2_run = e["l2"] in ("pass", "fail")
        l2_lose = c["l2"] == "pass" and e["l2"] == "fail"
        why = [w for w, ok in (("experimental L1 not passed", e["l1"] != "pass"), ("experimental L2 run and failed", l2_run and e["l2"] == "fail"),
                                ("lost to control on L1", l1_lose), ("lost to control on L2", l2_lose)) if ok]
        if not why:
            continue
        item = claude_a.get(e["item"] or "", {})
        resp = pickfit_responses("run1", q, "experimental")
        returned = sorted({p for x in resp for p in (x["picks"] or [])})
        b = {"question": q, "why_tagged": why,
             "agent_pick": e["pick"], "experimental_l1": e["l1"], "l1_grader_checks": [{"check": c_["check"], "verdict": c_["verdict"], "reason": c_["reason"]}
                                                                                     for c_ in item.get("checks", [])],
             "experimental_l2": e["l2"], "experimental_l2_items": json.loads((RES / "l2" / "l2-results.json").read_text(encoding="utf-8"))["results"].get(q, {}).get("experimental", {}).get("items"),
             "control_pick": c["pick"], "control_l1": c["l1"], "control_l2": c["l2"],
             "pickfit_calls": resp, "pickfit_returned_picks": returned,
             "agent_pick_returned_by_pickfit": any(norm(p) in {norm(x) for x in parts(e["pick"] or "")} for p in returned),
             "agent_used_get_install_guide": any(x["tool"] == "get_install_guide" for x in resp),
             "reference_tools": {r: lookup(r, data, cand) for r in sorted(refs.get(q, set()))},
             "agent_pick_lookup": lookup(e["pick"] or "", data, cand)}
        for r, h in b["reference_tools"].items():
            h["returned_by_pickfit"] = any(norm(p) in {norm(x) for x in parts(r)} for p in returned)
            if h.get("in_candidates"):
                h["in_candidates"] = {k: h["in_candidates"][k] for k in ("full_name", "rule_label", "prescreen", "prescreen_result")}
        bundles.append(b)
    (a.out / "bundles-run1.json").write_text(json.dumps(bundles, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # empty pickfit responses, every round of the 20 questions (experimental group, the model-matched one)
    empty = []
    for r in rows:  # B set reference tools, for the B set's empty responses
        if r["round"] == "bset" and r["l1"] == "pass" and r["item_id"]:
            refs.setdefault(r["question"], set()).add(r["pick"])
    rounds = [(r, f"q{i:02d}") for r in ("run1", "run2", "run3", "haiku") for i in range(1, 21)] + [("bset", f"b{i:02d}") for i in range(1, 13)]
    for rnd, q in rounds:
        if True:
            for x in pickfit_responses(rnd, q, "experimental"):
                if x["picks"] == []:
                    in_data = [r for r in sorted(refs.get(q, set())) if lookup(r, data, cand)["in_data"] and (q, r) not in FALSE_MATCHES]
                    empty.append({"round": rnd, "question": q, "tool": x["tool"], "well_known": x["well_known"],
                                  "reference_tools_in_pickfit_data": in_data,
                                  "verdict": "miss (a tool that passed L1 was in pickfit's data)" if in_data else
                                             "correct: no tool that passed L1 is in pickfit's data"})
    total = sum(len(pickfit_responses(r, q, "experimental")) for r, q in rounds)
    by_set = {s_: {"responses": sum(len(pickfit_responses(r, q, "experimental")) for r, q in rounds if (r == "bset") == (s_ == "B")),
                   "empty": sum(1 for x in empty if (x["round"] == "bset") == (s_ == "B"))} for s_ in ("A", "B")}
    (a.out / "empty-responses.json").write_text(json.dumps({"responses": total, "empty": len(empty), "by_set": by_set,
        "correct": sum(1 for x in empty if x["verdict"].startswith("correct")), "miss": sum(1 for x in empty if x["verdict"].startswith("miss")),
        "note": "name matching against data/software at 4e0dd4b, matches checked by hand (false matches: " + json.dumps({f"{k[0]}:{k[1]}": v for k, v in FALSE_MATCHES.items()}) + "); 'correct' means no tool that passed L1 for that question is in pickfit's data, so returning nothing was right for pickfit's data, not that no such tool exists",
        "rows": empty}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(len(bundles), "questions to tag;", len(empty), "empty of", total, "experimental pickfit responses")
    if a.dry_run:
        return 0

    config = grade.load_config()
    for tagger, call in (("claude", None), ("muse", grade.call_muse)):
        out = a.out / f"{tagger}-run1.jsonl"
        done = {json.loads(x)["question"] for x in out.read_text(encoding="utf-8").splitlines()} if out.exists() else set()
        for b in bundles:
            if b["question"] in done:
                continue
            user = json.dumps(b, ensure_ascii=False, indent=1)
            if tagger == "claude":
                import anthropic
                sys.path.insert(0, str(ROOT))
                from pickfit.env import read_env
                client = anthropic.Anthropic(api_key=read_env(["ANTHROPIC_API_KEY"])["ANTHROPIC_API_KEY"])
                r = client.messages.create(model=config["grader_model"], max_tokens=4000, system=SYSTEM, messages=[{"role": "user", "content": user}],
                                           output_config={"effort": config["grader_effort"], "format": {"type": "json_schema", "schema": SCHEMA}})
                u = r.usage
                usage = {"input_tokens": u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
                         "cached_input_tokens": u.cache_read_input_tokens or 0, "output_tokens": u.output_tokens}
                res = {"model": r.model, "text": next((x.text for x in r.content if x.type == "text"), ""), "request_id": r._request_id, "usage": usage}
                cap = "grading"
            else:
                res = call(config, SYSTEM, user)
                cap = "baseten_grading"
            res["cost_usd"] = round(grade.cost(res["model"] if res["model"] in grade.PRICES else config["muse_model"], res["usage"]), 6)
            grade.record({"use": f"e_tag_{tagger}", "question": b["question"], "at": grade.now(), "model": res["model"],
                          "request_id": res["request_id"], "usage": res["usage"], "cost_usd": res["cost_usd"]}, cap)
            tag = grade.parse_json_reply(res["text"])
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"question": b["question"], "tagger": tagger, "model": res["model"], "tag": tag,
                                     "raw": None if tag else res["text"][:1000]}, ensure_ascii=False) + "\n")
            print(tagger, b["question"], (tag or {}).get("primary"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
