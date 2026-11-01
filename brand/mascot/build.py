#!/usr/bin/env python3
"""Build the Fitz mascot SVGs from one set of shapes and one palette.

Every file in brand/mascot/ except README.md, index.html and this script is
written by this script, so palette and line weight stay the same everywhere.

    python3 brand/mascot/build.py

Version 2: tail grows from the back and sweeps up behind, short orange beak
on the face at the cap line, a wing on the side, and the measuring tape
draped around the neck with both ends hanging in front.
"""

from __future__ import annotations

import math
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------- palette
INK = "#4A2E22"  # outlines, eyes
BODY = "#A9BC4C"  # olive yellow-green
WING = "#869E3A"  # darker olive: wing
TAIL = "#7C9334"  # darkest olive: tail
CAP = "#C4552D"  # rufous cap
BELLY = "#FFF3D3"  # cream
BEAK = "#E8964A"  # warm horn orange: reads on light and dark
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
# One chubby head-body mass, a little fuller at the front where the face is.
BODY_PATH = (
    "M104 66 C 142 64, 168 92, 166 126 C 164 160, 136 185, 100 185 "
    "C 62 185, 36 162, 36 130 C 36 94, 66 68, 104 66 Z"
)
EYE_NEAR = (102, 117)
EYE_FAR = (134, 114)
BEAK_BASE = (148, 110)

# Tail: leaves the BACK of the body and sweeps up and back, cocked.
TAIL_PATH = (
    "M72 104 L46 122 C 35 104, 22 82, 14 62 Q 9 46 21 41 Q 33 37 38 51 "
    "C 44 68, 56 88, 72 104 Z"
)
TAIL_SPLIT = "M22 42.5 Q 24.5 48 26.5 54"

# Rufous cap: crown and forehead, coming down the front to meet the beak.
CAP_PATH = (
    "M58 58 C 64 82, 82 96, 104 98 C 126 100, 144 96, 156 100 "
    "C 162 103, 166 106, 178 108 L178 40 L58 40 Z"
)

# Beak: short, sharp, on the face at the cap line. Two halves so it can open.
BEAK_UP = "M150 100 Q 172 101 189 111 L147 110 Q 146.5 104 150 100 Z"
BEAK_LO = "M147 110 L189 111 Q 172 115.5 152 119.5 Q 147 115.5 147 110 Z"

# Wing: a teardrop on the side, tip pointing back past the body edge.
WING_PATH = "M84 135 C 93 148, 88 169, 69 174 C 56 177, 43 171, 28 162 C 42 157, 54 133, 84 135 Z"

# Tape draped around the neck: each piece starts behind the body (hidden by
# the clip) and its free end hangs down the chest.
TAPE_L = ((28, 131), (100, 121), (103, 174))
TAPE_R = ((174, 135), (137, 129), (136, 165))
TAPE_W = 9.5

SHADOW = f'<ellipse class="shadow" cx="103" cy="193.5" rx="36" ry="3.6" fill="{INK}" opacity=".12"/>'


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


def beak(kind="closed"):
    bx, by = BEAK_BASE
    s = f'fill="{BEAK}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"'
    if kind == "closed":
        inner = f'<path d="{BEAK_LO}" {s}/><path d="{BEAK_UP}" {s}/>'
    elif kind == "open":
        inner = (
            f'<path d="{BEAK_LO}" {s} transform="rotate(12 {bx} {by})"/>'
            f'<path d="{BEAK_UP}" {s} transform="rotate(-4 {bx} {by})"/>'
        )
    elif kind in ("down", "up"):
        a = 9 if kind == "down" else -8
        inner = f'<g transform="rotate({a} {bx} {by})"><path d="{BEAK_LO}" {s}/><path d="{BEAK_UP}" {s}/></g>'
    else:
        raise ValueError(kind)
    return f'<g class="beak">{inner}</g>'


