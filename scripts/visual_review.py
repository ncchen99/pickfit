"""The calibration check of the visual-quality scores (comfort.v1) before deployment: docs/usability-pilot.md section 11.

`controls` draws the apps the independent reviewers read, by a fixed rule committed before anyone looks: usdx and
capitolisation (where the model and 念誠 disagreed) plus, for desktop and web apps each, 3 with no defect (score 2)
and 3 with a major one (score 0), the lowest sha256("<SEED>:<slug>") in each group. `packets` writes, for each app,
the screenshots the model read with its defects' boxes drawn in, and a JSON packet of the defects; no score, verdict
or note of what anyone expects goes in. The other commands are the analyses of section 11, computed in memory: they
never write a record.

    uv run python scripts/visual_review.py controls   # writes data/calibration/visual-review-controls.json
    uv run python scripts/visual_review.py packets OUT_DIR
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


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "controls":
        out = draw_controls(checked_records())
        CONTROLS.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif command == "packets":
        packets(Path(sys.argv[2]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
