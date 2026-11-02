"""Draw the 12 apps for the usability (ease.v1) pilot, by a seeded sha256 over slugs (usability proposal section 5).

The draw reads only the records in data/software and the run folders copied to ~/.pickfit/evidence; no model output.
Within each stratum the apps are ranked by sha256("<SEED>:<slug>") and the lowest ones are taken; strata are drawn in
the order below and an app is drawn once.

1. gui_video (4, named in the proposal): concessio, nip4, breaktimer-app, neon-vision-editor.
2. probe (2), "looks clean but is hard to use": a GUI app with a run whose screen is main_ui, that has an operation
   which passed pickfit's check (so the in-use call has something to read) and an operation in the same run's
   report.json that stopped at the step cap or gave up without passing.
3. gui_launch_linux (1), gui_launch_macos (1): a GUI app none of whose GUI runs has a passed operation, with a GUI
   run on that OS.
4. web_operated (3): a web app with a run at level function.
5. web_install (1): a web app with a passed run and none at level function.

Writes data/calibration/ease-pilot.json (the draw and the pool sizes).

    uv run python scripts/ease_pilot.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = Path.home() / ".pickfit" / "evidence"
OUT = REPO / "data" / "calibration" / "ease-pilot.json"
SEED = "pickfit-ease.v1-pilot-2026-11-02"
GUI_VIDEO = ("concessio", "nip4", "breaktimer-app", "neon-vision-editor")
STRATA = (("probe", 2), ("gui_launch_linux", 1), ("gui_launch_macos", 1), ("web_operated", 3), ("web_install", 1))
STUCK = ("step_cap", "give_up")


def rank(slug: str) -> str:
    return hashlib.sha256(f"{SEED}:{slug}".encode()).hexdigest()


def _stuck(run_id: str) -> int:
    report = json.loads((EVIDENCE / run_id / "report.json").read_text(encoding="utf-8"))
    return sum(1 for c in report["commands"] if (op := c.get("operate"))
               and op.get("stop") in STUCK and not op.get("passed"))


def pools(data_dir: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {name: [] for name, _ in STRATA}
    for path in sorted(data_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        slug = record["slug"]
        gui = [r for r in record["verification"]["runs"] if r.get("gui")]
        web = [r for r in record["verification"]["runs"] if r.get("web")]
        if gui:
            def passed_ops(run: dict) -> int:
                return sum(op["passed"] for op in run["gui"].get("operations", []))
            if any(r["gui"]["screen"] == "main_ui" and passed_ops(r) and _stuck(r["id"]) for r in gui):
                out["probe"].append(slug)
            if not any(passed_ops(r) for r in gui):
                for os_ in ("linux", "macos"):
                    if any(r["os"] == os_ for r in gui):
                        out[f"gui_launch_{os_}"].append(slug)
        if web:
            levels = {r["level"] for r in web}
            if "function" in levels:
                out["web_operated"].append(slug)
            elif "install" in levels:
                out["web_install"].append(slug)
    return out


def draw(data_dir: Path) -> dict:
    chosen: list[dict] = [{"slug": s, "stratum": "gui_video"} for s in GUI_VIDEO]
    taken = set(GUI_VIDEO)
    pool = pools(data_dir)
    for name, n in STRATA:
        for slug in sorted((s for s in pool[name] if s not in taken), key=rank)[:n]:
            chosen.append({"slug": slug, "stratum": name})
            taken.add(slug)
    return {"seed": SEED, "rule": "sha256('<seed>:<slug>'), lowest first, strata in order (scripts/ease_pilot.py)",
            "pool_sizes": {name: len(v) for name, v in pool.items()}, "apps": chosen}


def main() -> None:
    out = draw(REPO / "data" / "software")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