def tape_piece(p, ink=INK, fill=TAPE, ticks=True):
    """One run of tape along a quadratic curve, with ticks and an end tab."""
    d = qd(p)
    x2, y2 = p[2]
    tx, ty = qtan(p, 1)
    ex, ey = x2 + tx * 6, y2 + ty * 6
    tab = f"M{f(x2)} {f(y2)} L{f(ex)} {f(ey)}"
    out = [
        f'<path d="{d}" fill="none" stroke="{ink}" stroke-width="{TAPE_W + SW2}"/>',
        f'<path d="{tab}" fill="none" stroke="{ink}" stroke-width="{TAPE_W + SW2}" stroke-linecap="round"/>',
        f'<path d="{d}" fill="none" stroke="{fill}" stroke-width="{TAPE_W}"/>',
        f'<path d="{tab}" fill="none" stroke="{METAL if fill == TAPE else fill}" stroke-width="{TAPE_W}"/>',
    ]
    if ticks:
        lines = []
        for k in range(18):
            t = 0.2 + k * 0.045
            if t > 0.97:
                break
            x, y = qpt(p, t)
            ux, uy = qtan(p, t)
            nx, ny = -uy, ux  # normal; start at one edge and go inward
            h = TAPE_W / 2
            ln = 4.2 if k % 2 == 0 else 2.6
            sx, sy = x + nx * h, y + ny * h
            lines.append(f"M{f(sx)} {f(sy)} L{f(sx - nx * ln)} {f(sy - ny * ln)}")
        out.append(f'<path d="{" ".join(lines)}" stroke="{ink}" stroke-width="1.8" stroke-linecap="round"/>')
    return "".join(out)


def tape(cid, pieces=(TAPE_L, TAPE_R)):
    return f'<g class="tape" clip-path="url(#{cid}-tape)">' + "".join(tape_piece(p) for p in pieces) + "</g>"


def clip_defs(cid):
    # body clip for cap and belly; tape clip = body plus the area under the chest,
    # so the free ends can hang a little past the outline
    return (
        f'<defs><clipPath id="{cid}"><path d="{BODY_PATH}"/></clipPath>'
        f'<clipPath id="{cid}-tape"><path d="{BODY_PATH}"/><rect x="80" y="150" width="80" height="50"/></clipPath></defs>'
    )


def feet():
    s = f'stroke="{INK}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    foot = "M{a} 181 L{b} 191 M{c} 193 L{b} 191 L{d} 192.5 M{b} 191 L{e} 195.5"
    return (
        f'<g class="feet"><path d="{foot.format(a=92, b=90, c=84, d=98, e=95)}" {s}/>'
        f'<path d="{foot.format(a=114, b=114, c=108, d=122, e=119)}" {s}/></g>'
    )


def bird(
    cid="fitz-body",
    eyes="open",
    brow=None,
    beak_kind="closed",
    blush=True,
    with_tape=True,
    pupils_class=True,
):
    e1 = eye(*EYE_NEAR, eyes)
    e2 = eye(*EYE_FAR, eyes, far=True)
    return (
        clip_defs(cid)
        + SHADOW
        + '<g class="bird">'
        + feet()
        + f'<g class="tail"><path d="{TAIL_PATH}" fill="{TAIL}" stroke="{INK}" stroke-width="{SW}" stroke-linejoin="round"/>'
        f'<path d="{TAIL_SPLIT}" fill="none" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/></g>'
        + '<g class="body">'
        + f'<path d="{BODY_PATH}" fill="{BODY}"/>'
        + f'<g clip-path="url(#{cid})"><path d="{CAP_PATH}" fill="{CAP}"/>'
        f'<ellipse cx="117" cy="164" rx="47" ry="33" fill="{BELLY}"/></g>'
        + (tape(cid) if with_tape else "")
        + f'<path d="{BODY_PATH}" fill="none" stroke="{INK}" stroke-width="{SW}"/>'
        + f'<g class="wing"><path d="{WING_PATH}" fill="{WING}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/></g>'
        + (
            f'<g class="blush" fill="{BLUSH}" opacity=".55"><ellipse cx="92" cy="130" rx="7.5" ry="4.2"/>'
            f'<ellipse cx="146" cy="127" rx="5" ry="3.6"/></g>'
            if blush
            else ""
        )
        + f'<g class="{"pupils" if pupils_class else "eyes"}">{e1}{e2}</g>'
        + brows(brow)
        + beak(beak_kind)
        + "</g></g>"
    )


