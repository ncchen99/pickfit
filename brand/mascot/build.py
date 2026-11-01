#!/usr/bin/env python3
"""Build the Fitz mascot SVGs from one set of shapes and one palette.

Every file in brand/mascot/ except README.md, index.html and this script is
written by this script, so palette and line weight stay the same everywhere.

    python3 brand/mascot/build.py

Version 2: front-facing face with a short orange beak centred just below the
eyes, the tail sweeping up from behind the body, wings on both sides, and the
measuring tape draped around the neck with both ends hanging in front.
`fx` turns the face a little to the right (eyes, beak, cap point and tape
shift together) for states where Fitz looks at something beside it.
"""

from __future__ import annotations

import math
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------- palette
INK = "#4A2E22"  # outlines, eyes
BODY = "#A9BC4C"  # olive yellow-green
WING = "#869E3A"  # darker olive: wings
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
# One chubby head-body mass.
BODY_PATH = (
    "M100 67 C 138 67, 165 92, 165 127 C 165 162, 136 185, 100 185 "
    "C 64 185, 35 162, 35 127 C 35 92, 62 67, 100 67 Z"
)
EYE_Y = 117
EYE_DX = 24  # half the distance between the eyes

# Tail: grows from behind the body and sweeps up and back past the left shoulder.
TAIL_PATH = (
    "M68 102 L42 120 C 33 105, 22 88, 15 71 Q 10 56 22 51.5 Q 34 47.5 38.5 61 "
    "C 43 76, 54 90, 68 102 Z"
)
TAIL_SPLIT = "M22.5 53 Q 25 58 27 64"

# Wings: teardrops hanging at the sides, tips pointing down and out.
WING_L = "M50 133 C 61 140, 63 160, 52 172 C 44 179, 32 178, 22 176 C 32 166, 34 140, 50 133 Z"
WING_R = "M150 133 C 139 140, 137 160, 148 172 C 156 179, 168 178, 178 176 C 168 166, 166 140, 150 133 Z"

TAPE_W = 9.5

SHADOW = f'<ellipse class="shadow" cx="100" cy="193.5" rx="40" ry="3.6" fill="{INK}" opacity=".12"/>'


def cap_path(fx=0):
    """Rufous cap over the crown; its front point comes down between the eyes to the beak."""
    c = 100 + fx
    return (
        f"M28 112 C 46 96, {74 + fx} 90, {c - 10} 100 L{c} 108.5 L{c + 10} 100 "
        f"C {126 + fx} 90, 154 96, 172 112 L172 40 L28 40 Z"
    )


def tape_pieces(fx=0):
    s = fx * 0.5
    return (
        ((26, 128), (80 + s, 126), (83 + s, 172)),
        ((174, 128), (120 + s, 126), (117 + s, 172)),
    )


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
def eye(cx, cy, kind, small=False):
    """One eye, wrapped in <g class="eye"> so it can blink."""
    rx, ry = (6, 7.6) if small else (6.8, 8.3)
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


# (left brow, right brow) as points relative to each eye centre:
# two points = straight line, three = start, control, end of a curve.
BROWS = {
    "worried": (((-8, -12), (6, -16.5)), ((-6, -16.5), (8, -12))),
    "raised": (((-7.5, -15), (0, -21), (7.5, -15)), ((-7.5, -15), (0, -21), (7.5, -15))),
    "curious": (((-7, -14.5), (6, -15)), ((-6.5, -17), (0, -24), (6.5, -17))),
    "determined": (((-7.5, -17), (6, -13)), ((-6, -13), (7.5, -17))),
}


def _brow(pts, at):
    x, y = at
    p = [(x + a, y + b) for a, b in pts]
    if len(p) == 2:
        return f"M{f(p[0][0])} {f(p[0][1])} L{f(p[1][0])} {f(p[1][1])}"
    return f"M{f(p[0][0])} {f(p[0][1])} Q{f(p[1][0])} {f(p[1][1])} {f(p[2][0])} {f(p[2][1])}"


def brows(kind, left, right):
    if not kind:
        return ""
    a, b = BROWS[kind]
    s = f'stroke="{INK}" stroke-width="3.5" stroke-linecap="round" fill="none"'
    return f'<g class="brows"><path d="{_brow(a, left)}" {s}/><path d="{_brow(b, right)}" {s}/></g>'


