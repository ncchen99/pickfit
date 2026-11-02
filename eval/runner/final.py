"""Final tables for the 20-question evaluation and the B set (eval/README.md 6, 9.1 C-D, 9.2, 9.4).

L1 comes from the Claude grader (README 9.4: 念誠 2026-11-02 22:15), unblinded through the answer and item keys;
`unknown` counts as not passed (9.1 C1), `needs_l2` follows C3. L2 comes from results/l2/l2-results.json, D5 from
the d5-*.json files, preferences from blind.unblind_prefer. Muse is descriptive: its disagreements are listed.

  uv run --with pyyaml==6.0.2 python eval/runner/final.py --out eval/results/final
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blind  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "eval" / "results"
EASY = ["q03", "q04", "q07", "q08", "q12", "q13", "q19", "q20"]
MEDIUM = ["q02", "q05", "q06", "q09", "q10", "q14", "q15", "q17", "q18"]
HARD = ["q01", "q11", "q16"]
MAIN = sorted(MEDIUM + HARD)
QS = [f"q{i:02d}" for i in range(1, 21)]


def jl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def grades(batch: str, grader: str) -> dict[str, dict[str, Any]]:
    return {r["item_id"]: r for r in jl(RES / "grades" / f"{grader}-{batch}.jsonl")}


def picks(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return {r["answer_id"]: r for r in csv.DictReader(fh)}


def l2_table() -> dict[str, dict[str, dict[str, Any]]]:
    res = json.loads((RES / "l2" / "l2-results.json").read_text(encoding="utf-8"))["results"]
    out = {}
    for q, groups in res.items():
        out[q] = {}
        for g, v in groups.items():
            if not isinstance(v, dict) or "l2" not in v:  # per-question notes
                continue
            items = v.get("items", {})
            all_run = (v.get("l2") != "not_run" and v.get("all_items_run") is not False
                       and not any(str(t).startswith("not run") for t in items.values()))
            out[q][g] = {"l2": v.get("l2"), "all_items_run": all_run, "pick": v.get("pick")}
    return out


def answer_l1(set_name: str, c6_overturned: bool, l2: dict) -> list[dict[str, Any]]:
    d = RES / "blind"
    akey = json.loads((d / f"answers-{set_name}" / "answers-key.json").read_text(encoding="utf-8"))["answers"]
    ikey = json.loads((d / f"l1-{set_name}" / "l1-items-key.json").read_text(encoding="utf-8"))
    pk = picks(d / f"answers-{set_name}" / "picks.csv")
    cl = grades(set_name, "claude")
    rows = []
    for item_id, aids in ikey["items"].items():
        v = cl[item_id]["overall"]
        for aid in aids:
            a = akey[aid]
            verdict, note = v, ""
            if v == "unknown":  # README 9.4: the grader could not tell; C1 counts it as not passed
                verdict, note = "fail", "grader: unknown (not passed, C1)"
            if v == "needs_l2":  # 9.1 C3
                if a["round"] == "run1" and a["group"] in ("control", "experimental"):
                    l2v = l2.get(a["question"], {}).get(a["group"], {}).get("l2")
                    verdict, note = ("pass" if l2v == "pass" else "fail"), f"L1 from L2 ({l2v})"
                elif a["round"] == "run1":
                    verdict, note = "fail", "L1 needs L2; L2 not run for this group (C3)"
                else:
                    verdict, note = "undetermined", "rerun: needs L2 (C3)"
            rows.append({**a, "answer_id": aid, "item_id": item_id, "grader_verdict": v, "l1": verdict,
                         "pass": verdict == "pass", "note": note, "pick": pk[aid]["pick_tool"] or pk[aid]["pick_kind"]})
    for e in ikey["no_item"]:
        a = akey[e["answer_id"]]
        if e["pick_kind"] == "no_fit":
            verdict = "fail" if c6_overturned else "pass"
            note = "no_fit: " + ("overturned by C6 (a candidate passed L1)" if c6_overturned else "C6 found nothing that passes L1")
        else:
            verdict, note = "fail", "no identifiable recommendation (9.1 C2)"
        rows.append({**a, "answer_id": e["answer_id"], "item_id": None, "grader_verdict": e["pick_kind"], "l1": verdict,
                     "pass": verdict == "pass", "note": note, "pick": e["pick_kind"]})
    return rows


def by(rows: list[dict], rnd: str, group: str) -> dict[str, dict]:
    return {r["question"]: r for r in rows if r["round"] == rnd and r["group"] == group}


def count(m: dict[str, dict], qs: list[str]) -> int:
    return sum(1 for q in qs if m.get(q, {}).get("pass"))


def disagreements(batch: str) -> list[dict[str, Any]]:
    c, m = grades(batch, "claude"), grades(batch, "muse")
    return [{"item_id": i, "claude": c[i]["overall"], "muse": m.get(i, {}).get("overall")}
            for i in sorted(c) if c[i]["overall"] != m.get(i, {}).get("overall")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    l2 = l2_table()
    c6 = grades("C6", "claude")
    c6_key = json.loads((RES / "blind" / "l1-C6" / "l1-items-key.json").read_text(encoding="utf-8"))["items"]
    c6_pass = [k["tool"] for k in c6_key if c6[k["item_id"]]["overall"] == "pass"]
    rows_a = answer_l1("A", bool(c6_pass), l2)
    rows_b = answer_l1("B", False, l2)

    run1 = {g: by(rows_a, "run1", g) for g in ("control", "experimental", "rules_only")}
    table = []
    for q in QS:
        diff = "easy" if q in EASY else "medium" if q in MEDIUM else "hard"
        row = {"question": q, "difficulty": diff}
        for g in ("control", "experimental", "rules_only"):
            r = run1[g].get(q, {})
            row[g] = {"pick": r.get("pick"), "l1": r.get("l1"), "grader": r.get("grader_verdict"), "item": r.get("item_id"),
                      "note": r.get("note")}
        for g in ("control", "experimental"):
            row[g]["l2"] = l2.get(q, {}).get(g, {}).get("l2")
            row[g]["l2_all_items_run"] = l2.get(q, {}).get(g, {}).get("all_items_run")
        table.append(row)

    ctrl, exp, ro = run1["control"], run1["experimental"], run1["rules_only"]
    d1_wins = [q for q in MAIN if exp[q]["pass"] and not ctrl[q]["pass"]]
    d1_losses = [q for q in MAIN if ctrl[q]["pass"] and not exp[q]["pass"]]
    d1 = {"experimental": count(exp, MAIN), "control": count(ctrl, MAIN), "rules_only": count(ro, MAIN)}
    d1["difference"] = d1["experimental"] - d1["control"]
    d1["met"] = d1["difference"] >= 3
    d2 = {"experimental": count(exp, EASY), "control": count(ctrl, EASY),
          "control_pass_experimental_fail": [q for q in EASY if ctrl[q]["pass"] and not exp[q]["pass"]]}
    d2["met"] = d2["experimental"] >= d2["control"]
    # D3: questions where both groups ran every [L2] item; C6-correct no-fit answers are left out (C7)
    d3_qs = [q for q in QS if l2.get(q, {}).get("control", {}).get("all_items_run")
             and l2.get(q, {}).get("experimental", {}).get("all_items_run")]
    d3 = {"questions": d3_qs, "experimental": sum(1 for q in d3_qs if l2[q]["experimental"]["l2"] == "pass"),
          "control": sum(1 for q in d3_qs if l2[q]["control"]["l2"] == "pass"),
          "not_all_run": [q for q in QS if q not in d3_qs]}
    d3["met"] = None if len(d3_qs) < 6 else d3["experimental"] >= d3["control"]
    d4 = {"experimental": count(exp, ["q10", "q20"]), "control": count(ctrl, ["q10", "q20"])}
    d4["met"] = d4["experimental"] >= d4["control"]
    d5s = {f: json.loads((RES / f).read_text(encoding="utf-8")) for f in ("d5-run1-run2-run3.json", "d5-haiku.json", "d5-bset.json")}
    d5 = {f: {k: d5s[f][k] for k in ("violations", "found", "cannot_check")} for f in d5s}
    d5["met"] = d5s["d5-run1-run2-run3.json"]["violations"] == 0
    d6 = {"rules_only": d1["rules_only"], "experimental": d1["experimental"],
          "rules_only_at_least_experimental": d1["rules_only"] >= d1["experimental"]}

    stability = {}
    for g in ("control", "experimental"):
        per = {}
        for q in QS:
            vs = [by(rows_a, rnd, g).get(q, {}).get("l1") for rnd in ("run1", "run2", "run3")]
            complete = all(v in ("pass", "fail") for v in vs)
            per[q] = {"runs": vs, "passes": sum(v == "pass" for v in vs), "unstable": complete and len(set(vs)) > 1, "complete": complete}
        stability[g] = per
    both_complete = [q for q in QS if stability["control"][q]["complete"] and stability["experimental"][q]["complete"]]
    stab = {"per_question": stability, "both_complete": both_complete,
            "unstable": {g: [q for q in both_complete if stability[g][q]["unstable"]] for g in ("control", "experimental")},
            "main_l1_by_round": {rnd: {g: count(by(rows_a, rnd, g), MAIN) for g in ("control", "experimental")} for rnd in ("run1", "run2", "run3")}}
    haiku = {g: {"main": count(by(rows_a, "haiku", g), MAIN), "all20": count(by(rows_a, "haiku", g), QS)} for g in ("control", "experimental")}
    bqs = sorted({r["question"] for r in rows_b})
    bset = {g: {"l1": count(by(rows_b, "bset", g), bqs), "of": len(bqs),
                "per_question": {q: by(rows_b, "bset", g).get(q, {}).get("l1") for q in bqs}} for g in ("control", "experimental")}
    pref = blind.unblind_prefer(RES / "blind" / "prefer-run1", RES / "blind" / "prefer-run1" / "choices.json")
    unknowns = sorted({(r["question"], r["pick"], r["item_id"]) for r in rows_a + rows_b if r["grader_verdict"] == "unknown"})

    out = {"source": "README 9.4: L1 by the Claude grader (claude-opus-5-5, effort high, blind); unknown = not passed",
           "c6": {"q01_candidates_passing": c6_pass, "no_fit_overturned": bool(c6_pass)},
           "run1_table": table,
           "D1": {**d1, "wins": d1_wins, "losses": d1_losses}, "D2": d2, "D3": d3, "D4": d4, "D5": d5, "D6": d6,
           "all20_l1": {g: count(run1[g], QS) for g in run1},
           "l2_passes": {g: sum(1 for q in QS if l2.get(q, {}).get(g, {}).get("l2") == "pass") for g in ("control", "experimental")},
           "stability": stab, "haiku": haiku, "bset": bset, "preference": pref,
           "grader_unknown_items": [{"question": q, "pick": p, "item": i} for q, p, i in unknowns],
           "claude_vs_muse": {b: disagreements(b) for b in ("A", "B", "C6")}}
    (a.out / "results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (a.out / "answers-l1.json").write_text(json.dumps(rows_a + rows_b, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("written", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