# ---------------------------------------------------------------- accents
def sparks(cls="sparks"):
    s = f'stroke="{SPARK}" stroke-width="4.5" stroke-linecap="round"'
    return (
        f'<g class="{cls}">'
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
        f'<g class="{cls}"><g transform="translate(184 113) rotate(-2)">'
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


def strip(x0, length, y=106.5, h=9, cls="strip"):
    """A straight run of tape from the beak tip, with its hook end."""
    ticks = " ".join(
        f"M{f(x)} {f(y)} L{f(x)} {f(y + (5 if k % 2 == 0 else 3))}"
        for k, x in enumerate(range(x0 + 6, x0 + length - 3, 6))
    )
    xe = x0 + length
    return (
        f'<g class="{cls}">'
        f'<rect x="{x0 - 6}" y="{y}" width="{length + 6}" height="{h}" fill="{TAPE}" stroke="{INK}" stroke-width="{SW2}"/>'
        f'<path d="{ticks}" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M{xe} {f(y - 1)} L{xe + 4} {f(y - 1)} L{xe + 4} {f(y + h + 9)} L{xe} {f(y + h + 9)} Z" '
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
    "thinking": dict(eyes="look_up", brow="curious", extra=lambda: question(170, 54), tilt=-5),
    "surprised": dict(eyes="wide", brow="raised", beak_kind="open", extra=lambda: exclaim(), blush=False),
    "sorry": dict(eyes="look_down", brow="worried", beak_kind="down", extra=lambda: sweat(162, 70)),
    "proud": dict(
        eyes="proud",
        beak_kind="up",
        tilt=-4,
        extra=lambda: star(166, 50, 11) + star(184, 74, 6),
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
        "Fitz, the PickFit tailorbird: a round olive bird with a rufous cap, a short sharp beak, "
        "a wing on its side, its tail cocked up behind, and a tailor's measuring tape around its neck."
    )
    write("fitz.svg", doc(VIEW, bird(), "Fitz", desc))


def build_front():
    cid = "fitz-front-body"
    body = "M100 67 C 138 67, 165 92, 165 127 C 165 162, 136 185, 100 185 C 64 185, 35 162, 35 127 C 35 92, 62 67, 100 67 Z"
    cap = "M28 112 C 46 96, 74 90, 90 100 L100 106 L110 100 C 126 90, 154 96, 172 112 L172 40 L28 40 Z"
    tail = (
        f'<g transform="translate(-6 -2)"><path d="{TAIL_PATH}" fill="{TAIL}" stroke="{INK}" stroke-width="{SW}" stroke-linejoin="round"/>'
        f'<path d="{TAIL_SPLIT}" fill="none" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/></g>'
    )
    wing_l = "M50 133 C 61 140, 63 160, 52 172 C 44 179, 32 178, 22 176 C 32 166, 34 140, 50 133 Z"
    wing_r = "M150 133 C 139 140, 137 160, 148 172 C 156 179, 168 178, 178 176 C 168 166, 166 140, 150 133 Z"
    tl = ((26, 128), (82, 126), (84, 174))
    tr = ((174, 128), (118, 126), (116, 174))
    eyes = eye(76, 117, "open") + eye(124, 117, "open")
    bk = (
        f'<path d="M91 105 Q100 99 109 105 L101.6 127 Q100 130 98.4 127 Z" fill="{BEAK}" '
        f'stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/>'
    )
    blush = (
        f'<g fill="{BLUSH}" opacity=".55"><ellipse cx="66" cy="131" rx="7.5" ry="4.2"/>'
        f'<ellipse cx="134" cy="131" rx="7.5" ry="4.2"/></g>'
    )
    out = (
        f'<defs><clipPath id="{cid}"><path d="{body}"/></clipPath>'
        f'<clipPath id="{cid}-tape"><path d="{body}"/><rect x="60" y="150" width="80" height="50"/></clipPath></defs>'
        f"{SHADOW}{feet()}{tail}"
        f'<path d="{body}" fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="{cap}" fill="{CAP}"/>'
        f'<ellipse cx="100" cy="166" rx="48" ry="34" fill="{BELLY}"/></g>'
        f'<g clip-path="url(#{cid}-tape)">{tape_piece(tl)}{tape_piece(tr)}</g>'
        f'<path d="{body}" fill="none" stroke="{INK}" stroke-width="{SW}"/>'
        f'<path d="{wing_l}" fill="{WING}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/>'
        f'<path d="{wing_r}" fill="{WING}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/>'
        f"{blush}{eyes}{bk}"
    )
    write("fitz-front.svg", doc(VIEW, out, "Fitz, front view", "Fitz the tailorbird facing the viewer."))


# ------------------------------------------------ animated states
BIRD_PIVOT = "transform-box:fill-box;transform-origin:50% 100%;"
TAIL_PIVOT = ".tail{transform-box:fill-box;transform-origin:85% 95%}"
WING_PIVOT = ".wing{transform-box:fill-box;transform-origin:88% 12%}"
EYE_PIVOT = ".eye{transform-box:fill-box;transform-origin:50% 50%}"
PIVOTS = TAIL_PIVOT + WING_PIVOT + EYE_PIVOT


def build_states():
    # idle: blink, tail bob, breathing
    css = (
        PIVOTS
        + f".bird{{{BIRD_PIVOT}animation:breathe 4s ease-in-out infinite}}"
        ".tail{animation:bob 4s ease-in-out infinite}"
        ".eye{animation:blink 4s ease-in-out infinite}"
        "@keyframes breathe{0%,100%{transform:scale(1,1)}50%{transform:scale(1.012,.986)}}"
        "@keyframes bob{0%,55%,100%{transform:rotate(0)}64%{transform:rotate(-8deg)}74%{transform:rotate(4deg)}84%{transform:rotate(-2deg)}}"
        "@keyframes blink{0%,40%,48%,100%{transform:scaleY(1)}44%{transform:scaleY(.12)}}"
    )
    write("states/fitz-idle.svg", doc(VIEW, bird(), "Fitz, idle", "Fitz blinks and bobs its tail.", css))

    # searching: head tilts, looks left and right, dots
    css = (
        PIVOTS
        + f".bird{{{BIRD_PIVOT}animation:tilt 3.2s ease-in-out infinite}}"
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

    reel = '<defs><clipPath id="reel"><rect x="187" y="90" width="113" height="60"/></clipPath></defs>'

    # testing: tape runs from the beak across a package
    view = "0 0 300 200"
    css = (
        PIVOTS
        + ".tail{animation:bob 3.2s ease-in-out infinite}"
        ".wing{animation:brace 3.2s ease-in-out infinite}"
        ".strip{animation:pull 3.2s cubic-bezier(.5,0,.3,1) infinite}"
        ".eye{animation:blink 3.2s ease-in-out infinite}"
        ".edge{animation:edge 3.2s ease-in-out infinite}"
        "@keyframes bob{0%,100%{transform:rotate(0)}40%{transform:rotate(-5deg)}55%{transform:rotate(2deg)}}"
        "@keyframes brace{0%,100%{transform:rotate(0)}30%,70%{transform:rotate(-10deg)}}"
        "@keyframes pull{0%,8%{transform:translateX(-100px)}36%,72%{transform:translateX(0)}92%,100%{transform:translateX(-100px)}}"
        "@keyframes blink{0%,80%,88%,100%{transform:scaleY(1)}84%{transform:scaleY(.12)}}"
        "@keyframes edge{0%,34%,74%,100%{opacity:0}40%,68%{opacity:1}}"
    )
    body = (
        package()
        + reel
        + f'<g clip-path="url(#reel)">{strip(192, 92)}</g>'
        + f'<path class="edge" d="M292 100 L292 130" stroke="{GOOD}" stroke-width="3" stroke-linecap="round" stroke-dasharray="4 5"/>'
        + bird(brow="determined")
    )
    write("states/fitz-testing.svg", doc(view, body, "Fitz, testing",
                                         "Fitz pulls its measuring tape across a software package.", css))

    # test failed: tape comes up short, head shake, sorry face
    css = (
        PIVOTS
        + f".bird{{{BIRD_PIVOT}animation:shake 3.4s ease-in-out infinite}}"
        ".strip{animation:pull 3.4s cubic-bezier(.5,0,.3,1) infinite}"
        ".gap{animation:gap 3.4s ease-in-out infinite}"
        ".sweat{animation:drop 3.4s ease-in-out infinite}"
        ".wing{animation:droop 3.4s ease-in-out infinite}"
        "@keyframes pull{0%,6%{transform:translateX(-70px)}26%{transform:translateX(0)}30%{transform:translateX(-5px)}34%,52%{transform:translateX(0)}64%,100%{transform:translateX(-70px)}}"
        "@keyframes shake{0%,64%,90%,100%{transform:rotate(0)}68%{transform:rotate(-4deg)}74%{transform:rotate(4deg)}80%{transform:rotate(-3deg)}86%{transform:rotate(2deg)}}"
        "@keyframes gap{0%,30%,60%,100%{opacity:0}36%,54%{opacity:1}}"
        "@keyframes drop{0%,38%,94%,100%{opacity:0;transform:translateY(-4px)}46%,86%{opacity:1;transform:translateY(0)}}"
        "@keyframes droop{0%,36%,94%,100%{transform:rotate(0)}46%,86%{transform:rotate(8deg)}}"
    )
    gap = (
        f'<g class="gap" stroke="{BAD}" stroke-width="3" stroke-linecap="round" fill="none">'
        f'<path d="M260 96 L284 96" stroke-dasharray="3 5"/><path d="M260 91 L260 101 M284 91 L284 101"/>'
        f'<path d="M267 70 L277 80 M277 70 L267 80" stroke-width="3.5"/></g>'
    )
    body = (
        package()
        + reel
        + f'<g clip-path="url(#reel)">{strip(192, 62)}</g>'
        + gap
        + bird(eyes="look_down", brow="worried")
        + sweat(162, 66)
    )
    write("states/fitz-test-failed.svg", doc(view, body, "Fitz, test failed",
                                             "Fitz's tape comes up short of the package; it shakes its head, sorry.", css))

    # recommending: presents a stitched leaf, wing lifted toward it
    view = "0 0 270 200"
    css = (
        PIVOTS
        + f".offer{{{BIRD_PIVOT}animation:offer 2.6s ease-in-out infinite}}"
        ".tail{animation:bob 2.6s ease-in-out infinite}"
        ".wing{animation:lift 2.6s ease-in-out infinite}"
        ".star{transform-box:fill-box;transform-origin:50% 50%;animation:twinkle 2.6s ease-in-out infinite}"
        ".star.s2{animation-delay:.35s}.star.s3{animation-delay:.7s}"
        "@keyframes offer{0%,100%{transform:rotate(0) translateY(0)}35%,65%{transform:rotate(3deg) translateY(-3px)}}"
        "@keyframes bob{0%,100%{transform:rotate(0)}45%{transform:rotate(-7deg)}60%{transform:rotate(2deg)}}"
        "@keyframes lift{0%,100%{transform:rotate(0)}35%,65%{transform:rotate(-16deg)}}"
        "@keyframes twinkle{0%,100%{transform:scale(.55);opacity:.5}40%{transform:scale(1.1);opacity:1}}"
    )
    body = (
        '<g class="offer">' + bird(eyes="happy") + leaf() + "</g>"
        + star(236, 60, 9, "star") + star(258, 90, 6, "star s2") + star(212, 50, 5, "star s3")
    )
    write("states/fitz-recommending.svg", doc(view, body, "Fitz, recommending",
                                              "Fitz holds out a stitched leaf: this one fits.", css))

    # success: hop with a wing flap, sparkles and a check badge
    view = "0 0 220 200"
    css = (
        PIVOTS
        + f".bird{{{BIRD_PIVOT}animation:hop 1.8s cubic-bezier(.3,0,.4,1) infinite}}"
        ".tail{animation:flick 1.8s ease-in-out infinite}"
        ".wing{animation:flap 1.8s ease-in-out infinite}"
        ".badge{transform-box:fill-box;transform-origin:50% 50%;animation:pop 1.8s ease-out infinite}"
        ".sparks{animation:fade 1.8s ease-in-out infinite}"
        "@keyframes hop{0%,100%{transform:translateY(0) scale(1,1)}10%{transform:translateY(0) scale(1.05,.94)}"
        "35%{transform:translateY(-14px) scale(.97,1.04)}60%{transform:translateY(0) scale(1.04,.95)}72%{transform:translateY(0) scale(1,1)}}"
        "@keyframes flick{0%,100%{transform:rotate(0)}35%{transform:rotate(-10deg)}60%{transform:rotate(3deg)}}"
        "@keyframes flap{0%,70%,100%{transform:rotate(0)}22%{transform:rotate(-28deg)}36%{transform:rotate(-6deg)}48%{transform:rotate(-24deg)}}"
        "@keyframes pop{0%,100%{transform:scale(1)}30%{transform:scale(1.15)}45%{transform:scale(.96)}}"
        "@keyframes fade{0%,100%{opacity:.4}35%{opacity:1}}"
    )
    body = bird(eyes="happy") + sparks() + check_badge(196, 40)
    write("states/fitz-success.svg", doc(view, body, "Fitz, success",
                                         "Fitz hops and flaps a wing next to a green check.", css))


# ------------------------------------------------ icons
# Each size is drawn on its own grid. The "-dark" variants swap the brown
# outline for cream so the silhouette holds on dark backgrounds.
def icon_64(ink=INK, suffix=""):
    cid = "i64" + suffix
    body = "M35 18.5 C 48 18, 56.5 27.5, 56 39 C 55.5 50.5, 46 58, 34 58 C 21.5 58, 13 50.5, 13 40 C 13 28, 22.5 19, 35 18.5 Z"
    tl = ((10, 43), (34, 39.5), (35, 56))
    tr = ((60, 44), (46, 41.5), (46.5, 56))

    def piece(p):
        x2, y2 = p[2]
        return (
            f'<path d="{qd(p)} L{f(x2)} {f(y2 + 2.5)}" fill="none" stroke="{ink}" stroke-width="5"/>'
            f'<path d="{qd(p)}" fill="none" stroke="{TAPE}" stroke-width="3.2"/>'
            f'<path d="M{f(x2)} {f(y2)} L{f(x2)} {f(y2 + 2.5)}" stroke="{METAL}" stroke-width="3.2"/>'
        )

    s = (
        f'<defs><clipPath id="{cid}"><path d="{body}"/></clipPath>'
        f'<clipPath id="{cid}t"><path d="{body}"/><rect x="26" y="48" width="28" height="16"/></clipPath></defs>'
        f'<path d="M24 34 L15.5 41 C 11.5 35, 7 27, 4.5 20 Q 2.8 14.5 7 13 Q 11.2 11.5 13 16 C 15 22, 19 29, 24 34 Z" fill="{TAIL}" stroke="{ink}" stroke-width="2.4" stroke-linejoin="round"/>'
        f'<path d="{body}" fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="M19 17 C 21 26, 27 31, 35 31.5 C 42 32, 48 31, 52 32.5 C 54.5 33.5, 56 34.5, 60 35 L60 10 L19 10 Z" fill="{CAP}"/>'
        f'<ellipse cx="39" cy="53" rx="16" ry="11" fill="{BELLY}"/></g>'
        f'<g clip-path="url(#{cid}t)">{piece(tl)}{piece(tr)}</g>'
        f'<path d="{body}" fill="none" stroke="{ink}" stroke-width="2.4"/>'
        f'<path d="M28 44 C 31 48.5, 29.5 54, 23.5 55.5 C 19.5 56.5, 15 54.5, 9.5 51.5 C 14.5 49.5, 18.5 43.5, 28 44 Z" fill="{WING}" stroke="{ink}" stroke-width="1.6" stroke-linejoin="round"/>'
        f'<ellipse cx="34.5" cy="38" rx="2.5" ry="3" fill="{INK}"/><ellipse cx="45" cy="37" rx="2.2" ry="2.7" fill="{INK}"/>'
        f'<circle cx="33.8" cy="36.9" r=".9" fill="{WHITE}"/><circle cx="44.4" cy="35.9" r=".85" fill="{WHITE}"/>'
        f'<path d="M50.5 31.8 Q 57 32 62.5 35.6 Q 57 37.2 51.2 38.6 Q 49.2 35.2 50.5 31.8 Z" fill="{BEAK}" stroke="{ink}" stroke-width="1.4" stroke-linejoin="round"/>'
    )
    write(f"icons/fitz-64{suffix}.svg", doc("0 0 64 64", s, "Fitz icon", "Fitz the tailorbird, 64 px icon."))


def icon_32(ink=INK, suffix=""):
    cid = "i32" + suffix
    body = "M17 8.5 C 24 8.2, 28.5 13.2, 28.2 19.2 C 27.9 25.3, 23 29.5, 16.5 29.5 C 10 29.5, 5.5 25.5, 5.5 19.8 C 5.5 13.5, 10.5 8.8, 17 8.5 Z"
    s = (
        f'<defs><clipPath id="{cid}"><path d="{body}"/></clipPath></defs>'
        f'<path d="M11.5 15.5 L7.6 19.5 C 5.6 16.5, 3.6 12.5, 2.4 9 Q 1.6 6.2 3.7 5.5 Q 5.8 4.8 6.7 7 C 7.8 10, 9.4 13, 11.5 15.5 Z" fill="{TAIL}" stroke="{ink}" stroke-width="1.5" stroke-linejoin="round"/>'
        f'<path d="{body}" fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="M9 8 C 10 12.5, 13.5 15.2, 17.5 15.4 C 21 15.6, 24 15.2, 26 16 L31 17 L31 4 L9 4 Z" fill="{CAP}"/>'
        f'<ellipse cx="19" cy="27" rx="8.5" ry="5.6" fill="{BELLY}"/>'
        f'<path d="M4 21.5 Q 16.5 19.8 17 29" fill="none" stroke="{TAPE}" stroke-width="2.2"/>'
        f'<path d="M30 22.5 Q 23 21 23.2 29" fill="none" stroke="{TAPE}" stroke-width="2.2"/></g>'
        f'<path d="{body}" fill="none" stroke="{ink}" stroke-width="1.5"/>'
        f'<path d="M14 22.5 C 15.6 24.6, 14.8 27.3, 11.8 28 C 9.8 28.4, 7.6 27.4, 4.8 25.8 C 7.4 24.8, 9.2 22.2, 14 22.5 Z" fill="{WING}" stroke="{ink}" stroke-width="1" stroke-linejoin="round"/>'
        f'<ellipse cx="17.2" cy="19" rx="1.4" ry="1.75" fill="{INK}"/><ellipse cx="22.4" cy="18.4" rx="1.25" ry="1.6" fill="{INK}"/>'
        f'<path d="M25 15.3 Q 28.6 15.6 31.6 17.9 Q 28.6 18.9 25.3 19.6 Q 24.2 17.5 25 15.3 Z" fill="{BEAK}" stroke="{ink}" stroke-width=".9" stroke-linejoin="round"/>'
    )
    write(f"icons/fitz-32{suffix}.svg", doc("0 0 32 32", s, "Fitz icon", "Fitz the tailorbird, 32 px icon."))


def icon_16(ink=INK, suffix=""):
    cid = "i16" + suffix
    # edges sit on half pixels so the 1 px outline lands on whole pixels
    body_e = 'cx="8.5" cy="10.5" rx="5" ry="5"'
    s = (
        f'<defs><clipPath id="{cid}"><ellipse {body_e}/></clipPath></defs>'
        f'<path d="M6 8 L4 10.5 C 3 9, 1.8 6.5, 1.2 4.5 Q 0.8 2.6 2.2 2.2 Q 3.6 1.8 4.1 3.3 C 4.6 5, 5.2 6.6, 6 8 Z" fill="{TAIL}" stroke="{ink}" stroke-width="1" stroke-linejoin="round"/>'
        f'<ellipse {body_e} fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="M5 5 C 6 7.6, 8 8.6, 10 8.6 L 16 9 L16 0 L5 0 Z" fill="{CAP}"/>'
        f'<path d="M0 13.5 Q 9 15.2 16 12.5 L16 16 L0 16 Z" fill="{BELLY}"/></g>'
        f'<ellipse {body_e} fill="none" stroke="{ink}" stroke-width="1"/>'
        f'<rect x="9.5" y="9.5" width="1.8" height="2" rx=".5" fill="{INK}"/>'
        f'<path d="M12.2 8.4 L16 10.2 L12.6 11.6 Z" fill="{BEAK}"/>'
    )
    write(f"icons/fitz-16{suffix}.svg", doc("0 0 16 16", s, "Fitz icon", "Fitz the tailorbird, 16 px icon."))


def mono():
    """One-colour line version; uses currentColor so it can be recoloured."""
    cid = "mono-body"
    cc = "currentColor"
    hollow = "".join(  # tape as an outlined strip: knock the middle out with a mask
        f'<path d="{qd(p)}" stroke="#000" stroke-width="{TAPE_W - SW2 + 1}" fill="none"/>' for p in (TAPE_L, TAPE_R)
    )
    # Masks hide lines that would sit behind something: the tail behind the
    # body, the body edge and tape behind the wing, the beak's base inside it.
    m = f'maskUnits="userSpaceOnUse" x="-10" y="-10" width="220" height="220"'
    full = '<rect x="-10" y="-10" width="220" height="220" fill="#fff"/>'
    wing_hole = f'<path d="{WING_PATH}" fill="#000"/>'
    beak_hole = f'<path d="{BEAK_UP}" fill="#000"/><path d="{BEAK_LO}" fill="#000"/>'
    s = (
        f'<defs><clipPath id="{cid}"><path d="{BODY_PATH}"/></clipPath>'
        f'<clipPath id="{cid}-t"><path d="{BODY_PATH}"/><rect x="80" y="150" width="80" height="50"/></clipPath>'
        f'<mask id="{cid}-tape" {m}>{full}{hollow}{wing_hole}</mask>'
        f'<mask id="{cid}-out" {m}>{full}<path d="{BODY_PATH}" fill="#000"/></mask>'
        f'<mask id="{cid}-edge" {m}>{full}{wing_hole}{beak_hole}</mask></defs>'
        f'<g fill="none" stroke="{cc}" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round">'
        + feet().replace(INK, cc)
        + f'<path d="{TAIL_PATH}" mask="url(#{cid}-out)"/>'
        f'<path d="{BODY_PATH}" mask="url(#{cid}-edge)"/>'
        f'<path d="{WING_PATH}" stroke-width="{SW2}"/>'
        f'<g clip-path="url(#{cid})"><path d="{CAP_PATH}" fill="{cc}" stroke="none" mask="url(#{cid}-edge)"/></g>'
        f'<g clip-path="url(#{cid}-t)"><g mask="url(#{cid}-tape)">'
        + "".join(f'<path d="{qd(p)}" stroke-width="{TAPE_W + SW2}" stroke-linecap="butt"/>' for p in (TAPE_L, TAPE_R))
        + "</g></g></g>"
        f'<ellipse cx="{EYE_NEAR[0]}" cy="{EYE_NEAR[1]}" rx="6.8" ry="8.3" fill="{cc}"/>'
        f'<ellipse cx="{EYE_FAR[0]}" cy="{EYE_FAR[1]}" rx="6" ry="7.6" fill="{cc}"/>'
        f'<g fill="none" stroke="{cc}" stroke-width="{SW2}" stroke-linejoin="round"><path d="{BEAK_UP}"/><path d="{BEAK_LO}"/></g>'
    )
    write("fitz-mono.svg", doc(VIEW, s, "Fitz, one colour", "Fitz the tailorbird as a one-colour line drawing."))
    # 32 px mono icon: outlined body, solid cap, tail, eye and beak
    body = "M17 8.5 C 24 8.2, 28.5 13.2, 28.2 19.2 C 27.9 25.3, 23 29.5, 16.5 29.5 C 10 29.5, 5.5 25.5, 5.5 19.8 C 5.5 13.5, 10.5 8.8, 17 8.5 Z"
    s = (
        f'<defs><clipPath id="m32"><path d="{body}"/></clipPath></defs>'
        f'<g fill="{cc}">'
        '<path d="M11.5 15.5 L7.6 19.5 C 5.6 16.5, 3.6 12.5, 2.4 9 Q 1.6 6.2 3.7 5.5 Q 5.8 4.8 6.7 7 C 7.8 10, 9.4 13, 11.5 15.5 Z"/>'
        '<path clip-path="url(#m32)" d="M9 8 C 10 12.5, 13.5 15.2, 17.5 15.4 C 21 15.6, 24 15.2, 26 16 L31 17 L31 4 L9 4 Z"/>'
        '<ellipse cx="17.2" cy="19.4" rx="1.4" ry="1.75"/><ellipse cx="22.4" cy="18.8" rx="1.25" ry="1.6"/>'
        '<path d="M25 15.3 Q 28.6 15.6 31.6 17.9 Q 28.6 18.9 25.3 19.6 Q 24.2 17.5 25 15.3 Z"/></g>'
        f'<g fill="none" stroke="{cc}" stroke-linejoin="round"><path d="{body}" stroke-width="2"/>'
        '<path d="M14 22.5 C 15.6 24.6, 14.8 27.3, 11.8 28 C 9.8 28.4, 7.6 27.4, 4.8 25.8 C 7.4 24.8, 9.2 22.2, 14 22.5 Z" stroke-width="1.3"/></g>'
    )
    write("icons/fitz-mono-32.svg", doc("0 0 32 32", s, "Fitz icon, one colour", "Fitz silhouette, one colour."))


if __name__ == "__main__":
    build_main()
    build_front()
    build_expressions()
    build_states()
    for ink, suffix in ((INK, ""), (BELLY, "-dark")):
        icon_64(ink, suffix)
        icon_32(ink, suffix)
        icon_16(ink, suffix)
    mono()
