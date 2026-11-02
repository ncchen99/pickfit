"""Numbered text on a screenshot, for the operator to point at: the host's own Vision framework reads pickfit's
screenshot (ocr_mac.swift, compiled once with the Command Line Tools' swiftc into ~/.pickfit/bin).

The operator names a mark instead of guessing coordinates; pickfit clicks the middle of that text over VNC. On a
Mac the operator's own aim was off by tens of pixels (writer-computer 11/2: every click on "Add Folder" landed
~57 px below it). Nothing runs in the box for it, and the text is the app's: data for the operator, never
instructions. On a host that is not a Mac, or when the tool cannot be built, there are no marks.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SOURCE = Path(__file__).with_name("ocr_mac.swift")
BIN_DIR = Path.home() / ".pickfit" / "bin"
MAX_MARKS = 80
MIN_CONFIDENCE = 0.5
TEXT_MAX = 48  # characters of a mark's text the operator is told
OCR_TIMEOUT_S = 60  # the first run loads Vision's text model (measured ~28 s once, then ~0.15 s)


@dataclass(frozen=True)
class Mark:
    number: int
    text: str
    x: int  # the text's box on the screen, in pixels
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


def ocr_tool() -> Path | None:
    """The compiled text finder (built once per source version), or None where it cannot run."""
    if sys.platform != "darwin" or not SOURCE.exists():
        return None
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:12]
    tool = BIN_DIR / f"pickfit-ocr-{digest}"
    if tool.exists():
        return tool
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        built = subprocess.run(["/usr/bin/swiftc", "-O", "-o", str(tool), str(SOURCE)], capture_output=True,
                               timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return tool if built.returncode == 0 and tool.exists() else None


def parse(raw: str, *, limit: int = MAX_MARKS) -> list[Mark]:
    """The tool's JSON as numbered marks, top to bottom then left to right; odd entries are dropped."""
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    found: list[tuple[int, int, str, int, int]] = []
    for item in items if isinstance(items, list) else []:
        try:
            text = " ".join(str(item["text"]).split())[:TEXT_MAX]
            x, y, w, h = (int(item[k]) for k in ("x", "y", "w", "h"))
            conf = float(item.get("conf", 1))
        except (KeyError, TypeError, ValueError):
            continue
        if text and conf >= MIN_CONFIDENCE and w > 0 and h > 0:
            found.append((y, x, text, w, h))
    found.sort(key=lambda f: (round(f[0] / 8), f[1]))  # rows of about one line, then left to right
    return [Mark(i, text, x, y, w, h) for i, (y, x, text, w, h) in enumerate(found[:limit], start=1)]


def text_marks(png: bytes, tool: Path | None = None) -> list[Mark]:
    """The text pickfit finds on a screenshot, numbered; [] when there is no tool or it fails."""
    tool = tool or ocr_tool()
    if tool is None:
        return []
    with tempfile.NamedTemporaryFile(suffix=".png") as fh:
        fh.write(png)
        fh.flush()
        try:
            done = subprocess.run([str(tool), fh.name], capture_output=True, text=True, timeout=OCR_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired):
            return []
    return parse(done.stdout) if done.returncode == 0 else []


def draw(view_png: bytes, marks: list[Mark], view: Any) -> bytes:
    """The operator's view with a numbered tag at each mark's top left (view: gui_operate.View, crop and zoom)."""
    from PIL import Image, ImageDraw

    image = Image.open(io.BytesIO(view_png)).convert("RGB")
    pen = ImageDraw.Draw(image)
    for mark in marks:
        x = round((mark.x - view.x) * view.zoom)
        y = round((mark.y - view.y) * view.zoom)
        if not (0 <= x < image.width and 0 <= y < image.height):
            continue
        label = str(mark.number)
        left, top = max(0, x - 2), max(0, y - 11)
        pen.rectangle((left, top, left + 7 * len(label) + 4, top + 11), fill=(200, 0, 160))
        pen.text((left + 2, top), label, fill=(255, 255, 255))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def listing(marks: list[Mark]) -> str:
    """The marks as one line each for the operator's turn (the text is the app's)."""
    return "\n".join(f"{m.number}: {json.dumps(m.text, ensure_ascii=False)}" for m in marks)
