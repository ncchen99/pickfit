#!/usr/bin/env python3
"""Build the Fitz mascot SVGs from one set of shapes and one palette.

Every file in brand/mascot/ except README.md, index.html and this script is
written by this script, so palette and line weight stay the same everywhere.

    python3 brand/mascot/build.py
"""

from __future__ import annotations

import math
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------- palette
INK = "#4A2E22"  # outlines, eyes, beak
BODY = "#A9BC4C"  # olive yellow-green
WING = "#869E3A"  # darker olive: wing
TAIL = "#7C9334"  # darkest olive: tail
CAP = "#C4552D"  # rufous cap
BELLY = "#FFF3D3"  # cream
TAPE = "#F5C243"  # measuring tape
METAL = "#C3CAD2"  # tape end tab
BLUSH = "#F2917C"
WHITE = "#FFFFFF"
SWEAT = "#7CC0E8"
LEAF = "#6CBF4E"
LEAF_DARK = "#3E8A3A"
BOX = "#E8BC7E"
BOX_DARK = "#C9924E"
SPARK = "#F5C243"
BAD = "#D9533C"
GOOD = "#4CA65A"

SW = 4.5  # outer line weight (200-unit canvas)
SW2 = 3  # inner detail line weight

# ---------------------------------------------------------------- geometry
BODY_C = (100, 126)
BODY_R = (64, 57)
EYE_NEAR = (96, 118)
EYE_FAR = (134, 116)
BEAK_BASE = (143, 124.5)

# tail: narrow where it leaves the body, wider rounded tip, leaning back a little
TAIL_PATH = "M67 104 C 62 86, 52 67, 46 53 Q 40 36 55.5 33 Q 71 30 72 46 C 72.5 64, 76 84, 81 102 Z"
TAIL_SPLIT = "M56.5 34 Q57.6 39.5 58 45"

# measuring-tape band around the neck: two quadratic curves
BAND_TOP = ((32, 136), (106, 160), (168, 134))
BAND_BOT = ((33, 146.5), (106, 171), (168, 144.5))

# rufous cap: crown plus forehead, reaching down to the beak like the real bird
CAP_PATH = (
    "M28 106 C 52 93, 74 102, 95 98 C 116 94, 134 92, 147 102 "
    "C 153 108, 158 116, 172 118 L172 40 L28 40 Z"
)
WING_PATH = "M56 150 Q 54 167 71 172 Q 84 175 84 164 Q 80 152 56 150 Z"
SHADOW = f'<ellipse class="shadow" cx="103" cy="193.5" rx="34" ry="3.6" fill="{INK}" opacity=".12"/>'


def qpt(p, t):
    (x0, y0), (x1, y1), (x2, y2) = p
    a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
    return a * x0 + b * x1 + c * x2, a * y0 + b * y1 + c * y2


def qtan(p, t):
    (x0, y0), (x1, y1), (x2, y2) = p
    dx = 2 * (1 - t) * (x1 - x0) + 2 * t * (x2 - x1)
    dy = 2 * (1 - t) * (y1 - y0) + 2 * t * (y2 - y1)
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def t_at_x(p, x):
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if qpt(p, mid)[0] < x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def qd(p):
    (x0, y0), (x1, y1), (x2, y2) = p
    return f"M{f(x0)} {f(y0)} Q{f(x1)} {f(y1)} {f(x2)} {f(y2)}"


# ---------------------------------------------------------------- parts
def eye(cx, cy, kind, far=False):
    """One eye, wrapped in <g class="eye"> so it can blink."""
    rx, ry = (6, 7.6) if far else (6.8, 8.3)
    if kind in ("open", "look_up", "look_down", "wide"):
        dy = {"look_up": -2, "look_down": 2.2}.get(kind, 0)
        if kind == "wide":
            rx, ry = rx + 1.2, ry + 1.6
        hl = 2.4 if kind == "wide" else 2.1
        return (
            f'<g class="eye"><ellipse cx="{f(cx)}" cy="{f(cy + dy)}" rx="{f(rx)}" ry="{f(ry)}" fill="{INK}"/>'
            f'<circle cx="{f(cx - 1.9)}" cy="{f(cy + dy - 2.8)}" r="{hl}" fill="{WHITE}"/></g>'
        )
    if kind == "happy":  # closed, smiling arcs
        return (
            f'<g class="eye"><path d="M{f(cx - rx)} {f(cy + 2)} Q{f(cx)} {f(cy - 7)} {f(cx + rx)} {f(cy + 2)}" '
            f'fill="none" stroke="{INK}" stroke-width="4" stroke-linecap="round"/></g>'
        )
    if kind == "proud":  # pointed ^ ^, chin goes up with it
        return (
            f'<g class="eye"><path d="M{f(cx - rx)} {f(cy + 2.5)} L{f(cx)} {f(cy - 4.5)} L{f(cx + rx)} {f(cy + 2.5)}" '
            f'fill="none" stroke="{INK}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>'
        )
    raise ValueError(kind)


