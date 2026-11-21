"""Probe for H-006: operations that need a drag, in fresh Modal boxes with pickfit's display, with no model.

Chromium shows a page pickfit writes into ~/pickfit-in/, in two kinds:
  dnd     an orange card and a dashed blue box; dropping the card in the box (HTML drag and drop, which Chromium
          starts only on pointer motion after the press, through X11's drag protocol) makes the page download a file;
  slider  an orange handle on a track; pulling it to the blue mark at the track's end (pointer events) does the same.
The file holds the operation's nonce and nothing else writes it. The check is pickfit's own: once every box-user
process has stopped, root finds that file under ~/Downloads/, written after the app started.

Box 1, per page: a look (one screenshot) to find the orange and the blue by colour; a click on the orange where
the drag would start, which must not pass; the drag from the orange to the blue, which must pass. Box 2, fresh:
each drag that passed, replayed from its recording with a fresh nonce. --operator also lets the operator model
choose the actions from the goal first (Muse Spark Open; its Baseten deployment was off on 2026-11-16).

Usage: uv run python scripts/probe_gui_drag.py [--out runs/probe-gui-drag] [--operator]
Prints one line per operation; writes summary.json, each operation's record and every screenshot under
--out/<stamp>/.
"""

from __future__ import annotations

import argparse
import io
import json
import time
from pathlib import Path
from typing import Any

from pickfit.env import REPO_ROOT
from pickfit.ledger import taipei_now
from pickfit.verify import gui_operate as op
from pickfit.verify.box import BoxLimits
from pickfit.verify.modal_box import ModalBox

ORANGE, BLUE = (232, 121, 43), (43, 107, 232)

STYLE = "body{margin:0;font:22px sans-serif;background:#f4f1ea;color:#222}#note{position:absolute;left:120px;top:600px}"
SAVE = """function save() {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["dropped " + WORD + "\\n"], {type: "text/plain"}));
  a.download = "dropped.txt"; document.body.appendChild(a); a.click(); note.textContent = "done";
}
const WORD = "{nonce}".split("").join(""), note = document.getElementById("note");"""

PAGES = {
    "dnd": """<!doctype html><html><head><meta charset="utf-8"><title>drag and drop</title><style>STYLE
#card{position:absolute;left:120px;top:220px;width:220px;height:140px;background:#e8792b;color:#fff;
display:flex;align-items:center;justify-content:center;border-radius:12px;user-select:none}
#box{position:absolute;left:740px;top:150px;width:380px;height:300px;border:8px dashed #2b6be8;
display:flex;align-items:center;justify-content:center;color:#2b6be8}
</style></head><body><div id="card" draggable="true">card</div><div id="box">drop here</div>
<div id="note">waiting</div><script>SAVE
const card = document.getElementById("card"), box = document.getElementById("box");
card.addEventListener("dragstart", e => { e.dataTransfer.setData("text/plain", "card"); note.textContent = "dragging"; });
box.addEventListener("dragover", e => e.preventDefault());
box.addEventListener("drop", e => { e.preventDefault(); box.textContent = ""; card.style.position = "static";
  box.appendChild(card); save(); });
</script></body></html>""",
    "slider": """<!doctype html><html><head><meta charset="utf-8"><title>slider</title><style>STYLE
#track{position:absolute;left:200px;top:390px;width:800px;height:20px;background:#ccc;border-radius:10px}
#end{position:absolute;left:990px;top:370px;width:60px;height:60px;background:#2b6be8;border-radius:30px}
#handle{position:absolute;left:170px;top:360px;width:80px;height:80px;background:#e8792b;border-radius:40px;
touch-action:none}
</style></head><body><div id="track"></div><div id="end"></div><div id="handle"></div>
<div id="note">waiting</div><script>SAVE
const handle = document.getElementById("handle");
let held = false, start = 0, left = 170;
handle.addEventListener("pointerdown", e => { held = true; start = e.clientX - left; handle.setPointerCapture(e.pointerId); });
handle.addEventListener("pointermove", e => { if (!held) return;
  left = Math.max(170, Math.min(980, e.clientX - start)); handle.style.left = left + "px"; note.textContent = "at " + left; });
handle.addEventListener("pointerup", e => { held = false; if (left >= 950) save(); });
</script></body></html>""",
}

# A fresh profile per start: a profile lock left by the previous operation's stopped Chromium cannot get in the way.
COMMAND = ("mkdir -p ~/Downloads && chromium --user-data-dir=\"$(mktemp -d)\" --no-sandbox --no-first-run "
           "--no-default-browser-check --disable-gpu --password-store=basic --window-position=0,0 "
           "--window-size=1280,800 --app=file:///home/sbx/pickfit-in/{page}.html")
GOALS = {"dnd": "Drag the orange card into the dashed blue box on the right and release it inside the box.",
         "slider": "Drag the orange handle along the track to the blue circle at its right end and release it there."}


