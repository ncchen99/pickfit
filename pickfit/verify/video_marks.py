"""What a verification clip draws on the picture (video.py), none of it words that need translating:

- the honesty marks in the top right corner of every frame a change touches: "2×" when the segment plays at twice
  its speed, "−11 s" when that much of the recording was left out of the segment or just before it;
- a ripple where pickfit clicked, from its action log (the recording shows the pointer, not the press);
- the keys of a shortcut pickfit pressed, as keycaps in the bottom left corner (⌘⇧G on a Mac, Ctrl S elsewhere).

Pillow draws them on transparent PNGs that ffmpeg lays over the segment, each only while it applies. The font is
the one embedded in Pillow (Aileron, CC0); it has no ×, −, ⌘, ⇧, ⌥, ⌃ or arrows, so those are drawn as lines.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

MARK_FONT = 34  # pixels at the clip's 1280 width: about 10 px on a 390 px phone
MARK_PAD, MARK_GAP, MARK_EDGE = 12, 8, 14
MARK_FILL, MARK_TEXT = (0, 0, 0, 200), (255, 255, 255, 255)
KEY_FONT = 34
KEY_FILL, KEY_TEXT, KEY_EDGE = (245, 245, 245, 235), (20, 20, 20, 255), (0, 0, 0, 150)
KEY_HOLD_S = 1.4  # a shortcut's keycaps stay this long in the clip
RIPPLE_STAGES = ((10, 255), (17, 230), (24, 190), (31, 140), (38, 90))  # (radius, alpha), one per frame from the press
RIPPLE_STAGE_S = 0.1
RIPPLE_RING, RIPPLE_COLOR = 4, (255, 204, 0)
DRAWN = set("×−⌘⇧⌥⌃↵⌫←→↑↓")  # drawn as lines: the font has no glyph for these

# A Mac's modifiers as its keycaps show them, in Apple's order; elsewhere as words.
MAC_MODIFIERS = {"ctrl": "⌃", "alt": "⌥", "shift": "⇧", "cmd": "⌘"}
MAC_ORDER = ("ctrl", "alt", "shift", "cmd")
PC_MODIFIERS = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift", "super": "Super", "meta": "Super",
                "cmd": "Super", "win": "Super"}
KEY_LABELS = {"return": "↵", "enter": "↵", "backspace": "⌫", "tab": "Tab", "escape": "Esc", "esc": "Esc",
              "delete": "Del", "insert": "Ins", "home": "Home", "end": "End", "page_up": "PgUp", "pageup": "PgUp",
              "page_down": "PgDn", "pagedown": "PgDn", "up": "↑", "down": "↓", "left": "←", "right": "→",
              "arrowup": "↑", "arrowdown": "↓", "arrowleft": "←", "arrowright": "→", "space": "Space", "menu": "Menu",
              "slash": "/", "backslash": "\\", "comma": ",", "period": ".", "minus": "-", "equal": "=", "plus": "+",
              "semicolon": ";", "apostrophe": "'", "bracketleft": "[", "bracketright": "]", "grave": "`"}


def _font(size: int) -> Any:
    from PIL import ImageFont

    return ImageFont.load_default(size=size)  # Aileron (CC0), embedded in Pillow


def _png(img: Any) -> bytes:
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def _symbol_width(ch: str, size: int) -> int:
    return round(size * (0.55 if ch in "×−" else 0.72))


def text_width(text: str, size: int) -> int:
    """The width of `text` as _draw_text draws it."""
    from PIL import Image, ImageDraw

    draw, font = ImageDraw.Draw(Image.new("L", (1, 1))), _font(size)
    return sum(_symbol_width(c, size) if c in DRAWN else round(draw.textlength(c, font=font)) for c in text)


def _draw_symbol(draw: Any, ch: str, x: int, y: int, size: int, fill: Any) -> None:
    """One of DRAWN as lines in a box `_symbol_width` wide whose top is the text's top at `y` (cap height ~0.7 em)."""
    w, line = _symbol_width(ch, size), max(2, round(size * 0.09))
    top, bottom = y + round(size * 0.16), y + round(size * 0.86)
    mid, cx = (top + bottom) // 2, x + w // 2
    left, right = x + round(w * 0.12), x + w - round(w * 0.12)
    if ch == "×":
        h, low = round(size * 0.17), y + round(size * 0.6)  # centred on the digits beside it
        draw.line((cx - h, low - h, cx + h, low + h), fill=fill, width=line)
        draw.line((cx - h, low + h, cx + h, low - h), fill=fill, width=line)
    elif ch == "−":
        draw.line((left, mid + 2, right, mid + 2), fill=fill, width=line)
    elif ch == "⌘":
        r, h = round(w * 0.13), round(w * 0.16)
        for sx in (-1, 1):
            for sy in (-1, 1):
                ox, oy = cx + sx * (h + r), mid + sy * (h + r)
                draw.ellipse((ox - r, oy - r, ox + r, oy + r), outline=fill, width=max(2, line - 1))
        for k in (-h, h):
            draw.line((cx - h - r, mid + k, cx + h + r, mid + k), fill=fill, width=max(2, line - 1))
            draw.line((cx + k, mid - h - r, cx + k, mid + h + r), fill=fill, width=max(2, line - 1))
    elif ch == "⇧":
        s = round(w * 0.2)
        draw.polygon([(cx, top), (right, mid), (cx + s, mid), (cx + s, bottom), (cx - s, bottom), (cx - s, mid),
                      (left, mid)], outline=fill, width=max(2, line - 1))
    elif ch == "⌥":
        a, b = left + round((right - left) * 0.32), left + round((right - left) * 0.68)
        draw.line((left, top + 4, a, top + 4), fill=fill, width=line)
        draw.line((a, top + 4, b, bottom - 4), fill=fill, width=line)
        draw.line((b, bottom - 4, right, bottom - 4), fill=fill, width=line)
        draw.line((b - 2, top + 4, right, top + 4), fill=fill, width=line)
    elif ch == "⌃":
        draw.line((left, mid + 4, cx, top + 4, right, mid + 4), fill=fill, width=line, joint="curve")
    elif ch in "↵⌫←→↑↓":
        head = round(w * 0.22)
        if ch == "↵":
            draw.line((right, top + 2, right, mid + 4, left + 2, mid + 4), fill=fill, width=line, joint="curve")
            tip = (left, mid + 4)
            draw.line((tip[0] + head, tip[1] - head, *tip, tip[0] + head, tip[1] + head), fill=fill, width=line)
        elif ch == "⌫":
            draw.polygon([(left, mid), (left + head + 2, top + 4), (right, top + 4), (right, bottom - 4),
                          (left + head + 2, bottom - 4)], outline=fill, width=max(2, line - 1))
            k = round(w * 0.12)
            ox = (left + head + right) // 2 + 2
            draw.line((ox - k, mid - k, ox + k, mid + k), fill=fill, width=max(2, line - 1))
            draw.line((ox - k, mid + k, ox + k, mid - k), fill=fill, width=max(2, line - 1))
        elif ch in "←→":
            a, b = (right, left) if ch == "←" else (left, right)
            step = head if ch == "←" else -head
            draw.line((a, mid, b, mid), fill=fill, width=line)
            draw.line((b + step, mid - head, b, mid, b + step, mid + head), fill=fill, width=line)
        else:
            a, b = (bottom, top) if ch == "↑" else (top, bottom)
            step = head if ch == "↑" else -head
            draw.line((cx, a, cx, b), fill=fill, width=line)
            draw.line((cx - head, b + step, cx, b, cx + head, b + step), fill=fill, width=line)