# (near brow, far brow) as points relative to each eye centre:
# two points = straight line, three = start, control, end of a curve.
BROWS = {
    "worried": (((-9, -12), (5, -16.5)), ((-7, -18), (6, -14))),
    "raised": (((-7.5, -15), (0, -21), (7.5, -15)), ((-6.5, -16), (0, -22), (6.5, -16))),
    "curious": (((-7, -14.5), (6, -15)), ((-6.5, -17), (0, -24), (6.5, -17))),
    "determined": (((-7.5, -17), (6, -13)), ((-6.5, -13.5), (6, -17.5))),
}


def _brow(pts, at):
    x, y = at
    p = [(x + a, y + b) for a, b in pts]
    if len(p) == 2:
        return f"M{f(p[0][0])} {f(p[0][1])} L{f(p[1][0])} {f(p[1][1])}"
    return f"M{f(p[0][0])} {f(p[0][1])} Q{f(p[1][0])} {f(p[1][1])} {f(p[2][0])} {f(p[2][1])}"


def brows(kind):
    if not kind:
        return ""
    a, b = BROWS[kind]
    s = f'stroke="{INK}" stroke-width="3.5" stroke-linecap="round" fill="none"'
    return f'<g class="brows"><path d="{_brow(a, EYE_NEAR)}" {s}/><path d="{_brow(b, EYE_FAR)}" {s}/></g>'


BEAK_UP = "M146 119.8 L189 124.6 L143 124.6 Q143 121.2 146 119.8 Z"
BEAK_LO = "M143 124.6 L189 124.6 L146 129.4 Q143 128 143 124.6 Z"


def beak(kind="closed"):
    bx, by = BEAK_BASE
    if kind == "closed":
        inner = f'<path d="{BEAK_UP}"/><path d="{BEAK_LO}"/>'
    elif kind == "open":
        inner = (
            f'<path d="{BEAK_UP}" transform="rotate(-3 {bx} {by})"/>'
            f'<path d="{BEAK_LO}" transform="rotate(9 {bx} {by})"/>'
        )
    elif kind == "down":
        inner = f'<g transform="rotate(9 {bx} {by})"><path d="{BEAK_UP}"/><path d="{BEAK_LO}"/></g>'
    elif kind == "up":
        inner = f'<g transform="rotate(-8 {bx} {by})"><path d="{BEAK_UP}"/><path d="{BEAK_LO}"/></g>'
    else:
        raise ValueError(kind)
    return f'<g class="beak" fill="{INK}">{inner}</g>'


def tape_ticks():
    out = []
    for i, t in enumerate([0.1 + k * 0.065 for k in range(13)]):
        x, y = qpt(BAND_TOP, t)
        tx, ty = qtan(BAND_TOP, t)
        nx, ny = -ty, tx  # normal pointing into the band (down)
        if ny < 0:
            nx, ny = -nx, -ny
        ln = 5.5 if i % 2 == 0 else 3.5
        out.append(f"M{f(x)} {f(y)} L{f(x + nx * ln)} {f(y + ny * ln)}")
    return f'<path d="{" ".join(out)}" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>'


def tape_end():
    """The free end of the tape hanging down the chest."""
    x = 94
    _, y = qpt(BAND_BOT, t_at_x(BAND_BOT, x))
    ticks = " ".join(
        f"M-5.5 {y0} L{-1.5 if k % 2 else 0} {y0}" for k, y0 in enumerate(range(7, 20, 6))
    )
    return (
        f'<g class="tape-end" transform="translate({f(x)} {f(y - 6)}) rotate(7)">'
        f'<rect x="-5.5" y="0" width="11" height="25" rx="1.5" fill="{TAPE}" stroke="{INK}" stroke-width="{SW2}"/>'
        f'<path d="{ticks}" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>'
        f'<rect x="-5.5" y="21" width="11" height="6.5" rx="1.5" fill="{METAL}" stroke="{INK}" stroke-width="{SW2}"/>'
        f"</g>"
    )


def band(cid):
    (a, _, b) = BAND_TOP
    (c, _, d) = BAND_BOT
    shape = (
        f"{qd(BAND_TOP)} L{f(d[0])} {f(d[1])} "
        f"Q{f(BAND_BOT[1][0])} {f(BAND_BOT[1][1])} {f(c[0])} {f(c[1])} Z"
    )
    return (
        f'<g class="band" clip-path="url(#{cid})">'
        f'<path d="{shape}" fill="{TAPE}"/>'
        f"{tape_ticks()}"
        f'<path d="{qd(BAND_TOP)}" fill="none" stroke="{INK}" stroke-width="{SW2}"/>'
        f'<path d="{qd(BAND_BOT)}" fill="none" stroke="{INK}" stroke-width="{SW2}"/>'
        f"</g>"
    )


def feet():
    s = f'stroke="{INK}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    return (
        f'<g class="feet"><path d="M91 179 L89 192 M83.5 192.5 L95 192.5" {s}/>'
        f'<path d="M113 179 L115 192 M109.5 192.5 L121 192.5" {s}/></g>'
    )


