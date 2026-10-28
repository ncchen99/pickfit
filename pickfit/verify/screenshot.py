"""Redraw captured terminal output as a PNG for the screen judge (P3.4).

This is not a screen capture: it draws the command and the output pickfit
recorded on a fixed character grid, with ANSI colors, and says so in the
title bar. The fixed grid lets the program map the judge's 0-1000 evidence
boxes back to the exact text under them, and draw them on a copy.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COLS = 100
MAX_ROWS = 46
HEAD_ROWS = 10  # rows kept from the top when the middle is cut
FONT_SIZE = 15
PAD = 14
TITLE_H = 30
PROMPT = "sbx@box:~/work$ "

BG = (13, 17, 23)
FG = (201, 209, 217)
TITLE_BG = (33, 38, 45)
TITLE_FG = (139, 148, 158)
PROMPT_FG = (63, 185, 80)
DIM = (110, 118, 129)
MARK = (255, 166, 0)

# xterm's 16 colors: normal then bright.
PALETTE = [(1, 1, 1), (222, 56, 43), (57, 181, 74), (255, 199, 6), (0, 111, 184), (118, 38, 113),
           (44, 181, 233), (204, 204, 204), (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
           (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255)]

MONO_FONTS = ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/SFNSMono.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "/usr/share/fonts/TTF/DejaVuSansMono.ttf", "/usr/share/fonts/dejavu/DejaVuSansMono.ttf")
WIDE_FONTS = ("/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Light.ttc",
              "/System/Library/Fonts/PingFang.ttc",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc")

_SGR = re.compile(r"\x1b\[([0-9;]*)m")
_OTHER_ESCAPES = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-ln-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")

Color = tuple[int, int, int]


@lru_cache(maxsize=4)
def _font(paths: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def _wide(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")


@dataclass
class Cell:
    ch: str
    fg: Color
    bold: bool = False
    wide: bool = False


def _color_256(n: int) -> Color:
    if n < 16:
        return PALETTE[n]
    if n < 232:
        n -= 16
        steps = [0, 95, 135, 175, 215, 255]
        return steps[n // 36], steps[(n // 6) % 6], steps[n % 6]
    level = 8 + (n - 232) * 10
    return level, level, level


def parse_ansi(text: str, default: Color = FG) -> list[list[Cell]]:
    """Text with SGR colors -> logical lines of cells (other escapes dropped, \\r handled)."""
    text = _OTHER_ESCAPES.sub("", text.replace("\r\n", "\n").replace("\t", "    "))
    lines: list[list[Cell]] = [[]]
    fg, bold = default, False
    pos = 0
    for m in [*_SGR.finditer(text), None]:
        chunk = text[pos:m.start()] if m else text[pos:]
        for ch in chunk:
            if ch == "\n":
                lines.append([])
            elif ch == "\r":
                lines[-1] = []  # a progress bar redraws its line: keep the last state
            elif ch.isprintable():
                lines[-1].append(Cell(ch, fg, bold, _wide(ch)))
        if m is None:
            break
        pos = m.end()
        codes = [int(c) if c else 0 for c in m.group(1).split(";")]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                fg, bold = default, False
            elif c == 1:
                bold = True
            elif c == 22:
                bold = False
            elif 30 <= c <= 37:
                fg = PALETTE[c - 30 + (8 if bold else 0)]
            elif 90 <= c <= 97:
                fg = PALETTE[c - 90 + 8]
            elif c == 39:
                fg = default
            elif c == 38 and i + 2 < len(codes) and codes[i + 1] == 5:
                fg = _color_256(codes[i + 2])
                i += 2
            elif c == 38 and i + 4 < len(codes) and codes[i + 1] == 2:
                fg = (codes[i + 2], codes[i + 3], codes[i + 4])
                i += 4
            i += 1
    while len(lines) > 1 and not lines[-1]:
        lines.pop()
    return lines


def wrap(line: list[Cell], cols: int) -> list[list[Cell]]:
    rows: list[list[Cell]] = [[]]
    width = 0
    for cell in line:
        w = 2 if cell.wide else 1
        if width + w > cols:
            rows.append([])
            width = 0
        rows[-1].append(cell)
        width += w
    return rows


def _plain_row(row: list[Cell]) -> str:
    return "".join(c.ch for c in row)


@dataclass
class Screen:
    """A rendered terminal image and the grid that maps pixels back to text."""

    path: Path
    width: int
    height: int
    cell_w: float
    cell_h: int
    top: int  # y of the first text row
    rows: list[str] = field(default_factory=list)  # plain text of each drawn row

    def text_in_box(self, x_min: int, y_min: int, x_max: int, y_max: int) -> str:
        """The text of the grid cells a 0-1000 normalized box covers (rows joined by newlines)."""
        x0, x1 = sorted((x_min * self.width / 1000, x_max * self.width / 1000))
        y0, y1 = sorted((y_min * self.height / 1000, y_max * self.height / 1000))
        c0 = max(0, int((x0 - PAD) // self.cell_w))
        c1 = max(c0, int((x1 - PAD) // self.cell_w))
        picked: list[str] = []
        for r in range(len(self.rows)):
            top = self.top + r * self.cell_h
            covered = min(y1, top + self.cell_h) - max(y0, top)
            if covered < 0.4 * self.cell_h:  # a box edge that only grazes a row does not select it
                continue
            row, col, out = self.rows[r], 0, []
            for ch in row:
                w = 2 if _wide(ch) else 1
                if col + w > c0 and col <= c1:
                    out.append(ch)
                col += w
            text = "".join(out).strip()
            if text:
                picked.append(text)
        return "\n".join(picked)


def render_terminal(command: str, stdout: str, stderr: str, path: Path, *, title: str,
                    cols: int = COLS, max_rows: int = MAX_ROWS) -> Screen:
    """Draw `$ command` and its output on a terminal-like PNG at `path`."""
    font = _font(MONO_FONTS, FONT_SIZE)
    wide_font = _font(WIDE_FONTS, FONT_SIZE)
    cell_w = font.getlength("M") if hasattr(font, "getlength") else FONT_SIZE * 0.6
    ascent, descent = font.getmetrics() if hasattr(font, "getmetrics") else (FONT_SIZE, 4)
    cell_h = ascent + descent + 3

    logical: list[list[Cell]] = []
    for i, part in enumerate(command.split("\n")):
        prefix = PROMPT if i == 0 else "> "
        logical.append([Cell(ch, PROMPT_FG if i == 0 else DIM) for ch in prefix]
                       + [Cell(ch, FG, wide=_wide(ch)) for ch in part])
    output = stdout.rstrip("\n")
    if stderr.strip():
        output = f"{output}\n{stderr.rstrip()}" if output else stderr.rstrip()
    if output:
        logical += parse_ansi(output)
    rows = [row for line in logical for row in wrap(line, cols)]
    if len(rows) > max_rows:
        cut = len(rows) - max_rows + 1
        note = f"[... {cut} lines omitted ...]"
        rows = rows[:HEAD_ROWS] + [[Cell(ch, DIM) for ch in note]] + rows[HEAD_ROWS + cut:]

    width = int(PAD * 2 + cell_w * cols)
    top = TITLE_H + PAD
    height = top + cell_h * max(len(rows), 1) + PAD
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, TITLE_H], fill=TITLE_BG)
    for k, color in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        x = PAD + k * 18
        draw.ellipse([x, TITLE_H // 2 - 6, x + 12, TITLE_H // 2 + 6], fill=color)
    draw.text((PAD + 64, (TITLE_H - FONT_SIZE) // 2 - 1), title[:110], font=font, fill=TITLE_FG)
    for r, row in enumerate(rows):
        y = top + r * cell_h
        col = 0
        for cell in row:
            x = PAD + col * cell_w
            use = wide_font if cell.wide else font
            draw.text((x, y), cell.ch, font=use, fill=cell.fg)
            if cell.bold:  # no bold face on every host: overstrike one pixel to the right
                draw.text((x + 1, y), cell.ch, font=use, fill=cell.fg)
            col += 2 if cell.wide else 1
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)
    return Screen(path=path, width=width, height=height, cell_w=cell_w, cell_h=cell_h, top=top,
                  rows=[_plain_row(row) for row in rows])


def annotate(screen: Screen, regions: list[tuple[str, tuple[int, int, int, int]]], path: Path) -> Path:
    """A copy of the screenshot with each (label, 0-1000 box) drawn on it."""
    image = Image.open(screen.path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = _font(MONO_FONTS, 13)
    for label, (x_min, y_min, x_max, y_max) in regions:
        x0, x1 = sorted((x_min * screen.width / 1000, x_max * screen.width / 1000))
        y0, y1 = sorted((y_min * screen.height / 1000, y_max * screen.height / 1000))
        draw.rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2], outline=MARK, width=3)
        tag = label[:60]
        tw = font.getlength(tag) if hasattr(font, "getlength") else len(tag) * 8
        ty = y0 - 20 if y0 - 20 > TITLE_H else y1 + 4
        draw.rectangle([x0 - 2, ty, x0 + tw + 8, ty + 17], fill=MARK)
        draw.text((x0 + 3, ty + 1), tag, font=font, fill=(0, 0, 0))
    image.save(path, "PNG", optimize=True)
    return path