def args(page: str) -> op.OperateArgs:
    text = PAGES[page].replace("STYLE", STYLE).replace("SAVE", SAVE)
    return op.OperateArgs.model_validate({
        "command": COMMAND.format(page=page), "wait_s": 40, "feature": 1, "goal": GOALS[page] + " Then say done.",
        "inputs": [{"path": f"~/pickfit-in/{page}.html", "text": text}],
        "check": {"kind": "file", "path": "~/Downloads/", "contains": ["dropped {nonce}"], "format": "text"}})


def middle(png: bytes, rgb: tuple[int, int, int]) -> tuple[int, int] | None:
    """The centre of the pixels of one colour (within 12 per channel) on a screenshot."""
    from PIL import Image

    image = Image.open(io.BytesIO(png)).convert("RGB")
    mask = Image.new("L", image.size)
    mask.putdata([255 if all(abs(a - b) <= 12 for a, b in zip(p, rgb)) else 0 for p in image.getdata()])
    box = mask.getbbox()
    return ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2) if box else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "runs" / "probe-gui-drag")
    ap.add_argument("--operator", action="store_true", help="let the operator model try each goal first")
    a = ap.parse_args(argv)
    stamp = taipei_now().strftime("%Y%m%d-%H%M%S")
    out = a.out / stamp
    out.mkdir(parents=True, exist_ok=True)
    run_id = f"probe-gui-drag-{stamp}"
    summary: dict[str, Any] = {"run_id": run_id, "operations": [], "boxes": []}

    def one(box: ModalBox, page: str, tag: str, actions: list[dict[str, Any]] | None) -> op.Operation:
        began = time.monotonic()
        result, operation, _ = op.run_operation(box, args(page), tag, actions=actions, evidence_dir=out,
                                                run_id=run_id, log=lambda s: print(s, flush=True))
        row = {"tag": tag, "page": page, "passed": operation.passed, "mode": operation.mode, "stop": operation.stop,
               "actions": operation.actions(), "line": operation.result.get("line"), "error": operation.error,
               "cost_usd": operation.cost_usd, "seconds": round(time.monotonic() - began, 1)}
        summary["operations"].append(row)
        print(f"{tag}: {'PASSED' if operation.passed else 'not passed'} · {row['line']} · {row['seconds']}s",
              flush=True)
        (out / f"{tag}.json").write_text(json.dumps({"stdout": result.stdout, "stderr": result.stderr,
                                                     "operation": operation.to_dict()}, indent=1, default=str))
        return operation

    def boxed(name: str, work: Any) -> Any:
        box = ModalBox(limits=BoxLimits(lifetime_s=1800), display=True, tags={"pickfit": "probe-gui-drag"},
                       log=lambda s: None)
        began = time.monotonic()
        try:
            box.start()
            return work(box)
        finally:
            box.close()
            alive = time.monotonic() - began
            summary["boxes"].append({"box": name, "alive_s": round(alive, 1),
                                     "usd": round(alive * box.usd_per_second(), 5)})

    def first(box: ModalBox) -> dict[str, list[dict[str, Any]]]:
        passed: dict[str, list[dict[str, Any]]] = {}
        for page in PAGES:
            if a.operator:
                operated = one(box, page, f"{page}-operated", None)
                if operated.passed and any(x["kind"] == "drag" for x in operated.actions()):
                    passed[page] = operated.actions()
            look = one(box, page, f"{page}-look", [{"kind": "wait", "seconds": 1}])
            shot = next((s.screenshot for s in look.steps if s.screenshot), None)
            png = Path(shot).read_bytes() if shot else b""
            grab, goal = (middle(png, ORANGE), middle(png, BLUE)) if png else (None, None)
            print(f"{page}: orange at {grab}, blue at {goal}", flush=True)
            if not grab or not goal:
                continue
            one(box, page, f"{page}-click-only", [{"kind": "click", "x": grab[0], "y": grab[1], "count": 1}])
            dragged = one(box, page, f"{page}-drag", [{"kind": "drag", "x": grab[0], "y": grab[1], "to_x": goal[0],
                                                       "to_y": goal[1]}])
            if dragged.passed and page not in passed:
                passed[page] = dragged.actions()
        return passed

    recorded = boxed("first", first)
    if recorded:
        boxed("fresh", lambda box: [one(box, page, f"{page}-replayed", actions) for page, actions in recorded.items()])
    summary["box_usd"] = round(sum(b["usd"] for b in summary["boxes"]), 5)
    summary["model_usd"] = round(sum(o["cost_usd"] for o in summary["operations"]), 5)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "operations"}, indent=1))
    rows = {o["tag"]: o["passed"] for o in summary["operations"]}
    controls_fail = not any(v for t, v in rows.items() if t.endswith("-click-only"))
    replays_pass = any(v for t, v in rows.items() if t.endswith("-replayed"))
    return 0 if controls_fail and replays_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