def bird(
    cid="fitz-body",
    eyes="open",
    brow=None,
    beak_kind="closed",
    blush=True,
    tape_hanging=True,
    pupils_class=True,
):
    cx, cy = BODY_C
    rx, ry = BODY_R
    ell = f'cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}"'
    cap = CAP_PATH
    wing = WING_PATH
    e1 =eye(*EYE_NEAR, eyes)
    e2 = eye(*EYE_FAR, eyes, far=True)
    return (
        f'<defs><clipPath id="{cid}"><ellipse {ell}/></clipPath></defs>'
        f"{SHADOW}"
        f'<g class="bird">'
        f"{feet()}"
        f'<g class="tail"><path d="{TAIL_PATH}" fill="{TAIL}" stroke="{INK}" stroke-width="{SW}" stroke-linejoin="round"/>'
        f'<path d="{TAIL_SPLIT}" fill="none" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/></g>'
        f'<g class="body">'
        f'<ellipse {ell} fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="{cap}" fill="{CAP}"/>'
        f'<ellipse cx="112" cy="164" rx="49" ry="34" fill="{BELLY}"/></g>'
        f'<path d="{wing}" fill="{WING}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/>'
        + (tape_end() if tape_hanging else "")
        + band(cid)
        + f'<ellipse {ell} fill="none" stroke="{INK}" stroke-width="{SW}"/>'
        + (
            f'<g class="blush" fill="{BLUSH}" opacity=".55"><ellipse cx="80" cy="132" rx="8" ry="4.5"/>'
            f'<ellipse cx="154" cy="135" rx="5.5" ry="4"/></g>'
            if blush
            else ""
        )
        + f'<g class="{"pupils" if pupils_class else "eyes"}">{e1}{e2}</g>'
        + brows(brow)
        + beak(beak_kind)
        + "</g></g>"
    )


# ---------------------------------------------------------------- accents
def sparks(cls="sparks", at=(0, 0)):
    x, y = at
    s = f'stroke="{SPARK}" stroke-width="4.5" stroke-linecap="round"'
    return (
        f'<g class="{cls}" transform="translate({x} {y})">'
        f'<path d="M158 52 L161 41" {s}/><path d="M168 60 L177 53" {s}/><path d="M172 72 L182 71" {s}/></g>'
    )


def star(x, y, r, cls="star", color=SPARK):
    k = r * 0.18
    d = (
        f"M{f(x)} {f(y - r)} Q{f(x + k)} {f(y - k)} {f(x + r)} {f(y)} "
        f"Q{f(x + k)} {f(y + k)} {f(x)} {f(y + r)} Q{f(x - k)} {f(y + k)} {f(x - r)} {f(y)} "
        f"Q{f(x - k)} {f(y - k)} {f(x)} {f(y - r)} Z"
    )
    return f'<path class="{cls}" d="{d}" fill="{color}"/>'


def question(x, y, cls="question"):
    return (
        f'<g class="{cls}" transform="translate({x} {y})" fill="none" stroke="{CAP}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M-6 -7 Q-6 -15 1 -15 Q8 -15 8 -8 Q8 -3 2 -0.5 L2 4"/>'
        f'<circle cx="2" cy="11" r="1.2" fill="{CAP}"/></g>'
    )


def sweat(x, y, cls="sweat"):
    return (
        f'<g transform="translate({x} {y})"><g class="{cls}">'
        f'<path d="M0 -10 C4 -4 7 0 7 3.5 A7 7 0 0 1 -7 3.5 C-7 0 -4 -4 0 -10 Z" fill="{SWEAT}"/>'
        f'<path d="M-3 2.5 Q-3 5 -1 6" stroke="{WHITE}" stroke-width="1.8" stroke-linecap="round" fill="none"/></g></g>'
    )


def exclaim(cls="exclaim"):
    s = f'stroke="{CAP}" stroke-width="4.5" stroke-linecap="round"'
    return (
        f'<g class="{cls}"><path d="M163 46 L165 30" {s}/><path d="M174 56 L184 44" {s}/>'
        f'<path d="M178 70 L192 66" {s}/></g>'
    )


# ---------------------------------------------------------------- props
def leaf(cls="leaf"):
    """A stitched leaf held at the beak tip: what Fitz presents."""
    shape = "M0 0 C 10 -24, 44 -32, 66 -22 C 54 -2, 26 10, 0 0 Z"
    rib = "M2 -1 Q 30 -11 62 -21"
    stitches = " ".join(
        f"M{f(x - 3)} {f(y - 4)} L{f(x + 3)} {f(y + 4)}"
        for x, y in [(18, -6.5), (30, -10.5), (42, -14.3), (53, -17.5)]
    )
    return (
        f'<g class="{cls}"><g transform="translate(186 125) rotate(-4)">'
        f'<path d="{shape}" fill="{LEAF}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/>'
        f'<path d="{rib}" fill="none" stroke="{LEAF_DARK}" stroke-width="2.4" stroke-linecap="round"/>'
        f'<path d="{stitches}" stroke="{BELLY}" stroke-width="2.4" stroke-linecap="round"/>'
        f"</g></g>"
    )


