"""The calibration check of the visual-quality scores (comfort.v1) before deployment: docs/usability-pilot.md section 11.

`controls` draws the apps the independent reviewers read, by a fixed rule committed before anyone looks: usdx and
capitolisation (where the model and 念誠 disagreed) plus, for desktop and web apps each, 3 with no defect (score 2)
and 3 with a major one (score 0), the lowest sha256("<SEED>:<slug>") in each group. `packets` writes, for each app,
the screenshots the model read with its defects' boxes drawn in, and a JSON packet of the defects; no score, verdict
or note of what anyone expects goes in. The other commands are the analyses of section 11, computed in memory: they
never write a record.

    uv run python scripts/visual_review.py controls   # writes data/calibration/visual-review-controls.json
    uv run python scripts/visual_review.py packets OUT_DIR
    uv run python scripts/visual_review.py analyses   # consistency, unassessed apps, weight variants (JSON)
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data" / "software"
CONTROLS = REPO / "data" / "calibration" / "visual-review-controls.json"
SEED = "pickfit-visual-review-2026-11-03"
DISPUTED = ("usdx", "capitolisation")
GROUPS = (("desktop_app", 2), ("web_app", 2), ("desktop_app", 0), ("web_app", 0))
PER_GROUP = 3


def rank(slug: str) -> str:
    return hashlib.sha256(f"{SEED}:{slug}".encode()).hexdigest()


def checked_records() -> dict[str, dict[str, Any]]:
    out = {}
    for path in sorted(DATA.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("visual_check"):
            out[path.stem] = record
    return out


def draw_controls(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    apps = [{"slug": s, "group": "disputed"} for s in DISPUTED]
    for kind, score in GROUPS:
        pool = sorted((s for s, r in records.items() if s not in DISPUTED and r["kind"] == kind
                       and r["visual_check"]["score"] == score), key=rank)
        name = f"{'desktop' if kind == 'desktop_app' else 'web'}_{'clean' if score == 2 else 'major'}"
        apps += [{"slug": s, "group": name} for s in pool[:PER_GROUP]]
    return {"seed": SEED, "rule": "sha256('<seed>:<slug>'), lowest first, per group (scripts/visual_review.py)",
            "apps": apps}


def packets(out_dir: Path) -> None:
    """For each control app: its first-look screenshots with every listed defect's box drawn and numbered, the clean
    screenshots, and packet.json with the defects (no score)."""
    from PIL import Image, ImageDraw

    from pickfit.usability import bundle_for, first_look_text

    controls = json.loads(CONTROLS.read_text(encoding="utf-8"))["apps"]
    for app in controls:
        record = json.loads((DATA / f"{app['slug']}.json").read_text(encoding="utf-8"))
        bundle = bundle_for(record)
        folder = out_dir / app["slug"]
        folder.mkdir(parents=True, exist_ok=True)
        shots = bundle.first_look_shots()
        defects = record["visual_check"]["defects"]
        images = []
        for i, shot in enumerate(shots, start=1):
            clean = folder / f"image-{i}.png"
            boxed = folder / f"image-{i}-boxes.png"
            with Image.open(shot.path) as image:
                image = image.convert("RGB")
                image.save(clean)
                pen = ImageDraw.Draw(image)
                for n, d in enumerate(defects, start=1):
                    if d["screenshot"] != shot.path.name:
                        continue
                    x0, y0, x1, y1 = (round(v / 1000 * size) for v, size in
                                      zip(d["box"], (image.width, image.height, image.width, image.height)))
                    pen.rectangle((x0, y0, x1, y1), outline=(230, 0, 120), width=3)
                    pen.rectangle((x0, max(0, y0 - 16), x0 + 22, max(16, y0)), fill=(230, 0, 120))
                    pen.text((x0 + 4, max(0, y0 - 15)), str(n), fill=(255, 255, 255))
                image.save(boxed)
            images.append({"image": i, "what": shot.label, "file": clean.name, "with_boxes": boxed.name})
        packet = {"slug": app["slug"], "kind": record["kind"], "summary": record.get("summary"),
                  "sandbox": bundle.sandbox, "images": images, "context": first_look_text(bundle),
                  "defects": [{"number": n, "image": next((im["image"] for im in images
                                                           if shots[im["image"] - 1].path.name == d["screenshot"]), None),
                               "kind": d["kind"], "severity": d["severity"], "cause": d["cause"],
                               "problem": d["problem"], "quote": d["quote"], "box": d["box"],
                               "quote_found_by": d["found_by"]} for n, d in enumerate(defects, start=1)]}
        (folder / "packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --- the analyses of section 11 (in memory; no record is written) ------------------------------------------------


def _without_visual(record: dict[str, Any], now: Any) -> dict[str, Any]:
    """The record as main has it: no visual_check, scores refreshed back to b3.v5 or web.v1."""
    import copy

    from pickfit.score import refresh_scores

    out = copy.deepcopy(record)
    out.pop("visual_check", None)
    refresh_scores(out, now)
    return out


def _treasure(total: float | None, popularity: float | None) -> bool:
    from pickfit.schema import TREASURE_MAX_POPULARITY, TREASURE_MIN_QUALITY

    return total is not None and popularity is not None and total >= TREASURE_MIN_QUALITY and \
        popularity <= TREASURE_MAX_POPULARITY


def variant_totals(name: str, records: dict[str, dict[str, Any]], now: Any) -> dict[str, tuple[float | None, bool]]:
    """(quality, treasure) per checked record: current (what refresh_scores gives: an app-caused defect takes 5% off the
    old formula's total), or deduct10 (major -10%, minor -5%, in memory). The additive 15% and 10% versions of section 11
    were computed with the code of commit 14251615."""
    import copy

    from pickfit import score as s

    out = {}
    for slug, record in records.items():
        pop = record["scores"]["popularity"]["score"]
        if name == "current":
            data = copy.deepcopy(record)
            s.refresh_scores(data, now)
            total = data["scores"]["quality"]["total"]
        else:
            old = _without_visual(record, now)["scores"]["quality"]["total"]
            v = record["visual_check"]["score"]
            total = None if old is None else (old if v in (2, None) else round(old * (0.95 if v == 1 else 0.90), 1))
        out[slug] = (total, _treasure(total, pop))
    return out


def all_records() -> dict[str, dict[str, Any]]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(DATA.glob("*.json"))}


def consistency() -> dict[str, Any]:
    """Desktop against web: defects per app, kinds and severity, how quotes were verified, and how much each
    screenshot shows (OCR lines, DOM text)."""
    import collections
    import statistics

    from pickfit.usability import TextFinder, bundle_for

    finder = TextFinder()
    out: dict[str, Any] = {}
    for kind in ("desktop_app", "web_app"):
        recs = [r for r in checked_records().values() if r["kind"] == kind]
        app = [[d for d in r["visual_check"]["defects"] if d["cause"] == "app"] for r in recs]
        kinds = collections.Counter(d["kind"] for ds in app for d in ds)
        major = collections.Counter(d["kind"] for ds in app for d in ds if d["severity"] == "major")
        found = collections.Counter(d["found_by"] for ds in app for d in ds)
        lines, chars = [], []
        for r in recs:
            bundle = bundle_for(r)
            for shot in bundle.first_look_shots():
                ocr = finder.lines(shot)
                lines.append(len(ocr))
                chars.append(sum(len(line.text) for line in ocr))
        scores = collections.Counter(r["visual_check"]["score"] for r in recs)
        out[kind] = {
            "apps": len(recs), "scores": dict(scores),
            "defects_per_app": round(sum(map(len, app)) / len(recs), 2),
            "apps_with_a_defect": round(sum(1 for ds in app if ds) / len(recs), 2),
            "kinds": dict(kinds.most_common()), "major_share_by_kind": {
                k: round(major[k] / n, 2) for k, n in kinds.most_common()},
            "major_share": round(sum(major.values()) / max(1, sum(kinds.values())), 2),
            "quote_found_by": dict(found), "screens_per_app": round(len(lines) / len(recs), 2),
            "ocr_lines_per_screen_median": statistics.median(lines), "ocr_chars_per_screen_median": statistics.median(chars),
            "defects_per_100_ocr_lines": round(100 * sum(map(len, app)) / max(1, sum(lines)), 2),
        }
    return out


def unassessed(now: Any) -> dict[str, Any]:
    """Apps without a visual check: their formula, and how far they move in the treasure-value order (the Worker's
    tie-break and filler) against all desktop and web apps, current against main."""
    import statistics

    records = all_records()
    gui_web = {s: r for s, r in records.items() if r["kind"] in ("desktop_app", "web_app") and r.get("scores")}
    unchecked = {s: r for s, r in gui_web.items() if not r.get("visual_check")}
    formulas = {r["scores"]["formula_version"] for r in unchecked.values()}

    def value(total: float | None, pop: float | None) -> float:
        return -1.0 if total is None or pop is None else total * (1 - pop / 100)

    def order(values: dict[str, float]) -> dict[str, int]:
        return {s: i for i, s in enumerate(sorted(values, key=lambda s: (-values[s], s)))}

    result: dict[str, Any] = {"unchecked": len(unchecked), "their_formulas": sorted(formulas),
                              "unchecked_with_visual_fields": sum(1 for r in unchecked.values()
                                                                   if "visual" in r["scores"]["quality"])}
    main_values = {}
    for s, r in gui_web.items():
        old = _without_visual(r, now)["scores"] if r.get("visual_check") else r["scores"]
        main_values[s] = value(old["quality"]["total"], old["popularity"]["score"])
    main_rank = order(main_values)
    checked = {s: r for s, r in gui_web.items() if r.get("visual_check")}
    for name in ("current", "deduct10"):
        totals = variant_totals(name, checked, now)
        values = dict(main_values) | {s: value(t, gui_web[s]["scores"]["popularity"]["score"]) for s, (t, _) in totals.items()}
        rank = order(values)
        falls = [rank[s] - main_rank[s] for s in unchecked]
        result[name] = {"unchecked_that_fall": sum(1 for f in falls if f > 0),
                        "median_fall": statistics.median([f for f in falls if f > 0] or [0]),
                        "max_fall": max(falls), "unchecked_treasures_lost": 0}
    return result


def variants(now: Any) -> dict[str, Any]:
    """Each variant against main, over the checked apps: quality median and mean change, desktop and web, and the
    treasures lost and gained."""
    import statistics

    checked = checked_records()
    main = {s: _without_visual(r, now)["scores"] for s, r in checked.items()}
    out = {}
    for name in ("current", "deduct10"):
        totals = variant_totals(name, checked, now)
        row: dict[str, Any] = {}
        for kind in ("desktop_app", "web_app", None):
            slugs = [s for s, r in checked.items() if kind is None or r["kind"] == kind]
            d = [totals[s][0] - main[s]["quality"]["total"] for s in slugs
                 if totals[s][0] is not None and main[s]["quality"]["total"] is not None]
            row[kind or "all"] = {"n": len(d), "median": round(statistics.median(d), 1), "mean": round(statistics.mean(d), 1),
                                  "min": round(min(d), 1), "max": round(max(d), 1)}
        row["treasures_lost"] = sorted(s for s in checked if main[s]["treasure"]["is_treasure"] and not totals[s][1])
        row["treasures_gained"] = sorted(s for s in checked if totals[s][1] and not main[s]["treasure"]["is_treasure"])
        row["moved_over_5"] = sorted((s, main[s]["quality"]["total"], totals[s][0]) for s in checked
                                     if totals[s][0] is not None and main[s]["quality"]["total"] is not None
                                     and abs(totals[s][0] - main[s]["quality"]["total"]) > 5)
        out[name] = row
    return out


def analyses() -> dict[str, Any]:
    from pickfit.ledger import taipei_now

    now = taipei_now()
    return {"consistency": consistency(), "unassessed": unassessed(now), "variants": variants(now)}


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "controls":
        out = draw_controls(checked_records())
        CONTROLS.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif command == "packets":
        packets(Path(sys.argv[2]))
    elif command == "analyses":
        print(json.dumps(analyses(), ensure_ascii=False, indent=2))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
