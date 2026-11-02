"""Compare 念誠's blind ratings with pickfit's usability for the pilot, against the pass criteria committed first
(docs/usability-pilot.md section 3).

Reads data/calibration/ease-ratings.yaml, data/calibration/ease-pilot.json and the results in ~/.pickfit/usability.
Refuses while the ratings are blank, so pickfit's scores are not shown before he has rated.

    uv run python scripts/ease_compare.py            # the four criteria and the side numbers, as JSON
    uv run python scripts/ease_compare.py --per-app  # also each app's pair of answers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pickfit.usability import RESULTS_DIR, WEIGHTS
from scripts.ease_sheet import PILOT, RATINGS, read_ratings

REPO = Path(__file__).resolve().parents[1]
MIN_SHARE = 10 / 12
MIN_COMPARABLE = 5
MIN_SPEARMAN = 0.5
PROBE_MAX = 50.0
VERDICT_ORDER = {"hard": 0, "some_friction": 1, "easy": 2}


def human_verdict(overall: Any) -> str | None:
    if not isinstance(overall, int):
        return None
    return "easy" if overall >= 4 else "some_friction" if overall == 3 else "hard"


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    var = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(cov / var, 3) if var else None


def _raw_items(call: str, answer: dict[str, Any]) -> dict[str, Any]:
    """A sample's raw answers by name: scores (ready, and ease.v1's holistic scores) and r1's check answers."""
    def checks(prefix: str, group: dict[str, Any]) -> dict[str, Any]:
        return {f"{prefix}.{name}": c["ok"] for name, c in group.items()}

    if call == "first_look":
        out = {"ready": answer["ready"]["score"]}
        if "comfortable" in answer:
            out["comfortable"] = answer["comfortable"]["score"]
        else:
            out |= checks("comfortable", answer["comfort"])
        return out
    out = {}
    for op in answer["operations"]:
        for item in ("findable", "responsive"):
            group = op[item]
            if "score" in group:
                out[f"{op['operation']}.{item}"] = group["score"]
            else:
                out |= checks(f"{op['operation']}.{item}", group)
    return out


def self_agreement(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """How often muse-spark-1.3's two samples gave the same raw answer (before pickfit's checks): scores, or r1's
    yes/no checks, where both samples answered."""
    same = within = pairs = 0
    for result in results.values():
        by_call: dict[str, list[dict[str, Any]]] = {}
        for raw in result["raw"]:
            if raw["answer"] is not None:
                by_call.setdefault(raw["call"], []).append(raw["answer"])
        for call, answers in by_call.items():
            if len(answers) < 2:
                continue
            a, b = (_raw_items(call, x) for x in answers[:2])
            for key in a.keys() & b.keys():
                x, y = a[key], b[key]
                if x is None or y is None:
                    continue
                pairs += 1
                same += x == y
                within += abs(int(x) - int(y)) <= 1
    return {"pairs": pairs, "same": round(same / pairs, 3) if pairs else None,
            "within_one": round(within / pairs, 3) if pairs else None}


def compare(per_app: bool = False) -> dict[str, Any]:
    ratings = read_ratings(RATINGS.read_text(encoding="utf-8"))
    pilot = json.loads(PILOT.read_text(encoding="utf-8"))["apps"]
    if not any(isinstance(v.get("overall"), int) for v in ratings["apps"].values()):
        raise SystemExit("the ratings are still blank: rate first (runs/ease-sheet/index.html)")
    results = {a["slug"]: json.loads((RESULTS_DIR / f"{a['slug']}.json").read_text(encoding="utf-8")) for a in pilot}
    dims: dict[str, Any] = {}
    for dim in WEIGHTS:
        pairs = [(slug, r["dimensions"][dim]["score"], ratings["apps"].get(slug, {}).get(dim))
                 for slug, r in results.items()]
        both = [(s, p, h) for s, p, h in pairs if p is not None and isinstance(h, int)]
        agree = sum(abs(p - h) <= 1 for _, p, h in both)
        dims[dim] = {"comparable": len(both), "within_one": agree,
                     "share": round(agree / len(both), 3) if both else None,
                     "passed": len(both) >= MIN_COMPARABLE and agree / len(both) >= MIN_SHARE}
    scored = [(results[s]["score"], ratings["apps"].get(s, {}).get("overall")) for s in results]
    scored = [(p, h) for p, h in scored if p is not None and isinstance(h, int)]
    rho = spearman([p for p, _ in scored], [h for _, h in scored])
    probes = {a["slug"]: results[a["slug"]]["score"] for a in pilot if a["stratum"] == "probe"}
    verdicts = [(s, results[s]["verdict"], human_verdict(ratings["apps"].get(s, {}).get("overall"))) for s in results]
    clash = [s for s, p, h in verdicts if p and h and abs(VERDICT_ORDER[p] - VERDICT_ORDER[h]) == 2]
    popularity = []
    for slug, result in results.items():
        record = json.loads((REPO / "data" / "software" / f"{slug}.json").read_text(encoding="utf-8"))
        pop = ((record.get("scores") or {}).get("popularity") or {}).get("score")
        if pop is not None and result["score"] is not None:
            popularity.append((result["score"], pop))
    out = {
        "criteria": {
            "1_dimensions": dims,
            "2_spearman": {"n": len(scored), "rho": rho, "passed": rho is not None and rho >= MIN_SPEARMAN},
            "3_probes": {"scores": probes, "passed": all(v is not None and v <= PROBE_MAX for v in probes.values())},
            "4_verdicts": {"compared": sum(1 for _, p, h in verdicts if p and h), "two_apart": clash,
                           "passed": not clash},
        },
        "side": {"self_agreement": self_agreement(results),
                 "popularity_rho": spearman([p for p, _ in popularity], [q for _, q in popularity]),
                 "linux_vs_macos": "none of the 12 has a GUI run on both",
                 "cost_usd": round(sum(r["cost_usd"] for r in results.values()), 4)},
    }
    c = out["criteria"]
    out["passed"] = all(d["passed"] for d in c["1_dimensions"].values()) and all(
        c[k]["passed"] for k in ("2_spearman", "3_probes", "4_verdicts"))
    if per_app:
        out["apps"] = {s: {"pickfit": {k: v["score"] for k, v in r["dimensions"].items()} | {
            "score": r["score"], "verdict": r["verdict"]}, "rater": ratings["apps"].get(s)} for s, r in results.items()}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-app", action="store_true")
    args = parser.parse_args()
    print(json.dumps(compare(args.per_app), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