def package(x=212, y=134, w=72, h=58):
    """A software package: a box with </> on it."""
    cx = x + w / 2
    my = y + h / 2 + 4
    return (
        f'<g class="package">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{BOX}" stroke="{INK}" stroke-width="{SW}"/>'
        f'<path d="M{x + 2} {y + 14} L{x + w - 2} {y + 14}" stroke="{BOX_DARK}" stroke-width="{SW2}"/>'
        f'<path d="M{f(cx - 10)} {f(my - 7)} L{f(cx - 17)} {f(my)} L{f(cx - 10)} {f(my + 7)} '
        f'M{f(cx + 10)} {f(my - 7)} L{f(cx + 17)} {f(my)} L{f(cx + 10)} {f(my + 7)} '
        f'M{f(cx + 3)} {f(my - 9)} L{f(cx - 3)} {f(my + 9)}" fill="none" stroke="{INK}" stroke-width="{SW2}" '
        f'stroke-linecap="round" stroke-linejoin="round"/></g>'
    )


def strip(x0, length, y=120, h=9, cls="strip"):
    """A straight run of tape from the beak tip, with its hook end."""
    ticks = " ".join(
        f"M{f(x)} {y} L{f(x)} {y + (5 if k % 2 == 0 else 3)}"
        for k, x in enumerate(range(x0 + 6, x0 + length - 3, 6))
    )
    xe = x0 + length
    return (
        f'<g class="{cls}">'
        f'<rect x="{x0 - 6}" y="{y}" width="{length + 6}" height="{h}" fill="{TAPE}" stroke="{INK}" stroke-width="{SW2}"/>'
        f'<path d="{ticks}" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M{xe} {y - 1} L{xe + 4} {y - 1} L{xe + 4} {y + h + 9} L{xe} {y + h + 9} Z" '
        f'fill="{METAL}" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/></g>'
    )


def check_badge(x, y, r=15, cls="badge"):
    return (
        f'<g class="{cls}"><circle cx="{x}" cy="{y}" r="{r}" fill="{GOOD}" stroke="{INK}" stroke-width="{SW2}"/>'
        f'<path d="M{x - 6.5} {y + 0.5} L{x - 1.5} {y + 5.5} L{x + 7} {y - 5}" fill="none" stroke="{WHITE}" '
        f'stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>'
    )


# ---------------------------------------------------------------- documents
REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"


def doc(view, body, title, desc, css="", size=None):
    w, h = size or view.split()[2:]
    style = f"<style>{css}{REDUCED}</style>" if css else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" width="{w}" height="{h}" '
        f'role="img" aria-labelledby="t d">'
        f'<title id="t">{title}</title><desc id="d">{desc}</desc>{style}{body}</svg>\n'
    )


def write(name, text):
    p = HERE / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    print("wrote", p.relative_to(HERE))


# ---------------------------------------------------------------- build
EXPRESSIONS = {
    "neutral": dict(eyes="open"),
    "happy": dict(eyes="happy", extra=lambda: sparks()),
    "thinking": dict(eyes="look_up", brow="curious", extra=lambda: question(170, 58), tilt=-5),
    "surprised": dict(eyes="wide", brow="raised", beak_kind="open", extra=lambda: exclaim(), blush=False),
    "sorry": dict(eyes="look_down", brow="worried", beak_kind="down", extra=lambda: sweat(160, 74)),
    "proud": dict(
        eyes="proud",
        beak_kind="up",
        tilt=-4,
        extra=lambda: star(166, 52, 11) + star(184, 76, 6),
    ),
}

VIEW = "0 0 200 200"


def build_expressions():
    for name, o in EXPRESSIONS.items():
        b = bird(
            eyes=o["eyes"],
            brow=o.get("brow"),
            beak_kind=o.get("beak_kind", "closed"),
            blush=o.get("blush", True),
        )
        if o.get("tilt"):
            b = f'<g transform="rotate({o["tilt"]} 104 192)">{b}</g>'
        extra = o["extra"]() if "extra" in o else ""
        write(
            f"expressions/fitz-{name}.svg",
            doc(VIEW, b + extra, f"Fitz, {name}", f"Fitz the tailorbird, {name} expression."),
        )


def build_main():
    desc = (
        "Fitz, the PickFit tailorbird: a round olive bird with a rufous cap, "
        "tail cocked straight up, a needle beak and a measuring tape around its neck."
    )
    write("fitz.svg", doc(VIEW, bird(), "Fitz", desc))