def beak(kind="closed", fx=0):
    """Short triangle centred between the eyes, just below them, pointing down."""
    c = 100 + fx
    lean = fx * 0.5  # the tip follows the turn of the face
    s = f'fill="{BEAK}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"'
    tip = f"L{f(c + 2 + lean)} 134.5 Q{f(c + lean)} 138 {f(c - 2 + lean)} 134.5 Z"
    if kind == "closed":
        inner = f'<path d="M{f(c - 10)} 112.5 Q{f(c)} 107.5 {f(c + 10)} 112.5 {tip}" {s}/>'
    elif kind == "up":  # chin up: the beak looks shorter
        inner = f'<path d="M{f(c - 10)} 112 Q{f(c)} 107 {f(c + 10)} 112 L{f(c + 1.5)} 127 Q{f(c)} 129.5 {f(c - 1.5)} 127 Z" {s}/>'
    elif kind == "open":  # upper beak, dark mouth, small lower beak
        inner = (
            f'<ellipse cx="{f(c)}" cy="129" rx="7" ry="7" fill="{INK}"/>'
            f'<path d="M{f(c - 6.5)} 132.5 Q{f(c)} 130 {f(c + 6.5)} 132.5 L{f(c + 1)} 141 Q{f(c)} 142.5 {f(c - 1)} 141 Z" {s}/>'
            f'<path d="M{f(c - 10)} 112 Q{f(c)} 107 {f(c + 10)} 112 L{f(c + 1.5)} 126.5 Q{f(c)} 129 {f(c - 1.5)} 126.5 Z" {s}/>'
        )
    else:
        raise ValueError(kind)
    return f'<g class="beak">{inner}</g>'


def tape_piece(p, ink=INK):
    """One run of tape along a quadratic curve, with ticks and an end tab."""
    d = qd(p)
    x2, y2 = p[2]
    tx, ty = qtan(p, 1)
    ex, ey = x2 + tx * 6, y2 + ty * 6
    tab = f"M{f(x2)} {f(y2)} L{f(ex)} {f(ey)}"
    lines = []
    for k in range(18):
        t = 0.2 + k * 0.045
        if t > 0.97:
            break
        x, y = qpt(p, t)
        ux, uy = qtan(p, t)
        nx, ny = -uy, ux
        h = TAPE_W / 2
        ln = 4.2 if k % 2 == 0 else 2.6
        sx, sy = x + nx * h, y + ny * h
        lines.append(f"M{f(sx)} {f(sy)} L{f(sx - nx * ln)} {f(sy - ny * ln)}")
    return (
        f'<path d="{d}" fill="none" stroke="{ink}" stroke-width="{TAPE_W + SW2}"/>'
        f'<path d="{tab}" fill="none" stroke="{ink}" stroke-width="{TAPE_W + SW2}" stroke-linecap="round"/>'
        f'<path d="{d}" fill="none" stroke="{TAPE}" stroke-width="{TAPE_W}"/>'
        f'<path d="{tab}" fill="none" stroke="{METAL}" stroke-width="{TAPE_W}"/>'
        f'<path d="{" ".join(lines)}" stroke="{ink}" stroke-width="1.8" stroke-linecap="round"/>'
    )


def clip_defs(cid):
    # body clip for cap and belly; tape clip = body plus the area under the chest,
    # so the free ends can hang a little past the outline
    return (
        f'<defs><clipPath id="{cid}"><path d="{BODY_PATH}"/></clipPath>'
        f'<clipPath id="{cid}-tape"><path d="{BODY_PATH}"/><rect x="60" y="150" width="80" height="50"/></clipPath></defs>'
    )


def feet():
    s = f'stroke="{INK}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    foot = "M{x} 181 L{x} 190.5 M{a} 193.5 L{x} 190.5 L{b} 193.5 M{x} 190.5 L{x} 195"
    return (
        f'<g class="feet"><path d="{foot.format(x=88, a=82, b=94)}" {s}/>'
        f'<path d="{foot.format(x=112, a=106, b=118)}" {s}/></g>'
    )


def tail():
    return (
        f'<g class="tail"><path d="{TAIL_PATH}" fill="{TAIL}" stroke="{INK}" stroke-width="{SW}" stroke-linejoin="round"/>'
        f'<path d="{TAIL_SPLIT}" fill="none" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/></g>'
    )