def draw_text(draw: Any, xy: tuple[int, int], text: str, size: int, fill: Any) -> int:
    """`text` at `xy` (its top left), the font's glyphs and DRAWN's lines in one run; returns its width."""
    font, x, y = _font(size), *xy
    for ch in text:
        if ch in DRAWN:
            _draw_symbol(draw, ch, x, y, size, fill)
            x += _symbol_width(ch, size)
        else:
            draw.text((x, y), ch, font=font, fill=fill)
            x += round(draw.textlength(ch, font=font))
    return x - xy[0]


def honesty_marks(faster: bool, trimmed_s: float) -> list[str]:
    """The marks a segment carries: "2×" at twice its speed, "−N s" when N seconds were left out of it or before it."""
    marks = ["2×"] if faster else []
    if trimmed_s >= 0.5:
        marks.append(f"−{max(1, round(trimmed_s))} s")
    return marks


def marks_png(width: int, height: int, marks: list[str]) -> bytes:
    """The honesty marks as pills in the top right corner of a transparent frame the clip's size."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    right = width - MARK_EDGE
    for mark in reversed(marks):
        w = text_width(mark, MARK_FONT) + 2 * MARK_PAD
        h = round(MARK_FONT * 1.05) + MARK_PAD
        draw.rounded_rectangle((right - w, MARK_EDGE, right, MARK_EDGE + h), radius=h // 2 - 2, fill=MARK_FILL)
        draw_text(draw, (right - w + MARK_PAD, MARK_EDGE + MARK_PAD // 2 - 2), mark, MARK_FONT, MARK_TEXT)
        right -= w + MARK_GAP
    return _png(img)


def key_caps(name: str, os: str) -> list[str]:
    """A key combination as pickfit logged it (cmd+shift+g, ctrl+s, Return, Enter, Control+a) as keycap labels."""
    parts = [p for p in name.replace("-", "+").split("+") if p] or [name]
    if name.strip() and name.strip("+") == "":
        parts = ["+"]
    *mods, key = parts
    mods = [m.lower() for m in mods]
    if os == "macos":
        mods = [{"command": "cmd", "super": "cmd", "meta": "cmd", "control": "ctrl", "option": "alt"}.get(m, m)
                for m in mods]
        caps = [MAC_MODIFIERS[m] for m in MAC_ORDER if m in mods] + [MAC_MODIFIERS.get(m, m.title()) for m in mods
                                                                     if m not in MAC_ORDER]
    else:
        caps = [PC_MODIFIERS.get(m, m.title()) for m in mods]
    label = KEY_LABELS.get(key.lower(), key.upper() if len(key) == 1 else key[:1].upper() + key[1:])
    return caps + [label]


def keys_png(caps: list[str]) -> tuple[bytes, int, int]:
    """Keycaps side by side on a transparent image: (png, width, height)."""
    from PIL import Image, ImageDraw

    pad, gap, h = 14, 8, round(KEY_FONT * 1.05) + 20
    widths = [max(h - 6, text_width(c, KEY_FONT) + 2 * pad) for c in caps]
    width = sum(widths) + gap * (len(caps) - 1) + 6
    img = Image.new("RGBA", (width, h + 6), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x = 3
    for cap, w in zip(caps, widths):
        draw.rounded_rectangle((x, 6, x + w, h + 5), radius=10, fill=KEY_EDGE)  # its shadow
        draw.rounded_rectangle((x, 1, x + w, h), radius=10, fill=KEY_FILL, outline=KEY_EDGE, width=2)
        draw_text(draw, (x + (w - text_width(cap, KEY_FONT)) // 2, 1 + (h - KEY_FONT) // 2 - 3), cap, KEY_FONT,
                  KEY_TEXT)
        x += w + gap
    return _png(img), width, h + 6


def ripple_pngs() -> list[tuple[bytes, int]]:
    """The ripple's frames: a ring that grows and fades, each (png, its radius plus the ring); centred on the click."""
    from PIL import Image, ImageDraw

    out = []
    size = RIPPLE_STAGES[-1][0] + RIPPLE_RING + 4
    for radius, alpha in RIPPLE_STAGES:
        img = Image.new("RGBA", (2 * size, 2 * size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        box = (size - radius, size - radius, size + radius, size + radius)
        draw.ellipse(box, outline=(0, 0, 0, alpha // 2), width=RIPPLE_RING + 3)  # a dark edge for light screens
        draw.ellipse(box, outline=(*RIPPLE_COLOR, alpha), width=RIPPLE_RING)
        out.append((_png(img), size))
    return out


@dataclass(frozen=True)
class Overlay:
    """A picture laid over a piece: `png` at (x, y) of the clip's frame, from `start` until `end` (piece seconds)."""

    png: bytes
    x: int
    y: int
    start: float
    end: float