def build_front():
    cx, cy = BODY_C
    rx, ry = BODY_R
    ell = f'cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}"'
    cid = "fitz-front-body"
    cap = "M28 106 C 52 92, 78 104, 100 98 C 122 104, 148 92, 172 106 L172 40 L28 40 Z"
    top = ((34, 137), (100, 165), (166, 137))
    bot = ((35, 147.5), (100, 176), (165, 147.5))
    shape = f"{qd(top)} L165 147.5 Q100 176 35 147.5 Z"
    ticks = []
    for i, t in enumerate([0.12 + k * 0.064 for k in range(13)]):
        x, y = qpt(top, t)
        tx, ty = qtan(top, t)
        nx, ny = -ty, tx
        if ny < 0:
            nx, ny = -nx, -ny
        ln = 5.5 if i % 2 == 0 else 3.5
        ticks.append(f"M{f(x)} {f(y)} L{f(x + nx * ln)} {f(y + ny * ln)}")
    end_t = t_at_x(bot, 118)
    ex, ey = qpt(bot, end_t)
    hang = (
        f'<g transform="translate({f(ex)} {f(ey - 7)}) rotate(-7)">'
        f'<rect x="-5.5" y="0" width="11" height="32" rx="1.5" fill="{TAPE}" stroke="{INK}" stroke-width="{SW2}"/>'
        f'<path d="M-5.5 7 L-1.5 7 M-5.5 13 L0 13 M-5.5 19 L-1.5 19" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>'
        f'<rect x="-5.5" y="27" width="11" height="6.5" rx="1.5" fill="{METAL}" stroke="{INK}" stroke-width="{SW2}"/></g>'
    )
    tail = (
        f'<g transform="rotate(-24 72 104)"><path d="{TAIL_PATH}" fill="{TAIL}" stroke="{INK}" stroke-width="{SW}" stroke-linejoin="round"/>'
        f'<path d="{TAIL_SPLIT}" fill="none" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/></g>'
    )
    wing_l = "M42 126 Q 35 156 57 174 Q 69 180 71 168 Q 67 142 42 126 Z"
    wing_r = "M158 126 Q 165 156 143 174 Q 131 180 129 168 Q 133 142 158 126 Z"
    eyes = eye(78, 118, "open") + eye(122, 118, "open")
    bk = f'<path d="M95 121.5 Q100 118.5 105 121.5 L100.9 136 Q100 138 99.1 136 Z" fill="{INK}"/>'
    blush = (
        f'<g fill="{BLUSH}" opacity=".55"><ellipse cx="65" cy="132" rx="8" ry="4.5"/>'
        f'<ellipse cx="135" cy="132" rx="8" ry="4.5"/></g>'
    )
    body = (
        f'<defs><clipPath id="{cid}"><ellipse {ell}/></clipPath></defs>'
        f"{SHADOW}{feet()}{tail}"
        f'<ellipse {ell} fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="{cap}" fill="{CAP}"/>'
        f'<ellipse cx="100" cy="166" rx="50" ry="35" fill="{BELLY}"/></g>'
        f'<path d="{wing_l}" fill="{WING}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/>'
        f'<path d="{wing_r}" fill="{WING}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/>'
        f"{hang}"
        f'<g clip-path="url(#{cid})"><path d="{shape}" fill="{TAPE}"/>'
        f'<path d="{" ".join(ticks)}" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="{qd(top)}" fill="none" stroke="{INK}" stroke-width="{SW2}"/>'
        f'<path d="{qd(bot)}" fill="none" stroke="{INK}" stroke-width="{SW2}"/></g>'
        f'<ellipse {ell} fill="none" stroke="{INK}" stroke-width="{SW}"/>'
        f"{blush}{eyes}{bk}"
    )
    write("fitz-front.svg", doc(VIEW, body, "Fitz, front view", "Fitz the tailorbird facing the viewer."))


# ------------------------------------------------ animated states
BIRD_PIVOT = "transform-box:fill-box;transform-origin:50% 100%;"
TAIL_PIVOT = ".tail{transform-box:fill-box;transform-origin:68% 92%}"
EYE_PIVOT = ".eye{transform-box:fill-box;transform-origin:50% 50%}"