def bird(cid="fitz-body", eyes="open", brow=None, beak_kind="closed", blush=True, fx=0):
    left = (100 + fx - EYE_DX, EYE_Y)
    right = (100 + fx + EYE_DX, EYE_Y)
    e = eye(*left, eyes) + eye(*right, eyes, small=fx > 0)
    w = f'fill="{WING}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"'
    return (
        clip_defs(cid)
        + SHADOW
        + '<g class="bird">'
        + feet()
        + tail()
        + '<g class="body">'
        + f'<path d="{BODY_PATH}" fill="{BODY}"/>'
        + f'<g clip-path="url(#{cid})"><path d="{cap_path(fx)}" fill="{CAP}"/>'
        f'<ellipse cx="{100 + fx * 0.4}" cy="166" rx="48" ry="34" fill="{BELLY}"/></g>'
        + f'<g class="tape" clip-path="url(#{cid}-tape)">'
        + "".join(tape_piece(p) for p in tape_pieces(fx))
        + "</g>"
        + f'<path d="{BODY_PATH}" fill="none" stroke="{INK}" stroke-width="{SW}"/>'
        + f'<g class="wing l"><path d="{WING_L}" {w}/></g><g class="wing r"><path d="{WING_R}" {w}/></g>'
        + (
            f'<g class="blush" fill="{BLUSH}" opacity=".55">'
            f'<ellipse cx="{f(left[0] - 9)}" cy="128" rx="7.5" ry="4.2"/>'
            f'<ellipse cx="{f(right[0] + 9 - fx * 0.3)}" cy="128" rx="{7.5 - fx * 0.15}" ry="4.2"/></g>'
            if blush
            else ""
        )
        + f'<g class="pupils">{e}</g>'
        + brows(brow, left, right)
        + beak(beak_kind, fx)
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
def leaf(x, y, cls="leaf"):
    """A stitched leaf held at the beak tip: what Fitz presents."""
    shape = "M0 0 C 10 -24, 44 -32, 66 -22 C 54 -2, 26 10, 0 0 Z"
    rib = "M2 -1 Q 30 -11 62 -21"
    stitches = " ".join(
        f"M{f(sx - 3)} {f(sy - 4)} L{f(sx + 3)} {f(sy + 4)}"
        for sx, sy in [(18, -6.5), (30, -10.5), (42, -14.3), (53, -17.5)]
    )
    return (
        f'<g class="{cls}"><g transform="translate({x} {y}) rotate(22)">'
        f'<path d="{shape}" fill="{LEAF}" stroke="{INK}" stroke-width="{SW2}" stroke-linejoin="round"/>'
        f'<path d="{rib}" fill="none" stroke="{LEAF_DARK}" stroke-width="2.4" stroke-linecap="round"/>'
        f'<path d="{stitches}" stroke="{BELLY}" stroke-width="2.4" stroke-linecap="round"/>'
        f"</g></g>"
    )


def package(x=212, y=150, w=72, h=42):
    """A software package: a box with </> on it."""
    cx = x + w / 2
    my = y + h / 2 + 5
    return (
        f'<g class="package">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{BOX}" stroke="{INK}" stroke-width="{SW}"/>'
        f'<path d="M{x + 2} {y + 12} L{x + w - 2} {y + 12}" stroke="{BOX_DARK}" stroke-width="{SW2}"/>'
        f'<path d="M{f(cx - 10)} {f(my - 6)} L{f(cx - 16)} {f(my)} L{f(cx - 10)} {f(my + 6)} '
        f'M{f(cx + 10)} {f(my - 6)} L{f(cx + 16)} {f(my)} L{f(cx + 10)} {f(my + 6)} '
        f'M{f(cx + 3)} {f(my - 8)} L{f(cx - 3)} {f(my + 8)}" fill="none" stroke="{INK}" stroke-width="{SW2}" '
        f'stroke-linecap="round" stroke-linejoin="round"/></g>'
    )


def strip(x0, length, y=133, h=9, cls="strip"):
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
        f'<path d="M{xe} {f(y - 1)} L{xe + 4} {f(y - 1)} L{xe + 4} {f(y + h + 8)} L{xe} {f(y + h + 8)} Z" '
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
    "thinking": dict(eyes="look_up", brow="curious", extra=lambda: question(172, 52), tilt=-6),
    "surprised": dict(eyes="wide", brow="raised", beak_kind="open", extra=lambda: exclaim(), blush=False),
    "sorry": dict(eyes="look_down", brow="worried", extra=lambda: sweat(160, 72)),
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
            b = f'<g transform="rotate({o["tilt"]} 100 192)">{b}</g>'
        extra = o["extra"]() if "extra" in o else ""
        write(
            f"expressions/fitz-{name}.svg",
            doc(VIEW, b + extra, f"Fitz, {name}", f"Fitz the tailorbird, {name} expression."),
        )


def build_main():
    desc = (
        "Fitz, the PickFit tailorbird: a round olive bird with a rufous cap, a short orange beak "
        "between its eyes, wings at its sides, its tail cocked up behind, and a tailor's measuring "
        "tape around its neck."
    )
    write("fitz.svg", doc(VIEW, bird(), "Fitz", desc))
    write("fitz-turn.svg", doc(VIEW, bird(cid="fitz-turn", fx=10), "Fitz, turned",
                               "Fitz with its face turned a little to the right, toward what it is showing."))


# ------------------------------------------------ animated states
BIRD_PIVOT = "transform-box:fill-box;transform-origin:50% 100%;"
PIVOTS = (
    ".tail{transform-box:fill-box;transform-origin:90% 92%}"
    ".wing{transform-box:fill-box}.wing.l{transform-origin:68% 4%}.wing.r{transform-origin:32% 4%}"
    ".eye{transform-box:fill-box;transform-origin:50% 50%}"
)


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
    dots = "".join(f'<circle class="dot" cx="{x}" cy="56" r="4.5" fill="{CAP}"/>' for x in (160, 174, 188))
    write(
        "states/fitz-searching.svg",
        doc(VIEW, bird(brow="curious") + f"<g>{dots}</g>", "Fitz, searching",
            "Fitz tilts its head and looks left and right while searching.", css),
    )

    # The tape runs from the beak tip across the chest to a package on the right.
    fx = 10
    tip_x = 100 + fx + fx * 0.5
    x0 = int(tip_x) + 2
    reel = f'<defs><clipPath id="reel"><rect x="{x0 - 3}" y="110" width="{300 - x0}" height="60"/></clipPath></defs>'

    # testing: tape runs from the beak across a package
    view = "0 0 300 200"
    full = 284 - x0
    css = (
        PIVOTS
        + ".tail{animation:bob 3.2s ease-in-out infinite}"
        ".wing.r{animation:brace 3.2s ease-in-out infinite}"
        ".strip{animation:pull 3.2s cubic-bezier(.5,0,.3,1) infinite}"
        ".eye{animation:blink 3.2s ease-in-out infinite}"
        ".edge{animation:edge 3.2s ease-in-out infinite}"
        "@keyframes bob{0%,100%{transform:rotate(0)}40%{transform:rotate(-5deg)}55%{transform:rotate(2deg)}}"
        "@keyframes brace{0%,100%{transform:rotate(0)}30%,70%{transform:rotate(-12deg)}}"
        f"@keyframes pull{{0%,8%{{transform:translateX(-{full + 8}px)}}36%,72%{{transform:translateX(0)}}92%,100%{{transform:translateX(-{full + 8}px)}}}}"
        "@keyframes blink{0%,80%,88%,100%{transform:scaleY(1)}84%{transform:scaleY(.12)}}"
        "@keyframes edge{0%,34%,74%,100%{opacity:0}40%,68%{opacity:1}}"
    )
    body = (
        package()
        + bird(cid="fitz-test", brow="determined", fx=fx)
        + reel
        + f'<g clip-path="url(#reel)">{strip(x0, full)}</g>'
        + beak("closed", fx)  # beak again on top: it holds the tape end
        + f'<path class="edge" d="M293 122 L293 152" stroke="{GOOD}" stroke-width="3" stroke-linecap="round" stroke-dasharray="4 5"/>'
    )
    write("states/fitz-testing.svg", doc(view, body, "Fitz, testing",
                                         "Fitz pulls its measuring tape from its beak across a software package.", css))

    # test failed: tape comes up short, head shake, sorry face
    short = 254 - x0
    css = (
        PIVOTS
        + f".shake{{{BIRD_PIVOT}animation:shake 3.4s ease-in-out infinite}}"
        ".strip{animation:pull 3.4s cubic-bezier(.5,0,.3,1) infinite}"
        ".gap{animation:gap 3.4s ease-in-out infinite}"
        ".sweat{animation:drop 3.4s ease-in-out infinite}"
        ".wing{animation:droop 3.4s ease-in-out infinite}"
        f"@keyframes pull{{0%,6%{{transform:translateX(-{short + 8}px)}}26%{{transform:translateX(0)}}30%{{transform:translateX(-5px)}}"
        f"34%,52%{{transform:translateX(0)}}64%,100%{{transform:translateX(-{short + 8}px)}}}}"
        "@keyframes shake{0%,64%,90%,100%{transform:rotate(0)}68%{transform:rotate(-4deg)}74%{transform:rotate(4deg)}80%{transform:rotate(-3deg)}86%{transform:rotate(2deg)}}"
        "@keyframes gap{0%,30%,60%,100%{opacity:0}36%,54%{opacity:1}}"
        "@keyframes drop{0%,38%,94%,100%{opacity:0;transform:translateY(-4px)}46%,86%{opacity:1;transform:translateY(0)}}"
        "@keyframes droop{0%,36%,94%,100%{transform:rotate(0)}46%,86%{transform:rotate(6deg)}}"
        ".wing.r{animation-name:droopr}@keyframes droopr{0%,36%,94%,100%{transform:rotate(0)}46%,86%{transform:rotate(-6deg)}}"
    )
    gap = (
        f'<g class="gap" stroke="{BAD}" stroke-width="3" stroke-linecap="round" fill="none">'
        f'<path d="M261 122 L284 122" stroke-dasharray="3 5"/><path d="M261 117 L261 127 M284 117 L284 127"/>'
        f'<path d="M268 97 L278 107 M278 97 L268 107" stroke-width="3.5"/></g>'
    )
    body = (
        package()
        + '<g class="shake">' + bird(cid="fitz-fail", eyes="look_down", brow="worried", fx=fx)
        + reel + f'<g clip-path="url(#reel)">{strip(x0, short)}</g>' + beak("closed", fx) + "</g>"
        + gap
        + sweat(160, 70)
    )
    write("states/fitz-test-failed.svg", doc(view, body, "Fitz, test failed",
                                             "Fitz's tape comes up short of the package; it shakes its head, sorry.", css))

    # recommending: presents a stitched leaf, right wing lifted toward it
    view = "0 0 250 200"
    css = (
        PIVOTS
        + f".offer{{{BIRD_PIVOT}animation:offer 2.6s ease-in-out infinite}}"
        ".tail{animation:bob 2.6s ease-in-out infinite}"
        ".wing.r{animation:lift 2.6s ease-in-out infinite}"
        ".star{transform-box:fill-box;transform-origin:50% 50%;animation:twinkle 2.6s ease-in-out infinite}"
        ".star.s2{animation-delay:.35s}.star.s3{animation-delay:.7s}"
        "@keyframes offer{0%,100%{transform:rotate(0) translateY(0)}35%,65%{transform:rotate(3deg) translateY(-3px)}}"
        "@keyframes bob{0%,100%{transform:rotate(0)}45%{transform:rotate(-7deg)}60%{transform:rotate(2deg)}}"
        "@keyframes lift{0%,100%{transform:rotate(0)}35%,65%{transform:rotate(-22deg)}}"
        "@keyframes twinkle{0%,100%{transform:scale(.55);opacity:.5}40%{transform:scale(1.1);opacity:1}}"
    )
    body = (
        '<g class="offer">' + bird(cid="fitz-rec", eyes="happy", fx=fx) + leaf(tip_x - 3, 135) + beak("closed", fx) + "</g>"
        + star(206, 86, 9, "star") + star(230, 112, 6, "star s2") + star(186, 70, 5, "star s3")
    )
    write("states/fitz-recommending.svg", doc(view, body, "Fitz, recommending",
                                              "Fitz holds out a stitched leaf: this one fits.", css))

    # success: hop with both wings up, sparkles and a check badge
    view = "0 0 210 200"
    css = (
        PIVOTS
        + f".bird{{{BIRD_PIVOT}animation:hop 1.8s cubic-bezier(.3,0,.4,1) infinite}}"
        ".tail{animation:flick 1.8s ease-in-out infinite}"
        ".wing.l{animation:flapl 1.8s ease-in-out infinite}.wing.r{animation:flapr 1.8s ease-in-out infinite}"
        ".badge{transform-box:fill-box;transform-origin:50% 50%;animation:pop 1.8s ease-out infinite}"
        ".sparks{animation:fade 1.8s ease-in-out infinite}"
        "@keyframes hop{0%,100%{transform:translateY(0) scale(1,1)}10%{transform:translateY(0) scale(1.05,.94)}"
        "35%{transform:translateY(-14px) scale(.97,1.04)}60%{transform:translateY(0) scale(1.04,.95)}72%{transform:translateY(0) scale(1,1)}}"
        "@keyframes flick{0%,100%{transform:rotate(0)}35%{transform:rotate(-10deg)}60%{transform:rotate(3deg)}}"
        "@keyframes flapl{0%,70%,100%{transform:rotate(0)}22%{transform:rotate(30deg)}36%{transform:rotate(8deg)}48%{transform:rotate(26deg)}}"
        "@keyframes flapr{0%,70%,100%{transform:rotate(0)}22%{transform:rotate(-30deg)}36%{transform:rotate(-8deg)}48%{transform:rotate(-26deg)}}"
        "@keyframes pop{0%,100%{transform:scale(1)}30%{transform:scale(1.15)}45%{transform:scale(.96)}}"
        "@keyframes fade{0%,100%{opacity:.4}35%{opacity:1}}"
    )
    body = bird(eyes="happy") + sparks() + check_badge(190, 36)
    write("states/fitz-success.svg", doc(view, body, "Fitz, success",
                                         "Fitz hops and flaps its wings next to a green check.", css))


# ------------------------------------------------ icons
# Each size is drawn on its own grid. The "-dark" variants swap the brown
# outline for cream so the silhouette holds on dark backgrounds.
I64_BODY = "M32 19 C 46 19, 55 28, 55 40 C 55 51, 45 58, 32 58 C 19 58, 9 51, 9 40 C 9 28, 18 19, 32 19 Z"
I64_TAIL = "M24 30 L14 36 C 10 29, 6 21, 4 15 Q 3 9.5 7.5 8.5 Q 12 7.5 13.5 12 C 15.5 18, 19 25, 24 30 Z"
I32_BODY = "M16 9 C 23.5 9, 28 14, 28 20 C 28 25.8, 23 29.5, 16 29.5 C 9 29.5, 4 25.8, 4 20 C 4 14, 8.5 9, 16 9 Z"
I32_TAIL = "M12 15 L7.5 18.5 C 5.5 15, 3.5 11, 2.5 8 Q 2 5.2 4.2 4.7 Q 6.4 4.2 7.2 6.5 C 8.2 9.5, 9.8 12.5, 12 15 Z"
I32_CAP = "M3 19 C 6 16, 10 14.5, 13.5 16.2 L16 17.8 L18.5 16.2 C 22 14.5, 26 16, 29 19 L29 5 L3 5 Z"
I32_BEAK = "M14.2 18.6 Q16 17.6 17.8 18.6 L16.4 23.2 Q16 23.9 15.6 23.2 Z"


def icon_64(ink=INK, suffix=""):
    cid = "i64" + suffix

    def piece(p):
        x2, y2 = p[2]
        return (
            f'<path d="{qd(p)} L{f(x2)} {f(y2 + 2.5)}" fill="none" stroke="{ink}" stroke-width="5"/>'
            f'<path d="{qd(p)}" fill="none" stroke="{TAPE}" stroke-width="3.2"/>'
            f'<path d="M{f(x2)} {f(y2)} L{f(x2)} {f(y2 + 2.5)}" stroke="{METAL}" stroke-width="3.2"/>'
        )

    w = f'fill="{WING}" stroke="{ink}" stroke-width="1.6" stroke-linejoin="round"'
    s = (
        f'<defs><clipPath id="{cid}"><path d="{I64_BODY}"/></clipPath>'
        f'<clipPath id="{cid}t"><path d="{I64_BODY}"/><rect x="18" y="48" width="28" height="16"/></clipPath></defs>'
        f'<path d="{I64_TAIL}" fill="{TAIL}" stroke="{ink}" stroke-width="2.4" stroke-linejoin="round"/>'
        f'<path d="{I64_BODY}" fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="M6 37 C 12 31, 20 28, 27 31.5 L32 34.5 L37 31.5 C 44 28, 52 31, 58 37 L58 12 L6 12 Z" fill="{CAP}"/>'
        f'<ellipse cx="32" cy="54" rx="15" ry="10" fill="{BELLY}"/></g>'
        f'<g clip-path="url(#{cid}t)">{piece(((7, 42), (25, 41.5), (26.5, 55)))}{piece(((57, 42), (39, 41.5), (37.5, 55)))}</g>'
        f'<path d="{I64_BODY}" fill="none" stroke="{ink}" stroke-width="2.4"/>'
        f'<path d="M15.5 43 C 19.5 45, 20 52, 16.5 55.5 C 14 58, 10 57.5, 6.5 57 C 9.5 53.5, 10.5 45, 15.5 43 Z" {w}/>'
        f'<path d="M48.5 43 C 44.5 45, 44 52, 47.5 55.5 C 50 58, 54 57.5, 57.5 57 C 54.5 53.5, 53.5 45, 48.5 43 Z" {w}/>'
        f'<ellipse cx="24" cy="38.5" rx="2.6" ry="3.1" fill="{INK}"/><ellipse cx="40" cy="38.5" rx="2.6" ry="3.1" fill="{INK}"/>'
        f'<circle cx="23.2" cy="37.3" r=".95" fill="{WHITE}"/><circle cx="39.2" cy="37.3" r=".95" fill="{WHITE}"/>'
        f'<path d="M28.5 36.6 Q32 34.8 35.5 36.6 L32.7 45 Q32 46.2 31.3 45 Z" fill="{BEAK}" stroke="{ink}" stroke-width="1.4" stroke-linejoin="round"/>'
    )
    write(f"icons/fitz-64{suffix}.svg", doc("0 0 64 64", s, "Fitz icon", "Fitz the tailorbird, 64 px icon."))


def icon_32(ink=INK, suffix=""):
    cid = "i32" + suffix
    w = f'fill="{WING}" stroke="{ink}" stroke-width="1" stroke-linejoin="round"'
    s = (
        f'<defs><clipPath id="{cid}"><path d="{I32_BODY}"/></clipPath></defs>'
        f'<path d="{I32_TAIL}" fill="{TAIL}" stroke="{ink}" stroke-width="1.5" stroke-linejoin="round"/>'
        f'<path d="{I32_BODY}" fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="{I32_CAP}" fill="{CAP}"/>'
        f'<ellipse cx="16" cy="27.5" rx="8" ry="5" fill="{BELLY}"/>'
        f'<path d="M3 21.6 Q 11.5 21.2 12.5 29.5" fill="none" stroke="{TAPE}" stroke-width="2.2"/>'
        f'<path d="M29 21.6 Q 20.5 21.2 19.5 29.5" fill="none" stroke="{TAPE}" stroke-width="2.2"/></g>'
        f'<path d="{I32_BODY}" fill="none" stroke="{ink}" stroke-width="1.5"/>'
        f'<path d="M8 22.5 C 10 23.5, 10.2 26.8, 8.5 28.2 C 7.3 29.2, 5.3 29, 3.4 28.6 C 5 26.8, 5.5 23.2, 8 22.5 Z" {w}/>'
        f'<path d="M24 22.5 C 22 23.5, 21.8 26.8, 23.5 28.2 C 24.7 29.2, 26.7 29, 28.6 28.6 C 27 26.8, 26.5 23.2, 24 22.5 Z" {w}/>'
        f'<ellipse cx="12" cy="19.4" rx="1.4" ry="1.75" fill="{INK}"/><ellipse cx="20" cy="19.4" rx="1.4" ry="1.75" fill="{INK}"/>'
        f'<path d="{I32_BEAK}" fill="{BEAK}" stroke="{ink}" stroke-width=".9" stroke-linejoin="round"/>'
    )
    write(f"icons/fitz-32{suffix}.svg", doc("0 0 32 32", s, "Fitz icon", "Fitz the tailorbird, 32 px icon."))


def icon_16(ink=INK, suffix=""):
    cid = "i16" + suffix
    # edges sit on half pixels so the 1 px outline lands on whole pixels
    body_e = 'cx="8.5" cy="10.5" rx="5" ry="5"'
    s = (
        f'<defs><clipPath id="{cid}"><ellipse {body_e}/></clipPath></defs>'
        f'<path d="M6.5 7.5 L4.5 10 C 3.4 8.4, 2.2 6, 1.6 4.2 Q 1.2 2.4 2.6 2 Q 4 1.6 4.5 3 C 5.1 4.6, 5.7 6.2, 6.5 7.5 Z" fill="{TAIL}" stroke="{ink}" stroke-width="1" stroke-linejoin="round"/>'
        f'<ellipse {body_e} fill="{BODY}"/>'
        f'<g clip-path="url(#{cid})"><path d="M0 9.4 C 3 7.6, 6 7.2, 8.5 8.6 C 11 7.2, 14 7.6, 17 9.4 L17 0 L0 0 Z" fill="{CAP}"/>'
        f'<path d="M0 13.8 Q 8.5 15.8 17 13.8 L17 16 L0 16 Z" fill="{BELLY}"/></g>'
        f'<ellipse {body_e} fill="none" stroke="{ink}" stroke-width="1"/>'
        f'<rect x="5.8" y="9.3" width="1.5" height="2" rx=".5" fill="{INK}"/><rect x="9.7" y="9.3" width="1.5" height="2" rx=".5" fill="{INK}"/>'
        f'<path d="M7.2 11.2 L9.8 11.2 L8.5 14 Z" fill="{BEAK}"/>'
    )
    write(f"icons/fitz-16{suffix}.svg", doc("0 0 16 16", s, "Fitz icon", "Fitz the tailorbird, 16 px icon."))


def mono():
    """One-colour line version; uses currentColor so it can be recoloured."""
    cid = "mono-body"
    cc = "currentColor"
    pieces = tape_pieces()
    hollow = "".join(  # tape as an outlined strip: knock the middle out with a mask
        f'<path d="{qd(p)}" stroke="#000" stroke-width="{TAPE_W - SW2 + 1}" fill="none"/>' for p in pieces
    )
    m = 'maskUnits="userSpaceOnUse" x="-10" y="-10" width="220" height="220"'
    full = '<rect x="-10" y="-10" width="220" height="220" fill="#fff"/>'
    wing_hole = f'<path d="{WING_L}" fill="#000"/><path d="{WING_R}" fill="#000"/>'
    beak_shape = "M90 112.5 Q100 107.5 110 112.5 L102 134.5 Q100 138 98 134.5 Z"
    s = (
        f'<defs><clipPath id="{cid}"><path d="{BODY_PATH}"/></clipPath>'
        f'<clipPath id="{cid}-t"><path d="{BODY_PATH}"/><rect x="60" y="150" width="80" height="50"/></clipPath>'
        f'<mask id="{cid}-tape" {m}>{full}{hollow}{wing_hole}</mask>'
        f'<mask id="{cid}-out" {m}>{full}<path d="{BODY_PATH}" fill="#000"/></mask>'
        f'<mask id="{cid}-edge" {m}>{full}{wing_hole}<path d="{beak_shape}" fill="#000" stroke="#000" stroke-width="7"/></mask></defs>'
        f'<g fill="none" stroke="{cc}" stroke-width="{SW}" stroke-linecap="round" stroke-linejoin="round">'
        + feet().replace(INK, cc)
        + f'<path d="{TAIL_PATH}" mask="url(#{cid}-out)"/>'
        f'<path d="{BODY_PATH}" mask="url(#{cid}-edge)"/>'
        f'<path d="{WING_L}" stroke-width="{SW2}"/><path d="{WING_R}" stroke-width="{SW2}"/>'
        f'<g clip-path="url(#{cid})"><path d="{cap_path()}" fill="{cc}" stroke="none" mask="url(#{cid}-edge)"/></g>'
        f'<g clip-path="url(#{cid}-t)"><g mask="url(#{cid}-tape)">'
        + "".join(f'<path d="{qd(p)}" stroke-width="{TAPE_W + SW2}" stroke-linecap="butt"/>' for p in pieces)
        + "</g></g></g>"
        f'<ellipse cx="76" cy="{EYE_Y}" rx="6.8" ry="8.3" fill="{cc}"/>'
        f'<ellipse cx="124" cy="{EYE_Y}" rx="6.8" ry="8.3" fill="{cc}"/>'
        f'<path d="{beak_shape}" fill="none" stroke="{cc}" stroke-width="{SW2}" stroke-linejoin="round"/>'
    )
    write("fitz-mono.svg", doc(VIEW, s, "Fitz, one colour", "Fitz the tailorbird as a one-colour line drawing."))
    # 32 px mono icon: outlined body and wings; solid cap, tail, eyes and beak
    s = (
        f'<defs><clipPath id="m32"><path d="{I32_BODY}"/></clipPath>'
        f'<mask id="m32b" maskUnits="userSpaceOnUse" x="0" y="0" width="32" height="32"><rect width="32" height="32" fill="#fff"/>'
        f'<path d="{I32_BEAK}" fill="#000" stroke="#000" stroke-width="2.4"/></mask></defs>'
        f'<g fill="{cc}">'
        f'<path d="{I32_TAIL}"/>'
        f'<path clip-path="url(#m32)" mask="url(#m32b)" d="{I32_CAP}"/>'
        '<ellipse cx="12" cy="19.6" rx="1.4" ry="1.75"/><ellipse cx="20" cy="19.6" rx="1.4" ry="1.75"/>'
        f'<path d="{I32_BEAK}"/></g>'
        f'<g fill="none" stroke="{cc}" stroke-linejoin="round"><path d="{I32_BODY}" stroke-width="2"/>'
        '<path d="M8 22.5 C 10 23.5, 10.2 26.8, 8.5 28.2 C 7.3 29.2, 5.3 29, 3.4 28.6 C 5 26.8, 5.5 23.2, 8 22.5 Z" stroke-width="1.2"/>'
        '<path d="M24 22.5 C 22 23.5, 21.8 26.8, 23.5 28.2 C 24.7 29.2, 26.7 29, 28.6 28.6 C 27 26.8, 26.5 23.2, 24 22.5 Z" stroke-width="1.2"/></g>'
    )
    write("icons/fitz-mono-32.svg", doc("0 0 32 32", s, "Fitz icon, one colour", "Fitz silhouette, one colour."))


if __name__ == "__main__":
    build_main()
    build_expressions()
    build_states()
    for ink, suffix in ((INK, ""), (BELLY, "-dark")):
        icon_64(ink, suffix)
        icon_32(ink, suffix)
        icon_16(ink, suffix)
    mono()
