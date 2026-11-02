"""Probe: can Meta's SAM 3.1 locate GUI controls on pickfit's saved screenshots? Measure only.

Reads docs/research/notes/sam-3-1-gui-probe-targets.json (one row per screenshot: the noun phrase, written
before any SAM call, and the true target point), sends each screenshot once to SAM 3.1 through Meta's
Responses API as a base64 data URL, and records per row: the boxes returned, whether the target point lies
inside one (and inside the most confident one), latency and cost. Every call is held and settled in the
shared ledger's Meta budget (stage probe-sam-3.1), so the pipeline caps apply; the probe stops at MAX_USD.

    uv run python scripts/probe_sam_gui.py [--limit N] [--out results.json]

The API key comes from .env (MODEL_API_KEY) and is never printed.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import time
from pathlib import Path

import httpx2 as httpx

from pickfit.env import REPO_ROOT, require_env
from pickfit.ledger import default_ledger

URL = "https://api.meta.ai/v1/responses"
MODEL = "sam-3.1"
STAGE = "probe-sam-3.1"
USD_PER_IMAGE = 2.50 / 1000
MAX_USD = 0.10
TARGETS = REPO_ROOT / "docs" / "research" / "notes" / "sam-3-1-gui-probe-targets.json"
BOX = re.compile(r"<\|box;x1=(-?\d+);y1=(-?\d+);x2=(-?\d+);y2=(-?\d+);w=(\d+);h=(\d+)(?:;c=([0-9.]+))?\|>")


def call_sam(client: httpx.Client, key: str, phrase: str, png: bytes) -> tuple[str, float, int]:
    """(the streamed output text, seconds, HTTP status). Raises on a refused request."""
    body = {"model": MODEL, "stream": True, "metadata": {"mask_encoding": "one_bit"},
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": phrase},
                {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode()}]}]}
    began = time.monotonic()
    text: list[str] = []
    with client.stream("POST", URL, json=body, headers={"Authorization": f"Bearer {key}",
                                                        "Accept": "text/event-stream"}, timeout=120) as resp:
        if resp.status_code != 200:
            detail = resp.read().decode("utf-8", "replace")[:400]
            raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            event = json.loads(payload)
            if event.get("type") == "response.output_text.delta":
                text.append(event.get("delta") or "")
    return "".join(text), round(time.monotonic() - began, 2), 200


def boxes_of(text: str) -> list[dict]:
    return [{"box": [int(m[1]), int(m[2]), int(m[3]), int(m[4])], "frame": [int(m[5]), int(m[6])],
             "conf": float(m[7]) if m[7] else None} for m in BOX.finditer(text)]


def inside(point: list[float], box: list[int]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="sam-3-1-gui-probe-results.json")
    args = ap.parse_args()
    key = require_env("MODEL_API_KEY")
    rows = json.loads(TARGETS.read_text())[: args.limit]
    ledger = default_ledger()
    run_id = f"{STAGE}-{time.strftime('%Y%m%d-%H%M%S')}"
    spent, results = 0.0, []
    with httpx.Client() as client:
        for row in rows:
            if spent + USD_PER_IMAGE > MAX_USD:
                print("stopped: the probe's $%.2f limit" % MAX_USD)
                break
            png = Path(row["screenshot"]).expanduser().read_bytes()
            hold = ledger.reserve(USD_PER_IMAGE, run_id=run_id, stage=STAGE, scope=STAGE, provider="meta", model=MODEL)
            try:
                text, seconds, _ = call_sam(client, key, row["phrase"], png)
            except Exception as err:
                ledger.release(hold, status="error")
                print(f"#{row['id']} {row['phrase']!r}: {type(err).__name__}: {str(err)[:300]}")
                return 2
            ledger.settle(hold, USD_PER_IMAGE)
            spent += USD_PER_IMAGE
            found = boxes_of(text)
            best = max(found, key=lambda b: b["conf"] or 0.0) if found else None
            hit = any(inside(row["target"], b["box"]) for b in found)
            top = bool(best and inside(row["target"], best["box"]))
            results.append({**row, "boxes": found, "hit": hit, "top_hit": top, "seconds": seconds,
                            "chars": len(text)})
            print(f"#{row['id']:3} {row['kind']:4} {row['phrase']:24} boxes {len(found):2} hit {hit!s:5} top {top!s:5} "
                  f"{seconds:5.1f}s")
    Path(args.out).write_text(json.dumps({"run_id": run_id, "cost_usd": round(spent, 4), "results": results},
                                         indent=1) + "\n")
    for kind in ("icon", "text"):
        part = [r for r in results if r["kind"] == kind]
        if part:
            print(f"{kind}: {sum(r['hit'] for r in part)}/{len(part)} hit, {sum(r['top_hit'] for r in part)}/{len(part)} "
                  f"top, boxes median {sorted(len(r['boxes']) for r in part)[len(part) // 2]}, "
                  f"latency median {sorted(r['seconds'] for r in part)[len(part) // 2]}s")
    print(f"cost ${spent:.4f} for {len(results)} calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