def build_states():
    # idle: blink, tail bob, breathing
    css = (
        f"{TAIL_PIVOT}{EYE_PIVOT}"
        f".bird{{{BIRD_PIVOT}animation:breathe 4s ease-in-out infinite}}"
        ".tail{animation:bob 4s ease-in-out infinite}"
        ".eye{animation:blink 4s ease-in-out infinite}"
        "@keyframes breathe{0%,100%{transform:scale(1,1)}50%{transform:scale(1.012,.986)}}"
        "@keyframes bob{0%,55%,100%{transform:rotate(0)}64%{transform:rotate(-8deg)}74%{transform:rotate(4deg)}84%{transform:rotate(-2deg)}}"
        "@keyframes blink{0%,40%,48%,100%{transform:scaleY(1)}44%{transform:scaleY(.12)}}"
    )
    write("states/fitz-idle.svg", doc(VIEW, bird(), "Fitz, idle", "Fitz blinks and bobs its tail.", css))

    # searching: head tilts, looks left and right, dots
    css = (
        f"{TAIL_PIVOT}{EYE_PIVOT}"
        f".bird{{{BIRD_PIVOT}animation:tilt 3.2s ease-in-out infinite}}"
        ".pupils{animation:look 3.2s ease-in-out infinite}"
        ".tail{animation:bob 3.2s ease-in-out infinite}"
        ".dot{animation:dot 1.2s ease-in-out infinite}.dot:nth-child(2){animation-delay:.2s}.dot:nth-child(3){animation-delay:.4s}"
        "@keyframes tilt{0%,100%{transform:rotate(0)}18%,38%{transform:rotate(-6deg)}60%,80%{transform:rotate(6deg)}}"
        "@keyframes look{0%,100%{transform:translateX(0)}18%,38%{transform:translateX(-3.5px)}60%,80%{transform:translateX(3.5px)}}"
        "@keyframes bob{0%,100%{transform:rotate(0)}50%{transform:rotate(-4deg)}}"
        "@keyframes dot{0%,100%{opacity:.25;transform:translateY(0)}40%{opacity:1;transform:translateY(-4px)}}"
    )
    dots = "".join(f'<circle class="dot" cx="{x}" cy="58" r="4.5" fill="{CAP}"/>' for x in (160, 174, 188))
    write(
        "states/fitz-searching.svg",
        doc(VIEW, bird(brow="curious") + f"<g>{dots}</g>", "Fitz, searching",
            "Fitz tilts its head and looks left and right while searching.", css),
    )

    # testing: tape runs from the beak across a package
    view = "0 0 300 200"
    css = (
        f"{TAIL_PIVOT}{EYE_PIVOT}"
        ".tail{animation:bob 3.2s ease-in-out infinite}"
        ".strip{animation:pull 3.2s cubic-bezier(.5,0,.3,1) infinite}"
        ".eye{animation:blink 3.2s ease-in-out infinite}"
        ".edge{animation:edge 3.2s ease-in-out infinite}"
        "@keyframes bob{0%,100%{transform:rotate(0)}40%{transform:rotate(-5deg)}55%{transform:rotate(2deg)}}"
        "@keyframes pull{0%,8%{transform:translateX(-100px)}36%,72%{transform:translateX(0)}92%,100%{transform:translateX(-100px)}}"
        "@keyframes blink{0%,80%,88%,100%{transform:scaleY(1)}84%{transform:scaleY(.12)}}"
        "@keyframes edge{0%,34%,74%,100%{opacity:0}40%,68%{opacity:1}}"
    )
    body = (
        package()
        + '<defs><clipPath id="reel"><rect x="187" y="100" width="113" height="60"/></clipPath></defs>'
        + f'<g clip-path="url(#reel)">{strip(192, 92)}</g>'
        + f'<path class="edge" d="M292 112 L292 142" stroke="{GOOD}" stroke-width="3" stroke-linecap="round" stroke-dasharray="4 5"/>'
        + bird(brow="determined", tape_hanging=False)
    )
    write("states/fitz-testing.svg", doc(view, body, "Fitz, testing",
                                         "Fitz pulls its measuring tape across a software package.", css))

    # test failed: tape comes up short, head shake, sorry face
    css = (
        f"{TAIL_PIVOT}{EYE_PIVOT}"
        f".bird{{{BIRD_PIVOT}animation:shake 3.4s ease-in-out infinite}}"
        ".strip{animation:pull 3.4s cubic-bezier(.5,0,.3,1) infinite}"
        ".gap{animation:gap 3.4s ease-in-out infinite}"
        ".sweat{animation:drop 3.4s ease-in-out infinite}"
        "@keyframes pull{0%,6%{transform:translateX(-70px)}26%{transform:translateX(0)}30%{transform:translateX(-5px)}34%,52%{transform:translateX(0)}64%,100%{transform:translateX(-70px)}}"
        "@keyframes shake{0%,64%,90%,100%{transform:rotate(0)}68%{transform:rotate(-4deg)}74%{transform:rotate(4deg)}80%{transform:rotate(-3deg)}86%{transform:rotate(2deg)}}"
        "@keyframes gap{0%,30%,60%,100%{opacity:0}36%,54%{opacity:1}}"
        "@keyframes drop{0%,38%,94%,100%{opacity:0;transform:translateY(-4px)}46%,86%{opacity:1;transform:translateY(0)}}"
    )
    gap = (
        f'<g class="gap" stroke="{BAD}" stroke-width="3" stroke-linecap="round" fill="none">'
        f'<path d="M260 108 L284 108" stroke-dasharray="3 5"/><path d="M260 103 L260 113 M284 103 L284 113"/>'
        f'<path d="M268 84 L278 94 M278 84 L268 94" stroke-width="3.5"/></g>'
    )
    body = (
        package()
        + '<defs><clipPath id="reel"><rect x="187" y="100" width="113" height="60"/></clipPath></defs>'
        + f'<g clip-path="url(#reel)">{strip(192, 62)}</g>'
        + gap
        + bird(eyes="look_down", brow="worried", tape_hanging=False)
        + sweat(162, 70)
    )
    write("states/fitz-test-failed.svg", doc(view, body, "Fitz, test failed",
                                             "Fitz's tape comes up short of the package; it shakes its head, sorry.", css))

    # recommending: presents a stitched leaf
    view = "0 0 270 200"
    css = (
        f"{TAIL_PIVOT}{EYE_PIVOT}"
        f".offer{{{BIRD_PIVOT}animation:offer 2.6s ease-in-out infinite}}"
        ".tail{animation:bob 2.6s ease-in-out infinite}"
        ".star{transform-box:fill-box;transform-origin:50% 50%;animation:twinkle 2.6s ease-in-out infinite}"
        ".star.s2{animation-delay:.35s}.star.s3{animation-delay:.7s}"
        "@keyframes offer{0%,100%{transform:rotate(0) translateY(0)}35%,65%{transform:rotate(3deg) translateY(-3px)}}"
        "@keyframes bob{0%,100%{transform:rotate(0)}45%{transform:rotate(-7deg)}60%{transform:rotate(2deg)}}"
        "@keyframes twinkle{0%,100%{transform:scale(.55);opacity:.5}40%{transform:scale(1.1);opacity:1}}"
    )
    body = (
        '<g class="offer">' + bird(eyes="happy") + leaf() + "</g>"
        + star(236, 70, 9, "star") + star(256, 100, 6, "star s2") + star(212, 58, 5, "star s3")
    )
    write("states/fitz-recommending.svg", doc(view, body, "Fitz, recommending",
                                              "Fitz holds out a stitched leaf: this one fits.", css))

    # success: hop with sparkles and a check badge
    view = "0 0 220 200"
    css = (
        f"{TAIL_PIVOT}"
        f".bird{{{BIRD_PIVOT}animation:hop 1.8s cubic-bezier(.3,0,.4,1) infinite}}"
        ".tail{animation:flick 1.8s ease-in-out infinite}"
        ".badge{transform-box:fill-box;transform-origin:50% 50%;animation:pop 1.8s ease-out infinite}"
        ".sparks{animation:fade 1.8s ease-in-out infinite}"
        "@keyframes hop{0%,100%{transform:translateY(0) scale(1,1)}10%{transform:translateY(0) scale(1.05,.94)}"
        "35%{transform:translateY(-14px) scale(.97,1.04)}60%{transform:translateY(0) scale(1.04,.95)}72%{transform:translateY(0) scale(1,1)}}"
        "@keyframes flick{0%,100%{transform:rotate(0)}35%{transform:rotate(-10deg)}60%{transform:rotate(3deg)}}"
        "@keyframes pop{0%,100%{transform:scale(1)}30%{transform:scale(1.15)}45%{transform:scale(.96)}}"
        "@keyframes fade{0%,100%{opacity:.4}35%{opacity:1}}"
    )
    body = bird(eyes="happy") + sparks() + check_badge(196, 40)
    write("states/fitz-success.svg", doc(view, body, "Fitz, success",
                                         "Fitz hops with joy next to a green check.", css))


# ------------------------------------------------ icons
def icon_64():
    cid = "i64"
    body_e = 'cx="30" cy="38" rx="21" ry="20"'
    top = ((9, 41), (34, 50), (52, 40))
    bot = ((9, 46.5), (34, 56), (52, 45.5))
    band = f"{qd(top)} L52 45.5 Q34 56 9 46.5 Z"
    s = (
        f'<defs><clipPath id="{cid}"><ellipse {body_e}/></clipPath></defs>'
        f'<path d="M18.5 37 L13.2 9.5 Q12.5 4.8 16.7 4.4 Q20.9 4 21.7 8.6 L26.5 35 Z" fill="{TAIL}" stroke="{INK}" stroke-width="2.4" stroke-linejoin="round"/>'
        f'<ellipse {body_e} fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="M6 33 C 15 28, 23 31, 31 29 C 38 27, 44 25, 54 28 L54 10 L6 10 Z" fill="{CAP}"/>'
        f'<ellipse cx="35" cy="53" rx="17" ry="12" fill="{BELLY}"/>'
        f'<path d="{band}" fill="{TAPE}"/><path d="{qd(top)} M{qd(bot)[1:]}" fill="none" stroke="{INK}" stroke-width="1.6"/></g>'
        f'<ellipse {body_e} fill="none" stroke="{INK}" stroke-width="2.4"/>'
        f'<ellipse cx="30" cy="35.5" rx="2.4" ry="3" fill="{INK}"/><ellipse cx="41.5" cy="34.8" rx="2.2" ry="2.8" fill="{INK}"/>'
        f'<circle cx="29.2" cy="34.4" r=".9" fill="{WHITE}"/><circle cx="40.8" cy="33.7" r=".85" fill="{WHITE}"/>'
        f'<path d="M47 37 L62.5 39.6 L47 42 Q45.6 39.5 47 37 Z" fill="{INK}"/>'
    )
    write("icons/fitz-64.svg", doc("0 0 64 64", s, "Fitz icon", "Fitz the tailorbird, 64 px icon."))


def icon_32():
    cid = "i32"
    body_e = 'cx="14.5" cy="19.5" rx="10.6" ry="10.2"'
    s = (
        f'<defs><clipPath id="{cid}"><ellipse {body_e}/></clipPath></defs>'
        f'<path d="M8.6 19 L5.6 4.6 Q5.3 2.4 7.4 2.2 Q9.5 2 9.9 4.2 L12.8 18 Z" fill="{TAIL}" stroke="{INK}" stroke-width="1.5" stroke-linejoin="round"/>'
        f'<ellipse {body_e} fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="M3 17 C 8 14.5, 12 16, 15.5 15 C 19 14, 22 13, 27 14.5 L27 4 L3 4 Z" fill="{CAP}"/>'
        f'<ellipse cx="17" cy="27.5" rx="9" ry="6.5" fill="{BELLY}"/>'
        f'<path d="M3 21.5 Q16 26 27 20.5 L27 23.5 Q16 29 3 24.5 Z" fill="{TAPE}"/></g>'
        f'<ellipse {body_e} fill="none" stroke="{INK}" stroke-width="1.5"/>'
        f'<ellipse cx="15.3" cy="17.9" rx="1.35" ry="1.7" fill="{INK}"/><ellipse cx="20.6" cy="17.5" rx="1.25" ry="1.6" fill="{INK}"/>'
        f'<path d="M22.6 18.4 L31.6 19.9 L22.6 21.4 Q21.8 19.9 22.6 18.4 Z" fill="{INK}"/>'
    )
    write("icons/fitz-32.svg", doc("0 0 32 32", s, "Fitz icon", "Fitz the tailorbird, 32 px icon."))


def icon_16():
    cid = "i16"
    # edges sit on half pixels so the 1 px outline lands on whole pixels
    body_e = 'cx="7.5" cy="10.5" rx="5" ry="5"'
    s = (
        f'<defs><clipPath id="{cid}"><ellipse {body_e}/></clipPath></defs>'
        f'<path d="M4.5 9 L2.5 2.5 Q2.5 0.5 4 0.5 Q5.5 0.5 5.5 2 L7.5 8 Z" fill="{TAIL}" stroke="{INK}" stroke-width="1" stroke-linejoin="round"/>'
        f'<ellipse {body_e} fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="M0 9 L9 8 L16 10 L16 0 L0 0 Z" fill="{CAP}"/>'
        f'<path d="M0 13 Q8 15 16 12 L16 16 L0 16 Z" fill="{BELLY}"/></g>'
        f'<ellipse {body_e} fill="none" stroke="{INK}" stroke-width="1"/>'
        f'<rect x="8.5" y="9" width="2" height="2" rx=".5" fill="{INK}"/>'
        f'<path d="M11.5 9.5 L16 10 L16 11 L11.5 11.5 Z" fill="{INK}"/>'
    )
    write("icons/fitz-16.svg", doc("0 0 16 16", s, "Fitz icon", "Fitz the tailorbird, 16 px icon."))


def mono():
    """One-colour line version; uses currentColor so it can be recoloured."""
    cx, cy = BODY_C
    rx, ry = BODY_R
    ell = f'cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}"'
    cid = "mono-body"
    cap = CAP_PATH
    wing = WING_PATH
    shape_top = qd(BAND_TOP)
    s = (
        f'<defs><clipPath id="{cid}"><ellipse {ell}/></clipPath></defs>'
        f'<g fill="none" stroke="currentColor" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M91 179 L89 192 M83.5 192.5 L95 192.5 M113 179 L115 192 M109.5 192.5 L121 192.5" stroke-width="4"/>'
        f'<path d="{TAIL_PATH}"/>'
        f"<ellipse {ell}/>"
        f'<path d="{wing}" stroke-width="{SW2}"/>'
        f'<g clip-path="url(#{cid})"><path d="{cap}" fill="currentColor" stroke="none"/>'
        f'<path d="{shape_top}" stroke-width="{SW2}"/><path d="{qd(BAND_BOT)}" stroke-width="{SW2}"/>{tape_ticks().replace(INK, "currentColor")}</g>'
        f"</g>"
        f'<ellipse cx="{EYE_NEAR[0]}" cy="{EYE_NEAR[1]}" rx="6.8" ry="8.3" fill="currentColor"/>'
        f'<ellipse cx="{EYE_FAR[0]}" cy="{EYE_FAR[1]}" rx="6" ry="7.6" fill="currentColor"/>'
        f'<g fill="currentColor"><path d="{BEAK_UP}"/><path d="{BEAK_LO}"/></g>'
    )
    write("fitz-mono.svg", doc(VIEW, s, "Fitz, one colour", "Fitz the tailorbird as a one-colour line drawing."))
    # 32 px mono icon: outlined body, solid cap, tail, eye and beak
    body_e = 'cx="14.5" cy="19.5" rx="10.5" ry="10"'
    s = (
        f'<defs><clipPath id="m32"><ellipse {body_e}/></clipPath></defs>'
        '<g fill="currentColor">'
        '<path d="M8.6 19 L5.6 4.6 Q5.3 2.4 7.4 2.2 Q9.5 2 9.9 4.2 L12.8 18 Z"/>'
        '<path clip-path="url(#m32)" d="M3 17 C 8 14.5, 12 16, 15.5 15 C 19 14, 22 13, 27 14.5 L27 4 L3 4 Z"/>'
        '<ellipse cx="15.3" cy="18.4" rx="1.4" ry="1.75"/><ellipse cx="20.6" cy="18" rx="1.3" ry="1.65"/>'
        '<path d="M22.6 18.4 L31.6 19.9 L22.6 21.4 Z"/></g>'
        f'<g fill="none" stroke="currentColor"><ellipse {body_e} stroke-width="2"/>'
        '<path clip-path="url(#m32)" d="M3 22 Q16 26.5 27 21" stroke-width="1.5"/></g>'
    )
    write("icons/fitz-mono-32.svg", doc("0 0 32 32", s, "Fitz icon, one colour", "Fitz silhouette, one colour."))


if __name__ == "__main__":
    build_main()
    build_front()
    build_expressions()
    build_states()
    icon_64()
    icon_32()
    icon_16()
    mono()
